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
--- Gets the player to where a climb can start: nowhere, when they stand
--- within reach already (of x, y, or of x2, y2 -- a ladder's own square),
--- else a walk to beside `sq`. **The walk is not needed by somebody standing
--- at the ladder, and it must not be what stops them**: it is vanilla's
--- path finder, which is told nothing of squares raised below the street
--- at runtime, and a walk that fails takes the climb with it, silently. A
--- player was trapped below on a server (0.7.4; DEV_GUIDE, *A climb is
--- asked for until it is answered*). False, with a word why, when there is
--- no way to it.
function Client.approach(playerObj, sq, x, y, x2, y2)
    if S.within(playerObj, x, y, C.Reach) or (x2 ~= nil and S.within(playerObj, x2, y2, C.Reach)) then
        ISTimedActionQueue.clear(playerObj)
        return true
    end
    if sq and luautils.walkAdj(playerObj, sq, false) then return true end
    U.log("no way found to the climb at %d,%d from %.1f,%.1f", x, y, playerObj:getX(), playerObj:getY())
    U.note(playerObj, getText("IGUI_SEW_Closer"), 220, 170, 120)
    return false
end

function Client.climbDown(playerObj, sq)
    if not Client.approach(playerObj, sq, sq:getX(), sq:getY()) then return end
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
    if not Client.approach(playerObj, sq, shaft.x, shaft.y, shaft.lx, shaft.ly) then return end
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
    local shaft = S.shaftAt(sq:getX(), sq:getY())
    if shaft and shaft.outfall then return "outfall", sq end
    if shaft then return "down", sq end
    return "shut", sq
end

---------------------------------------------------------------------------
-- Digging
---------------------------------------------------------------------------
Client.DIRS = { { "N", 0, -1 }, { "E", 1, 0 }, { "S", 0, 1 }, { "W", -1, 0 } }

--- True when a ladder of ours hangs on that edge of the square that holds it
--- (as an object, or attached to its wall): the wall behind a ladder stays.
local function ladderOn(holder, north)
    local name = north and C.Sprites.ladder.N or C.Sprites.ladder.W
    if not holder then return false end
    if U.findSprite(holder, name) then return true end
    local spr, found = getSprite(name), false
    U.eachObject(holder, function(o)
        if U.try("isAttached", function() return o:isAttachedAnimSprite(spr) end) == true then
            found = true
            return false
        end
    end)
    return found
end

--- What can be dug from where the player stands, each way: { dir, dx, dy,
--- kind } with kind "dig" (rock there) or "break" (a wall, and a space behind
--- it). What this machine can see for itself; the server decides (SEW_Mine).
function Client.mineOffers(p)
    local out = {}
    if not S.below(p) then return out end
    if SandboxVars and SandboxVars.Sewars and tonumber(SandboxVars.Sewars.Digging) == 1 then return out end
    local x, y = math.floor(p:getX()), math.floor(p:getY())
    local here = U.square(x, y, C.Z, false)
    if not here or not U.floorOf(here) then return out end
    for _, d in ipairs(Client.DIRS) do
        local sq = U.square(x + d[2], y + d[3], C.Z, false)
        local floor = sq and U.floorOf(sq)
        -- The edge is held by the southern or eastern of the two squares.
        local edgeHolder, edgeNorth = (d[2] + d[3] > 0) and sq or here, d[2] == 0
        if ladderOn(edgeHolder, edgeNorth) then
            -- Nothing to offer: the ladder's wall is the way out.
        elseif not floor or U.spriteName(floor) == C.Sprites.floorRock then
            out[#out + 1] = { dir = d[1], dx = d[2], dy = d[3], kind = "dig" }
        elseif U.try("blocked", function() return here:isBlockedTo(sq) end) == true then
            -- Not a door: that opens. (The edge is held by the southern or eastern square.)
            local holder, north = (d[2] + d[3] > 0) and sq or here, d[2] == 0
            local door = false
            U.eachObject(holder, function(o)
                if instanceof(o, "IsoDoor") and U.try("door.north", function() return o:getNorth() end) == north then
                    door = true
                    return false
                end
            end)
            if not door then out[#out + 1] = { dir = d[1], dx = d[2], dy = d[3], kind = "break" } end
        end
    end
    return out
end

function Client.mine(playerObj, dx, dy)
    ISTimedActionQueue.add(SEWMine:new(playerObj, math.floor(playerObj:getX()), math.floor(playerObj:getY()), dx, dy))
end

--- The Dig submenu: one entry for each way that can be dug, greyed with the
--- reason when there is nothing to dig with.
function Client.mineMenu(playerObj, context)
    local offers = Client.mineOffers(playerObj)
    if #offers == 0 then return false end
    local top = context:addOption(getText("ContextMenu_SEW_Mine"), nil, nil)
    local tool = S.mineTool(playerObj)
    if not tool then
        top.notAvailable = true
        local tip = ISWorldObjectContextMenu.addToolTip()
        tip.description = getText("Tooltip_SEW_MineNoTool")
        top.toolTip = tip
        return true
    end
    local sub = context:getNew(context)
    context:addSubMenu(top, sub)
    for _, o in ipairs(offers) do
        local opt = sub:addOption(getText("ContextMenu_SEW_" .. (o.kind == "dig" and "Dig_" or "Break_") .. o.dir),
                                  playerObj, Client.mine, o.dx, o.dy)
        local tip = ISWorldObjectContextMenu.addToolTip()
        tip.description = getText(tool == "pick" and "Tooltip_SEW_MinePick" or "Tooltip_SEW_MineHammer")
        opt.toolTip = tip
    end
    return true
end

---------------------------------------------------------------------------
-- The dev build's menu
---------------------------------------------------------------------------
-- The author tests by playing and never types in the debug console, so
-- everything a test needs is on the right-click menu in the dev build: a
-- "Sewers (dev)" submenu, only when SEW.Dev is set (the installed SewarsDev
-- copy) and only in single player, where this process is also the server.
-- Each stop goes round the dev town's list (C.DevStartTown) in turn.
Client.devNext = { gas = 0, gate = 0, breach = 0 }

--- The places of one kind in the dev town, in a fixed order: "gas" (index
--- in SEW.Index.gas) or "gate" (index in SEW.Index.gates).
function Client.devList(kind)
    local out = {}
    local list = kind == "gas" and SEW.Index.gas or SEW.Index.gates
    for i, g in ipairs(list or {}) do
        if g.town == C.DevStartTown then out[#out + 1] = i end
    end
    return out
end

-- A dev trip below: { x, y, note, waited }. Never straight down onto a
-- square far away: its chunk is not loaded yet, so its tunnel is not built,
-- the player stands on nothing and the rescue sends them to the nearest
-- ladder (found in play: "it keeps teleporting me away from the gas"). So
-- the player is put on the street above first, the chunk streams in round
-- them, the tunnel is built there, and only then do they go down -- the
-- climb's own order (DEV_GUIDE, "Never build where no player is standing").
Client.devTravel = nil

--- The square below ground a dev stop takes you to: the middle of a stretch
--- of gas, or the tunnel side of a locked gate.
function Client.devTarget(what, i)
    if what == "gas" then
        local g = SEW.Index.gas[i]
        return g.x, g.y
    end
    local g = SEW.Index.gates[i]
    local ox, oy = g.x, g.y
    if g.edge == "N" then oy = g.y - 1 else ox = g.x - 1 end
    if S.shelterAt(ox, oy) then return g.x, g.y end
    return ox, oy
end

--- Each tick of a dev trip: build round the spot once its chunk is here, and
--- step down onto the floor once it exists.
function Client.devArrive(p)
    local t = Client.devTravel
    if not t then return end
    t.waited = t.waited + 1
    if U.chunkLoaded(t.x, t.y) and SEW.Build then SEW.Build.around(t.x, t.y, 1) end
    local sq = U.square(t.x, t.y, C.Z, false)
    if sq and U.floorOf(sq) then
        Client.devTravel = nil
        U.teleport(p, t.x, t.y, C.Z)
        Client.vault(p)
        U.note(p, t.note, 200, 190, 150)
    elseif t.waited > C.ArriveTimeout then
        Client.devTravel = nil
        U.log("WARN dev build: the tunnel at %d,%d was never built; staying on the street", t.x, t.y)
    end
end

--- One dev stop: "gas", "gate", "key", "outfall", "poison", "temple" (the
--- passage short of the temple's south gate), "breach" (where the cult broke
--- into a sewer, each in turn), "trapdoor" (the field over the temple's
--- postern), "nest" (the false wall under Louisville), "warren" (its first
--- den), "cave" (the cover over a cave) or "hatch" (the house by the nest).
--- Nobody is moved without choosing one: a new character stays where the
--- game put it.
function Client.devGo(p, what)
    if not SEW.Dev or isClient() then return false end
    local T = SEW.Index.temple
    if what == "temple" or what == "breach" then
        if not T then return false end
        local x, y, note = T.hx, T.hy, getText("IGUI_SEW_DevAtTemple")
        if what == "breach" then
            Client.devNext.breach = Client.devNext.breach % #T.breaches + 1
            local b = T.breaches[Client.devNext.breach]
            x, y, note = b.tx, b.ty, getText("IGUI_SEW_DevAtBreach", b.n)
        end
        Client.devTravel = { x = x, y = y, waited = 0, note = note }
        U.teleport(p, x, y, 0)
        Client.vault(p)
        return true
    elseif what == "nest" or what == "warren" then
        -- The tunnel side of the nest's false wall; or its first den, past the
        -- rodents (who will come: that is the test).
        local L, Wn = SEW.Index.lair, SEW.Index.warren
        if not L or not Wn then return false end
        local x, y, note = L.tx, L.ty, getText("IGUI_SEW_DevAtNest")
        if what == "warren" then x, y, note = Wn.dens[1], Wn.dens[2], getText("IGUI_SEW_DevAtWarren", #Wn.dens / 3) end
        Client.devTravel = { x = x, y = y, waited = 0, note = note }
        U.teleport(p, x, y, 0)
        Client.vault(p)
        return true
    elseif what == "dig" then
        -- A pick and three pipe bombs, to dig and to blast with.
        local inv, n = p:getInventory(), 0
        for _, id in ipairs({ C.Mine.pick[1], "Base.PipeBomb", "Base.PipeBomb", "Base.PipeBomb" }) do
            if U.addItem(inv, id) then n = n + 1 end
        end
        U.note(p, getText("IGUI_SEW_DevDig", n), 200, 190, 150)
        return n > 0
    elseif what == "gun" then
        -- A pistol, a magazine and a box of rounds: for shooting the ROUS (0.7.5).
        local inv, n = p:getInventory(), 0
        for _, id in ipairs(C.DevKitGun) do
            if U.addItem(inv, id) then n = n + 1 end
        end
        U.note(p, getText("IGUI_SEW_DevGun", n), 200, 190, 150)
        return n > 0
    elseif what == "fire" then
        -- The street over a tunnel set alight, a few squares from the player:
        -- for the fire that must not come down (SEW_Fire). The tunnel under it
        -- is built first, as a climb would build it. Vanilla's own call
        -- (SCampfireSystem: IsoFireManager.StartFire).
        if S.below(p) then return false end
        local px, py, n = math.floor(p:getX()), math.floor(p:getY()), 0
        if SEW.Build then SEW.Build.around(px, py, 1) end
        for dx = -6, 6 do
            for dy = -6, 6 do
                local top = U.square(px + dx, py + dy, 0, false)
                local under = U.square(px + dx, py + dy, C.Z, false)
                if n < 6 and math.abs(dx) + math.abs(dy) >= 3 and top and U.floorOf(top) and under and S.ours(under) then
                    if U.try("dev.fire", function()
                        IsoFireManager.StartFire(getCell(), top, true, 100, 500)
                        return true
                    end) then n = n + 1 end
                end
            end
        end
        U.note(p, getText("IGUI_SEW_DevFire", n), 200, 190, 150)
        return n > 0
    elseif what == "snow" then
        -- Snow on the ground, held there (Client.devWeather): for the snow that
        -- must not lie in the tunnels (SEW_Weather). Again: off.
        Client.devSnow = not Client.devSnow
        U.note(p, getText(Client.devSnow and "IGUI_SEW_DevSnowOn" or "IGUI_SEW_DevSnowOff"), 200, 190, 150)
        return true
    elseif what == "wind" then
        -- A freezing gale, held (Client.devGale): for the wind that must
        -- not reach the tunnels (SEW_Wind). Again: off.
        Client.devWind = not Client.devWind
        Client.devGale(Client.devWind)
        U.note(p, getText(Client.devWind and "IGUI_SEW_DevWindOn" or "IGUI_SEW_DevWindOff"), 200, 190, 150)
        return true
    elseif what == "maps" then
        -- Both annotated maps, in hand: read them from the inventory.
        if not SEW.Maps then return false end
        local inv, n = p:getInventory(), 0
        for _, which in ipairs(SEW.Maps.WHICH) do
            local item = SEW.Maps.make(which)
            if item then inv:AddItem(item); n = n + 1 end
        end
        U.note(p, getText("IGUI_SEW_DevMaps", n), 200, 190, 150)
        return n > 0
    elseif what == "trapdoor" then
        if not T then return false end
        U.teleport(p, T.tx, T.ty + 1, 0)
        Client.vault(p)
        U.note(p, getText("IGUI_SEW_DevTemple"), 200, 190, 150)
        return true
    end
    if what == "gas" or what == "gate" then
        local list = Client.devList(what)
        if #list == 0 then return false end
        Client.devNext[what] = Client.devNext[what] % #list + 1
        local x, y = Client.devTarget(what, list[Client.devNext[what]])
        Client.devTravel = { x = x, y = y, waited = 0,
                             note = getText(what == "gas" and "IGUI_SEW_DevAtGas" or "IGUI_SEW_DevAtGate",
                                            Client.devNext[what], #list) }
        U.teleport(p, x, y, 0)
        Client.vault(p)
        return true
    elseif what == "key" then
        SEW_Key(C.DevStartTown)
        U.note(p, getText("IGUI_SEW_DevKey"), 200, 190, 150)
        return true
    elseif what == "outfall" then
        -- On the bank: the grate goes into it within a few seconds (SEW_Build.cover).
        local o = Client.devOutfall()
        if not o then return false end
        U.teleport(p, o.x, o.y, 0)
        Client.vault(p)
        U.note(p, getText("IGUI_SEW_DevOutfall"), 200, 190, 150)
        return true
    elseif what == "cave" then
        -- The street, not the tunnel: the cover is a climb and a short walk
        -- from the cave's breach.
        local v = Client.devCave()
        if not v then return false end
        U.teleport(p, v.sx, v.sy, 0)
        Client.vault(p)
        U.note(p, getText("IGUI_SEW_DevCave"), 200, 190, 150)
        return true
    elseif what == "hatch" then
        -- The floor beside the hatch in the house nearest the nest. The house
        -- is looked at when a player on the street comes near, and the trapdoor
        -- goes into its floor if nothing is under it (SEW_Build.hatch).
        local h = Client.devLairHatch()
        if not h then return false end
        U.teleport(p, h.x, h.y, 0)
        Client.vault(p)
        U.note(p, getText("IGUI_SEW_DevLair"), 200, 190, 150)
        return true
    elseif what == "poison" then
        local v = U.try("poison", function() return p:getStats():get(CharacterStat.POISON) end) or 0
        U.note(p, getText("IGUI_SEW_DevPoison", string.format("%.0f", v)), 200, 190, 150)
        return true
    end
    return false
end

--- The dev build's snow: the cell's snow target held at full while it is
--- switched on (the climate sets it back otherwise). IsoCell.setSnowTarget
--- is what FBORenderSnow.RenderSnow reads; nothing in vanilla Lua calls it,
--- and nothing outside the dev build calls it here.
function Client.devWeather()
    if not Client.devSnow or not SEW.Dev or isClient() then return false end
    return U.try("dev.snow", function()
        getCell():setSnowTarget(100)
        return true
    end) == true
end

--- The dev build's gale: the climate's temperature and wind held by its
--- admin values (ISAdmPanelClimate's sliders: getClimateFloat, setEnableAdmin,
--- setAdminValue), -10 C and a full wind. An admin panel's calls, so the dev
--- build's alone, in single player.
function Client.devGale(on)
    if not SEW.Dev or isClient() then return false end
    return U.try("dev.wind", function()
        local clim = getClimateManager()
        for id, v in pairs({ [4] = -10, [6] = 1 }) do
            local f = clim:getClimateFloat(id)
            f:setEnableAdmin(on)
            if on then f:setAdminValue(v) end
        end
        return true
    end) == true
end

function Client.devMenu(playerObj, context)
    local top = context:addOption(getText("ContextMenu_SEW_Dev"), nil, nil)
    local sub = context:getNew(context)
    context:addSubMenu(top, sub)
    for _, what in ipairs({ "dig", "gun", "fire", "snow", "wind", "maps", "temple", "breach", "trapdoor", "nest", "warren",
                            "hatch", "cave", "outfall", "gas", "poison", "gate", "key" }) do
        sub:addOption(getText("ContextMenu_SEW_Dev_" .. what), playerObj, Client.devGo, what)
    end
end

function Client.fillMenu(playerIndex, context, worldobjects, test)
    local playerObj = getSpecificPlayer(playerIndex)
    if not playerObj or playerObj:getVehicle() then return end
    if SEW.Dev and not isClient() and not test then U.try("devMenu", Client.devMenu, playerObj, context) end
    -- The map, anywhere below ground. Here and nowhere else: it has no key (0.7.6).
    if S.below(playerObj) and SEW.Map and not test then
        context:addOption(getText("ContextMenu_SEW_Map"), playerObj, SEW.Map.toggle)
    end
    -- Digging, from wherever the player stands below.
    if S.below(playerObj) and not test then U.try("mineMenu", Client.mineMenu, playerObj, context) end
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
    elseif what == "outfall" then
        local opt = context:addOption(getText("ContextMenu_SEW_OutfallDown"), playerObj, Client.climbDown, where)
        local tip = ISWorldObjectContextMenu.addToolTip()
        tip.description = getText("Tooltip_SEW_Outfall")
        opt.toolTip = tip
    elseif what == "hatch" then
        local opt = context:addOption(getText("ContextMenu_SEW_HatchDown"), playerObj, Client.climbDown, where)
        local tip = ISWorldObjectContextMenu.addToolTip()
        -- In a house's floor, or (the temple's) under the weeds of a field.
        local shaft = S.shaftAt(where:getX(), where:getY())
        tip.description = getText((shaft and shaft.trapdoor) and "Tooltip_SEW_Trap" or "Tooltip_SEW_Hatch")
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
        local label = (where.hatch or where.trapdoor) and "ContextMenu_SEW_HatchUp"
            or where.outfall and "ContextMenu_SEW_OutfallUp" or "ContextMenu_SEW_Exit"
        local opt = context:addOption(getText(label), playerObj, Client.climbUp, where)
        if where.outfall then
            local tip = ISWorldObjectContextMenu.addToolTip()
            tip.description = getText("Tooltip_SEW_OutfallUp")
            opt.toolTip = tip
        elseif where.hatch or where.trapdoor then
            local tip = ISWorldObjectContextMenu.addToolTip()
            tip.description = getText(where.trapdoor and "Tooltip_SEW_TrapUp" or "Tooltip_SEW_HatchUp")
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

-- A climb this client has finished and the server has not answered yet:
-- { x, y, mode, waited, asked }. On a server the grant is the server's half
-- of the action (SEWClimb:complete), and a player was trapped below on one
-- (0.7.4) with nothing to say which step had failed. So silence is not left
-- to stand (DEV_GUIDE, *Never let a failure strand the player*): after
-- C.ClimbAskAgain ticks the client asks again by command, which needs no
-- timed action; and if that is not answered either, a climb *out* is made
-- anyway -- up a ladder the player is standing at, onto a street square this
-- machine has. It is their own character, and the street needs no building.
-- A refusal is an answer, and is obeyed.
local awaited = nil
-- The last answer: { x, y, mode, at } of a `go`, and the tick of a refusal.
-- The server's half of the action ends first, so its answer is often here
-- before this client's half ends: that climb is answered, not awaited.
local answered, refusedAt = nil, -1e9
Client.now = 0

--- The action has ended on this client (SEWClimb:perform).
function Client.expect(x, y, mode)
    if not isClient() then return false end
    local g = answered
    if g and g.x == x and g.y == y and g.mode == mode and Client.now - g.at < 120 then return false end
    if Client.now - refusedAt < 30 then return false end
    awaited = { x = x, y = y, mode = mode, waited = 0, asked = false }
    return true
end

Net.onClient("go", function(args)
    awaited = nil
    answered = { x = args.x, y = args.y, mode = args.mode, at = Client.now }
    pending = { x = args.x, y = args.y, z = args.z, street = args.street, mode = args.mode, hatch = args.hatch,
                outfall = args.outfall, waited = 0 }
end)

local REFUSED = { shut = "IGUI_SEW_Shut", reach = "IGUI_SEW_Reach", level = "IGUI_SEW_Level",
                  unready = "IGUI_SEW_Unready", rous = "IGUI_SEW_RousAlive", open = "IGUI_SEW_Refused",
                  solid = "IGUI_SEW_MineSolid", foreign = "IGUI_SEW_MineForeign", tool = "IGUI_SEW_MineTool",
                  off = "IGUI_SEW_MineOff" }
Net.onClient("refused", function(args)
    awaited = nil
    refusedAt = Client.now
    local p = getPlayer()
    -- In the log with where the server has this player, for the next report.
    U.log("refused: %s (the server has you at %s)", tostring(args.why), tostring(args.at or "?"))
    U.note(p, getText(REFUSED[args.why] or "IGUI_SEW_Refused"), 220, 170, 120)
end)

--- Every tick while a climb is unanswered.
function Client.unanswered(p)
    local a = awaited
    if not a then return end
    a.waited = a.waited + 1
    if not a.asked and a.waited >= C.ClimbAskAgain then
        a.asked = true
        U.log("WARN the server has not answered the climb %s at %d,%d; asking again by command", a.mode, a.x, a.y)
        Net.send(p, "climb", { x = a.x, y = a.y, mode = a.mode })
    elseif a.asked and a.waited >= C.ClimbAskAgain + C.ClimbGiveUp then
        awaited = nil
        local s = S.shaftAt(a.x, a.y)
        if a.mode == "up" and s and S.below(p)
                and (S.within(p, s.x, s.y, C.Reach + 0.8) or S.within(p, s.lx, s.ly, C.Reach + 0.8)) then
            U.log("WARN the server never answered the climb out at %d,%d; climbing out anyway", a.x, a.y)
            pending = { x = a.x, y = a.y, z = 0, street = s.street or "", mode = "up",
                        hatch = s.hatch ~= nil or s.trapdoor == true, outfall = s.outfall == true, waited = 0 }
        else
            U.log("WARN the server never answered the climb %s at %d,%d", a.mode, a.x, a.y)
            U.note(p, getText("IGUI_SEW_Unready"), 220, 170, 120)
        end
    end
end

-- The nest (SEW_Nest): a wall opened, the last of them dead, a bite, and
-- one of them killed. A hit and a shove say nothing: the fight is the notice.
local NEST = { wall = "IGUI_SEW_NestWall", gate = "IGUI_SEW_NestGate", cleared = "IGUI_SEW_NestCleared",
               bite = "IGUI_SEW_RousBite", kill = "IGUI_SEW_RousKill" }
Net.onClient("nest", function(args)
    local key = NEST[args.what]
    local p = getPlayer()
    if args.what == "bite" then
        U.try("biteSound", function() p:playSound("AnimalVoiceRatStressed") end)
        U.note(p, getText(key), 230, 90, 80)
    elseif args.what == "kill" then
        U.try("killSound", function() p:playSound("AnimalVoiceRatStressed") end)
        U.note(p, getText(key), 210, 190, 150)
    elseif key then
        U.note(p, getText(key), 210, 190, 150)
    end
end)

--- A swing or a shot near the nest, on a client: the server judges it, from
--- where it has the rodents (SEW_Nest.swing). In single player the server's
--- half hears the engine's event itself.
function Client.swung(character)
    if not isClient() or character ~= getPlayer() or not S.below(character) then return false end
    local L = SEW.Index and SEW.Index.lair
    if not L or U.dist(character:getX(), character:getY(), L.x, L.y) > C.Rous.range + C.Rous.hunt then return false end
    local dir = U.try("swing.facing", function() return character:getForwardDirection() end)
    return Net.send(character, "swing", { fx = dir and dir:getX() or nil, fy = dir and dir:getY() or nil })
end
Events.OnWeaponSwingHitPoint.Add(function(character) U.try("swung", Client.swung, character) end)

-- Digging (SEW_Mine): a square dug out, a wall down, a blast near by.
local MINED = { dig = "IGUI_SEW_MineDug", ["break"] = "IGUI_SEW_MineBroke", blast = "IGUI_SEW_MineBlast" }
Net.onClient("mined", function(args)
    local p = getPlayer()
    if MINED[args.what] then U.note(p, getText(MINED[args.what]), 200, 190, 150) end
end)

-- Sewer gas (SEW_Gas): walked into a stretch, with or without a mask on.
Net.onClient("gas", function(args)
    local p = getPlayer()
    if not p then return end
    local female = U.try("female", function() return p:isFemale() end) == true
    if args.protected then
        U.try("gasSound", function() p:playSound(female and "VoiceFemaleMuffledCough" or "VoiceMaleMuffledCough") end)
        U.note(p, getText("IGUI_SEW_GasMask"), 180, 200, 120)
    else
        U.try("gasSound", function() p:playSound(female and "VoiceFemaleCough" or "VoiceMaleCough") end)
        U.note(p, getText("IGUI_SEW_GasIn"), 200, 210, 90)
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
        if m.outfall then
            U.note(p, getText("IGUI_SEW_DownOutfall"), 190, 200, 170)
        elseif m.street and m.street ~= "" then
            U.note(p, getText("IGUI_SEW_DownUnder", m.street), 190, 200, 170)
        else
            U.note(p, getText("IGUI_SEW_Down"), 190, 200, 170)
        end
    elseif m.mode == "up" then
        U.try("sound", function() p:playSound((m.hatch or m.outfall) and "SEW_Ladder" or "SEW_Lid") end)
        if m.outfall then
            U.note(p, getText("IGUI_SEW_UpOutfall"), 200, 200, 170)
        elseif m.street and m.street ~= "" then
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
    -- Somebody else's underground: a stair with no floor under it, or one
    -- going on down from this level (the square is then the one below).
    -- Found by players: a bunker's stairs sent them to a ladder a town away.
    if sq and (U.try("sq.z", function() return sq:getZ() end) ~= C.Z or U.foreign(sq)) then return end
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
        -- No daylight through a trapdoor, in somebody's floor or in a field.
        if not s.hatch and not s.trapdoor and math.abs(s.x - px) <= r and math.abs(s.y - py) <= r then
            lamp(s.x, s.y, shaftLight)
        end
    end
    for _, h in ipairs(SEW.Index.shelters) do
        local cx, cy = h.x + math.floor(h.w / 2), h.y + math.floor(h.h / 2)
        if math.abs(cx - px) <= r and math.abs(cy - py) <= r then lamp(cx, cy, C.ShelterLight) end
    end
    for _, v in ipairs(SEW.Index.caves or {}) do
        if math.abs(v.x - px) <= r and math.abs(v.y - py) <= r then lamp(v.x, v.y, C.CaveLight) end
    end
    -- The temple's sconces, braziers and candles, and the candles down its passages.
    -- The candles the cult's pilgrims left burning in the warren.
    local Wn = SEW.Index.warren
    if Wn then
        for i = 1, #Wn.lights, 2 do
            local lx, ly = Wn.lights[i], Wn.lights[i + 1]
            if math.abs(lx - px) <= r and math.abs(ly - py) <= r then lamp(lx, ly, C.CaveLight) end
        end
    end
    -- Nearer than the rest: there are sixty of them, and the hall alone has twenty.
    local T = SEW.Index.temple
    if T and math.abs(T.x - px) <= 600 and math.abs(T.y - py) <= 600 then
        r = C.TempleLightRange
        for i = 1, #T.lights, 2 do
            local lx, ly = T.lights[i], T.lights[i + 1]
            if math.abs(lx - px) <= r and math.abs(ly - py) <= r then lamp(lx, ly, C.TempleLight) end
        end
    end
end

-- The sewer's own sounds are the player's to switch on (0.7.6: the Workshop
-- found them too much). A tick box in Options -> Mods, Build 42's own mod
-- options, off until ticked; a sound is this machine's and nobody else's, so
-- it is no sandbox option.
Client.soundOption = nil
U.try("ambience.option", function()
    if not (PZAPI and PZAPI.ModOptions) then return end
    local opts = PZAPI.ModOptions:create("Sewars", getText("IGUI_SEW_ModName"))
    Client.soundOption = opts:addTickBox("sewerAmbience", getText("IGUI_SEW_Ambience"), false,
                                         getText("IGUI_SEW_AmbienceTip"))
    PZAPI.ModOptions:load()
end)

function Client.ambienceOn()
    local o = Client.soundOption
    return o ~= nil and U.try("ambience.value", function() return o:getValue() end) == true
end

local nextSound = 0
function Client.ambience(p, now)
    if not Client.ambienceOn() then return end
    -- In the sewer, not in a basement at its level (found by a player: drips,
    -- rats and groans in every cellar).
    if not S.inSewer(p) then return end
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
    -- 0.5: a gas mask and a spare filter, once, even for a character that
    -- had the first kit -- so the gas can be tried both ways.
    if not md.SEWDevGas then
        for _, id in ipairs(C.DevKitGas or {}) do U.addItem(inv, id) end
        md.SEWDevGas = true
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
--- The dev menu's cave: the one in C.DevStartTown whose breach is nearest
--- its cover, a climb and a short walk from it.
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

--- The dev menu's outfall: the first of C.DevStartTown's, by position, or nil.
function Client.devOutfall()
    local best = nil
    for _, s in pairs(SEW.Index and SEW.Index.shafts or {}) do
        if s.outfall and s.town == C.DevStartTown and (not best or s.x < best.x or (s.x == best.x and s.y < best.y)) then
            best = s
        end
    end
    return best
end

--- The dev menu's hatch by the nest: the one nearest it (the generator
--- picked it by walking the tunnels), or nil in a build with no nest.
function Client.devLairHatch()
    local L = SEW.Index and SEW.Index.lair
    if not L then return nil end
    return S.shaftAt(L.hx, L.hy)
end

-- The kit, and nothing else: a new dev character stays where the game put
-- it. Every place it used to be started at is a stop on the dev menu.
Events.OnCreatePlayer.Add(function(_, p)
    U.try("devKit", Client.devKit, p)
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
    Client.now = tick
    local p = getPlayer()
    if not p then return end
    if pending then U.try("arrive", Client.arrive, p) end
    U.try("unanswered", Client.unanswered, p)
    if Client.devTravel then U.try("devArrive", Client.devArrive, p) end
    if Client.devSnow then Client.devWeather() end
    if tick % 10 == 0 then
        U.try("vault", Client.vault, p)
        U.try("floor", Client.checkFloor, p, tick)
    end
    if tick % 90 == 0 then U.try("light", Client.light, p) end
    if tick % 30 == 0 then U.try("ambience", Client.ambience, p, tick) end
end)

return Client
