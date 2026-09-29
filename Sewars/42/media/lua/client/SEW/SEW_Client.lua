--[[ Sewars -- the player's side: the menus, the climb, the dark.

    A client never changes the world. It offers *Climb down into the sewer*
    at a cover and *Climb out to the street* at a ladder, walks its player
    there and queues SEWClimb; the server's half of that action grants the
    move, and `go` comes back here, where the client moves **its own**
    character (DEV_GUIDE, "The server owns the sewers; a client asks").

    Below ground it also looks after its own player:

      * the arrival waits for the floor to reach this machine before
        stepping onto it (the server sends the squares, then `go`);
      * the vault switch: IsoPlayer.ignoreAutoVault is set while below and
        cleared on the way up. Climbing a wall down here would step off the
        tunnel into squares that do not exist (pz_trekship DEV_GUIDE, "A wall
        keeps a player in only where the engine thinks there is a building");
        a flag left on would follow the character for the life of the save;
      * a floor check: no floor under a player below ground asks the server
        for a rescue, at most every few seconds;
      * the light: lampposts at the shafts (daylight through the cover's
        holes, dimmer at night) and in the shelters, hung by this client
        because the engine lights a lamppost only for the machine that made it;
      * and the sound of the place.
]]

if isServer() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Net"
require "SEW/SEW_Sewer"
require "SEW/SEW_Actions"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local Net = SEW.Net
local S = SEW.Sewer

local Client = {}
SEW.Client = Client

---------------------------------------------------------------------------
-- The menus
---------------------------------------------------------------------------
function Client.climbDown(playerObj, sq)
    if not luautils.walkAdj(playerObj, sq, false) then return end
    ISTimedActionQueue.add(SEWClimb:new(playerObj, sq:getX(), sq:getY(), "down"))
end

function Client.climbUp(playerObj, shaft)
    local sq = U.square(shaft.x, shaft.y, C.Z, false)
    if not sq then return end
    if not luautils.walkAdj(playerObj, sq, false) then return end
    ISTimedActionQueue.add(SEWClimb:new(playerObj, shaft.x, shaft.y, "up"))
end

--- What the menu offers where the player clicked. Pure, so the tests can
--- ask it: returns ("down", square) at a cover that leads somewhere,
--- ("shut", square) at one that does not, ("up", shaft) at a ladder below.
function Client.offer(playerObj, x, y)
    if S.below(playerObj) then
        local shaft = S.shaftNear(x, y, C.ClickSlack + 0.5)
        if shaft then return "up", shaft end
        return nil
    end
    local sq = S.manholeNear(x, y, C.ClickSlack)
    if not sq then return nil end
    if S.shaftAt(sq:getX(), sq:getY()) then return "down", sq end
    return "shut", sq
end

function Client.fillMenu(playerIndex, context, worldobjects, test)
    local playerObj = getSpecificPlayer(playerIndex)
    if not playerObj or playerObj:getVehicle() then return end
    -- The map, anywhere below ground (and on its key, SEW_Map).
    if S.below(playerObj) and SEW.Map and not test then
        context:addOption(getText("ContextMenu_SEW_Map"), playerObj, SEW.Map.toggle)
    end
    local x, y = U.clickedSquare(playerIndex, context, playerObj)
    if not x then return end
    local what, where = Client.offer(playerObj, x, y)
    if not what then return end
    if test then return true end
    if what == "down" then
        local opt = context:addOption(getText("ContextMenu_SEW_Enter"), playerObj, Client.climbDown, where)
        local tip = ISWorldObjectContextMenu.addToolTip()
        tip.description = getText(S.hasLiftTool(playerObj) and "Tooltip_SEW_EnterTool" or "Tooltip_SEW_Enter")
        opt.toolTip = tip
    elseif what == "shut" then
        local opt = context:addOption(getText("ContextMenu_SEW_Enter"), nil, nil)
        opt.notAvailable = true
        local tip = ISWorldObjectContextMenu.addToolTip()
        tip.description = getText("Tooltip_SEW_Shut")
        opt.toolTip = tip
    elseif what == "up" then
        local opt = context:addOption(getText("ContextMenu_SEW_Exit"), playerObj, Client.climbUp, where)
        if where.street and where.street ~= "" then
            local tip = ISWorldObjectContextMenu.addToolTip()
            tip.description = getText("Tooltip_SEW_ExitTo", where.street)
            opt.toolTip = tip
        end
    end
end
Events.OnFillWorldObjectContextMenu.Add(function(...) return U.try("menu", Client.fillMenu, ...) end)

---------------------------------------------------------------------------
-- Moving
---------------------------------------------------------------------------
local pending = nil        -- { x, y, z, street, mode, waited }

Net.onClient("go", function(args)
    pending = { x = args.x, y = args.y, z = args.z, street = args.street, mode = args.mode, waited = 0 }
end)

local REFUSED = { shut = "IGUI_SEW_Shut", reach = "IGUI_SEW_Reach", level = "IGUI_SEW_Level",
                  unready = "IGUI_SEW_Unready" }
Net.onClient("refused", function(args)
    local p = getPlayer()
    U.note(p, getText(REFUSED[args.why] or "IGUI_SEW_Refused"), 220, 170, 120)
end)

--- True when this machine has the square and it can be stood on.
local function arrivable(x, y, z)
    local sq = U.square(x, y, z, false)
    return sq ~= nil and U.floorOf(sq) ~= nil
end

function Client.arrive(p)
    local m = pending
    if not m then return end
    if not arrivable(m.x, m.y, m.z) then
        m.waited = m.waited + 1
        if m.waited < C.ArriveTimeout then return end
        U.log("WARN the floor at %d,%d,%d never reached this machine; not moving", m.x, m.y, m.z)
        U.note(p, getText("IGUI_SEW_Unready"), 220, 170, 120)
        pending = nil
        return
    end
    pending = nil
    U.teleport(p, m.x, m.y, m.z)
    Client.vault(p)
    if m.mode == "down" then
        U.try("sound", function() p:playSound("SEW_Ladder") end)
        if m.street and m.street ~= "" then
            U.note(p, getText("IGUI_SEW_DownUnder", m.street), 190, 200, 170)
        else
            U.note(p, getText("IGUI_SEW_Down"), 190, 200, 170)
        end
    elseif m.mode == "up" then
        U.try("sound", function() p:playSound("SEW_Lid") end)
        if m.street and m.street ~= "" then
            U.note(p, getText("IGUI_SEW_UpOnto", m.street), 200, 200, 170)
        end
        Client.clearLamps()
    elseif m.mode == "rescue" then
        U.note(p, getText("IGUI_SEW_Rescued"), 200, 190, 150)
    end
end

---------------------------------------------------------------------------
-- Looking after the player below
---------------------------------------------------------------------------
local holdingVault = false
function Client.vault(p)
    local below = S.below(p)
    if below and not holdingVault then
        U.try("vault.on", function() p:setIgnoreAutoVault(true) end)
        holdingVault = true
    elseif not below and holdingVault then
        U.try("vault.off", function() p:setIgnoreAutoVault(false) end)
        holdingVault = false
    end
end

local lastRescue = -1e9
function Client.checkFloor(p, now)
    if pending or not S.below(p) then return end
    local sq = U.try("square", function() return p:getCurrentSquare() end)
    if sq and U.floorOf(sq) then return end
    if now - lastRescue < 180 then return end
    lastRescue = now
    U.log("no floor under the player at %.1f,%.1f,%.1f: asking for a rescue", p:getX(), p:getY(), p:getZ())
    Net.send(p, "rescue", {})
end

-- key -> IsoLightSource
local lamps = {}
local function lampKey(x, y) return x .. "," .. y end

function Client.clearLamps()
    local cell = U.cell()
    for k, light in pairs(lamps) do
        if cell then U.try("removeLamppost", function() cell:removeLamppost(light) end) end
        lamps[k] = nil
    end
end

local function lamp(x, y, c)
    local k = lampKey(x, y)
    if lamps[k] then return end
    local cell = U.cell()
    if not cell or not U.square(x, y, C.Z, false) then return end
    local light = U.try("addLamppost", function()
        return cell:addLamppost(x, y, C.Z, c[1], c[2], c[3], c[4])
    end)
    if light then lamps[k] = light end
end

-- Kahlua has no `next` (DEV_GUIDE, "Kahlua is not Lua 5.4"): 0.2.0 called it
-- here every 90 ticks and -debug stopped the game on each one.
local function anyLamp()
    for _ in pairs(lamps) do return true end
    return false
end

function Client.light(p)
    if not S.below(p) then
        if anyLamp() then Client.clearLamps() end
        return
    end
    local px, py = p:getX(), p:getY()
    local hour = U.try("hour", function() return getGameTime():getHour() end) or 12
    local shaftLight = (hour >= 6 and hour < 20) and C.ShaftLightDay or C.ShaftLightNight
    local cell = U.cell()
    -- Drop the far ones first, so the count stays small.
    for k, light in pairs(lamps) do
        local lx, ly = k:match("^(-?%d+),(-?%d+)$")
        if U.dist(px, py, tonumber(lx), tonumber(ly)) > C.LightRange + 8 then
            if cell then U.try("removeLamppost", function() cell:removeLamppost(light) end) end
            lamps[k] = nil
        end
    end
    local r = C.LightRange
    -- 442 shafts and 93 shelters: a walk of the whole index every 90 ticks
    -- costs nothing worth slicing.
    for _, s in pairs(SEW.Index.shafts) do
        if math.abs(s.x - px) <= r and math.abs(s.y - py) <= r then lamp(s.x, s.y, shaftLight) end
    end
    for _, h in ipairs(SEW.Index.shelters) do
        local cx, cy = h.x + math.floor(h.w / 2), h.y + math.floor(h.h / 2)
        if math.abs(cx - px) <= r and math.abs(cy - py) <= r then lamp(cx, cy, C.ShelterLight) end
    end
end

local nextSound = 0
function Client.ambience(p, now)
    if not S.below(p) then return end
    if now < nextSound then return end
    local lo, hi = C.AmbienceTicks[1], C.AmbienceTicks[2]
    nextSound = now + ZombRand(lo, hi)
    if now < lo then return end
    local name = C.Ambience[ZombRand(#C.Ambience) + 1]
    U.try("ambience", function() p:playSoundLocal(name) end)
end

---------------------------------------------------------------------------
-- The dev build's kit
---------------------------------------------------------------------------
--- A torch, batteries and a crowbar, once per character, for testing. Only in
--- the installed dev copy (SEW.Dev, written by tools/deploy_windows.py) and
--- only in single player, where this process is also the authority: on a
--- server a client adding to its own inventory would be a client edit.
function Client.devKit(p)
    if not SEW.Dev or isClient() or not p then return false end
    local md = U.try("devKit.md", function() return p:getModData() end)
    if not md then return false end
    local inv = U.try("devKit.inv", function() return p:getInventory() end)
    if not inv then return false end
    -- 0.3: a Muldraugh sewer plan, once, even for a character that had the
    -- first kit -- so the map's reveal can be tried without hunting for one.
    if not md.SEWDevPlan and SEW.Index and SEW.Index.plans then
        for i, pl in ipairs(SEW.Index.plans) do
            if pl.town == "muldraugh" then
                local plan = U.try("devKit.plan", function() return instanceItem(C.PlanItem) end)
                if plan then
                    plan:getModData().SewarsPlan = i
                    inv:AddItem(plan)
                    md.SEWDevPlan = true
                end
                break
            end
        end
    end
    if md.SEWDevKit then return false end
    local given = 0
    for _, id in ipairs(C.DevKit) do
        if U.addItem(inv, id) then given = given + 1 end
    end
    md.SEWDevKit = true
    U.log("dev build: gave %s %d items (%s)", tostring(U.try("name", function() return p:getUsername() end)),
          given, table.concat(C.DevKit, ", "))
    return true
end
Events.OnCreatePlayer.Add(function(_, p) U.try("devKit", Client.devKit, p) end)

local tick = 0
Events.OnTick.Add(function()
    tick = tick + 1
    local p = getPlayer()
    if not p then return end
    if pending then U.try("arrive", Client.arrive, p) end
    if tick % 10 == 0 then
        U.try("vault", Client.vault, p)
        U.try("floor", Client.checkFloor, p, tick)
    end
    if tick % 90 == 0 then U.try("light", Client.light, p) end
    if tick % 30 == 0 then U.try("ambience", Client.ambience, p, tick) end
end)

return Client
