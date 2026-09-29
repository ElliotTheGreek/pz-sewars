--[[ Sewars -- the authority: who may climb, what gets built, who gets rescued.

    Runs in single player and on any server (never on a client). A client
    asks by completing SEWClimb (SEW_Actions.lua), whose complete() runs
    here, or by the `rescue` command; this file answers with `go`, and the
    client moves its own character (DEV_GUIDE, "The server owns the sewers;
    a client asks").

    Three jobs:

      grant   a climb, checked against the server's own copy of the climber:
              standing within reach of the cover (or the ladder), at the right
              level, and the cover leads somewhere. Down, the tunnel under it
              is built first -- all of it is loaded, because the climber is
              standing over it -- and only then is the move sent, so the floor
              reaches the client before the client steps onto it.
      build   every few ticks, the chunks round each player below ground,
              nearest first, a couple a tick (DEV_GUIDE, "Slice any search").
      rescue  a player below with no floor under them -- a save from before
              a chunk was built, or a fall -- is sent to the nearest ladder.
              Never left to fall (DEV_GUIDE, "Never let a failure strand the
              player").
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Net"
require "SEW/SEW_Sewer"
require "SEW/SEW_Build"
require "SEW/SEW_Discovery"
require "SEW/SEW_Story"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local Net = SEW.Net
local S = SEW.Sewer
local B = SEW.Build

local Server = {}
SEW.Server = Server

local function nameOf(p)
    return U.try("username", function() return p:getUsername() end) or "player"
end

local function refuse(player, why)
    U.log("refused %s: %s", nameOf(player), why)
    Net.toClient(player, "refused", { why = why })
    return false
end

--- A climb, down a cover or up a ladder. Called from SEWClimb:complete().
function Server.grant(player, x, y, mode)
    x, y = math.floor(tonumber(x) or 0), math.floor(tonumber(y) or 0)
    local shaft = S.shaftAt(x, y)
    if not shaft then return refuse(player, "shut") end

    if mode == "down" then
        if S.below(player) then return refuse(player, "level") end
        if not S.within(player, x, y, C.Reach + 1.0) then return refuse(player, "reach") end
        local done, left = B.around(x, y, C.EntryRadiusChunks)
        if not B.isCurrent(math.floor(x / 8) .. "," .. math.floor(y / 8)) then
            return refuse(player, "unready")
        end
        SEW.Discovery.ladder(player, x, y)
        U.log("%s climbs down at %d,%d (%s; %d chunks built, %d waiting)",
              nameOf(player), x, y, shaft.town, done, left)
        Net.toClient(player, "go", { x = x, y = y, z = C.Z, street = shaft.street or "", mode = "down" })
        return true
    elseif mode == "up" then
        if not S.below(player) then return refuse(player, "level") end
        if not (S.within(player, shaft.x, shaft.y, C.Reach + 1.0)
                or S.within(player, shaft.lx, shaft.ly, C.Reach + 1.0)) then
            return refuse(player, "reach")
        end
        SEW.Discovery.ladder(player, x, y)
        U.log("%s climbs out at %d,%d (%s)", nameOf(player), x, y, shaft.town)
        Net.toClient(player, "go", { x = x, y = y, z = 0, street = shaft.street or "", mode = "up" })
        return true
    end
    return refuse(player, "mode")
end

--- A client below ground found no floor under its player.
Net.onServer("rescue", function(player, args)
    if not S.below(player) then return end
    local px = U.try("px", function() return player:getX() end) or 0
    local py = U.try("py", function() return player:getY() end) or 0
    -- The floor may simply not be built yet: build here first, and only move
    -- the player if there is still nothing under them.
    B.around(px, py, 1)
    local sq = U.square(px, py, C.Z, false)
    if sq and U.floorOf(sq) then
        Net.toClient(player, "go", { x = math.floor(px), y = math.floor(py), z = C.Z, mode = "hold" })
        return
    end
    local shaft, d = S.nearestShaft(px, py, 400)
    if shaft then
        B.around(shaft.x, shaft.y, 1)
        U.log("rescue: %s had no floor at %d,%d; sent to the ladder at %d,%d (%d squares)",
              nameOf(player), px, py, shaft.x, shaft.y, d)
        Net.toClient(player, "go", { x = shaft.x, y = shaft.y, z = C.Z, street = shaft.street, mode = "rescue" })
    else
        U.log("WARN rescue: %s below ground at %d,%d with no sewer in reach; sent up", nameOf(player), px, py)
        Net.toClient(player, "go", { x = math.floor(px), y = math.floor(py), z = 0, mode = "rescue" })
    end
end)

---------------------------------------------------------------------------
-- Building round players below
---------------------------------------------------------------------------
local ticks = 0
local function service()
    ticks = ticks + 1
    if ticks % C.BuildEveryTicks ~= 0 then return end
    local players = U.players()
    -- Discovery first, for everyone: the build loop below stops when its budget
    -- is spent, and a player later in the list must not miss what they walk into.
    for _, p in ipairs(players) do
        if S.below(p) then U.try("discover", SEW.Discovery.look, p) end
    end
    local budget = C.BuildChunksPerTick
    for _, p in ipairs(players) do
        if budget <= 0 then return end
        if S.below(p) then
            local px = U.try("px", function() return p:getX() end)
            local py = U.try("py", function() return p:getY() end)
            if px and py then
                for _, pend in ipairs(B.pending(px, py, C.BuildRadiusChunks)) do
                    if budget <= 0 then break end
                    if B.chunk(pend.key) then budget = budget - 1 end
                end
            end
        end
    end
end
Events.OnTick.Add(function() U.try("service", service) end)

Events.OnGameStart.Add(function()
    local towns, shafts = 0, 0
    for _ in pairs(SEW.Data or {}) do towns = towns + 1 end
    for _ in pairs(SEW.Index and SEW.Index.shafts or {}) do shafts = shafts + 1 end
    U.log("Sewars %s: %d towns, %d shafts, layout %s", C.Version, towns, shafts,
          tostring(SEW.Index and SEW.Index.rev))
    if towns == 0 then U.log("WARN no sewer data loaded: server/SEW/Data is missing from the install") end
end)
if isServer() then
    Events.OnServerStarted.Add(function()
        local towns = 0
        for _ in pairs(SEW.Data or {}) do towns = towns + 1 end
        U.log("Sewars %s on a server: %d towns", C.Version, towns)
    end)
end

---------------------------------------------------------------------------
-- Debug console (single player, or an admin's server log)
---------------------------------------------------------------------------
--- Where you are, the nearest shaft, and whether the tunnel here is built.
function SEW_Here()
    local p = U.players()[1]
    if not p then return end
    local px, py, pz = p:getX(), p:getY(), p:getZ()
    local key = math.floor(px / 8) .. "," .. math.floor(py / 8)
    local shaft, d = S.nearestShaft(px, py)
    U.log("here %.1f,%.1f,%.1f chunk %s town %s built %s; nearest shaft %s at %s squares (%s)",
          px, py, pz, key, tostring(B.townOf(key)), tostring(B.state().built[key]),
          shaft and (shaft.x .. "," .. shaft.y) or "none", d and math.floor(d) or "-",
          shaft and shaft.street or "")
end

--- Builds everything within r chunks of you now (r defaults to 3).
function SEW_Build(r)
    local p = U.players()[1]
    if not p then return end
    local done, left = B.around(p:getX(), p:getY(), r or 3)
    U.log("SEW_Build: %d chunks built, %d not loaded", done, left)
end

--- Forgets which chunks are built, so the next pass revisits all of them
--- (hull only: furniture and the dead are never placed twice).
function SEW_Rebuild()
    B.state().built = {}
    U.log("SEW_Rebuild: every chunk will be revisited")
end

return Server
