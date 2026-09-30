# Sewars: design

How the sewers work and why. `DEV_GUIDE.md` is how to work on them without
breaking them. Where this file says **open**, nothing is decided yet and the
author has the last word.

---

## 1. What vanilla already has (read off the map, 2026-09-28)

Vanilla has **sewer art and no sewer system.** The facts, all from
`python tools/pzmap.py census` against the installed map:

| | |
|---|---|
| Manhole covers on the streets | **446** across the map, 76 in Muldraugh. All decoration: `street_decoration_01_15`, `attachedFloor`, no properties, no hole under them |
| Storm drains at the kerb | `street_decoration_01_13/14/30/31`, likewise decoration |
| The `location_sewer_01` sheet | Brick and concrete walls, doorways, a sludge floor, two outfall pipes, pipework, metal grating, and **sewer ladders** in all four facings. See `design/art/vanilla_sewer_tiles.png` |
| Where vanilla uses that sheet | Almost all at z 0 and above, as **plain building walls**. Below ground: a handful of pipes in basements, one room named `tunnel` at z -1, and a deep bunker at around 5550,12450 that goes down to **z -17** |
| Map cells with levels below ground | 72 of 4,065 (66 reach z -1, the deepest -17) |

So there is nothing to conflict with, a matching tile sheet to build from, and
proof that the engine draws and walks levels well below the street.

`design/art/map_muldraugh.png` is Muldraugh's street grid with every manhole on
it, drawn by `tools/pzmap.py town`. Look at it: the covers sit along the
streets at junctions and on long runs, which is exactly where a sewer's access
shafts would be.

## 2. The player's loop

1. **Find a cover.** Any `street_decoration_01_15` in the world.
2. **Right-click it: *Enter sewer*.** A short timed action (lifting the lid,
   a crowbar makes it faster). The player climbs down.
3. **Arrive at the foot of a ladder** in the tunnel under that cover.
4. **Walk.** The tunnels follow the streets. Other covers are other ladders.
5. **Right-click a ladder: *Climb out*.** Up through the cover above it,
   onto the street, which the player can see was the right one.

Two things the loop must never do (trekship DEV_GUIDE, *Never let a failure
strand the player*, *A door with no handle on the inside*):

- **Strand a player below.** Every tunnel stretch that can be reached has a
  way out, and a player who logs in below with no tunnel built round them is
  put at the nearest ladder, not left to fall.
- **Offer a one-way move.** *Enter sewer* and *Climb out* are written and
  tested as a pair.

## 3. Where the sewers are: under the town, at z -1 (decided)

**Decided 2026-09-28, from the bytecode: the tunnel under 10603,9526 *is* at
10603,9526, one storey down.** Coordinates need no translation, the map is
right, climbing out needs no search, a player's base under the high street is
under the high street, and no move is long enough for the speed anti-cheat to
ration.

The three facts it rests on (DEV_GUIDE, *Below ground is real*):

- `IsoChunk.setSquare` grows a chunk's level range **downward** as readily as
  up -- `setMinMaxLevel(min(minLevel, z), max(maxLevel, z))` -- and vanilla's
  own upstairs building takes that path every day. `getOrCreateGridSquare`
  reaches it; the mod never calls `setMinMaxLevel` itself.
- z is valid from -32 to 31 (`IsoChunkMap.isWorldSquareOutOfRangeZ`), and
  `IsoChunk.Save` writes the level range, so what is built persists.
- `FBORenderCell.renderInternal` (bci 400-428) sets `maxZ = ceil(z) + 1` for a
  camera player below zero: **the street above is not drawn at all**, whatever
  rooms or buildings there are. That rule is what vanilla's basements use,
  and it keys on the player's z alone.

What only the game could settle, and has since (0.2 to 0.5): runtime squares
below ground are lit, zombies path on them, and they survive a save and
reload. The fallback (the trekship's way: tunnels in a mapped black void
region, each cover a long move to its copy) was never needed.

## 4. Laying the tunnels out from the streets

The layout is **generated offline** and shipped as data, as the trekship
ships its decks: `tools/gen_sewers.py` reads the map, writes Lua, and the
server builds from the Lua. Nothing in the game reads a map file.

1. **Towns** are clusters of manholes (446 on the map; linked within 220
   squares): 16 of them, named from vanilla's own town folders.
2. **Keep-out**: every building footprint (all room rectangles, any level)
   plus two squares, and anything the map already has below ground. B42
   stamps *random* basements under buildings at world generation, so a
   tunnel must never pass under one; the server also leaves alone any square
   it finds already holding something.
3. **Centre lines** from vanilla's `streets.xml` -- 1,098 named streets with
   widths -- rasterised and made 4-connected (a diagonal step between walls
   cannot be walked). Streets are kept by bounding-box overlap: Dixie Highway
   crosses Muldraugh as one segment with both ends outside it.
4. **Width** from the street: 10 wide and up is a 5-wide **trunk** with a
   sludge channel down its middle, bridged every nine squares and wherever a
   stretch would otherwise be cut off; 6-9 a 3-wide **main**; narrower a
   1-wide **culvert**.
5. **Shafts**: every manhole gets a grating square under it and a ladder on
   the nearest wall. A cover off the named streets (a car park, an alley) is
   joined to the network by a culvert routed under the road where it can be;
   one with nothing in reach gets a small cellar of its own. Four covers over
   buildings are left shut, and say so when right-clicked.
6. **Vaults**: 7x7 brick chambers at junctions of the wider tunnels, 45
   squares apart.
7. **Only what a ladder can reach** is kept, and `tests/test_layout.py`
   walks every town to prove it.
8. **Shelters** (section 7) off the tunnel walls, one per five shafts.
9. **Walls** on every edge between inside and out, and between a shelter and
   its tunnel (its steel door on one edge); brick in trunks and vaults,
   concrete elsewhere, varied per square; pillars at outer corners.
10. **Dressing** by position hash: pipes, EXIT stencils near ladders,
    graffiti, grime, puddles, debris, smears, a light pool under each cover,
    SAFE by each shelter door.

11. **Caves** (0.4), last and from a generator of their own, so nothing above
    moves under a save: one per eight shafts, 50 squares apart, each breaking
    through a plain tunnel wall away from ladders, doors and the channel. A
    passage 18-40 squares, winding, a square wider here and there, sometimes
    a side branch, then a hideout grown out from its end. A cave keeps two
    squares of rock from every other space, so its breach is its only way in.
    Floors `m`, earth walls `e`, breaches `o` (concrete) and `q` (brick).

12. **Houses with a way down** (0.4), after the caves and from their own
    generator again: one per six shafts, 40 squares apart, in a garage,
    kitchen, laundry, shed or storeroom whose house the map gives no
    basement. The hatch goes on a floor square with nothing else on it
    (`clear_floor`, from the map), and its culvert leaves the house by the
    cheapest way out (a square under the house costs four), at most 8 squares
    under it and 30 in all, meeting the tunnel end-on on plain walkway.
    **These are the only tunnel squares under a building**, and they are
    listed in the index: B42 stamps random basements under houses when a
    world is made, so the server looks under the house in game and puts the
    trapdoor into its floor only if nothing is there (SEW_Build.hatch).

13. **Towns the map gives few covers** (0.4), last of all. A map cell with
    1,500 street-level building squares is built up; built-up cells that
    touch are a district; a district of 5,000 building squares or more with
    fewer than 5 vanilla covers per 10,000 of them becomes a town of its own
    (Louisville, Irvington, Brandenburg, March Ridge, Valley Station and ten
    smaller ones). Its tunnels follow its streets exactly as above, kept to
    its own cells and out of every older town's chunks (one town per chunk,
    and nothing in a save moves). Its covers are ours: on the tunnel's edge
    within two squares of the street's centre line, on painted road with
    nothing else on it, by junctions 45 apart and then every 70 squares along
    any run with none. In game the server puts each into the road when a
    player on the street first comes near (SEW_Build.cover).

14. **The rats' nest** (0.5), under Louisville's district only, last of all
    from its own generator (`dig_lair`), so nothing above moves. Placed where
    solid rock clear of everything by two squares fits it, nearest a house
    with a way down and the park south of downtown. A false wall off plain
    walkway (`x` concrete, `y` brick: a wall until pulled away, then a breach),
    a winding run through the rock with a square of rock either side, a round
    nest of radius 6 (floor `n`), and on its far side a bricked-up room, the
    hoard (floor `v`), behind a wall they have gnawed half through (`z`).
    Both walls are on the north or west edge of the square they are found
    from, because from inside a square only those walls face the camera
    (found in play: on the south, their cracks and claws were on the far
    side). It is
    on no plan and on no player's map: hidden is the point. `SEW.Index.lair`
    names its squares, where its rodents sleep, and the hatch and cover
    nearest it by walking the tunnels.

15. **Storm-drain outfalls** (0.5), after the nest, from their own
    generator (`dig_outfalls`): culverts from plain walkway out to the bank
    of a creek, the river or a lake -- dry natural ground beside a body of
    water of 300 squares or more (a pool is smaller), clear of buildings and
    the map's own underground -- 8 to 80 squares, never under water or
    beside other space, meeting the tunnel end-on. Shortest first, one per
    body of water before a second, 120 apart, up to 4 a town: 16 under 10
    towns. Each ends in a shaft whose top is a grate of ours in the bank,
    `made` like a cover of ours (the server sets it in as a player comes
    near). New squares only.

16. **Locked gates** (0.5, `gate_shelters`): in a town with two or more
    county rooms (maintenance rooms and pump stations), half of them sit
    behind a locked grille -- the door edge is `j` instead of `d`, nothing
    else changes. One key per town (`gate_key`: an id above anything vanilla
    hands out), left in the first crate of every **unlocked** county room
    (`key_spots`), so a town with one county room has no gate. 47 gates in
    13 towns.

17. **Sewer gas** (0.5, `vent_gas`), last of all: stretches of 1-wide culvert
    (in no 2x2 block of walkway), 16-48 squares, 60 apart, one per twelve
    shafts, never within 10 of any ladder (the outfalls' included), off
    every shelter, cave, hatch culvert and the nest. It adds no square: it
    lists gas squares (`g`) and a placard at each way in (`p`, on a wall of
    ours by the way in) in the town's data, and each stretch in the index.
    97 stretches in 17 towns.

`design/art/plans/<town>.png` is each town's plan over its streets (caves in
ochre, breaches pink, hatches cyan, gas yellow-green, water blue, outfalls
white); look at it after any change. `tools/render_sewer.py` draws a stretch with the real tiles.

## 5. Building a stretch

The trekship's builder, on a smaller scale (trekship DEV_GUIDE, *Never build
where no player is standing*, *Tag every object you place*):

- **The server builds**, only in loaded chunks, as a player comes near, a
  stretch at a time (sliced; *Slice any search that touches thousands of
  squares*).
- Floor, walls on every tunnel edge, the ladder on the shaft square's wall,
  the channel, pipes and grating as dressing. Every placed object tagged
  `C.Tag`.
- **Once built, it is the player's.** A stretch is built once and recorded;
  later passes repair only what the mod placed and a player has not changed.
  Anything a player builds down there is never touched (trekship
  `BUILDING.md`: a builder that takes a player's wall for wilderness is the
  worst bug a base-building mod can have).
- **A roof.** Build A is below the street and was expected to need none. It
  does, and cannot have one: the engine never roofs a square below z 0, so a
  tunnel is outdoors to it and to every mod that asks. Lua callers are told
  otherwise (`SEW_Compat.lua`; DEV_GUIDE, *Below ground is outdoors to the
  engine*); the engine's own weather is the game's to show. Build B is in the
  void and would: every floor square gets the invisible roof tile one storey
  up, or it rains in the sewer.

## 6. The dead below

- **A population of their own**, spawned by the server as stretches are
  built, thin in culverts and thicker in chambers and near outfalls. Sandbox
  option for the density.
- **Ones that fall in.** An open cover is a hole: a zombie walking onto it
  may drop into the tunnel below. (**Open**: whether covers stay open once a
  player uses one, and whether a player can close one behind them.)
- **Sewer-dressed.** Outfits from vanilla's own set that read as having been
  down here: workers' overalls, waders, filthy clothes. A later pass may add
  our own (section 8).
- **Sound.** In build A, noise travels between the street and the tunnel the
  way the engine lets it; in build B it cannot.

### Rats, and the rodents of unusual size (0.5)

- **Rats**: vanilla's own (`rat`, `ratfemale`), put down on a stretch's
  walkway on its first build by the sandbox's density, and the engine's
  after that. They flee, can be trapped, and are food.
- **ROUS**: four, in the nest only. An animal of our own on the rat's
  model, 2.8 times its size, that stands its ground. The server sets them on
  whoever is below within 16 squares and bites for them -- the engine cannot
  make a rat attack, and a mod cannot give an animal new behaviour
  (DEV_GUIDE, *A mod cannot add an action group*). The hoard's
  wall gives only when the server can find none of them alive within 60
  squares of the nest -- it looks, rather than counting kills, so it cannot
  be fooled by a death it never heard of, and one lured away and left alive
  keeps it shut. (**Open**: whether they should ever come back.)

## 7. Shelters

Random, found, and the reason to explore.

| Kind | What it is |
|---|---|
| Maintenance room | A locked steel door off a trunk; a desk, lockers, tools, a cot |
| Pump station | A chamber with machinery and a generator that can be brought back |
| Squat | A bricked-up side tunnel: bedrolls, candles, cans, a journal |
| Last stand | A barricade across a culvert, and what is left of whoever held it |

- **Placed by the generator**, from a seed per world, so two worlds differ and
  one world stays the same after a reload. (**Open**: seed from the world or
  fixed per release.)
- **Stocked once, ever** (trekship *Never restock an existing container*).
- **Some are claimed**: a zombie survivor in a sleeping bag, or a note saying
  where they went.

### Locked gates and the county's key (0.5)

- **Half the county's rooms are locked** (section 4, 16) behind vanilla's
  barred cell door: you can see the crates, and it will not open.
- **One key per town**, the *Sewer Maintenance Key* named for it, in the
  crates of the county rooms that are not locked, and on some of the dead in
  sanitation overalls (who also carry the town's plans). It works from the
  hands or a key ring, as every key in the game does -- not from a bag.
- **A latch, with a handle on the inside.** The server locks a shut grille
  again once its room is empty, so the dead never follow a key-holder in;
  while anybody is in the room it stays unlocked, so nobody is ever shut in
  (DEV_GUIDE, *A locked gate is a key id and a lock set before it is sent*).
- **New rooms only**: the grille goes in on a room's first build, and the key
  with the room's first stocking. A room a save has already built keeps its
  steel door; nothing a player may have made theirs is taken away.
- A sledgehammer still takes one down. (**Open**: set pieces behind gates, as
  they land.)

## 7b. Sewer gas (0.5)

- **Where**: some narrow culverts well away from the ladders (section 4,
  17), with a yellow-green haze on the floor and the county's placard --
  *DANGER / SEWER GAS / MASK REQUIRED* -- at every way in.
- **What**: each game minute in it without a gas mask or respirator adds
  poison up to the sandbox's cap; the engine turns poison into sickness and,
  past 10, lost health, and lets it wear off once you are out. A mask with
  a filter keeps it out and uses the filter up.
- **Sandbox, Sewer gas**: Off / Mild (queasy at worst) / Harmful / Deadly --
  a dose of poison a game minute and a cap, `C.Gas`: 1 up to 10 (poison
  under 10 costs no health), 2 up to 20 (the worst drink of tainted water,
  held), 4 up to 40. A first guess for the play-test to tune.
- **Built once**: the haze and placards go down once per chunk (`s.gas`),
  first build or not, so a save from before the gas gets them the next time
  a player is near; a player who scrubs the haze away keeps it away. Not
  while the sandbox has gas off.
- **The map**: a stretch walked into, or on the sheet of a plan read, is
  marked on the sewer map.

## 7c. Storm-drain outfalls (0.5)

- A grate in a riverbank or lakeshore near town (section 4, 15): a way in
  nobody on the street sees, and a way out onto the bank, away from the
  streets. Blue on the sewer map once used, and the map now shows the water
  above faintly. (**Open**: flooding through them, section 10.)
- To the code it is a cover of ours (`made`): the server sets the grate
  (`sewars_01_47`, a floor decal) into the bank when a player up top first
  comes near, and the climb is SEWClimb's, quicker than a lid and with no
  scrape. A rescue may send a player to an outfall's ladder: it is a real
  way out.

## 8. Art

Vanilla's `location_sewer_01` is the base, because it matches the game and
costs nothing. What it lacks, we make:

- **Tunnel walls with character**: arched brick, curved concrete pipe,
  staining, graffiti, tide lines. Tiles, rendered through the trekship's
  isometric pipeline or painted with an image model and cut to 128x256.
- **A manhole shaft seen from below**, a lit disc overhead where the cover is.
- **Signs and stencils**: sector numbers, "NO ENTRY", flow arrows, town names
  -- so a player can navigate.
- **Shelter dressing**: the journals, candles, cots.

Made with the **Flowdot** workflows and the **Gemini** toolkit
(`generate-image` for paint, `analyze-image` for critique), keyed, and vetted
at game size against vanilla's own tiles. `DEV_GUIDE.md` *Art* is the
pipeline.

## 9. Order of work

| # | What | Status |
|---|---|---|
| 0 | Can a runtime square exist at z -1, and is the street hidden from below | **settled** from bytecode (section 3), and in play: lit, pathed, saved |
| 1 | *Climb down* / *Climb out* | **done**, single player, hosted and dedicated |
| 2 | The generator, every town | **done**: 31 towns, 442 shafts under the map's covers and 732 under ours |
| 3 | The server builds as players walk | **done**, sliced, current-revision tracked |
| 4 | Zombies below | **done** (sandbox density and outfit mix, never on a player); falling in through open covers: not yet |
| 5 | Shelters | **done**: 239, four kinds, stocked once, a journal in each; 47 county rooms behind locked grilles |
| 6 | The map, plans and journals | **done** (0.3) |
| 7 | Caves, hatches, Louisville's covers, rats, the nest | **done** (0.4, 0.5) |
| 8 | Art | procedural pass **done** (48 tiles); image-model pass next |
| 9 | Danger and reward: gas, gates, outfalls | **built** and tested offline; waiting on the author's play-test |

## 10. Open decisions for the author

- **Covers**: once opened, do they stay open? Can they be closed from below?
  Can a player weld or weigh one shut?
- **Storm drains**: too small to use, or a crawl-in for later?
- **Flooding**: does rain raise the water in the channels?
- **Depth**: one level of tunnels, or a deeper storm-relief level under the
  trunks?
- **The ROUS**: should they ever come back?
- **Sandbox**: zombie density, their outfits, shelter supplies and rats are
  options; shelter frequency and whether covers need a tool are not.
