--[[ Sewars -- two annotated maps, in the game's own way of making one.

    Vanilla's annotated maps are stash descriptions (StashDescriptions/*.lua):
    a name, the stamps and handwriting on the map, and a building whose
    contents the engine rewrites when the map is read. The engine reads the
    global StashDescriptions once, as a world starts (StashSystem
    .initAllStashes), so a mod's file here is read with vanilla's.

    Ours have **no building**. That is on purpose, and it has two effects
    (zombie.core.stash.StashSystem, read in the bytecode):

      * the engine never hands one out by itself: checkStashItem offers a
        stash only for a map item of its `item` type whose building has a
        room and has not been visited. Ours name an item type nothing spawns
        and no building, so vanilla's own roll never picks them;
      * reading one prepares nothing: prepareBuildingStash finds no room at
        its building and returns. (doBuildingStash, which it would otherwise
        reach, marks a building explored and refills or empties its
        containers: not something to point at somebody's house.)

    So the mod hands them out itself (server/SEW/SEW_Maps.lua), with the
    engine's own StashSystem.doStashItem to turn an ordinary map into one --
    the stamps, the handwriting and the name "Annotated Map" are vanilla's.
    What area each shows is client/SEW/SEW_MapSheets.lua (LootMaps.Init).

    The marks, in world squares, are worked out from SEW.Index: the temple's
    trapdoor, the manhole nearest the nest by the tunnels, the false wall.
]]

require "StashDescriptions/StashUtil"
require "SEW/SEW_Config"
require "SEW/SEW_Index"

SEW = SEW or {}
local C = SEW.Config
local INK = { 0.129, 0.129, 0.129 }
local RED = { 0.55, 0.08, 0.06 }

local T, L = SEW.Index and SEW.Index.temple, SEW.Index and SEW.Index.lair

if T then
    local m = C.Maps.temple
    local stash = StashUtil.newStash(m.stash, "Map", C.Maps.never, "Stash_AnnotedMap")
    -- The trapdoor; the junction to start from, and the way from it.
    stash:addStamp("X", nil, T.tx, T.ty, RED[1], RED[2], RED[3])
    stash:addStamp(nil, "Stash_SEW_Temple_1", T.tx + 14, T.ty - 10, INK[1], INK[2], INK[3])
    stash:addStamp("Circle", nil, m.from[1], m.from[2], INK[1], INK[2], INK[3])
    stash:addStamp("ArrowNorth", nil, m.from[1], math.floor((m.from[2] + T.ty) / 2), INK[1], INK[2], INK[3])
    stash:addStamp(nil, "Stash_SEW_Temple_2", m.from[1] + 14, math.floor((m.from[2] + T.ty) / 2) - 8, INK[1], INK[2], INK[3])
    stash:addStamp(nil, "Stash_SEW_Temple_3", m.bounds[1] + 24, m.bounds[2] + 30, RED[1], RED[2], RED[3])
end

if L then
    local m = C.Maps.nest
    local stash = StashUtil.newStash(m.stash, "Map", C.Maps.never, "Stash_AnnotedMap")
    -- The manhole to go down; below it, where the wall is that is not a wall.
    stash:addStamp("X", nil, L.cx, L.cy, INK[1], INK[2], INK[3])
    stash:addStamp(nil, "Stash_SEW_Nest_1", L.cx - 58, L.cy - 22, INK[1], INK[2], INK[3])
    stash:addStamp("Skull", nil, L.tx, L.ty, RED[1], RED[2], RED[3])
    stash:addStamp(nil, "Stash_SEW_Nest_2", L.tx + 12, L.ty - 6, INK[1], INK[2], INK[3])
    stash:addStamp(nil, "Stash_SEW_Nest_3", m.bounds[1] + 12, m.bounds[4] - 34, RED[1], RED[2], RED[3])
end
