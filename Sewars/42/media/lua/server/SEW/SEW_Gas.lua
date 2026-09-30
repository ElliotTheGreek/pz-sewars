--[[ Sewars -- sewer gas: the foul stretches, and what breathing them does.

    Runs in single player and on any server (never on a client). DESIGN.md 7b
    is the design; DEV_GUIDE, *Sewer gas is poison the server gives, and only
    the server*, the engine facts behind it.

    The generator (tools/gen_sewers.py vent_gas) marked some narrow culverts
    as gas, well clear of the ladders, and wrote each town's gas squares
    (`T.gas`, "xyi" per square: x, y in the chunk, the stretch's id) and the
    placards at their ways in (`T.gasSigns`). Nothing about the tunnel itself
    changes: a gas square is walkway like any other.

      * The builder lays the haze and hangs the placards once per chunk
        (SEW_Build, s.gas), even in a chunk built before there was gas.
      * Every C.Gas.lookEvery ticks, each player below: in a stretch they had
        not been in a moment ago? Their map gets it (SEW_Discovery.gas) and
        their client a `gas` note (and a cough, muffled through a mask).
      * Every game minute, each player below in a stretch breathes it. A
        mask or respirator with a filter (the engine's isProtectedFromToxic)
        keeps it out and its filter is used up (Clothing.drainGasMask);
        otherwise poison is added (CharacterStat.POISON) up to the sandbox's
        cap, which the engine turns into sickness, and past 10 into lost
        health, and lets decay by itself once they are out of it.

    **Only here, on the server.** In multiplayer the server simulates every
    player's body and stats and pushes them to the owner every second
    (NetworkPlayerManager.update); a client's own write would be overwritten.
    syncPlayerStats sends the change at once.
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Net"
require "SEW/SEW_Sewer"
require "SEW/SEW_Build"
require "SEW/SEW_Discovery"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local Net = SEW.Net
local S = SEW.Sewer
local B = SEW.Build

local G = {}
SEW.Gas = G

--- The sandbox's strength, 1 (Off) .. 4 (Deadly); Harmful when unset.
function G.strength()
    return B.option("Gas", 3, #C.Gas.dose)
end

-- chunk key -> { ["x,y"] = stretch id } | false, parsed once from the data.
local parsed = {}

local function chunkGas(key)
    local cached = parsed[key]
    if cached ~= nil then return cached or nil end
    local tid = B.townOf(key)
    local body = tid and SEW.Data[tid].gas and SEW.Data[tid].gas[key]
    if not body then
        parsed[key] = false
        return nil
    end
    local cx, cy = key:match("^(-?%d+),(-?%d+)$")
    cx, cy = tonumber(cx), tonumber(cy)
    local set = {}
    for i = 1, #body, 3 do
        local x = cx * 8 + tonumber(body:sub(i, i))
        local y = cy * 8 + tonumber(body:sub(i + 1, i + 1))
        set[x .. "," .. y] = body:sub(i + 2, i + 2)
    end
    parsed[key] = set
    return set
end

function G.reset() parsed = {} end

--- The stretch of gas the square x, y (below ground) is in: its town and
--- id, or nil.
function G.at(x, y)
    x, y = math.floor(x), math.floor(y)
    local key = math.floor(x / 8) .. "," .. math.floor(y / 8)
    local set = chunkGas(key)
    local id = set and set[x .. "," .. y]
    if not id then return nil end
    return B.townOf(key), id
end

-- "town:id" -> its place in SEW.Index.gas, built once.
local indexOf = nil
function G.index(town, id)
    if not indexOf then
        indexOf = {}
        for i, g in ipairs(SEW.Index and SEW.Index.gas or {}) do indexOf[g.town .. ":" .. g.id] = i end
    end
    return indexOf[tostring(town) .. ":" .. tostring(id)]
end

--- Lays a chunk's haze and hangs its placards. Called by SEW_Build.chunk
--- once per chunk (s.gas), first build or not. Returns how many went in.
function G.dress(key)
    local tid = B.townOf(key)
    local T = tid and SEW.Data[tid]
    if not T then return 0 end
    local n = 0
    local set = chunkGas(key)
    if set then
        for k in pairs(set) do
            local x, y = k:match("^(-?%d+),(-?%d+)$")
            local sq = U.square(tonumber(x), tonumber(y), C.Z, false)
            if sq and U.floorOf(sq) and B.put(sq, C.Sprites.haze) then n = n + 1 end
        end
    end
    for _, s in ipairs(T.gasSigns and T.gasSigns[key] or {}) do
        local sq = U.square(s[1], s[2], C.Z, false)
        if sq and B.hang(sq, C.Sprites.gasSign[s[3]]) then n = n + 1 end
    end
    return n
end

--- True when this chunk has gas or a placard in it.
function G.inChunk(key)
    local tid = B.townOf(key)
    local T = tid and SEW.Data[tid]
    return T ~= nil and ((T.gas and T.gas[key] ~= nil) or (T.gasSigns and T.gasSigns[key] ~= nil))
end

--- True when the character wears a mask or respirator with a filter (or an
--- SCBA with air): the engine's own test, without its tiny drain.
function G.protected(p)
    return U.try("gas.protected", function() return p:isProtectedFromToxic(false) end) == true
end

--- A minute of the filter: each worn piece of clothing is asked to drain its
--- gas mask (the engine's call is a no-op for anything that is not a mask
--- with a filter in it). Batched: a missing method fails once.
function G.drainFilter(p)
    local worn = U.try("gas.worn", function() return p:getWornItems() end)
    local n = worn and U.try("gas.wornSize", function() return worn:size() end) or 0
    local call = U.batch("gas.drain")
    for i = 0, n - 1 do
        local it = call(function() return worn:getItemByIndex(i) end)
        if it and instanceof(it, "Clothing") then
            call(function() it:drainGasMask(C.Gas.filterDrain) end)
        end
    end
end

--- One game minute of gas for one player: poison up to the cap, or a
--- filter's worth of breath. Returns the poison it added.
function G.breathe(p, strength)
    strength = strength or G.strength()
    local dose, cap = C.Gas.dose[strength] or 0, C.Gas.cap[strength] or 0
    if dose <= 0 then return 0 end
    if G.protected(p) then
        G.drainFilter(p)
        return 0
    end
    local added = U.try("gas.poison", function()
        local stats = p:getStats()
        local now = stats:get(CharacterStat.POISON)
        local give = math.max(0, math.min(dose, cap - now))
        if give > 0 then stats:add(CharacterStat.POISON, give) end
        return give
    end) or 0
    if added > 0 and isServer() then
        U.try("gas.sync", function() syncPlayerStats(p, C.Gas.syncMask) end)
    end
    return added
end

-- username -> "town:id" of the stretch they were in at the last look.
G.inside = {}

local function nameOf(p)
    return U.try("username", function() return p:getUsername() end) or "player"
end

--- Every C.Gas.lookEvery ticks: who has walked into a stretch.
function G.look()
    if G.strength() <= 1 then return end
    for _, p in ipairs(U.players()) do
        local name = nameOf(p)
        local town, id = nil, nil
        if S.below(p) then town, id = G.at(p:getX(), p:getY()) end
        local here = id and (town .. ":" .. id) or nil
        if here and G.inside[name] ~= here then
            local i = G.index(town, id)
            if i then SEW.Discovery.gas(p, i) end
            Net.toClient(p, "gas", { protected = G.protected(p) })
        end
        G.inside[name] = here
    end
end

--- Every game minute: everybody in a stretch breathes it.
function G.minute()
    local strength = G.strength()
    if strength <= 1 then return end
    for _, p in ipairs(U.players()) do
        if S.below(p) and G.at(p:getX(), p:getY()) then G.breathe(p, strength) end
    end
end

local ticks = 0
Events.OnTick.Add(function()
    ticks = ticks + 1
    if ticks % C.Gas.lookEvery == 0 then U.try("gas.look", G.look) end
end)
Events.EveryOneMinute.Add(function() U.try("gas.minute", G.minute) end)

--- Debug console: the stretches of gas in a town (default the one you are in).
function SEW_Gas(town)
    local p = U.players()[1]
    local here = p and B.townOf(math.floor(p:getX() / 8) .. "," .. math.floor(p:getY() / 8))
    for i, g in ipairs(SEW.Index.gas or {}) do
        if g.town == (town or here) then
            U.log("gas %d (%s %s): %d squares round %d,%d", i, g.town, g.id, g.n, g.x, g.y)
        end
    end
    if p then
        local t, id = G.at(p:getX(), p:getY())
        U.log("you are %s; strength %d; poison %s", id and ("in gas " .. t .. " " .. id) or "in clean air",
              G.strength(), tostring(U.try("poison", function() return p:getStats():get(CharacterStat.POISON) end)))
    end
end

--- Debug console: to the middle of the n-th stretch of gas (below ground).
function SEW_GoGas(i)
    local g = (SEW.Index.gas or {})[i or 1]
    local p = U.players()[1]
    if not g or not p or isClient() then return end
    B.around(g.x, g.y, 1)
    U.teleport(p, g.x, g.y, C.Z)
    U.log("SEW_GoGas: in gas %d (%s %s) at %d,%d", i or 1, g.town, g.id, g.x, g.y)
end

return G
