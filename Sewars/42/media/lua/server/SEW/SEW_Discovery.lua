--[[ Sewars -- what each player has found below: the sewer map's memory.

    The map (ROADMAP 0.3) starts black and fills in as a player walks. What
    they have found is kept here, **on the server, per username**:

        c  chunks walked ("cx,cy")          -- the fog lifts chunk by chunk
        s  shelters entered (index in SEW.Index.shelters)
        l  ladders used ("x,y" of the cover)
        m  marks given by journals and plans (id -> { x, y, kind })
        g  stretches of sewer gas walked into, or read of on a plan (index
           in SEW.Index.gas)

    It is server mod data (C.SeenKey) and **never transmitted whole**: it grows
    with every chunk anybody walks (DEV_GUIDE, "State that is transmitted whole
    cannot hold a list that grows"). Each client is sent its own player's record
    when it asks (`mapState`), and one small message per new find after that.
    A client never writes it: it is what the server saw the player do.

    Player mod data would have been the obvious home, and is exactly the trap
    pz_trekship documents: a client's write to its own player never reaches the
    server's copy. Kept by name here, it survives the character's own save
    being lost too -- which, for a map, is the right way round.
]]

if isClient() then return end

require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Net"
require "SEW/SEW_Sewer"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local Net = SEW.Net
local S = SEW.Sewer

local D = {}
SEW.Discovery = D

function D.nameOf(p)
    return U.try("username", function() return p:getUsername() end) or "player"
end

function D.record(p)
    local all = ModData.getOrCreate(C.SeenKey)
    local name = D.nameOf(p)
    local r = all[name]
    if not r then
        r = { c = {}, s = {}, l = {}, m = {}, g = {} }
        all[name] = r
    end
    r.g = r.g or {}
    return r
end

local function tell(p, what, value)
    Net.toClient(p, "found", { what = what, value = value })
end

--- The chunk under the player, and the shelter they are in, if new.
--- Returns how many new things were found (for the tests and the log).
function D.look(p)
    local px = U.try("px", function() return p:getX() end)
    local py = U.try("py", function() return p:getY() end)
    if not px or not py then return 0 end
    local r = D.record(p)
    local n = 0
    local key = math.floor(px / 8) .. "," .. math.floor(py / 8)
    if not r.c[key] and SEW.Build and SEW.Build.townOf(key) then
        r.c[key] = 1
        tell(p, "c", key)
        n = n + 1
    end
    local i = S.shelterAt(px, py)
    if i and not r.s[i] then
        r.s[i] = 1
        tell(p, "s", i)
        U.log("%s found a shelter (%s) at %d,%d", D.nameOf(p), SEW.Index.shelters[i].kind, px, py)
        n = n + 1
    end
    return n
end

function D.ladder(p, x, y)
    local r = D.record(p)
    local key = math.floor(x) .. "," .. math.floor(y)
    if r.l[key] then return false end
    r.l[key] = 1
    tell(p, "l", key)
    return true
end

--- Reveals every chunk of a town inside a square region (a plan's district).
function D.reveal(p, town, x0, y0, x1, y1)
    local T = SEW.Index.towns[town]
    if not T then return 0 end
    local r = D.record(p)
    local new = {}
    for cx = math.floor(x0 / 8), math.floor(x1 / 8) do
        for cy = math.floor(y0 / 8), math.floor(y1 / 8) do
            local key = cx .. "," .. cy
            if not r.c[key] and SEW.Build and SEW.Build.townOf(key) == town then
                r.c[key] = 1
                new[#new + 1] = key
            end
        end
    end
    if #new > 0 then Net.toClient(p, "revealed", { keys = new }) end
    return #new
end

--- A stretch of sewer gas on the player's map (index in SEW.Index.gas).
function D.gas(p, i)
    local r = D.record(p)
    if not i or r.g[i] then return false end
    r.g[i] = 1
    tell(p, "g", i)
    return true
end

--- A mark on the player's map, from a journal: id is stable per journal.
function D.mark(p, id, x, y, kind)
    local r = D.record(p)
    if r.m[id] then return false end
    r.m[id] = { x = x, y = y, kind = kind }
    Net.toClient(p, "found", { what = "m", value = id, x = x, y = y, kind = kind })
    return true
end

Net.onServer("mapState", function(p)
    local r = D.record(p)
    local c, s, l, g = {}, {}, {}, {}
    for k in pairs(r.c) do c[#c + 1] = k end
    for k in pairs(r.s) do s[#s + 1] = k end
    for k in pairs(r.l) do l[#l + 1] = k end
    for k in pairs(r.g) do g[#g + 1] = k end
    Net.toClient(p, "mapState", { c = c, s = s, l = l, m = r.m, g = g })
end)

return D
