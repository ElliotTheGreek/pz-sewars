--[[ Sewars -- an admin's works: ways down put where they are wanted, tunnels
    drawn on the map, deeper levels, rooms set down from the mod's own or from
    a template, ground marked as indoors (0.9; DESIGN.md 7i, SERVERS.md).

    Runs in single player and on any server (never on a client). Every entry
    here is asked for by a client's command and answered only for an admin
    (SEW_Sewer.isAdmin, on the server's own copy of the player).

    **Nothing here builds anything of its own.** The sewers are records, one
    a square, and SEW_Build raises them (DEV_GUIDE, *Digging changes the
    records, not the objects*). A work is a change to the records, worked out
    by the same planner a pick uses (SEW_Mine.plan: what is opened, the walls
    that stand where rock is now exposed, the walls that come down), written
    as the players' own records (B.setRecord), and built by the builder. So
    every later pass, a pick, a bomb, the map and a revision all read one
    thing, and what an admin made is kept exactly as what a player dug is.

      entrance  a cover, a trapdoor or a grate on a square of the street, a
                shaft under it, and a passage dug from its foot to the
                nearest tunnel
      shaft     from a tunnel, a cover in its floor and a ladder down to the
                level below (the sewers' own is -1; an admin's go to -3)
      tunnel    a straight run 1, 3 or 5 wide at any of the three levels,
                joined to what it meets or walled off from it
      shelter   a copy of one of the mod's own rooms, with its furniture,
                its stock and its dead, behind the wall an admin stands at
      template  the objects in a box anywhere in the world, kept by name with
                a kind of stock, and set down below like a shelter
      indoors   a room or a box of squares marked as indoors (SEW_Indoors)
      rebuild   the tunnel round the admin revisited now: missing hull back
      check     what a square is, to the mod and to the engine

    What is refused, always: the labyrinth and its rock; a square that holds
    something not ours (somebody's basement); a ladder's wall; the nest's
    walls. And a work that needs to look at the ground (a shaft, a room)
    is refused where the ground is not loaded: an admin stands at it.
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Net"
require "SEW/SEW_Sewer"
require "SEW/SEW_Build"
require "SEW/SEW_Mine"
require "SEW/SEW_Indoors"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local Net = SEW.Net
local S = SEW.Sewer
local B = SEW.Build
local Mi = SEW.Mine

local Wk = {}
SEW.Works = Wk

local N4 = { { 0, -1 }, { -1, 0 }, { 1, 0 }, { 0, 1 } }
local FLOOR, NORTH, WEST, FIX, DRESS = 3, 4, 5, 6, 7
-- What a run is made of, by its width: a culvert and a main in concrete, a
-- trunk in brick -- the sewers' own, so an admin's tunnel is a sewer's.
local STYLE = { [1] = { floor = "t", wall = "c" }, [3] = { floor = "t", wall = "c" }, [5] = { floor = "k", wall = "b" } }
-- A room's floor and the hull round it.
local ROOM = { floor = "s", wall = "c" }

local function nameOf(p)
    return U.try("username", function() return p:getUsername() end) or "player"
end

local function refuse(player, why)
    U.log("refused %s: %s", nameOf(player), why)
    Net.toClient(player, "refused", { why = why })
    return false
end

--- Only an admin's asking is heard.
local function admin(player)
    if S.isAdmin(player) then return true end
    refuse(player, "admin")
    return false
end

local function told(player, what, n, name)
    Net.toClient(player, "worked", { what = what, n = n, name = name })
end

local function int(v)
    return math.floor(tonumber(v) or 0)
end

local function ckey(x, y)
    return math.floor(x / 8) .. "," .. math.floor(y / 8)
end

local function with(rec, i, ch)
    return rec:sub(1, i - 1) .. ch .. rec:sub(i + 1)
end

--- The level the server has a player at: 0 on the street, -1 to -3 below.
function Wk.levelOf(player)
    local z = U.try("getZ", function() return player:getZ() end) or 0
    return math.floor(z + 0.5)
end

---------------------------------------------------------------------------
-- Writing a plan
---------------------------------------------------------------------------
--- Writes a plan into the records of level z and builds what of it is
--- loaded. What is not is written down as never yet built (state `unbuilt`):
--- the builder's own pass builds it when somebody comes near, looking first
--- for anything of somebody else's on the square, as on any first build.
--- `first`: the opened squares get what a first build gives (doors,
--- dressing). Returns how many squares were built now, and the chunks touched.
function Wk.write(p, z, first)
    local s = B.state()
    local keys, built = {}, 0
    for _, e in ipairs(p.order) do
        B.setRecord(e.x, e.y, e.rec, z)
        keys[ckey(e.x, e.y)] = true
    end
    for _, e in ipairs(p.order) do
        local opened = e.opened == true
        if U.chunkLoaded(e.x, e.y) then
            if B.square(e.x, e.y, e.rec, first == true and opened, false, z, opened) == "built" then built = built + 1 end
        else
            local k = B.zkey(z) .. ":" .. ckey(e.x, e.y)
            s.unbuilt[k] = s.unbuilt[k] or {}
            s.unbuilt[k][e.x .. "," .. e.y] = opened and 2 or 1
            s.built[ckey(e.x, e.y)] = nil
        end
    end
    Wk.changed(z, keys)
    return built, keys
end

---------------------------------------------------------------------------
-- What a client's map is told (SEW_Map draws an admin's and a digger's work
-- from this: the plans are pictures made with the layout, and know neither)
---------------------------------------------------------------------------
--- The squares of chunk `key` at level z that the players' own records make
--- somewhere to stand: 64 characters, a row at a time, "1" where there is.
--- nil when the chunk has none.
function Wk.bits(z, key)
    local dug = B.dugOf(z)[key]
    if not dug then return nil end
    local cx, cy = key:match("^(-?%d+),(-?%d+)$")
    cx, cy = tonumber(cx) * 8, tonumber(cy) * 8
    local out, any = {}, false
    for dy = 0, 7 do
        for dx = 0, 7 do
            local rec = dug[(cx + dx) .. "," .. (cy + dy)]
            local f = rec and rec:sub(FLOOR, FLOOR) or "."
            local space = f ~= "." and f ~= "r"
            any = any or space
            out[#out + 1] = space and "1" or "0"
        end
    end
    return any and table.concat(out) or nil
end

local function sendBits(player, list)
    -- A few at a time: a command is a packet, and a network an admin drew
    -- can be hundreds of chunks (DEV_GUIDE, *State that is transmitted
    -- whole cannot hold a list that grows*).
    local batch = {}
    for _, e in ipairs(list) do
        batch[#batch + 1] = e
        if #batch >= C.Works.batch then
            Net.toClient(player, "works", { list = batch })
            batch = {}
        end
    end
    if #batch > 0 then Net.toClient(player, "works", { list = batch }) end
end

--- Chunks of level z whose records have changed: told to every player who
--- has that chunk on their map, and to every admin.
function Wk.changed(z, keys)
    local zs = B.zkey(z)
    for _, p in ipairs(U.players()) do
        local seen = SEW.Discovery and SEW.Discovery.record(p).w or {}
        local isAdmin = S.isAdmin(p)
        local list = {}
        for key in pairs(keys) do
            local k = zs .. ":" .. key
            if isAdmin or seen[k] then list[#list + 1] = { k = k, b = Wk.bits(z, key) or "" } end
        end
        if #list > 0 then sendBits(p, list) end
    end
end

--- Everything a player has seen (or, for an admin who asks, everything).
function Wk.sendSeen(player, all)
    local list = {}
    local seen = SEW.Discovery and SEW.Discovery.record(player).w or {}
    for _, z in ipairs(C.Levels) do
        local zs = B.zkey(z)
        for key in pairs(B.dugOf(z)) do
            local k = zs .. ":" .. key
            if all or seen[k] then
                local b = Wk.bits(z, key)
                if b then list[#list + 1] = { k = k, b = b } end
            end
        end
    end
    table.sort(list, function(a, b) return a.k < b.k end)
    sendBits(player, list)
    return #list
end

--- A player at level z has walked into chunk `key`: on their map from now on.
--- Returns true when it was new and had something to show.
function Wk.seen(player, z, key)
    if not SEW.Discovery then return false end
    local r = SEW.Discovery.record(player)
    local k = B.zkey(z) .. ":" .. key
    if r.w[k] then return false end
    local b = Wk.bits(z, key)
    if not b then return false end
    r.w[k] = 1
    sendBits(player, { { k = k, b = b } })
    return true
end

---------------------------------------------------------------------------
-- Ways down
---------------------------------------------------------------------------
--- The admin's shafts, to one client or to all: few, and sent whole.
function Wk.publish(player)
    local list = {}
    for k, v in pairs(B.state().shafts) do
        list[k] = { x = v.x, y = v.y, z = v.z, lx = v.lx, ly = v.ly, town = v.town, street = v.street,
                    made = true, custom = true, trapdoor = v.trapdoor, outfall = v.outfall }
    end
    local names = {}
    for name, t in pairs(B.state().templates) do names[#names + 1] = { name = name, w = t.w, h = t.h, loot = t.loot } end
    table.sort(names, function(a, b) return a.name < b.name end)
    local args = { list = list, templates = names }
    if player then
        Net.toClient(player, "shafts", args)
        return
    end
    for _, p in ipairs(U.players()) do Net.toClient(p, "shafts", args) end
end

--- The shortest way through the rock from sx, sy to a square beside plain
--- walkway, no longer than `max`: the squares of it, first to last, and the
--- walkway square the last one meets. nil when there is none. By the
--- records alone (nothing is made to look): the caller looks at the squares
--- of the way it is given, and asks again without any that will not do.
local function route(sx, sy, max, barred)
    local z = Mi.z
    local function open(x, y)
        if barred[x .. "," .. y] or Mi.isSpace(x, y) then return false end
        if z == C.Z and S.inLabyrinth(x, y) then return false end
        local r = B.recordAt(x, y, z)
        if r and r:sub(FIX, FIX) ~= "." then return false end
        return U.chunkLoaded(x, y)
    end
    local function walkway(x, y)
        local f = Mi.floor(x, y)
        return f == "t" or f == "k" or f == "m"
    end
    if not open(sx, sy) then return nil end
    local start = { sx, sy, 0 }
    local prev, queue, head = { [sx .. "," .. sy] = start }, { start }, 1
    while head <= #queue do
        local q = queue[head]
        head = head + 1
        for _, n in ipairs(N4) do
            local nx, ny = q[1] + n[1], q[2] + n[2]
            if walkway(nx, ny) and Mi.gives(q[1], q[2], nx, ny) then
                local path, at = {}, q
                while at do
                    table.insert(path, 1, { at[1], at[2] })
                    at = at[4]
                end
                return path, { nx, ny }
            end
        end
        if q[3] < max then
            for _, n in ipairs(N4) do
                local nx, ny = q[1] + n[1], q[2] + n[2]
                local k = nx .. "," .. ny
                if not prev[k] and open(nx, ny) then
                    local e = { nx, ny, q[3] + 1, q }
                    prev[k] = e
                    queue[#queue + 1] = e
                end
            end
        end
    end
    return nil
end

--- The ladder a shaft's foot gets: on its north wall where it has one, else
--- its west ("L", "l": SEW_Build's fixtures). `open`: the one neighbour the
--- foot is open to, or nil.
local function ladderFor(x, y, open)
    if open and open[1] == x and open[2] == y - 1 then return "l" end
    return "L"
end

local function addShaft(x, y, z, kind)
    local s = B.state()
    local shaft = { x = x, y = y, z = z, lx = x, ly = y, town = S.townAt(x, y) or "", street = "", made = true,
                    custom = true }
    if kind == "trapdoor" then shaft.trapdoor = true end
    if kind == "outfall" then shaft.outfall = true end
    s.shafts[S.shaftKey(x, y, z)] = shaft
    return shaft
end

--- A way down put on the street at x, y: `kind` is "cover", "trapdoor" or
--- "outfall". The shaft is under it; a passage is dug from its foot to the
--- nearest tunnel within the sandbox's Sewars.Passage.
function Wk.entrance(player, x, y, kind)
    if not admin(player) then return false end
    x, y = int(x), int(y)
    if kind ~= "trapdoor" and kind ~= "outfall" then kind = "cover" end
    if S.shaftAt(x, y) then return refuse(player, "taken") end
    local top = U.chunkLoaded(x, y) and U.square(x, y, 0, false)
    if not top or not U.floorOf(top) then return refuse(player, "unready") end
    if S.inLabyrinth(x, y) then return refuse(player, "hard") end
    local max = C.Works.passage[B.option("Passage", 2, #C.Works.passage)]
    return Mi.with(C.Z, function()
        local p, dug
        if Mi.isSpace(x, y) then
            -- A tunnel is right under it: the ladder goes on its wall.
            local rec = B.recordAt(x, y, C.Z)
            if rec:sub(FIX, FIX) ~= "." then return refuse(player, "taken") end
            p = Mi.plan({}, {})
            local e = Mi.planAt(p, x, y)
            e.rec = with(e.rec, FIX, rec:sub(NORTH, NORTH) == "." and rec:sub(WEST, WEST) ~= "." and "l" or "L")
            dug = 0
        else
            local barred, path, touch = {}, nil, nil
            for _ = 1, 8 do
                path, touch = route(x, y, max, barred)
                if not path then break end
                local bad = false
                for _, q in ipairs(path) do
                    if Mi.rock(q[1], q[2]) ~= "ok" then
                        barred[q[1] .. "," .. q[2]] = true
                        bad = true
                    end
                end
                if not bad then break end
                path = nil
            end
            if not path then return refuse(player, "far") end
            p = Mi.plan(path, { { path[#path][1], path[#path][2], touch[1], touch[2] } }, STYLE[1])
            local e = Mi.planAt(p, x, y)
            e.rec = with(with(e.rec, FLOOR, "g"), FIX, ladderFor(x, y, path[2] or touch))
            dug = #path
        end
        Wk.write(p, C.Z, false)
        local shaft = addShaft(x, y, C.Z, kind)
        B.cover(shaft)
        Wk.publish(nil)
        U.log("%s put a way down (%s) at %d,%d: %d squares of passage", nameOf(player), kind, x, y, dug)
        told(player, "entrance", dug)
        return true
    end)
end

--- A shaft from the tunnel the admin stands in down to the level below: a
--- cover in this tunnel's floor at x, y, and under it the foot of a ladder.
function Wk.shaft(player, x, y)
    if not admin(player) then return false end
    x, y = int(x), int(y)
    local top = Wk.levelOf(player)
    local z = top - 1
    if not S.isLevel(top) or not S.isLevel(z) then return refuse(player, "level") end
    if not S.within(player, x, y, C.Reach + 1.0) then return refuse(player, "reach") end
    if S.shaftAt(x, y, z) or S.shaftAt(x, y, top) then return refuse(player, "taken") end
    if not U.chunkLoaded(x, y) then return refuse(player, "unready") end
    local here = Mi.with(top, function() return Mi.isSpace(x, y) and B.recordAt(x, y, top) end)
    if not here or here:sub(FIX, FIX) ~= "." or here:sub(FLOOR, FLOOR) == "w" then return refuse(player, "solid") end
    return Mi.with(z, function()
        local p
        if Mi.isSpace(x, y) then
            local rec = B.recordAt(x, y, z)
            if rec:sub(FIX, FIX) ~= "." then return refuse(player, "taken") end
            p = Mi.plan({}, {})
            local e = Mi.planAt(p, x, y)
            e.rec = with(e.rec, FIX, rec:sub(NORTH, NORTH) == "." and rec:sub(WEST, WEST) ~= "." and "l" or "L")
        else
            local why = Mi.rock(x, y)
            if why ~= "ok" then return refuse(player, why) end
            p = Mi.plan({ { x, y } }, {}, STYLE[1])
            local e = Mi.planAt(p, x, y)
            e.rec = with(with(e.rec, FLOOR, "g"), FIX, "L")
        end
        Wk.write(p, z, false)
        local shaft = addShaft(x, y, z, "cover")
        B.cover(shaft)
        Wk.publish(nil)
        U.log("%s put a shaft at %d,%d from level %d down to %d", nameOf(player), x, y, top, z)
        told(player, "shaft", -z)
        return true
    end)
end

--- Takes away a way down an admin put in: its cover and its ladder. What
--- was dug for it stays dug.
function Wk.remove(player, x, y, z)
    if not admin(player) then return false end
    x, y, z = int(x), int(y), int(z or C.Z)
    local s = B.state()
    local key = S.shaftKey(x, y, z)
    local shaft = s.shafts[key]
    if not shaft then return refuse(player, "shut") end
    local sprite = shaft.outfall and C.Sprites.outfall or shaft.trapdoor and C.Sprites.hatch or C.Sprites.cover
    local top = U.square(x, y, z + 1, false)
    if top then
        local doomed = {}
        U.eachObject(top, function(o)
            if U.isOurs(o) and U.spriteName(o) == sprite then doomed[#doomed + 1] = o end
        end)
        for _, o in ipairs(doomed) do
            U.try("works.uncover", function() top:transmitRemoveItemFromSquare(o) end)
        end
    end
    s.shafts[key], s.covers[key], s.access[key] = nil, nil, nil
    Mi.with(z, function()
        local rec = B.recordAt(x, y, z)
        if rec then
            local p = Mi.plan({}, {})
            local e = Mi.planAt(p, x, y)
            e.rec = with(e.rec, FIX, ".")
            if e.rec:sub(FLOOR, FLOOR) == "g" then e.rec = with(e.rec, FLOOR, "t") end
            Wk.write(p, z, false)
        end
    end)
    Wk.publish(nil)
    if SEW.Server then SEW.Server.publishAccess(nil) end
    U.log("%s took away the way down at %d,%d,%d", nameOf(player), x, y, z)
    told(player, "removed", 0)
    return true
end

---------------------------------------------------------------------------
-- Tunnels
---------------------------------------------------------------------------
--- A straight run from x0, y0 to x1, y1 at level z, `width` 1, 3 or 5
--- across. `join`: walls between it and what it meets come down, and where
--- it crosses a tunnel it runs through; without, it is refused across a
--- tunnel and walled off from one it runs beside. May run through ground
--- that is not loaded (it is drawn on a map): that part is built when
--- somebody comes near.
function Wk.tunnel(player, x0, y0, x1, y1, width, z, join)
    if not admin(player) then return false end
    x0, y0, x1, y1, z, width = int(x0), int(y0), int(x1), int(y1), int(z), int(width)
    if not S.isLevel(z) then return refuse(player, "level") end
    local style = STYLE[width]
    if not style then width, style = 1, STYLE[1] end
    -- Straight: along whichever way it runs further.
    if math.abs(x1 - x0) >= math.abs(y1 - y0) then y1 = y0 else x1 = x0 end
    if math.abs(x1 - x0) + math.abs(y1 - y0) + 1 > C.Works.maxRun then return refuse(player, "long") end
    local half = math.floor((width - 1) / 2)
    local run, inRun = {}, {}
    for x = math.min(x0, x1), math.max(x0, x1) do
        for y = math.min(y0, y1), math.max(y0, y1) do
            for c = -half, half do
                local qx, qy = (y0 == y1) and x or x + c, (y0 == y1) and y + c or y
                run[#run + 1] = { qx, qy }
                inRun[qx .. "," .. qy] = true
            end
        end
    end
    return Mi.with(z, function()
        local dig, through = {}, {}
        for _, q in ipairs(run) do
            if z == C.Z and S.inLabyrinth(q[1], q[2]) then return refuse(player, "hard") end
            if Mi.isSpace(q[1], q[2]) then
                if not join then return refuse(player, "apart") end
            elseif U.chunkLoaded(q[1], q[2]) then
                local why = Mi.rock(q[1], q[2])
                if why ~= "ok" then return refuse(player, why) end
                dig[#dig + 1] = q
            else
                local r = B.recordAt(q[1], q[2], z)
                if r and r:sub(FIX, FIX) ~= "." then return refuse(player, "solid") end
                dig[#dig + 1] = q
            end
        end
        if join then
            -- Every wall between the run and a space that is there already.
            local done = {}
            for _, q in ipairs(run) do
                for _, n in ipairs(N4) do
                    local nx, ny = q[1] + n[1], q[2] + n[2]
                    local a, b = q[1] .. "," .. q[2], nx .. "," .. ny
                    local edge = a < b and (a .. "|" .. b) or (b .. "|" .. a)
                    if not done[edge] and Mi.isSpace(nx, ny) and Mi.gives(q[1], q[2], nx, ny) then
                        done[edge] = true
                        through[#through + 1] = { q[1], q[2], nx, ny }
                    end
                end
            end
        end
        if #dig == 0 and #through == 0 then return refuse(player, "nothing") end
        local built = Wk.write(Mi.plan(dig, through, style), z, false)
        U.log("%s ran a tunnel %d wide at level %d from %d,%d to %d,%d: %d squares opened, %d walls down, %d built now",
              nameOf(player), width, z, x0, y0, x1, y1, #dig, #through, built)
        told(player, "tunnel", #dig)
        return true
    end)
end

---------------------------------------------------------------------------
-- Rooms: the mod's own shelters, copied
---------------------------------------------------------------------------
Wk.KINDS = { "maintenance", "pump", "squat", "laststand" }

-- kind -> side -> { shelter index, the square inside its door }: which of
-- the generator's shelters has its door on which side. Found once.
local catalog = nil
local function shelters()
    if catalog then return catalog end
    catalog = {}
    for _, kind in ipairs(Wk.KINDS) do catalog[kind] = {} end
    local function door(x, y, col)
        local r = B.dataAt(x, y)
        local ch = r and r:sub(col, col)
        return ch == "d" or ch == "j"
    end
    for i, h in ipairs(SEW.Index.shelters or {}) do
        local sides = catalog[h.kind]
        if sides then
            for x = h.x, h.x + h.w - 1 do
                if not sides.N and door(x, h.y, NORTH) then sides.N = { i = i, x = x, y = h.y } end
                if not sides.S and door(x, h.y + h.h, NORTH) then sides.S = { i = i, x = x, y = h.y + h.h - 1 } end
            end
            for y = h.y, h.y + h.h - 1 do
                if not sides.W and door(h.x, y, WEST) then sides.W = { i = i, x = h.x, y = y } end
                if not sides.E and door(h.x + h.w, y, WEST) then sides.E = { i = i, x = h.x + h.w - 1, y = y } end
            end
        end
    end
    return catalog
end
Wk.shelters = shelters

--- The side of a room its door is on when it is walked into going dx, dy.
local function sideFor(dx, dy)
    if dy == -1 then return "S" elseif dy == 1 then return "N" elseif dx == -1 then return "E" end
    return "W"
end

--- True when every square of the box is rock that may be opened, here and now.
local function rockBox(x0, y0, w, h)
    for x = x0, x0 + w - 1 do
        for y = y0, y0 + h - 1 do
            if Mi.isSpace(x, y) then return false, "space" end
            if not U.chunkLoaded(x, y) then return false, "unready" end
            local why = Mi.rock(x, y)
            if why ~= "ok" then return false, why end
        end
    end
    return true
end

--- A copy of one of the mod's own shelters of `kind`, behind the wall the
--- admin faces going dx, dy from where they stand: its hull, its door, its
--- furniture stocked as a new shelter's is, and its dead.
function Wk.shelter(player, kind, dx, dy)
    if not admin(player) then return false end
    dx, dy = int(dx), int(dy)
    if math.abs(dx) + math.abs(dy) ~= 1 then return refuse(player, "mode") end
    local z = Wk.levelOf(player)
    if not S.isLevel(z) then return refuse(player, "level") end
    local src = shelters()[kind] and shelters()[kind][sideFor(dx, dy)]
    if not src then return refuse(player, "noroom") end
    local h = SEW.Index.shelters[src.i]
    local ax, ay = int(player:getX()), int(player:getY())
    local ox, oy = ax + dx - src.x, ay + dy - src.y
    return Mi.with(z, function()
        if not Mi.isSpace(ax, ay) then return refuse(player, "level") end
        local ok, why = rockBox(h.x + ox, h.y + oy, h.w, h.h)
        if not ok then return refuse(player, why == "space" and "apart" or why) end
        local p = Mi.plan({}, {})
        for x = h.x, h.x + h.w - 1 do
            for y = h.y, h.y + h.h - 1 do
                local r = B.dataAt(x, y)
                if r then
                    local e = Mi.planAt(p, x + ox, y + oy)
                    -- A county room's locked grille is its town's: a copy has a door.
                    local n, w = r:sub(NORTH, NORTH), r:sub(WEST, WEST)
                    e.rec = ((x + ox) % 8) .. ((y + oy) % 8) .. r:sub(FLOOR, FLOOR)
                        .. (n == "j" and "d" or n) .. (w == "j" and "d" or w) .. r:sub(FIX, DRESS)
                    e.opened = true
                end
            end
        end
        -- The walls and the door on its south and east sides are held by
        -- the squares beyond them: squares that may be there already (the
        -- tunnel the admin stands in), which get no first build -- so a door
        -- on one of those edges is hung here.
        local doors = {}
        for x = h.x, h.x + h.w - 1 do
            local r = B.dataAt(x, h.y + h.h)
            local ch = r and r:sub(NORTH, NORTH) or "c"
            if ch == "j" then ch = "d" end
            Mi.planEdge(p, x + ox, h.y + h.h - 1 + oy, x + ox, h.y + h.h + oy, ch)
            if ch == "d" then doors[#doors + 1] = { x + ox, h.y + h.h + oy, true } end
        end
        for y = h.y, h.y + h.h - 1 do
            local r = B.dataAt(h.x + h.w, y)
            local ch = r and r:sub(WEST, WEST) or "c"
            if ch == "j" then ch = "d" end
            Mi.planEdge(p, h.x + h.w - 1 + ox, y + oy, h.x + h.w + ox, y + oy, ch)
            if ch == "d" then doors[#doors + 1] = { h.x + h.w + ox, y + oy, false } end
        end
        Wk.write(p, z, true)
        for _, d in ipairs(doors) do
            local sq = U.square(d[1], d[2], z, false)
            if sq then B.putDoor(sq, d[3]) end
        end
        -- Its furniture and its dead, from the same shelter, moved.
        local T = SEW.Data[h.town]
        local seed, things, dead = U.hash(ax, ay, 61), 0, 0
        for cx = math.floor(h.x / 8), math.floor((h.x + h.w - 1) / 8) do
            for cy = math.floor(h.y / 8), math.floor((h.y + h.h - 1) / 8) do
                local key = cx .. "," .. cy
                for _, e in ipairs(T.furniture[key] or {}) do
                    if e[1] >= h.x and e[1] < h.x + h.w and e[2] >= h.y and e[2] < h.y + h.h then
                        if B.furnish({ e[1] + ox, e[2] + oy, e[3], e[4] }, seed, z) then things = things + 1 end
                    end
                end
                for _, d in ipairs(T.claimed[key] or {}) do
                    if d[1] >= h.x and d[1] < h.x + h.w and d[2] >= h.y and d[2] < h.y + h.h then
                        B.setPiece(ckey(d[1] + ox, d[2] + oy),
                                   { d[1] + ox, d[2] + oy, d[3], d[4] and d[4] + ox, d[5] and d[5] + oy, z })
                        dead = dead + 1
                    end
                end
            end
        end
        U.log("%s set down a %s (a copy of shelter %d) at %d,%d level %d: %d things, %d dead", nameOf(player), kind, src.i,
              h.x + ox, h.y + oy, z, things, dead)
        told(player, "room", things)
        return true
    end)
end

---------------------------------------------------------------------------
-- Rooms: an admin's own, from a template
---------------------------------------------------------------------------
Wk.LOOT = { "none", "medical", "military", "gunstore", "police", "survival", "food", "tools", "mechanics",
            "electronics", "laboratory" }

local function lootOk(loot)
    for _, v in ipairs(Wk.LOOT) do if v == loot then return true end end
    return false
end

--- Keeps the objects in the box from x0, y0 to x1, y1 at the admin's own
--- level as a template: each square's objects by picture, a door as a door,
--- which of them was the floor. Named for its stock and numbered.
function Wk.capture(player, x0, y0, x1, y1, loot)
    if not admin(player) then return false end
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    if x1 < x0 then x0, x1 = x1, x0 end
    if y1 < y0 then y0, y1 = y1, y0 end
    local w, h = x1 - x0 + 1, y1 - y0 + 1
    if w > C.Works.maxRoom or h > C.Works.maxRoom then return refuse(player, "long") end
    if not lootOk(loot) then loot = "none" end
    local z = Wk.levelOf(player)
    local cells, n = {}, 0
    for x = x0, x1 do
        for y = y0, y1 do
            if not U.chunkLoaded(x, y) then return refuse(player, "unready") end
            local sq = U.square(x, y, z, false)
            if sq then
                local floor = U.floorOf(sq)
                local list = {}
                U.eachObject(sq, function(o)
                    local name = U.spriteName(o)
                    if name and not instanceof(o, "IsoWorldInventoryObject") then
                        local door = instanceof(o, "IsoDoor")
                        list[#list + 1] = { s = name, f = (o == floor) and 1 or nil, d = door and 1 or nil,
                                            n = door and U.try("tpl.north", function() return o:getNorth() end) and 1 or nil }
                    end
                end)
                if #list > 0 then
                    cells[(x - x0) .. "," .. (y - y0)] = list
                    n = n + #list
                end
            end
        end
    end
    if n == 0 then return refuse(player, "nothing") end
    local s = B.state()
    local i = 1
    while s.templates[loot .. " " .. i] do i = i + 1 end
    local name = loot .. " " .. i
    s.templates[name] = { w = w, h = h, loot = loot, cells = cells }
    Wk.publish(nil)
    U.log("%s kept a room template \"%s\": %d by %d, %d objects", nameOf(player), name, w, h, n)
    told(player, "template", n, name)
    return true
end

function Wk.forget(player, name)
    if not admin(player) then return false end
    local s = B.state()
    if not s.templates[name] then return refuse(player, "noroom") end
    s.templates[name] = nil
    Wk.publish(nil)
    told(player, "forgot", 0, name)
    return true
end

--- One of a template's objects on a square below: tagged as ours and as a
--- template's (the builder's revision never takes a template's wall for one
--- of its own: SEW_Build.unwall), a door made a door, a container made and
--- stocked once.
local function setDown(sq, o, loot, seed)
    if o.f then
        -- The rock of ours under a wall gives way to a template's own floor.
        local rock = {}
        U.eachObject(sq, function(old)
            if U.isOurs(old) and U.spriteName(old) == C.Sprites.floorRock then rock[#rock + 1] = old end
        end)
        for _, old in ipairs(rock) do
            U.try("tpl.unrock", function() sq:transmitRemoveItemFromSquare(old) end)
        end
    end
    if o.d then
        return U.try("tpl.door", function()
            local door = IsoDoor.new(getCell(), sq, o.s, o.n == 1)
            door:getModData()[C.Tag] = 1
            door:getModData()[C.TemplateTag] = 1
            sq:AddSpecialObject(door)
            if isServer() then door:transmitCompleteItemToClients() end
            return true
        end) == true
    end
    local obj = U.try("tpl.new", function() return IsoObject.new(sq, o.s, "") end)
    if not obj then return false end
    U.try("tpl.tag", function()
        obj:getModData()[C.Tag] = 1
        obj:getModData()[C.TemplateTag] = 1
    end)
    U.try("tpl.containers", function() obj:createContainersFromSpriteProperties() end)
    local c = U.containerOf(obj)
    if c then
        U.try("tpl.explored", function() c:setExplored(true) end)
        local list = C.Loot["template_" .. tostring(loot)]
        if list then
            local lo, hi = unpack(C.LootCount[B.option("Loot", 3, #C.LootCount)])
            local mine = U.hash(sq:getX(), sq:getY(), seed)
            U.fill(obj, list, lo + mine % (hi - lo + 1), mine)
        end
    end
    return U.try("tpl.send", function()
        sq:transmitAddObjectToSquare(obj, -1)
        return true
    end) == true
end

--- A copy of template `name` behind the wall the admin faces going dx, dy:
--- its box set against that wall with the admin at the middle of its side,
--- a hull round it, an opening where the admin stands.
function Wk.place(player, name, dx, dy)
    if not admin(player) then return false end
    dx, dy = int(dx), int(dy)
    if math.abs(dx) + math.abs(dy) ~= 1 then return refuse(player, "mode") end
    local z = Wk.levelOf(player)
    if not S.isLevel(z) then return refuse(player, "level") end
    local t = B.state().templates[name]
    if not t then return refuse(player, "noroom") end
    local ax, ay = int(player:getX()), int(player:getY())
    -- The box: against the wall, the admin at the middle of that side.
    local x0, y0
    if dy == -1 then x0, y0 = ax - math.floor(t.w / 2), ay - t.h
    elseif dy == 1 then x0, y0 = ax - math.floor(t.w / 2), ay + 1
    elseif dx == -1 then x0, y0 = ax - t.w, ay - math.floor(t.h / 2)
    else x0, y0 = ax + 1, ay - math.floor(t.h / 2) end
    return Mi.with(z, function()
        if not Mi.isSpace(ax, ay) then return refuse(player, "level") end
        local ok, why = rockBox(x0, y0, t.w, t.h)
        if not ok then return refuse(player, why == "space" and "apart" or why) end
        local dig = {}
        for x = x0, x0 + t.w - 1 do
            for y = y0, y0 + t.h - 1 do dig[#dig + 1] = { x, y } end
        end
        local p = Mi.plan(dig, { { ax, ay, ax + dx, ay + dy } }, ROOM)
        -- A template's own floor goes down before the builder looks for one.
        local seed, n = U.hash(ax, ay, 67), 0
        for _, e in ipairs(p.order) do B.setRecord(e.x, e.y, e.rec, z) end
        for k, list in pairs(t.cells) do
            local cx, cy = k:match("^(-?%d+),(-?%d+)$")
            local sq = U.square(x0 + tonumber(cx), y0 + tonumber(cy), z, true)
            for _, o in ipairs(list) do
                if sq and o.f and setDown(sq, o, t.loot, seed) then n = n + 1 end
            end
        end
        Wk.write(p, z, false)
        for k, list in pairs(t.cells) do
            local cx, cy = k:match("^(-?%d+),(-?%d+)$")
            local sq = U.square(x0 + tonumber(cx), y0 + tonumber(cy), z, false)
            for _, o in ipairs(list) do
                if sq and not o.f and setDown(sq, o, t.loot, seed) then n = n + 1 end
            end
        end
        U.log("%s set down the template \"%s\" at %d,%d level %d: %d objects", nameOf(player), name, x0, y0, z, n)
        told(player, "room", n)
        return true
    end)
end

---------------------------------------------------------------------------
-- Rebuild
---------------------------------------------------------------------------
--- The tunnel round the admin, revisited now: floors, walls, ladders and
--- door frames that are missing are put back. Never furniture, never the
--- dead, never anything a player built (SEW_Build).
function Wk.rebuild(player)
    if not admin(player) then return false end
    local px, py = player:getX(), player:getY()
    local s = B.state()
    local r = C.Works.rebuild
    for dx = -r, r do
        for dy = -r, r do
            s.built[(math.floor(px / 8) + dx) .. "," .. (math.floor(py / 8) + dy)] = nil
        end
    end
    local done, left = B.around(px, py, r)
    U.log("%s rebuilt the sewer round %d,%d: %d chunks, %d not loaded", nameOf(player), px, py, done, left)
    told(player, "rebuilt", done)
    return true
end

---------------------------------------------------------------------------
-- Indoors (SEW_Indoors: what a mark is, and how the engine is told)
---------------------------------------------------------------------------
local function doorOn(sq, north)
    local list = U.try("specials", function() return sq:getSpecialObjects() end)
    local n = list and list:size() or 0
    for i = 0, n - 1 do
        local o = list:get(i)
        local door = instanceof(o, "IsoDoor") or (instanceof(o, "IsoThumpable") and o:isDoor())
        if door and (north == nil or o:getNorth() == north) then return true end
    end
    return false
end

--- True when one of the square's four edges holds a door: such a square is
--- left out of a mark, so a locked door still holds against the dead
--- (IsoDoor.Thump: a zombie opens one from a square that is not outdoors).
local function byDoor(x, y, z)
    local sq = U.square(x, y, z, false)
    if sq and doorOn(sq, nil) then return true end
    local south = U.square(x, y + 1, z, false)
    if south and doorOn(south, true) then return true end
    local east = U.square(x + 1, y, z, false)
    return east ~= nil and doorOn(east, false)
end

--- A set of squares ({ ["x,y"] = true }) as rectangles: each row's runs,
--- and a run that sits exactly under the one above grows it. Top row first.
local function rectsOf(set)
    local rows, ys = {}, {}
    for k in pairs(set) do
        local x, y = k:match("^(-?%d+),(-?%d+)$")
        x, y = tonumber(x), tonumber(y)
        if not rows[y] then
            rows[y] = {}
            ys[#ys + 1] = y
        end
        table.insert(rows[y], x)
    end
    table.sort(ys)
    local rects, open = {}, {}
    for _, y in ipairs(ys) do
        table.sort(rows[y])
        local runs, x0, prev = {}, nil, nil
        for _, x in ipairs(rows[y]) do
            if x0 == nil then
                x0 = x
            elseif x ~= prev + 1 then
                runs[#runs + 1] = { x0, prev }
                x0 = x
            end
            prev = x
        end
        if x0 ~= nil then runs[#runs + 1] = { x0, prev } end
        local now = {}
        for _, r in ipairs(runs) do
            local k = r[1] .. "," .. r[2]
            local up = open[k]
            if up and up[2] + up[4] == y then
                up[4] = up[4] + 1
                now[k] = up
            else
                local rect = { r[1], y, r[2] - r[1] + 1, 1 }
                rects[#rects + 1] = rect
                now[k] = rect
            end
        end
        open = now
    end
    return rects
end
Wk.rectsOf = rectsOf

--- What is marked as indoors, to one client or to all.
function Wk.publishIndoor(player)
    local list = {}
    for id, m in pairs(B.state().indoor) do list[id] = { z = m.z, rects = m.rects } end
    if player then
        Net.toClient(player, "indoor", { list = list })
        return
    end
    for _, p in ipairs(U.players()) do Net.toClient(p, "indoor", { list = list }) end
end

--- Marks ground below the street as indoors, at the admin's own level: the
--- box from x, y to x1, y1; or, with no second corner, the room x, y is in
--- (every square that can be walked to from it without passing a wall or a
--- shut door). Never a square the game already has a room on, one already
--- marked, or one beside a door.
function Wk.indoor(player, x, y, x1, y1)
    if not admin(player) then return false end
    local z = Wk.levelOf(player)
    if z >= 0 then return refuse(player, "level") end
    x, y = int(x), int(y)
    local In = SEW.Indoors
    local s = B.state()
    In.marks = s.indoor
    local set, n = {}, 0
    local function take(qx, qy)
        local sq = U.square(qx, qy, z, false)
        if not sq or not U.floorOf(sq) then return false end
        if sq:getRoom() ~= nil or In.at(qx, qy, z) or byDoor(qx, qy, z) then return true end
        set[qx .. "," .. qy] = true
        n = n + 1
        return true
    end
    if x1 ~= nil then
        x1, y1 = int(x1), int(y1)
        if x1 < x then x, x1 = x1, x end
        if y1 < y then y, y1 = y1, y end
        if (x1 - x + 1) * (y1 - y + 1) > C.Works.maxIndoor then return refuse(player, "long") end
        for qx = x, x1 do
            for qy = y, y1 do
                if not U.chunkLoaded(qx, qy) then return refuse(player, "unready") end
                take(qx, qy)
            end
        end
    else
        local seen, queue, head = { [x .. "," .. y] = true }, { { x, y } }, 1
        while head <= #queue do
            local q = queue[head]
            head = head + 1
            if #queue > C.Works.maxIndoor then return refuse(player, "long") end
            if take(q[1], q[2]) then
                local here = U.square(q[1], q[2], z, false)
                for _, d in ipairs(N4) do
                    local nx, ny = q[1] + d[1], q[2] + d[2]
                    local k = nx .. "," .. ny
                    local there = not seen[k] and U.chunkLoaded(nx, ny) and U.square(nx, ny, z, false)
                    if there and U.floorOf(there)
                            and U.try("indoor.blocked", function() return here:isBlockedTo(there) end) ~= true then
                        seen[k] = true
                        queue[#queue + 1] = { nx, ny }
                    end
                end
            end
        end
    end
    if n == 0 then return refuse(player, "nothing") end
    local rects = rectsOf(set)
    local id = z .. ":" .. rects[1][1] .. ":" .. rects[1][2]
    s.indoor[id] = { z = z, rects = rects }
    In.touch()
    Wk.publishIndoor(nil)
    U.log("%s marked %d squares at level %d as indoors (%s, %d rectangles)", nameOf(player), n, z, id, #rects)
    -- A server makes the room at its next start (SEW_Indoors); single
    -- player and every client have made it by now.
    told(player, isServer() and "indoorLater" or "indoor", n)
    return true
end

--- Takes a mark away. The room it made stays until the world is next
--- started: a room is never taken away under a running world (SEW_Indoors).
function Wk.outdoor(player, x, y)
    if not admin(player) then return false end
    local z = Wk.levelOf(player)
    local In = SEW.Indoors
    local s = B.state()
    In.marks = s.indoor
    local id = In.at(int(x), int(y), z)
    if not id then return refuse(player, "nothing") end
    local n = 0
    for _, r in ipairs(s.indoor[id].rects) do n = n + r[3] * r[4] end
    s.indoor[id] = nil
    In.touch()
    Wk.publishIndoor(nil)
    U.log("%s took the indoors mark %s away (%d squares); its room goes at the next start", nameOf(player), id, n)
    told(player, "outdoor", n)
    return true
end

--- What a square is: to the game (a room on it), to an admin's marks, to
--- the mod (a square of the sewer's, where the mod answers for the game).
function Wk.check(player, x, y)
    if not admin(player) then return false end
    x, y = int(x), int(y)
    local z = Wk.levelOf(player)
    local sq = U.square(x, y, z, false)
    local room = sq ~= nil and sq:getRoom() ~= nil
    local marked = SEW.Indoors.at(x, y, z) ~= nil
    local ours = sq ~= nil and S.ours(sq)
    U.log("check %d,%d,%d for %s: room %s, marked %s, ours %s, record %s", x, y, z, nameOf(player), tostring(room),
          tostring(marked), tostring(ours), tostring(B.recordAt(x, y, z)))
    told(player, room and "check_room" or marked and "check_marked" or ours and "check_sewer" or "check_no", 0)
    return true
end

---------------------------------------------------------------------------
-- The commands
---------------------------------------------------------------------------
Net.onServer("works", function(player, a)
    local what = a.what
    if what == "entrance" then return Wk.entrance(player, a.x, a.y, a.kind) end
    if what == "shaft" then return Wk.shaft(player, a.x, a.y) end
    if what == "remove" then return Wk.remove(player, a.x, a.y, a.z) end
    if what == "tunnel" then return Wk.tunnel(player, a.x0, a.y0, a.x1, a.y1, a.width, a.z, a.join == true) end
    if what == "shelter" then return Wk.shelter(player, a.kind, a.dx, a.dy) end
    if what == "capture" then return Wk.capture(player, a.x0, a.y0, a.x1, a.y1, a.loot) end
    if what == "place" then return Wk.place(player, a.name, a.dx, a.dy) end
    if what == "forget" then return Wk.forget(player, a.name) end
    if what == "rebuild" then return Wk.rebuild(player) end
    if what == "indoor" then return Wk.indoor(player, a.x0 or a.x, a.y0 or a.y, a.x1, a.y1) end
    if what == "outdoor" then return Wk.outdoor(player, a.x, a.y) end
    if what == "check" then return Wk.check(player, a.x, a.y) end
    if what == "all" then
        -- The whole of what has been dug and drawn, for an admin's map.
        if not admin(player) then return false end
        return Wk.sendSeen(player, true)
    end
    return refuse(player, "mode")
end)

return Wk
