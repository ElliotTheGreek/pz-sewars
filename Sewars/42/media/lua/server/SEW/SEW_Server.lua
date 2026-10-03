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
      rescue  a player in the sewer with no floor under them -- a save from
              before a chunk was built, or a fall -- is sent to the nearest
              ladder. Never left to fall (DEV_GUIDE, "Never let a failure
              strand the player"). Only in the sewer: never out of a
              basement or a bunker (Server.ours).
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Net"
require "SEW/SEW_Sewer"
require "SEW/SEW_Build"
require "SEW/SEW_Discovery"
require "SEW/SEW_Story"
require "SEW/SEW_Nest"
require "SEW/SEW_Gas"
require "SEW/SEW_Keys"
require "SEW/SEW_Maps"
require "SEW/SEW_Mine"
require "SEW/SEW_Rooms"

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

    -- A hatch leads anywhere only once its house has been found clear (SEW_Build.hatch).
    if shaft.hatch and B.hatch(shaft) ~= "open" then return refuse(player, "shut") end
    -- And a cover of ours only once it is in the road.
    if shaft.made and B.cover(shaft) ~= "placed" then return refuse(player, "shut") end

    if mode == "down" then
        if S.below(player) then return refuse(player, "level") end
        if not S.within(player, x, y, C.Reach + 1.0) then return refuse(player, "reach") end
        local done, left = B.around(x, y, C.EntryRadiusChunks)
        if not B.isCurrent(math.floor(x / 8) .. "," .. math.floor(y / 8)) then
            return refuse(player, "unready")
        end
        -- Nobody is sent onto a square the engine has left a room on (SEW_Rooms).
        SEW.Rooms.around(x, y, C.Rooms.reach + 1)
        SEW.Discovery.ladder(player, x, y)
        U.log("%s climbs down at %d,%d (%s; %d chunks built, %d waiting)",
              nameOf(player), x, y, shaft.town, done, left)
        Net.toClient(player, "go", { x = x, y = y, z = C.Z, street = shaft.street or "", mode = "down",
                                     hatch = shaft.hatch ~= nil or shaft.trapdoor == true,
                                     outfall = shaft.outfall == true })
        return true
    elseif mode == "up" then
        if not S.below(player) then return refuse(player, "level") end
        if not (S.within(player, shaft.x, shaft.y, C.Reach + 1.0)
                or S.within(player, shaft.lx, shaft.ly, C.Reach + 1.0)) then
            return refuse(player, "reach")
        end
        SEW.Discovery.ladder(player, x, y)
        U.log("%s climbs out at %d,%d (%s)", nameOf(player), x, y, shaft.town)
        Net.toClient(player, "go", { x = x, y = y, z = 0, street = shaft.street or "", mode = "up",
                                     hatch = shaft.hatch ~= nil or shaft.trapdoor == true,
                                     outfall = shaft.outfall == true })
        return true
    end
    return refuse(player, "mode")
end

--- True when a player with no floor under them is the sewer's to rescue: on
--- its level, and either standing on no square at all (nobody's basement has
--- one of those) or on a bare square in or beside a chunk the sewer has
--- squares in. A basement's stairs, a bunker fourteen levels down and a
--- cellar another mod dug are none of our business (found by players: each
--- was "rescued" to a ladder or to the street).
function Server.ours(player, px, py)
    if not S.below(player) then return false end
    local sq = U.try("square", function() return player:getCurrentSquare() end)
    if not sq then return true end
    if U.try("sq.z", function() return sq:getZ() end) ~= C.Z or B.foreign(sq) then return false end
    local cx, cy = math.floor(px / 8), math.floor(py / 8)
    for dx = -1, 1 do
        for dy = -1, 1 do
            local key = (cx + dx) .. "," .. (cy + dy)
            if B.townOf(key) or B.state().dug[key] then return true end
        end
    end
    return false
end

--- A client below ground found no floor under its player.
Net.onServer("rescue", function(player, args)
    local px = U.try("px", function() return player:getX() end) or 0
    local py = U.try("py", function() return player:getY() end) or 0
    if not Server.ours(player, px, py) then return end
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
        SEW.Rooms.around(shaft.x, shaft.y, C.Rooms.reach + 1)
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
-- Every hatch and every cover of ours in the index, listed once.
local surfaceList = nil
--- What the server puts in at street level near a player there, each once:
--- the trapdoors of houses with a way down (SEW_Build.hatch, which may leave
--- one shut) and the covers of ours in the towns the map gives few
--- (SEW_Build.cover).
function Server.hatches(p)
    if not surfaceList then
        surfaceList = {}
        for _, s in pairs(SEW.Index and SEW.Index.shafts or {}) do
            if s.hatch or s.made then surfaceList[#surfaceList + 1] = s end
        end
    end
    local st = B.state()
    local px, py = p:getX(), p:getY()
    for _, s in ipairs(surfaceList) do
        local key = s.x .. "," .. s.y
        if math.abs(s.x - px) <= C.HatchRange and math.abs(s.y - py) <= C.HatchRange then
            if s.hatch and not st.hatches[key] then B.hatch(s)
            elseif s.made and not st.covers[key] then B.cover(s) end
        end
    end
end

local ticks = 0
local function service()
    ticks = ticks + 1
    if ticks % C.BuildEveryTicks ~= 0 then return end
    local players = U.players()
    -- Discovery first, for everyone: the build loop below stops when its budget
    -- is spent, and a player later in the list must not miss what they walk into.
    for _, p in ipairs(players) do
        if S.below(p) then U.try("discover", SEW.Discovery.look, p) else U.try("hatches", Server.hatches, p) end
    end
    -- Whoever a set piece is owed (SEW_Build.setPiece), now that nobody is near.
    U.try("settle", B.settle)
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

--- The houses with a way down in a town, and whether each is open yet.
function SEW_Hatches(town)
    local st = B.state().hatches
    for _, s in pairs(SEW.Index.shafts) do
        if s.hatch and (not town or s.town == town) then
            U.log("hatch %d,%d (%s, %s): %s", s.x, s.y, s.town, s.hatch, tostring(st[s.x .. "," .. s.y] or "not looked at"))
        end
    end
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
