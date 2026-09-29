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
        local d = U.dist(x, y, s.x, s.y)
        if d < bestD then best, bestD = s, d end
    end
    return best, bestD
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

function S.isManhole(sq)
    return sq ~= nil and U.findSprite(sq, C.ManholeSprite) ~= nil
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

function S.below(player)
    return player ~= nil and (U.try("getZ", function() return player:getZ() end) or 0) < -0.5
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

return S
