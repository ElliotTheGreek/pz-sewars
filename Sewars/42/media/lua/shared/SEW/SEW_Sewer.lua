--[[ Sewars -- read-only questions about the sewers, the same answer everywhere.

    Answered from SEW.Index (generated, small, loaded by every process) and
    from what is standing on the squares. Nothing here changes anything.
]]

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Index"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util

local S = {}
SEW.Sewer = S

--- The shaft under the manhole at x, y, or nil.
function S.shaftAt(x, y)
    return SEW.Index and SEW.Index.shafts[math.floor(x) .. "," .. math.floor(y)] or nil
end

--- The shaft nearest to x, y within `range`, looking at both the square under
--- the cover and the square its ladder hangs on.
function S.shaftNear(x, y, range)
    local best, bestD = nil, (range or 2) + 0.001
    local r = math.ceil(range or 2) + 1
    for dx = -r, r do
        for dy = -r, r do
            local s = S.shaftAt(x + dx, y + dy)
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
        -- basement instead, and its way up may be shut.
        if not s.hatch then
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

--- Vanilla's cover, one of ours (the towns the map gives few), or an
--- outfall's grate in a riverbank.
function S.isManhole(sq)
    return sq ~= nil and (U.findSprite(sq, C.ManholeSprite) ~= nil or U.findSprite(sq, C.Sprites.cover) ~= nil
                          or U.findSprite(sq, C.Sprites.outfall) ~= nil)
end

--- The manhole cover nearest to x, y at street level within `slack` squares:
--- the square it is on, or nil.
function S.manholeNear(x, y, slack)
    local best, bestD = nil, 1e9
    for dx = -slack, slack do
        for dy = -slack, slack do
            local sq = U.square(x + dx, y + dy, 0, false)
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
    if not S.below(player) then return false end
    local sq = U.try("inSewer.sq", function() return player:getCurrentSquare() end)
    return sq ~= nil and S.ours(sq)
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
