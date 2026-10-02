--[[ Sewars -- what the two annotated maps show: a sheet of the game's own map.

    A map item is drawn by LootMaps.Init[<its stash name>] if there is one,
    else by LootMaps.Init[<its map id>] (ISMapDefinitions.lua, LootMaps
    .callLua) -- which is how vanilla's own annotated maps show a few streets
    round their X rather than the whole of Muldraugh (LootMaps.Init
    .MulStashMap1). Ours do the same: the game's map data and style, cut to
    the fields round the temple's trapdoor, and to the blocks round the nest's
    manhole. The marks on them are the stash's (shared/StashDescriptions/
    SewarsStashDesc.lua).

    The world map (M) asks the same function for the bounds of every
    annotated map the character has read, to show where each is.
]]

if isServer() then return end

require "ISUI/Maps/ISMapDefinitions"
require "SEW/SEW_Config"

SEW = SEW or {}
local C = SEW.Config

local Sheets = {}
SEW.MapSheets = Sheets

--- The init function of one sheet: vanilla's data and style, our bounds.
function Sheets.init(b)
    return function(mapUI)
        local mapAPI = mapUI.javaObject:getAPIv1()
        MapUtils.initDirectoryMapData(mapUI, LootMaps.DEFAULT_MAP_DIRECTORY)
        MapUtils.initDefaultStyleV3(mapUI)
        mapAPI:setBoundsInSquares(b[1], b[2], b[3], b[4])
        MapUtils.overlayPaper(mapUI)
    end
end

if LootMaps and LootMaps.Init then
    for _, which in ipairs({ "temple", "nest" }) do
        local m = C.Maps[which]
        LootMaps.Init[m.stash] = Sheets.init(m.bounds)
    end
end

return Sheets
