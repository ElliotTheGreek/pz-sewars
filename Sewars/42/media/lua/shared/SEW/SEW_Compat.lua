--[[ Sewars -- below ground is indoors, for every mod that asks.

    The engine calls a tunnel square outdoors. A square is `exterior` unless
    it has a room or a roof (IsoGridSquare.RecalcProperties), and nothing
    below z 0 ever gets a roof: IsoCell.checkHaveRoof walks z 31 down to 0
    and stops. A runtime tunnel has no room either. And IsoPlayer.isOutside
    asks only "no room and not in a player-built room", so a player in the
    sewer is outside to anyone who asks -- Flying Birds flew its flocks over
    them, rain barrels and crops below would count as under the sky.

    There is no engine switch for it (haveRoof has no setter, and a room id
    without a room is worse than none; DEV_GUIDE, *Below ground is outdoors
    to the engine*). So the question is answered where every mod asks it:
    in the class tables Kahlua looks methods up in (KahluaThread
    getClassMetatable -> __classmetatables[class].__index, a plain table,
    chained to the superclass's). isOutside on a square, a player or any
    other character is wrapped: below z 0, the answer is no.

    Lua callers only -- other mods and vanilla Lua. The engine's own Java
    calls are untouched. Runs in every process, because a server-side mod
    asks too.
]]

require "SEW/SEW_Config"
require "SEW/SEW_Util"

SEW = SEW or {}
local U = SEW.Util

local P = {}
SEW.Compat = P

-- The classes whose isOutside is wrapped, by the name tostring gives the
-- Class key ("class zombie.iso.IsoGridSquare"). IsoGameCharacter covers
-- zombies and animals; IsoPlayer declares its own and is wrapped apart.
P.Classes = {
    "zombie.iso.IsoGridSquare",
    "zombie.characters.IsoGameCharacter",
    "zombie.characters.IsoPlayer",
}

-- Where the wrapper keeps the engine's own method, in the index table itself,
-- so a second load (a Lua reload) wraps the original and not the wrapper.
local ORIGINAL = "SEW_isOutsideEngine"

--- Nothing below the street is outside: squares at z -1 and deeper, and
--- anybody standing on one.
function P.below(obj)
    local z = obj:getZ()
    return z ~= nil and z < 0
end

local function wrap(index)
    local engine = rawget(index, ORIGINAL) or index.isOutside
    if not engine then return false end
    rawset(index, ORIGINAL, engine)
    rawset(index, "isOutside", function(self, ...)
        if P.below(self) then return false end
        return engine(self, ...)
    end)
    return true
end

--- Wrap isOutside in every class in P.Classes. Returns how many were wrapped.
function P.install()
    local metas = __classmetatables
    if type(metas) ~= "table" then
        U.log("compat: no class metatables; isOutside left as the engine has it")
        return 0
    end
    local want = {}
    for _, name in ipairs(P.Classes) do want["class " .. name] = name end
    local done, names = 0, {}
    for class, mt in pairs(metas) do
        local name = want[tostring(class)]
        local index = name and type(mt) == "table" and mt.__index
        if type(index) == "table" and wrap(index) then
            done = done + 1
            names[#names + 1] = name:match("[^.]+$")
        end
    end
    if done < #P.Classes then
        U.log("WARN compat: isOutside wrapped on %d of %d classes (%s)", done, #P.Classes, table.concat(names, ", "))
    else
        U.log("compat: below ground is indoors (%s)", table.concat(names, ", "))
    end
    P.wrapped = done
    return done
end

U.try("compat install", P.install)
