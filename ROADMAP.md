# Sewars roadmap

The plan, and where it has got to. Updated as work lands -- if this file and
the code disagree, the code is right and this file is stale; fix it.

**The theme, from the author (2026-09-28): story told through the map.** The
sewers are something you *learn*: a map of your own that starts black and
fills in as you walk, hideouts marked as you find them, and journals and plans
that point you somewhere new. Every feature below either gives the map
something to reveal or a reason to go and reveal it.

Status: `[x]` done and tested offline · `[~]` in progress · `[ ]` not started ·
**(game)** needs the author's play-test to be called done.

---

## 0.2 -- the sewers (done)

- [x] Tunnels under 16 towns from vanilla's street map: trunks, mains, culverts, brick vaults
- [x] Climb down any manhole / climb out any ladder, server-granted
- [x] Shelters behind steel doors, stocked once; the dead below
- [x] Our own tiles (26), sounds (4), poster
- [x] Local dev build: `tools/dev.py`, SewarsDev, test kit (torch, batteries, crowbar)
- [x] Tests: assets, layout walk, single-player + client/server flow, 17 mutations
- [x] **(game)** First play-test: "awesome it's great!" (2026-09-28)

## 0.3 -- the map (the spine of everything after) -- built, awaiting play-test

- [x] Engine research: custom panel drawing, texture limits (none below GPU), fog as merged rectangles
- [x] Per-town sewer map images, generated with the layout (`gen_sewers.py`, 256px tiles, media/ui/sewermap)
- [x] Discovery store: chunks walked, shelters entered, ladders used, journal marks -- server-owned, per username, one message per find (`SEW_Discovery.lua`)
- [x] The sewer map panel: pan, zoom, controller, fog of war by chunk as merged runs, cached per find (`SEW_Map.lua`)
- [x] Markers: ladders used (street names when zoomed in), shelters found (by kind), journal marks, you-are-here
- [x] Open it: *Sewer map* on the right-click menu below ground, and a key (rebindable, Options -> Mods; **K** since 0.3.2, N clashed with the engine)
- [x] **Municipal sewer plan** item: 46 placed in maintenance rooms and pump stations, each a substantial sheet of the town; reading one reveals it
- [ ] Plans (and gate keys) on sanitation-worker zombies -- `addItemToSpawnAtDeath` is lost if the zombie unloads; test on a server first
- [x] Tests: discovery SP + MP, panel draws clipped, fog lifts after new finds, plan reveals exactly its sheet, journals from both menu shapes; 24 mutations caught
- [ ] **(game)** the map opens, fills in, and is readable in the dark

## 0.3.1 -- fixes from the play-test (done, awaiting play-test)

- [x] Map and journal are vanilla windows: move by the title bar, resize, X and Escape close; B prompt only with a controller
- [x] Footer text no longer garbled (`%` beside a placeholder); "<1%" instead of "0%"
- [x] **Dead ends**: side streets stopped at the edge of the road they meet, short of its trunk. Loose ends now snap on to the next street (82 in Muldraugh alone), a gap-closer joins what is left, trunks get bridges where side tunnels meet them, and sludge channels run on straight stretches only. `test_layout.py` fails on any tunnel that stops just short of another
- [x] "UP" graffiti only within 12 squares of a ladder
- [x] Existing saves: a revision pass removes our own walls the new layout opened (never a player's)

## 0.3.2 -- dead ends under open road (built, awaiting play-test)

- [x] **Dead end on Harris St** (Muldraugh, found in play): the street list stops 49 squares short of Irma Dr where the painted road does not. A late pass now runs any 1-wide dead end on under painted road to the network (up to 80 squares), after the shelters are placed so none moves; 3 ends joined in Muldraugh. Shelters, ladders, furniture and journals unchanged; existing saves open the old end wall on the revision pass
- [x] `test_layout.py` fails on any tunnel that ends in a wall with the road running on to more tunnel (fails on the 0.3.1 layout, Harris St included)
- [ ] **(game)** Harris St east of its ladder runs through to Irma Dr
- [x] **Below ground is indoors to other mods** (a player's report: Flying Birds, Workshop 3789637851, flew flocks through the sewer). The engine calls every square below z 0 outdoors; `isOutside` on squares, players and other characters now answers no below ground for every Lua caller, any mod and vanilla's rain barrels, crops, campfires and foraging included (`SEW_Compat.lua`). Tested SP and MP, three mutations caught
- [ ] **(game)** with Flying Birds: flocks over the street, none below
- [x] **The sludge floated** (found in play): vanilla's `location_sewer_01_26` draws its water 128 px up the cell, for a channel a level below the walkway, so on our walkway it hung against the wall over squares that looked walkable. Ours now (`sewars_01_26`): the same water on the floor diamond, still blocking like vanilla's (the bridges are the way across). Build revision 2 swaps it in on chunks already built, ours only. `test_assets` checks where it is drawn, `test_flow` the swap, two mutations caught
- [x] **(game)** the channel lies flat in the walkway; bridges cross it
- [x] **Our tiles drew over characters** (a player's report from a dedicated server, 0.3.1): a tile of ours has no depth texture. Floor tiles now carry `RenderLayer=Floor`, wall tiles `WallOverlay` (the wall's depth), and the caves' earth and breaches are laid over vanilla walls instead of being walls of their own. Fixes saves already built (properties are read by sprite name). `test_assets` checks every tile
- [ ] **(game)** walk over a puddle, a light pool and past graffiti and a ladder: the character is drawn over them
- [x] **Earth floated over black by a breach** (found in play, the depth fix above): the camera's cutaway cuts a wall and what is attached to it only, and our pictures were objects of their own beside their walls, so they stayed full height over a wall cut down. Earth, breaches, ladders, stencils and graffiti are now attached to their wall or door frame, as vanilla hangs a wall overlay (`AttachExistingAnim` + `transmitUpdatedSpriteToClients`); saved and sent with the wall. Build revision 5 moves an old save's loose pictures on to their walls. `test_flow`: none loose, old ones moved once, the client gets them; three mutations caught
- [ ] **(game)** by a cave's breach and at a ladder, walls cut away with their pictures; an old save's caves the same after walking back into them
- [x] **The map key was vanilla's Start/Stop Engine** (a Workshop comment): N is vanilla's engine key, and ours opened the map in a car in any town. Now **K**, the one letter vanilla's `keyBinding.lua` leaves unbound, under a new option id so a 0.3.1 player's saved N is not read back; never while in a vehicle. `sim.lua` loads ModOptions.ini the way vanilla does; `test_flow` checks K opens and closes, N and the car do not; three mutations caught
- [ ] **(game)** K opens the map below; N starts a car and opens nothing; Options -> Mods shows K
- [x] **Every one of the dead carried something, and every crate was full** (a Workshop comment). 4 of 11 tunnel outfits and 2 of every 3 shelter dead came with a pack vanilla fills, and a crate was stocked by walking its list to 45% of capacity (a last stand's held every gun). Now: ordinary outfits with no bag (checked against vanilla's clothing and guid table), equipped ones by share; a crate draws a few picks by a seeded generator (`U.rng`: the position hash is linear and stepped through a list); guns one pick in eleven. Two sandbox options: **Shelter supplies** (None / Scarce / Normal / Plenty) and **Who the dead were** (Mostly ordinary / Mixed / Survivors, 0.3.1's balance). New chunks and shelters only (stocked once). Three mutations caught
- [ ] **(game)** the sandbox page shows both options; a new shelter's crate holds a few things
- [ ] Remaining ends are at a town's edge, where the road leaves town: dress them (a collapse, a grate) so they read as the end of the line, not a bug

## 0.3.3 -- the sewer is really indoors, and other mods can tell (proposed)

The engine calls every square below z 0 outdoors (DEV_GUIDE, *Below ground is
outdoors to the engine*). 0.3.2 fixed what Lua asks; the Java side is still open,
and so is the next Flying Birds.

- [ ] **(game)** Weather below: is rain drawn in the tunnel, does the player get wet, is it the outdoor temperature with wind chill? The bytecode says likely: `Temperature.getWindChillAmountForPlayer` and `ClimateManager.getAirTemperatureForSquare` key on rooms, `BodyDamage` on `isOutside`
- [ ] If so, a fix: find an engine lever, or counter it in Lua below ground (dry the player, hold a cellar temperature) -- tested as a pair with the street, where the weather must stay
- [ ] **An API for other mods**: `SEW.Sewer.below(player)` documented and kept stable, plus `OnSewerEnter` / `OnSewerExit` events, so an ambience or weather mod can opt out without guessing from z
- [ ] **Map mods**: the layout is cut from the vanilla map; a map mod that rebuilds a town can put a building or a basement over a tunnel. Refuse a cover with a building over it at runtime (not only the four known), and say in the README which map mods are known safe
- [ ] A *Plays well with* line on the Workshop page once Flying Birds is confirmed in game

## 0.4 -- more underground

- [x] **Broken walls into caves**: rubble breaches off some tunnels into winding dug-out caves (dirt and rock), with hideouts at the ends -- people dug, and broke out of the sewer. 59 caves in 14 towns, generated after everything else from their own seed (no shelter, shaft, journal or piece of furniture moved); a breach knocked through vanilla's own brick or concrete wall (a door frame to the engine), a winding dirt passage (vanilla dirt floor, our earth walls), sometimes a side branch, loose stones, and a hideout with a bedroll, two stocked crates, a candle's glow and sometimes its builder. Caves reach chunks a save built before they existed (`s.caves`), once. `test_layout` walks every cave and proves the breach is the only way in; `test_flow` builds one in a 0.3 save; six mutations caught
- [x] **Dev build starts at a cave**: a new character in SewarsDev is put on the cover nearest a Muldraugh cave's breach (`C.DevStartTown`); `SEW_Caves()` / `SEW_GoCave(n)` in the console
- [ ] **(game)** the breach, the passage and the hideout: walls, floor, light, the crates, the dead
- [x] **Houses with a way down**: a hatch in the floor of some houses (garages, kitchens, storerooms) near a tunnel, with a short culvert to the network; skipped at runtime if the house got a random basement. 72 hatches in 11 towns, generated after the caves (nothing else moves), each on a clear floor square of a garage, garage storage, laundry, kitchen, shed or storeroom, its culvert out from under the house in 8 squares or fewer. The server looks at the house once, when a player on the street comes within 40 squares and it is loaded: nothing but ours under it and the trapdoor (our tile) goes into the floor; anything else there and it stays shut for good, and the server refuses a climb down it. *Climb down / up through the hatch*, a shorter climb, no lid. Rescues never go to a hatch's ladder. `SEW_Hatches()` / `SEW_GoHatch(n)` in the console. `test_layout` walks every hatch from the street covers; `test_flow` opens one and climbs it both ways, and leaves one with a basement shut; five mutations caught
- [x] Found on the way: `keep` missed every room listed by a neighbouring cell's header (a building across a cell edge was half missing). The 0.3 tunnels never met one; the first caves and hatches did, under three houses. Caves and hatches plan against every room now (`room_mask`), and `test_layout` checks against it; the 0.3 layout is unchanged
- [ ] **(game)** does B42 stamp its random basement into z -1 before the server first looks at the house (at chunk load)? If later, a hatch could open over one -- watch for `hatch ... opened` over a house that has a basement
- [ ] **(game)** a hatch: the trapdoor in the floor, down, the culvert, back up into the house
- [x] **Towns the map gives few covers** (asked in play: "I travelled to Louisville but don't see any manhole covers"). Vanilla paints 13 covers on all of Louisville -- ten times Muldraugh's buildings -- and none on Irvington, Brandenburg, March Ridge or Valley Station. Built-up districts with fewer than 5 covers per 10,000 building squares (the covered towns have 10-30) get 15 new towns with covers of our own: 732 of them, on clear painted road by junctions and along long runs, put into the road by the server when a player on the street first comes near. Louisville alone: 470 covers, 94 shelters, 59 caves, 78 hatches. Every older town is byte-identical (new towns keep out of their chunks), so the old Louisville strip stays a network of its own. Our cover is vanilla's picture as a floor tile. `test_layout` walks all 31 towns and checks every cover of ours is on clear road; `test_flow` puts one in and climbs down it; three mutations caught
- [x] Found on the way: a shaft with no wall beside it got a wall built on its north edge whatever was there; at a junction that cut a street off (131 squares stranded in Louisville). New towns hang the ladder on a side with rock behind it; covers of ours stand on the tunnel's edge. And `test_layout` recomputed a town's extent per square -- invisible at Muldraugh's size, over ten minutes at Louisville's; 20 seconds now
- [ ] **(game)** Louisville: covers appear in the road as you walk; down one, the tunnels under the streets
- [ ] **Storm-drain outfalls**: culverts that open onto creek and river banks outside town -- secret exits and entries
- [x] **Rats**: vanilla B42 rats in the tunnels, trappable. Put down with a stretch of walkway on its first build, by a new sandbox option (**Rats in the sewers**: None / Few / Some / Swarming), once -- the engine saves and syncs them after that. `test_flow` checks they are down on the walkway, below ground and handed to the world; one mutation caught
- [ ] **(game)** rats in the tunnels: seen, heard, trappable; still there after a save and reload (the engine saves a chunk's animals at every level -- unproven below 0)
- [x] **The rats' nest under Louisville** (asked by the author): one per world, hidden. A tunnel wall off a culvert near the park south of downtown is a false wall -- loose brickwork cracked round a gnawed hole, and an *R.O.U.S. -- THEY EXIST* warning a few squares along. *Pull at the loose bricks* (a crowbar or sledgehammer is quicker) opens a rat run through the rock to a round nest of bones and litter, where four **rodents of unusual size** sleep: our own animal, `rous`, on vanilla's rat at 2.8 times its size, not wild, never fleeing. They hunt any player below within 16 squares and bite (a scratch or a cut on a limb), driven by the server: the engine cannot make a rat bite, and a mod cannot give an animal a new action group. At the far side a bricked-up room holds the **hoard** -- rifles, ammunition, medicine, tools, a generator, food, gold -- behind a wall they gnawed half through: *Tear through the gnawed wall* is refused while any of them lives. Laid out last in `gen_sewers.py` (`dig_lair`), so nothing else moves; 4 new tile pairs and 2 floor decals; `test_layout` proves the two walls are the only ways in; `test_flow` walks the whole of it; eleven mutations caught
- [x] **Dev build starts by the nest**: a new character in SewarsDev is put in the house whose hatch is nearest the nest (`C.DevStart = "lair"`); `SEW_GoLair()` and `SEW_Lair()` in the console
- [x] **Fixes from the first play-test of the nest** (the author: "they just stand around and don't attack", "I cannot shoot them", rats "on the outside void space", and both walls on the south, where their art is on the far side):
  - The ROUS had our own action group, which the game never loads (it reads `media/actiongroups` from its own folder only), so they had no states at all. Back on the rat's; the server chases (the engine's path, or by hand a step a tick, never through a wall) and bites on a timer (`syncBodyPart` on a server). `test_flow`: the sim's engine path does nothing below ground, and they still reach the player, never off the floor, and bite
  - Rats were put on the corners of their squares (addAnimal takes x, y as given), on the wall lines; now in the middle, and a leash every two seconds puts any animal below ground that is off the walkway back on it, or takes it away
  - Every hit on a ROUS is logged with what it has left, to settle the shooting in the next test; `healthLossMultiplier` 0.008 (a guess)
  - The false wall is always on the north or west of the tunnel square it is found from, and the gnawed wall on the north or west of the nest square in front of it, where their pictures face the camera; never off a hatch's culvert (one was, under the house). The nest moved: **a new world is needed** for it (`test_layout` checks both walls face the camera)
  - Five new mutations (the bite, walking by hand, walls, the middle of the square, the leash), all caught
- [ ] **(game)** the ROUS come at you and bite; can be shot, and die in a sensible number of hits (`[SEW] a ROUS was hit` lines)
- [ ] **(game)** the nest: the cracks by the false wall, pulling it away, the run, the nest, the gate refused, then opened once they are dead, the hoard
- [ ] **(game)** rats stay inside the walls
- [x] Engine research: rats (addAnimal), sickness (CharacterStat.POISON + syncPlayerStats), masks (isProtectedFromToxic), locked doors (forceLocked jail sprite -- runtime doors otherwise open for anyone), keys, journals (own item + panel), petrol pumps, water tiles, no vanilla hatch

## 0.5 -- danger and reward

- [ ] **Sewer gas**: some stretches sicken you over time; a gas mask or respirator stops it; warning placards at the entrances
- [ ] **Locked maintenance gates**: steel grilles on the way into set pieces and some shelters; keys on sanitation-worker zombies and in maintenance rooms
- [ ] **Flooding**: rain upstairs floods the low culverts (wet, cold, slow); **pump stations** drain their district when run with fuel
- [x] **Journals**: one in every shelter (93), ten texts by what they point at; reading one marks the next place on your map, with street and direction
- [ ] Tapes (recorded voices, vanilla's RecMedia) and more journal texts as caves and set pieces land

## 0.6 -- the deep and the strange

- [ ] **The interceptor (z -2)**: long storm-relief tunnels between towns along the highways, reached by ladders in the brick vaults
- [ ] **Bootlegger's tunnel**: Prohibition-era, a still, barrels, a bourbon cache, a speakeasy room
- [ ] **Fallout shelter**: Cold War, bunks and canned food, a radio; off a trunk line
- [ ] **The quarantine**: welded grates, army barricades, biohazard drums, sealed tunnels near the hot zone
- [ ] **The cavern under Louisville**: a pillared limestone mine, huge and dark (after the real Louisville Mega Cavern)

## Art (FlowDot: Gemini paints materials, the generator does geometry)

- [x] Procedural pass: stencils, graffiti, grime, puddles, light pools, wall variants
- [~] Materials: wet brick, stained concrete, tunnel floor (generated, `design/art/materials/`, not yet in game)
- [ ] Project the materials onto vanilla wall silhouettes; new brick and concrete wall sets; new tunnel floor
- [ ] Cave materials: packed earth, limestone, rubble breach
- [ ] Map paper texture, plan item and journal icons, gas placard, gate, floor hatch
- [ ] 3D pieces via Gemini concept -> fal TRELLIS -> iso render: pump, still, army barrels, bunks
- [x] Poster and Workshop preview from the author's ladder screenshot; Steam gallery (`workshop/store/`): the way down in four captioned shots, and each alone
- [ ] A painted poster and Workshop preview

## Release

- [x] First Workshop upload: 0.3.1, item **3810188405**, public (2026-09-29); `WORKSHOP_ID` set
- [x] 0.3.2 folded into 0.5.0 (never uploaded on its own)
- [~] **0.5.0 update**: caves, hatches, Louisville and the sparse towns, rats, the nest; staged with `package --install` (2026-09-30), upload from the game's Workshop screen
