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

--- Pulling at one of the nest's walls: walk to whichever side of it is
--- nearer, then SEWPry, which the server grants or refuses (SEW_Nest.pry).
function Client.pry(playerObj, which)
    local ax, ay, bx, by = S.gateSquares(which)
    if not ax then return end
    local px, py = playerObj:getX(), playerObj:getY()
    local x, y = ax, ay
    if U.dist(px, py, bx + 0.5, by + 0.5) < U.dist(px, py, ax + 0.5, ay + 0.5) then x, y = bx, by end
    local sq = U.square(x, y, C.Z, false)
    if not sq then return end
    if not luautils.walkAdj(playerObj, sq, false) then return end
    ISTimedActionQueue.add(SEWPry:new(playerObj, x, y, which))
end

--- The nest's wall (or gate) near x, y below ground that is still shut, or nil.
function Client.gateNear(x, y)
    for _, which in ipairs({ "wall", "gate" }) do
        local ax, ay, bx, by = S.gateSquares(which)
        if ax and (U.dist(x, y, ax, ay) <= C.ClickSlack + 0.5 or U.dist(x, y, bx, by) <= C.ClickSlack + 0.5)
                and not S.gateOpenHere(ax, ay, bx, by) then
            return which
        end
    end
    return nil
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
        local which = Client.gateNear(x, y)
        if which then return "pry", which end
        return nil
    end
    local sq = S.manholeNear(x, y, C.ClickSlack)
    if not sq then
        -- A hatch in a house's floor.
        local h = S.hatchNear(x, y, C.ClickSlack)
        if h and S.shaftAt(h:getX(), h:getY()) then return "hatch", h end
        return nil
    end
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
    elseif what == "hatch" then
        local opt = context:addOption(getText("ContextMenu_SEW_HatchDown"), playerObj, Client.climbDown, where)
        local tip = ISWorldObjectContextMenu.addToolTip()
        tip.description = getText("Tooltip_SEW_Hatch")
        opt.toolTip = tip
    elseif what == "shut" then
        local opt = context:addOption(getText("ContextMenu_SEW_Enter"), nil, nil)
        opt.notAvailable = true
        local tip = ISWorldObjectContextMenu.addToolTip()
        tip.description = getText("Tooltip_SEW_Shut")
        opt.toolTip = tip
    elseif what == "pry" then
        local opt = context:addOption(getText(where == "gate" and "ContextMenu_SEW_PryGate" or "ContextMenu_SEW_PryWall"),
                                      playerObj, Client.pry, where)
        local tip = ISWorldObjectContextMenu.addToolTip()
        tip.description = getText(where == "gate" and "Tooltip_SEW_PryGate" or "Tooltip_SEW_PryWall")
        opt.toolTip = tip
    elseif what == "up" then
        local opt = context:addOption(getText(where.hatch and "ContextMenu_SEW_HatchUp" or "ContextMenu_SEW_Exit"),
                                      playerObj, Client.climbUp, where)
        if where.hatch then
            local tip = ISWorldObjectContextMenu.addToolTip()
            tip.description = getText("Tooltip_SEW_HatchUp")
            opt.toolTip = tip
        elseif where.street and where.street ~= "" then
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
    pending = { x = args.x, y = args.y, z = args.z, street = args.street, mode = args.mode, hatch = args.hatch,
                waited = 0 }
end)

local REFUSED = { shut = "IGUI_SEW_Shut", reach = "IGUI_SEW_Reach", level = "IGUI_SEW_Level",
                  unready = "IGUI_SEW_Unready", rous = "IGUI_SEW_RousAlive", open = "IGUI_SEW_Refused" }
Net.onClient("refused", function(args)
    local p = getPlayer()
    U.note(p, getText(REFUSED[args.why] or "IGUI_SEW_Refused"), 220, 170, 120)
end)

-- The nest (SEW_Nest): a wall opened, or the last of them dead.
local NEST = { wall = "IGUI_SEW_NestWall", gate = "IGUI_SEW_NestGate", cleared = "IGUI_SEW_NestCleared",
               bite = "IGUI_SEW_RousBite" }
Net.onClient("nest", function(args)
    local key = NEST[args.what]
    local p = getPlayer()
    if args.what == "bite" then
        U.try("biteSound", function() p:playSound("AnimalVoiceRatStressed") end)
        U.note(p, getText(key), 230, 90, 80)
    elseif key then
        U.note(p, getText(key), 210, 190, 150)
    end
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
        U.try("sound", function() p:playSound(m.hatch and "SEW_Ladder" or "SEW_Lid") end)
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
        -- No daylight through a trapdoor in somebody's floor.
        if not s.hatch and math.abs(s.x - px) <= r and math.abs(s.y - py) <= r then lamp(s.x, s.y, shaftLight) end
    end
    for _, h in ipairs(SEW.Index.shelters) do
        local cx, cy = h.x + math.floor(h.w / 2), h.y + math.floor(h.h / 2)
        if math.abs(cx - px) <= r and math.abs(cy - py) <= r then lamp(cx, cy, C.ShelterLight) end
    end
    for _, v in ipairs(SEW.Index.caves or {}) do
        if math.abs(v.x - px) <= r and math.abs(v.y - py) <= r then lamp(v.x, v.y, C.CaveLight) end
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
--- The dev build's start: a new character is put on the street at the cover
--- nearest a cave's breach (C.DevStartTown), a climb and a short walk from
--- it. The street, not the tunnel: below, the floor would not exist yet
--- until the server built it round somebody standing there.
function Client.devCave()
    local best, bd = nil, nil
    for _, v in ipairs(SEW.Index and SEW.Index.caves or {}) do
        if v.town == C.DevStartTown then
            local d = math.abs(v.bx - v.sx) + math.abs(v.by - v.sy)
            if not bd or d < bd then best, bd = v, d end
        end
    end
    return best
end

--- The dev build's start by the nest: the hatch nearest it (the generator
--- picked it by walking the tunnels), or nil in a build with no nest.
function Client.devLairHatch()
    local L = SEW.Index and SEW.Index.lair
    if not L then return nil end
    return S.shaftAt(L.hx, L.hy)
end

local devStartAt = nil       -- the tick a new dev character is moved, once
function Client.devStart(p, now)
    if not SEW.Dev or isClient() or not p then devStartAt = nil return false end
    local md = U.try("devStart.md", function() return p:getModData() end)
    if not md or md.SEWDevStart then devStartAt = nil return false end
    if not devStartAt then devStartAt = now + 30 return false end
    if now < devStartAt then return false end
    devStartAt = nil
    md.SEWDevStart = true
    -- By the rats' nest: on the floor beside the hatch in the house nearest
    -- it. The house is looked at when a player on the street comes near, and
    -- the trapdoor goes into its floor if nothing is under it (SEW_Build.hatch).
    local h = C.DevStart == "lair" and Client.devLairHatch()
    if h then
        U.teleport(p, h.x, h.y, 0)
        U.log("dev build: started by the hatch %d,%d (%s); the nest's false wall is at %d,%d below",
              h.x, h.y, tostring(h.hatch), SEW.Index.lair.tx, SEW.Index.lair.ty)
        U.note(p, getText("IGUI_SEW_DevLair"), 200, 190, 150)
        return true
    end
    local v = Client.devCave()
    if not v then
        U.log("WARN dev build: no cave in %s to start at", tostring(C.DevStartTown))
        return false
    end
    U.teleport(p, v.sx, v.sy, 0)
    U.log("dev build: started at the cover %d,%d; the cave's breach is at %d,%d below", v.sx, v.sy, v.bx, v.by)
    U.note(p, getText("IGUI_SEW_DevCave"), 200, 190, 150)
    return true
end

--- Only a character that has just been made: one that has lived an hour is
--- somebody's game, and is left where it stands.
local function isNew(p)
    local h = U.try("hours", function() return p:getHoursSurvived() end)
    return h ~= nil and h < 0.5
end

local devStartPlayer = nil
Events.OnCreatePlayer.Add(function(_, p)
    U.try("devKit", Client.devKit, p)
    -- The dev flag and single player are devStart's to check, once, not here too.
    if isNew(p) then devStartPlayer = p end
end)

--- Debug console: the caves of a town, and a hop to the street over one.
function SEW_Caves(town)
    for i, v in ipairs(SEW.Index.caves or {}) do
        if not town or v.town == town then
            U.log("cave %d (%s): breach %d,%d, hideout %d,%d, cover %d,%d", i, v.town, v.bx, v.by, v.x, v.y, v.sx, v.sy)
        end
    end
end

--- Debug console: onto the floor beside the n-th hatch of a town (default Muldraugh's first).
function SEW_GoHatch(i, town)
    local list = {}
    for _, s in pairs(SEW.Index.shafts) do
        if s.hatch and s.town == (town or C.DevStartTown) then list[#list + 1] = s end
    end
    table.sort(list, function(a, b) return a.x < b.x or (a.x == b.x and a.y < b.y) end)
    local s, p = list[i or 1], getPlayer()
    if not s or not p or isClient() then return end
    U.teleport(p, s.x, s.y, 0)
    U.log("SEW_GoHatch: at the hatch %d,%d (%s, %s); it opens once the house is looked at", s.x, s.y, s.town, s.hatch)
end

--- Debug console: into the house by the hatch nearest the rats' nest.
function SEW_GoLair()
    local h, p = Client.devLairHatch(), getPlayer()
    if not h or not p or isClient() then return end
    U.teleport(p, h.x, h.y, 0)
    U.log("SEW_GoLair: at the hatch %d,%d; down it, the false wall is at %d,%d", h.x, h.y,
          SEW.Index.lair.tx, SEW.Index.lair.ty)
end

function SEW_GoCave(i)
    local v = (SEW.Index.caves or {})[i or 1]
    local p = getPlayer()
    if not v or not p or isClient() then return end
    U.teleport(p, v.sx, v.sy, 0)
    U.log("SEW_GoCave: on the cover %d,%d over cave %d (%s)", v.sx, v.sy, i or 1, v.town)
end

local tick = 0
Events.OnTick.Add(function()
    tick = tick + 1
    local p = getPlayer()
    if not p then return end
    if pending then U.try("arrive", Client.arrive, p) end
    if devStartPlayer then
        if devStartPlayer == p then U.try("devStart", Client.devStart, p, tick) end
        -- Done once no start is waiting for its tick: moved, or refused.
        if devStartPlayer ~= p or not devStartAt then devStartPlayer = nil end
    end
    if tick % 10 == 0 then
        U.try("vault", Client.vault, p)
        U.try("floor", Client.checkFloor, p, tick)
    end
    if tick % 90 == 0 then U.try("light", Client.light, p) end
    if tick % 30 == 0 then U.try("ambience", Client.ambience, p, tick) end
end)

return Client
