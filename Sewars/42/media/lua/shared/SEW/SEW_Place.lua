--[[ Sewars -- where the labyrinth is (0.9; SERVERS.md, *If another mod is in
    the way*; DESIGN.md 7g).

    The labyrinth is the one thing of ours that stands in ground nothing
    else is in: no tunnel leads to it, and no town's chunks are its. So it
    is the one thing that can be somewhere else, and the one thing another
    mod may have built on. The sandbox's Sewars.MazeX and Sewars.MazeY say
    which square its trapdoor is on; this file moves everything that says
    where the labyrinth is, together, by the difference:

      * SEW.Index: its town's bounds, its rooms, its two ways (the trapdoor
        and the way out, which are kept under where they are), its lights,
        and SEW.Index.labyrinth itself;
      * SEW.Data (where there is any: a server, single player): its squares,
        furniture and dead, which are kept by chunk -- so it moves by whole
        chunks, eight squares, and a record's place in its chunk never
        changes;
      * its annotated map: the sheet it shows (C.Maps) and the marks on it
        (the global StashDescriptions, which the engine reads after this:
        IsoWorld.init runs GlobalModData.init, and so OnInitGlobalModData,
        before StashSystem.init).

    **Once, as a world starts**, before a chunk is loaded or a cache is
    made. A setting changed while a world runs waits for the next start. A
    client moves by its own sandbox at its start and then by what the
    server says it did (`place`), which is the last word.

    **Refused**: a place on or within C.Place.clear squares of any town's
    sheet of the map. The labyrinth stays where the mod has it and the log
    says why. Nothing else is checked: what is on or under the ground there
    is the host's to know (another mod's, a basement), and squares that
    already hold something underground are left alone as anywhere else.

    **A world that already has one** (SEW_Place.reconcile): what was built
    at the old place stays there, in the ground, with nothing leading to it;
    the chunks' stamps under both places are forgotten so the new one is
    built whole.
]]

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Index"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util

local P = {}
SEW.Place = P

-- How far the labyrinth stands from where the generator put it, in squares.
P.dx, P.dy = 0, 0

local function maze() return SEW.Index and SEW.Index.labyrinth end

-- Where the generator put its trapdoor: read before anything moves.
local HOME = maze() and { x = maze().tx, y = maze().ty } or nil

--- The square the mod's own labyrinth has its trapdoor on, or nil.
function P.home()
    if HOME then return HOME.x, HOME.y end
    return nil
end

-- What forgets a cache made from where things were (SEW_Build, SEW_Sewer, ...).
local hooks = {}
function P.onMove(fn) hooks[#hooks + 1] = fn end

--- True when the labyrinth moved by dx, dy from the mod's own place would
--- be clear of every town; or false and what is in the way (a town's id, or
--- "edge" for off the map's north or west).
function P.clear(dx, dy)
    local L = maze()
    local m = C.Place.clear
    local x0, y0 = L.x0 - P.dx + dx, L.y0 - P.dy + dy
    if x0 - m < 0 or y0 - m < 0 then return false, "edge" end
    local hit = nil
    for tid, t in pairs(SEW.Index.towns) do
        if tid ~= L.town and x0 - m <= t.x1 and x0 + L.size + m >= t.x0
                and y0 - m <= t.y1 and y0 + L.size + m >= t.y0 then
            -- Never by the order of pairs: the smaller id is the one named.
            if hit == nil or tid < hit then hit = tid end
        end
    end
    if hit then return false, hit end
    return true
end

--- What the sandbox asks for: how far from the mod's own place, in squares,
--- to the nearest chunk. 0, 0 when it says nothing (a world from before the
--- settings), or the mod's own place -- or a place that is refused, and then
--- what is in the way as well.
function P.wanted()
    if not HOME then return 0, 0 end
    local v = SandboxVars and SandboxVars.Sewars
    local x, y = tonumber(v and v.MazeX) or HOME.x, tonumber(v and v.MazeY) or HOME.y
    local dx = math.floor((x - HOME.x) / 8 + 0.5) * 8
    local dy = math.floor((y - HOME.y) / 8 + 0.5) * 8
    if dx == 0 and dy == 0 then return 0, 0 end
    local ok, why = P.clear(dx, dy)
    if not ok then return 0, 0, why end
    return dx, dy
end

-- A table kept by chunk ("cx,cy" -> ...), kept by the chunks cx, cy further on.
local function rekey(tbl, cx, cy)
    local out = {}
    for k, v in pairs(tbl) do
        local kx, ky = tostring(k):match("^(-?%d+),(-?%d+)$")
        if kx then out[#out + 1] = { k, math.floor(tonumber(kx) + cx) .. "," .. math.floor(tonumber(ky) + cy), v } end
    end
    for _, e in ipairs(out) do tbl[e[1]] = nil end
    for _, e in ipairs(out) do tbl[e[2]] = e[3] end
end

-- The dead of these lists face a square (SEW_Build.spawn): that moves too.
local FACING = { claimed = true, caveClaimed = true, warrenDead = true }

--- Puts the labyrinth dx, dy squares (whole chunks) from the mod's own
--- place, wherever it is now. True when anything moved.
function P.move(dx, dy)
    local L = maze()
    if not L then return false end
    dx, dy = math.floor(dx), math.floor(dy)
    local mx, my = dx - P.dx, dy - P.dy
    if mx == 0 and my == 0 then return false end
    local I, tid = SEW.Index, L.town

    local t = I.towns[tid]
    t.x0, t.x1, t.y0, t.y1 = t.x0 + mx, t.x1 + mx, t.y0 + my, t.y1 + my
    for _, h in ipairs(I.shelters) do
        if h.town == tid then h.x, h.y = h.x + mx, h.y + my end
    end
    -- Its ways are kept under where they are.
    local ways = {}
    for k, s in pairs(I.shafts) do
        if s.town == tid then ways[#ways + 1] = { k, s } end
    end
    for _, e in ipairs(ways) do I.shafts[e[1]] = nil end
    for _, e in ipairs(ways) do
        local s = e[2]
        s.x, s.y, s.lx, s.ly = s.x + mx, s.y + my, s.lx + mx, s.ly + my
        I.shafts[s.x .. "," .. s.y] = s
    end
    for _, k in ipairs({ "x", "tx", "ex", "dx", "x0" }) do L[k] = L[k] + mx end
    for _, k in ipairs({ "y", "ty", "ey", "dy", "y0" }) do L[k] = L[k] + my end
    for i = 1, #L.lights, 2 do
        L.lights[i], L.lights[i + 1] = L.lights[i] + mx, L.lights[i + 1] + my
    end

    -- Its annotated map: the sheet, and the marks on it.
    local m = C.Maps.labyrinth
    m.bounds[1], m.bounds[2], m.bounds[3], m.bounds[4] = m.bounds[1] + mx, m.bounds[2] + my, m.bounds[3] + mx, m.bounds[4] + my
    for _, st in ipairs(StashDescriptions or {}) do
        if st.name == m.stash then
            for _, a in ipairs(st.annotations or {}) do a.x, a.y = a.x + mx, a.y + my end
        end
    end

    -- Its squares and what stands on them, where this process has them.
    local T = SEW.Data and SEW.Data[tid]
    if T then
        for name, tbl in pairs(T) do
            if type(tbl) == "table" then
                for _, list in pairs(tbl) do
                    if type(list) == "table" then
                        for _, e in ipairs(list) do
                            if type(e) == "table" and type(e[1]) == "number" and type(e[2]) == "number" then
                                e[1], e[2] = e[1] + mx, e[2] + my
                                if FACING[name] and type(e[4]) == "number" and type(e[5]) == "number" then
                                    e[4], e[5] = e[4] + mx, e[5] + my
                                end
                            end
                        end
                    end
                end
                rekey(tbl, mx / 8, my / 8)
            end
        end
    end

    P.dx, P.dy = dx, dy
    for _, fn in ipairs(hooks) do U.try("place.moved", fn) end
    return true
end

--- A saved world that built the labyrinth somewhere else: the stamps of the
--- chunks under where it was and where it is are forgotten, so the builder
--- builds this one whole and from the first -- a chunk both have in common
--- would otherwise pass for built. What stands at the old place stays.
function P.reconcile(s)
    local L = maze()
    if not L or not s then return 0 end
    local now = P.dx .. "," .. P.dy
    local was = s.place or "0,0"
    if was == now then return 0 end
    local wx, wy = was:match("^(-?%d+),(-?%d+)$")
    wx, wy = tonumber(wx) or 0, tonumber(wy) or 0
    local t = SEW.Index.towns[L.town]
    local n = 0
    for _, off in ipairs({ { 0, 0 }, { wx - P.dx, wy - P.dy } }) do
        for cx = math.floor((t.x0 + off[1]) / 8), math.floor((t.x1 + off[1]) / 8) do
            for cy = math.floor((t.y0 + off[2]) / 8), math.floor((t.y1 + off[2]) / 8) do
                local key = cx .. "," .. cy
                for _, name in ipairs({ "built", "first", "caves", "gas", "hung", "warren", "owed" }) do
                    if s[name] and s[name][key] ~= nil then
                        s[name][key] = nil
                        n = n + 1
                    end
                end
            end
        end
    end
    s.place = now
    local hx, hy = P.home()
    U.log("place: this world's labyrinth was at %d,%d and is at %d,%d now; %d stamp(s) of its chunks are "
          .. "forgotten. What was built at the old place stays in the ground there",
          hx + wx, hy + wy, hx + P.dx, hy + P.dy, n)
    return n
end

--- As a world starts: where the sandbox says, or the mod's own place.
function P.settle()
    if not HOME then return end
    local dx, dy, why = P.wanted()
    if why then
        local v = SandboxVars.Sewars
        U.log("WARN place: the sandbox puts the labyrinth at %s,%s (MazeX, MazeY), which is %s: "
              .. "it stays at the mod's own %d,%d", tostring(v.MazeX), tostring(v.MazeY),
              why == "edge" and "off the north or west of the map" or ("on or beside " .. why .. "'s sewers"),
              HOME.x, HOME.y)
    end
    if P.move(dx, dy) then
        U.log("place: the labyrinth's trapdoor is at %d,%d by the sandbox (MazeX, MazeY), not the mod's own %d,%d",
              HOME.x + P.dx, HOME.y + P.dy, HOME.x, HOME.y)
    end
    -- The world's own record of it, where this process keeps the world.
    if not isClient() and SEW.Build then P.reconcile(SEW.Build.state()) end
end

Events.OnInitGlobalModData.Add(function() U.try("place", P.settle) end)

return P
