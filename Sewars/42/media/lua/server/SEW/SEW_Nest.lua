--[[ Sewars -- rats in the tunnels, and the nest under Louisville.

    Runs in single player and on any server (never on a client).

    Rats. Vanilla's own B42 rats (`rat`, `ratfemale`; grey, now and then
    white), put down on a stretch of walkway the first time it is built, by
    the sandbox's density -- once, like the dead and the crates. After that
    they are the engine's: addAnimal on the server makes them, their
    constructor registers them and AnimalSynchronizationManager sends them to
    every client in range, and a chunk saves its animals whatever their level
    (AnimalPopulationManager.removeChunkFromWorld walks minLevel..maxLevel).
    That is also how the engine puts vermin into a chunk itself
    (IsoChunk.addRatsAfterLoading: new, addToWorld, randomizeAge).

    The nest (tools/gen_sewers.py dig_lair, SEW.Index.lair). One per world,
    under Louisville, and hidden: its only way in is a tunnel wall that is not
    one -- loose brickwork with a gnawed hole at its foot -- which a player
    pulls away (SEWPry, "wall"). A run through the rock, and a round nest of
    bones where the rodents of unusual size sleep (SEW_Rats.lua). They wake
    for anybody below within C.Rous.hunt squares and go for them, and bite.

    The chase and the bite are ours, not the engine's (found in play, 0.5:
    they stood and stared). An animal attacks only from the `attack` state
    of its action group, the rat's has none, and a mod cannot add an action
    group -- ActionGroup.load reads media/actiongroups through
    ZomboidFileSystem.getMediaFile, the game's own folder only. And goAttack
    alone never bites: fightAnimal needs a fightingOpponent Lua cannot set.
    So each hunted ROUS is sent after its player with the engine's own
    pathing (pathToCharacter); one that makes no headway -- the pathfinder
    may know nothing of squares raised below the street at runtime -- is
    walked by hand, a step a tick, never through a wall (isBlockedTo). Close
    enough, it stops, faces them and bites on a timer: a scratch or a cut on
    an arm or a leg, made on the server's copy of the player and sent with
    syncBodyPart, as vanilla's own health command does. At the far
    side of the nest a wall they have gnawed half through stands in front of
    a bricked-up room and its hoard, and it gives (SEWPry, "gate") only when
    not one of them is left alive -- the server looks, it does not count
    kills, so one that is still alive anywhere near keeps it shut.

    What is opened is recorded (SEW_Build state, lair.open) and the square is
    rebuilt from its record: the builder turns a gate that is open into a
    breach (SEW_Build, GATE).
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Net"
require "SEW/SEW_Sewer"
require "SEW/SEW_Build"
require "SEW/SEW_Rats"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local Net = SEW.Net
local S = SEW.Sewer
local B = SEW.Build

local N = {}
SEW.Nest = N

local function lair() return SEW.Index and SEW.Index.lair end
N.lair = lair

local function nameOf(p)
    return U.try("username", function() return p:getUsername() end) or "player"
end

--- One animal, put down on the server and handed to the world. nil when the
--- engine will not make it (no such type, no breed).
function N.addAnimal(x, y, kind, breedName)
    return U.try("addAnimal", function()
        local def = AnimalDefinitions.getDef(kind)
        local breed = def and def:getBreedByName(breedName)
        if not breed then
            U.warnOnce("breed:" .. kind .. breedName, "no animal %s of breed %s", kind, breedName)
            return nil
        end
        local a = addAnimal(getCell(), x, y, C.Z, kind, breed)
        if a then
            a:addToWorld()
            -- In the middle of its square: the constructor takes x, y as
            -- given, and a whole number is the square's north-west corner,
            -- on the wall line (found in play, 0.5: rats beyond the walls).
            N.place(a, x + 0.5, y + 0.5)
        end
        return a
    end)
end

--- Stands an animal at x, y (below ground), leaving no old position behind.
function N.place(a, x, y)
    return U.try("animal.place", function()
        a:setX(x); a:setY(y)
        a:setLastX(x); a:setLastY(y)
        a:setNextX(x); a:setNextY(y)
        return true
    end) == true
end

---------------------------------------------------------------------------
-- Rats
---------------------------------------------------------------------------
--- A chunk's rats on its first build: so many per hundred squares of its
--- walkway (`open`, {x, y} each), by the sandbox. Returns how many.
function N.rats(open, cx, cy)
    local d = C.RatDensity[B.option("Rats", 3, #C.RatDensity)]
    if not d or d <= 0 or #open == 0 then return 0 end
    local want = #open * d / 100
    local n = math.floor(want) + ((U.hash(cx, cy, 61) % 100) < (want % 1) * 100 and 1 or 0)
    local roll = U.rng(U.hash(cx, cy, 67))
    local made = 0
    for _ = 1, n do
        local p = open[roll(#open)]
        local a = N.addAnimal(p[1], p[2], C.RatTypes[roll(#C.RatTypes)], C.RatBreeds[roll(#C.RatBreeds)])
        if a then
            U.try("randomizeAge", function() a:randomizeAge() end)
            made = made + 1
        end
    end
    return made
end

---------------------------------------------------------------------------
-- The rodents of unusual size
---------------------------------------------------------------------------
--- Only an animal is asked: getAnimalType on a zombie or a player throws, and
--- under -debug every weapon hit on one dumped a stack trace (found in play,
--- 0.5: OnWeaponHitCharacter hands us whatever was hit).
local function isRous(a)
    if not instanceof(a, "IsoAnimal") then return false end
    return U.try("animalType", function() return a:getAnimalType() end) == C.Rous.type
end

--- One ROUS at x, y.
function N.spawnRous(x, y)
    if not SEW.Rats or not SEW.Rats.defined then
        U.warnOnce("rous.undefined", "the ROUS is not defined; the nest at %d,%d stays empty", x, y)
        return nil
    end
    local a = N.addAnimal(x, y, C.Rous.type, C.Rous.breed)
    if not a then return nil end
    U.try("rous.size", function() a:getData():setSizeForced(C.Rous.size) end)
    U.try("rous.name", function() a:setCustomName(getText("IGUI_SEW_Rous")) end)
    return a
end

--- The nest's rodents whose place is in chunk `key`, each once in a save.
function N.lairChunk(key)
    local L = lair()
    if not L then return 0 end
    local st = B.state().lair
    local made = 0
    for i = 1, #L.rous, 2 do
        local x, y = L.rous[i], L.rous[i + 1]
        local k = x .. "," .. y
        if not st.rous[k] and math.floor(x / 8) .. "," .. math.floor(y / 8) == key then
            if N.spawnRous(x, y) then
                st.rous[k] = true
                made = made + 1
            end
        end
    end
    if made > 0 then U.log("the nest under %s: %d rodents of unusual size put down", L.town, made) end
    return made
end

--- True once every one of the nest's rodents has been put down.
function N.allSpawned()
    local L = lair()
    if not L then return false end
    local st = B.state().lair
    for i = 1, #L.rous, 2 do
        if not st.rous[L.rous[i] .. "," .. L.rous[i + 1]] then return false end
    end
    return true
end

--- The living ROUS within r squares of x, y below ground, as the server
--- sees them. Per square, so batched: a missing method fails once.
function N.living(x, y, r)
    local out = {}
    local cell = U.cell()
    if not cell then return out end
    local call = U.batch("rous.scan")
    for sx = math.floor(x) - r, math.floor(x) + r do
        for sy = math.floor(y) - r, math.floor(y) + r do
            local list = call(function()
                local sq = cell:getGridSquare(sx, sy, C.Z)
                return sq and sq:getAnimals()
            end)
            local n = list and list:size() or 0
            for i = 0, n - 1 do
                local a = list:get(i)
                if a and isRous(a) and not U.try("rous.dead", function() return a:isDead() end) then
                    out[#out + 1] = a
                end
            end
        end
    end
    return out
end

-- animal -> { p = the player it is after, lx, ly = where it was at the
-- last check, stuck = walked by hand, bite = the tick it may bite again }.
-- This session's only: a reload finds them again on the next look.
N.hunting = {}
local hunted = 0

local LIMBS = { "Hand_L", "Hand_R", "ForeArm_L", "ForeArm_R", "LowerLeg_L", "LowerLeg_R", "Foot_L", "Foot_R" }

--- A bite: a scratch, or now and then a cut, on an arm or a leg, and some
--- health. Made on the server's copy of the player; on a server, sent as
--- vanilla's health command sends a wound (syncBodyPart).
function N.bite(a, p)
    local ok = U.try("rous.bite", function()
        local limb = LIMBS[ZombRand(#LIMBS) + 1]
        local part = p:getBodyDamage():getBodyPart(BodyPartType[limb])
        if ZombRand(3) == 0 then part:setCut(true) else part:setScratched(true, true) end
        part:AddDamage(C.Rous.bite)
        if isServer() then syncBodyPart(part, 0xFFFFFFFFFFF) end
        return true
    end)
    if ok then Net.toClient(p, "nest", { what = "bite" }) end
    return ok == true
end

--- One step of one hunter, every tick.
local function chase(a, h, tick)
    local p = h.p
    if U.try("rous.dead", function() return a:isDead() end) ~= false or not S.below(p) then return false end
    local ax, ay = a:getX(), a:getY()
    local px, py = p:getX(), p:getY()
    local d = U.dist(ax, ay, px, py)
    if d > C.Rous.hunt + 6 then return false end
    -- Close enough to bite -- and nothing between: a player behind a wall a
    -- step away was bitten through it (found by a test, 0.5).
    local walled = false
    if d <= C.Rous.reach then
        local cell = U.cell()
        local here = cell and cell:getGridSquare(math.floor(ax), math.floor(ay), C.Z)
        local there = cell and cell:getGridSquare(math.floor(px), math.floor(py), C.Z)
        walled = here ~= nil and there ~= nil and here ~= there
            and U.try("blocked", function() return here:isBlockedTo(there) end) ~= false
    end
    if d <= C.Rous.reach and not walled then
        if not h.close then
            U.try("rous.stop", function() a:stopAllMovementNow() end)
            h.close = true
        end
        U.try("rous.face", function() a:faceThisObject(p) end)
        if tick >= (h.bite or 0) then
            h.bite = tick + C.Rous.biteEvery
            N.bite(a, p)
        end
        return true
    end
    h.close = false
    if not h.stuck then
        -- The engine's own pathing, asked again now and then; if it has not
        -- brought the animal on by half a square in a while, walk it by hand.
        if tick >= (h.path or 0) then
            h.path = tick + 60
            if h.lx and U.dist(ax, ay, h.lx, h.ly) < 0.5 then
                h.stuck = true
                U.try("rous.stop", function() a:stopAllMovementNow() end)
                U.debug("a ROUS at %.1f,%.1f makes no headway on the engine's path: walked by hand", ax, ay)
            else
                h.lx, h.ly = ax, ay
                U.try("rous.path", function() a:pathToCharacter(p) end)
            end
        end
        if not h.stuck then return true end
    end
    -- By hand: straight at them, a square at a time, never through a wall.
    local step = C.Rous.speed
    local nx, ny = ax + (px - ax) / d * step, ay + (py - ay) / d * step
    local cell = U.cell()
    local here = cell and cell:getGridSquare(math.floor(ax), math.floor(ay), C.Z)
    local there = cell and cell:getGridSquare(math.floor(nx), math.floor(ny), C.Z)
    if here and there and here ~= there then
        if not U.floorOf(there) or U.try("blocked", function() return here:isBlockedTo(there) end) ~= false then
            -- Blocked: along whichever side is open.
            local alt = nil
            for _, c in ipairs({ { nx, ay }, { ax, ny } }) do
                local sq = cell:getGridSquare(math.floor(c[1]), math.floor(c[2]), C.Z)
                if sq == here or (sq and U.floorOf(sq) and U.try("blocked", function() return here:isBlockedTo(sq) end) == false) then
                    alt = c
                    break
                end
            end
            if not alt then return true end
            nx, ny = alt[1], alt[2]
        end
    elseif not there then
        return true
    end
    N.place(a, nx, ny)
    U.try("rous.face", function() a:faceThisObject(p) end)
    return true
end

--- Every tick: each hunter after its player. Every C.Rous.every ticks, a look
--- round each player below near the nest for ROUS within reach of the hunt;
--- and when the last of them near the nest is found dead, the players there
--- are told.
function N.hunt(tick)
    local L = lair()
    if not L then return end
    if tick % C.Rous.every == 0 then
        local st = B.state().lair
        for _, p in ipairs(U.players()) do
            if S.below(p) then
                local px, py = p:getX(), p:getY()
                if U.dist(px, py, L.x, L.y) <= C.Rous.range then
                    for _, a in ipairs(N.living(px, py, C.Rous.hunt)) do
                        local h = N.hunting[a]
                        if not h then
                            h = {}
                            N.hunting[a] = h
                            hunted = hunted + 1
                        end
                        -- After the nearest.
                        if not h.p or (h.p ~= p and U.dist(a:getX(), a:getY(), px, py)
                                < U.dist(a:getX(), a:getY(), h.p:getX(), h.p:getY())) then
                            h.p = p
                        end
                    end
                    if not st.cleared and N.allSpawned() and U.dist(px, py, L.x, L.y) <= 12
                            and #N.living(L.x, L.y, C.Rous.range) == 0 then
                        st.cleared = true
                        U.log("the nest under %s: the last rodent of unusual size is dead (%s there)", L.town, nameOf(p))
                        Net.toClient(p, "nest", { what = "cleared" })
                    end
                end
            end
        end
    end
    if hunted == 0 then return end
    local gone = {}
    for a, h in pairs(N.hunting) do
        if not chase(a, h, tick) then gone[#gone + 1] = a end
    end
    for _, a in ipairs(gone) do
        N.hunting[a] = nil
        hunted = hunted - 1
    end
end

---------------------------------------------------------------------------
-- The leash
---------------------------------------------------------------------------
--- Is x, y below ground somewhere an animal may stand: a floor of ours that is
--- not the rock under an outside wall?
local function walkway(cell, x, y)
    local sq = cell:getGridSquare(math.floor(x), math.floor(y), C.Z)
    local f = sq and U.floorOf(sq)
    return f ~= nil and U.spriteName(f) ~= C.Sprites.floorRock
end

--- Every so often: any animal below ground that has got off the walkway --
--- through a wall the pathfinder does not know about, or never on it -- is
--- put back on the nearest walkway within a few squares, or taken away.
function N.leash()
    local cell = U.cell()
    local list = cell and U.try("animals", function() return cell:getAnimals() end)
    local n = list and list:size() or 0
    local moved, removed = 0, 0
    for i = n - 1, 0, -1 do
        local a = list:get(i)
        local z = a and U.try("az", function() return a:getZ() end)
        if z and z < -0.5 and not U.try("adead", function() return a:isDead() end) then
            local x, y = a:getX(), a:getY()
            if not walkway(cell, x, y) then
                local best, bd = nil, 1e9
                for dx = -C.LeashReach, C.LeashReach do
                    for dy = -C.LeashReach, C.LeashReach do
                        local tx, ty = math.floor(x) + dx, math.floor(y) + dy
                        local dd = dx * dx + dy * dy
                        if dd < bd and walkway(cell, tx, ty) then best, bd = { tx, ty }, dd end
                    end
                end
                if best then
                    N.place(a, best[1] + 0.5, best[2] + 0.5)
                    moved = moved + 1
                else
                    U.try("aremove", function() a:removeFromWorld() end)
                    removed = removed + 1
                end
            end
        end
    end
    if moved + removed > 0 then
        U.debug("leash: %d animals put back on the walkway, %d taken away", moved, removed)
    end
    return moved, removed
end

--- A hit on a ROUS, logged: what the weapon did and what it has left. The
--- first test in game could not shoot them (0.5); this says why next time.
function N.onHit(attacker, target, weapon, damage)
    if not target or not isRous(target) then return end
    local hp = U.try("rous.hp", function() return target:getHealth() end)
    U.log("a ROUS was hit by %s with %s for %s; health %s", nameOf(attacker),
          tostring(U.try("wname", function() return weapon:getType() end)), tostring(damage), tostring(hp))
end

---------------------------------------------------------------------------
-- The walls that open
---------------------------------------------------------------------------
--- The record of the square x, y (its town's data), or nil.
function N.record(x, y)
    local L = lair()
    local T = L and SEW.Data and SEW.Data[L.town]
    local body = T and T.chunks[math.floor(x / 8) .. "," .. math.floor(y / 8)]
    if not body then return nil end
    for i = 1, #body, 7 do
        local r = body:sub(i, i + 6)
        if tonumber(r:sub(1, 1)) == x % 8 and tonumber(r:sub(2, 2)) == y % 8 then return r end
    end
    return nil
end

local function refuse(player, why)
    U.log("refused %s: %s", nameOf(player), why)
    Net.toClient(player, "refused", { why = why })
    return false
end

--- A player pulling at one of the nest's walls. Called from SEWPry:complete().
function N.pry(player, which)
    local ax, ay, bx, by = S.gateSquares(which)
    if not ax then return refuse(player, "shut") end
    if not S.below(player) then return refuse(player, "level") end
    if not (S.within(player, ax, ay, C.Reach + 1.0) or S.within(player, bx, by, C.Reach + 1.0)) then
        return refuse(player, "reach")
    end
    local st = B.state().lair
    if st.open[which] then return refuse(player, "open") end
    local L = lair()
    if which == "gate" and (not N.allSpawned() or #N.living(L.x, L.y, C.Rous.range) > 0) then
        return refuse(player, "rous")
    end
    -- The edge is held by the square south or east of it.
    local x, y = math.max(ax, bx), math.max(ay, by)
    local rec = N.record(x, y)
    if not rec then return refuse(player, "shut") end
    st.open[which] = true
    local how = B.square(x, y, rec, false, false)
    if how ~= "built" then
        st.open[which] = nil
        return refuse(player, "unready")
    end
    U.log("%s opened the nest's %s at %d,%d (%s)", nameOf(player), which, x, y, L.town)
    Net.toClient(player, "nest", { what = which })
    return true
end

local ticks = 0
Events.OnTick.Add(function()
    ticks = ticks + 1
    U.try("nest", N.hunt, ticks)
    if ticks % C.LeashEvery == 0 then U.try("leash", N.leash) end
end)
Events.OnWeaponHitCharacter.Add(function(...) U.try("rous.hit", N.onHit, ...) end)

---------------------------------------------------------------------------
-- Debug console
---------------------------------------------------------------------------
--- Where the nest is, what is open, and how many rodents are alive near it.
function SEW_Lair()
    local L = lair()
    if not L then U.log("SEW_Lair: no nest in this build") return end
    local st = B.state().lair
    U.log("nest (%s): false wall %d,%d, nest %d,%d, hoard %d,%d; wall %s, gate %s; rodents put down %s, alive near it %d",
          L.town, L.tx, L.ty, L.x, L.y, L.vx, L.vy, tostring(st.open.wall or false), tostring(st.open.gate or false),
          tostring(N.allSpawned()), #N.living(L.x, L.y, C.Rous.range))
end

return N
