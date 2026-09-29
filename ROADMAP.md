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
- [x] Open it: *Sewer map* on the right-click menu below ground, and the **N** key (rebindable, Options -> Mods)
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
- [ ] Remaining ends are at a town's edge, where the road leaves town: dress them (a collapse, a grate) so they read as the end of the line, not a bug

## 0.4 -- more underground

- [ ] **Broken walls into caves**: rubble breaches off some tunnels into winding dug-out caves (dirt and rock), with hideouts at the ends -- people dug, and broke out of the sewer
- [ ] **Houses with a way down**: a hatch in the floor of some houses (garages, kitchens, storerooms) near a tunnel, with a short culvert to the network; skipped at runtime if the house got a random basement
- [ ] **Storm-drain outfalls**: culverts that open onto creek and river banks outside town -- secret exits and entries
- [ ] **Rats**: vanilla B42 rats in the tunnels, trappable
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
- [ ] 0.3.2 update, after its play-test
