--[[ Sewars -- raising the tunnels, a chunk at a time, on the server.

    The layout is data (tools/gen_sewers.py -> Data/SEW_Town_*.lua), one
    string per chunk, seven characters a square:

        x  y  floor  north-wall  west-wall  fixture  dressing

        floor    t tunnel  k vault  s shelter  g grating  w channel (sludge,
                 not walkable)  r rock under a wall outside  m cave (dug earth)
                 n the rats' nest and its run (dug earth)  v the rats' hoard
                 p a passage the cult dug (earth)  h the temple's stone floor
                 a its carpet  q its boards  . none
        walls    c concrete  b brick  d a door frame with its steel door
                 j a door frame with a locked grille (a county room: DESIGN.md 7, Locked gates)
                 e earth  o breach through concrete  q breach through brick
                 O Q the same, where the cult broke into a sewer from their side
                 x y the false wall into the nest (concrete, brick): a wall
                 until it is pulled away, then a breach
                 z the gnawed wall from the nest into the hoard: brick until
                 it is torn through, then a breach  . none
        fixture  L ladder on the N edge  l ladder on the W edge
                 P pillar (concrete)  Q pillar (brick)  . none
        dressing p pipe  e EXIT stencil  a-g graffiti  h SAFE stencil  i grime
                 u puddle  v debris  x light pool  y smear  z loose stones
                 j bones  k nest litter  l claw marks  n cracks and a gnawed
                 hole (on the false wall)  o the R.O.U.S. warning  . none

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
    -- Chunks whose caves have had their dressing, furniture and dead: kept
    -- apart from `first` so caves reach chunks built before there were any.
    s.caves = s.caves or {}
    -- "x,y" of a hatch -> "open" (its trapdoor is in the floor) or "blocked"
    -- (a basement is under its house). Decided once, when first looked at.
    s.hatches = s.hatches or {}
    -- "x,y" of a cover of ours -> "placed".
    s.covers = s.covers or {}
    -- The rats' nest: which of its two walls are open ("wall", the false wall
    -- from the sewer; "gate", into the hoard), and which rodents have been
    -- put down ("x,y" of each, from the index).
    s.lair = s.lair or {}
    s.lair.open = s.lair.open or {}
    s.lair.rous = s.lair.rous or {}
    -- Chunks whose sewer gas has its haze and placards (SEW_Gas.dress): once,
    -- first build or not, so gas reaches chunks built before there was any.
    s.gas = s.gas or {}
    -- Chunks whose pictures -- the cult's marks, the temple's sconces and
    -- banners -- have been hung (T.pictures): once, first build or not, so
    -- the marks by a breach reach a sewer a save built before the temple.
    s.hung = s.hung or {}
    -- Chunks whose dens of the warren have their caches, relics and dead
    -- (T.warren, T.warrenDead): once, first build or not, so a save that
    -- already has the nest gets the dens' contents with their floors.
    s.warren = s.warren or {}
    -- The dead of a set piece -- the temple's, the dens' -- who could not be
    -- put down when their chunk was built, because a player was standing too
    -- near: chunk key -> { { x, y, outfit, fx, fy }, ... }. They are owed, and
    -- put down once nobody is (B.settle).
    s.owed = s.owed or {}
    -- What players have dug (SEW_Mine): records of their own, read in place
    -- of the generator's. Chunk key -> { ["x,y"] = record }. It grows with
    -- the digging, and like the rest of this is never transmitted.
    s.dug = s.dug or {}
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

---------------------------------------------------------------------------
-- Records, by square
---------------------------------------------------------------------------
-- chunk key -> { ["x,y"] = record } of the generator's data, cut up the first
-- time a square of the chunk is asked for.
local cut = {}

--- The generator's record of x, y, or nil.
function B.dataAt(x, y)
    local key = math.floor(x / 8) .. "," .. math.floor(y / 8)
    local c = cut[key]
    if c == nil then
        c = false
        local tid = B.townOf(key)
        local body = tid and SEW.Data[tid].chunks[key]
        if body then
            c = {}
            local cx, cy = math.floor(x / 8) * 8, math.floor(y / 8) * 8
            for i = 1, #body, 7 do
                local rec = body:sub(i, i + 6)
                c[(cx + tonumber(rec:sub(1, 1))) .. "," .. (cy + tonumber(rec:sub(2, 2)))] = rec
            end
        end
        cut[key] = c
    end
    return c and c[x .. "," .. y] or nil
end

--- The record of x, y as it stands: what a player dug there (SEW_Mine), else
--- the generator's, else nil.
function B.recordAt(x, y)
    local over = B.state().dug[math.floor(x / 8) .. "," .. math.floor(y / 8)]
    return (over and over[x .. "," .. y]) or B.dataAt(x, y)
end

--- Writes a record of the players' own for x, y. It is read in place of the
--- generator's from now on, by every pass.
function B.setRecord(x, y, rec)
    local dug = B.state().dug
    local key = math.floor(x / 8) .. "," .. math.floor(y / 8)
    dug[key] = dug[key] or {}
    dug[key][x .. "," .. y] = rec
end

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

--- A steel door on the square's north (or west) edge -- or, given a key id,
--- a county room's locked grille. **Found by class and edge, never by
--- sprite**: an open door wears a different picture (pz_trekship DEV_GUIDE,
--- "Never find a door by its sprite").
---
--- The grille (DEV_GUIDE, *A locked gate is a key id and a lock set before
--- it is sent*) is vanilla's cell door made from its sprite (the IsoSprite
--- overload: 2000 health, as vanilla's own test builds one), keyed to its
--- town and locked by key -- before it is sent: transmitCompleteItemToClients
--- carries the key id and the locks, and a later sync() would not carry the
--- key id. Not CustomLock: that asks everybody for the key, from inside too,
--- and would shut in a player without one (SEW_Keys.latch is the handle on
--- the inside).
local function putDoor(sq, north, key)
    if hasDoor(sq, north) then return false end
    local door
    if key then
        local sprite = north and C.Sprites.gate.N or C.Sprites.gate.W
        door = U.try("IsoDoor.gate", function() return IsoDoor.new(getCell(), sq, getSprite(sprite), north) end)
        if not door then return false end
        U.try("gate.lock", function()
            door:setKeyId(key)
            door:setLockedByKey(true)
        end)
    else
        local sprite = north and C.Sprites.door.N or C.Sprites.door.W
        door = U.try("IsoDoor.new", function() return IsoDoor.new(getCell(), sq, sprite, north) end)
        if not door then return false end
    end
    tag(door)
    return U.try("AddSpecialObject", function()
        sq:AddSpecialObject(door)
        if isServer() then door:transmitCompleteItemToClients() end
        return true
    end) == true
end

--- Somebody else's underground, left alone (SEW_Util: the client asks the
--- same before it calls for a rescue).
local foreign = U.foreign

B.foreign = foreign

local FLOOR = {
    t = function() return C.Sprites.floorTunnel end,
    k = function() return C.Sprites.floorVault end,
    s = function() return C.Sprites.floorShelter end,
    r = function() return C.Sprites.floorRock end,
    -- The sludge tile carries no solidfloor (it is solidtrans: water you cannot
    -- wade), so on its own it is no floor at all to the engine. It goes over one.
    w = function() return C.Sprites.floorVault end,
    g = function(x, y) return C.Sprites.grating[(U.hash(x, y) % #C.Sprites.grating) + 1] end,
    -- Mostly the one dirt, the darker one here and there. Not hash % 2: the
    -- hash's multipliers are odd, so its parity is (x + y)'s -- a checkerboard
    -- (the first render).
    m = function(x, y) return C.Sprites.floorCave[(U.hash(x, y, 5) % 5 == 0) and 2 or 1] end,
    -- Not hash % 3 either: the hash is linear, and any small modulus of it
    -- lays stripes (the first render of the nest). One step of U.rng mixes it.
    n = function(x, y) return C.Sprites.floorCave[(U.rng(U.hash(x, y, 5))(4) == 1) and 2 or 1] end,
    v = function() return C.Sprites.floorVault end,
    -- The cult's passages are dug earth, as a cave's; the temple is built.
    p = function(x, y) return C.Sprites.floorCave[(U.rng(U.hash(x, y, 5))(4) == 1) and 2 or 1] end,
    h = function() return C.Sprites.floorTemple end,
    a = function() return C.Sprites.floorCarpet end,
    q = function() return C.Sprites.floorBoards end,
}

-- A breach, and the wall it was broken through: o concrete, q brick; O and Q
-- the same where the cult broke into a sewer (tools/gen_temple.py).
local BREACH = { o = "o", q = "q", O = "o", Q = "q" }

-- The nest's two walls that open: each a wall until it is opened (state, by
-- which), then a breach through the same material.
local GATE = { x = { which = "wall", shut = "c", open = "o" },
               y = { which = "wall", shut = "b", open = "q" },
               z = { which = "gate", shut = "b", open = "q" } }
B.GATE = GATE

--- The id of the maintenance key of the town whose tunnel x, y is in, or nil
--- (a town with no locked gates has none).
function B.townKey(x, y)
    local tid = B.townOf(math.floor(x / 8) .. "," .. math.floor(y / 8))
    local t = tid and SEW.Index and SEW.Index.towns[tid]
    return t and t.key or nil
end

--- True when the nest's "wall" or "gate" has been opened in this save.
function B.gateOpen(which)
    return B.state().lair.open[which] == true
end

--- Floors that belong to a cave or the nest: new ground when their chunk's
--- caves are dug, even in a chunk built before there were any.
local DUG = { m = true, n = true, v = true, p = true }

local function variant(style, edge, x, y)
    local set = C.Sprites.wallVariants[style]
    local list = set and set[edge]
    if not list then return C.Sprites.wall[style][edge] end
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
        for _, set in pairs(C.Sprites.breach) do
            for _, v in pairs(set) do structural[v] = true end
        end
        for _, v in pairs(C.Sprites.earthFace) do structural[v] = true end
        for _, v in pairs(C.Sprites.ladder) do structural[v] = true end
    end
    return structural[name] == true
end

--- Removes our structural pieces from a square that its record no longer asks
--- for. Returns how many were removed.
function B.unwall(sq, walls, n, w, fix)
    local want = {}
    for _, v in ipairs(walls) do want[v] = true end
    if n == "d" or n == "j" then want[C.Sprites.doorFrame.N] = true end
    if w == "d" or w == "j" then want[C.Sprites.doorFrame.W] = true end
    if BREACH[n] then want[C.Sprites.breach[BREACH[n]].N], want[C.Sprites.doorFrame.N] = true, true end
    if BREACH[w] then want[C.Sprites.breach[BREACH[w]].W], want[C.Sprites.doorFrame.W] = true, true end
    if n == "e" then want[C.Sprites.earthFace.N] = true end
    if w == "e" then want[C.Sprites.earthFace.W] = true end
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

---------------------------------------------------------------------------
-- Pictures on walls
---------------------------------------------------------------------------
-- A picture of ours on a wall -- earth, a breach, a ladder, a stencil,
-- graffiti, grime -- is attached to the wall or door frame it hangs on, the
-- way vanilla hangs a wall overlay (ISMoveableSpriteProps: AttachExistingAnim,
-- then transmitUpdatedSpriteToClients). The camera's cutaway cuts a wall and
-- what is attached to it and nothing else (FBORenderCell.performDrawWallSegmentSingle
-- -> DoCutawayShaderAttached); a picture that is an object of its own stayed
-- full height over its cut wall (found in play, 0.3.2: floating earth by a
-- breach). Attached sprites are saved and sent with the object (IsoObject.save).

-- sprite name -> the edge it hangs on
local overlayEdges = nil
local function overlayEdge(name)
    if not overlayEdges then
        overlayEdges = {}
        local Sp = C.Sprites
        local sets = { Sp.earthFace, Sp.ladder, Sp.exit, Sp.safe, Sp.grime, Sp.cracks, Sp.claws, Sp.rousWarning,
                       Sp.gasSign }
        for _, set in pairs(Sp.breach) do sets[#sets + 1] = set end
        for _, set in pairs(Sp.graffiti) do sets[#sets + 1] = set end
        -- The cult's: sigil, slogan, sconce, banner.
        for _, k in ipairs({ "sigil", "burrow", "torch", "banner" }) do sets[#sets + 1] = Sp.cult[k] end
        for _, set in ipairs(sets) do
            overlayEdges[set.N] = "N"
            overlayEdges[set.W] = "W"
        end
        -- And the triptych behind the idol: north walls only.
        for _, v in ipairs(Sp.cult.mural) do overlayEdges[v] = "N" end
    end
    return name and overlayEdges[name]
end
B.overlayEdge = overlayEdge

-- sprite name -> the edges an object wearing it can carry a picture on:
-- our walls, corners and door frames.
local hostEdges = nil
local function hostEdge(name)
    if not hostEdges then
        hostEdges = {}
        local function add(n, e)
            if n then hostEdges[n] = hostEdges[n] or {}; hostEdges[n][e] = true end
        end
        for _, set in pairs(C.Sprites.wall) do
            add(set.N, "N"); add(set.W, "W"); add(set.NW, "N"); add(set.NW, "W")
        end
        for _, set in pairs(C.Sprites.wallVariants) do
            for _, v in ipairs(set.N or {}) do add(v, "N") end
            for _, v in ipairs(set.W or {}) do add(v, "W") end
        end
        add(C.Sprites.doorFrame.N, "N"); add(C.Sprites.doorFrame.W, "W")
    end
    return name and hostEdges[name]
end

local function hostOf(sq, edge)
    local host = nil
    U.eachObject(sq, function(o)
        local h = U.isOurs(o) and hostEdge(U.spriteName(o))
        if h and h[edge] then
            host = o
            return false
        end
    end)
    return host
end

--- True when `sprite` is on the square, as an object or attached to one.
function B.hasPicture(sq, sprite)
    if U.findSprite(sq, sprite) then return true end
    local spr = getSprite(sprite)
    local found = false
    U.eachObject(sq, function(o)
        if U.try("isAttached", function() return o:isAttachedAnimSprite(spr) end) == true then
            found = true
            return false
        end
    end)
    return found
end

--- A picture of ours: on its wall when the square has one on its edge,
--- otherwise (a stencil on an edge with no wall of ours) an object of its own.
local function hang(sq, sprite)
    local edge = overlayEdge(sprite)
    local host = edge and hostOf(sq, edge)
    if not host then return put(sq, sprite) end
    local spr = getSprite(sprite)
    if U.try("isAttached", function() return host:isAttachedAnimSprite(spr) end) == true then return false end
    return U.try("AttachExistingAnim", function()
        host:AttachExistingAnim(spr, 0, 0, false, 0, false, 0.0)
        if isServer() then host:transmitUpdatedSpriteToClients() end
        return true
    end) == true
end
B.hang = hang

--- Squares built before 0.3.2's play-test carry our pictures as objects of
--- their own: each one that now has a wall to hang on is taken off the
--- square and hung there. Only ours. Returns how many moved.
function B.rehang(sq)
    local loose = {}
    U.eachObject(sq, function(o)
        local edge = U.isOurs(o) and overlayEdge(U.spriteName(o))
        if edge and hostOf(sq, edge) then loose[#loose + 1] = o end
    end)
    for _, o in ipairs(loose) do
        local name = U.spriteName(o)
        U.try("rehang", function() sq:transmitRemoveItemFromSquare(o) end)
        hang(sq, name)
    end
    return #loose
end

local function dressSprite(code, n, x, y, gateEdge)
    local side = (n == "c" or n == "b") and "N" or "W"
    -- The nest's: the cracks on the false wall, whichever edge it is; claws
    -- on the gnawed wall, or on the nest's earth.
    if (code == "n" or code == "l") and gateEdge then
        side = gateEdge
    elseif code == "l" then
        side = (n == "e") and "N" or "W"
    end
    local Sp = C.Sprites
    if code == "p" then return Sp.pipes[(U.hash(x, y, 7) % #Sp.pipes) + 1] end
    if code == "e" then return Sp.exit[side] end
    if code == "h" then return Sp.safe[side] end
    if code == "i" then return Sp.grime[side] end
    if code == "u" then return Sp.puddle end
    if code == "v" then return Sp.debris end
    if code == "x" then return Sp.lightpool end
    if code == "y" then return Sp.smear end
    if code == "z" then return Sp.stones[(U.hash(x, y, 17) % #Sp.stones) + 1] end
    if code == "j" then return Sp.bones end
    if code == "k" then return Sp.litter end
    if code == "l" then return Sp.claws[side] end
    if code == "n" then return Sp.cracks[side] end
    if code == "o" then return Sp.rousWarning[side] end
    local g = Sp.graffiti[code]
    return g and g[side] or nil
end

--- One square from its record. `first` is the chunk's first build: dressing
--- goes down only then, so a player who scrubs the graffiti off keeps it off.
--- `caves` is true when this chunk's caves have not been dug yet: a cave
--- square is then new ground, even in a chunk built before caves existed.
--- Returns "built", "foreign" or "unloaded".
function B.square(x, y, rec, first, caves)
    local sq = U.square(x, y, B.Z, true)
    if not sq then return "unloaded" end
    local f, n, w, fix, dress = rec:sub(3, 3), rec:sub(4, 4), rec:sub(5, 5), rec:sub(6, 6), rec:sub(7, 7)
    -- The nest's walls that open: a wall, or once opened a breach.
    local gateEdge = GATE[n] and "N" or GATE[w] and "W" or nil
    if GATE[n] then n = B.gateOpen(GATE[n].which) and GATE[n].open or GATE[n].shut end
    if GATE[w] then w = B.gateOpen(GATE[w].which) and GATE[w].open or GATE[w].shut end
    local fresh = first or (caves == true and DUG[f] == true)
    if fresh and foreign(sq) then return "foreign" end

    local floorFn = FLOOR[f]
    local floor = U.floorOf(sq)
    -- Our rock under an outside wall, where a revised layout now puts a floor
    -- (a cave dug into it, a culvert run on): the rock gives way to it.
    if floor and floorFn and f ~= "r" and not first and U.isOurs(floor) and U.spriteName(floor) == C.Sprites.floorRock then
        U.try("unrock", function() sq:transmitRemoveItemFromSquare(floor) end)
        floor = nil
    end
    if floorFn and not floor then put(sq, floorFn(x, y)) end
    if f == "w" then
        -- Chunks built before 0.3.2 carry vanilla's floating sludge: ours only.
        if not first then
            local old = {}
            U.eachObject(sq, function(o)
                if U.isOurs(o) and U.spriteName(o) == C.Sprites.sludgeOld then old[#old + 1] = o end
            end)
            for _, o in ipairs(old) do
                U.try("unsludge", function() sq:transmitRemoveItemFromSquare(o) end)
            end
        end
        put(sq, C.Sprites.sludge)
    end

    -- Walls. A door frame stands in for the wall on its edge.
    local nw, ww = n, w
    if n == "d" or n == "j" or BREACH[n] then nw = "." end
    if w == "d" or w == "j" or BREACH[w] then ww = "." end
    local walls = wallSprites(nw ~= "." and nw or nil, ww ~= "." and ww or nil, x, y)
    -- A revised layout can open an edge an older one walled (0.3 joined streets
    -- that used to stop short of the trunk). A revision pass takes away our own
    -- wall pieces the record no longer asks for -- only ours, never a player's.
    if not first then B.unwall(sq, walls, n, w, fix) end
    for _, spr in ipairs(walls) do put(sq, spr) end
    if n == "d" or n == "j" then put(sq, C.Sprites.doorFrame.N) end
    if w == "d" or w == "j" then put(sq, C.Sprites.doorFrame.W) end
    -- Ours on vanilla's: hung on the wall or frame, so it is drawn, cut and
    -- saved with it ("Pictures on walls" above).
    if BREACH[n] then put(sq, C.Sprites.doorFrame.N) end
    if BREACH[w] then put(sq, C.Sprites.doorFrame.W) end
    if not first then B.rehang(sq) end
    if BREACH[n] then hang(sq, C.Sprites.breach[BREACH[n]].N) end
    if BREACH[w] then hang(sq, C.Sprites.breach[BREACH[w]].W) end
    if n == "e" then hang(sq, C.Sprites.earthFace.N) end
    if w == "e" then hang(sq, C.Sprites.earthFace.W) end
    if first then
        if n == "d" then putDoor(sq, true) end
        if w == "d" then putDoor(sq, false) end
        if n == "j" or w == "j" then
            local key = B.townKey(x, y)
            if not key then
                U.warnOnce("gateKey:" .. x .. "," .. y, "a locked gate at %d,%d with no town key", x, y)
            elseif n == "j" then putDoor(sq, true, key)
            else putDoor(sq, false, key) end
        end
    end

    if fix == "L" then hang(sq, C.Sprites.ladder.N)
    elseif fix == "l" then hang(sq, C.Sprites.ladder.W)
    elseif fix == "P" then put(sq, C.Sprites.wall.c.pillar)
    elseif fix == "Q" then put(sq, C.Sprites.wall.b.pillar) end

    -- Rubble by a breach and the nest's signs on the sewer's side are the
    -- cave's too, on squares a save built before them.
    local late = caves == true and (dress == "z" or dress == "n" or dress == "o")
    if (fresh or late) and dress ~= "." then
        local spr = dressSprite(dress, n, x, y, gateEdge)
        if overlayEdge(spr) then hang(sq, spr) else put(sq, spr) end
    end
    -- A tunnel is no room: on a server, whatever room the engine gave this
    -- square comes off (SEW_Rooms).
    if SEW.Rooms then SEW.Rooms.built(sq) end
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
            -- Seeded by the square too, or two crates of a chunk would match.
            -- The rats' hoard is always worth the fight.
            local lo, hi = unpack(loot:sub(1, 5) == "hoard" and C.HoardCount
                                  or C.LootCount[B.option("Loot", 3, #C.LootCount)])
            local mine = U.hash(x, y, seed)
            U.fill(obj, C.Loot[loot], lo + mine % (hi - lo + 1), mine)
            -- Now and then, somebody's map to the temple or to the nest (SEW_Maps).
            if SEW.Maps then SEW.Maps.crate(c, x, y) end
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

--- One of the dead at x, y. `fx, fy`: the square it is turned to -- the
--- temple's stand round their slab, facing it (tools/gen_temple.py).
--- Returns how many were made; false, "near" when a player is too close.
function B.spawn(x, y, outfit, fx, fy)
    if nearAPlayer(x, y, C.SpawnClearance) then return false, "near" end
    local list = U.try("addZombiesInOutfit", function()
        return addZombiesInOutfit(x, y, B.Z, 1, outfit, 50, false, false, false, false, false, false, 1.0)
    end)
    local n = list ~= nil and U.try("zombies.size", function() return list:size() end) or false
    if fx and fy and n and n > 0 then
        U.try("zombie.face", function() list:get(0):faceLocation(fx + 0.5, fy + 0.5) end)
    end
    return n
end

--- One of a set piece's dead (the temple's, the dens'): put down now, or
--- owed if a player is standing too near. The tunnels' own dead are simply
--- not put down beside a player; these are the point of the place, and a
--- hall found empty because somebody arrived through its trapdoor is not it.
function B.setPiece(key, z)
    local n, why = B.spawn(z[1], z[2], B.dress(z[3], z[1], z[2]), z[4], z[5])
    if why == "near" then
        local s = B.state()
        s.owed[key] = s.owed[key] or {}
        table.insert(s.owed[key], { z[1], z[2], z[3], z[4], z[5] })
    end
    return n
end

--- Puts down whoever is owed, in loaded chunks, now that nobody is near.
--- Returns how many were.
function B.settle()
    local s = B.state()
    local made, done = 0, {}
    for key, list in pairs(s.owed) do
        local cx, cy = key:match("^(-?%d+),(-?%d+)$")
        if U.chunkLoaded(tonumber(cx) * 8 + 4, tonumber(cy) * 8 + 4) then
            local left = {}
            for _, z in ipairs(list) do
                local n, why = B.spawn(z[1], z[2], B.dress(z[3], z[1], z[2]), z[4], z[5])
                if why == "near" then left[#left + 1] = z elseif n then made = made + 1 end
            end
            if #left == 0 then done[#done + 1] = key else s.owed[key] = left end
        end
    end
    for _, key in ipairs(done) do s.owed[key] = nil end
    return made
end

--- A Sewars sandbox option, 1..n; `default` when the save has none (a world
--- made before the option existed) or it is out of range.
function B.option(name, default, n)
    local v = SandboxVars and SandboxVars.Sewars and SandboxVars.Sewars[name]
    v = tonumber(v)
    if not v or v < 1 or v > n then return default end
    return math.floor(v)
end

function B.density()
    return C.Density[B.option("Zombies", 3, #C.Density)]
end

local EQUIPPED = {}
for _, o in ipairs(C.OutfitsEquipped) do EQUIPPED[o] = true end

--- What one of the tunnels' dead at x, y wore: equipped (a bag, packed by
--- vanilla) by the sandbox's share, else an ordinary outfit.
function B.outfit(x, y, k)
    local roll = U.rng(U.hash(x, y, k))
    local mix = B.option("Outfits", 2, #C.EquippedShare)
    if roll(100) <= C.EquippedShare[mix] * 100 then return C.OutfitsEquipped[roll(#C.OutfitsEquipped)] end
    return C.Outfits[roll(#C.Outfits)]
end

--- A shelter's or hideout's own dead, named by the generator: one named
--- equipped keeps the pack by the sandbox's share, or is dressed ordinary.
function B.dress(outfit, x, y)
    if not EQUIPPED[outfit] then return outfit end
    local roll = U.rng(U.hash(x, y, 41))
    if roll(100) <= C.EquippedKeep[B.option("Outfits", 2, #C.EquippedKeep)] * 100 then return outfit end
    return C.Outfits[roll(#C.Outfits)]
end

---------------------------------------------------------------------------
-- A chunk
---------------------------------------------------------------------------
--- A house with a way down (ROADMAP 0.4). The generator ran a culvert a few
--- squares under this house to a hatch in its floor, but B42 stamps random
--- basements under houses when a world is made, and only the game knows which
--- got one. So the house is looked at here, once, when all of it is loaded:
--- nothing but ours (or nothing) under it, and the trapdoor goes into its
--- floor; a basement, and it stays shut for good. Returns "open", "blocked",
--- or nil when it cannot tell yet (not loaded: DEV_GUIDE, "Never build where
--- no player is standing").
function B.hatch(shaft)
    if not shaft or not shaft.hatch then return nil end
    local s = B.state()
    local key = shaft.x .. "," .. shaft.y
    if s.hatches[key] then return s.hatches[key] end
    local under = shaft.under or {}
    if not U.chunkLoaded(shaft.x, shaft.y) then return nil end
    for i = 1, #under, 2 do
        if not U.chunkLoaded(under[i], under[i + 1]) then return nil end
    end
    local top = U.square(shaft.x, shaft.y, 0, false)
    if not top or not U.floorOf(top) then return nil end
    for i = 1, #under, 2 do
        local sq = U.square(under[i], under[i + 1], B.Z, false)
        if sq and foreign(sq) then
            s.hatches[key] = "blocked"
            U.log("hatch at %d,%d (%s, %s): something is under the house already; left shut",
                  shaft.x, shaft.y, shaft.town, shaft.hatch)
            return "blocked"
        end
    end
    if not put(top, C.Sprites.hatch) and not U.findSprite(top, C.Sprites.hatch) then return nil end
    s.hatches[key] = "open"
    U.log("hatch at %d,%d (%s, %s): opened", shaft.x, shaft.y, shaft.town, shaft.hatch)
    return "open"
end

--- A cover of ours (ROADMAP 0.4: the towns the map gives few), or an
--- outfall's grate in a riverbank (DESIGN.md 7c). Put in the first time its
--- square is loaded with a floor there; recorded, so a player who lifts it
--- away is not given another. Returns "placed", or nil when it cannot tell yet.
function B.cover(shaft)
    if not shaft or not shaft.made then return nil end
    local s = B.state()
    local key = shaft.x .. "," .. shaft.y
    if s.covers[key] then return s.covers[key] end
    if not U.chunkLoaded(shaft.x, shaft.y) then return nil end
    local top = U.square(shaft.x, shaft.y, 0, false)
    if not top or not U.floorOf(top) then return nil end
    -- The temple's way out is a trapdoor in a field: a house's hatch, with no house.
    local sprite = shaft.outfall and C.Sprites.outfall or shaft.trapdoor and C.Sprites.hatch or C.Sprites.cover
    if not U.findSprite(top, sprite) and not put(top, sprite) then return nil end
    s.covers[key] = "placed"
    U.debug("cover at %d,%d (%s) placed", shaft.x, shaft.y, shaft.town)
    return "placed"
end

--- True when a chunk's records hold any of a cave: its earth floor, or a
--- breach in a tunnel wall.
function B.hasCave(body)
    for i = 1, #body, 7 do
        local f, n, w = body:sub(i + 2, i + 2), body:sub(i + 3, i + 3), body:sub(i + 4, i + 4)
        if DUG[f] or BREACH[n] or BREACH[w] or GATE[n] or GATE[w] then return true end
    end
    return false
end

--- Builds chunk `key` ("cx,cy") if it is loaded. Returns true when it is now
--- current; false when it must be tried again (not loaded).
function B.chunk(key)
    local tid = B.townOf(key)
    if not tid then
        -- No town's chunk -- but players may have dug into it (SEW_Mine): what
        -- they dug is all there is here, and a pass puts back any of it missing.
        local dug = B.state().dug[key]
        if not dug then return true end
        local kx, ky = key:match("^(-?%d+),(-?%d+)$")
        if not U.chunkLoaded(tonumber(kx) * 8 + 4, tonumber(ky) * 8 + 4) then return false end
        for k, rec in pairs(dug) do
            local x, y = k:match("^(-?%d+),(-?%d+)$")
            if B.square(tonumber(x), tonumber(y), rec, false, false) == "unloaded" then return false end
        end
        B.state().built[key] = B.rev()
        return true
    end
    local T = SEW.Data[tid]
    local body = T.chunks[key]
    local cx, cy = key:match("^(-?%d+),(-?%d+)$")
    cx, cy = tonumber(cx), tonumber(cy)
    if not U.chunkLoaded(cx * 8 + 4, cy * 8 + 4) then return false end

    local s = B.state()
    local first = s.first[key] == nil
    -- Caves not yet dug here: a chunk with cave in it whose caves are not done.
    local caves = s.caves[key] == nil and B.hasCave(body)
    local built, skipped, open, nest, runs = 0, 0, {}, 0, {}
    -- What players have dug here is read in place of the generator's record.
    local over, seen = s.dug[key], nil
    for i = 1, #body, 7 do
        local rec = body:sub(i, i + 6)
        local x, y = cx * 8 + tonumber(rec:sub(1, 1)), cy * 8 + tonumber(rec:sub(2, 2))
        if over then
            seen = seen or {}
            seen[x .. "," .. y] = true
            rec = over[x .. "," .. y] or rec
        end
        local how = B.square(x, y, rec, first, caves)
        if how == "unloaded" then return false end
        if how == "foreign" then
            skipped = skipped + 1
        else
            built = built + 1
            local f = rec:sub(3, 3)
            if f == "t" or f == "k" or f == "m" then open[#open + 1] = { x, y } end
            -- Where the rats run: the walkway, and the cult's passages and hall --
            -- they were let go where they liked. None of the tunnels' dead there.
            if f == "t" or f == "k" or f == "m" or f == "p" or f == "h" then runs[#runs + 1] = { x, y } end
            if f == "n" then nest = nest + 1 end
        end
    end
    -- And the squares they dug that the generator never had.
    if over then
        for k, rec in pairs(over) do
            if not (seen and seen[k]) then
                local x, y = k:match("^(-?%d+),(-?%d+)$")
                if B.square(tonumber(x), tonumber(y), rec, false, false) == "unloaded" then return false end
            end
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
                B.spawn(p[1], p[2], B.outfit(p[1], p[2], k))
            end
        end
        -- A shelter's own dead; the temple's are a set piece, and owed if a player is too near.
        local piece = SEW.Index.temple ~= nil and SEW.Index.temple.town == tid
        for _, z in ipairs(T.claimed[key] or {}) do
            if piece then B.setPiece(key, z) else B.spawn(z[1], z[2], B.dress(z[3], z[1], z[2]), z[4], z[5]) end
        end
        -- The town's maintenance key, in the unlocked county rooms' crates
        -- (DESIGN.md 7, Locked gates): once, with the rest of the stocking.
        if SEW.Keys then
            for _, k in ipairs(T.keys and T.keys[key] or {}) do U.try("key", SEW.Keys.stock, k[1], k[2], tid) end
        end
        -- And the rats, vanilla's own, on the walkway (SEW_Nest).
        if SEW.Nest then U.try("rats", SEW.Nest.rats, runs, cx, cy) end
        s.first[key] = B.rev()
    end
    -- The hideouts' furniture and their dead, once, first build or not.
    if caves then
        local seed = U.hash(cx, cy, 29)
        for _, e in ipairs(T.caveFurniture and T.caveFurniture[key] or {}) do B.furnish(e, seed) end
        for _, z in ipairs(T.caveClaimed and T.caveClaimed[key] or {}) do B.spawn(z[1], z[2], B.dress(z[3], z[1], z[2])) end
        -- The rodents of unusual size, where the nest is in this chunk.
        if nest > 0 and SEW.Nest then U.try("rous", SEW.Nest.lairChunk, key) end
        s.caves[key] = B.rev()
    end
    -- Sewer gas: the haze on its floor and the placards at its ways in, once
    -- (SEW_Gas). Not while the sandbox has it off: a server that turns it on
    -- later gets them then.
    if s.gas[key] == nil and SEW.Gas and SEW.Gas.strength() > 1 and SEW.Gas.inChunk(key) then
        U.try("gas", SEW.Gas.dress, key)
        s.gas[key] = B.rev()
    end
    -- The warren's dens (0.6): what the rats dragged there and who came after
    -- it, once. Stocked like the hoard where the generator says so.
    if s.warren[key] == nil and T.warren and (T.warren[key] or T.warrenDead[key]) then
        local seed = U.hash(cx, cy, 43)
        for _, e in ipairs(T.warren[key] or {}) do B.furnish(e, seed) end
        for _, z in ipairs(T.warrenDead[key] or {}) do B.setPiece(key, z) end
        s.warren[key] = B.rev()
    end
    -- The cult's pictures: on the wall of their square, once.
    if s.hung[key] == nil and T.pictures and T.pictures[key] then
        for _, e in ipairs(T.pictures[key]) do
            local sq = U.square(e[1], e[2], B.Z, false)
            if sq then hang(sq, e[3]) end
        end
        s.hung[key] = B.rev()
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
            if (B.townOf(key) or B.state().dug[key]) and not B.isCurrent(key) then
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
