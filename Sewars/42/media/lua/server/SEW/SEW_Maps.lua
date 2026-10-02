--[[ Sewars -- annotated maps to the temple and to the nest, and how they get about.

    Runs in single player and on any server (never on a client).

    The maps themselves are the game's (shared/StashDescriptions/
    SewarsStashDesc.lua): an ordinary map item, turned into an "Annotated
    Map" by the engine's own StashSystem.doStashItem -- stamps, handwriting,
    name -- exactly as vanilla's loot does it. doStashItem is static, takes
    any MapItem, and checks no role (bytecode: it throws only for an item
    that is not a map); its one Lua caller in vanilla is the debug stash
    window, which is a debug window by its Lua, not by the method.

    The engine will not hand ours out (they have no building: see the stash
    file), so this does, four ways:

      loot     wherever the game fills a container with loot and a map is in
               it (OnFillContainer: houses, cars, the dead's pockets), now
               and then that map is one of ours instead of a plain one. This
               is how they are found above ground, anywhere in the world;
      crates   now and then in a shelter's or hideout's crate, when it is
               first stocked (SEW_Build.furnish): new shelters only;
      the dead now and then on one of the dead below ground (OnZombieDead,
               after the engine has emptied the inventory: DEV_GUIDE, *The
               dead carry what OnZombieDead gives them*);
      placed   one of each where the other place's people would have had it:
               the nest's in the temple's scriptorium, the temple's in the
               warren (the generator's `m1` / `m2`, SEW_Story.stockExtras).

    Vanilla's sandbox option *Annotated map chance* set to None turns the
    first three off.
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Sewer"
require "SEW/SEW_Build"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local B = SEW.Build

local M = {}
SEW.Maps = M

M.WHICH = { "temple", "nest" }

-- full type -> true, for every map item the loot may hold.
local plain = nil
local function isPlainMap(item)
    if not plain then
        plain = {}
        for _, id in ipairs(C.Maps.items) do plain[id] = true end
    end
    local full = U.try("map.type", function() return item:getFullType() end)
    return full ~= nil and plain[full] == true
end

--- False when the save's sandbox has annotated maps turned off (1: None).
function M.allowed()
    local v = SandboxVars and tonumber(SandboxVars.AnnotatedMapChance)
    return v ~= 1
end

--- Turns a plain map item into the annotated map to "temple" or "nest".
--- Returns true when it is one now.
function M.annotate(item, which)
    local m = C.Maps[which]
    if not m or not item then return false end
    return U.try("map.annotate", function()
        local stash = StashSystem.getStash(m.stash)
        if not stash then
            U.warnOnce("map.stash:" .. m.stash, "no stash description named %s", m.stash)
            return false
        end
        StashSystem.doStashItem(stash, item)
        return item:getStashMap() == m.stash
    end) == true
end

--- A new annotated map to "temple" or "nest", or nil.
function M.make(which)
    local m = C.Maps[which]
    if not m then return nil end
    local item = U.try("map.make", function() return instanceItem(m.item) end)
    if not item then
        U.warnOnce("map.item:" .. tostring(m.item), "could not make %s", tostring(m.item))
        return nil
    end
    if not M.annotate(item, which) then return nil end
    return item
end

--- The game has just filled a container with loot: a plain map in it is,
--- now and then, one of ours. Returns how many were.
function M.onFill(roomName, containerType, container)
    if not container or not M.allowed() then return 0 end
    local items = U.try("fill.items", function() return container:getItems() end)
    local n = items and items:size() or 0
    local made = 0
    for i = 0, n - 1 do
        local item = items:get(i)
        if item and isPlainMap(item) and not U.try("fill.stash", function() return item:getStashMap() end)
                and ZombRand(1000) < C.Maps.loot * 1000 then
            if M.annotate(item, M.WHICH[ZombRand(#M.WHICH) + 1]) then made = made + 1 end
        end
    end
    return made
end

--- A shelter's or hideout's crate, as it is first stocked: now and then a
--- map, by where the crate stands (the same in every world, like its loot).
function M.crate(container, x, y)
    if not container or not M.allowed() then return false end
    local roll = U.rng(U.hash(x, y, 71))
    if roll(1000) > C.Maps.crate * 1000 then return false end
    local item = M.make(M.WHICH[roll(#M.WHICH)])
    return item ~= nil and U.try("crate.map", function() container:AddItem(item); return true end) == true
end

--- One of the dead below ground: now and then it carried a map.
function M.onDead(z)
    if not z or not M.allowed() then return false end
    if (U.try("z.z", function() return z:getZ() end) or 0) > -0.5 then return false end
    if ZombRand(1000) >= C.Maps.dead * 1000 then return false end
    local inv = U.try("z.inv", function() return z:getInventory() end)
    local item = inv and M.make(M.WHICH[ZombRand(#M.WHICH) + 1])
    return item ~= nil and U.try("z.map", function() inv:AddItem(item); return true end) == true
end

Events.OnFillContainer.Add(function(...) U.try("maps.fill", M.onFill, ...) end)
Events.OnZombieDead.Add(function(z) U.try("maps.dead", M.onDead, z) end)

return M
