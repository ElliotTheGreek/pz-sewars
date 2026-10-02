--[[ Sewars -- digging: a pick, a sledgehammer, and what a pipe bomb does to rock.

    Runs in single player and on any server (never on a client).

    The sewers are data (tools/gen_sewers.py -> Data/), and SEW_Build raises
    them from one record a square. Digging changes the records, not the
    objects: what a player has dug is kept as records of its own, by chunk
    (SEW_Build state `dug`, B.setRecord), which the builder reads in place of
    the generator's -- so a square dug out stays dug through every revision
    pass, a wall knocked through is not put back, and a square the generator
    never knew of is rebuilt like any other. Each change is then built by
    the builder's own B.square, which takes away our wall where the record no
    longer has one and stands earth where rock is now exposed.

      dig     with a pick or a sledgehammer, from the square the digger
              stands on into the one beside it. Rock there: it becomes dug
              earth, with earth walls wherever more rock is behind it. A
              space there, behind a wall of ours: the wall comes down.
      blast   a bomb that goes off below ground -- vanilla's own, placed or
              thrown, with vanilla's own fuse, damage and noise; the engine
              tells Lua with OnThrowableExplode (IsoTrap.triggerExplosion) --
              opens every square of rock within C.Mine.blast of it, and takes
              down our walls inside that round.

    What never gives:
      * a square that holds something not ours (a basement the game put
        there: DEV_GUIDE, *Not over anything else*);
      * a door, a locked grille, a ladder's wall, the nest's two walls;
      * the hoard, from any side, while its rodents live (the gnawed wall is
        the way in, and it has its price);
      * anything a player built: only records and objects of ours are touched.
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Net"
require "SEW/SEW_Sewer"
require "SEW/SEW_Build"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local Net = SEW.Net
local S = SEW.Sewer
local B = SEW.Build

local Mi = {}
SEW.Mine = Mi

local N4 = { { 0, -1 }, { -1, 0 }, { 1, 0 }, { 0, 1 } }
local SOFT = { c = true, b = true, e = true }      -- walls that give
local FLOOR, NORTH, WEST, FIX, DRESS = 3, 4, 5, 6, 7

local function nameOf(p)
    return U.try("username", function() return p:getUsername() end) or "player"
end

local function blank(x, y)
    return (x % 8) .. (y % 8) .. "....."
end

local function with(rec, i, ch)
    return rec:sub(1, i - 1) .. ch .. rec:sub(i + 1)
end

--- The floor code of x, y as the builder has it: "." where nothing is.
function Mi.floor(x, y)
    local r = B.recordAt(x, y)
    return r and r:sub(FLOOR, FLOOR) or "."
end

--- True when x, y is somewhere to stand: any floor of ours but the rock under a wall.
function Mi.isSpace(x, y)
    local f = Mi.floor(x, y)
    return f ~= "." and f ~= "r"
end

--- The square that holds the edge between two neighbours (the southern or
--- eastern of them), and which of its walls it is.
local function edge(ax, ay, bx, by)
    return math.max(ax, bx), math.max(ay, by), (ax == bx) and NORTH or WEST
end

function Mi.edgeCode(ax, ay, bx, by)
    local hx, hy, col = edge(ax, ay, bx, by)
    local r = B.recordAt(hx, hy)
    return r and r:sub(col, col) or "."
end

--- True when the wall on this edge has a ladder hanging on it.
local function ladderOn(ax, ay, bx, by)
    local hx, hy, col = edge(ax, ay, bx, by)
    local r = B.recordAt(hx, hy)
    local fix = r and r:sub(FIX, FIX) or "."
    return (col == NORTH and fix == "L") or (col == WEST and fix == "l")
end

--- May the wall between two squares come down? The hoard is shut from every
--- side until the nest's own wall into it has been opened.
local function gives(ax, ay, bx, by)
    if not SOFT[Mi.edgeCode(ax, ay, bx, by)] or ladderOn(ax, ay, bx, by) then return false end
    if (Mi.floor(ax, ay) == "v" or Mi.floor(bx, by) == "v") and not B.gateOpen("gate") then return false end
    return true
end

--- May the rock at x, y be dug out? "ok", or why not.
function Mi.rock(x, y)
    if Mi.isSpace(x, y) then return "space" end
    if not U.chunkLoaded(x, y) then return "unready" end
    local sq = U.square(x, y, C.Z, true)
    if not sq then return "unready" end
    if B.foreign(sq) then return "foreign" end
    -- A ladder hangs on a wall this square holds: the rock behind it stays.
    local r = B.recordAt(x, y)
    local fix = r and r:sub(FIX, FIX) or "."
    if fix == "L" or fix == "l" then return "solid" end
    return "ok"
end

---------------------------------------------------------------------------
-- A plan: the records a dig or a blast changes, worked out before anything
-- is touched, then written and built.
---------------------------------------------------------------------------
local function at(plan, x, y)
    local k = x .. "," .. y
    local e = plan[k]
    if not e then
        e = { x = x, y = y, rec = B.recordAt(x, y) or blank(x, y) }
        plan[k] = e
        plan.order[#plan.order + 1] = e
    end
    return e
end

local function setEdge(plan, ax, ay, bx, by, ch)
    local hx, hy, col = edge(ax, ay, bx, by)
    local e = at(plan, hx, hy)
    e.rec = with(e.rec, col, ch)
    -- A wall has to stand on something: rock, where nothing else is.
    if ch ~= "." and e.rec:sub(FLOOR, FLOOR) == "." then e.rec = with(e.rec, FLOOR, "r") end
end

--- Opens the rock squares in `dig` ({x, y} each), and takes down the walls
--- on `through` ({ax, ay, bx, by} each). Returns the plan.
local function plan(dig, through)
    local p = { order = {} }
    local opened = {}
    for _, d in ipairs(dig) do
        local e = at(p, d[1], d[2])
        e.rec = with(with(with(e.rec, FLOOR, "m"), FIX, "."), DRESS, ".")
        e.opened = true
        opened[d[1] .. "," .. d[2]] = true
    end
    -- Earth wherever rock is behind what was opened; nothing between two
    -- squares opened together; a wall that was there against another space
    -- is that space's, and stays unless it is one of those to go through.
    for _, d in ipairs(dig) do
        for _, n in ipairs(N4) do
            local nx, ny = d[1] + n[1], d[2] + n[2]
            if opened[nx .. "," .. ny] then
                setEdge(p, d[1], d[2], nx, ny, ".")
            elseif not Mi.isSpace(nx, ny) then
                setEdge(p, d[1], d[2], nx, ny, "e")
            end
        end
    end
    for _, t in ipairs(through) do setEdge(p, t[1], t[2], t[3], t[4], ".") end
    return p
end

--- Writes a plan into the records and builds it. Returns how many squares
--- were opened.
local function carry(p)
    local opened = 0
    for _, e in ipairs(p.order) do B.setRecord(e.x, e.y, e.rec) end
    for _, e in ipairs(p.order) do
        local how = B.square(e.x, e.y, e.rec, false, false)
        if how == "built" and e.opened then
            opened = opened + 1
            -- What came down: stones on the floor, and a few to pick up.
            local sq = U.square(e.x, e.y, C.Z, false)
            local roll = U.rng(U.hash(e.x, e.y, 53))
            if sq and roll(3) == 1 then B.put(sq, C.Sprites.stones[roll(#C.Sprites.stones)]) end
            if sq then
                for _ = 1, roll(C.Mine.stones) - 1 do
                    U.try("mine.stone", function() sq:SpawnWorldInventoryItem(C.Mine.stone, 0.0, 0.0, 0.0) end)
                end
            end
        end
    end
    return opened
end

--- Makes sure every chunk of a town that the squares touch is built first:
--- a record is only half the truth until its square has been raised.
local function ready(squares)
    for _, q in ipairs(squares) do
        local key = math.floor(q[1] / 8) .. "," .. math.floor(q[2] / 8)
        if not U.chunkLoaded(q[1], q[2]) then return false end
        if B.townOf(key) and not B.isCurrent(key) and not B.chunk(key) then return false end
    end
    return true
end

---------------------------------------------------------------------------
-- Digging
---------------------------------------------------------------------------
--- 1 off, 2 picks and hammers, 3 and explosives (the sandbox's Sewars.Digging).
function Mi.level()
    return B.option("Digging", 3, 3)
end

--- "pick", "hammer" or nil: the best digging tool the character carries.
function Mi.tool(character)
    return S.mineTool(character)
end

local function refuse(player, why)
    U.log("refused %s: %s", nameOf(player), why)
    Net.toClient(player, "refused", { why = why })
    return false
end

--- A player digging from the square ax, ay towards dx, dy. Called from
--- SEWMine:complete().
function Mi.dig(player, ax, ay, dx, dy)
    ax, ay = math.floor(tonumber(ax) or 0), math.floor(tonumber(ay) or 0)
    dx, dy = tonumber(dx) or 0, tonumber(dy) or 0
    if math.abs(dx) + math.abs(dy) ~= 1 then return refuse(player, "mode") end
    if Mi.level() < 2 then return refuse(player, "off") end
    if not S.below(player) then return refuse(player, "level") end
    if not S.within(player, ax, ay, C.Reach) then return refuse(player, "reach") end
    if not Mi.tool(player) then return refuse(player, "tool") end
    local bx, by = ax + dx, ay + dy
    if not ready({ { ax, ay }, { bx, by }, { bx + 1, by }, { bx, by + 1 } }) then return refuse(player, "unready") end
    local here = U.square(ax, ay, C.Z, false)
    if not here or not U.floorOf(here) then return refuse(player, "level") end

    local p, what
    if Mi.isSpace(bx, by) then
        -- Something is already there: only the wall between is in the way.
        if not gives(ax, ay, bx, by) then
            return refuse(player, (Mi.floor(bx, by) == "v" and SOFT[Mi.edgeCode(ax, ay, bx, by)]) and "rous" or "solid")
        end
        p, what = plan({}, { { ax, ay, bx, by } }), "break"
    else
        local why = Mi.rock(bx, by)
        if why ~= "ok" then return refuse(player, why) end
        -- The wall the digger faces is theirs to go through, if it is one of ours.
        local code = Mi.edgeCode(ax, ay, bx, by)
        if code ~= "." and not gives(ax, ay, bx, by) then return refuse(player, "solid") end
        p, what = plan({ { bx, by } }, { { ax, ay, bx, by } }), "dig"
    end
    carry(p)
    U.try("mine.noise", function() addSound(player, ax, ay, C.Z, C.Mine.noise[1], C.Mine.noise[2]) end)
    U.try("mine.xp", function() addXp(player, Perks.Masonry, C.Mine.xp) end)
    U.log("%s %s at %d,%d", nameOf(player), what == "dig" and "dug out" or "broke through to", bx, by)
    Net.toClient(player, "mined", { what = what })
    return true
end

---------------------------------------------------------------------------
-- Blasting
---------------------------------------------------------------------------
--- A bomb has gone off at x, y below ground: every square of rock within
--- C.Mine.blast of it is opened, and our walls inside that round come down.
--- Returns how many squares of rock were opened.
function Mi.blast(x, y)
    x, y = math.floor(x), math.floor(y)
    if Mi.level() < 3 then return 0 end
    local r = C.Mine.blast
    local round = {}
    for bx = x - r, x + r do
        for by = y - r, y + r do
            if (bx - x) * (bx - x) + (by - y) * (by - y) <= (r + 0.5) * (r + 0.5) then round[#round + 1] = { bx, by } end
        end
    end
    if not ready(round) then
        U.debug("a blast at %d,%d in ground not all loaded: nothing moved", x, y)
        return 0
    end
    local inRound, dig = {}, {}
    for _, q in ipairs(round) do inRound[q[1] .. "," .. q[2]] = true end
    for _, q in ipairs(round) do
        if not Mi.isSpace(q[1], q[2]) and Mi.rock(q[1], q[2]) == "ok" then dig[#dig + 1] = q end
    end
    local willBe = {}
    for _, q in ipairs(dig) do willBe[q[1] .. "," .. q[2]] = true end
    local function space(qx, qy) return willBe[qx .. "," .. qy] or Mi.isSpace(qx, qy) end
    -- Every wall of ours inside the round, between two squares that are both
    -- open once the dust settles. (North and west of each: every edge once.)
    local through = {}
    for _, q in ipairs(round) do
        for _, n in ipairs({ { 0, -1 }, { -1, 0 } }) do
            local nx, ny = q[1] + n[1], q[2] + n[2]
            if inRound[nx .. "," .. ny] and space(q[1], q[2]) and space(nx, ny) and gives(q[1], q[2], nx, ny) then
                through[#through + 1] = { q[1], q[2], nx, ny }
            end
        end
    end
    if #dig == 0 and #through == 0 then return 0 end
    local opened = carry(plan(dig, through))
    U.log("a blast at %d,%d: %d squares of rock opened, %d walls down", x, y, opened, #through)
    for _, p in ipairs(U.players()) do
        if S.below(p) and U.dist(p:getX(), p:getY(), x, y) <= 30 then Net.toClient(p, "mined", { what = "blast" }) end
    end
    return opened
end

-- Blasts waiting for the dust: { x, y, at }. The engine tells Lua first and
-- does its own damage after, in the same call; the rock moves a moment later.
Mi.pending = {}
local ticks = 0

--- The engine's OnThrowableExplode: (the trap, its square). Only below
--- ground, and only what explodes -- a smoke bomb and a noise maker have no
--- explosion range.
function Mi.onExplode(trap, square)
    if not trap then return false end
    local range = U.try("trap.range", function() return trap:getExplosionRange() end) or 0
    if range <= 0 then return false end
    local sq = square or U.try("trap.square", function() return trap:getSquare() end)
    local z = sq and U.try("trap.z", function() return sq:getZ() end)
    if z ~= C.Z then return false end
    Mi.pending[#Mi.pending + 1] = { x = sq:getX(), y = sq:getY(), at = ticks + C.Mine.blastDelay }
    return true
end

Events.OnThrowableExplode.Add(function(...) U.try("mine.explode", Mi.onExplode, ...) end)
Events.OnTick.Add(function()
    ticks = ticks + 1
    if #Mi.pending == 0 then return end
    local later = {}
    for _, b in ipairs(Mi.pending) do
        if ticks >= b.at then U.try("mine.blast", Mi.blast, b.x, b.y) else later[#later + 1] = b end
    end
    Mi.pending = later
end)

return Mi
