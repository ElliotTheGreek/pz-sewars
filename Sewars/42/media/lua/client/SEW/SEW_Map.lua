--[[ Sewars -- the sewer map: your own, black until you walk it.

    ROADMAP 0.3, and the spine of what comes after: the sewers are something
    you learn. This is a panel of its own rather than a layer on the world map,
    because the world map has exactly one fog of war per character and Lua
    cannot add a second (pz_trekship MAP_MARKERS.md) -- walking a tunnel would
    have lifted the fog on the streets above it.

    What it draws, bottom to top:
      paper;
      the town's plan -- 256px tiles generated with the layout
        (tools/gen_sewers.py map_images, media/ui/sewermap/<town>_<i>_<j>.png),
        one pixel a square: the streets above faint, tunnels in pale ink;
      the fog -- one bit per 8x8 chunk, from what the server says this player
        has walked (SEW_Discovery.lua), drawn as runs of undiscovered chunks
        merged per row and cached until something new is found: there is no
        render-to-texture reachable from Lua, and one rectangle a chunk would
        be fourteen thousand draws a frame for the largest town;
      the gas -- stretches of sewer gas walked into or read of on a plan;
      markers -- ladders used, shelters found, marks from journals, you.

    The server owns what has been found; this file keeps a mirror of this
    player's record (`mapState` on opening, one `found` per new find after).

    Controls: drag the map to pan, the wheel to zoom, < > to switch town; drag
    the title bar to move the window, its corner or bottom edge to resize it,
    X or Escape to close. A controller pans with the stick, zooms with the
    triggers, switches town on the bumpers, closes on B. Opened from the right-click menu below ground
    (SEW_Client) or the key (Options -> Mods; N by default, because M is
    vanilla's world map).
]]

if isServer() then return end

require "ISUI/ISPanelJoypad"
require "ISUI/ISCollapsableWindowJoypad"
require "ISUI/ISButton"
require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Net"
require "SEW/SEW_Sewer"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local Net = SEW.Net
local S = SEW.Sewer

local M = {}
SEW.Map = M

M.TILE = 256
M.PAPER = { 0.80, 0.74, 0.62 }
M.FOG = { 0.16, 0.13, 0.10 }
M.INK = { 0.23, 0.18, 0.13 }
M.ZOOMS = { 0.5, 0.75, 1, 1.5, 2, 3, 4, 6 }

---------------------------------------------------------------------------
-- What this player has found (a mirror of the server's record)
---------------------------------------------------------------------------
M.state = { c = {}, s = {}, l = {}, m = {}, g = {} }
M.version = 0          -- bumped on every change; the fog cache keys on it
SEW.Place.onMove(function() M.version = M.version + 1 end)
M.asked = false

-- What has been dug and drawn (0.9): "level:cx,cy" -> 64 characters, a row
-- at a time, "1" where the players' own records make somewhere to stand
-- (SEW_Works.bits). The plans are pictures made with the layout and know
-- nothing of a pick or of an admin's works, so these are drawn over them:
-- the chunks this player has walked, or all of them for an admin who asked.
M.works = {}
M.worksVersion = 0
-- An admin's whole map: no fog, and every ladder there is.
M.all = false
-- Each level's ink: the sewers' own blue, then red, then yellow.
M.LEVEL = { [-1] = { 0.16, 0.38, 0.78 }, [-2] = { 0.78, 0.18, 0.14 }, [-3] = { 0.80, 0.64, 0.08 } }
M.WIDTHS = { 1, 3, 5 }

Net.onClient("works", function(args)
    for _, e in ipairs(args.list or {}) do
        if e.b == nil or e.b == "" then M.works[e.k] = nil else M.works[e.k] = e.b end
    end
    M.worksVersion = M.worksVersion + 1
end)

-- The works as rectangles to draw, by level: { { x, y, w }, ... } in squares,
-- one for each run of a row. Made again only when the works change.
local runsCache = { v = -1, by = {} }
function M.runs(level)
    if runsCache.v ~= M.worksVersion then
        local by = {}
        for k, bits in pairs(M.works) do
            local z, cx, cy = k:match("^(-?%d+):(-?%d+),(-?%d+)$")
            z, cx, cy = tonumber(z), tonumber(cx), tonumber(cy)
            if z then
                by[z] = by[z] or {}
                local list = by[z]
                for row = 0, 7 do
                    local start = nil
                    for col = 0, 8 do
                        local on = col < 8 and bits:sub(row * 8 + col + 1, row * 8 + col + 1) == "1"
                        if on and not start then
                            start = col
                        elseif not on and start then
                            list[#list + 1] = { cx * 8 + start, cy * 8 + row, col - start }
                            start = nil
                        end
                    end
                end
            end
        end
        runsCache = { v = M.worksVersion, by = by }
    end
    return runsCache.by[level] or {}
end

local function setFrom(list)
    local t = {}
    for _, k in ipairs(list or {}) do t[k] = 1 end
    return t
end

Net.onClient("mapState", function(args)
    M.state = { c = setFrom(args.c), s = setFrom(args.s), l = setFrom(args.l), m = args.m or {}, g = setFrom(args.g) }
    M.version = M.version + 1
end)

-- One handler per message (SEW_Net keeps one): the journal's note lives here
-- too, rather than in SEW_StoryUI, where a second onClient("found") would
-- silently have replaced this one.
Net.onClient("found", function(args)
    if args.what == "m" then
        M.state.m[args.value] = { x = args.x, y = args.y, kind = args.kind }
        U.note(U.try("player", getPlayer), getText("IGUI_SEW_JournalMarked"), 200, 210, 170)
    elseif M.state[args.what] then
        M.state[args.what][args.value] = 1
        -- The first sight of the temple's hall is worth a word.
        local h = args.what == "s" and SEW.Index.shelters[tonumber(args.value) or args.value]
        if h and h.kind == "temple_hall" then
            U.note(U.try("player", getPlayer), getText("IGUI_SEW_TempleHall"), 230, 150, 90)
        end
        -- And so is the labyrinth's heart, for whoever gets that far.
        if h and h.kind == "labyrinth_heart" then
            U.note(U.try("player", getPlayer), getText("IGUI_SEW_LabyrinthHeart"), 230, 190, 110)
        end
    end
    M.version = M.version + 1
end)

Net.onClient("revealed", function(args)
    for _, k in ipairs(args.keys or {}) do M.state.c[k] = 1 end
    M.version = M.version + 1
end)

function M.ask(player)
    Net.send(player, "mapState", {})
    M.asked = true
end

--- Which town to show: the one the player is in or under, else the nearest.
--- The temple's sheet reaches over the ends of two towns' (its passages run
--- under them): there, the town's own map is the one -- the passage is drawn
--- on it too -- and the temple's only where no town's is.
function M.townAt(x, y)
    local best, bestD = nil, 1e12
    local temple, under = SEW.Index.temple, nil
    for tid, t in pairs(SEW.Index.towns) do
        if x >= t.x0 and x <= t.x1 and y >= t.y0 and y <= t.y1 then
            if temple and tid == temple.town then under = tid else return tid end
        end
        local cx, cy = (t.x0 + t.x1) / 2, (t.y0 + t.y1) / 2
        local d = (cx - x) * (cx - x) + (cy - y) * (cy - y)
        if d < bestD then best, bestD = tid, d end
    end
    return under or best
end

--- Towns this player has walked any of, in a stable order, for switching.
function M.knownTowns()
    local seen = {}
    for k in pairs(M.state.c) do
        local cx, cy = k:match("^(-?%d+),(-?%d+)$")
        cx, cy = tonumber(cx) * 8, tonumber(cy) * 8
        for tid, t in pairs(SEW.Index.towns) do
            if cx >= t.x0 - 8 and cx <= t.x1 and cy >= t.y0 - 8 and cy <= t.y1 then seen[tid] = true end
        end
    end
    local out = {}
    for tid in pairs(seen) do out[#out + 1] = tid end
    table.sort(out)
    return out
end

--- How much of a town has been walked: found, total (chunks), and how many of
--- its shelters -- cached per state version, because the footer asks every frame.
local progressCache = {}
function M.progress(tid)
    local cached = progressCache[tid]
    if cached and cached.v == M.version then return cached.found, cached.total, cached.shelters end
    local t = SEW.Index.towns[tid]
    local shelters = 0
    for i in pairs(M.state.s) do
        local h = SEW.Index.shelters[tonumber(i) or i]
        if h and h.town == tid then shelters = shelters + 1 end
    end
    local found = 0
    for k in pairs(M.state.c) do
        local cx, cy = k:match("^(-?%d+),(-?%d+)$")
        cx, cy = tonumber(cx), tonumber(cy)
        if cx * 8 >= t.x0 - 7 and cx * 8 <= t.x1 and cy * 8 >= t.y0 - 7 and cy * 8 <= t.y1 then
            found = found + 1
        end
    end
    progressCache[tid] = { v = M.version, found = found, total = t.chunks or 0, shelters = shelters }
    return found, t.chunks or 0, shelters
end

--- The fog of one town as rectangles in chunk units: { {cx0, cy, cx1}, ... }
--- -- runs of unwalked chunks per row. Cached per town and state version.
local fogCache = {}
function M.fog(tid)
    -- An admin's whole map has none.
    if M.all then return {} end
    local cached = fogCache[tid]
    if cached and cached.v == M.version then return cached.rects end
    local t = SEW.Index.towns[tid]
    local rects = {}
    local c = M.state.c
    for cy = math.floor(t.y0 / 8), math.floor(t.y1 / 8) do
        local run = nil
        for cx = math.floor(t.x0 / 8), math.floor(t.x1 / 8) + 1 do
            local open = cx <= math.floor(t.x1 / 8) and not c[cx .. "," .. cy]
            if open and not run then
                run = cx
            elseif not open and run then
                rects[#rects + 1] = { run, cy, cx - 1 }
                run = nil
            end
        end
    end
    fogCache[tid] = { v = M.version, rects = rects }
    return rects
end

local texCache = {}
function M.tex(tid, i, j)
    local k = tid .. "_" .. i .. "_" .. j
    local t = texCache[k]
    if t == nil then
        t = U.try("map.tex", function() return getTexture("media/ui/sewermap/" .. k .. ".png") end) or false
        texCache[k] = t
    end
    return t or nil
end

---------------------------------------------------------------------------
-- The panel
---------------------------------------------------------------------------
-- Vanilla's own window (ISCollapsableWindowJoypad): a title bar to drag it by,
-- corner and edge handles to resize it, the X to close it -- and Escape, the
-- way vanilla's build window takes it (isKeyConsumed + onKeyRelease). The
-- first version was a bare ISPanelJoypad with a "B" on its close button: on a
-- PC that read as a controller prompt and the author could not close the map
-- at all. The B is shown now only while a controller has the window.
SEWMapWindow = ISCollapsableWindowJoypad:derive("SEWMapWindow")

local FOOT = 22

function SEWMapWindow:new(x, y, w, h, player, tid)
    local o = ISCollapsableWindowJoypad.new(self, x, y, w, h)
    o.player = player
    o.playerNum = U.try("playerNum", function() return player:getPlayerNum() end) or 0
    o.tid = tid
    o.minimumWidth = 360
    o.minimumHeight = 260
    o.zoomIdx = 3
    local t = SEW.Index.towns[tid]
    local px = U.try("px", function() return player:getX() end) or (t.x0 + t.x1) / 2
    local py = U.try("py", function() return player:getY() end) or (t.y0 + t.y1) / 2
    if px < t.x0 or px > t.x1 or py < t.y0 or py > t.y1 then px, py = (t.x0 + t.x1) / 2, (t.y0 + t.y1) / 2 end
    o.cx, o.cy = px, py
    o.title = getText("IGUI_SEW_MapTitle", t.name)
    -- The level shown: the one the player is at, the sewers' own from the street.
    o.level = S.levelOf(player) or C.Z
    -- An admin drawing a tunnel: { width, join, from = { x, y } } (SEW_Works.tunnel).
    o.draw = nil
    return o
end

function SEWMapWindow:createChildren()
    ISCollapsableWindowJoypad.createChildren(self)
    -- A collapsing map is one more thing to go wrong in the dark.
    if self.collapseButton then self.collapseButton:setVisible(false) end
    if self.pinButton then self.pinButton:setVisible(false) end
    local th = self:titleBarHeight()
    local bw = th + 4
    self.prevBtn = ISButton:new(self.width - 2 * bw - 4, 0, bw, th, "<", self, SEWMapWindow.prevTown)
    self.prevBtn.anchorLeft, self.prevBtn.anchorRight = false, true
    self.prevBtn:initialise()
    self:addChild(self.prevBtn)
    self.nextBtn = ISButton:new(self.width - bw - 2, 0, bw, th, ">", self, SEWMapWindow.nextTown)
    self.nextBtn.anchorLeft, self.nextBtn.anchorRight = false, true
    self.nextBtn:initialise()
    self:addChild(self.nextBtn)
    self:insertNewLineOfButtons(self.prevBtn, self.nextBtn)
    -- Along the foot, at the right: the level shown; and for an admin, the pen.
    local fy = self.height - FOOT - self:resizeWidgetHeight() + 2
    self.levelBtn = ISButton:new(self.width - 96, fy, 90, FOOT - 4, "", self, SEWMapWindow.nextLevel)
    self.levelBtn.anchorLeft, self.levelBtn.anchorRight = false, true
    self.levelBtn.anchorTop, self.levelBtn.anchorBottom = false, true
    self.levelBtn:initialise()
    self:addChild(self.levelBtn)
    if S.isAdmin(self.player) then
        self.drawBtn = ISButton:new(self.width - 196, fy, 96, FOOT - 4, "", self, SEWMapWindow.nextPen)
        self.drawBtn.anchorLeft, self.drawBtn.anchorRight = false, true
        self.drawBtn.anchorTop, self.drawBtn.anchorBottom = false, true
        self.drawBtn:initialise()
        self:addChild(self.drawBtn)
        self.joinBtn = ISButton:new(self.width - 276, fy, 76, FOOT - 4, "", self, SEWMapWindow.flipJoin)
        self.joinBtn.anchorLeft, self.joinBtn.anchorRight = false, true
        self.joinBtn.anchorTop, self.joinBtn.anchorBottom = false, true
        self.joinBtn:initialise()
        self:addChild(self.joinBtn)
    end
    self:labels()
end

--- What the buttons along the foot say, as things stand.
function SEWMapWindow:labels()
    if self.levelBtn then self.levelBtn.title = getText("IGUI_SEW_MapLevel", tostring(-self.level)) end
    if self.drawBtn then
        self.drawBtn.title = self.draw and (getText("IGUI_SEW_MapDraw") .. ": "
            .. getText("IGUI_SEW_MapWidth", tostring(self.draw.width))) or getText("IGUI_SEW_MapDraw")
    end
    if self.joinBtn then
        self.joinBtn.title = getText((not self.draw or self.draw.join) and "IGUI_SEW_MapJoin" or "IGUI_SEW_MapApart")
    end
end

--- The next level down, and round again.
function SEWMapWindow:nextLevel()
    local at = 1
    for i, l in ipairs(C.Levels) do if l == self.level then at = i end end
    self.level = C.Levels[at % #C.Levels + 1]
    if self.draw then self.draw.from = nil end
    self:labels()
end

--- The admin's pen: off, then each width in turn, then off again.
function SEWMapWindow:nextPen()
    if not self.draw then
        self.draw = { width = M.WIDTHS[1], join = true }
    else
        local at = 0
        for i, w in ipairs(M.WIDTHS) do if w == self.draw.width then at = i end end
        if at >= #M.WIDTHS then self.draw = nil else self.draw.width, self.draw.from = M.WIDTHS[at + 1], nil end
    end
    self:labels()
end

function SEWMapWindow:flipJoin()
    if self.draw then self.draw.join = not self.draw.join end
    self:labels()
end

--- A click on the map with the pen down: where the tunnel starts, and then
--- where it ends -- asked of the server, which draws it or says why not.
function SEWMapWindow:penClick(sx, sy)
    local d = self.draw
    if not d then return false end
    local wx, wy = self:toWorld(sx, sy)
    wx, wy = math.floor(wx), math.floor(wy)
    if not d.from then
        d.from = { wx, wy }
        return false
    end
    Net.send(self.player, "works", { what = "tunnel", x0 = d.from[1], y0 = d.from[2], x1 = wx, y1 = wy,
                                     width = d.width, z = self.level, join = d.join })
    d.from = nil
    return true
end

function SEWMapWindow:scale() return M.ZOOMS[self.zoomIdx] end

--- The map's own rectangle inside the window: under the title bar, above the
--- footer and the resize strip.
function SEWMapWindow:view()
    local top = self:titleBarHeight()
    local bottom = self.height - FOOT - self:resizeWidgetHeight()
    return top, bottom
end

--- World square -> screen pixel inside the window.
function SEWMapWindow:toScreen(wx, wy)
    local s = self:scale()
    local top, bottom = self:view()
    return self.width / 2 + (wx - self.cx) * s, (top + bottom) / 2 + (wy - self.cy) * s
end

function SEWMapWindow:toWorld(sx, sy)
    local s = self:scale()
    local top, bottom = self:view()
    return self.cx + (sx - self.width / 2) / s, self.cy + (sy - (top + bottom) / 2) / s
end

function SEWMapWindow:prerender()
    ISCollapsableWindowJoypad.prerender(self)
    local top, bottom = self:view()
    local P = M.PAPER
    self:drawRect(0, top, self.width, self.height - top, 0.97, P[1] * 0.55, P[2] * 0.55, P[3] * 0.55)
    self:drawRect(0, top, self.width, bottom - top, 1, P[1], P[2], P[3])
end

function SEWMapWindow:render()
    local t = SEW.Index.towns[self.tid]
    if t then self:drawMap(t) end
    ISCollapsableWindowJoypad.render(self)
    self:updateJoypad()
end

function SEWMapWindow:drawMap(t)
    local s = self:scale()
    local top, bottom = self:view()
    self:setStencilRect(0, top, self.width, bottom - top)

    local own = self.level == C.Z
    -- The plan, the tiles on screen only. It is the sewers' own level's.
    local size = M.TILE * s
    for i = 0, (own and (t.tw or 1) or 0) - 1 do
        for j = 0, (t.th or 1) - 1 do
            local sx, sy = self:toScreen(t.x0 + i * M.TILE, t.y0 + j * M.TILE)
            if sx < self.width and sy < bottom and sx + size > 0 and sy + size > top then
                local tex = M.tex(self.tid, i, j)
                if tex then self:drawTextureScaled(tex, sx, sy, size, size, 1, 1, 1, 1) end
            end
        end
    end

    -- The fog.
    local F = M.FOG
    local cs = 8 * s
    for _, r in ipairs(own and M.fog(self.tid) or {}) do
        local sx, sy = self:toScreen(r[1] * 8, r[2] * 8)
        local rw = (r[3] - r[1] + 1) * cs
        if sx < self.width and sy < bottom and sx + rw > 0 and sy + cs > top then
            self:drawRect(sx, sy, rw, cs + 0.5, 1, F[1], F[2], F[3])
        end
    end

    -- What was dug and drawn at this level, in the level's ink.
    local K = M.LEVEL[self.level] or M.INK
    for _, r in ipairs(M.runs(self.level)) do
        local sx, sy = self:toScreen(r[1], r[2])
        if sx < self.width and sy < bottom and sx + r[3] * s > 0 and sy + s > top then
            self:drawRect(sx, sy, r[3] * s, s + 0.5, 0.9, K[1], K[2], K[3])
        end
    end
    -- The pen: where the tunnel starts, and the line to the mouse.
    if self.draw and self.draw.from then
        local fx, fy = self:toScreen(self.draw.from[1], self.draw.from[2])
        local wx, wy = self:toWorld(self:getMouseX(), self:getMouseY())
        local ex, ey = math.floor(wx), math.floor(wy)
        if math.abs(ex - self.draw.from[1]) >= math.abs(ey - self.draw.from[2]) then ey = self.draw.from[2] else ex = self.draw.from[1] end
        local tx, ty = self:toScreen(ex, ey)
        local w = self.draw.width * s
        self:drawRect(math.min(fx, tx), math.min(fy, ty), math.abs(tx - fx) + w, math.abs(ty - fy) + w, 0.55, K[1], K[2], K[3])
    end

    -- Sewer gas this player knows of: a sickly ring at each stretch's middle,
    -- named when zoomed in.
    for i in pairs(own and M.state.g or {}) do
        local g = SEW.Index.gas and SEW.Index.gas[tonumber(i) or i]
        if g and g.town == self.tid then
            local sx, sy = self:toScreen(g.x + 0.5, g.y + 0.5)
            local r = math.max(5, math.sqrt(g.n) * s)
            self:drawRect(sx - r, sy - r, r * 2, r * 2, 0.35, 0.62, 0.70, 0.18)
            self:drawRectBorder(sx - r, sy - r, r * 2, r * 2, 0.9, 0.45, 0.52, 0.10)
            if s >= 1.5 then
                self:drawText(getText("IGUI_SEW_MapGas"), sx + r + 2, sy - 7, 0.40, 0.46, 0.08, 1, UIFont.Small)
            end
        end
    end

    -- Markers.
    local I = M.INK
    local mk = math.max(3, math.floor(3 * s))
    for key in pairs(M.ladders()) do
        local sh = S.custom[key] or SEW.Index.shafts[key]
        -- A ladder is on the level of its foot, and of the cover over it.
        local foot = sh and (sh.z or C.Z)
        if sh and sh.town == self.tid and (foot == self.level or foot + 1 == self.level) then
            local sx, sy = self:toScreen(sh.x + 0.5, sh.y + 0.5)
            -- An outfall in the river's blue, a ladder to the street in gold.
            if sh.outfall then
                self:drawRect(sx - mk, sy - mk, mk * 2, mk * 2, 1, 0.22, 0.48, 0.74)
            else
                self:drawRect(sx - mk, sy - mk, mk * 2, mk * 2, 1, 0.85, 0.66, 0.12)
            end
            self:drawRectBorder(sx - mk, sy - mk, mk * 2, mk * 2, 1, I[1], I[2], I[3])
            local label = sh.outfall and getText("IGUI_SEW_MapOutfall") or sh.street
            if s >= 3 and label and label ~= "" then
                self:drawText(label, sx + mk + 2, sy - 7, I[1], I[2], I[3], 1, UIFont.Small)
            end
        end
    end
    for i in pairs(own and M.state.s or {}) do
        local h = SEW.Index.shelters[tonumber(i) or i]
        if h and h.town == self.tid then
            local sx, sy = self:toScreen(h.x, h.y)
            self:drawRectBorder(sx, sy, h.w * s, h.h * s, 1, 0.20, 0.42, 0.70)
            self:drawRect(sx, sy, h.w * s, h.h * s, 0.35, 0.20, 0.42, 0.70)
            if s >= 2 then
                self:drawText(getText("IGUI_SEW_Shelter_" .. h.kind), sx, sy - 14, 0.16, 0.30, 0.52, 1, UIFont.Small)
            end
        end
    end
    for _, m in pairs(own and M.state.m or {}) do
        if type(m) == "table" and m.x and M.townAt(m.x, m.y) == self.tid then
            local sx, sy = self:toScreen(m.x + 0.5, m.y + 0.5)
            self:drawText("X", sx - 4, sy - 8, 0.70, 0.12, 0.10, 1, UIFont.Medium)
        end
    end
    local px = U.try("px", function() return self.player:getX() end)
    local py = U.try("py", function() return self.player:getY() end)
    if px and M.townAt(px, py) == self.tid then
        local sx, sy = self:toScreen(px, py)
        self:drawRect(sx - mk, sy - mk, mk * 2, mk * 2, 1, 0.78, 0.10, 0.08)
    end
    self:clearStencilRect()

    -- The footer. The percentage is formatted here and passed in whole: the
    -- translator turns %1 into a format placeholder, and a literal "%" after it
    -- ("%1% walked") came out as "2$s%" on the author's screen.
    local found, total, nShelters = M.progress(self.tid)
    local pct = total > 0 and math.floor(100 * found / total) or 0
    -- One chunk of a town of eighteen hundred is "0%", which reads as broken.
    local shown = (pct == 0 and found > 0) and "<1%" or (tostring(pct) .. "%")
    -- With the pen down the foot says how to use it.
    self:drawText(self.draw and getText("IGUI_SEW_MapDrawTip") or getText("IGUI_SEW_MapFooter", shown, nShelters),
                  8, bottom + 3, 0.92, 0.88, 0.78, 1, UIFont.Small)
end

--- The ladders to show: the ones this player has used; for an admin's whole
--- map, every one there is.
function M.ladders()
    if not M.all then return M.state.l end
    local out = {}
    for key in pairs(SEW.Index.shafts) do out[key] = 1 end
    for key in pairs(S.custom) do out[key] = 1 end
    return out
end

function SEWMapWindow:zoomBy(dir, sx, sy)
    local wx, wy
    if sx then wx, wy = self:toWorld(sx, sy) end
    self.zoomIdx = math.max(1, math.min(#M.ZOOMS, self.zoomIdx + dir))
    if wx then
        -- Keep the square under the mouse under the mouse.
        local nx, ny = self:toWorld(sx, sy)
        self.cx, self.cy = self.cx + (wx - nx), self.cy + (wy - ny)
    end
end

function SEWMapWindow:onMouseWheel(del)
    self:zoomBy(del < 0 and 1 or -1, self:getMouseX(), self:getMouseY())
    return true
end

--- The title bar moves the window (vanilla's); the map itself pans.
function SEWMapWindow:onMouseDown(x, y)
    local top, bottom = self:view()
    if y < top or y > bottom then
        return ISCollapsableWindowJoypad.onMouseDown(self, x, y)
    end
    self:bringToTop()
    self.dragging = { x = x, y = y, cx = self.cx, cy = self.cy }
    return true
end

--- With the pen down, a click that was not a drag is a point of the tunnel.
function SEWMapWindow:penUp(x, y)
    local d = self.dragging
    if self.draw and d and math.abs(x - d.x) < 4 and math.abs(y - d.y) < 4 then self:penClick(x, y) end
end

function SEWMapWindow:onMouseMove(dx, dy)
    if self.dragging then
        local d = self.dragging
        local s = self:scale()
        self.cx = d.cx - (self:getMouseX() - d.x) / s
        self.cy = d.cy - (self:getMouseY() - d.y) / s
        return
    end
    ISCollapsableWindowJoypad.onMouseMove(self, dx, dy)
end

function SEWMapWindow:onMouseMoveOutside(dx, dy)
    if self.dragging then return self:onMouseMove(dx, dy) end
    ISCollapsableWindowJoypad.onMouseMoveOutside(self, dx, dy)
end

function SEWMapWindow:onMouseUp(x, y)
    self:penUp(x, y)
    self.dragging = nil
    ISCollapsableWindowJoypad.onMouseUp(self, x, y)
end

function SEWMapWindow:onMouseUpOutside(x, y)
    self.dragging = nil
    ISCollapsableWindowJoypad.onMouseUpOutside(self, x, y)
end

--- Escape closes it, and the game does not also open its pause menu.
function SEWMapWindow:isKeyConsumed(key)
    return key == Keyboard.KEY_ESCAPE
end

function SEWMapWindow:onKeyRelease(key)
    if key ~= Keyboard.KEY_ESCAPE or not self:isVisible() then return end
    -- A tunnel half drawn: Escape lets go of it first.
    if self.draw and self.draw.from then
        self.draw.from = nil
        return
    end
    self:close()
end

function SEWMapWindow:switchTown(dir)
    local list = M.knownTowns()
    if #list == 0 then return end
    local at = 0
    for i, tid in ipairs(list) do if tid == self.tid then at = i end end
    local nxt = list[((at - 1 + dir) % #list) + 1]
    if not nxt then return end
    self.tid = nxt
    local t = SEW.Index.towns[nxt]
    self.cx, self.cy = (t.x0 + t.x1) / 2, (t.y0 + t.y1) / 2
    self.title = getText("IGUI_SEW_MapTitle", t.name)
end
function SEWMapWindow:prevTown() self:switchTown(-1) end
function SEWMapWindow:nextTown() self:switchTown(1) end

--- The stick pans and the triggers zoom, every frame, as vanilla's world map
--- does it (ISWorldMap:updateJoypad).
function SEWMapWindow:updateJoypad()
    if not self.joyfocus then return end
    local id = self.joyfocus.id
    local now = getTimestampMs()
    local dt = math.min(100, now - (self.lastJoy or now))
    self.lastJoy = now
    local ax = U.try("povX", function() return getJoypadMovementAxisX(id) end) or 0
    local ay = U.try("povY", function() return getJoypadMovementAxisY(id) end) or 0
    if math.abs(ax) < 0.5 then ax = 0 end
    if math.abs(ay) < 0.5 then ay = 0 end
    local speed = 0.4 * dt / self:scale()
    self.cx, self.cy = self.cx + ax * speed, self.cy + ay * speed
    self.zoomWait = (self.zoomWait or 0) - dt
    if self.zoomWait <= 0 then
        if isJoypadRTPressed(id) then self:zoomBy(1); self.zoomWait = 200
        elseif isJoypadLTPressed(id) then self:zoomBy(-1); self.zoomWait = 200 end
    end
end

function SEWMapWindow:onJoypadDown(button, joypadData)
    if button == Joypad.LBumper then
        self:switchTown(-1)
    elseif button == Joypad.RBumper then
        self:switchTown(1)
    elseif button == Joypad.BButton then
        self:close()
    else
        ISCollapsableWindowJoypad.onJoypadDown(self, button, joypadData)
    end
end

--- The B prompt only while a controller has the window (the Steam Deck).
function SEWMapWindow:onGainJoypadFocus(joypadData)
    ISCollapsableWindowJoypad.onGainJoypadFocus(self, joypadData)
    if self.closeButton then self:setISButtonForB(self.closeButton) end
    if self:getJoypadFocus() then
        self:restoreJoypadFocus(joypadData)
    else
        self:setJoypadFocusTopLeft(joypadData)
    end
end

function SEWMapWindow:onLoseJoypadFocus(joypadData)
    ISCollapsableWindowJoypad.onLoseJoypadFocus(self, joypadData)
    self:clearISButtons()
    self:clearJoypadFocus(joypadData)
end

function SEWMapWindow:close()
    -- An admin's whole map is asked for each time (SEW_Admin.showAll).
    M.all = false
    -- Where it was and how big, for the next time it opens this session.
    M.layout = { x = self:getX(), y = self:getY(), w = self:getWidth(), h = self:getHeight(), zoom = self.zoomIdx }
    M.window = nil
    if self.joyfocus then
        U.try("map.releaseFocus", function() setJoypadFocus(self.playerNum, nil) end)
    end
    self:setVisible(false)
    self:removeFromUIManager()
end

---------------------------------------------------------------------------
-- Opening
---------------------------------------------------------------------------
function M.open(player)
    if M.window then return M.window end
    local px = U.try("px", function() return player:getX() end) or 0
    local py = U.try("py", function() return player:getY() end) or 0
    local tid = M.townAt(px, py)
    if not tid then return nil end
    M.ask(player)
    local sw = U.try("sw", getCore and function() return getCore():getScreenWidth() end) or 1280
    local sh = U.try("sh", getCore and function() return getCore():getScreenHeight() end) or 720
    local L = M.layout
    local w = L and L.w or math.min(900, sw - 80)
    local h = L and L.h or math.min(640, sh - 80)
    local x = L and L.x or (sw - w) / 2
    local y = L and L.y or (sh - h) / 2
    local win = SEWMapWindow:new(x, y, w, h, player, tid)
    if L and L.zoom then win.zoomIdx = L.zoom end
    win:initialise()
    win:instantiate()
    win:addToUIManager()
    M.window = win
    if JoypadState and JoypadState.players and JoypadState.players[win.playerNum + 1] then
        U.try("map.focus", function() setJoypadFocus(win.playerNum, win) end)
    end
    return win
end

function M.toggle(player)
    if M.window then
        M.window:close()
        return
    end
    M.open(player)
end

-- No key (0.7.6). The map was on K from 0.3.2 (N before that, which is
-- vanilla's engine key): every default is some other mod's key too, and the
-- Workshop said so twice. The map is on the right-click menu below ground
-- (SEW_Client.fillMenu) and nowhere else. A ModOptions.ini that still holds
-- the old binding's line keeps it, unread.

return M
