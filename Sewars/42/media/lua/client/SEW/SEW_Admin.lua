--[[ Sewars -- an admin's menu: the works (SEW_Works) asked for by a click.

    Runs in single player and on any client (never on a server). Nothing
    here changes anything: every entry sends a command, and the server asks
    its own copy of the player whether they are an admin (SEW_Sewer.isAdmin)
    before it does a thing. The menu is only shown to one.

    One entry on the right-click menu, *Sewers (admin)*, and under it what
    can be done where the click was:

      on a way down       who may use it (both ways, in only, out only,
                          nobody); taking away one an admin put in
      on the street       a way down put here: cover, trapdoor or grate
      in a tunnel         a shaft down a level; a room set down behind a
                          wall (the mod's four, or a template)
      anywhere            a corner marked, and from it a box: kept as a room
                          template, or (below ground) marked as indoors
      below ground        this room marked as indoors, or no longer; what
                          this square is to the game
      and                 the sewer round here rebuilt; a template
                          forgotten; the whole map
]]

if isServer() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Net"
require "SEW/SEW_Sewer"
require "SEW/SEW_Indoors"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local Net = SEW.Net
local S = SEW.Sewer

local A = {}
SEW.Admin = A

-- The corner of a box, marked by a click: { x, y, z }.
A.corner = nil
-- The room templates the server has: { { name, w, h, loot }, ... }.
A.templates = {}

A.MODES = { "open", "in", "shut", "none" }
A.KINDS = { "cover", "trapdoor", "outfall" }
A.ROOMS = { "maintenance", "pump", "squat", "laststand" }
A.LOOT = { "none", "medical", "military", "gunstore", "police", "survival", "food", "tools", "mechanics",
           "electronics", "laboratory" }
A.WAYS = { { "north", 0, -1 }, { "east", 1, 0 }, { "south", 0, 1 }, { "west", -1, 0 } }

--- A template's name as a player reads it: its stock's word and its number.
function A.templateName(name)
    local loot, n = tostring(name):match("^(%a+) (%d+)$")
    if not loot then return tostring(name) end
    return getText("ContextMenu_SEW_Loot_" .. loot) .. " " .. n
end

--- Asks the server for a work.
function A.work(playerObj, args)
    return Net.send(playerObj, "works", args)
end

function A.access(playerObj, args)
    return Net.send(playerObj, "access", args)
end

function A.mark(playerObj, x, y, z)
    A.corner = { x = x, y = y, z = z }
    U.note(playerObj, getText("IGUI_SEW_Wk_corner"), 200, 210, 170)
end

function A.showAll(playerObj)
    if not SEW.Map then return end
    SEW.Map.all = true
    A.work(playerObj, { what = "all" })
    if not SEW.Map.window then SEW.Map.toggle(playerObj) end
end

local function submenu(context, text)
    local opt = context:addOption(text, nil, nil)
    local sub = context:getNew(context)
    context:addSubMenu(opt, sub)
    return sub, opt
end

--- The admin's entry and what is under it. `x, y`: the square clicked;
--- `level`: the level the player is at (0 on the street); `sewer`: that
--- level when it is one of the sewer's (S.levelOf), else nil; `shaft`: the
--- way down the click was on, if it was on one.
function A.menu(playerObj, context, x, y, level, sewer, shaft)
    local top = submenu(context, getText("ContextMenu_SEW_Admin"))
    local px, py = math.floor(playerObj:getX()), math.floor(playerObj:getY())

    if shaft and not shaft.exit then
        local z = shaft.z or C.Z
        local now = S.accessMode(S.access, shaft.x, shaft.y, z)
        local way = submenu(top, getText("ContextMenu_SEW_AdmWay"))
        for _, mode in ipairs(A.MODES) do
            local opt = way:addOption(getText("ContextMenu_SEW_AdmWay_" .. mode), playerObj, A.access,
                                      { x = shaft.x, y = shaft.y, z = z, mode = mode })
            -- How it stands now is shown, and is not there to choose.
            if mode == now then opt.notAvailable = true end
        end
        if shaft.custom then
            top:addOption(getText("ContextMenu_SEW_AdmRemove"), playerObj, A.work,
                          { what = "remove", x = shaft.x, y = shaft.y, z = z })
        end
    elseif level == 0 then
        local put = submenu(top, getText("ContextMenu_SEW_AdmPut"))
        for _, kind in ipairs(A.KINDS) do
            put:addOption(getText("ContextMenu_SEW_AdmPut_" .. kind), playerObj, A.work,
                          { what = "entrance", x = x, y = y, kind = kind })
        end
    end

    if sewer then
        if S.isLevel(level - 1) then
            top:addOption(getText("ContextMenu_SEW_AdmShaft"), playerObj, A.work, { what = "shaft", x = px, y = py })
        end
        local room = submenu(top, getText("ContextMenu_SEW_AdmRoom"))
        for _, w in ipairs(A.WAYS) do
            local way = submenu(room, getText("IGUI_SEW_Dir_" .. w[1]))
            for _, kind in ipairs(A.ROOMS) do
                way:addOption(getText("IGUI_SEW_Shelter_" .. kind), playerObj, A.work,
                              { what = "shelter", kind = kind, dx = w[2], dy = w[3] })
            end
            for _, t in ipairs(A.templates) do
                way:addOption(A.templateName(t.name), playerObj, A.work,
                              { what = "place", name = t.name, dx = w[2], dy = w[3] })
            end
        end
    end

    top:addOption(getText("ContextMenu_SEW_AdmCorner"), playerObj, A.mark, x, y, level)
    local c = A.corner
    if c and c.z == level then
        local keep = submenu(top, getText("ContextMenu_SEW_AdmCapture"))
        for _, loot in ipairs(A.LOOT) do
            keep:addOption(getText("ContextMenu_SEW_Loot_" .. loot), playerObj, A.work,
                           { what = "capture", x0 = c.x, y0 = c.y, x1 = x, y1 = y, loot = loot })
        end
        if level < 0 then
            top:addOption(getText("ContextMenu_SEW_AdmIndoorBox"), playerObj, A.work,
                          { what = "indoor", x0 = c.x, y0 = c.y, x1 = x, y1 = y })
        end
    end
    if level < 0 then
        top:addOption(getText("ContextMenu_SEW_AdmIndoorRoom"), playerObj, A.work, { what = "indoor", x = x, y = y })
        if SEW.Indoors.at(x, y, level) then
            top:addOption(getText("ContextMenu_SEW_AdmOutdoor"), playerObj, A.work, { what = "outdoor", x = x, y = y })
        end
        top:addOption(getText("ContextMenu_SEW_AdmCheck"), playerObj, A.work, { what = "check", x = x, y = y })
        top:addOption(getText("ContextMenu_SEW_AdmRebuild"), playerObj, A.work, { what = "rebuild" })
    end
    if #A.templates > 0 then
        local forget = submenu(top, getText("ContextMenu_SEW_AdmForget"))
        for _, t in ipairs(A.templates) do
            forget:addOption(A.templateName(t.name), playerObj, A.work, { what = "forget", name = t.name })
        end
    end
    top:addOption(getText("ContextMenu_SEW_AdmMap"), playerObj, A.showAll)
    return top
end

---------------------------------------------------------------------------
-- What the server says back
---------------------------------------------------------------------------
-- The ways down an admin put in, and the templates there are. On a client
-- only: in single player the server's own table is S.custom already.
Net.onClient("shafts", function(args)
    if isClient() then
        local list = {}
        for k, v in pairs(args.list or {}) do list[k] = v end
        S.custom = list
    end
    A.templates = {}
    for _, t in ipairs(args.templates or {}) do A.templates[#A.templates + 1] = t end
end)

-- What is marked as indoors: declared to the engine here and now, as a
-- player's own room is on a client (SEW_Indoors). A client only: single
-- player's list is the saved state's, and its marks are declared as made.
Net.onClient("indoor", function(args)
    local In = SEW.Indoors
    if isClient() then
        local list = {}
        for id, m in pairs(args.list or {}) do
            local rects = {}
            for _, r in ipairs(m.rects or {}) do rects[#rects + 1] = { r[1], r[2], r[3], r[4] } end
            list[id] = { z = m.z, rects = rects }
        end
        In.marks = list
        In.touch()
    end
    if not isServer() then In.declareAll(false) end
end)

local WORKED = { entrance = true, shaft = true, tunnel = true, room = true, template = true, forgot = true,
                 removed = true, rebuilt = true, indoor = true, indoorLater = true, outdoor = true,
                 check_room = true, check_marked = true, check_sewer = true, check_no = true }
Net.onClient("worked", function(args)
    if not WORKED[args.what] then return end
    local value = args.name and A.templateName(args.name) or tostring(args.n or 0)
    U.note(getPlayer(), getText("IGUI_SEW_Wk_" .. args.what, value), 200, 210, 170)
end)

return A
