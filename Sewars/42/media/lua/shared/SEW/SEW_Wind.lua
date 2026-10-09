--[[ Sewars -- no wind in the sewer.

    Runs in every process. A server (and single player) is where a player's
    body is simulated (BodyDamage.Update returns at once on a client); a
    client is where its own wind chill moodle is worked out. Each needs the
    same answer, and neither is told the other's.

    Asked by a player (on 0.7.5, playing with cold mods): "could you make it so
    the sewers protect from windchill?" What the engine does (42.21.0):

        ClimateManager.getAirTemperatureForSquare(square, vehicle, wind)
          6-22     square.isInARoom(), or a vehicle: the indoor sums, no wind
          245-258  else, when asked with the wind: Temperature.WindchillCelsiusKph
          260-295  then, room or not: IsoCell.getHeatSourceHighestTemperature,
                   and the higher of the two is the answer
        IsoGridSquare.isInARoom    a room, or a player-built region with a roof
        Thermoregulator.update     asks twice a pass, without the wind and with it
        Temperature.getWindChillAmountForPlayer   the moodle: the same question

    A square of ours has no room and will not get one (DEV_GUIDE, *A square
    of ours keeps no room on a server*), so to the engine a culvert a storey
    under the road is a hilltop. There is no flag for it and no Lua in the
    way: it is Java asking Java. The one thing that overrules the wind is a
    heat source:

        getHeatSourceHighestTemperature(air, x, y, z)   for each source at that level:
          87-180   off = air - 30, kept to -15..5 (the source's square not in a room)
          182-211  t = lerp(1 - distance / radius, air, source + off)
          213-286  taken when higher than what is had, nearer than the radius, in sight

    So each player in the sewer has a heat source on the square they stand on,
    radius 1 (that square and no other: distance 0 is the only one under 1),
    at the still air's temperature plus the 15 the engine takes off again. In
    air at or under 15 C that comes to the still air's temperature rounded
    down (a source holds whole degrees): asked without the wind the answer is
    what it was, asked with it the answer is at most a degree under that.
    **It warms nobody.** Above 15 C the engine's 15 becomes something else and
    the two questions would stop agreeing, so nothing is done there.

    A heat source is a line in the cell's list on this machine: nothing in
    the world, nothing sent, nothing saved. It is moved with the player (there
    is no setter for where it is: taken away and made again), and taken away
    when they climb out, sit in a car, step into a room or leave.

    IsoHeatSource is exposed to Lua (LuaManager$Exposer) and addHeatSource /
    removeHeatSource are IsoCell's own public calls, but no vanilla Lua makes
    one in this build (its campfires are Java now). **Unplayed**: the first
    call the engine refuses is the last one tried. C.Wind.shelter = false
    turns it all off.
]]

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Sewer"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local S = SEW.Sewer

local Wd = {}
SEW.Wind = Wd

-- By player: the heat source that stands for the still air round them, where
-- it is and what it holds.
Wd.held = {}
-- Set when the engine refused one of the calls: no second try this session.
Wd.broken = false

local function who(p)
    return p:getUsername() or ("player " .. tostring(p:getPlayerNum()))
end

--- Where a player's still air goes and what it holds, or nil when the wind is
--- the engine's business: not in the sewer, in a car, in a room, or a day too
--- warm for the sums to hold.
function Wd.want(p)
    if not C.Wind.shelter or not S.inSewer(p) then return nil end
    if p:getVehicle() then return nil end
    local sq = p:getCurrentSquare()
    if not sq or sq:isInARoom() then return nil end
    local air = getClimateManager():getTemperature()
    if air > C.Wind.warmest then return nil end
    return sq:getX(), sq:getY(), math.floor(air) + C.Wind.lift
end

function Wd.drop(name)
    local h = Wd.held[name]
    if not h then return false end
    Wd.held[name] = nil
    getCell():removeHeatSource(h.src)
    return true
end

--- One player: their source made, moved, kept in step with the air, or taken
--- away. Returns true when they have one after it.
function Wd.serve(p)
    local name = who(p)
    local x, y, t = Wd.want(p)
    local h = Wd.held[name]
    if h and (x ~= h.x or y ~= h.y) then
        Wd.drop(name)
        h = nil
    end
    if not x then return false end
    if not h then
        local src = IsoHeatSource.new(x, y, C.Z, 1, t)
        getCell():addHeatSource(src)
        Wd.held[name] = { src = src, x = x, y = y, t = t }
    elseif h.t ~= t then
        h.src:setTemperature(t)
        h.t = t
    end
    return true
end

--- Every player this machine answers for; and nobody who has gone keeps one.
function Wd.pass()
    local here = {}
    for _, p in ipairs(U.players()) do
        here[who(p)] = true
        Wd.serve(p)
    end
    local gone = {}
    for name in pairs(Wd.held) do
        if not here[name] then gone[#gone + 1] = name end
    end
    for _, name in ipairs(gone) do Wd.drop(name) end
end

local tick = 0
Events.OnTick.Add(function()
    tick = tick + 1
    if Wd.broken or tick % C.Wind.every ~= 0 then return end
    local ok, err = pcall(Wd.pass)
    if not ok then
        Wd.broken = true
        U.warnOnce("wind", "the sewer keeps the street's wind: %s", tostring(err))
    end
end)

return Wd
