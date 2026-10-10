--[[ Sewars -- no snow in the sewer.

    Runs in single player and on any client (never on a server): it is about
    what this machine draws.

    Found by two players (0.7.4): "pls fix snow underground". The engine lays
    snow on a square by three things and nothing else -- no level, no roof
    (FBORenderSnow.RenderSnow 156-212, gridSquareIsSnow 71-152):

        no room on the square, the `exterior` flag in its properties, a solid floor

    and every square of ours is flagged exterior, because the flag is "no
    room and no roof" and nothing below the street is ever roofed
    (IsoGridSquare.RecalcProperties 463-531; DEV_GUIDE, *Below ground is
    outdoors to the engine*). The debug option that turns snow off is
    debug-only (Weather.<init>: newDebugOnlyOption), and a room on a square
    of ours is what stopped servers in 0.7.2. That leaves the flag.

    So this takes the flag off: PropertyContainer.unset(IsoFlagType.exterior)
    on the squares of ours round the player, a row of them a tick, and the
    chunk is asked to draw itself again (invalidateRenderChunkLevel, as
    vanilla's furniture cursor does). The engine puts the flag back whenever
    it works a square's properties out again -- something built or broken on
    it or beside it, the chunk loaded again -- and the next pass takes it off
    again; until then that square may show snow.

    **The flag is read by a good deal more than the snow**, which is why it
    is taken off here and not on a server, and why two kinds of square keep
    it:

      * a square with a door on one of its edges. A zombie that can open
        doors opens a *locked* one only when it stands on a square that is
        not exterior (IsoDoor.Thump 61-107: the dead inside a house let
        themselves out). Both squares of every door stay "outdoors", so the
        county's grilles and a player's own locked door hold as they did;
      * a square that is not ours.

    What else changes with it, by the bytecode, for a square of ours on this
    machine: rain's puddles and splashes go the way of the snow
    (IsoPuddlesGeometry.shouldRender, RainManager.AddSplashes); a generator
    below powers the tunnel when the sandbox forbids outdoor ones
    (IsoGridSquare.haveElectricity); the wall cutaway may read a tunnel as a
    room (calculateWallAlphaAndCircleStencil*). Sight is not touched: looking
    up out of level -1 is let through whatever the flag
    (testVisionAdjacent 1029-1044). **Unplayed**: the checklist in DEV_GUIDE
    says what to look at. C.Weather.indoors = false turns it all off.
]]

if isServer() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Sewer"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local S = SEW.Sewer

local W = {}
SEW.Weather = W

-- The row of the window round the player that is looked at next.
W.row = 0
-- Set when the engine refused one of the calls: no second try this session.
W.broken = false
W.cleared = 0

--- True when a door stands on the square's north (north = true) or west
--- (false) edge, or on either (nil).
function W.doorOn(sq, north)
    local list = sq:getSpecialObjects()
    local n = list and list:size() or 0
    for i = 0, n - 1 do
        local o = list:get(i)
        local door = instanceof(o, "IsoDoor") or (instanceof(o, "IsoThumpable") and o:isDoor())
        if door and (north == nil or o:getNorth() == north) then return true end
    end
    return false
end

--- True when one of the square's four edges holds a door. An edge is held by
--- the southern or eastern of its two squares.
function W.byDoor(sq, cell)
    if W.doorOn(sq, nil) then return true end
    local x, y, z = sq:getX(), sq:getY(), sq:getZ()
    local south = cell:getGridSquare(x, y + 1, z)
    if south and W.doorOn(south, true) then return true end
    local east = cell:getGridSquare(x + 1, y, z)
    return east ~= nil and W.doorOn(east, false)
end

--- Takes the exterior flag off one square if it is ours to take. Returns
--- true when it did.
function W.indoors(sq, cell)
    if not sq:has(IsoFlagType.exterior) then return false end
    if not S.ours(sq) or W.byDoor(sq, cell) then return false end
    sq:getProperties():unset(IsoFlagType.exterior)
    sq:invalidateRenderChunkLevel(FBORenderChunk.DIRTY_REDRAW)
    return true
end

--- One row of the window round x, y at the sewer's level. Returns how many
--- squares lost the flag.
function W.sweepRow(x, y, row, z)
    local cell = U.cell()
    if not cell then return 0 end
    local r, n = C.Weather.reach, 0
    local sy = math.floor(y) + row
    for sx = math.floor(x) - r, math.floor(x) + r do
        local sq = cell:getGridSquare(sx, sy, z or C.Z)
        if sq and W.indoors(sq, cell) then n = n + 1 end
    end
    return n
end

--- Every tick, for a player in the sewer: the next rows of the window. A
--- call the engine refuses is refused once, not once a square a tick.
function W.tick(p)
    local level = S.levelOf(p)
    if W.broken or not C.Weather.indoors or not level then return 0 end
    local r, n = C.Weather.reach, 0
    local px, py = p:getX(), p:getY()
    for _ = 1, C.Weather.rows do
        local ok, got = pcall(W.sweepRow, px, py, W.row - r, level)
        if not ok then
            W.broken = true
            U.warnOnce("weather", "the sewer stays outdoors to the weather: %s", tostring(got))
            return n
        end
        n = n + got
        W.row = (W.row + 1) % (2 * r + 1)
    end
    W.cleared = W.cleared + n
    return n
end

Events.OnTick.Add(function()
    local p = getPlayer()
    if p then W.tick(p) end
end)

return W
