--[[ Sewars -- no square of the sewer's keeps a room on a server.

    Found by players on dedicated servers (0.7.2): "as soon as another
    player enters the sewer the game completely softlocks for everyone",
    and in the server's log, every tick,

        NullPointerException: Cannot read field "def" because
        "zombie.iso.IsoGridSquare.getRoom().building" is null
            at IsoGameCharacter.updateInternal

    Every character's update asks its square for its room and, given one,
    reads room.building.def with no check (the burglar alarm, bci 345-368).
    The exception leaves IsoWorld.update, so nothing after that player is
    updated: the whole server stops, and goes on stopping while they stand
    there. A room with no building is one the engine has blanked
    (IsoRoom.clear) and a square still points at; how a server comes by one
    under a street is not yet known (DEV_GUIDE, "A square of ours keeps no
    room on a server").

    What is known is what the sewer needs: a tunnel is no room. So on a
    server a square of ours has its room taken off -- IsoGridSquare.
    setRoomID(-1), after which getRoom() answers nil whatever the square
    still points at -- at each moment one could come by it or a player could
    step onto it:

      load    the engine reads a chunk from disk and gives each square the
              room the map has at that place (LoadGridsquare)
      build   the builder makes or revisits a square (SEW_Build.square)
      grant   a climb down is granted: the squares at the ladder's foot
      walk    every tick, the squares round each player in the sewer

    Only ours (something of ours on the square, SEW_Sewer.ours): a basement
    at the same level keeps its rooms. And only on a server: in single
    player the engine keeps a square's room in step itself
    (WorldRegionToMetaGrid.updateSquares, which a server never runs).
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Sewer"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local S = SEW.Sewer

local Rooms = {}
SEW.Rooms = Rooms

-- How many rooms have been taken off, for the log and the tests.
Rooms.cleared = 0

--- True where this is done at all: a server, dedicated or hosted.
function Rooms.on()
    return isServer()
end

--- Takes the engine's room off one square of the sewer's. Returns true when
--- there was one. No U.try in here: it runs for every square a server
--- loads, and each caller's one pcall is the guard.
function Rooms.clear(sq)
    if sq == nil or sq:getZ() ~= C.Z then return false end
    if sq:getRoom() == nil then return false end
    if not S.ours(sq) then return false end
    sq:setRoomID(-1)
    Rooms.cleared = Rooms.cleared + 1
    local n = Rooms.cleared
    -- The first, and then now and again: a server's admin can say it happened.
    if n == 1 or n == 10 or n == 100 or n % 1000 == 0 then
        U.log("rooms: the engine had a room on the sewer at %d,%d; taken off (%d so far)", sq:getX(), sq:getY(), n)
    end
    return true
end

--- Every square of ours within `r` of x, y. Returns how many had a room.
function Rooms.around(x, y, r)
    if not Rooms.on() then return 0 end
    local n = 0
    x, y = math.floor(x), math.floor(y)
    for dx = -r, r do
        for dy = -r, r do
            local sq = U.square(x + dx, y + dy, C.Z, false)
            if sq and Rooms.clear(sq) then n = n + 1 end
        end
    end
    return n
end

--- A square the builder has just made or revisited.
function Rooms.built(sq)
    if not Rooms.on() then return false end
    return Rooms.clear(sq)
end

--- A square the engine has just loaded.
function Rooms.loaded(sq)
    if not Rooms.on() then return false end
    return Rooms.clear(sq)
end

--- Round every player in the sewer, every tick: nobody walks faster than
--- C.Rooms.reach squares a tick.
function Rooms.walk()
    if not Rooms.on() then return end
    for _, p in ipairs(U.players()) do
        if S.below(p) then Rooms.around(p:getX(), p:getY(), C.Rooms.reach) end
    end
end

-- On a server only, and not merely a check inside: vanilla keeps
-- LoadGridsquare free of Lua (LoadGridsquarePerformanceWorkaround), and a
-- handler here would cost single player a Lua call for every square it loads.
-- A server fires it for every square with anything on it, at every level the
-- chunk has (IsoChunk.doLoadGridsquare, bci 626-880).
if isServer() then
    Events.LoadGridsquare.Add(function(sq)
        local ok, err = pcall(Rooms.loaded, sq)
        if not ok then U.warnOnce("rooms.loaded", tostring(err)) end
    end)

    Events.OnTick.Add(function()
        local ok, err = pcall(Rooms.walk)
        if not ok then U.warnOnce("rooms.walk", tostring(err)) end
    end)
end

return Rooms
