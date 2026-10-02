--[[ Sewars -- the street does not hear the sewer.

    To the engine a level is three squares of distance and a floor stops no
    sound (DEV_GUIDE, "The street hears the sewer"): a zombie on the road
    hears a player walking under it and comes to stand over them. Asked for
    by a player on a server; the sandbox's "The street hears the sewer" puts
    the engine's own behaviour back.

    It runs on a client (single player too) and never on a server, because
    that is where a zombie hears: IsoZombie.RespondToSound returns at once on
    a server and for a zombie this machine does not own. The engine fires
    OnZombieUpdate for each zombie on each update, before its hearing; a
    zombie at street level that is on its way to a player's sound at the
    sewer's level, near a player who is in the sewer, is stopped the way the
    engine stops one itself (RespondToSound, bci 168-188: bPathfind and
    bMoving off, the path dropped).

    What it does not do: a zombie already chasing somebody it saw keeps
    after them for a few seconds when they climb down (the engine's own
    memory of a sighting, which Lua cannot clear before it is read again);
    a zombie may still turn its head to the noise; and a sound not made by
    a player -- a bomb -- is heard as before.
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
-- Empty nearly always, and then a zombie's update costs one length check.
Street.below = {}

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
    if not Street.hears() then
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

--- One zombie's update. Returns true when it was stopped. No U.try in here:
--- it runs for every zombie on every tick, and the caller's one pcall is the
--- guard (DEV_GUIDE, "Slice any search that touches thousands of squares").
function Street.quiet(z)
    local list = Street.below
    if #list == 0 then return false end
    -- Cheapest first: nearly every zombie is not on its way to a player's sound.
    if not z:isMovingToPlayerSound() then return false end
    if z:getZ() < 0 or z:getPathTargetZ() ~= C.Z then return false end
    -- Somebody else's to decide: the client that owns it runs this too.
    if z:isRemoteZombie() then return false end
    local tx, ty, r = z:getPathTargetX(), z:getPathTargetY(), C.Street.reach
    for i = 1, #list do
        local p = list[i]
        if math.abs(p[1] - tx) <= r and math.abs(p[2] - ty) <= r then
            z:setVariable("bPathfind", false)
            z:setVariable("bMoving", false)
            z:setPath2(nil)
            return true
        end
    end
    return false
end

Events.OnZombieUpdate.Add(function(z)
    if #Street.below == 0 then return end
    local ok, err = pcall(Street.quiet, z)
    if not ok then U.warnOnce("street.quiet", tostring(err)) end
end)

local tick = 0
Events.OnTick.Add(function()
    tick = tick + 1
    if tick % C.Street.every == 0 then U.try("street.look", Street.look) end
end)

return Street
