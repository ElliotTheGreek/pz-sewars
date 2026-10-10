--[[ Sewars -- ground an admin has marked as indoors: a room the engine knows.

    Runs everywhere (shared): a room is each process's own to declare.

    Below the street nothing is indoors to the engine unless it is a room:
    the roof test stops at level 0 (IsoCell.checkHaveRoof), and the regions
    that make a player's own roofed walls a room have no levels under 0 at
    all (IsoGridSquare.getIsoWorldRegion 0-8: z < 0, null). A basement the
    map came with is a room, and indoors; one a player dug, or a tunnel, is
    not -- rain wets whoever stands in it, the air is the street's, the
    game's sounds are the open air's. Everything the mod did about that
    until now answers one asker at a time (SEW_Compat, SEW_Weather, SEW_Wind).

    This is the engine's own answer, for the ground an admin marks: the
    rooms editor the game ships (zombie.buildingRooms.BuildingRoomsEditor,
    exposed to Lua; its own Lua tool calls createBuilding, createRoom and
    addRectangle) makes a real RoomDef in a real BuildingDef, and a square
    whose room has a building is indoors to every reader there is. A room it
    makes is explored and has had its spawn (BRERoom.<init>), so nothing
    spawns in it and nobody's loot is rolled.

    **Three rules, each one a way the engine blanks a room -- and a blanked
    room on a square is what stopped servers in 0.7.2** (DEV_GUIDE, *A square
    of ours keeps no room on a server*, and *A room is declared once*):

      1. Never twice. Declaring a building where one is already is the
         editor's way of replacing it: the old one is cleared, and on a
         server the squares go on pointing at it. So: only where the meta
         grid has no room, and once a process (In.declared).
      2. Never taken away while the world runs. A mark an admin removes is
         forgotten by the next start, not before.
      3. Not "user defined" on a machine that works out regions (single
         player, a client): that pass throws away every user-defined building
         of a map cell whenever anybody builds a wall in it
         (WorldRegionToMetaGrid.removeUserDefinedBuildingsFromCell).

    And on a server a mark made during play is declared at the next start,
    not at once: the editor's tables are written on the main thread while a
    chunk may be loading on another, and vanilla never does that on a server.
    A client and single player declare at once, as vanilla's clients do.

    A mark is a level and a list of rectangles, none of them holding a square
    with a door on its edge (a zombie opens a locked door from a square that
    is not outdoors: SEW_Weather).
]]

require "SEW/SEW_Config"
require "SEW/SEW_Util"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util

local In = {}
SEW.Indoors = In

-- id -> { z = level, rects = { { x, y, w, h }, ... } }: what is marked, as
-- this process knows it. A server's and single player's is the saved state's
-- own table (In.load); a client's is what the server sent.
In.marks = {}
-- id -> true: declared to the engine by this process. Never twice.
In.declared = {}
-- Set when the engine refused: nothing more is declared this session.
In.broken = false
In.made = 0

local CELL = 256

--- The rectangles of a mark, cut at the map's cell borders and grouped by
--- cell: a building is one cell's.
local function byCell(rects)
    local out = {}
    for _, r in ipairs(rects) do
        local x, y, w, h = r[1], r[2], r[3], r[4]
        local yy = y
        while yy < y + h do
            local hh = math.min(y + h, (math.floor(yy / CELL) + 1) * CELL) - yy
            local xx = x
            while xx < x + w do
                local ww = math.min(x + w, (math.floor(xx / CELL) + 1) * CELL) - xx
                local key = math.floor(xx / CELL) .. "," .. math.floor(yy / CELL)
                out[key] = out[key] or {}
                table.insert(out[key], { xx, yy, ww, hh })
                xx = xx + ww
            end
            yy = yy + hh
        end
    end
    return out
end
In.byCell = byCell

--- Declares one mark to the engine, once. `loading`: the world is not up
--- yet (OnLoadMapZones), so the editor must not go looking for squares.
--- Returns how many buildings it made.
function In.declare(id, mark, loading)
    if In.broken or In.declared[id] then return 0 end
    In.declared[id] = true
    local ok, got = pcall(function()
        local ed = BuildingRoomsEditor.getInstance()
        local grid = getWorld():getMetaGrid()
        local made = {}
        local cells = byCell(mark.rects)
        local keys = {}
        for key in pairs(cells) do keys[#keys + 1] = key end
        table.sort(keys)
        for _, key in ipairs(keys) do
            local rects = cells[key]
            local clear = true
            for _, r in ipairs(rects) do
                if grid:getRoomAt(r[1], r[2], mark.z) ~= nil then clear = false end
            end
            -- Rule 1: only where there is no room.
            if clear then
                local b = ed:createBuilding()
                local room = b:createRoom(mark.z)
                room:setName("sewers")
                for _, r in ipairs(rects) do room:addRectangle(r[1], r[2], r[3], r[4]) end
                made[#made + 1] = { b = b, x = rects[1][1], y = rects[1][2] }
            end
        end
        if #made == 0 then return 0 end
        ed:applyChanges(loading == true)
        for _, m in ipairs(made) do
            -- Left in the editor's list, the next applyChanges would declare it again.
            if loading then ed:removeBuilding(m.b) end
            -- Rule 3.
            if not isServer() then
                local def = grid:getRoomAt(m.x, m.y, mark.z)
                if def and def:getBuilding() then def:getBuilding():setUserDefined(false) end
            end
        end
        return #made
    end)
    if not ok then
        In.broken = true
        U.warnOnce("indoors", "the engine would not make a room of marked ground: %s", tostring(got))
        return 0
    end
    In.made = In.made + got
    if got > 0 then U.log("indoors: mark %s declared (%d buildings, level %d)", tostring(id), got, mark.z) end
    return got
end

--- Everything marked and not yet declared by this process.
function In.declareAll(loading)
    local ids = {}
    for id in pairs(In.marks) do ids[#ids + 1] = id end
    table.sort(ids)
    local n = 0
    for _, id in ipairs(ids) do n = n + In.declare(id, In.marks[id], loading) end
    return n
end

-- "z:cx,cy" -> { rects }: where the marks are, by chunk, for the question
-- below. Made again when the marks change (In.touch).
local index = nil
function In.touch() index = nil end

--- The id of the mark x, y at level z is in, or nil.
function In.at(x, y, z)
    if not index then
        index = {}
        for id, m in pairs(In.marks) do
            for _, r in ipairs(m.rects) do
                for cx = math.floor(r[1] / 8), math.floor((r[1] + r[3] - 1) / 8) do
                    for cy = math.floor(r[2] / 8), math.floor((r[2] + r[4] - 1) / 8) do
                        local k = m.z .. ":" .. cx .. "," .. cy
                        index[k] = index[k] or {}
                        table.insert(index[k], { r[1], r[2], r[3], r[4], id })
                    end
                end
            end
        end
    end
    x, y, z = math.floor(x), math.floor(y), math.floor(z)
    local list = index[z .. ":" .. math.floor(x / 8) .. "," .. math.floor(y / 8)]
    if not list then return nil end
    for _, r in ipairs(list) do
        if x >= r[1] and x < r[1] + r[3] and y >= r[2] and y < r[2] + r[4] then return r[5] end
    end
    return nil
end

--- A server's and single player's marks are the saved state's own table.
function In.load()
    if isClient() then return end
    local s = ModData.getOrCreate(C.StateKey)
    s.indoor = s.indoor or {}
    In.marks = s.indoor
    In.touch()
end

-- Before any chunk loads, with the saved state in hand (IsoWorld.init fires
-- this after GlobalModData.init and before the meta grid is read): a
-- server's whole list, and single player's.
if not isClient() then
    Events.OnLoadMapZones.Add(function()
        local ok, err = pcall(function()
            In.load()
            In.declareAll(true)
        end)
        if not ok then U.warnOnce("indoors.load", tostring(err)) end
    end)
end

return In
