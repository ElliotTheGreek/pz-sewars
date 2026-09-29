--[[ Sewars -- shared helpers.

    Carried over from pz_trekship's TREK_Util.lua, which paid for every line
    of it (its DEV_GUIDE says how): wrapped engine calls, square lookups that
    never hand back an orphan, stocking that proves the container grew.
]]

require "SEW/SEW_Config"

SEW = SEW or {}
local C = SEW.Config

local U = {}
SEW.Util = U

---------------------------------------------------------------------------
-- Logging
---------------------------------------------------------------------------
function U.log(fmt, ...)
    local msg = fmt
    if select("#", ...) > 0 then
        local ok, formatted = pcall(string.format, fmt, ...)
        if ok then msg = formatted end
    end
    print(C.ModPrefix .. " " .. tostring(msg))
end

function U.debug(fmt, ...)
    if C.Debug then U.log(fmt, ...) end
end

-- Noisy the first time, silent afterwards, so a per-tick failure cannot
-- flood console.txt.
local reported = {}
function U.warnOnce(key, fmt, ...)
    if reported[key] then return end
    reported[key] = true
    U.log("WARN (" .. tostring(key) .. ") " .. tostring(fmt), ...)
end

--- For a call repeated over many squares: stops after its first failure. A
--- missing method throws out of Java with a full stack trace **per call**,
--- and in a per-square loop that locks the game (pz_trekship DEV_GUIDE,
--- "Batch anything repeated per square").
function U.batch(label)
    local broken = false
    return function(fn)
        if broken then return nil end
        local ok, result = pcall(fn)
        if not ok then
            broken = true
            U.warnOnce(label, tostring(result))
            return nil
        end
        return result
    end
end

--- For a call that happens once. Returns nil on error -- and a nil from here
--- does not mean "no" (pz_trekship DEV_GUIDE, "A nil from U.try").
function U.try(label, fn, ...)
    local args = { ... }
    local ok, result = pcall(function() return fn(unpack(args)) end)
    if not ok then
        U.warnOnce(label, tostring(result))
        return nil
    end
    return result
end

---------------------------------------------------------------------------
-- The world
---------------------------------------------------------------------------
function U.cell()
    return U.try("getCell", getCell)
end

--- True when the chunk that owns this column is streamed in. Chunks are
--- columns: every level of one shares it, so a player standing on the street
--- has the tunnel's chunk loaded under them.
function U.chunkLoaded(x, y)
    local cell = U.cell()
    if not cell then return false end
    local chunk = U.try("getChunkForGridSquare", function()
        return cell:getChunkForGridSquare(math.floor(x), math.floor(y), 0)
    end)
    return chunk ~= nil
end

--- Grid square lookup. With create=true a square is made if its chunk is
--- loaded -- at z -1 too: IsoChunk.setSquare grows the chunk's level range
--- downward for it (setMinMaxLevel(min(minLevel, z), ...)) -- and nil is
--- returned for an unloaded chunk rather than an orphan square.
function U.square(x, y, z, create)
    x, y, z = math.floor(x), math.floor(y), math.floor(z)
    local cell = U.cell()
    if not cell then return nil end
    local sq = U.try("getGridSquare", function() return cell:getGridSquare(x, y, z) end)
    if sq or not create then return sq end
    if not U.chunkLoaded(x, y) then return nil end
    return U.try("getOrCreateGridSquare", function()
        return cell:getOrCreateGridSquare(x, y, z)
    end)
end

function U.eachObject(sq, fn)
    if not sq then return end
    local objs = U.try("getObjects", function() return sq:getObjects() end)
    if not objs then return end
    local n = U.try("objects.size", function() return objs:size() end) or 0
    for i = 0, n - 1 do
        local o = U.try("objects.get", function() return objs:get(i) end)
        if o and fn(o, i) == false then return end
    end
end

function U.spriteName(o)
    return U.try("spriteName", function()
        local spr = o:getSprite()
        return spr and spr:getName()
    end)
end

function U.findSprite(sq, name)
    local found = nil
    U.eachObject(sq, function(o)
        if U.spriteName(o) == name then
            found = o
            return false
        end
    end)
    return found
end

function U.isOurs(o)
    local md = U.try("md", function() return o:getModData() end)
    return md ~= nil and md[C.Tag] ~= nil
end

function U.floorOf(sq)
    return sq and U.try("getFloor", function() return sq:getFloor() end)
end

---------------------------------------------------------------------------
-- Stocking (pz_trekship TREK_Util, cut down to what shelters need)
---------------------------------------------------------------------------
function U.containerOf(obj)
    if not obj then return nil end
    local c = U.try("getContainer", function() return obj:getContainer() end)
    if c then return c end
    return U.try("getItemContainer", function() return obj:getItemContainer() end)
end

local function sizeOf(container)
    local items = U.try("getItems", function() return container:getItems() end)
    return items and items:size() or 0
end

--- Adds one item and proves the inventory grew. `instanceItem` is the global
--- that exists in build 42 (vanilla calls it in 187 places); the Lua global
--- InventoryItemFactory is null (pz_trekship DEV_GUIDE, "The jar is not the
--- API"). A full container drops what it is handed without a word, so the
--- count is the only answer that cannot lie.
function U.addItem(container, id)
    if not container or not id then return false end
    local before = sizeOf(container)
    local ok = pcall(function()
        local item = instanceItem(id)
        if item then container:AddItem(item) end
    end)
    if ok and sizeOf(container) > before then return true end
    U.warnOnce("item:" .. id, "could not add " .. id)
    return false
end

--- Fills a container to `fraction` of its own capacity by weight, picking
--- from `list` by a rolling position so two crates do not hold the same.
function U.fill(obj, list, fraction, cap, seed)
    local container = U.containerOf(obj)
    if not container or not list or #list == 0 then return 0 end
    fraction, cap = fraction or C.FillFraction, cap or C.FillItemCap
    local capacity = U.try("capacity", function() return container:getCapacity() end) or 0
    local target = capacity > 0 and capacity * fraction or nil
    local start = seed or 0
    local added, taken = 0, 0
    while taken < cap do
        if target then
            local held = U.try("weight", function() return container:getContentsWeight() end) or 0
            if held >= target then break end
        end
        local id = list[((start + taken) % #list) + 1]
        taken = taken + 1
        if U.addItem(container, id) then added = added + 1 end
    end
    return added
end

---------------------------------------------------------------------------
-- Players
---------------------------------------------------------------------------
--- Every player this process looks after: the local one in single player,
--- every connected one on a server.
function U.players()
    local out = {}
    if isServer() then
        local list = U.try("getOnlinePlayers", getOnlinePlayers)
        local n = list and list:size() or 0
        for i = 0, n - 1 do
            local p = list:get(i)
            if p then out[#out + 1] = p end
        end
    else
        for i = 0, 3 do
            local p = U.try("getSpecificPlayer", function() return getSpecificPlayer(i) end)
            if p then out[#out + 1] = p end
        end
    end
    return out
end

--- Moves a character without leaving the old position behind, which the
--- engine otherwise interpolates towards and reads as a fall.
function U.teleport(player, x, y, z)
    if not player then return false end
    return U.try("teleport", function()
        player:setX(x + 0.5)
        player:setY(y + 0.5)
        player:setZ(z)
        player:setLastX(x + 0.5)
        player:setLastY(y + 0.5)
        player:setLastZ(z)
        return true
    end) == true
end

--- The square a right-click landed on, at the player's own level. **Not the
--- objects the menu was handed**: a click resolves to the floor square under
--- the cursor (pz_trekship DEV_GUIDE, "A right-click lands on the floor").
function U.clickedSquare(playerIndex, context, player)
    local z = math.floor(player:getZ())
    local x = U.try("screenToIsoX", function() return screenToIsoX(playerIndex, context.x, context.y, z) end)
    local y = U.try("screenToIsoY", function() return screenToIsoY(playerIndex, context.x, context.y, z) end)
    if not x or not y then return nil end
    return math.floor(x), math.floor(y), z
end

function U.note(player, text, r, g, b)
    if not player or not text then return end
    U.try("haloNote", function() player:setHaloNote(text, r or 200, g or 200, b or 170, 250) end)
end

function U.dist(x1, y1, x2, y2)
    local dx, dy = x1 - x2, y1 - y2
    return math.sqrt(dx * dx + dy * dy)
end

--- A cheap, stable hash of a few integers, the same on every machine, for
--- choices that must come out the same on every build pass.
function U.hash(a, b, c)
    local h = (a or 0) * 73856093 + (b or 0) * 19349663 + (c or 0) * 83492791
    h = h % 2147483647
    if h < 0 then h = -h end
    return h
end

return U
