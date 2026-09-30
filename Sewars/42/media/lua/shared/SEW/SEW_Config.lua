--[[ Sewars -- every constant the mod uses. Start here.

    shared/: loaded by single player, every client and every server. No guard,
    and nothing in here touches the world (DEV_GUIDE.md, "The server owns the
    sewers; a client asks").
]]

SEW = SEW or {}
SEW.Config = SEW.Config or {}
local C = SEW.Config

C.Version = "0.3.2"
C.ModPrefix = "[SEW]"
C.Debug = false

-- Bump when what the builder puts on a square changes, so every stretch
-- already built is revisited once and has its missing hull put back. The
-- layout's own revision (SEW.Index.rev, from tools/gen_sewers.py) is folded
-- in, so regenerating the tunnels does the same by itself.
C.BuildRev = 5   -- 2: the sludge swapped for our floor-level tile; 3: caves;
                 -- 4: earth and breaches laid over vanilla walls (their depth);
                 -- 5: pictures on walls attached to them, cut away with them

-- The tunnels' level: one storey under the street. FBORenderCell.renderInternal
-- (bci 400-428) draws nothing above ceil(z) + 1 for a camera player below zero,
-- so from down here the town above is simply not drawn (DESIGN.md 3).
C.Z = -1

-- The way in: the round cast-iron cover vanilla paints on its streets. Checked
-- by eye on design/art/vanilla_street_tiles.png and counted on the real map by
-- tools/pzmap.py (446 on the map). 13, 14, 30 and 31 are kerb storm drains.
C.ManholeSprite = "street_decoration_01_15"

-- How far a player may stand from a cover or a ladder and still use it. The
-- right-click lands on the floor square under the cursor, not on the picture
-- (pz_trekship DEV_GUIDE, "A right-click lands on the floor"), so a margin.
C.Reach = 1.6
-- How far from the square that was clicked the menu looks for a cover or a shaft.
C.ClickSlack = 1

-- Timed actions, in ticks.
C.LiftTicks = 110          -- prising the cover up and climbing down
C.LiftTicksCrowbar = 60    -- with a crowbar or a pipe wrench in the inventory
C.ClimbTicks = 80          -- climbing the ladder and shouldering the cover up
C.HatchTicks = 50          -- a trapdoor in a house's floor: no lid to prise up

-- Houses with a way down: the server looks at a hatch's house when a player
-- on the street comes this close, and opens the hatch only if nothing is
-- below it (B42 stamps random basements under houses: SEW_Server).
C.HatchRange = 40
C.LiftTools = { "Base.Crowbar", "Base.PipeWrench" }

-- Tag in every placed object's mod data. A rebuild keeps anything carrying
-- it and never touches anything that does not -- which, down here, is the
-- player's (pz_trekship BUILDING.md).
C.Tag = "sew"

-- Server mod data: which chunks are built at which revision. Never
-- transmitted: it is a list that grows with every chunk anybody walks into
-- (pz_trekship DEV_GUIDE, "State that is transmitted whole cannot hold a
-- list that grows").
C.StateKey = "SewarsBuilt"

-- Server mod data: what each player has found below, by username (the sewer
-- map's memory; SEW_Discovery.lua). Never transmitted whole.
C.SeenKey = "SewarsSeen"

-- Building round players below ground: this many chunks each way, and at
-- most this many chunks built per tick.
C.BuildRadiusChunks = 5
C.BuildChunksPerTick = 2
C.BuildEveryTicks = 15
-- On the way down, the stretch under the cover is built before the move is
-- granted, this many chunks each way.
C.EntryRadiusChunks = 2

-- No zombie is put down within this many squares of a player.
C.SpawnClearance = 12

-- The client's wait for the floor to reach it before it climbs down, in ticks.
C.ArriveTimeout = 600

-- Sprites. Vanilla's are checked against tools/_catalog/tiles.json by
-- tests/test_assets.py; ours are sewars_01, drawn by tools/gen_sewer_art.py.
C.Sprites = {
    floorTunnel  = "floors_interior_tilesandwood_01_24",
    floorVault   = "floors_interior_tilesandwood_01_30",
    floorShelter = "floors_interior_tilesandwood_01_31",
    -- Under the walls outside the tunnel: dark earth, not a tiled floor that
    -- would show as a strip round every tunnel (seen on the first render).
    floorRock    = "floors_burnt_01_0",
    grating      = { "location_sewer_01_40", "location_sewer_01_41", "location_sewer_01_42" },
    -- Vanilla's picture lowered onto the floor; vanilla's own tile draws its
    -- water two thirds of a storey up and floated over the walkway (0.3.2).
    sludge       = "sewars_01_26",
    sludgeOld    = "location_sewer_01_26",
    wall = {
        c = { N = "location_sewer_01_9", W = "location_sewer_01_8", NW = "location_sewer_01_10",
              pillar = "location_sewer_01_11" },
        b = { N = "location_sewer_01_1", W = "location_sewer_01_0", NW = "location_sewer_01_2",
              pillar = "location_sewer_01_3" },
        -- A cave's dug earth: vanilla's concrete wall (its collision and its
        -- depth), with our earth face laid over it (earthFace). A wall tile of
        -- our own would have no depth texture and be drawn over characters.
        e = { N = "location_sewer_01_9", W = "location_sewer_01_8", NW = "location_sewer_01_10" },
    },
    earthFace = { N = "sewars_01_28", W = "sewars_01_27" },
    -- A tunnel wall knocked through into a cave: vanilla's door frame (walked
    -- through), with the broken wall laid over it -- o concrete, q brick.
    breach = {
        o = { N = "sewars_01_31", W = "sewars_01_30" },
        q = { N = "sewars_01_33", W = "sewars_01_32" },
    },
    -- A cave's floor: vanilla's dark dirt, two shades by position.
    floorCave = { "floors_exterior_natural_01_20", "floors_exterior_natural_01_21" },
    -- A trapdoor in a house's floor, over a ladder down (ours).
    hatch = "sewars_01_34",
    -- A manhole cover of ours, in the towns the map gives few (vanilla's
    -- picture as a floor tile: SEW_Build.cover).
    cover = "sewars_01_35",
    -- Loose stones: rubble at a breach, and what came down from a cave's roof.
    -- Vanilla's ground stones (CustomName Stone2 / LargeStone, nothing that
    -- blocks). Not boulders_36..39: those names have no picture in the packs,
    -- and 56..63 are floors of their own.
    stones = { "boulders_48", "boulders_49", "boulders_50", "boulders_51",
               "boulders_52", "boulders_53", "boulders_54", "boulders_55" },
    -- Plain runs of wall pick from these by a hash of the square, so a
    -- corridor is not one panel repeated (the first render). Same edge flags
    -- and material as the plain piece; the plain one is listed most.
    wallVariants = {
        c = { N = { "location_sewer_01_9", "location_sewer_01_9", "location_sewer_01_13", "location_sewer_01_15" },
              W = { "location_sewer_01_8", "location_sewer_01_8", "location_sewer_01_12", "location_sewer_01_14" } },
        b = { N = { "location_sewer_01_1", "location_sewer_01_1", "location_sewer_01_5", "location_sewer_01_7" },
              W = { "location_sewer_01_0", "location_sewer_01_0", "location_sewer_01_4", "location_sewer_01_6" } },
    },
    doorFrame    = { N = "location_sewer_01_19", W = "location_sewer_01_18" },
    door         = { N = "fixtures_doors_01_25", W = "fixtures_doors_01_24" },
    pipes        = { "location_sewer_01_34", "location_sewer_01_35",
                     "location_sewer_01_36", "location_sewer_01_37" },
    ladder       = { N = "sewars_01_1", W = "sewars_01_0" },
    exit         = { N = "sewars_01_3", W = "sewars_01_2" },
    graffiti     = {
        a = { N = "sewars_01_5",  W = "sewars_01_4" },    -- KEEP OUT
        b = { N = "sewars_01_7",  W = "sewars_01_6" },    -- THEY HEAR YOU
        c = { N = "sewars_01_9",  W = "sewars_01_8" },    -- DONT GO DEEPER
        d = { N = "sewars_01_11", W = "sewars_01_10" },   -- tally, DAY 31
        e = { N = "sewars_01_13", W = "sewars_01_12" },   -- hand prints
        f = { N = "sewars_01_15", W = "sewars_01_14" },   -- UP
        g = { N = "sewars_01_17", W = "sewars_01_16" },   -- the eye
    },
    safe         = { N = "sewars_01_19", W = "sewars_01_18" },
    grime        = { N = "sewars_01_21", W = "sewars_01_20" },
    puddle       = "sewars_01_22",
    debris       = "sewars_01_23",
    lightpool    = "sewars_01_24",
    smear        = "sewars_01_25",
    -- The rats' nest (0.5): the false wall's cracks and gnawed hole, claw
    -- marks, bones and litter, and the warning by the false wall.
    cracks       = { N = "sewars_01_37", W = "sewars_01_36" },
    claws        = { N = "sewars_01_39", W = "sewars_01_38" },
    bones        = "sewars_01_40",
    litter       = "sewars_01_41",
    rousWarning  = { N = "sewars_01_43", W = "sewars_01_42" },
}

-- What the dead down here wore when they came down. Every name is in both
-- the male and female lists of vanilla's clothing.xml (checked by
-- tests/test_assets.py): addZombiesInOutfit picks a sex first. Most were the
-- town's own -- sewer and utility workers, the homeless, people who ran
-- underground in what they had on -- and none of these carries a bag.
C.Outfits = { "Sanitation", "Sanitation", "Hobbo", "Hobbo", "HazardSuit", "Grunge", "Resident",
              "Fossoil", "Redneck", "Trucker", "Generic01", "Generic02", "Generic03",
              "Generic04", "Generic05" }
-- Some came down equipped, and vanilla packs their bags for them. Until 0.3.2
-- four of the eleven outfits were these, and two of every three shelter dead
-- (a player's report: "they all carry something").
C.OutfitsEquipped = { "Survivalist", "Camper", "Evacuee", "Bandit" }
-- By the sandbox's Sewars.Outfits (Mostly ordinary / Mixed / Survivors): the
-- share of the tunnels' dead who are equipped, and the share of a shelter's or
-- hideout's own dead (tools/gen_sewers.py names theirs) who keep their pack --
-- the rest are dressed from C.Outfits. Survivors is 0.3.1's balance.
C.EquippedShare = { 0.05, 0.15, 0.36 }
C.EquippedKeep  = { 0.25, 0.5, 1.0 }

-- Zombies per hundred squares of new tunnel, by the sandbox's density.
C.Density = { 0, 0.6, 1.4, 2.6 }

-- Shelter loot, by the list the generator names (tools/gen_sewers.py
-- FURNITURE). Every id is checked against the build by tests/test_assets.py.
C.Loot = {
    tools    = { "Base.Hammer", "Base.Screwdriver", "Base.Wrench", "Base.PipeWrench", "Base.Crowbar",
                 "Base.Saw", "Base.DuctTape", "Base.Rope", "Base.HandTorch", "Base.Battery" },
    hardware = { "Base.NailsBox", "Base.ScrewsBox", "Base.Wire", "Base.MetalPipe", "Base.SmallSheetMetal",
                 "Base.DuctTape", "Base.Garbagebag", "Base.Tarp" },
    mechanic = { "Base.Wrench", "Base.EngineParts", "Base.ElectronicsScrap", "Base.WeldingRods",
                 "Base.BlowTorch", "Base.Battery", "Base.Wire" },
    fuel     = { "Base.PetrolCan", "Base.JerryCan", "Base.Matches", "Base.Lighter" },
    food     = { "Base.TinnedBeans", "Base.TinnedSoup", "Base.CannedCorn", "Base.CannedChili",
                 "Base.CannedTomato2", "Base.TinOpener", "Base.WaterBottle", "Base.Crisps" },
    survival = { "Base.Candle", "Base.Matches", "Base.Lighter", "Base.Sheet", "Base.Pillow",
                 "Base.WaterPurificationTablets", "Base.Notebook", "Base.Pencil", "Base.HandTorch" },
    -- Mostly what a last stand is fought with: a gun is one pick in eleven.
    arms     = { "Base.BaseballBat", "Base.BaseballBat", "Base.Machete", "Base.Axe", "Base.Crowbar",
                 "Base.Pistol", "Base.Bullets9mmBox", "Base.Revolver", "Base.Bullets38Box",
                 "Base.Shotgun", "Base.ShotgunShellsBox" },
    medical  = { "Base.Bandage", "Base.Disinfectant", "Base.Pills", "Base.AlcoholWipes",
                 "Base.Splint", "Base.SutureNeedle", "Base.Antibiotics" },
}
-- The rats' hoard under Louisville (0.5): what they sat on, and what whoever
-- walled the room up long before them left there. Stocked with C.HoardCount
-- picks, whatever the sandbox's supplies -- it is the one place worth the fight.
C.Loot.hoardArms = { "Base.AssaultRifle", "Base.HuntingRifle", "Base.Shotgun", "Base.Pistol3",
                     "Base.Katana", "Base.Machete", "Base.Sledgehammer" }
C.Loot.hoardAmmo = { "Base.556Box", "Base.308Box", "Base.ShotgunShellsBox", "Base.Bullets45Box",
                     "Base.556Clip", "Base.45Clip", "Base.GoldCoin" }
C.Loot.hoardMedical = { "Base.FirstAidKit", "Base.Antibiotics", "Base.Antibiotics", "Base.Bandage",
                        "Base.Disinfectant", "Base.PillsBeta", "Base.PillsAntiDep", "Base.SutureNeedle",
                        "Base.Splint" }
C.Loot.hoardTools = { "Base.Toolbox", "Base.BlowTorch", "Base.PropaneTank", "Base.WeldingMask",
                      "Base.Sledgehammer", "Base.Crowbar", "Base.Generator" }
C.Loot.hoardFood = { "Base.TinnedBeans", "Base.CannedChili", "Base.CannedCorn", "Base.TinnedSoup",
                     "Base.Honey", "Base.WaterBottle", "Base.TinOpener", "Base.Peanuts" }
C.Loot.hoardSurvival = { "Base.HandTorch", "Base.Battery", "Base.Battery", "Base.Lighter",
                         "Base.WaterPurificationTablets", "Base.Bag_ALICEpack", "Base.Tarp", "Base.Rope" }
C.Loot.hoardValuables = { "Base.GoldBar", "Base.GoldBar", "Base.SilverBar", "Base.Money", "Base.Money",
                          "Base.Diamond", "Base.Ring_Right_RingFinger_Gold", "Base.WristWatch_Right_ClassicGold" }
C.HoardCount = { 5, 9 }

-- How many picks a crate or shelf is stocked with (U.fill), fewest and most,
-- by the sandbox's Sewars.Loot (None / Scarce / Normal / Plenty); never past
-- this share of its capacity by weight. Journals and plans go in whatever
-- this is (SEW_Build.furnish).
C.LootCount = { { 0, 0 }, { 1, 2 }, { 2, 4 }, { 4, 7 } }
C.FillFraction = 0.45

-- Light down here, for addLamppost: r, g, b, radius. The engine lights a
-- lamppost on the client that made it only, so each client hangs its own.
C.ShaftLightDay   = { 0.55, 0.60, 0.68, 4 }
C.ShaftLightNight = { 0.16, 0.18, 0.26, 3 }
C.ShelterLight    = { 0.85, 0.55, 0.28, 5 }
-- A cave's hideout: somebody's last candle.
C.CaveLight       = { 0.70, 0.42, 0.18, 4 }
C.LightRange = 34

-- The story's items (SEW_Story.lua, media/scripts/sewars_items.txt), and the
-- size of a plan's sheet -- the map's tile, 256 squares (tools/gen_sewers.py MAP_TILE).
C.PlanItem = "Sewars.SewerPlan"
C.JournalItem = "Sewars.SewerJournal"
C.MapTile = 256

-- The dev build's kit: given once per character, in single player, only when
-- SEW.Dev is set -- which only tools/deploy_windows.py does, by writing
-- shared/SEW/SEW_Dev.lua into the installed SewarsDev copy. The source tree and
-- the Workshop package never contain that file.
C.DevKit = { "Base.HandTorch", "Base.Battery", "Base.Battery", "Base.Crowbar" }
-- And where a new dev character starts (SEW_Client devStart): "lair", in the
-- house whose hatch is nearest the rats' nest under Louisville; "cave", on
-- the cover nearest a cave in C.DevStartTown. SEW_GoCave(n), SEW_GoHatch(n)
-- and SEW_GoLair() in the console hop to any of them.
C.DevStart = "lair"
C.DevStartTown = "muldraugh"

-- Rats (0.5): vanilla's own B42 rats, put down with a stretch of tunnel on
-- its first build, per hundred squares of walkway, by the sandbox's
-- Sewars.Rats (None / Few / Normal / Many). Once, like the dead: the engine
-- keeps them after that (saved with the chunk, synced by itself).
C.RatDensity = { 0, 0.5, 1.2, 2.5 }
C.RatTypes = { "rat", "rat", "ratfemale", "ratfemale", "ratfemale" }
C.RatBreeds = { "grey", "grey", "grey", "grey", "white" }

-- Rodents of unusual size (0.5), in the nest under Louisville only: an animal
-- of our own, `rous`, on vanilla's rat (SEW_Rats.lua). The engine cannot make
-- a rat bite, so the chase and the bite are the server's (SEW_Nest.hunt).
C.Rous = {
    type = "rous", breed = "grey",
    size = 2.8,                 -- vanilla's rat is 0.7..1.0
    healthLoss = 0.008,         -- how little a hit takes off it (a hen's is 0.1; a guess: SEW_Nest logs each hit)
    hunt = 16,                  -- squares: a player this close is hunted
    every = 30,                 -- ticks between looks for them round each player
    range = 60,                 -- squares from the nest searched for the living
    reach = 1.15,               -- squares: this close, it bites
    bite = 8,                   -- health off the bitten limb (and a scratch, or a cut)
    biteEvery = 120,            -- ticks between bites, each
    speed = 0.07,               -- squares a tick when walked by hand (a sprint outruns it)
}
-- Every so many ticks, an animal below ground found off the walkway is put
-- back on it (within this many squares) or taken away (SEW_Nest.leash).
C.LeashEvery = 120
C.LeashReach = 4
-- Pulling the false wall away, and tearing through the gnawed wall into the
-- hoard, in ticks (a crowbar or a sledgehammer: faster).
C.PryTicks = { wall = 160, gate = 220 }
C.PryTicksTool = { wall = 90, gate = 120 }
C.PryTools = { "Base.Crowbar", "Base.Sledgehammer", "Base.Sledgehammer2" }

-- Ambience: one sound every so many ticks while below, give or take.
C.AmbienceTicks = { 700, 1900 }
C.Ambience = { "SEW_Drip", "SEW_Drip", "SEW_Drip", "AnimalRatScuttleWall", "SEW_Groan" }

return C
