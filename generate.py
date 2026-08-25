#!/usr/bin/env python3
"""
AzerothCore -> GatherMate (1) gathering-database generator.

Reads the live AzerothCore `gameobject` spawn table and emits GatherMate_Data-format Lua
(MiningData / HerbalismData / TreasureData) covering every zone (vanilla + TBC + WotLK, since
the 3.3.5 world DB contains them all). Output drops straight into the GatherMate_Data companion
addon, which exposes it through GatherMate's native Import UI (with a per-expansion filter).

Linkage:  gameobject.zoneId == WorldMapArea.dbc areaID -> zone rect ; WorldMapArea map name ==
          GatherMate1 Constants.lua zoneData key -> GatherMate internal zoneID.
Packing (GatherMate.lua:152):  id = floor(x*10000+0.5)*10000 + floor(y*10000+0.5)
Transform: nx = (locLeft - worldY)/(locLeft-locRight) ; ny = (locTop - worldX)/(locTop-locBottom)
Format:    GatherMateDataMineDB = { [zoneID] = { [packed] = nodeID, ... }, ... }
"""
import math, os, re, struct, sys
import mysql.connector

DB = dict(host="127.0.0.1", port=3306, user="acore", password="acore", database="acore_world")
HERE = os.path.dirname(os.path.abspath(__file__))
# defaults; override the GatherMate install + output dir via argv if needed
GATHERMATE = os.path.expanduser("~/Downloads/WoW-Client-3.3.5a/Interface/AddOns/GatherMate")
CONSTANTS_LUA = os.path.join(GATHERMATE, "Constants.lua")
WMA_DBC = os.path.expanduser("~/hearthforge/azerothcore/run/data/dbc/WorldMapArea.dbc")
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out", "GatherMate_Data")

# category -> (lua filename, global var, extras global var). Gas/Fish are kept from the
# upstream Wowhead data (AzerothCore doesn't expose them as static nodes), so we only
# generate these three. The extras var holds, per pooled location, the other nodes that
# share the exact same spawn point (so a tooltip can list "also here" precisely).
EMIT = {
    "Mining":         ("MiningData.lua",     "GatherMateDataMineDB",     "GatherMateDataMineExtraDB"),
    "Herb Gathering": ("HerbalismData.lua",  "GatherMateDataHerbDB",     "GatherMateDataHerbExtraDB"),
    "Treasure":       ("TreasureData.lua",   "GatherMateDataTreasureDB", "GatherMateDataTreasureExtraDB"),
}


def load_node_ids(path):
    txt = open(path, encoding="utf-8").read()
    name_to, cat = {}, None
    cats = "Mining|Herb Gathering|Treasure|Extract Gas|Fishing"
    for line in txt.splitlines():
        mcat = re.search(r'\["(%s)"\]\s*=\s*\{' % cats, line)
        if mcat:
            cat = mcat.group(1); continue
        if cat is None or re.match(r'\s*--', line):
            continue
        m = re.search(r'NL\["([^"]+)"\]\]\s*=\s*(\d+)', line)
        if m:
            name_to[m.group(1)] = (cat, int(m.group(2)))
        if re.match(r'\s*\}', line):
            cat = None
    return name_to


def load_rare_spawns(path):
    """Parse GatherMate's `rare_spawns` table (Constants.lua).

    Maps a rare node ID to the set of base node IDs it replaces (e.g. Silver
    Vein 204 -> {Tin 202, Iron 203}). Pooled server spawns that share one spot
    must collapse to the BASE node, never the rare one.
    """
    txt = open(path, encoding="utf-8").read()
    out, in_block = {}, False
    for line in txt.splitlines():
        if re.search(r'local\s+rare_spawns\s*=\s*\{', line):
            in_block = True
            continue
        if not in_block:
            continue
        m = re.match(r'\s*\[(\d+)\]\s*=\s*\{([^}]*)\}', line)
        if m:
            bases = {int(b) for b in re.findall(r'\[(\d+)\]\s*=\s*true', m.group(2))}
            out[int(m.group(1))] = bases
            continue
        if re.match(r'\s*\}', line):
            break
    return out


def resolve_node(candidates, rare_spawns, freq):
    """Collapse pooled spawns that share one physical spot into a single node.

    A rare node (Silver/Gold/Truesilver vein, Khorium, ...) that sits on the
    same coordinate as the base node it replaces (Iron/Tin, Mithril, ...) is
    dropped in favour of that base node, matching GatherMate's runtime
    `Collector.rareNodes` logic. Any residual collision is settled by server
    spawn frequency (most common wins), then by lowest node ID.
    """
    present = set(candidates)
    while True:
        dropped = {n for n in present
                   if n in rare_spawns and (rare_spawns[n] & present)}
        if not dropped:
            break
        present -= dropped
    if len(present) == 1:
        return next(iter(present))
    return max(present, key=lambda n: (freq.get(n, 0), -n))


def load_zonedata(path):
    txt = open(path, encoding="utf-8").read()
    out = {}
    for m in re.finditer(
            r'(?m)^\s*(?:\["([^"]+)"\]|([A-Za-z][\w]*))\s*=\s*\{\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*(\d+)', txt):
        name, w = (m.group(1) or m.group(2)), float(m.group(3))
        if w > 100:
            out[name] = int(m.group(5))
    return out


def load_worldmaparea(path, zone_by_name):
    d = open(path, "rb").read()
    _, nrec, _, recsize, _ = struct.unpack_from("<4sIIII", d, 0)
    base = 20
    sb = d[base + nrec * recsize:]
    def s(off):
        e = sb.find(b"\x00", off); return sb[off:e].decode("utf-8", "replace")
    out = {}
    for i in range(nrec):
        off = base + i * recsize
        _, _, areaID = struct.unpack_from("<III", d, off)
        nameOff, = struct.unpack_from("<I", d, off + 12)
        L, R, T, B = struct.unpack_from("<ffff", d, off + 16)
        gm = zone_by_name.get(s(nameOff))
        if gm is not None and areaID > 0:
            out[areaID] = (L, R, T, B, gm)
    return out


def main():
    node_ids = load_node_ids(CONSTANTS_LUA)
    rare_spawns = load_rare_spawns(CONSTANTS_LUA)
    area_map = load_worldmaparea(WMA_DBC, load_zonedata(CONSTANTS_LUA))

    conn = mysql.connector.connect(**DB)
    cur = conn.cursor()
    cur.execute("""SELECT gt.name, g.zoneId, g.position_x, g.position_y
                   FROM gameobject g JOIN gameobject_template gt ON gt.entry = g.id
                   WHERE gt.type = 3""")
    rows = cur.fetchall()
    conn.close()

    # data[category][zoneID][packed] = set of candidate node IDs, collapsed to one below
    data = {c: {} for c in EMIT}
    freq = {}  # nodeID -> total server spawn count (for rare-vs-base tiebreaks)
    per_zone, off_map, no_zone, no_name = {}, 0, 0, 0
    for name, zoneId, wx, wy in rows:
        info = node_ids.get(name)
        if not info or info[0] not in EMIT:
            no_name += 1; continue
        z = area_map.get(zoneId)
        if z is None:
            no_zone += 1; continue
        L, R, T, B, gm = z
        nx = (L - float(wy)) / (L - R)
        ny = (T - float(wx)) / (T - B)
        if not (0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0):
            off_map += 1; continue
        packed = math.floor(nx * 10000 + 0.5) * 10000 + math.floor(ny * 10000 + 0.5)
        cat, nid = info
        data[cat].setdefault(gm, {}).setdefault(packed, set()).add(nid)
        freq[nid] = freq.get(nid, 0) + 1

    # Pooled spawns (e.g. an ore pool holding Iron + Silver + Gold at one spot)
    # collapse to a single node per physical location; the base node wins. The
    # nodes folded away are recorded per location so a tooltip can list exactly
    # what else spawns there.
    extras = {c: {} for c in EMIT}
    collapsed = 0
    for cat in data:
        for gm in data[cat]:
            per_zone[gm] = per_zone.get(gm, 0) + len(data[cat][gm])
            for packed, ids in list(data[cat][gm].items()):
                if len(ids) > 1:
                    collapsed += 1
                n = resolve_node(ids, rare_spawns, freq)
                data[cat][gm][packed] = n
                rest = sorted(ids - {n})
                if rest:
                    extras[cat].setdefault(gm, {})[packed] = rest
    if collapsed:
        print(f"  collapsed {collapsed} pooled spawns (rare node folded into its base node)")

    os.makedirs(OUT_DIR, exist_ok=True)
    total = 0
    for cat, (fname, var, extra_var) in EMIT.items():
        lines = ["-- AzerothCore gathering data generated by Hearthforge. Do not edit by hand.",
                 f"{var} = {{"]
        cnt = 0
        for zid in sorted(data[cat]):
            lines.append(f"[{zid}] = {{")
            for packed in sorted(data[cat][zid]):
                lines.append(f"[{packed}] = {data[cat][zid][packed]},")
                cnt += 1
            lines.append("},")
        lines.append("}")
        if extras[cat]:
            lines.append(f"{extra_var} = {{")
            for zid in sorted(extras[cat]):
                lines.append(f"[{zid}] = {{")
                for packed in sorted(extras[cat][zid]):
                    lines.append(f"[{packed}] = {{ " + ", ".join(str(x) for x in extras[cat][zid][packed]) + " },")
                lines.append("},")
            lines.append("}")
        open(os.path.join(OUT_DIR, fname), "w").write("\n".join(lines) + "\n")
        total += cnt
        print(f"  {var:26s} {cnt:6d} nodes / {len(data[cat])} zones -> {fname}")

    print(f"  scanned {len(rows)} chests | skipped: name={no_name} zone={no_zone} off-map={off_map}")
    print(f"  zones with data: {len(per_zone)} | TOTAL nodes: {total}")
    print(f"  -> {OUT_DIR}")


if __name__ == "__main__":
    main()
