--[[ Sewars -- reading plans and journals: the menu and the page.

    Right-click a Municipal Sewer Plan: *Read the sewer plan* -- the server
    reveals its sheet on your map (SEW_Story.lua). Right-click a journal: *Read
    the journal* -- its page opens here, and the server marks what it describes
    on your map. The text is the client's own (IG_UI.json, keyed by what the
    journal points at, with the street and direction the generator wrote into
    SEW.Index.journals), so it is translated and the same for everybody.

    Inventory menu entries are either items or stacks with their own `items`
    list; code that handles one shape does nothing for the other
    (pz_trekship DEV_GUIDE, "A right-click offers nothing for a mod item").
]]

if isServer() then return end

require "ISUI/ISPanelJoypad"
require "ISUI/ISCollapsableWindowJoypad"
require "ISUI/ISButton"
require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Net"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local Net = SEW.Net

local SU = {}
SEW.StoryUI = SU

local function selected(items)
    local out = {}
    for _, v in ipairs(items or {}) do
        if instanceof(v, "InventoryItem") then
            out[#out + 1] = v
        elseif type(v) == "table" and v.items then
            for _, it in ipairs(v.items) do
                if instanceof(it, "InventoryItem") then out[#out + 1] = it end
            end
        end
    end
    return out
end

function SU.readPlan(player, item)
    Net.send(player, "readPlan", { id = item:getID() })
end

--- The page of journal `idx`, as title and lines.
function SU.page(idx)
    local j = SEW.Index.journals[idx]
    if not j then return nil end
    local street = (j.street and j.street ~= "") and j.street or getText("IGUI_SEW_UnderUnknown")
    local title = getText("IGUI_SEW_J_" .. j.text .. "_Title")
    local body = getText("IGUI_SEW_J_" .. j.text .. "_Body", street, j.dir)
    local lines = {}
    for line in string.gmatch(body .. "\n", "([^\n]*)\n") do lines[#lines + 1] = line end
    return title, lines
end

function SU.readJournal(player, item)
    local idx = U.try("journal.md", function() return item:getModData().SewarsJournal end)
    if not idx then return end
    SU.open(player, idx)
    Net.send(player, "readJournal", { id = item:getID() })
end

function SU.fillInventoryMenu(playerNum, context, items)
    local player = getSpecificPlayer(playerNum)
    if not player then return end
    for _, it in ipairs(selected(items)) do
        local full = it:getFullType()
        if full == C.PlanItem then
            context:addOption(getText("ContextMenu_SEW_ReadPlan"), player, SU.readPlan, it)
            return
        elseif full == C.JournalItem then
            context:addOption(getText("ContextMenu_SEW_ReadJournal"), player, SU.readJournal, it)
            return
        end
    end
end
Events.OnFillInventoryObjectContextMenu.Add(function(...) U.try("storyMenu", SU.fillInventoryMenu, ...) end)

Net.onClient("planRead", function(args)
    local p = getPlayer()
    if (args.n or 0) > 0 then
        U.note(p, getText("IGUI_SEW_PlanRevealed", args.n), 200, 210, 170)
    else
        U.note(p, getText("IGUI_SEW_PlanKnown"), 200, 190, 160)
    end
end)

---------------------------------------------------------------------------
-- The page
---------------------------------------------------------------------------
-- Vanilla's window, as the map is: a title bar to move it by, the X and Escape
-- to close it, and a B prompt only while a controller has it.
SEWJournalWindow = ISCollapsableWindowJoypad:derive("SEWJournalWindow")

function SEWJournalWindow:new(x, y, w, h, player, idx)
    local o = ISCollapsableWindowJoypad.new(self, x, y, w, h)
    o.player = player
    o.playerNum = U.try("playerNum", function() return player:getPlayerNum() end) or 0
    o.idx = idx
    o.title, o.lines = SU.page(idx)
    o.resizable = false
    return o
end

function SEWJournalWindow:createChildren()
    ISCollapsableWindowJoypad.createChildren(self)
    if self.collapseButton then self.collapseButton:setVisible(false) end
    if self.pinButton then self.pinButton:setVisible(false) end
end

function SEWJournalWindow:prerender()
    ISCollapsableWindowJoypad.prerender(self)
    -- Damp paper, dark ink.
    local th = self:titleBarHeight()
    self:drawRect(0, th, self.width, self.height - th, 0.97, 0.78, 0.72, 0.58)
end

function SEWJournalWindow:render()
    local y = self:titleBarHeight() + 14
    for _, line in ipairs(self.lines or {}) do
        self:drawText(line, 22, y, 0.18, 0.14, 0.10, 1, UIFont.Small)
        y = y + 18
    end
    ISCollapsableWindowJoypad.render(self)
end

function SEWJournalWindow:isKeyConsumed(key)
    return key == Keyboard.KEY_ESCAPE
end

function SEWJournalWindow:onKeyRelease(key)
    if key == Keyboard.KEY_ESCAPE and self:isVisible() then self:close() end
end

function SEWJournalWindow:onJoypadDown(button, joypadData)
    if button == Joypad.BButton then
        self:close()
    else
        ISCollapsableWindowJoypad.onJoypadDown(self, button, joypadData)
    end
end

function SEWJournalWindow:onGainJoypadFocus(joypadData)
    ISCollapsableWindowJoypad.onGainJoypadFocus(self, joypadData)
    if self.closeButton then self:setISButtonForB(self.closeButton) end
    self:setJoypadFocusTopLeft(joypadData)
end

function SEWJournalWindow:onLoseJoypadFocus(joypadData)
    ISCollapsableWindowJoypad.onLoseJoypadFocus(self, joypadData)
    self:clearISButtons()
    self:clearJoypadFocus(joypadData)
end

function SEWJournalWindow:close()
    SU.window = nil
    if self.joyfocus then U.try("journal.releaseFocus", function() setJoypadFocus(self.playerNum, nil) end) end
    self:setVisible(false)
    self:removeFromUIManager()
end

function SU.open(player, idx)
    if SU.window then SU.window:close() end
    local title, lines = SU.page(idx)
    if not title then return nil end
    local w = 520
    local h = 30 + #lines * 18 + 40
    local sw = U.try("sw", function() return getCore():getScreenWidth() end) or 1280
    local sh = U.try("sh", function() return getCore():getScreenHeight() end) or 720
    local win = SEWJournalWindow:new((sw - w) / 2, (sh - h) / 2, w, h, player, idx)
    win:initialise()
    win:instantiate()
    win:addToUIManager()
    SU.window = win
    if JoypadState and JoypadState.players and JoypadState.players[win.playerNum + 1] then
        U.try("journal.focus", function() setJoypadFocus(win.playerNum, win) end)
    end
    return win
end

return SU
