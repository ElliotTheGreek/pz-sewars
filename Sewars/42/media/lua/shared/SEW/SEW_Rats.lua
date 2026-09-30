--[[ Sewars -- the rodents of unusual size: an animal of our own, on vanilla's rat.

    shared/: every process needs the definition -- the server to spawn and
    run them, a client to draw them. No guard.

    Vanilla's animals are Lua tables the engine reads once, the first time it
    asks for one (AnimalDefinitions.getAnimalDefs -> loadAnimalDefinitions,
    first from IsoWorld.init, after every mod's Lua has loaded). So `rous` is
    one more entry in the same tables, copied from vanilla's `rat` the way
    vanilla copies its own (RatDefinitions.lua: copyTable), and changed where
    a ROUS is not a rat:

      * its size: the model is drawn at AnimalData.getSize() (ModelSlotRenderData),
        clamped to minSize..maxSize;
      * it stands its ground: not wild, never fleeing;
      * it moves as a rat: the rat's own animation set and action group.
        **Not one of ours**: a mod cannot add an action group
        (ActionGroup.load reads media/actiongroups from the game's folder
        only), and an animal with none has no states at all and stands still
        (found in play, 0.5). So it cannot bite by the engine either -- the
        rat's group has no attack state -- and the server hunts and bites
        with it (SEW_Nest.hunt). Nothing here asks the engine to attack;
      * it never starves, grows up or breeds, and cannot be picked up, petted
        or killed bare-handed;
      * butchered, it gives a good deal more than a rat.

    Nothing here runs if vanilla's rat is not there to copy (a future build);
    one WARN says so and the nest stays empty.
]]

require "SEW/SEW_Config"
require "SEW/SEW_Util"

SEW = SEW or {}
local C = SEW.Config
local U = SEW.Util

local R = {}
SEW.Rats = R

--- A deep enough copy of a definition table: vanilla's copyTable where the
--- game has it.
local function copy(t)
    if type(copyTable) == "function" then return copyTable(t) end
    local out = {}
    for k, v in pairs(t) do out[k] = type(v) == "table" and copy(v) or v end
    return out
end

function R.define()
    local AD = AnimalDefinitions
    local rat = AD and AD.animals and AD.animals.rat
    if not rat then
        U.log("WARN no vanilla rat to build the ROUS on (AnimalDefinitions.animals.rat); the nest stays empty")
        return false
    end
    local name, breed = C.Rous.type, C.Rous.breed
    local d = copy(rat)
    d.animset = "rat"
    d.minSize, d.maxSize = C.Rous.size, C.Rous.size
    d.minWeight, d.maxWeight = 8, 12
    d.wild = false
    d.alwaysFleeHumans = false
    d.attackDist = 0
    d.healthLossMultiplier = C.Rous.healthLoss
    d.hungerMultiplier, d.thirstMultiplier = 0, 0
    d.canBePicked, d.canBePet, d.canBeKilledWithoutWeapon = false, false, false
    d.collidable = true
    d.animalSize = 1
    d.corpseSize = 1
    d.wanderMul = 120
    d.dontAttackOtherMale = true
    d.mate, d.male, d.female, d.babyType, d.udder = nil, nil, nil, nil, nil
    d.maxAgeGeriatric = 100000
    d.minAge = 0
    -- One stage, which it never leaves.
    AD.stages = AD.stages or {}
    AD.stages[name] = { stages = {} }
    AD.stages[name].stages[name] = { ageToGrow = 100000 }
    d.stages = AD.stages[name].stages
    -- The rat's grey coat, and its sounds.
    local breeds = {}
    local src = rat.breeds and rat.breeds[breed]
    if src then breeds[breed] = copy(src) end
    d.breeds = breeds
    AD.breeds = AD.breeds or {}
    AD.breeds[name] = { breeds = breeds }
    AD.animals[name] = d

    -- The picture in the animal UI, as the rat's.
    if AnimalAvatarDefinition and AnimalAvatarDefinition.rat then
        AnimalAvatarDefinition[name] = copy(AnimalAvatarDefinition.rat)
    end
    -- Butchered (parts are keyed by type and breed).
    if AnimalPartsDefinitions and AnimalPartsDefinitions.animals then
        AnimalPartsDefinitions.animals[name .. breed] = {
            parts = { { item = "Base.DeadRatSkinned", nb = 4 } },
            bones = { { item = "Base.SmallAnimalBone", minNb = 3, maxNb = 6 } },
            noSkeleton = true,
            xpPerItem = 12,
        }
    end
    return true
end

R.defined = R.define()

return R
