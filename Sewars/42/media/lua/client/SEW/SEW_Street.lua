--[[ Sewars -- the street and the sewer do not hear each other.

    To the engine a level is three squares of distance and a floor stops no
    sound (DEV_GUIDE, "The street hears the sewer"): a zombie on the road
    hears a player walking under it and comes to stand over them, and one in
    the tunnel hears a player on the road and comes to stand under them.
    Asked for by players, twice: first the street's side, then (0.7.4) "same
    when I am outside with zombies in sewers". The sandbox's "The street
    hears the sewer" puts the engine's own behaviour back, both ways.

    It runs on a client (single player too) and never on a server, because
    that is where a zombie hears: IsoZombie.RespondToSound returns at once on
    a server and for a zombie this machine does not own. The engine fires
    OnZombieUpdate for each zombie on each update, before its hearing and
    before it acts on what it is after. Then, for a zombie on one side of
    the street's floor:

      heard   on its way to a player's sound on the other side: stopped the
              way the engine stops one itself (RespondToSound, bci 168-188:
              bPathfind and bMoving off, the path dropped)
      seen    after a player who is on the other side (it saw them before
              they climbed, and the engine keeps its memory of a sighting
              for a while): the target is dropped, and it is stopped

    "The other side" is the sewer and nothing else: a square of ours at the
    sewer's level. A basement at that level is not, and the house over it
    goes on hearing what is done there.

    What it does not do: a zombie may still turn its head to the noise; and
    a sound not made by a player -- a bomb -- is heard as before.
]]

if isServer() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Sewer"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local S = SEW.Sewer

local Street = {}
SEW.Street = Street

-- { x, y } for each player this machine knows of who is in the sewer.
-- Empty nearly always, and then a zombie on the street costs one length check.
Street.below = {}
-- The sandbox's Yes, read when the list is written.
Street.off = false

--- The sandbox's "The street hears the sewer": 1 (the default) is no.
function Street.hears()
    return SandboxVars ~= nil and SandboxVars.Sewars ~= nil and tonumber(SandboxVars.Sewars.StreetHears) == 2
end

--- Every player this machine knows: on a client the others too, because the
--- zombies over a player in the sewer may be owned by one on the street.
function Street.players()
    if not isClient() then return U.players() end
    local out = {}
    local list = U.try("getOnlinePlayers", getOnlinePlayers)
    local n = list and list:size() or 0
    for i = 0, n - 1 do
        local p = list:get(i)
        if p then out[#out + 1] = p end
    end
    return out
end

-- A square of ours (SEW_Sewer): a basement at the same level is not, and
-- the house over it must go on hearing what is done there.
local ours = S.ours

--- Who is in the sewer, written down every C.Street.every ticks.
function Street.look()
    local out = {}
    Street.off = Street.hears()
    if not Street.off then
        for _, p in ipairs(Street.players()) do
            if S.below(p) then
                local sq = U.try("street.sq", function() return p:getCurrentSquare() end)
                if sq and ours(sq) then out[#out + 1] = { p:getX(), p:getY() } end
            end
        end
    end
    Street.below = out
    return #out
end

-- As the engine stops one (RespondToSound, bci 168-188).
local function halt(z)
    z:setVariable("bPathfind", false)
    z:setVariable("bMoving", false)
    z:setPath2(nil)
end

-- The player a zombie is after, or nil.
local function prey(z)
    local t = z:getTarget()
    if t ~= nil and instanceof(t, "IsoPlayer") then return t end
    return nil
end

--- A zombie at street level or over it, with somebody in the sewer.
function Street.above(z)
    -- Seen: it is after a player who has gone down.
    local t = prey(z)
    if t ~= nil and S.inSewer(t) then
        z:setTarget(nil)
        halt(z)
        return true
    end
    -- Heard. Cheapest first: nearly every zombie is not on its way to a player's sound.
    if not z:isMovingToPlayerSound() then return false end
    if z:getPathTargetZ() ~= C.Z then return false end
    local tx, ty, r = z:getPathTargetX(), z:getPathTargetY(), C.Street.reach
    local list = Street.below
    for i = 1, #list do
        local p = list[i]
        if math.abs(p[1] - tx) <= r and math.abs(p[2] - ty) <= r then
            halt(z)
            return true
        end
    end
    return false
end

--- A zombie at the sewer's level: after a player up on the street, or on
--- its way to one's noise there. Only one of the sewer's: a basement's dead
--- hear the house over them.
function Street.under(z)
    local t = prey(z)
    local seen = t ~= nil and t:getZ() >= 0
    local heard = z:isMovingToPlayerSound() and z:getPathTargetZ() >= 0
    if not seen and not heard then return false end
    local sq = z:getCurrentSquare()
    if sq == nil or not ours(sq) then return false end
    if seen then z:setTarget(nil) end
    halt(z)
    return true
end

--- One zombie's update. Returns true when it was stopped. No U.try in here:
--- it runs for every zombie on every tick, and the caller's one pcall is the
--- guard (DEV_GUIDE, "Slice any search that touches thousands of squares").
function Street.quiet(z)
    if Street.off then return false end
    local zz = z:getZ()
    if zz >= 0 then
        if #Street.below == 0 then return false end
        -- Somebody else's to decide: the client that owns it runs this too.
        if z:isRemoteZombie() then return false end
        return Street.above(z)
    end
    if math.floor(zz + 0.5) ~= C.Z then return false end
    if z:isRemoteZombie() then return false end
    return Street.under(z)
end

Events.OnZombieUpdate.Add(function(z)
    local ok, err = pcall(Street.quiet, z)
    if not ok then U.warnOnce("street.quiet", tostring(err)) end
end)

local tick = 0
Events.OnTick.Add(function()
    tick = tick + 1
    if tick % C.Street.every == 0 then U.try("street.look", Street.look) end
end)

return Street
