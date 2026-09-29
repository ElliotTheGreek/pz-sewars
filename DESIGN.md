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

What only the game can settle, and the first thing to look at (DEV_GUIDE,
*Current state*): lighting of runtime squares below ground, zombie pathing on
them, and a save and reload.

The fallback, kept in case the game disagrees: the trekship's way -- the
tunnels in a mapped black void region, each cover a long move to its copy.
Everything above the builder would carry over; the builder would take an
offset.

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

`design/art/plans/<town>.png` is each town's plan over its streets; look at it
after any change. `tools/render_sewer.py` draws a stretch with the real tiles.

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
| 0 | Can a runtime square exist at z -1, and is the street hidden from below | **settled from bytecode** (section 3); the game confirms lighting, pathing, saving |
| 1 | *Climb down* / *Climb out* | **built**, tested single player and client-server |
| 2 | The generator, every town | **built**: 16 towns, 442 shafts, plans rendered |
| 3 | The server builds as players walk | **built**, sliced, current-revision tracked |
| 4 | Zombies below | **built** (sandbox density, never on a player); falling in through open covers: not yet |
| 5 | Shelters | **built**: 93, four kinds, stocked once |
| 6 | Art | procedural pass **built** (27 tiles, wall variants); image-model pass next |
| 7 | In game | **waiting on the author's first run** (DEV_GUIDE, *Current state*) |

## 10. Open decisions for the author

- **Section 3**: A or B, after spike 0.
- **Covers**: once opened, do they stay open? Can they be closed from below?
  Can a player weld or weigh one shut?
- **Storm drains**: too small to use, or a crawl-in for later?
- **Flooding**: does rain raise the water in the channels?
- **Depth**: one level of tunnels, or a deeper storm-relief level under the
  trunks?
- **Sandbox**: zombie density, shelter frequency, whether covers need a tool.
