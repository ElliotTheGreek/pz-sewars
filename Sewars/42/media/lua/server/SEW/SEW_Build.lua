--[[ Sewars -- raising the tunnels, a chunk at a time, on the server.

    The layout is data (tools/gen_sewers.py -> Data/SEW_Town_*.lua), one
    string per chunk, seven characters a square:

        x  y  floor  north-wall  west-wall  fixture  dressing

        floor    t tunnel  k vault  s shelter  g grating  w channel (sludge,
                 not walkable)  r rock under a wall outside  . none
        walls    c concrete  b brick  d a door frame with its steel door  . none
        fixture  L ladder on the N edge  l ladder on the W edge
                 P pillar (concrete)  Q pillar (brick)  . none
        dressing p pipe  e EXIT stencil  a-g graffiti  h SAFE stencil  i grime
                 u puddle  v debris  x light pool  y smear  . none

    Rules this file keeps (pz_trekship DEV_GUIDE, each by name):

      * **Never build where no player is standing.** A chunk is built only
        when it is loaded; one that is not is left for the next pass.
      * **The server changes the world only through transmit calls.** Every
        object is made whole -- tagged, its container made, stocked, explored
        -- and then sent with transmitAddObjectToSquare. A door goes in with
        AddSpecialObject and transmitCompleteItemToClients, which is the only
        way a closed door blocks (TestCollide reads the special objects).
        Floors are sent as objects too, the route vanilla's own building
        takes: IsoGridSquare.addFloor changes only the machine it runs on,
        and the player this is built for is standing right above it.
      * **Tag every object you place.** A pass never touches an object that is
        not ours, so what a player builds down here is theirs for good.
      * **Never restock an existing container**, and never put back what a
        player took: furniture and the dead are placed once, on a chunk's
        first build. Floors, walls and ladders are the tunnel and a later
        revision puts back any that are missing.
      * **Not over anything else.** A square at z -1 that already holds
        objects that are not ours -- a vanilla basement, a random basement,
        another mod -- is left alone entirely, with one WARN.
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Sewer"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util

local B = {}
SEW.Build = B

B.Z = C.Z

---------------------------------------------------------------------------
-- State
---------------------------------------------------------------------------
function B.state()
    local s = ModData.getOrCreate(C.StateKey)
    s.built = s.built or {}
    s.first = s.first or {}
    return s
end

function B.rev()
    return tostring(C.BuildRev) .. ":" .. tostring(SEW.Index and SEW.Index.rev or "?")
end

--- chunk key "cx,cy" -> town id, over every town's data. Built once.
local chunkTown = nil
function B.townOf(key)
    if not chunkTown then
        chunkTown = {}
        for tid, T in pairs(SEW.Data or {}) do
            for k in pairs(T.chunks) do chunkTown[k] = tid end
        end
    end
    return chunkTown[key]
end

function B.resetIndex() chunkTown = nil end

function B.isCurrent(key)
    return B.state().built[key] == B.rev()
end

---------------------------------------------------------------------------
-- Placing
---------------------------------------------------------------------------
local function tag(obj)
    U.try("tag", function() obj:getModData()[C.Tag] = 1 end)
end

local function send(sq, obj)
    return U.try("transmitAddObjectToSquare", function()
        sq:transmitAddObjectToSquare(obj, -1)
        return true
    end) == true
end

--- Puts a plain object with this sprite on the square unless one is there.
local function put(sq, sprite)
    if not sprite or U.findSprite(sq, sprite) then return false end
    local obj = U.try("IsoObject.new", function() return IsoObject.new(sq, sprite, "") end)
    if not obj then return false end
    tag(obj)
    return send(sq, obj)
end
B.put = put

local function hasDoor(sq, north)
    local found = false
    U.eachObject(sq, function(o)
        if instanceof(o, "IsoDoor") and U.try("door.north", function() return o:getNorth() end) == north then
            found = true
            return false
        end
    end)
    if found then return true end
    local specials = U.try("specials", function() return sq:getSpecialObjects() end)
    local n = specials and specials:size() or 0
    for i = 0, n - 1 do
        local o = specials:get(i)
        if instanceof(o, "IsoDoor") and o:getNorth() == north then return true end
    end
    return false
end

--- A steel door on the square's north (or west) edge. **Found by class and
--- edge, never by sprite**: an open door wears a different picture
--- (pz_trekship DEV_GUIDE, "Never find a door by its sprite").
local function putDoor(sq, north)
    if hasDoor(sq, north) then return false end
    local sprite = north and C.Sprites.door.N or C.Sprites.door.W
    local door = U.try("IsoDoor.new", function() return IsoDoor.new(getCell(), sq, sprite, north) end)
    if not door then return false end
    tag(door)
    return U.try("AddSpecialObject", function()
        sq:AddSpecialObject(door)
        if isServer() then door:transmitCompleteItemToClients() end
        return true
    end) == true
end

--- True when the square holds something that is not ours and not a dropped
--- item: somebody else's underground. Left alone.
local function foreign(sq)
    local other = false
    U.eachObject(sq, function(o)
        if not U.isOurs(o) and not instanceof(o, "IsoWorldInventoryObject") then
            other = true
            return false
        end
    end)
    return other
end

local FLOOR = {
    t = function() return C.Sprites.floorTunnel end,
    k = function() return C.Sprites.floorVault end,
    s = function() return C.Sprites.floorShelter end,
    r = function() return C.Sprites.floorRock end,
    -- The sludge tile carries no solidfloor (it is solidtrans: water you cannot
    -- wade), so on its own it is no floor at all to the engine. It goes over one.
    w = function() return C.Sprites.floorVault end,
    g = function(x, y) return C.Sprites.grating[(U.hash(x, y) % #C.Sprites.grating) + 1] end,
}

local function variant(style, edge, x, y)
    local list = C.Sprites.wallVariants[style][edge]
    return list[(U.hash(x, y, edge == "N" and 11 or 13) % #list) + 1]
end

local function wallSprites(n, w, x, y)
    local out = {}
    local sn, sw = C.Sprites.wall[n], C.Sprites.wall[w]
    if sn and sw and n == w then
        out[#out + 1] = sn.NW
    else
        if sn then out[#out + 1] = variant(n, "N", x, y) end
        if sw then out[#out + 1] = variant(w, "W", x, y) end
    end
    return out
end

-- Every sprite that is one of our walls, pillars, door frames or ladders.
local structural = nil
local function isStructural(name)
    if not structural then
        structural = {}
        for _, set in pairs(C.Sprites.wall) do
            for _, v in pairs(set) do structural[v] = true end
        end
        for _, set in pairs(C.Sprites.wallVariants) do
            for _, list in pairs(set) do for _, v in ipairs(list) do structural[v] = true end end
        end
        for _, v in pairs(C.Sprites.doorFrame) do structural[v] = true end
        for _, v in pairs(C.Sprites.ladder) do structural[v] = true end
    end
    return structural[name] == true
end

--- Removes our structural pieces from a square that its record no longer asks
--- for. Returns how many were removed.
function B.unwall(sq, walls, n, w, fix)
    local want = {}
    for _, v in ipairs(walls) do want[v] = true end
    if n == "d" then want[C.Sprites.doorFrame.N] = true end
    if w == "d" then want[C.Sprites.doorFrame.W] = true end
    if fix == "L" then want[C.Sprites.ladder.N] = true end
    if fix == "l" then want[C.Sprites.ladder.W] = true end
    if fix == "P" then want[C.Sprites.wall.c.pillar] = true end
    if fix == "Q" then want[C.Sprites.wall.b.pillar] = true end
    local doomed = {}
    U.eachObject(sq, function(o)
        local name = U.spriteName(o)
        if name and U.isOurs(o) and isStructural(name) and not want[name] then doomed[#doomed + 1] = o end
    end)
    for _, o in ipairs(doomed) do
        U.try("unwall", function() sq:transmitRemoveItemFromSquare(o) end)
    end
    return #doomed
end

local function dressSprite(code, n, x, y)
    local side = (n == "c" or n == "b") and "N" or "W"
    local Sp = C.Sprites
    if code == "p" then return Sp.pipes[(U.hash(x, y, 7) % #Sp.pipes) + 1] end
    if code == "e" then return Sp.exit[side] end
    if code == "h" then return Sp.safe[side] end
    if code == "i" then return Sp.grime[side] end
    if code == "u" then return Sp.puddle end
    if code == "v" then return Sp.debris end
    if code == "x" then return Sp.lightpool end
    if code == "y" then return Sp.smear end
    local g = Sp.graffiti[code]
    return g and g[side] or nil
end

--- One square from its record. `first` is the chunk's first build: dressing
--- goes down only then, so a player who scrubs the graffiti off keeps it off.
--- Returns "built", "foreign" or "unloaded".
function B.square(x, y, rec, first)
    local sq = U.square(x, y, B.Z, true)
    if not sq then return "unloaded" end
    if first and foreign(sq) then return "foreign" end

    local f, n, w, fix, dress = rec:sub(3, 3), rec:sub(4, 4), rec:sub(5, 5), rec:sub(6, 6), rec:sub(7, 7)
    local floorFn = FLOOR[f]
    if floorFn and not U.floorOf(sq) then put(sq, floorFn(x, y)) end
    if f == "w" then put(sq, C.Sprites.sludge) end

    -- Walls. A door frame stands in for the wall on its edge.
    local nw, ww = n, w
    if n == "d" then nw = "." end
    if w == "d" then ww = "." end
    local walls = wallSprites(nw ~= "." and nw or nil, ww ~= "." and ww or nil, x, y)
    -- A revised layout can open an edge an older one walled (0.3 joined streets
    -- that used to stop short of the trunk). A revision pass takes away our own
    -- wall pieces the record no longer asks for -- only ours, never a player's.
    if not first then B.unwall(sq, walls, n, w, fix) end
    for _, spr in ipairs(walls) do put(sq, spr) end
    if n == "d" then put(sq, C.Sprites.doorFrame.N) end
    if w == "d" then put(sq, C.Sprites.doorFrame.W) end
    if first then
        if n == "d" then putDoor(sq, true) end
        if w == "d" then putDoor(sq, false) end
    end

    if fix == "L" then put(sq, C.Sprites.ladder.N)
    elseif fix == "l" then put(sq, C.Sprites.ladder.W)
    elseif fix == "P" then put(sq, C.Sprites.wall.c.pillar)
    elseif fix == "Q" then put(sq, C.Sprites.wall.b.pillar) end

    if first and dress ~= "." then put(sq, dressSprite(dress, n, x, y)) end
    return "built"
end

---------------------------------------------------------------------------
-- Shelters and the dead
---------------------------------------------------------------------------
function B.furnish(entry, seed)
    local x, y, sprite, loot, extra = entry[1], entry[2], entry[3], entry[4], entry[5]
    local sq = U.square(x, y, B.Z, true)
    if not sq or U.findSprite(sq, sprite) then return false end
    local obj = U.try("IsoObject.new", function() return IsoObject.new(sq, sprite, "") end)
    if not obj then return false end
    tag(obj)
    U.try("containers", function() obj:createContainersFromSpriteProperties() end)
    local c = U.containerOf(obj)
    if c then
        -- Explored, or vanilla rolls its own loot into it on first look.
        U.try("explored", function() c:setExplored(true) end)
        -- The story's journal and plan go in first, so a full container
        -- cannot squeeze them out.
        if extra and SEW.Story then SEW.Story.stockExtras(c, extra) end
        if loot and C.Loot[loot] then
            U.fill(obj, C.Loot[loot], nil, nil, seed)
        elseif loot then
            U.warnOnce("loot:" .. loot, "no C.Loot list named " .. loot)
        end
    end
    return send(sq, obj)
end

local function nearAPlayer(x, y, range)
    for _, p in ipairs(U.players()) do
        local px = U.try("px", function() return p:getX() end) or 0
        local py = U.try("py", function() return p:getY() end) or 0
        if U.dist(px, py, x, y) < range then return true end
    end
    return false
end

function B.spawn(x, y, outfit)
    if nearAPlayer(x, y, C.SpawnClearance) then return false end
    local list = U.try("addZombiesInOutfit", function()
        return addZombiesInOutfit(x, y, B.Z, 1, outfit, 50, false, false, false, false, false, false, 1.0)
    end)
    return list ~= nil and U.try("zombies.size", function() return list:size() end) or false
end

function B.density()
    local v = SandboxVars and SandboxVars.Sewars and SandboxVars.Sewars.Zombies or 3
    return C.Density[v] or C.Density[3]
end

---------------------------------------------------------------------------
-- A chunk
---------------------------------------------------------------------------
--- Builds chunk `key` ("cx,cy") if it is loaded. Returns true when it is now
--- current; false when it must be tried again (not loaded).
function B.chunk(key)
    local tid = B.townOf(key)
    if not tid then return true end
    local T = SEW.Data[tid]
    local body = T.chunks[key]
    local cx, cy = key:match("^(-?%d+),(-?%d+)$")
    cx, cy = tonumber(cx), tonumber(cy)
    if not U.chunkLoaded(cx * 8 + 4, cy * 8 + 4) then return false end

    local s = B.state()
    local first = s.first[key] == nil
    local built, skipped, open = 0, 0, {}
    for i = 1, #body, 7 do
        local rec = body:sub(i, i + 6)
        local x, y = cx * 8 + tonumber(rec:sub(1, 1)), cy * 8 + tonumber(rec:sub(2, 2))
        local how = B.square(x, y, rec, first)
        if how == "unloaded" then return false end
        if how == "foreign" then
            skipped = skipped + 1
        else
            built = built + 1
            local f = rec:sub(3, 3)
            if f == "t" or f == "k" then open[#open + 1] = { x, y } end
        end
    end
    if skipped > 0 then
        U.warnOnce("foreign:" .. key, "chunk %s: %d squares already hold something underground "
                   .. "(a basement?) and were left alone", key, skipped)
    end

    if first then
        local seed = U.hash(cx, cy)
        for _, e in ipairs(T.furniture[key] or {}) do B.furnish(e, seed) end
        local d = B.density()
        if d > 0 then
            local want = #open * d / 100
            local n = math.floor(want) + ((U.hash(cx, cy, 3) % 100) < (want % 1) * 100 and 1 or 0)
            for k = 1, n do
                local p = open[(U.hash(cx, cy, k) % #open) + 1]
                B.spawn(p[1], p[2], C.Outfits[(U.hash(p[1], p[2], k) % #C.Outfits) + 1])
            end
        end
        for _, z in ipairs(T.claimed[key] or {}) do B.spawn(z[1], z[2], z[3]) end
        s.first[key] = B.rev()
    end
    s.built[key] = B.rev()
    U.debug("built chunk %s (%s): %d squares%s", key, tid, built, first and ", first" or "")
    return true
end

--- Every chunk within `r` chunks of x, y that has tunnel in it and is not
--- current, nearest first.
function B.pending(x, y, r)
    local out = {}
    local pcx, pcy = math.floor(x / 8), math.floor(y / 8)
    for dx = -r, r do
        for dy = -r, r do
            local key = (pcx + dx) .. "," .. (pcy + dy)
            if B.townOf(key) and not B.isCurrent(key) then
                out[#out + 1] = { key = key, d = dx * dx + dy * dy }
            end
        end
    end
    table.sort(out, function(a, b) return a.d < b.d end)
    return out
end

--- Builds everything near x, y now. Used before a climb down is granted:
--- the player is standing over it, so all of it is loaded.
function B.around(x, y, r)
    local done, left = 0, 0
    for _, p in ipairs(B.pending(x, y, r)) do
        if B.chunk(p.key) then done = done + 1 else left = left + 1 end
    end
    return done, left
end

return B
