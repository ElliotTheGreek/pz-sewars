--[[ Sewars -- read-only questions about the sewers, the same answer everywhere.

    Answered from SEW.Index (generated, small, loaded by every process) and
    from what is standing on the squares. Nothing here changes anything.
]]

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Index"
require "SEW/SEW_Place"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util

local S = {}
SEW.Sewer = S

--- True for a level there can be sewer at (C.Levels).
function S.isLevel(z)
    if z == nil then return false end
    for _, l in ipairs(C.Levels) do
        if l == z then return true end
    end
    return false
end

--- What a shaft is kept under: "x,y" for one whose foot is at the sewers'
--- own level -- every one the generator made, as saves and the index name
--- them -- and "x,y,z" for an admin's shaft down to a deeper one.
function S.shaftKey(x, y, z)
    x, y = math.floor(x), math.floor(y)
    if z == nil or math.floor(z + 0.5) == C.Z then return x .. "," .. y end
    return x .. "," .. y .. "," .. math.floor(z + 0.5)
end

-- The ways down an admin has put in (SEW_Works): key -> a shaft like the
-- index's, with `custom` and the level of its foot, `z`. On a server and in
-- single player this is the saved state's own table (SEW_Build.state); a
-- client's is what the server sent (SEW_Admin).
S.custom = {}

--- The shaft whose top is the cover at x, y and whose foot is at level z
--- (the sewers' own when not said): an admin's, or the generator's. Or nil.
function S.shaftAt(x, y, z)
    local key = S.shaftKey(x, y, z)
    local own = S.custom[key]
    if own then return own end
    if z ~= nil and math.floor(z + 0.5) ~= C.Z then return nil end
    return SEW.Index and SEW.Index.shafts[key] or nil
end

--- The town whose sheet of the map x, y is on: the one it is in, else the
--- nearest. For an admin's shaft, which is nobody's.
function S.townAt(x, y)
    local best, bestD = nil, 1e18
    for tid, t in pairs(SEW.Index and SEW.Index.towns or {}) do
        local dx = (x < t.x0) and (t.x0 - x) or (x > t.x1) and (x - t.x1) or 0
        local dy = (y < t.y0) and (t.y0 - y) or (y > t.y1) and (y - t.y1) or 0
        local d = dx * dx + dy * dy
        -- Never by the order of pairs: the smaller id breaks a tie.
        if d < bestD or (d == bestD and tid < best) then best, bestD = tid, d end
    end
    return best
end

--- A Sewars sandbox option, 1..n, the same answer on every machine (a
--- client has the server's sandbox); `default` when the save has none (a
--- world made before the option existed) or it is out of range.
function S.option(name, default, n)
    local v = SandboxVars and SandboxVars.Sewars and SandboxVars.Sewars[name]
    v = tonumber(v)
    if not v or v < 1 or v > n then return default end
    return math.floor(v)
end

--- True for somebody who may open and close the ways into the sewers
--- (0.8.1). On a server or a client: a role with any of the admin's tools,
--- which is what vanilla shows its admin button by (ISEquippedItem:
--- chr:getRole():hasAdminTool()) -- a moderator or a game master counts,
--- where the global isAdmin() is the one default admin role and nobody
--- else. In single player there are no roles: the dev build (until its
--- menu's *Be a player* is chosen, to see a closed cover as one), or -debug.
function S.isAdmin(player)
    if not isClient() and not isServer() then
        return (SEW.Dev == true and SEW.DevPlayer ~= true)
            or (isDebugEnabled ~= nil and isDebugEnabled() == true)
    end
    if player == nil then return false end
    local role = player:getRole()
    return role ~= nil and role:hasAdminTool() == true
end

-- A way down's key (S.shaftKey) -> what an admin has decided for that one,
-- whatever the sandbox says of the rest:
--   "open"  both ways       "in"    a way in only
--   "shut"  a way out only  "none"  closed both ways
-- This table is a client's copy, sent by the server at the start and
-- whenever one changes (SEW_Server: `access`); the server reads its own.
S.access = {}

--- How the way down at x, y (its foot at level z) stands for players: what
--- an admin said of it in `marks`, or else the sandbox's Sewars.Access --
--- Open, or Closed until an admin opens them, which is "shut": **the
--- sandbox never closes a way out**. Only an admin's own choice for one
--- way down does that ("in", "none"), where a server wants a pit.
function S.accessMode(marks, x, y, z)
    local m = marks and marks[S.shaftKey(x, y, z)]
    if m == "open" or m == "shut" or m == "in" or m == "none" then return m end
    return S.option("Access", 1, 2) == 1 and "open" or "shut"
end

--- May a player climb down a way that stands so? And up it?
function S.mayEnter(mode) return mode == "open" or mode == "in" end
function S.mayLeave(mode) return mode == "open" or mode == "shut" end

--- The shaft nearest to x, y within `range`, looking at both the square under
--- the cover and the square its ladder hangs on.
function S.shaftNear(x, y, range, z)
    local best, bestD = nil, (range or 2) + 0.001
    local r = math.ceil(range or 2) + 1
    for dx = -r, r do
        for dy = -r, r do
            local s = S.shaftAt(x + dx, y + dy, z)
            if s then
                local d = math.min(U.dist(x, y, s.x, s.y), U.dist(x, y, s.lx, s.ly))
                if d < bestD then best, bestD = s, d end
            end
        end
    end
    return best
end

--- The nearest shaft to x, y anywhere in `range` squares (a slower walk of
--- the whole index; for rescues, never per tick).
function S.nearestShaft(x, y, range)
    local best, bestD = nil, range or 1e9
    for _, s in pairs(SEW.Index and SEW.Index.shafts or {}) do
        -- Never a hatch's: its ladder is under a house that may have a
        -- basement instead, and its way up may be shut. Never the
        -- labyrinth's way out: its foot is in the heart, which is earned.
        -- Never a kerb drain's: not everybody fits back up one (S.fits).
        if not s.hatch and not s.exit and not s.drain then
            local d = U.dist(x, y, s.x, s.y)
            if d < bestD then best, bestD = s, d end
        end
    end
    return best, bestD
end

--- The hatch in a house's floor nearest to x, y at street level within
--- `slack` squares: the square it is on, or nil. Only a hatch the server has
--- opened is there to find: it places the trapdoor.
function S.hatchNear(x, y, slack)
    local best, bestD = nil, 1e9
    for dx = -slack, slack do
        for dy = -slack, slack do
            local sq = U.square(x + dx, y + dy, 0, false)
            if sq and U.findSprite(sq, C.Sprites.hatch) then
                local d = math.abs(dx) + math.abs(dy)
                if d < bestD then best, bestD = sq, d end
            end
        end
    end
    return best
end

-- chunk key -> { shelter indices touching that chunk }, built once.
local shelterChunks = nil
local function shelterIndex()
    if shelterChunks then return shelterChunks end
    shelterChunks = {}
    for i, h in ipairs(SEW.Index and SEW.Index.shelters or {}) do
        for cx = math.floor(h.x / 8), math.floor((h.x + h.w - 1) / 8) do
            for cy = math.floor(h.y / 8), math.floor((h.y + h.h - 1) / 8) do
                local k = cx .. "," .. cy
                shelterChunks[k] = shelterChunks[k] or {}
                table.insert(shelterChunks[k], i)
            end
        end
    end
    return shelterChunks
end
-- The labyrinth's rooms are where a host put them (SEW_Place).
SEW.Place.onMove(function() shelterChunks = nil end)

--- The index (in SEW.Index.shelters) of the shelter whose floor x, y is on, or nil.
function S.shelterAt(x, y)
    local list = shelterIndex()[math.floor(x / 8) .. "," .. math.floor(y / 8)]
    if not list then return nil end
    for _, i in ipairs(list) do
        local h = SEW.Index.shelters[i]
        if x >= h.x and x < h.x + h.w and y >= h.y and y < h.y + h.h then return i end
    end
    return nil
end

--- One of vanilla's kerb storm drains (DESIGN.md 7j).
function S.isDrain(sq)
    if sq == nil then return false end
    for _, name in ipairs(C.DrainSprites) do
        if U.findSprite(sq, name) ~= nil then return true end
    end
    return false
end

--- Vanilla's cover, one of ours (the towns the map gives few), an
--- outfall's grate in a riverbank, or a kerb storm drain.
function S.isManhole(sq)
    return sq ~= nil and (U.findSprite(sq, C.ManholeSprite) ~= nil or U.findSprite(sq, C.Sprites.cover) ~= nil
                          or U.findSprite(sq, C.Sprites.outfall) ~= nil)
        or S.isDrain(sq)
end

--- The shaft under the kerb drain at x, y: its own, or the one under the
--- grate beside it. Vanilla lays some drains two squares long, and the
--- generator gives a pair one shaft (gen_sewers.kerb_drains). Or nil: a
--- drain too far from any tunnel has none.
function S.drainShaft(x, y)
    local own = S.shaftAt(x, y)
    if own then return own.drain and own or nil end
    for dx = -1, 1 do
        for dy = -1, 1 do
            local s = S.shaftAt(x + dx, y + dy)
            if s and s.drain then return s end
        end
    end
    return nil
end

--- Are the kerb drains a way down at all? The sandbox's Sewars.Drains.
function S.drainsOpen()
    return S.option("Drains", 1, 2) == 1
end

--- Why a character does not fit through a kerb drain, or nil when they do:
--- "big" (the body: the game's own weight, at or over its line for
--- Overweight) or "load" (carrying too much). By the sandbox's
--- Sewars.DrainFit: 1 anybody fits, 2 not the overweight or the overloaded
--- (the default), 3 only the slim and the lightly loaded.
--- **The body is asked on the way down only.** A load can be put down at
--- the foot of the ladder; a body cannot, and no setting shuts anybody in
--- (DESIGN.md 2). The same answer on a client, for its menu, and on the
--- server, which decides (SEW_Server.grant).
function S.fits(character, mode)
    local fit = S.option("DrainFit", 2, 3)
    if fit == 1 or character == nil then return nil end
    if mode == "down" then
        local w = U.try("fits.weight", function() return character:getNutrition():getWeight() end)
        if w and w >= C.Drain.weight then return "big" end
    end
    local carried = U.try("fits.carried", function() return character:getInventoryWeight() end)
    local most = U.try("fits.most", function() return character:getMaxWeight() end)
    if carried and most and carried > most * (fit == 3 and C.Drain.light or C.Drain.load) then return "load" end
    return nil
end

--- The manhole cover nearest to x, y at street level within `slack` squares:
--- the square it is on, or nil.
function S.manholeNear(x, y, slack, z)
    local best, bestD = nil, 1e9
    for dx = -slack, slack do
        for dy = -slack, slack do
            local sq = U.square(x + dx, y + dy, z or 0, false)
            if S.isManhole(sq) then
                local d = math.abs(dx) + math.abs(dy)
                if d < bestD then best, bestD = sq, d end
            end
        end
    end
    return best
end

--- True on the sewer's own level, C.Z, and nowhere else. **Not "anywhere
--- under the street"**: the map has bunkers and basements two and fourteen
--- levels down, and players dig their own; none of that is the sewer, and a
--- player there gets no map, no dig menu, no gas and no rescue (DEV_GUIDE,
--- "Below ground is not all ours").
function S.below(player)
    if player == nil then return false end
    local z = U.try("getZ", function() return player:getZ() end) or 0
    return z < C.Z + 0.5 and z >= C.Z - 0.5
end

--- True when the square is the sewer's: something of ours is on it. A
--- basement at the same level is not (DEV_GUIDE, "Below ground is not all
--- ours").
function S.ours(sq)
    local found = false
    U.eachObject(sq, function(o)
        if U.isOurs(o) then
            found = true
            return false
        end
    end)
    return found
end

--- True when the player is in the sewer itself: at its level and standing
--- on a square of ours. For what belongs to the place and to nowhere else
--- at that level -- its sounds, and whether the street hears.
function S.inSewer(player)
    return S.levelOf(player) ~= nil and S.onOurs(player)
end

--- True when the player's own square has something of ours on it.
function S.onOurs(player)
    local sq = U.try("inSewer.sq", function() return player:getCurrentSquare() end)
    return sq ~= nil and S.ours(sq)
end

--- The level of sewer a player is at: C.Z anywhere at the sewers' own level
--- (S.below), and a deeper one only on a square of ours -- the map's
--- bunkers are down there too, and are nobody's business (DEV_GUIDE, *Below
--- ground is not all ours*). nil anywhere else.
function S.levelOf(player)
    if player == nil then return nil end
    local z = U.try("getZ", function() return player:getZ() end) or 0
    local l = math.floor(z + 0.5)
    if l == C.Z then return S.below(player) and l or nil end
    if not S.isLevel(l) or z < l - 0.5 then return nil end
    return S.onOurs(player) and l or nil
end

--- True when x, y is the labyrinth's: any of its squares, or the rock for
--- three squares round its outer wall -- further than a bomb reaches
--- (C.Mine.blast; DESIGN.md 7g). Nothing there gives to a pick or a
--- bomb: a labyrinth somebody can dig straight through is a corridor.
function S.inLabyrinth(x, y)
    local L = SEW.Index and SEW.Index.labyrinth
    if not L then return false end
    x, y = math.floor(x), math.floor(y)
    return x >= L.x0 - 3 and x <= L.x0 + L.size + 2 and y >= L.y0 - 3 and y <= L.y0 + L.size + 2
end

--- True when a character is close enough to a point to work there.
function S.within(player, x, y, reach)
    local px = U.try("px", function() return player:getX() end)
    local py = U.try("py", function() return player:getY() end)
    if not px or not py then return false end
    return U.dist(px, py, x + 0.5, y + 0.5) <= (reach or C.Reach)
end

function S.hasLiftTool(player)
    local inv = U.try("inventory", function() return player:getInventory() end)
    if not inv then return false end
    for _, id in ipairs(C.LiftTools) do
        local bare = id:match("%.(.+)$") or id
        if U.try("containsTypeRecurse", function() return inv:containsTypeRecurse(bare) end) then
            return true
        end
    end
    return false
end

--- True when the character carries something to pry or break with.
function S.hasPryTool(character)
    local inv = U.try("inventory", function() return character:getInventory() end)
    if not inv then return false end
    for _, id in ipairs(C.PryTools) do
        local bare = id:match("%.(.+)$") or id
        if U.try("containsTypeRecurse", function() return inv:containsTypeRecurse(bare) end) then return true end
    end
    return false
end

--- "pick", "hammer" or nil: what the character carries to dig with (a pick
--- is quicker). The server asks the same of its own copy (SEW_Mine.tool).
function S.mineTool(character)
    local inv = U.try("inventory", function() return character:getInventory() end)
    if not inv then return nil end
    for _, kind in ipairs({ "pick", "hammer" }) do
        for _, id in ipairs(C.Mine[kind]) do
            local bare = id:match("%.(.+)$") or id
            if U.try("containsTypeRecurse", function() return inv:containsTypeRecurse(bare) end) then return kind end
        end
    end
    return nil
end

--- The two squares either side of one of the nest's walls ("wall", the false
--- wall from the sewer, or "gate", into the hoard), from the index; nil
--- when this build has no nest.
function S.gateSquares(which)
    local L = SEW.Index and SEW.Index.lair
    if not L then return nil end
    if which == "wall" then return L.tx, L.ty, L.ex, L.ey end
    if which == "gate" then return L.gx, L.gy, L.vx, L.vy end
    return nil
end

--- True when the edge between two squares holds a door frame: one of the
--- nest's walls that has been opened (the builder puts a breach there,
--- over vanilla's frame). What the client can see for itself.
function S.gateOpenHere(ax, ay, bx, by)
    local x, y = math.max(ax, bx), math.max(ay, by)
    local sq = U.square(x, y, C.Z, false)
    if not sq then return false end
    local frame = (ax == bx) and C.Sprites.doorFrame.N or C.Sprites.doorFrame.W
    return U.findSprite(sq, frame) ~= nil
end

return S
