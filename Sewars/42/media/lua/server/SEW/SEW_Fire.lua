--[[ Sewars -- fire does not cross the street's floor.

    Runs in single player and on any server (never on a client).

    Found by a player (0.7.4): "you light the sewers on fire if you burn
    corpses on the streets above the sewer." The engine spreads a fire to one
    of thirteen squares, picked at random: the eight round it, the one over
    it, and four on the level *below* -- with no look at the floor between
    (IsoFire.Spread 84-611: cases at z - 1 for x - 1 and x, y - 1 and y, and
    one at z + 1). Under a vanilla street there is no square to take it. Under
    one of ours there is a tunnel, and CanAddFire asks only that the square
    hold something and is not marked unflamable.

    There is no property to give our squares (it is read off the sprites of
    vanilla's own floor and walls) and no way to stop the roll. But the engine
    says when a fire is made: OnNewFire, from the end of IsoFire's constructor
    (bci 339), before the fire is on its square. So the square is written
    down, and on the next tick a fire that came through the street's floor is
    put out, the way vanilla's own extinguisher does it (ISPutOutFire:
    square:stopFire(), or the global stopFire on a server, which tells the
    clients).

    "Came through the floor" is read from where the fire is, since the
    engine does not say where it came from:

      down   on a square of ours, with a square burning among the four over
             it that could have sent it, and nothing burning beside it in the
             tunnel;
      up     on the street, straight over a burning square of ours, with
             nothing burning beside it on the street.

    A fire lit in the tunnel -- a molotov, a campfire, a player's own
    mistake -- has nothing burning over it, or has its own flames beside it,
    and burns as the game means it to. So does a house over its basement:
    that is no square of ours.
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Sewer"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local S = SEW.Sewer

local F = {}
SEW.Fire = F

-- Fires made since the last tick: { x, y, z } each.
F.pending = {}

--- True when the square at x, y, z is burning.
function F.burning(x, y, z)
    local sq = U.square(x, y, z, false)
    return sq ~= nil and U.try("fire.burning", function() return sq:has(IsoFlagType.burning) end) == true
end

--- True when any of the eight squares round x, y on its own level is burning.
function F.beside(x, y, z)
    for dx = -1, 1 do
        for dy = -1, 1 do
            if (dx ~= 0 or dy ~= 0) and F.burning(x + dx, y + dy, z) then return true end
        end
    end
    return false
end

--- Did the fire at x, y, z come through the street's floor?
function F.across(x, y, z)
    if z == C.Z then
        local sq = U.square(x, y, z, false)
        if not sq or not S.ours(sq) or F.beside(x, y, z) then return false end
        -- The four that spread down onto this one (IsoFire.Spread).
        for dx = 0, 1 do
            for dy = 0, 1 do
                if F.burning(x + dx, y + dy, z + 1) then return true end
            end
        end
        return false
    elseif z == C.Z + 1 then
        local under = U.square(x, y, C.Z, false)
        if not under or not S.ours(under) or not F.burning(x, y, C.Z) then return false end
        return not F.beside(x, y, z)
    end
    return false
end

--- Puts the fire on a square out, as vanilla's extinguisher does.
function F.putOut(sq)
    return U.try("fire.out", function()
        if isServer() then stopFire(sq) else sq:stopFire() end
        return true
    end) == true
end

--- The engine has just made a fire. It is not on its square yet.
function F.onNew(fire)
    if not fire then return end
    -- A campfire's, a fireplace's: lit on purpose, and no spread made it.
    if U.try("fire.permanent", function() return fire:isPermanent() end) == true then return end
    local sq = U.try("fire.square", function() return fire:getSquare() end)
    if not sq then return end
    local z = sq:getZ()
    if z ~= C.Z and z ~= C.Z + 1 then return end
    F.pending[#F.pending + 1] = { sq:getX(), sq:getY(), z }
end

--- Every tick: the fires made since the last one, each looked at once.
--- Returns how many were put out.
function F.settle()
    if #F.pending == 0 then return 0 end
    local list, out = F.pending, 0
    F.pending = {}
    for _, f in ipairs(list) do
        if F.across(f[1], f[2], f[3]) then
            local sq = U.square(f[1], f[2], f[3], false)
            if sq and F.putOut(sq) then
                out = out + 1
                -- Logged, not debug: it is rare, and it is what a report of fire below needs.
                U.log("fire: put out at %s,%s,%s (it came through the street's floor)", f[1], f[2], f[3])
            end
        end
    end
    return out
end

Events.OnNewFire.Add(function(fire) U.try("fire.new", F.onNew, fire) end)
Events.OnTick.Add(function() U.try("fire.settle", F.settle) end)

return F
