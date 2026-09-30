--[[ Sewars -- the timed action that takes you down a manhole and back up.

    **Shared, and a global, on purpose** (pz_trekship DEV_GUIDE, "A timed
    action is rebuilt on the server by its name and its parameters"). In
    build 42 a client does not run a Lua timed action by itself: the server
    rebuilds it by looking its **global class name** up and calling `new` with
    arguments read off the action **by the parameter names of `new`**. So
    `new(character, x, y, mode)` stores each one under exactly that name.

    Where each half runs:
      * start, update, stop: wherever the action is -- the crouch and the
        scrape of the lid;
      * perform: the client (and single player) -- nothing but bookkeeping;
      * complete: **never on a client** -- the server (or single player). It
        is the request: SEW.Server.grant checks the climber on its own copy,
        builds the tunnel under the cover if it is not built, and tells the
        climber's client to move (SEW_Client, "go"). A client moves only its
        own character.

    mode is "down" (at a cover in the street; x, y the cover) or "up" (at a
    ladder below; x, y the square under the cover the ladder leads to).
]]

require "TimedActions/ISBaseTimedAction"
require "SEW/SEW_Config"
require "SEW/SEW_Util"
require "SEW/SEW_Sewer"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util
local S = SEW.Sewer

SEWClimb = ISBaseTimedAction:derive("SEWClimb")

function SEWClimb:new(character, x, y, mode)
    local o = ISBaseTimedAction.new(self, character)
    o.character = character
    o.x = x
    o.y = y
    o.mode = mode
    o.stopOnWalk = true
    o.stopOnRun = true
    local ticks = C.ClimbTicks
    local shaft = S.shaftAt(x, y)
    o.hatch = shaft ~= nil and shaft.hatch ~= nil
    if mode == "down" and o.hatch then
        ticks = C.HatchTicks
    elseif mode == "down" then
        ticks = S.hasLiftTool(character) and C.LiftTicksCrowbar or C.LiftTicks
    end
    o.maxTime = U.try("instant", function() return character:isTimedActionInstant() end) and 1 or ticks
    return o
end

function SEWClimb:isValid()
    if self.mode == "down" then
        return not S.below(self.character) and S.shaftAt(self.x, self.y) ~= nil
            and S.within(self.character, self.x, self.y, C.Reach + 0.8)
    elseif self.mode == "up" then
        local s = S.shaftAt(self.x, self.y)
        return s ~= nil and S.below(self.character)
            and (S.within(self.character, s.x, s.y, C.Reach + 0.8) or S.within(self.character, s.lx, s.ly, C.Reach + 0.8))
    end
    return false
end

function SEWClimb:waitToStart()
    U.try("face", function() self.character:faceLocation(self.x + 0.5, self.y + 0.5) end)
    return false
end

function SEWClimb:start()
    self:setActionAnim("Loot")
    U.try("lootLow", function()
        self.character:SetVariable("LootPosition", self.mode == "down" and "Low" or "High")
    end)
    if not isServer() then
        self.sound = U.try("sound", function()
            -- A trapdoor has no iron lid to scrape.
            return self.character:playSound((self.mode == "down" and not self.hatch) and "SEW_Lid" or "SEW_Ladder")
        end)
    end
end

function SEWClimb:stop()
    ISBaseTimedAction.stop(self)
end

function SEWClimb:perform()
    ISBaseTimedAction.perform(self)
end

function SEWClimb:complete()
    if SEW.Server and SEW.Server.grant then
        U.try("grant", SEW.Server.grant, self.character, self.x, self.y, self.mode)
    else
        U.warnOnce("noServer", "SEWClimb completed where SEW.Server is not loaded")
    end
    return true
end

function SEWClimb:getDuration()
    return self.maxTime
end

---------------------------------------------------------------------------
-- SEWPry: pulling at one of the nest's walls (SEW_Nest.lua)
---------------------------------------------------------------------------
-- The same contract as SEWClimb, and global for the same reason: `new`'s
-- parameter names are what the server rebuilds it from. `which` is "wall"
-- (the false wall from the sewer) or "gate" (the gnawed wall into the hoard);
-- x, y the square the player aimed at, for facing.

SEWPry = ISBaseTimedAction:derive("SEWPry")

function SEWPry:new(character, x, y, which)
    local o = ISBaseTimedAction.new(self, character)
    o.character = character
    o.x = x
    o.y = y
    o.which = which
    o.stopOnWalk = true
    o.stopOnRun = true
    local set = S.hasPryTool(character) and C.PryTicksTool or C.PryTicks
    o.maxTime = U.try("instant", function() return character:isTimedActionInstant() end) and 1
        or set[which] or C.PryTicks.wall
    return o
end

function SEWPry:isValid()
    local ax, ay, bx, by = S.gateSquares(self.which)
    return ax ~= nil and S.below(self.character)
        and (S.within(self.character, ax, ay, C.Reach + 0.8) or S.within(self.character, bx, by, C.Reach + 0.8))
end

function SEWPry:waitToStart()
    U.try("face", function() self.character:faceLocation(self.x + 0.5, self.y + 0.5) end)
    return false
end

function SEWPry:start()
    self:setActionAnim("Loot")
    U.try("lootLow", function() self.character:SetVariable("LootPosition", "Low") end)
end

function SEWPry:stop()
    ISBaseTimedAction.stop(self)
end

function SEWPry:perform()
    ISBaseTimedAction.perform(self)
end

function SEWPry:complete()
    if SEW.Nest and SEW.Nest.pry then
        U.try("pry", SEW.Nest.pry, self.character, self.which)
    else
        U.warnOnce("noNest", "SEWPry completed where SEW.Nest is not loaded")
    end
    return true
end

function SEWPry:getDuration()
    return self.maxTime
end

return SEWClimb
