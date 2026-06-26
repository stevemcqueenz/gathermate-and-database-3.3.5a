# AzerothCore GatherMate Database (3.3.5a)

**GatherMate gathering-node data extracted directly from the AzerothCore world database** —
the *true* server spawn points for mining, herbalism, and treasure, not a Wowhead scrape.
If you play on an AzerothCore 3.3.5a realm, these are the nodes that actually exist on your
server, in every zone.

> **20,324 nodes across 60 zones** — all three expansions, from one 3.3.5a world DB:
>
> | Expansion | Nodes | Zones |
> |---|---|---|
> | Vanilla (Eastern Kingdoms + Kalimdor) | 13,780 | 42 |
> | The Burning Crusade (Outland) | 3,135 | 8 |
> | Wrath of the Lich King (Northrend) | 3,409 | 10 |

## What's inside

| Folder | What it is | Source |
|---|---|---|
| `GatherMate/` | The GatherMate addon (v1, native 3.3.5a) — GPL v2 by kagaro, xinhuan, nevcairiel, ammo, **with one small added feature (Skill range, see below)** | Upstream + this repo |
| `GatherMate_Data/` | Import companion: `MiningData` / `HerbalismData` / `TreasureData` | **Generated from AzerothCore** |
| `GatherMate_Data/GasData.lua`, `FishData.lua` | Gas clouds + fishing pools | Upstream Wowhead data (AzerothCore doesn't expose these as static spawns) |
| `generate.py` | The extractor, for reproducing/updating the data | This repo |

### Added features

A few small GPL modifications to `GatherMate/` (`GatherMate.lua`, `Display.lua`, `Config.lua`,
`GatherMate.toc` + bundled `LibDataBroker-1.1` / `LibDBIcon-1.0`); everything else is unmodified upstream.

**Skill range** — a **Display → "Skill range"** dropdown that filters the map by your live
Mining / Herbalism skill (à la pfQuest):
- *Only what I can gather* — hides nodes whose required skill is above yours.
- *Only nodes that still skill me up* — the band `required ≤ skill < required + window`
  (slider, default 100, where gathering nodes go grey).

It reads your skill through GatherMate's existing (locale-aware) profession detection, gates nodes
in GatherMate's own display iterator, **stacks with** (never overwrites) your manual Herb/Mine
filters, and updates automatically as you level.

**Separate Minimap / World-Map icon scale + opacity** — the single "Icon Scale" and "Icon Alpha"
sliders are split into four (Minimap + World Map for each), so you can, e.g., keep small subtle
minimap pins and large bold world-map ones. Existing settings migrate across automatically.

**Minimap button** — a GatherMate button on the minimap; click it to open the options. Toggle it
under Display → "Minimap button" (or it can be hidden by other minimap-button managers).

## Install

1. Copy `GatherMate/` and `GatherMate_Data/` into your client's `Interface/AddOns/`.
2. Enable both on the character-select **AddOns** screen.
3. In-game: `/gathermate` → **Import** tab → enable **GatherMate_Data**, pick a style
   (**Replace** for a clean import, **Merge** to keep your own finds), optionally tick
   **Expansion only** + choose Vanilla / TBC / WotLK, then **Import**.
4. Open the world map — every herb, vein, and treasure on your realm is now pinned.

## How it's generated

`generate.py` reads two things and needs nothing else:

- the live `acore_world.gameobject` + `gameobject_template` tables (gathering nodes are
  `GAMEOBJECT_TYPE_CHEST`, classified by name via GatherMate's own node-ID table), and
- `WorldMapArea.dbc` from your client data (each zone's world-coordinate rectangle).

Each node's world `(x, y)` is converted into GatherMate's zone-normalized packed coordinate
(`floor(x*10000+0.5)*10000 + floor(y*10000+0.5)`) using its zone's map rectangle, then written
in GatherMate_Data format (`GatherMateDataMineDB[zoneID][packed] = nodeID`). Pooled nodes that
share a spawn point (e.g. Tin/Silver veins) collapse to one entry per physical location.

```sh
python3 generate.py /path/to/output/GatherMate_Data
```

Edit the `DB`, `GATHERMATE`, and `WMA_DBC` paths at the top of `generate.py` for your setup.

## Credits & license

- **GatherMate** © its authors (kagaro, xinhuan, nevcairiel, ammo), GPL v2 — included unmodified.
- **The data** is extracted from AzerothCore's open-source world database.
- This repository is released under the **GPL v2** (see `LICENSE`).
