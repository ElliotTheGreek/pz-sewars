--[[ Sewars -- the county's maintenance keys: in its rooms, and on its dead.

    Runs in single player and on any server (never on a client). DESIGN.md 7,
    *Locked gates*, is the design; DEV_GUIDE, *A locked gate is a key id and a
    lock set before it is sent*, the engine facts behind it.

    Half the maintenance rooms and pump stations of a town sit behind a
    locked grille (SEW_Build.putDoor), every one keyed to the town
    (SEW.Index.towns[t].key). The key is:

      * in the first crate of each county room that is **not** locked
        (tools/gen_sewers.py key_spots -> T.keys), put in when the room is
        first stocked (SEW_Build.chunk);
      * on some of the dead in sanitation overalls below that town, and some
        of them carry one of its sewer plans -- added when they die
        (OnZombieDead). IsoZombie.onKilled empties the inventory
        (DoZombieInventory) before the event and the corpse takes it after,
        so what is added here lies on the body. Not addItemToSpawnAtDeath:
        that list lives in memory and is gone once the zombie unloads.

    A key opens its town's grilles from the main inventory or a key ring
    only (ItemContainer.haveThisKeyId); its tooltip says so.
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Sewer"
require "SEW/SEW_Build"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local S = SEW.Sewer
local B = SEW.Build

local K = {}
SEW.Keys = K

--- A town's maintenance key, keyed and named, or nil (no such town, or it
--- has no gates).
function K.make(tid)
    local t = SEW.Index and SEW.Index.towns[tid]
    if not t or not t.key then return nil end
    local item = U.try("key.make", function() return instanceItem(C.KeyItem) end)
    if not item then
        U.warnOnce("key.item", "could not make %s", C.KeyItem)
        return nil
    end
    U.try("key.id", function() item:setKeyId(t.key) end)
    local name = getText("IGUI_SEW_KeyName", t.name)
    if name ~= "IGUI_SEW_KeyName" then U.try("key.name", function() item:setName(name) end) end
    return item
end

--- The town's key into the container of ours at x, y below ground (the
--- first crate of an unlocked county room). Returns true when it went in.
function K.stock(x, y, tid)
    local sq = U.square(x, y, C.Z, false)
    local c = nil
    U.eachObject(sq, function(o)
        if U.isOurs(o) then
            c = U.containerOf(o)
            if c then return false end
        end
    end)
    if not c then
        U.warnOnce("key.spot:" .. x .. "," .. y, "no crate of ours at %d,%d for the maintenance key", x, y)
        return false
    end
    local key = K.make(tid)
    return key ~= nil and U.try("key.add", function() c:AddItem(key); return true end) == true
end

--- One of the plans of a town, as an item, or nil.
function K.plan(tid, roll)
    local mine = {}
    for i, pl in ipairs(SEW.Index.plans or {}) do
        if pl.town == tid then mine[#mine + 1] = i end
    end
    if #mine == 0 then return nil end
    local item = U.try("plan.make", function() return instanceItem(C.PlanItem) end)
    if item then U.try("plan.md", function() item:getModData().SewarsPlan = mine[roll(#mine)] end) end
    return item
end

--- A zombie has died: one of the county's sanitation workers, below a town
--- with gates, may carry its key and one of its plans. Returns what it
--- added ("key", "plan", both, or nothing), for the tests and the log.
function K.onDead(z)
    if not z then return nil end
    if (U.try("z.z", function() return z:getZ() end) or 0) > -0.5 then return nil end
    if U.try("z.outfit", function() return z:getOutfitName() end) ~= C.Gates.outfit then return nil end
    local x, y = z:getX(), z:getY()
    local tid = B.townOf(math.floor(x / 8) .. "," .. math.floor(y / 8))
    local t = tid and SEW.Index.towns[tid]
    if not t then return nil end
    local inv = U.try("z.inv", function() return z:getInventory() end)
    if not inv then return nil end
    -- The engine's own dice: a death is a one-off, nothing to reproduce.
    local function roll(n) return ZombRand(n) + 1 end
    local added = {}
    -- The key only where the town has gates; a plan wherever it has plans.
    if t.key and roll(1000) <= C.Gates.keyChance * 1000 then
        local key = K.make(tid)
        if key and U.try("z.key", function() inv:AddItem(key); return true end) then added[#added + 1] = "key" end
    end
    if roll(1000) <= C.Gates.planChance * 1000 then
        local plan = K.plan(tid, roll)
        if plan and U.try("z.plan", function() inv:AddItem(plan); return true end) then added[#added + 1] = "plan" end
    end
    if #added > 0 then U.debug("a sanitation worker below %s died with: %s", tid, table.concat(added, ", ")) end
    return table.concat(added, ",")
end

Events.OnZombieDead.Add(function(z) U.try("keys.dead", K.onDead, z) end)

--- The latch, and the handle on the inside. A key-holder who opens a grille
--- unlocks it (IsoDoor.ToggleDoorActual clears locked and lockedByKey), and a
--- door-opening zombie reads only `locked` (bci 60-117). And nobody below is
--- ever "inside" to the engine (a tunnel is outdoors: canBeOpenFromInside
--- never fires), so a locked grille would shut in a player without the key
--- who followed a key-holder in (trekship DEV_GUIDE, "A door with no handle
--- on the inside"). So every C.Gates.latchEvery ticks, each grille of ours
--- near a player below:
---   * anybody in its room: unlocked, so they can always get out;
---   * shut, and its room empty: locked again, a spring latch.
--- Sent as vanilla's lock action sends it (ISLockDoor:complete,
--- syncIsoObject). Never one standing open, never a door that is not ours
--- or keyed to anything else. Returns how many it locked and unlocked.
function K.latch()
    local players = {}
    for _, p in ipairs(U.players()) do
        if S.below(p) then players[#players + 1] = p end
    end
    if #players == 0 then return 0, 0 end
    local locked, unlocked = 0, 0
    for _, g in ipairs(SEW.Index.gates or {}) do
        local near = false
        for _, p in ipairs(players) do
            if math.abs(p:getX() - g.x) <= C.Gates.latchRange and math.abs(p:getY() - g.y) <= C.Gates.latchRange then
                near = true
                break
            end
        end
        local sq = near and U.square(g.x, g.y, C.Z, false)
        local specials = sq and U.try("gate.specials", function() return sq:getSpecialObjects() end)
        local count = specials and specials:size() or 0
        for i = 0, count - 1 do
            local d = specials:get(i)
            if instanceof(d, "IsoDoor") and U.isOurs(d) and d:getNorth() == (g.edge == "N")
                    and d:getKeyId() == SEW.Index.towns[g.town].key then
                -- The room behind it: the shelter on one side of its edge.
                local room = S.shelterAt(g.x, g.y)
                    or (g.edge == "N" and S.shelterAt(g.x, g.y - 1)) or (g.edge == "W" and S.shelterAt(g.x - 1, g.y))
                local inside = false
                for _, p in ipairs(players) do
                    if room and S.shelterAt(p:getX(), p:getY()) == room then inside = true end
                end
                local want = nil
                if inside and d:isLockedByKey() then
                    want = false
                elseif not inside and not d:IsOpen() and not d:isLockedByKey() then
                    want = true
                end
                if want ~= nil then
                    U.try("gate.latch", function()
                        d:setLockedByKey(want)
                        if isServer() then d:syncIsoObject(false, 0, nil, nil) end
                    end)
                    if want then locked = locked + 1 else unlocked = unlocked + 1 end
                end
            end
        end
    end
    return locked, unlocked
end

local ticks = 0
Events.OnTick.Add(function()
    ticks = ticks + 1
    if ticks % C.Gates.latchEvery == 0 then U.try("keys.latch", K.latch) end
end)

--- Debug console: a town's locked gates and its key.
function SEW_Gates(town)
    local p = U.players()[1]
    local here = p and B.townOf(math.floor(p:getX() / 8) .. "," .. math.floor(p:getY() / 8))
    town = town or here
    local t = SEW.Index.towns[town or ""]
    U.log("%s: key %s", tostring(town), tostring(t and t.key or "none"))
    for i, g in ipairs(SEW.Index.gates or {}) do
        if g.town == town then U.log("gate %d at %d,%d (%s edge)", i, g.x, g.y, g.edge) end
    end
end

--- Debug console: the key of the town you are in (or `town`), in your hands.
function SEW_Key(town)
    local p = U.players()[1]
    if not p or isClient() then return end
    town = town or B.townOf(math.floor(p:getX() / 8) .. "," .. math.floor(p:getY() / 8))
    local key = K.make(town or "")
    if key then
        p:getInventory():AddItem(key)
        U.log("SEW_Key: the %s maintenance key", town)
    else
        U.log("SEW_Key: %s has no locked gates", tostring(town))
    end
end

--- Debug console: beside the n-th locked gate, on the tunnel side.
function SEW_GoGate(i)
    local g = (SEW.Index.gates or {})[i or 1]
    local p = U.players()[1]
    if not g or not p or isClient() then return end
    -- The door is on the north or west edge of g.x, g.y; one of the two
    -- squares either side is the tunnel, the other the room.
    local ox, oy = g.x, g.y
    if g.edge == "N" then oy = g.y - 1 else ox = g.x - 1 end
    local sx, sy = ox, oy
    if S.shelterAt(ox, oy) then sx, sy = g.x, g.y end
    B.around(sx, sy, 1)
    U.teleport(p, sx, sy, C.Z)
    U.log("SEW_GoGate: by gate %d (%s) at %d,%d", i or 1, g.town, g.x, g.y)
end

return K
