# Working on Sewars

Orientation for anyone -- human or agent -- picking this up in a new session.

`README.md` says what the mod does. `DESIGN.md` says how the sewers work and
why. **This file says how to build, test and update it without breaking it.**

This mod is a descendant of the Star Trek shuttle in
`C:\Users\Arcade\pz_trekship`, the way that one descends from the TARDIS. Its
tools came from there already paid for, and so did its rules: the trekship's
`DEV_GUIDE.md` is 3,400 lines of what the engine actually does, most of it
learned by breaking something. The rules below are the ones this mod will lean
on hardest. **When in doubt, read the trekship's section of the same name.**

---

## First five minutes

```sh
cd C:\Users\Arcade\pz_sewars
pip install lupa pillow numpy scipy          # once per machine
python tools/dev.py all                      # build everything, test everything, install SewarsDev (~3 min cold)
```

If that ends with `deployed ... -> ...\Zomboid\mods\Sewars`, you have a
working setup. After that, the loop is just `python tools/dev.py` (checks and
deploy, about a minute).

| Where | What |
|---|---|
| `C:\Users\Arcade\pz_sewars` | this repo |
| `C:\Users\Arcade\pz_trekship` | the mod this one is built on; read its `DEV_GUIDE.md` |
| `C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid` | game install |
| `C:\Users\Arcade\Zomboid\mods\Sewars` | the local dev build, installed as `SewarsDev` ("Sewars [DEV]") |
| `C:\Users\Arcade\Zomboid\Workshop\Sewars` | the Workshop staging folder the in-game uploader reads |
| `C:\Users\Arcade\Zomboid\console.txt` | the game log, **overwritten each launch** |
| `C:\Users\Arcade\Zomboid\server-console.txt` | the local dedicated server's log |

Target is **build 42.20.4**: single player, hosted co-op **and dedicated
servers**, for anyone who subscribes on the Workshop.

---

## Layout

```
Sewars/42/mod.info                                  identity, version, pack=sewars, tiledef=sewars 7462
Sewars/42/poster.png                                the mods-screen picture (generated)
Sewars/42/sandbox-options.txt ... media/            (see below)

media/lua/shared/SEW/SEW_Config.lua        every constant, sprite, loot list -- start here
media/lua/shared/SEW/SEW_Util.lua          safe engine calls, squares, stocking, teleport (from the trekship)
media/lua/shared/SEW/SEW_Net.lua           client -> server commands and replies, all three setups
media/lua/shared/SEW/SEW_Sewer.lua         read-only questions: which shaft, which cover, am I below
media/lua/shared/SEW/SEW_Actions.lua       SEWClimb, the timed action: down a cover, up a ladder (global, shared)
media/lua/shared/SEW/SEW_Rats.lua          the ROUS: an animal definition of ours, copied from vanilla's rat
media/lua/server/SEW/SEW_Nest.lua          rats on first build, the leash, the ROUS (spawn, chase, bite), the nest's walls that open
media/lua/shared/SEW/SEW_Compat.lua        below ground is indoors: isOutside wrapped for every Lua caller, other mods included
media/lua/shared/SEW/SEW_Index.lua         GENERATED: towns, shafts, shelters -- small, every process
media/lua/server/SEW/SEW_Build.lua         raising a chunk of tunnel: floors, walls, doors, ladders, dressing, shelters, the dead
media/lua/server/SEW/SEW_Server.lua        the authority: granting climbs, building round players below, rescues, console
media/lua/server/SEW/Data/SEW_Town_*.lua   GENERATED: every town's squares, by chunk -- 1.3 MB, server only
media/lua/client/SEW/SEW_Client.lua        the menus, the move, the vault switch, lamps, ambience
media/lua/shared/Translate/EN/*.json       ContextMenu, Tooltip, IG_UI, Sandbox -- one file per category
media/sewars.tiles, texturepacks/sewars.pack   GENERATED: our 36 tiles
media/scripts/sewars_sounds.txt, sound/SEW_*.wav   the sounds (wavs generated)
media/sandbox-options.txt                  zombie density, their outfits, shelter supplies

tools/dev.py              THE ENTRY POINT: build, check, mutate, deploy, run, log, package
tools/gen_sewers.py       the map -> the tunnels (Data/ and SEW_Index.lua), and plans in design/art/plans/
tools/gen_sewer_art.py    our tiles: drawn, projected, packed; review sheet in design/art/
tools/gen_sewer_sounds.py the four sounds, synthesised
tools/render_sewer.py     a stretch of real tunnel drawn with the game's tiles -- look before you launch
tools/gen_poster.py       poster.png and the Workshop preview, cut from the ladder screenshot (a render without it)
tools/gen_store_art.py    the Steam gallery images (workshop/store/) from design/art/screens/
tools/package_workshop.py stage the Workshop upload (WORKSHOP_ID and VISIBILITY live here)
tools/deploy_windows.py   install as SewarsDev and verify the copy file by file
tools/pzmap.py            the vanilla map: lotheader/lotpack reader, roads, manholes, rooms
tools/tilesheet.py        contact sheet of any vanilla tile set, straight from the packs
tools/pzcatalog.py        every sprite and item id in the installed build
tools/pzapi.py / javarefs.py / javadis.py   does it exist / what does it touch / under what condition
tools/luacheck.py         Lua syntax through a real Lua VM
tools/key_icon.py         generated icon on a key colour -> 64x64 transparent Item_*.png

tests/sim.lua             the simulated engine and network, as unkind as the real one
tests/test_flow.py        the whole loop: single player, then a server and a client
tests/test_layout.py      every generated town read back and walked from its ladders
tests/test_assets.py      every sprite, item, outfit, sound and text key against the game
tests/mutate.py           breaks each guard on purpose; every one must be caught

design/art/               raws, review sheets, renders, plans, screens/ (the author's screenshots) -- never deployed
workshop/                 description.txt, preview.png, store/ (gallery images); workshop/Sewars is the staged package
```

Lua lives in `SEW/` folders and every global hangs off one table, `SEW`
(`SEW.Config`, `SEW.Build`, ...), except `SEWClimb`, which the engine needs as
a global (*Rules*). Log lines start `[SEW]`, and a broken invariant is logged
as `[SEW] WARN`, because that is what `dev.py log` and a reader grep for.

---

## The loop

```sh
# 1. edit, then:
python tools/dev.py              # every static test, then install SewarsDev

# 2. run it -- enable "Sewars [DEV]" (not "Sewars") on the mods screen, new world
python tools/dev.py run

# 3. read what happened
python tools/dev.py log
```

**Mod Lua only loads when a world starts**, not at the main menu, and it is
only re-read on game restart. There is no hot reload. Every code change needs a
full restart. The static checks take a minute; a game round trip takes minutes
and needs the user. Never skip step 1 to save time.

When you touch a guard or add one, also run `python tools/dev.py mutate`
(several minutes): every mutation in `tests/mutate.py` must be caught.

---

## Updating the mod

### Changing a constant

Everything tunable is in `SEW_Config.lua`. Change it, `python tools/dev.py`.

### Changing how the sewers are laid out

1. Edit `tools/gen_sewers.py` (the constants at the top first: widths,
   margins, gaps).
2. `python tools/gen_sewers.py --plans`. It rewrites `Data/` and
   `SEW_Index.lua`, and draws `design/art/plans/<town>.png`. **Look at the
   plans**, then `python tools/render_sewer.py <town> [x y r]` and look at the
   tunnel itself.
3. `python tools/dev.py`. `test_layout.py` walks every town again.
4. The layout's revision is folded into the build revision by itself, so
   built chunks are revisited and their missing hull put back. **But moving a
   tunnel under a save is a migration, not a rebuild**: a player may have
   built in the old one, and nothing removes squares the new layout no longer
   uses. Write the old extent down and decide what happens to it before
   shipping (trekship: `C.LegacyCabin`).

### Changing what the builder puts on a square

Edit `SEW_Build.lua` (and the matching decode in `tools/render_sewer.py`, which
is a second reading of the same legend on purpose -- if they disagree the
render looks wrong). **Bump `C.BuildRev`.** Furniture, dressing and the dead are
placed on a chunk's first build only; a revision puts back floors, walls,
ladders and door frames that are missing and nothing else.

### Changing or adding tiles

Edit `tools/gen_sewer_art.py` (`TILES_DEF` and the painting functions), run it,
**look at `design/art/sewer_art_sheet.png`**, then point `C.Sprites` at the new
index. Indices are sprite names (`sewars_01_<n>`): never renumber an existing
tile, because placed objects in saves name it. Append.

### Adding an item, a sprite or a sound

Look it up first -- `python tools/pzcatalog.py sprites name location_sewer` or
`python tools/pzcatalog.py items Crowbar` -- because a wrong name fails
silently. `test_assets.py` then keeps it honest (sprites, items, obsolete
items, outfits in both lists, sounds declared both ways, text keys both ways).

### Releasing to the Workshop

1. Bump `modversion` in `Sewars/42/mod.info` and `C.Version`.
2. `python tools/dev.py all`, then a fresh world in game with SewarsDev.
3. `python tools/dev.py package --install` stages
   `~/Zomboid/Workshop/Sewars`. Upload from the game's Workshop screen.
4. **First upload only:** it goes up private (`VISIBILITY` in
   `tools/package_workshop.py`). Copy the item id Steam gives into
   `WORKSHOP_ID` there, check the page, set `VISIBILITY = "public"`, upload
   again. Never change `WORKSHOP_ID` after that: without it the uploader makes
   a second item with no subscribers, and that cannot be undone.
5. **The gallery is by hand.** The uploader sends only `preview.png`. The
   captioned screenshots in `workshop/store/` (`the_way_down.jpg` first) go
   up on the item's Steam page: *Add/edit images & videos*.

---

## Rules carried over from the trekship

Each is a paragraph here and a whole section there, where the story of how it
was learned is. These are the ones a sewer mod walks straight into.

### The server owns the sewers; a client asks

Build 42 loads `shared/`, `client/` and `server/` in *every* process. The mod
decides where each piece runs, on line one of each file:

| Folder | Guard on line one | Runs in | Owns |
|---|---|---|---|
| `server/SEW/` | `if isClient() then return end` | single player, any server | tunnels, shelters, spawns, the sewer state |
| `client/SEW/` | `if isServer() then return end` | single player, any client | menus, UI, **its own character** |
| `shared/SEW/` | none | everywhere | config, the protocol, layout data, read-only queries |

- **A client never changes the world.** It asks with a command; a server
  handler validates it (reach, state) against **its own copy** of the player.
- **A client moves only its own character**, after asking, because a server
  with the speed anti-cheat rations long moves. Going down a ladder is a move.
- **The server changes the world only through transmit calls**
  (`transmitAddObjectToSquare`, `transmitRemoveItemFromSquare`, ...). In
  single player they act locally, so there is one code path for all three
  setups.

### The jar is not the API

`tools/pzapi.py` says a method exists. **Grepping vanilla Lua for a call site**
says Lua may call it. **Read the path of the call site**: one under
`AdminPanel/` or `DebugUIs/` proves it works for an admin in a debug build,
which is not a player. You need both checks, and the second is the one that
gets skipped. Our first instance: `IsoChunk.setMinMaxLevel` is in the jar and
nowhere in vanilla Lua (`DESIGN.md` 3).

### A vanilla call site proves reachability, never correctness

And a method whose name is a summary (`RestoreToFullHealth`,
`createContainersFromSpriteProperties`) is a bundle of writes somebody else
chose. `tools/javadis.py` lists the bundle. Read it.

### A runtime-generated interior is not a building

A tunnel raised at runtime has no `IsoRoom` and no `IsoBuilding`. Roofs, rain,
`isOutside`, climbing walls, temperature and the camera's cutaway all key on
those. Before relying on any of them, ask what `getBuilding()` answers down
here -- it will be `null`. In the trekship this let players climb out of the
hull and rained in the cabin.

### A sprite is not the object the engine builds from it

`IsoObject.new(sq, sprite)` gives an `IsoObject` wearing that picture. A
ladder that should be climbable, a door that should open, a container that
should hold things: each needs the right class or the right follow-up call
(`createContainersFromSpriteProperties`, then stock, then `setExplored`,
before sending). Otherwise it is drawn and inert, and looks exactly like one
that works. **Do not place a sprite whose properties would make the engine
build something else on the next load.**

### A right-click lands on the floor, not on the picture

The context menu resolves the square under the cursor on the floor plane.
A ladder drawn up a wall is aimed at a square or two off. Give every
interaction a reach margin (`C.Reach`), and test both ends of it.

### Never build where no player is standing

Chunks stream only round a player, on the server as much as a client. An
unloaded square is not "nothing there", it is "cannot tell yet": return a
reason, write the position down, retry. Build a stretch when its chunks are
loaded, and **hold an arriving player** until the floor under them exists.

### Never let a failure strand the player

Move first (the ground cannot be inspected until somebody is on it), then
build, and if it fails put them back where they came from, with the reason.

### Tag every object you place; never restock

Every placed object carries `C.Tag`. A rebuild keeps tagged objects and never
touches untagged ones -- which, down here, are the player's. A container is
stocked **once, ever**, when it is made. New loot reaches new worlds only.

### State that is transmitted whole cannot hold a list that grows

`ModData.transmit` sends the whole table. Which stretches of every town are
built is a list that grows for the life of the save: give it its own key, and
publish it only when it changes.

### Slice any search that touches thousands of squares, and batch per-square calls

A town's network is thousands of squares. Build it a slice per tick. And a
missing method throws a Java stack trace **per call**: in a per-square loop
use the trekship's `U.batch`, not `U.try`.

### The game runs Lua 5.1

Kahlua: `unpack` is global, `table.unpack` and `math.huge` do not exist,
`math.atan2` does (and throws in the 5.4 tests). **Write Lua with the Write
tool, never shell heredocs** -- they mangle quotes and escapes.

### Every XML file must parse, and never write `--` in an XML comment

The game silently drops the whole file.

### Translations are one JSON file per category, routed by key prefix

`Translate/EN/IG_UI.json` holds `IGUI_*`, `ContextMenu.json` holds
`ContextMenu_*`, `ItemName.json` holds item ids. A key in the wrong file
resolves to nothing, silently. A mod cannot add a category.

### A check against an empty set is not a passing check

Every lookup check needs a floor on both sides. `pzmap.py census` refuses zero
manholes and `town` refuses fewer than 100 road squares for this reason.

### When a test is easy to satisfy, suspect the simulation

And mutation-test anything new: break the code on purpose, confirm the test
fails, and **assert the mutation actually changed the file**.

---

## Rules that are new here

Each was learned building 0.2.0. A heading that says the rule, what it cost,
the evidence, and what generalises. Add to this the day something breaks.

### Below ground is real: z -1 under the street, and the engine draws it

**New in this mod, and the design stands on it** (DESIGN.md 3). Three facts
from the bytecode, each checked before a line of Lua was written:

```
IsoChunk.setSquare          77  getMinLevel / min(z) ... setMinMaxLevel(min, max)
                                -> a square at z -1 grows the chunk's levels down
IsoChunkMap.isWorldSquareOutOfRangeZ   bipush 224 (-32) .. bipush 31
                                -> z is valid from -32 to 31
FBORenderCell.renderInternal 400-428   if player z < 0: maxZ = ceil(z) + 1
                                -> below ground, the street is simply not drawn
```

The third is the one that made it a sewer rather than a cellar with the town
on top of it, and it keys on nothing but the player's z -- not a room, not a
building. `IsoChunk.setMinMaxLevel` itself has no vanilla Lua call site and
is never called by the mod: `getOrCreateGridSquare` reaches it through
`setSquare`, which is the path vanilla's own upstairs building takes.

**Still unproven, and only the game can prove it**: that a runtime z -1
square is lit, pathed by zombies and saved the way a map-loaded basement is.
The in-game checklist below starts there.

### A sprite's properties decide whether it is a floor, not its picture

**New in this mod, caught before the game.** The sewer sheet's sludge
(`location_sewer_01_26`) looks like a floor tile and carries **no
`solidfloor`** -- it is `solidtrans`, water you cannot wade. Laid alone it is
no floor at all to the engine, and a channel square would have been a hole.
It goes over a floor now (`SEW_Build`, floor code `w`), `test_assets.py`
asserts the property both ways, and `tests/sim.lua` decides what is a floor
from the real catalogue. Read `tools/_catalog/tiles.json`, never the picture.

**And where a sprite is drawn is part of what it is (found in play, 0.3.2).**
The same sludge is packed at `oy 64`, not the floor's `oy 192`: its water sits
two thirds of a storey up its square, because vanilla lays it in a channel a
level *below* the walkway. On our walkway it hung in the air against the north
wall, one square off the squares that blocked. `tools/tilesheet.py` shows it
plainly (the water is halfway up the cell); the pack entry's offsets say it in
numbers. Our `sewars_01_26` is the same picture moved down onto the diamond,
and `test_assets.py` checks its bounding box. Before laying any vanilla tile
as floor dressing, look at where its cell puts it.

### A long street is one segment

**New in this mod.** Dixie Highway runs through Muldraugh as a single
straight segment from y 8858 to 11197; both ends lie outside the town. The
first generator kept streets with a *point* inside the town's box, and the
town's main road got no trunk under it -- visible at once on the plan, and on
no test. Streets are kept by bounding-box overlap now. **A plan is a test
nobody can write; look at it** (`design/art/plans/`).

### Render the tunnel before launching the game

**New in this mod.** `tools/render_sewer.py` draws a stretch of the shipped
data with the game's own tiles. Its first picture found three faults no test
could: corridor floors hidden behind full-height south walls (a preview
problem, fixed with a cutaway -- but the same geometry in game is why the
camera's cutaway matters), a tiled checkerboard under every outside wall
(the rock floor was a patterned tile; it is dark earth now), and grime that
read as boxes. It found a fourth on the art sheet: every west-wall word
mirrored. The render is a second reading of the data legend on purpose; if it
and `SEW_Build.lua` ever disagree, the picture shows it.

### Two guards that cover each other hide from a mutation -- and so does a kind network

**The trekship rule, met twice in the first mutation run.** Four of sixteen
mutations were missed at first:

- the server's level check on a climb out was also made by the action's
  `isValid`, and `setExplored` was called both by the builder and by the
  stocker -- each copy hid the other. The level check now has a test that
  asks the server directly; the second `setExplored` was deleted;
- the multiplayer test started at a shaft with no shelter in reach, so
  *every door reached the client* passed at 0 of 0 -- a check against an
  empty set. It starts by a shelter now and asserts there is a door;
- the simulated network always delivered the floor before the move, so the
  client's wait for its floor could be deleted. The test now holds the floor
  back one round and asserts the player waits on the street.

`python tools/dev.py mutate`: sixteen mutations, each asserted to have
changed the file, all caught.

### Kahlua is not Lua 5.4, and the simulation has to say so

**New in this mod, and it made the first play-test unplayable.** The lamp
code called `next(lamps)` every 90 ticks; Kahlua has no `next`. `U.try` caught
the error every time -- and **under `-debug` the game halts on every Lua error,
caught or not**, so the author's game stopped every second and a half. Three
failures lined up:

- the trekship's `pz_sim.lua` removes `next` and `math.huge` and ours was
  written without them -- it now removes `next`, `math.huge` and
  `table.unpack`;
- the test never simply **stood on the street and ticked**, the state where
  that branch runs. It does now, for four hundred ticks, before anything else;
- `tools/dev.py run` launched with `-debug`. It does not any more
  (`run --debug` for the console): a caught error costs a log line, not the
  session.

Also from the same hour: `tiledef=sewars 8823` made the mod **vanish from the
mods screen** -- the engine accepts 100..8189 (`ChooseGameInfo.readModInfoAux`)
and says so only in `console.txt`. `test_assets.py` checks the range.

### A translation's `%1` is a format placeholder, and a `%` beside it breaks it

**New in this mod, found in play (0.3).** The map's footer was
`"%1% walked"`, and the game showed `2$s%`: the translator turns `%1` into a
Java format placeholder (`%1$s`), and a literal `%` next to it is read as part
of the format. Pass anything with a percent sign in as the *argument*
(`getText(key, pct .. "%")`), never in the string. `test_assets.py` fails on
any translation with a `%` that is not a `%<digit>`.

### A window the player cannot close is a trap; use vanilla's

**Also 0.3, from the same play-test.** The map was a bare `ISPanelJoypad`
with its close button bound to the controller's B, which draws a "B" glyph on
it: on a PC that read as a prompt for a pad the author was not holding, and
the map could not be closed. Both windows are `ISCollapsableWindowJoypad`
now -- vanilla's title bar (drag to move), resize handles, the X -- plus
Escape through `isKeyConsumed`/`onKeyRelease` (vanilla's build window's
route), and the B glyph set only in `onGainJoypadFocus` and cleared on losing
it. Tests click the X, press Escape, drag the title bar and resize.

### The street list is not the road, and a layout change must not reshuffle

**Found in play, 0.3.1.** Harris St's centre line in `streets.xml` stops 49
squares short of Irma Dr; the painted road carries on. Its culvert ended in a
wall. The first fix (a longer snap) joined it -- and moved all 20 of
Muldraugh's shelters, because shelter placement is drawn from the tunnel's
shape through a seeded rng. The mod was public by then: in a save that strands
built shelters and points journals at empty tunnel. The fix that shipped is a
late pass (`run_on_road`) **after** the shelters, kept clear of shafts (it
first moved two ladders by opening the wall they hang on). **Before shipping
any layout change, diff the index against the previous one: shelters, shafts
and furniture must be identical** unless moving them is the point.

### Below ground is outdoors to the engine, and other mods ask the engine

**Found by a player (0.3.2): Flying Birds (Workshop 3789637851) flew its
flocks over people in the sewer.** Its birds are a client-side screen effect
that stays away "while the player is indoors", and to the engine the sewer
is not indoors. The trekship's rule (*A runtime-generated interior is not a
building*), met from below:

```
IsoGridSquare.RecalcProperties  463-537  roomId != -1 or haveRoof -> unset exterior, else set it
IsoCell.checkHaveRoof           2-8      z from 31 down while z >= 0   -> nothing below 0 is ever roofed
IsoChunk.loadInWorldStreamerThread 212   roofs down to minLevel, but only under a rain-blocking tile at z >= 1
IsoPlayer.isOutside                      no room and not isInARoom -- the exterior flag is not read at all
```

A tunnel square has no room and no roof, so it is `exterior`, and a player
on one is outside by a rule that does not even look at the flag. Vanilla's
basements escape by being rooms. **There is no engine switch**: `haveRoof`
has no setter; the chunk-load pass would need a roof at z 1 over the street,
which would stop the rain on the street; and `setRoomID` with no room behind
it hands every caller that trusts a room id a null.

So `SEW_Compat.lua` answers where every mod asks: Kahlua looks a Java
method up in `__classmetatables[class].__index`, an ordinary table chained to
the superclass's (`KahluaThread.getClassMetatable`,
`LuaJavaClassExposer.setupMetaTables`). `isOutside` on `IsoGridSquare`,
`IsoGameCharacter` and `IsoPlayer` is wrapped there: **below z 0, no**. It
reaches every Lua caller -- any mod, and vanilla's rain barrels, crops,
campfires, foraging and plowing, all of which counted the tunnels as open
sky -- and none of the engine's Java. The engine's method is kept in the
table under `SEW_isOutsideEngine`, so a second load wraps it and not the
wrapper.

What it cannot reach: a mod that asks `getBuilding()` or `getRoom()` (nil
below, and nothing honest can answer otherwise), and the engine's own
weather -- rain splashes read the square's cached flag in Java (checklist,
*Rain*). The sim models the engine's answer (`SquareMT:isOutside`,
`PlayerMT:isOutside`, `__classmetatables`), and `test_flow` asserts the
unwrapped answer below is *outdoors* before asserting ours is not.

### A tile of ours has no depth: give it the floor's or the wall's

**Found by players on a dedicated server (0.3.1): "the tiles you added cover
the character while walking."** B42 draws with depth textures, and a tile
from a mod's own pack has none. The engine then picks one by property
(`IsoSprite.setupTileDepth`), and a placed object goes in the floor pass only
by property (`FBORenderCell.isObjectRenderLayer_Floor`):

```
isObjectRenderLayer_Floor      sprite.solidfloor or sprite.renderLayer == 1
IsoWorld.LoadTileDefinitions   RenderLayer=Floor  -> renderLayer 1
IsoSprite.setupTileDepth       solidfloor / FloorOverlay / renderLayer 1   -> floor depth
                 560-661       WallOverlay and attachedW (or attachedN)    -> the wall's depth
                               anything else                               -> a default depth
```

Every puddle, smear, debris pile and light pool was an object in the object
pass with the default depth -- drawn over whoever walked across it -- and so
was every stencil, graffito and ladder. Vanilla's own decals never meet this:
the map loads them as part of the floor or wall they sit on
(`CellLoader.DoTileObjectCreation`).

So: **every floor tile of ours carries `RenderLayer=Floor`, every wall tile
`WallOverlay` with its attached edge, and no tile of ours is itself a wall, door
frame or floor.** Where we need a wall of our own look (a cave's earth, a
breach), the wall is vanilla's -- its collision, its depth -- and ours is laid
over it. `test_assets.py` holds all three. Properties are read by sprite name
at load, so objects already in a save are fixed with the tiledef, no
migration.

### A picture on a wall is part of the wall, or the cutaway leaves it behind

**Found in play (0.3.2), the day after the rule above shipped: by a cave's
breach the earth hung in the air over black.** The depth fix made our earth,
breaches, ladders, stencils and graffiti separate objects on the wall's
square. The camera's cutaway is decided per square but applied per object,
and only to walls and what hangs on them:

```
FBORenderCell.renderMinusFloor 34-202   sprite cutN/cutW, or a door/frame -> renderMinusFloor_DoorOrWall
IsoWorld.LoadTileDefinitions            cutN/cutW come from WallN/WallW/... -- never from WallOverlay or attachedN/W
  performDrawWallSegmentSingle 128-159  cut square -> DoCutawayShader(wall), then DoCutawayShaderAttached
renderMinusFloor_NotDoorOrWall 606-630  anything else: a plain render, full height, no cut
IsoObject.save 69-187 / load 185-476    attached sprites saved, loaded and sent with the object
```

So the wall was cut down and our picture stayed full height in front of the
dark behind it. Vanilla never meets this: a player's wall overlay is attached
to the wall (`ISMoveableSpriteProps`: `AttachExistingAnim`, then
`transmitUpdatedSpriteToClients`), and the map loads decals onto their wall.
**Every picture of ours on a wall is now attached to the wall or door frame of
ours on its edge** (`SEW_Build`, *Pictures on walls*); only one with no wall to
hang on is still an object. Build revision 5 moves an old save's loose ones
on to their walls (`B.rehang`, ours only). `U.findSprite` does not see an
attached sprite: ask `B.hasPicture`. `test_flow` checks none is left loose,
an old save's are moved once, and a client gets them on its wall.

The general rule: **a property fix is not a render fix.** The depth rule above
was right and was checked by property; how the renderer *groups* objects was
never looked at, and only the game showed it.

### A tile name in the catalogue is not a picture in the packs

**New in this mod (0.4, caves).** `boulders_36..39` are in
`tools/_catalog/tiles.json` with a property each -- and have no picture in
any pack. Placed, they would have drawn nothing and said nothing. Found only
because the art was looked at before use (`vanilla_cells` refused them).
`test_assets.py` now cuts every cave floor and stone out of the packs; do the
same for any vanilla sprite that has not been seen on a contact sheet.

### Louisville is ten Muldraughs: anything per square must be linear

**New in this mod (0.4).** Louisville's district is 76 map cells and 325,000
squares of tunnel -- half the mod. `test_layout.py` had `min(xs)` inside a
per-square comprehension since 0.2: invisible for a town of 40,000 squares,
over ten minutes for Louisville. Hoist anything whole-town out of a loop, and
when a test gets slow, profile it before waiting on it
(`cProfile`: 84,903 calls to `min` took 35 of 36 seconds).

### `U.hash(x, y) % 2` is a checkerboard

**New in this mod (0.4, caves).** The position hash's multipliers are odd,
so its parity is `(x + y)`'s, and a two-way pick by `% 2` tiled the first
cave floor like a chessboard (seen on the render). Pick by `% 5 == 0` or any
modulus that is not a power of two.

**And any small modulus of it is a pattern (0.5).** `% 3` striped the rats'
nest's floor in diagonal bands on its first render: both multipliers are 2
mod 3. A per-square pick from a hash goes through one step of `U.rng`
(`U.rng(U.hash(x, y, k))(n)`); `render_sewer.py` mirrors it (`lua_rng1`).

**And `U.hash(x, y, k)` for k = 1, 2, 3 is a walk, not a draw (0.3.2).** It
is linear in `k`, so over a list of ten it steps by one: `U.fill` walked the
list and every last stand's crate held every gun on it. A run of choices from
one seed uses `U.rng(seed)` (Park-Miller, exact in a double).

### A default key is someone else's, and a saved key outlives a new default

**Found by a Workshop comment (0.3.1): the map's N is vanilla's Start/Stop
Engine**, so every keyboard player had a clash, and the map opened in a car.
Before choosing a default, read vanilla's `media/lua/shared/keyBinding.lua`:
K is the only letter it leaves unbound (and `Keyboard.KEY_NONE` is always an
option). And `PZAPI.ModOptions:save()` writes every mod's options whenever a
player accepts the options screen, so changing the default does nothing for
anyone who has: the option's **id** changed (`sewerMap` -> `sewerMapKey`),
and `load()` keeps the old line unread. `tests/sim.lua` loads ModOptions.ini
the same way, starting from a 0.3.1 player's file.

### A mod cannot add an action group, and an animal without one stands still

**Found in play (0.5): the ROUS "just stand around and don't attack".** The
first build gave them an action group of our own (`media/actiongroups/rous`,
the rat's plus a pig's attack state), because an animal bites only from the
`attack` state of its group, and the rat's has none. The DEV_GUIDE entry
before this one said mods' folders were probably seen. They are not:

```
IsoAnimal.initType              25-39   ActionGroup.getActionGroup(adef.animset)
ActionGroup.load         21-30, 53-62   getMediaFile("actiongroups/<name>/actionGroup.xml")
ZomboidFileSystem.getMediaFile   0-39   new File(workdir, path) -- the game's folder, never a mod's
ActionGroup.getInitialState      0-49   no states: null, and a debug-channel line only
```

`AnimSets/` do load from mods (`AnimationSet.Load` -> `resolveAllDirectories`),
which is what made it look possible. With no group the animal has no states
at all -- no walk, no path, no attack -- and nothing is logged. And even with
one, `goAttack` alone never bites: `fightAnimal` needs a `fightingOpponent`
that only vanilla's own `spotted` and `checkAttackBehavior` set, and Lua has
no setter; `attackBack` acts only on a server.

So the ROUS keeps the rat's `animset`, and the chase and the bite are ours
(`SEW_Nest.hunt`): the engine's `pathToCharacter` first, walked by hand a
step a tick when it makes no headway (never across an edge `isBlockedTo`
says is a wall), and a bite on a timer made on the server's copy of the
player and sent with `syncBodyPart`, as vanilla's own health command does.
**What generalises: an animal type from a mod can only reuse a vanilla
animset**; anything it does beyond that animal's behaviour is Lua.

Also from the engine, for anyone adding an animal: `addAnimal` has no role
check in Java (vanilla's `AnimalCheats` check is in its Lua); the constructor
registers the animal and `AnimalSynchronizationManager` sends it to clients;
a chunk saves its animals at every level (`AnimalPopulationManager.
removeChunkFromWorld`); the definitions are read once, after mod Lua loads,
so a shared file can add one. `addAnimal` takes x, y as given -- a whole
number is the square's north-west corner, on its wall line (found in play:
rats beyond the tunnel walls); stand it at x + 0.5. `collidable` is animals
pushing each other, not walls. And the pathfinder is not told of levels a
runtime square adds below 0 (`setMinMaxLevel` notifies nothing; a chunk's
levels reach it when the chunk is added), so an animal wandering down here
may path through our walls: the server leashes every animal below ground
back onto the walkway (`SEW_Nest.leash`). Unproven either way; watch for it.

Also from the engine, for anyone adding an animal: `addAnimal` has no role
check in Java (vanilla's `AnimalCheats` check is in its Lua); the constructor
registers the animal and `AnimalSynchronizationManager` sends it to clients;
a chunk saves its animals at every level (`AnimalPopulationManager.
removeChunkFromWorld`); the definitions are read once, after mod Lua loads,
so a shared file can add one. A wild animal only flees; only a tame one
attacks unprovoked (`attackIfStressed`, stress over 80).

### The shell mangles escapes, and it will do it to you

**The trekship's rule, broken three times in one session -- and again in
0.4.** A heredoc turned `\b` into a backspace in a regex and `\n` into a
newline in a string, and each cost a round of confusion because the file
*looked* right in a terminal. In 0.4 a Python edit script fed through a
heredoc put two literal backspaces into `render_sewer.py`'s regexes; the Edit
tool then could not match the line, which is how it was found
(`grep -c $'\x08'` finds them).
Write Python and Lua with the Write/Edit tools, or a script file written by
them. Never a heredoc for anything with a backslash in it. (0.5: twice more,
a `\n` in a patch fed through a heredoc; both caught because the patch
asserted its match and wrote nothing.)

---

## Art

The art pipeline is the trekship's (its DEV_GUIDE *Item icons*, *Source art
lives in design/art*, *Vet icons*), with tiles as the main output rather than
items.

**What exists (0.2.0)**: `sewars_01`, 26 tiles drawn by
`tools/gen_sewer_art.py` -- the two ladders (vanilla's picture, no climb
property), EXIT stencils, seven graffiti pieces (KEEP OUT, THEY HEAR YOU, DONT
GO DEEPER, a tally with DAY 31, hand prints, UP, an eye), SAFE / KNOCK 3 by
every shelter door, grime, puddles, debris, a light pool under every cover
and a smear -- each in both wall facings, projected onto the game's own wall
and floor geometry. Walls vary between vanilla's plain, stained and panelled
pieces by position. `design/art/sewer_art_sheet.png` is every tile on
vanilla's wall, lit dim.

**What is next**: the pieces a script paints badly -- arched brick vaults,
round culvert mouths, a cover seen from below with light through its holes,
rusted grilles, shelter set-dressing -- with the image models, then keyed,
cut to the 128x256 cell and added to `TILES_DEF`.

**Tools**

- **Flowdot** (`flowdot` and `flowdot-local` MCP servers, configured in
  `.mcp.json`) runs the image and asset workflows. They must be enabled in
  the Claude Code session to be used.
- **Gemini toolkit**: `generate-image` for paint, `analyze-image` for a
  critique of a contact sheet at game size.
- `tools/tilesheet.py` renders any vanilla tile set out of the packs, so new
  tiles are always judged **beside the vanilla ones** they sit next to.
- `tools/render_sewer.py` shows them in a real stretch of tunnel.

**Rules**

- **Keep the raw.** Every generated original goes in `design/art/<category>/`
  as `.png`, with the sheet it was judged on. `design/` is never deployed.
- **Generate on a flat key colour and measure it**; `key_icon.py` samples the
  border rather than assuming `#FF00FF`.
- **Tiles are 128x256 at 2x**, the floor diamond's north-west corner at
  (64, 192) of the cell; a west wall is the face (64,192)-(0,224) up 192 px,
  a north wall (64,192)-(128,224). **Writing on a west wall runs from x 0 to
  x 64**, or it comes out mirrored.
- **Never renumber a tile.** `sewars_01_<n>` is saved in every placed object.
- **Judge at game size, in the dark.**
- **Never commit `.mcp.json`**: it holds API tokens. It is in `.gitignore`.

---

## Testing

### Static, no game needed -- `python tools/dev.py check`

| Check | Catches |
|---|---|
| `tools/luacheck.py` | Lua syntax, generated data included |
| `tests/test_assets.py` (71 checks) | every sprite in the config and the generator against the catalogue and our tiledef; floors really solidfloor and sludge not; doors and frames what they claim; items exist and are not obsolete; outfits in both vanilla lists, ordinary ones with no bag and equipped ones with one; sounds declared both ways with non-empty wavs; text keys both ways, in the right category files; sandbox options have words; every file's side guard; no role-gated or debug-only call |
| `tests/test_layout.py` | every town read back from the shipped Lua: records well formed, every shaft a grating under its cover and a ladder where the index says, **every walkable square reachable from a ladder** (walls block, doors pass, sludge does not hold you), one door per shelter, furniture on shelter floors, nothing under a building or a basement -- and a self-check that the walker really reads walls |
| `tests/test_flow.py` (49 checks) | the real Lua on `tests/sim.lua`: single player, then a server and a client -- the menu, the walk, the action rebuilt on the server by name, the build before the grant, the client waiting for its floor, the vault switch, lamps, the slice builder finishing, no duplicates on a second pass, stocking (a few picks, not a crate full), the outfit mix by sandbox, the map key (K, not a saved N, never in a car), the dead (and none on the player), a shut cover greyed out, refusals, the rescue, somebody else's underground left alone, the client editing nothing, doors reaching the client as doors, no WARN, no unknown sprite or text key |
| `tests/mutate.py` (`dev.py mutate`) | 68 guards broken one at a time; every one must be caught |

`tests/sim.lua` is as unkind as the engine where this mod leans on it: orphan
squares throw, floors come from real tile properties, containers drop what
does not fit, `instanceItem` knows only real ids, outfits must be in both
lists, `sendServerCommand` is inert in single player, a client's timed action
reaches the server only by class name and `new`'s parameter names, and the
server's objects reach a client only if it has the chunk. What it cannot tell
you: lighting, rendering, pathfinding, saving -- the game's own.

### In game

Enable **Sewars [DEV]**, new world, `-debug` (`python tools/dev.py run`).
Debug console (single player, or an admin's server log):

| Function | Does |
|---|---|
| `SEW_Here()` | where you are, the chunk, its town and build revision, the nearest shaft and its street |
| `SEW_Build(r)` | build every chunk within r (default 3) of you now |
| `SEW_Rebuild()` | forget which chunks are built; the next pass puts back missing hull (never furniture or the dead twice) |
| `SEW_GoLair()` | into the house by the hatch nearest the rats' nest under Louisville |
| `SEW_Lair()` | the nest: where, which of its walls are open, how many ROUS are alive near it |

### On a dedicated server

```sh
PZ="$USERPROFILE/Zomboid/PZ-Worlds.ps1"
powershell -File "$PZ" new sewtest -Template servertest
powershell -File "$PZ" mods sewtest enable SewarsDev
powershell -File "$PZ" start sewtest                     # join at 127.0.0.1:16261
powershell -File "$PZ" stop
```

A test harness only; nothing in the mod may depend on it.

### Watching the log

```sh
python tools/dev.py log        # after a run: the mod's lines, every WARN, errors naming the mod
tail -F -n 0 "/c/Users/Arcade/Zomboid/console.txt" | grep -E --line-buffered "\[SEW\]"   # live
```

**Check the timestamp** before drawing conclusions; the log is overwritten
each launch.

---

## Working with the user

They run the game and report what they see; that is the only way most of this
gets verified.

- **Be explicit about what is verified and what is not.** Static checks
  passing is not the same as it working in game.
- **Warn before anything destructive** to a save, *before* they load in.
- **They will spot real bugs from symptoms.** Investigate the report; do not
  explain it away.
- The author spells it *Sewars*: that is the mod's name and id. In-game text
  a player reads says *sewer*.

---

## Current state

Version **0.3.2** (local, not yet on the Workshop), build revision **5**,
layout from `tools/gen_sewers.py`. 2026-09-29. **Workshop:** item
**3810188405**, public, 0.3.1 uploaded 2026-09-29; `WORKSHOP_ID` is set in
`tools/package_workshop.py`.

**Built and passing every static test**: the whole loop (covers, the climb
down, tunnels under 31 towns -- 442 shafts under the map's covers and 732
under covers of ours, 239 shelters, 152 caves, 189 hatches, 475,777 walkable
squares, 4 covers left shut because they are over buildings), ladders out,
vaults and the sludge channel, shelters behind steel doors with stocked
crates and shelves and sometimes their dead, zombies below by sandbox
density, rescue, lamps at the shafts and shelters, ambience, 36 tiles of our
own, four sounds, the poster, the Workshop package (unpublished, private).

**Not yet seen in game** -- the checklist, in order:

1. **Muldraugh, any manhole in the road.** Right-click: *Climb down into the
   sewer*. The bar, the lid's scrape, and you are at the foot of a ladder.
   `console.txt`: `[SEW] ... climbs down at x,y (muldraugh; N chunks built)`.
2. **Below.** Is the street gone from view? Is it dark with a pool of light
   under the cover? Walls, the grating under you, the ladder on the wall.
3. **Walk.** Tunnels ahead build as you go; no falling, no stuck spots.
   Doors of the shelters open and shut. Crates hold loot.
4. **The dead.** Are there some, do they come at you, do they path round
   corners?
5. **Build something** down there, leave, come back: still there.
6. **Another ladder.** *Climb out to the street*: up on the right cover.
7. **Save and reload below.** Still standing on the floor; lamps come back.
8. **Rain** on the street while you are below: none in the tunnel. The
   engine still calls the tunnel outdoors (*Below ground is outdoors to the
   engine*); if rain is drawn down there, that is why.
9. **A dedicated server** (above): the same, and a second player sees what the
   first opened.
10. **Other mods think you are indoors.** `console.txt` at load:
    `[SEW] compat: below ground is indoors (IsoGridSquare, IsoGameCharacter,
    IsoPlayer)` -- a `WARN` there means a class was not found. With Flying
    Birds on: flocks on the street, none below.
11. **A cave (0.4).** A new character in SewarsDev starts on the cover
    nearest a Muldraugh cave (`[SEW] dev build: started at the cover ...`,
    which names the breach). Down, a short walk to a hole knocked through the
    wall, a dirt passage, a hideout with a candle's glow, a bedroll and two
    crates. `SEW_Caves()` lists them, `SEW_GoCave(n)` hops to any.
12. **A house with a way down (0.4).** `SEW_GoHatch()` puts you in a Muldraugh
    house with a hatch; within a few seconds `[SEW] hatch at ... opened` and
    a trapdoor in the floor. *Climb down through the hatch*, the culvert, the
    ladder back up into the house. `SEW_Hatches()` says which are open. The
    open question: whether B42's random basements are in z -1 when the server
    first looks (see ROADMAP).

13. **Louisville (0.4).** Walk its streets: covers appear in the road at
    junctions within a few seconds of coming near (the server puts them in;
    a cover further off appears as you approach). Down one: tunnels under
    the streets, shelters, caves. The old strip at x 12860-13009 is still
    its own network.
14. **Nothing draws over the character** (0.4, a player's report): walk over
    a puddle and a light pool, past graffiti, a ladder, an earth wall.

15. **The rats' nest (0.5).** A new character in SewarsDev starts in a
    Louisville house by its hatch (`[SEW] dev build: started by the hatch
    ...`, which names the false wall). Down the hatch, along the culvert to the
    street tunnel, and a few squares on: a wall with cracks and a gnawed hole
    at its foot on the trunk's west wall, and *R.O.U.S. THEY EXIST* nearby.
    Right-click it: *Pull at the loose bricks*. The run, the nest, and four
    big rats. **Do they come at you, and do they bite?** (*It bites!*, a
    scratch or a cut on a limb.) Do they walk smoothly or glide (glide: the
    engine's path failed below ground and they are walked by hand)? **Can
    you shoot and hit them**, and how many hits do they take? Every hit is
    logged: `[SEW] a ROUS was hit by ... health ...` -- no line at all means
    the shots never reach them. *Tear through the gnawed wall* (the clawed
    brick on the nest's west side) is refused while one lives, and gives
    after; the hoard behind it. `SEW_Lair()` says what the server sees.
16. **Rats (0.5).** In any tunnel opened up in a new world: vanilla's rats,
    running from you, and none beyond the walls (a new world: the first test's
    rats were put on the corners of their squares). Save and reload below:
    are they still there?

Known limits: only named streets get full tunnels (unnamed lanes and car
parks get the culverts that join their covers); the art is procedural until
the image-model pass; the poster is a render.

A git repository (main).
