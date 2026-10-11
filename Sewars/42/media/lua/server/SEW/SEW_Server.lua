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
require "SEW/SEW_Fire"

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

--- Where the server has a player, for the log on both machines: a refusal
--- that turns on it ("level", "reach") says what it was judged from.
local function whereIs(player)
    return U.try("where", function()
        return string.format("%.1f,%.1f,%.1f", player:getX(), player:getY(), player:getZ())
    end) or "?"
end

local function refuse(player, why)
    local at = whereIs(player)
    U.log("refused %s: %s (at %s)", nameOf(player), why, at)
    Net.toClient(player, "refused", { why = why, at = at })
    return false
end

local ticks = 0
-- username -> { x, y, mode, at }: the climb last granted. The same one asked
-- again inside C.ClimbRepeat ticks, by a player who has since made it -- the
-- action's own half, and then the client's command because the answer was
-- slow -- is answered once, and not with a refusal for standing where the
-- first answer put them. A player back where they started is asking anew.
Server.granted = {}

local function repeated(player, x, y, mode, z)
    local g = Server.granted[nameOf(player)]
    return g ~= nil and g.x == x and g.y == y and g.mode == mode and g.z == z and ticks - g.at < C.ClimbRepeat
        and Server.at(player, z) == (mode == "down")
end

--- True when the server has the player at level z (0: the street).
function Server.at(player, z)
    local pz = U.try("getZ", function() return player:getZ() end) or 0
    return pz < z + 0.5 and pz >= z - 0.5
end

--- A climb, down a cover or up a ladder. Called from SEWClimb:complete(),
--- and from the `climb` command a client sends when that went unanswered.
--- `z`: the level of the shaft's foot, when not the sewers' own (an admin's
--- shaft down from a tunnel: SEW_Works).
function Server.grant(player, x, y, mode, z)
    x, y = math.floor(tonumber(x) or 0), math.floor(tonumber(y) or 0)
    z = math.floor(tonumber(z) or C.Z)
    if not S.isLevel(z) then return refuse(player, "level") end
    if repeated(player, x, y, mode, z) then return true end
    local shaft = S.shaftAt(x, y, z)
    if not shaft then return refuse(player, "shut") end
    local access = S.accessMode(B.state().access, x, y, z)

    -- A hatch leads anywhere only once its house has been found clear (SEW_Build.hatch).
    if shaft.hatch and B.hatch(shaft) ~= "open" then return refuse(player, "shut") end
    -- And a cover of ours only once it is in the road.
    if shaft.made and B.cover(shaft) ~= "placed" then return refuse(player, "shut") end

    if mode == "down" then
        -- The labyrinth's way out is a way out: its hatch has no handle on top.
        if shaft.exit then return refuse(player, "sealed") end
        if not Server.at(player, z + 1) then return refuse(player, "level") end
        -- A way down an admin has closed, or one no admin has opened on a
        -- server whose sandbox closes them all.
        if not S.mayEnter(access) and not S.isAdmin(player) then return refuse(player, "closed") end
        if not S.within(player, x, y, C.Reach + 1.0) then return refuse(player, "reach") end
        -- A kerb drain: not where the sandbox bolts them down (an admin's
        -- own way in still), and not for anybody too big for it or carrying
        -- too much, admin or not (S.fits; DESIGN.md 7j).
        if shaft.drain then
            if not S.drainsOpen() and not S.isAdmin(player) then return refuse(player, "drainoff") end
            local why = S.fits(player, "down")
            if why then return refuse(player, why) end
        end
        local done, left = B.around(x, y, C.EntryRadiusChunks)
        if not B.isCurrent(math.floor(x / 8) .. "," .. math.floor(y / 8)) then
            return refuse(player, "unready")
        end
        -- Nobody is sent onto a square the engine has left a room on (SEW_Rooms).
        SEW.Rooms.around(x, y, C.Rooms.reach + 1, z)
        SEW.Discovery.ladder(player, x, y, z)
        U.log("%s climbs down at %d,%d to level %d (%s; %d chunks built, %d waiting)",
              nameOf(player), x, y, z, shaft.town, done, left)
        Server.granted[nameOf(player)] = { x = x, y = y, z = z, mode = mode, at = ticks }
        Net.toClient(player, "go", { x = x, y = y, z = z, street = shaft.street or "", mode = "down",
                                     hatch = shaft.hatch ~= nil or shaft.trapdoor == true,
                                     outfall = shaft.outfall == true, drain = shaft.drain == true })
        return true
    elseif mode == "up" then
        if not Server.at(player, z) then return refuse(player, "level") end
        -- A way an admin has made no way out. Their own choice for this one,
        -- never the sandbox's (S.accessMode): nobody is shut in by a setting.
        if not S.mayLeave(access) and not S.isAdmin(player) then return refuse(player, "noexit") end
        if not (S.within(player, shaft.x, shaft.y, C.Reach + 1.0)
                or S.within(player, shaft.lx, shaft.ly, C.Reach + 1.0)) then
            return refuse(player, "reach")
        end
        -- Up a kerb drain's ladder only what is carried counts: it can be
        -- put down. Never the body, and never the sandbox's Drains: a
        -- setting closes no way out.
        if shaft.drain then
            local why = S.fits(player, "up")
            if why then return refuse(player, why) end
        end
        SEW.Discovery.ladder(player, x, y, z)
        U.log("%s climbs out at %d,%d to level %d (%s)", nameOf(player), x, y, z + 1, shaft.town)
        Server.granted[nameOf(player)] = { x = x, y = y, z = z, mode = mode, at = ticks }
        Net.toClient(player, "go", { x = x, y = y, z = z + 1, street = shaft.street or "", mode = "up",
                                     hatch = shaft.hatch ~= nil or shaft.trapdoor == true,
                                     outfall = shaft.outfall == true, drain = shaft.drain == true })
        return true
    end
    return refuse(player, "mode")
end

---------------------------------------------------------------------------
-- Which ways down are open (0.8.1)
---------------------------------------------------------------------------
--- True when the way down at x, y is a way in for players, as the server has it.
function Server.open(x, y, z)
    return S.mayEnter(S.accessMode(B.state().access, x, y, z))
end

--- Everything an admin has decided, to one player's client (so its menu
--- can grey a closed cover out before anybody lifts it), or to everybody.
function Server.publishAccess(player)
    local list = {}
    for k, v in pairs(B.state().access) do list[k] = v end
    if player then
        Net.toClient(player, "access", { list = list })
        return
    end
    for _, p in ipairs(U.players()) do Net.toClient(p, "access", { list = list }) end
end

--- An admin decides who may use one way down: `mode` is "open" (both
--- ways), "in", "shut" (a way out only) or "none". Only what differs from
--- the sandbox is kept. Returns true when it was done.
function Server.setAccess(player, x, y, mode, z)
    if not S.isAdmin(player) then return refuse(player, "admin") end
    x, y = math.floor(tonumber(x) or 0), math.floor(tonumber(y) or 0)
    z = math.floor(tonumber(z) or C.Z)
    local shaft = S.shaftAt(x, y, z)
    -- Not the labyrinth's way out: that one opens for nobody from above.
    if not shaft or shaft.exit then return refuse(player, "shut") end
    if mode ~= "open" and mode ~= "in" and mode ~= "shut" and mode ~= "none" then return refuse(player, "mode") end
    local marks, key = B.state().access, S.shaftKey(x, y, z)
    marks[key] = nil
    if S.accessMode(marks, x, y, z) ~= mode then marks[key] = mode end
    U.log("%s made the way down at %d,%d,%d %s (%s)", nameOf(player), x, y, z, mode, shaft.town)
    Server.publishAccess(nil)
    Net.toClient(player, "accessSet", { x = x, y = y, z = z, mode = mode })
    return true
end

Net.onServer("access", function(player, args)
    Server.setAccess(player, args.x, args.y, args.mode, args.z)
end)

--- A client at its start asks what has been decided: where the labyrinth
--- is (SEW_Place: first, the rest is read by it), which ways down are
--- open, the ways down and templates an admin has made, what is marked as
--- indoors (SEW_Works).
Net.onServer("accessAsk", function(player)
    Net.toClient(player, "place", { dx = SEW.Place.dx, dy = SEW.Place.dy })
    Server.publishAccess(player)
    if SEW.Works then
        SEW.Works.publish(player)
        SEW.Works.publishIndoor(player)
    end
end)

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

--- A client whose climb went unanswered asks again (SEW_Client.unanswered).
--- The same request as the action's, checked the same way: a client is a
--- request, never a fact.
Net.onServer("climb", function(player, args)
    U.log("%s asks for the climb %s at %s,%s by command: the action went unanswered",
          nameOf(player), tostring(args.mode), tostring(args.x), tostring(args.y))
    Server.grant(player, args.x, args.y, args.mode, args.z)
end)

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
SEW.Place.onMove(function() surfaceList = nil end)
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

--- True for a player the builder builds round: at the sewers' own level, or
--- under it where an admin's works are (records, not what stands there: the
--- floor may not be built yet).
function Server.under(p)
    if S.below(p) then return true end
    local z = math.floor((U.try("getZ", function() return p:getZ() end) or 0) + 0.5)
    if z == C.Z or not S.isLevel(z) then return false end
    local cx, cy = math.floor(p:getX() / 8), math.floor(p:getY() / 8)
    local deep = B.dugOf(z)
    for dx = -1, 1 do
        for dy = -1, 1 do
            if deep[(cx + dx) .. "," .. (cy + dy)] then return true end
        end
    end
    return false
end

local function service()
    ticks = ticks + 1
    if ticks % C.BuildEveryTicks ~= 0 then return end
    local players = U.players()
    -- Discovery first, for everyone: the build loop below stops when its budget
    -- is spent, and a player later in the list must not miss what they walk into.
    for _, p in ipairs(players) do
        if Server.under(p) then U.try("discover", SEW.Discovery.look, p) else U.try("hatches", Server.hatches, p) end
    end
    -- Whoever a set piece is owed (SEW_Build.setPiece), now that nobody is near.
    U.try("settle", B.settle)
    local budget = C.BuildChunksPerTick
    for _, p in ipairs(players) do
        if budget <= 0 then return end
        if Server.under(p) then
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
