--[[
GatherMate_SkillRange — show only gathering nodes relevant to your current skill.

A small companion to GatherMate. It reads your live Mining / Herbalism skill and drives
GatherMate's own per-node filters so the map only shows what matters:
  * "gatherable" — hide nodes whose required skill is above yours (declutter)
  * "skillups"   — show only nodes that still grant skill points (req <= skill < req + window)

Non-destructive: your manual Herb/Mine filter choices are snapshotted when a mode turns on and
restored when it's switched off. A node is shown only if (you had it enabled) AND (it's in range).

Reuses three things GatherMate already provides:
  GatherMate.nodeMinHarvest[nodeType][nodeID]  -- required skill per node
  GatherMate.db.profile.filter[nodeType][nodeID] = true/false  -- per-node visibility (true = show)
  the "GatherMateConfigChanged" message          -- forces a map/minimap redraw
]]

local GatherMate = LibStub("AceAddon-3.0"):GetAddon("GatherMate")
local SR = LibStub("AceAddon-3.0"):NewAddon("GatherMate_SkillRange", "AceEvent-3.0", "AceConsole-3.0")

-- localized skill-line name -> GatherMate node type. enUS by default; extend per locale.
local SKILL_TO_TYPE = { ["Mining"] = "Mining", ["Herbalism"] = "Herb Gathering" }

local defaults = { profile = { mode = "off", gray = 100 } }  -- mode: off | gatherable | skillups

local cfg                 -- SavedVariables (AceDB profile)
local baseline = {}       -- baseline[nodeType] = snapshot of the user's explicit filter keys
local active = false      -- are we currently overriding filters?
local curSkill = {}       -- curSkill[nodeType] = effective skill (rank + modifier)

local function readSkills()
	wipe(curSkill)
	for i = 1, GetNumSkillLines() do
		local name, isHeader, _, rank, _, mod = GetSkillLineInfo(i)
		if name and not isHeader and SKILL_TO_TYPE[name] then
			curSkill[SKILL_TO_TYPE[name]] = (rank or 0) + (mod or 0)
		end
	end
end

local function snapshot()
	if active then return end
	wipe(baseline)
	for _, nodeType in pairs(SKILL_TO_TYPE) do
		local snap = {}
		local f = GatherMate.db.profile.filter[nodeType]
		if f then for nid, v in pairs(f) do snap[nid] = v end end  -- only the user's explicit keys
		baseline[nodeType] = snap
	end
	active = true
end

local function restore()
	if not active then return end
	for nodeType, snap in pairs(baseline) do
		local f = GatherMate.db.profile.filter[nodeType]
		local nm = GatherMate.nodeMinHarvest and GatherMate.nodeMinHarvest[nodeType]
		if f and nm then
			-- nil reverts to GatherMate's ["*"]=true default; explicit user choices are put back
			for nid in pairs(nm) do f[nid] = snap[nid] end
		end
	end
	active = false
	GatherMate:SendMessage("GatherMateConfigChanged")
end

local function inRange(nodeType, nodeID)
	local skill = curSkill[nodeType]
	if not skill then return false end  -- you don't have the profession -> can't gather it
	local nm = GatherMate.nodeMinHarvest[nodeType]
	local req = (nm and nm[nodeID]) or 1
	if cfg.mode == "gatherable" then
		return skill >= req
	elseif cfg.mode == "skillups" then
		return skill >= req and skill < req + (cfg.gray or 100)
	end
	return true
end

local function apply()
	if not cfg or cfg.mode == "off" then restore(); return end
	snapshot()
	readSkills()
	for _, nodeType in pairs(SKILL_TO_TYPE) do
		local f = GatherMate.db.profile.filter[nodeType]
		local nm = GatherMate.nodeMinHarvest and GatherMate.nodeMinHarvest[nodeType]
		local snap = baseline[nodeType]
		if f and nm then
			for nodeID in pairs(nm) do
				local base = snap[nodeID]
				if base == nil then base = true end  -- ["*"]=true default
				f[nodeID] = (base and inRange(nodeType, nodeID)) or false
			end
		end
	end
	GatherMate:SendMessage("GatherMateConfigChanged")
end
SR.Apply = apply

local options = {
	type = "group", name = "Skill Range",
	args = {
		desc = { type = "description", order = 0, fontSize = "medium",
			name = "Show only gathering nodes relevant to your current Mining / Herbalism skill.\n" },
		mode = { type = "select", order = 1, name = "Mode", width = "full",
			values = {
				off        = "Off — show everything",
				gatherable = "Only what I can gather (hide nodes above my skill)",
				skillups   = "Only nodes that skill me up",
			},
			sorting = { "off", "gatherable", "skillups" },
			get = function() return cfg.mode end,
			set = function(_, v) cfg.mode = v; apply() end },
		gray = { type = "range", order = 2, name = "Skill-up window", min = 25, max = 150, step = 5,
			desc = "In skill-up mode, stop showing a node once your skill is this far above its requirement (gathering nodes go grey at +100).",
			disabled = function() return cfg.mode ~= "skillups" end,
			get = function() return cfg.gray end,
			set = function(_, v) cfg.gray = v; apply() end },
	},
}

function SR:OnInitialize()
	self.db = LibStub("AceDB-3.0"):New("GatherMate_SkillRangeDB", defaults, true)
	cfg = self.db.profile
	self:RegisterChatCommand("gmsr", function(arg)
		arg = (arg or ""):lower():match("^(%S*)")
		if arg == "off" or arg == "gather" or arg == "gatherable" then
			cfg.mode = (arg == "off") and "off" or "gatherable"
		elseif arg == "skillup" or arg == "skillups" then
			cfg.mode = "skillups"
		else  -- no arg: cycle
			cfg.mode = (cfg.mode == "off" and "gatherable") or (cfg.mode == "gatherable" and "skillups") or "off"
		end
		self:Print("skill filter: " .. cfg.mode)
		apply()
	end)
end

function SR:OnEnable()
	-- add our panel to GatherMate's own config (defensive — Config may not be present)
	local Config = GatherMate.GetModule and GatherMate:GetModule("Config", true)
	if Config and Config.RegisterModule then pcall(function() Config:RegisterModule("skillrange", options) end) end
	self:RegisterEvent("SKILL_LINES_CHANGED", function() if cfg.mode ~= "off" then apply() end end)
	self:RegisterEvent("PLAYER_ENTERING_WORLD", function() apply() end)
	apply()
end
