--[[ Sewars -- reading what was left down here: plans and journals.

    ROADMAP: story told through the map. The generator (tools/gen_sewers.py
    story()) put one journal in every shelter and a sewer plan in maintenance
    rooms and pump stations; SEW_Build stamps each item with its index into
    SEW.Index.journals / .plans (mod data SewarsJournal / SewarsPlan) as it
    stocks the container.

    A client asks with the item's id (`readPlan`, `readJournal`), the way
    vanilla's own server commands name an item (ClientCommands.lua:407,
    getItemWithID). The server finds it **in that player's own inventory** --
    a client cannot read a plan it is not carrying -- and does the one thing
    reading does: a plan reveals its sheet (SEW.Discovery.reveal), a journal
    puts its mark on the reader's map (SEW.Discovery.mark). Reading the same
    journal twice marks nothing new; the text is the client's to show.
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Net"
require "SEW/SEW_Discovery"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local Net = SEW.Net

local St = {}
SEW.Story = St

--- The item with this id in the player's inventory (or a bag in it), if it is
--- of this full type.
function St.carried(player, id, fullType)
    local inv = U.try("inventory", function() return player:getInventory() end)
    if not inv or not id then return nil end
    -- getItemWithID is vanilla's own (ClientCommands.lua:407); the recursive
    -- one (for a plan in a bag) is public with no vanilla call site, so second.
    local it = U.try("byId", function() return inv:getItemWithID(id) end)
        or U.try("byIdDeep", function() return inv:getItemWithIDRecursiv(id) end)
    if not it then return nil end
    if U.try("fullType", function() return it:getFullType() end) ~= fullType then return nil end
    return it
end

function St.readPlan(player, id)
    local it = St.carried(player, id, C.PlanItem)
    if not it then return nil end
    local idx = U.try("plan.md", function() return it:getModData().SewarsPlan end)
    local plan = idx and SEW.Index.plans[idx]
    if not plan then
        U.warnOnce("plan:" .. tostring(idx), "a sewer plan with no sheet (%s)", tostring(idx))
        return nil
    end
    local t = SEW.Index.towns[plan.town]
    local x0, y0 = t.x0 + plan.i * C.MapTile, t.y0 + plan.j * C.MapTile
    local n = SEW.Discovery.reveal(player, plan.town, x0, y0, x0 + C.MapTile - 1, y0 + C.MapTile - 1)
    -- The county knew where the gas lies: every stretch on the sheet.
    for i, g in ipairs(SEW.Index.gas or {}) do
        if g.town == plan.town and g.x >= x0 and g.x < x0 + C.MapTile and g.y >= y0 and g.y < y0 + C.MapTile then
            SEW.Discovery.gas(player, i)
        end
    end
    U.log("%s read the sewer plan of %s, sheet %d-%d: %d chunks revealed",
          SEW.Discovery.nameOf(player), plan.town, plan.i, plan.j, n)
    Net.toClient(player, "planRead", { n = n })
    return n
end

function St.readJournal(player, id)
    local it = St.carried(player, id, C.JournalItem)
    if not it then return nil end
    local idx = U.try("journal.md", function() return it:getModData().SewarsJournal end)
    local j = idx and SEW.Index.journals[idx]
    if not j then
        U.warnOnce("journal:" .. tostring(idx), "a journal with no entry (%s)", tostring(idx))
        return nil
    end
    return SEW.Discovery.mark(player, "j" .. idx, j.x, j.y, j.kind)
end

Net.onServer("readPlan", function(player, args) St.readPlan(player, tonumber(args.id)) end)
Net.onServer("readJournal", function(player, args) St.readJournal(player, tonumber(args.id)) end)

--- The items a stocked container's `extra` asks for ("j3;p1"), made and put in.
--- Called by SEW_Build while the container is still being built, so they go
--- to clients inside the object.
function St.stockExtras(container, extra)
    local n = 0
    for code in string.gmatch(extra or "", "[^;]+") do
        local kind, idx = code:sub(1, 1), tonumber(code:sub(2))
        local full = kind == "j" and C.JournalItem or kind == "p" and C.PlanItem or nil
        local item = full and idx and U.try("extra.make", function() return instanceItem(full) end)
        if kind == "m" and SEW.Maps then
            -- An annotated map (SEW_Maps): m1 to the temple, m2 to the nest.
            local map = SEW.Maps.make(SEW.Maps.WHICH[idx or 0])
            if map and U.try("extra.map", function() container:AddItem(map); return true end) then n = n + 1 end
        elseif item then
            U.try("extra.md", function()
                item:getModData()[kind == "j" and "SewarsJournal" or "SewarsPlan"] = idx
            end)
            if U.try("extra.add", function() container:AddItem(item); return true end) then n = n + 1 end
        elseif full then
            U.warnOnce("extra:" .. full, "could not make %s", full)
        end
    end
    return n
end

return St
