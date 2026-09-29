--[[ A simulated Project Zomboid, as unkind as the engine where it matters.

    One of these runs per process: SIM_ROLE is "sp", "server" or "client".
    tests/test_flow.py wires two or three together over a simulated network.

    Where it is deliberately as harsh as the game (pz_trekship DEV_GUIDE,
    "The simulation has to be as unkind as the engine"):

      * getOrCreateGridSquare on an unloaded chunk hands back an orphan, and
        the first thing that adds to an orphan throws;
      * a square's floor is the object whose sprite carries solidfloor in the
        real tile catalogue -- a sludge tile is not one;
      * a sprite that is in neither the vanilla catalogue nor our tiledef is
        recorded as unknown (IsoObject.new takes it silently in the game and
        draws nothing);
      * containers exist only after createContainersFromSpriteProperties, and
        drop what they are handed once full;
      * instanceItem answers nil for an id the build does not have;
      * addZombiesInOutfit answers an empty list for an outfit that is not in
        both of vanilla's lists;
      * sendServerCommand is inert in single player;
      * on a client, a Lua timed action is sent to the server by class name
        with the arguments read off it by the parameter names of `new`;
        complete() never runs on a client;
      * the server's transmitAddObjectToSquare reaches a client only if that
        client has the chunk loaded; AddSpecialObject alone reaches nobody;
      * a client that edits the world is recorded (SIM.violations).
]]

SIM = SIM or {}
SIM.role = SIM_ROLE or "sp"
SIM.log = {}
SIM.violations = {}
SIM.unknownSprites = {}
SIM.unknownText = {}
SIM.notes = {}
SIM.sounds = {}
SIM.zombies = {}
SIM.lamps = {}
SIM.outbox = {}        -- messages for the network: { kind, ... }
SIM.loaded = {}        -- "cx,cy" -> true
SIM.squares = {}       -- "x,y,z" -> square
SIM.menu = nil
SIM.queue = {}         -- timed actions queued on this machine
SIM.tick = 0

-- Supplied by the Python side before the mod loads:
--   SIM.tiles[name] = { prop = "", ... }    vanilla + ours
--   SIM.items[id] = true
--   SIM.outfits[name] = true                 in both lists
--   SIM.text[key] = "text"

function isClient() return SIM.role == "client" end
function isServer() return SIM.role == "server" end

print = function(...)
    local parts = {}
    for i = 1, select("#", ...) do parts[#parts + 1] = tostring(select(i, ...)) end
    SIM.log[#SIM.log + 1] = table.concat(parts, " ")
end

unpack = unpack or table.unpack

-- Kahlua, the game's Lua, lacks some of the standard library. Remove what the
-- mod must not use, so a test fails where the game would (pz_trekship pz_sim.lua
-- does the same). `next` froze 0.2.0 under -debug: it was not removed here.
-- The sim's own code uses pairs() and keeps a private copy where it must.
local _next = next
next = nil
math.huge = nil
table.unpack = nil

local function violation(what)
    if SIM.role == "client" then SIM.violations[#SIM.violations + 1] = what end
end

---------------------------------------------------------------------------
-- Java-ish lists
---------------------------------------------------------------------------
local function List(t)
    t = t or {}
    return {
        _t = t,
        size = function(self) return #self._t end,
        get = function(self, i) return self._t[i + 1] end,
        add = function(self, v) self._t[#self._t + 1] = v end,
        remove = function(self, v)
            for i, o in ipairs(self._t) do if o == v then table.remove(self._t, i) return true end end
            return false
        end,
    }
end
SIM.List = List

---------------------------------------------------------------------------
-- Sprites, objects, containers, items
---------------------------------------------------------------------------
local function spriteOf(name)
    if not SIM.tiles[name] then SIM.unknownSprites[name] = true end
    return { getName = function() return name end,
             getProperties = function()
                 local p = SIM.tiles[name] or {}
                 return { has = function(_, k) return p[tostring(k)] ~= nil end,
                          Is = function(_, k) return p[tostring(k)] ~= nil end }
             end }
end
function getSprite(name) return spriteOf(name) end

local function Container(capacity)
    local c = { items = List(), capacity = capacity, explored = false }
    function c:getItems() return self.items end
    function c:getCapacity() return self.capacity end
    function c:getContentsWeight()
        local w = 0
        for _, it in ipairs(self.items._t) do w = w + it:getWeight() end
        return w
    end
    function c:AddItem(item)
        if type(item) == "string" then error("AddItem(String) is not what the mod should use") end
        if self:getContentsWeight() + item:getWeight() > self.capacity then return nil end
        self.items:add(item)
        return item
    end
    function c:setExplored(b) self.explored = b end
    function c:isExplored() return self.explored end
    function c:getItemWithID(id)
        for _, it in ipairs(self.items._t) do if it:getID() == id then return it end end
        return nil
    end
    c.getItemWithIDRecursiv = c.getItemWithID
    function c:containsTypeRecurse(bare)
        for _, it in ipairs(self.items._t) do if it:getType() == bare then return true end end
        return false
    end
    return c
end
SIM.Container = Container

SIM.nextItemId = 1000
function instanceItem(id)
    if not SIM.items[id] then return nil end
    local bare = id:match("%.(.+)$") or id
    SIM.nextItemId = SIM.nextItemId + 1
    local md, iid = {}, SIM.nextItemId
    return { getFullType = function() return id end, getType = function() return bare end,
             getWeight = function() return 1.0 end, getModData = function() return md end,
             getID = function() return iid end, class = "InventoryItem" }
end

local IsoObjectMT = {}
IsoObjectMT.__index = IsoObjectMT
function IsoObjectMT:getSprite() return self.sprite end
function IsoObjectMT:getModData() return self.md end
function IsoObjectMT:getSquare() return self.square end
function IsoObjectMT:getContainer() return self.container end
function IsoObjectMT:getItemContainer() return self.container end
function IsoObjectMT:createContainersFromSpriteProperties()
    local p = SIM.tiles[self.sprite:getName()] or {}
    if p.container then self.container = Container(tonumber(p.ContainerCapacity) or 50) end
end
function IsoObjectMT:getNorth() return self.north end
function IsoObjectMT:transmitCompleteItemToClients()
    if SIM.role == "server" then SIM.outbox[#SIM.outbox + 1] = { "addObject", self, true } end
end

local function newObject(sq, name, class)
    violation("IsoObject.new " .. tostring(name))
    local o = setmetatable({ sprite = spriteOf(name), md = {}, square = sq, class = class or "IsoObject" },
                           IsoObjectMT)
    return o
end

IsoObject = { new = function(sq, name, _) return newObject(sq, name) end }
IsoDoor = { new = function(_cell, sq, name, north)
    local o = newObject(sq, name, "IsoDoor")
    o.north = north
    return o
end }

function instanceof(o, class)
    if type(o) ~= "table" then return false end
    if class == "IsoDoor" then return o.class == "IsoDoor" end
    if class == "IsoWorldInventoryObject" then return o.class == "IsoWorldInventoryObject" end
    if class == "IsoObject" then return o.class ~= nil and o.class ~= "InventoryItem" end
    if class == "InventoryItem" then return o.class == "InventoryItem" end
    return false
end

---------------------------------------------------------------------------
-- Squares and the cell
---------------------------------------------------------------------------
local SquareMT = {}
SquareMT.__index = SquareMT
function SquareMT:getX() return self.x end
function SquareMT:getY() return self.y end
function SquareMT:getZ() return self.z end
function SquareMT:getObjects() return self.objects end
function SquareMT:getSpecialObjects() return self.specials end
function SquareMT:getFloor()
    for _, o in ipairs(self.objects._t) do
        local p = SIM.tiles[o.sprite:getName()]
        if p and p.solidfloor ~= nil then return o end
    end
    return nil
end
local function checkOrphan(sq)
    if sq.orphan then error("java.lang.NullPointerException: square has no chunk (orphan at "
                            .. sq.x .. "," .. sq.y .. "," .. sq.z .. ")") end
end
function SquareMT:AddTileObject(o)
    violation("AddTileObject")
    checkOrphan(self)
    self.objects:add(o)
    o.square = self
end
function SquareMT:transmitAddObjectToSquare(o, _)
    violation("transmitAddObjectToSquare")
    checkOrphan(self)
    self.objects:add(o)
    o.square = self
    if SIM.role == "server" then SIM.outbox[#SIM.outbox + 1] = { "addObject", o, false } end
end
function SquareMT:AddSpecialObject(o)
    violation("AddSpecialObject")
    checkOrphan(self)
    self.objects:add(o)
    self.specials:add(o)
    o.square = self
end
function SquareMT:transmitRemoveItemFromSquare(o)
    violation("transmitRemoveItemFromSquare")
    self.objects:remove(o)
end
function SquareMT:getChunk() return { getMinLevel = function() return -1 end } end

local function key(x, y, z) return x .. "," .. y .. "," .. z end
local function chunkKey(x, y) return math.floor(x / 8) .. "," .. math.floor(y / 8) end

function SIM.newSquare(x, y, z, orphan)
    local sq = setmetatable({ x = x, y = y, z = z, objects = List(), specials = List(), orphan = orphan },
                            SquareMT)
    if not orphan then SIM.squares[key(x, y, z)] = sq end
    return sq
end

function SIM.load(cx, cy) SIM.loaded[cx .. "," .. cy] = true end
function SIM.unload(cx, cy) SIM.loaded[cx .. "," .. cy] = nil end

local cell = {}
function cell:getGridSquare(x, y, z)
    if not SIM.loaded[chunkKey(x, y)] then return nil end
    return SIM.squares[key(x, y, z)]
end
function cell:getOrCreateGridSquare(x, y, z)
    local sq = SIM.squares[key(x, y, z)]
    if sq and SIM.loaded[chunkKey(x, y)] then return sq end
    if not SIM.loaded[chunkKey(x, y)] then return SIM.newSquare(x, y, z, true) end
    if z < -32 or z > 31 then return nil end
    return SIM.newSquare(x, y, z, false)
end
function cell:getChunkForGridSquare(x, y, _)
    return SIM.loaded[chunkKey(x, y)] and {} or nil
end
function cell:addLamppost(x, y, z, r, g, b, radius)
    local l = { x = x, y = y, z = z, radius = radius }
    SIM.lamps[l] = true
    return l
end
function cell:removeLamppost(l)
    if l == nil then error("removeLamppost(nil)") end
    SIM.lamps[l] = nil
end
function getCell() return cell end

---------------------------------------------------------------------------
-- Players
---------------------------------------------------------------------------
local PlayerMT = {}
PlayerMT.__index = PlayerMT
function PlayerMT:getX() return self.x end
function PlayerMT:getY() return self.y end
function PlayerMT:getZ() return self.z end
function PlayerMT:setX(v) self.x = v end
function PlayerMT:setY(v) self.y = v end
function PlayerMT:setZ(v) self.z = v end
function PlayerMT:setLastX(v) end
function PlayerMT:setLastY(v) end
function PlayerMT:setLastZ(v) end
function PlayerMT:getUsername() return self.name end
function PlayerMT:getVehicle() return nil end
function PlayerMT:getInventory() return self.inv end
function PlayerMT:getCurrentSquare()
    return SIM.squares[key(math.floor(self.x), math.floor(self.y), math.floor(self.z))]
end
PlayerMT.getSquare = PlayerMT.getCurrentSquare
function PlayerMT:setHaloNote(text) SIM.notes[#SIM.notes + 1] = text end
function PlayerMT:playSound(name) SIM.sounds[#SIM.sounds + 1] = name return 1 end
function PlayerMT:playSoundLocal(name) SIM.sounds[#SIM.sounds + 1] = name return 1 end
function PlayerMT:setIgnoreAutoVault(b) self.noVault = b end
function PlayerMT:faceLocation() return true end
function PlayerMT:SetVariable() end
function PlayerMT:isTimedActionInstant() return false end
function PlayerMT:getPlayerNum() return 0 end
function PlayerMT:getModData() self.md = self.md or {}; return self.md end

function SIM.newPlayer(name, x, y, z)
    return setmetatable({ name = name, x = x, y = y, z = z, inv = Container(50), noVault = false }, PlayerMT)
end

SIM.players = {}
function getPlayer() return SIM.players[1] end
function getSpecificPlayer(i) return SIM.players[i + 1] end
function getOnlinePlayers() return List(SIM.players) end

---------------------------------------------------------------------------
-- Events, mod data, text, time, sandbox
---------------------------------------------------------------------------
local function event()
    local e = { fns = {} }
    function e.Add(fn) e.fns[#e.fns + 1] = fn end
    function e.Remove(fn) end
    return e
end
Events = setmetatable({}, { __index = function(t, k) local e = event(); rawset(t, k, e); return e end })
function SIM.fire(name, ...)
    for _, fn in ipairs(Events[name].fns) do fn(...) end
end
function triggerEvent(name, ...) SIM.fire(name, ...) end

local store = {}
ModData = {
    getOrCreate = function(k) store[k] = store[k] or {}; return store[k] end,
    get = function(k) return store[k] end,
    add = function(k, v) store[k] = v end,
    transmit = function() end,
}

function getText(k, ...)
    local s = SIM.text[k]
    if not s then SIM.unknownText[k] = true; return k end
    local args = { ... }
    return (s:gsub("%%(%d)", function(n) return tostring(args[tonumber(n)]) end))
end

local hour = 12
function SIM.setHour(h) hour = h end
function getGameTime() return { getHour = function() return hour end } end

local seed = 7
function ZombRand(a, b)
    seed = (seed * 1103515245 + 12345) % 2147483648
    if b == nil then return seed % math.max(1, a) end
    return a + seed % math.max(1, b - a)
end

SandboxVars = { Sewars = { Zombies = 3 } }

function screenToIsoX(_, x, _, _) return x end
function screenToIsoY(_, _, y, _) return y end

---------------------------------------------------------------------------
-- Zombies
---------------------------------------------------------------------------
function addZombiesInOutfit(x, y, z, count, outfit, female, ...)
    if select("#", ...) ~= 7 then error("addZombiesInOutfit: expected the 13-argument overload") end
    if not SIM.outfits[outfit] then return List({}) end
    local out = {}
    for _ = 1, count do
        local zed = { x = x, y = y, z = z, outfit = outfit }
        SIM.zombies[#SIM.zombies + 1] = zed
        out[#out + 1] = zed
    end
    return List(out)
end

---------------------------------------------------------------------------
-- Network
---------------------------------------------------------------------------
function sendClientCommand(player, module, cmd, args)
    if SIM.role == "sp" then
        SIM.fire("OnClientCommand", module, cmd, player, args)
    elseif SIM.role == "client" then
        SIM.outbox[#SIM.outbox + 1] = { "clientCommand", player.name, module, cmd, args }
    else
        error("sendClientCommand on a server")
    end
end

function sendServerCommand(a, b, c, d)
    if SIM.role ~= "server" then return end      -- inert in single player
    if type(a) == "string" then
        SIM.outbox[#SIM.outbox + 1] = { "serverCommandAll", a, b, c }
    else
        SIM.outbox[#SIM.outbox + 1] = { "serverCommand", a.name, b, c, d }
    end
end

---------------------------------------------------------------------------
-- UI and timed actions
---------------------------------------------------------------------------
ISWorldObjectContextMenu = { addToolTip = function() return {} end }

function SIM.newMenu(x, y)
    local m = { x = x, y = y, options = {} }
    function m:addOption(name, target, fn, a, b, c)
        local o = { name = name, target = target, onSelect = fn, args = { a, b, c } }
        self.options[#self.options + 1] = o
        return o
    end
    return m
end

ISBaseTimedAction = {}
ISBaseTimedAction.__index = ISBaseTimedAction
function ISBaseTimedAction:derive(name)
    local cls = setmetatable({}, { __index = self })
    cls.__index = cls
    cls.Type = name
    return cls
end
function ISBaseTimedAction.new(cls, character)
    return setmetatable({ character = character }, cls)
end
function ISBaseTimedAction:isValid() return true end
function ISBaseTimedAction:waitToStart() return false end
function ISBaseTimedAction:start() end
function ISBaseTimedAction:update() end
function ISBaseTimedAction:stop() end
function ISBaseTimedAction:perform() end
function ISBaseTimedAction:complete() return true end
function ISBaseTimedAction:setActionAnim() end
function ISBaseTimedAction:getJobDelta() return 1 end

---------------------------------------------------------------------------
-- UI: panels, buttons, textures, drawing -- recorded, so a test can ask what
-- was drawn where, and whether it was inside the clip.
---------------------------------------------------------------------------
SIM.draws = {}
SIM.ui = {}
UIFont = { Small = "Small", Medium = "Medium", Large = "Large" }
Keyboard = { KEY_N = 49, KEY_M = 50, KEY_K = 37 }
Joypad = { AButton = 0, BButton = 1, XButton = 2, YButton = 3, LBumper = 4, RBumper = 5 }
JoypadState = { players = {} }
PZAPI = nil
function getTimestampMs() return SIM.tick * 16 end
function getJoypadMovementAxisX() return 0 end
function getJoypadMovementAxisY() return 0 end
function isJoypadLTPressed() return false end
function isJoypadRTPressed() return false end
function setJoypadFocus() end
function getCore() return { getScreenWidth = function() return 1920 end, getScreenHeight = function() return 1080 end } end

--- A texture only if the file is really there, as getTexture answers nil for a
--- path nothing is at.
function getTexture(path)
    local f = io.open(SIM.root .. "/../../" .. path, "rb")
    if not f then return nil end
    f:close()
    return { path = path }
end

local function record(el, kind, x, y, w, h, extra)
    SIM.draws[#SIM.draws + 1] = { kind = kind, x = x, y = y, w = w or 0, h = h or 0,
                                  el = el, clipped = el._stencil ~= nil, stencil = el._stencil, extra = extra }
end

ISUIElement = {}
ISUIElement.__index = ISUIElement
function ISUIElement:derive(name)
    local cls = setmetatable({}, { __index = self })
    cls.__index = cls
    cls.Type = name
    return cls
end
function ISUIElement.new(cls, x, y, w, h)
    return setmetatable({ x = x, y = y, width = w, height = h, children = {}, visible = true }, cls)
end
function ISUIElement:initialise() end
--- The engine's instantiate creates the Java element, whose constructor calls
--- back into createChildren (pz_trekship: panels with no children were a hole).
function ISUIElement:instantiate() if self.createChildren then self:createChildren() end end
function ISUIElement:createChildren() end
function ISUIElement:addChild(c) self.children[#self.children + 1] = c; c.parent = self end
function ISUIElement:addToUIManager() SIM.ui[self] = true end
function ISUIElement:removeFromUIManager() SIM.ui[self] = nil end
function ISUIElement:setVisible(b) self.visible = b end
function ISUIElement:getMouseX() return self._mx or 0 end
function ISUIElement:getMouseY() return self._my or 0 end
function ISUIElement:setStencilRect(x, y, w, h) self._stencil = { x, y, w, h } end
function ISUIElement:clearStencilRect() self._stencil = nil end
function ISUIElement:drawRect(x, y, w, h, a, r, g, b) record(self, "rect", x, y, w, h, { r, g, b }) end
function ISUIElement:drawRectBorder(x, y, w, h) record(self, "border", x, y, w, h) end
function ISUIElement:drawTextureScaled(tex, x, y, w, h)
    if tex == nil then error("drawTextureScaled(nil)") end
    record(self, "texture", x, y, w, h, tex.path)
end
function ISUIElement:drawText(text, x, y) record(self, "text", x, y, 0, 0, text) end
function ISUIElement:drawTextCentre(text, x, y) record(self, "text", x, y, 0, 0, text) end
function ISUIElement:prerender() end
function ISUIElement:render() end

ISPanelJoypad = ISUIElement:derive("ISPanelJoypad")
ISPanelJoypad.new = ISUIElement.new
function ISPanelJoypad:insertNewLineOfButtons(...) self._rows = (self._rows or 0) + 1 end
function ISPanelJoypad:onJoypadDown() end
function ISPanelJoypad:onGainJoypadFocus() end
function ISPanelJoypad:onLoseJoypadFocus() end
function ISPanelJoypad:getJoypadFocus() return nil end
function ISPanelJoypad:restoreJoypadFocus() end
function ISPanelJoypad:setJoypadFocusTopLeft() end
function ISPanelJoypad:clearJoypadFocus() end

ISButton = ISUIElement:derive("ISButton")
function ISButton:new(x, y, w, h, title, target, onclick)
    local o = ISUIElement.new(self, x, y, w, h)
    o.title, o.target, o.onclick = title, target, onclick
    o.borderColor = { a = 1 }; o.backgroundColor = { a = 1 }; o.backgroundColorMouseOver = { a = 1 }
    return o
end
function ISButton:setImage(t) self.image = t end
function ISButton:setJoypadButton(t) self.isJoypad = true; self.joypadTexture = t end
function ISButton:clearJoypadButton() self.isJoypad = false end
--- A click, as the engine delivers it: onclick(target, button).
function ISButton:click() if self.onclick then self.onclick(self.target, self) end end
function ISPanelJoypad:setISButtonForB(b) self.ISButtonB = b; b:setJoypadButton("B") end
function ISPanelJoypad:clearISButtons() if self.ISButtonB then self.ISButtonB:clearJoypadButton() end end

-- Vanilla's window: a title bar that drags it, resize widgets, an X that
-- closes it (ISCollapsableWindow.lua:55), and a prerender that clips to the
-- whole window which render clears (lines 169, 193).
Keyboard.KEY_ESCAPE = 1
ISCollapsableWindowJoypad = ISPanelJoypad:derive("ISCollapsableWindowJoypad")
function ISCollapsableWindowJoypad.new(cls, x, y, w, h)
    local o = ISPanelJoypad.new(cls, x, y, w, h)
    o.resizable, o.drawFrame, o.clearStentil = true, true, true
    return o
end
function ISCollapsableWindowJoypad:createChildren()
    self.closeButton = ISButton:new(1, 1, 15, 15, "", self, function(win) win:close() end)
    self:addChild(self.closeButton)
    self.resizeWidget = ISUIElement.new(ISUIElement, self.width - 10, self.height - 10, 10, 10)
    self:addChild(self.resizeWidget)
    self.collapseButton = ISButton:new(self.width - 16, 1, 15, 15, "", self, nil)
    self:addChild(self.collapseButton)
    self.pinButton = ISButton:new(self.width - 16, 1, 15, 15, "", self, nil)
    self:addChild(self.pinButton)
end
function ISCollapsableWindowJoypad:titleBarHeight() return 16 end
function ISCollapsableWindowJoypad:resizeWidgetHeight() return 12 end
function ISCollapsableWindowJoypad:prerender()
    self:drawRect(0, 0, self.width, 16, 1, 0, 0, 0)
    self:setStencilRect(0, 0, self.width, self.height)
end
function ISCollapsableWindowJoypad:render() self:clearStencilRect() end
function ISCollapsableWindowJoypad:onMouseDown(x, y) self.moving = true end
function ISCollapsableWindowJoypad:onMouseMove(dx, dy) if self.moving then self.x, self.y = self.x + dx, self.y + dy end end
function ISCollapsableWindowJoypad:onMouseMoveOutside(dx, dy) self:onMouseMove(dx, dy) end
function ISCollapsableWindowJoypad:onMouseUp() self.moving = false end
function ISCollapsableWindowJoypad:onMouseUpOutside() self.moving = false end
function ISCollapsableWindowJoypad:close() self:setVisible(false) end
function ISUIElement:getX() return self.x end
function ISUIElement:getY() return self.y end
function ISUIElement:getWidth() return self.width end
function ISUIElement:getHeight() return self.height end
function ISUIElement:setWidth(w) self.width = w end
function ISUIElement:setHeight(h) self.height = h end
function ISUIElement:bringToTop() end
function ISUIElement:isVisible() return self.visible end

CharacterActionAnims = {}
ISTimedActionQueue = { add = function(a) SIM.queue[#SIM.queue + 1] = a end, clear = function() end }

luautils = {}
--- Vanilla walks to a free square next to the target, and returns early if the
--- player is already within 1.6 on both axes. The sim puts them one square
--- short, diagonally where it can, which is the far end of what vanilla allows.
function luautils.walkAdj(p, sq)
    local dx, dy = math.abs(sq:getX() + 0.5 - p.x), math.abs(sq:getY() + 0.5 - p.y)
    if dx <= 1.6 and dy <= 1.6 then return true end
    p.x, p.y = sq:getX() + 1.5, sq:getY() + 1.5
    return true
end

--- The names of a function's parameters, as the engine reads them
--- (NetTimedAction.set walks Prototype.locvars).
local function params(fn)
    local out, i = {}, 1
    while true do
        local n = debug.getlocal(fn, i)
        if not n then break end
        out[#out + 1] = n
        i = i + 1
    end
    return out
end
SIM.params = params

--- Runs every queued action on this machine. On a client the action is
--- started and then handed to the server by class name and arguments.
function SIM.runActions()
    local q = SIM.queue
    SIM.queue = {}
    for _, a in ipairs(q) do
        if a:isValid() then
            a:waitToStart()
            a:start()
            for _ = 1, math.min(a.maxTime or 1, 5) do a:update() end
            if SIM.role == "client" then
                local names = params(getmetatable(a).new or a.new)
                local args = {}
                -- self and character are not sent: the server supplies its own copy of the player.
                for i = 3, #names do args[#args + 1] = { names[i], a[names[i]] } end
                SIM.outbox[#SIM.outbox + 1] = { "netAction", a.character.name, a.Type, args }
                a:perform()
            else
                a:perform()
                a:complete()
            end
        else
            SIM.log[#SIM.log + 1] = "[SIM] action not valid: " .. tostring(a.Type)
        end
    end
end

--- The server's half: rebuild the action by its global class name from the
--- arguments the client sent, as NetTimedAction.parse does.
function SIM.serverAction(player, className, args)
    local cls = _G[className]
    if not cls then error("NetTimedAction: no global class " .. tostring(className)) end
    local vals = {}
    for i, pair in ipairs(args) do vals[i] = pair[2] end
    local a = cls:new(player, unpack(vals))
    if a:isValid() then a:complete() else SIM.log[#SIM.log + 1] = "[SIM] server: action not valid" end
end

---------------------------------------------------------------------------
-- require
---------------------------------------------------------------------------
SIM.root = SIM.root or "."
SIM.required = {}
function require(name)
    if SIM.required[name] then return SIM.required[name] end
    if name == "TimedActions/ISBaseTimedAction" then return ISBaseTimedAction end
    if name == "ISUI/ISPanelJoypad" then return ISPanelJoypad end
    if name == "ISUI/ISButton" then return ISButton end
    if name == "ISUI/ISCollapsableWindowJoypad" then return ISCollapsableWindowJoypad end
    local found
    for _, side in ipairs({ "shared", "client", "server" }) do
        local path = SIM.root .. "/" .. side .. "/" .. name .. ".lua"
        local f = io.open(path, "r")
        if f then f:close(); found = path; break end
    end
    if not found then error("require: no such file " .. name) end
    SIM.required[name] = true
    local r = dofile(found)
    SIM.required[name] = r or true
    return SIM.required[name]
end

function SIM.tickN(n)
    for _ = 1, n do
        SIM.tick = SIM.tick + 1
        SIM.fire("OnTick")
    end
end
