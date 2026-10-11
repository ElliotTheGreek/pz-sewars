# Sewers on a server

For whoever runs a server with **Sewers Under Every Town**: what to install,
every setting and what it really does, the admin's tools (who may use a way
down, new ways down, tunnels drawn on the map, deeper levels, rooms set
down, ground marked as indoors), and the languages the mod speaks. `README.md` is what a player gets;
this is what a host gets.

Everything here is in the mod itself (Workshop **3810188405**, Mod ID
**`Sewars`**).

---

## Installing

| | |
|---|---|
| Workshop ID | `3810188405` |
| Mod ID | `Sewars` |
| Game | build 42 (written against 42.21) |
| Map | none: it adds no map folder and overwrites no vanilla file |

Add both ids to the server's config and restart. Every player needs the mod.

**Adding it to a running world is fine.** Nothing is built ahead of time:
the server builds a stretch of tunnel when a player first comes near it, so
an old world fills in as people explore. A world that never had the mod
uses the defaults below for every setting. **Taking it out** of a world is
the risky direction: have everybody on the street first.

**The server decides everything.** Tunnels, loot, the dead, digging, who may
climb and which ways down are open are all decided and saved on the server.
A client only ever asks.

---

## The settings

The sandbox has a page called **Sewers**. In a server's
`<name>_SandboxVars.lua` the same settings are the `Sewars` table (the id
keeps the old spelling). The numbers are what goes in that file; the first
column of each table is the name to use.

```lua
Sewars = {
    Zombies = 3, Outfits = 2, Loot = 3, Rats = 3, Gas = 3,
    Digging = 3, StreetHears = 1, ExitSigns = 3,
    Access = 1, Hatches = 1, Outfalls = 1,
    Drains = 1, DrainFit = 2,
    Nest = 1, Rous = 2, CultDead = 4,
    Labyrinth = 1, MazeDead = 4,
    Passage = 2,
    MazeX = 8922, MazeY = 10322,
},
```

A world from before a setting existed uses its default.

### Who may go down

| Setting | Values | Default | What it does |
|---|---|---|---|
| `Access` *Ways into the sewers* | 1 Open, 2 Closed until an admin opens them | 1 | Open: anybody climbs down any cover, trapdoor or grate. Closed: nobody but an admin does, until an admin opens that one. A setting never closes a way *out*. See *Who may use a way down* below. Takes effect at once, both ways. |
| `Passage` *Longest passage to a new way down* | 1 20 squares, 2 40, 3 80 | 2 | How far the nearest tunnel may be from a way down an admin puts on a street. |
| `Hatches` *Trapdoors in houses* | 1 Yes, 2 No | 1 | Some garages, kitchens and storerooms get a trapdoor in the floor with a ladder to the sewer. No: no house gets one from now on. A trapdoor already in a floor stays. |
| `Outfalls` *Storm-drain outfalls* | 1 Yes, 2 No | 1 | The iron grates in riverbanks and lakeshores. No: none is put in from now on. One already in a bank stays. |

| `Drains` *Kerb storm drains* | 1 Yes, 2 No | 1 | The iron grates at the kerbs of the game's own streets, 378 of which have a ladder and a short culvert to the sewers under them. Yes: a player squeezes down one. No: they are bolted down, and nobody but an admin goes down one. A ladder under one takes a player up whatever this says. At once, both ways. |
| `DrainFit` *Who fits through a kerb drain* | 1 Anybody, 2 Not the overweight or overloaded, 3 Only the slim and lightly loaded | 2 | A kerb drain is narrow. 2: a character at or over the game's weight for its High Weight trait (85; Very High Weight is 100) does not go down one, and nobody carrying more than they can carry (the Weighed Down moodle) goes down or comes up one. 3: the same, and nobody carrying more than half of what they can carry. 1: no limit. At once. |

**Kerb drains, and what the size limit never does.** It is asked of the
server's own copy of the player, and the player's menu says which of the
two it is (*too big*, or *carrying too much*). On the way **up** only what
is carried counts: it can be put down at the foot of the ladder, so the
limit shuts nobody in. Every drain's culvert joins tunnels that a manhole's
ladder serves. Manhole covers, trapdoors, outfalls and ways down an admin
puts in are never limited. The grates are the map's own: nothing is put on
the street, and the 275 that are too far from any tunnel are greyed out
for everybody (*choked with silt and leaves*). An admin's *This way down
is* works on a drain as on any cover; an admin goes down a bolted one, and
fits or does not like anybody else.

`Hatches = 2` is the one most roleplay servers want: a player's house never
grows a back door into the sewers. The trapdoors are decided house by house
the first time a player comes near, so set it **before** the world is
explored. If you turn it back to Yes later, the houses nobody had a trapdoor
in get theirs then.

### What is down there

| Setting | Values | Default | What it does |
|---|---|---|---|
| `Zombies` *The dead in the sewers* | 1 None, 2 Few, 3 Some, 4 Many | 3 | The tunnels' own dead, put down when a stretch is first built. |
| `Outfits` *Who the dead were* | 1 Mostly ordinary, 2 Mixed, 3 Survivors | 2 | How many of them came down with a full pack. |
| `Loot` *Shelter supplies* | 1 None, 2 Scarce, 3 Normal, 4 Plenty | 3 | What is in a shelter's or hideout's crates when first found. Journals and sewer plans are there regardless. |
| `Rats` *Rats in the sewers* | 1 None, 2 Few, 3 Some, 4 Swarming | 3 | The game's own rats. |
| `Gas` *Sewer gas* | 1 Off, 2 Mild, 3 Harmful, 4 Deadly | 3 | How much poison a minute in the gas gives, and how far it goes. Off also leaves out the haze and placards. |
| `ExitSigns` *EXIT stencils* | 1 None, 2 Few, 3 By every ladder | 3 | The EXIT stencils by the ladders. |

All of these act on tunnels **not yet built**. A stretch somebody has already
walked keeps what it was given: the mod never restocks a crate and never
puts the dead down twice.

### What players may do

| Setting | Values | Default | What it does |
|---|---|---|---|
| `Digging` *Digging in the sewers* | 1 Off, 2 Picks and hammers, 3 Picks, hammers and explosives | 3 | Whether rock can be dug and tunnel walls knocked through, and whether a bomb opens the rock round it. At once. |
| `StreetHears` *The street hears the sewer* | 1 No, 2 Yes | 1 | No: zombies on one side of the street's surface do not come to a player on the other, and a chase is dropped at the cover. Yes: the game's own rule. At once. |

### The set pieces

| Setting | Values | Default | What it does |
|---|---|---|---|
| `Nest` *The rats' nest* | 1 Open, 2 Sealed | 1 | Sealed: the false wall under Louisville will not come away, and pulling at it is not offered. A wall already down stays down. At once: unseal it the day of your event. |
| `Rous` *Rodents of unusual size* | 1 Weak, 2 Normal, 3 Tough, 4 Monstrous | 2 | Blows of any weapon to put one down: 2, 3, 6 or 12. Bullets: 1, 2, 4 or 8. A shove always throws one back. At once. |
| `CultDead` *The dead in the temple* | 1 None, 2 A few, 3 Half, 4 All | 4 | How many of the cult's dead stand in their temple. Parts of it not yet walked into. |
| `Labyrinth` *The labyrinth* | 1 Yes, 2 No | 1 | No: its trapdoor and the hut over its way out are not put in, and its annotated map is not handed out. If they are already in the ground they stay. |
| `MazeDead` *The dead in the labyrinth* | 1 None, 2 A few, 3 Half, 4 All | 4 | All is about a thousand, put down a corridor at a time as players walk. Corridors not yet walked. |

**There is no switch for the temple or the caves**, on purpose. Both are
joined to the tunnels through holes in the tunnel walls, and those walls are
part of what is saved under every town: a setting that walled them up could
be turned off again later and would then tear down something players had
built against. What you can do instead: close the temple's trapdoor to
players (below), set `CultDead`, and treat the two passages into it as
somewhere your story has not got to yet.

### If another mod is in the way

| Setting | Values | Default | What it does |
|---|---|---|---|
| `MazeX` *The labyrinth's place: east* | 0 to 100000 | 8922 | The square the labyrinth's trapdoor is on, counted east. The whole labyrinth goes with it. **At the next start, and before anybody has found it.** |
| `MazeY` *The labyrinth's place: south* | 0 to 100000 | 10322 | The same square, counted south. |

**Leave these alone unless you have to.** They are for one case: another
mod has something in the ground the labyrinth is in (a map of its own, a
bunker, a base, a dungeon), and the two would be built through each other.

**What the mod has in ground that is otherwise empty**, so you can tell
whether anything of yours is in it:

| | Squares east | Squares south | Level | On the surface |
|---|---|---|---|---|
| The labyrinth | 8922 to 9178 | 10322 to 10578 | -1 | A trapdoor at 8922, 10322; a brick hut three squares a side round 9051, 10442 |
| The temple and its two passages | 11505 to 11595 | 8330 to 8755 | -1 | A trapdoor at 11544, 8582 |

That is map cells 34 to 35 east, 40 to 41 south for the labyrinth, and
cells 44 to 45 east, 32 to 34 south for the temple (a cell is 256 squares).
Everything else the mod builds is under a town's own streets.

**Only the labyrinth can be moved.** Nothing leads to it, so nothing else
has to move with it. The temple is cut into the sewers of two towns and
the nest and its caves into Louisville's: a setting that moved one would
leave holes in tunnel walls leading nowhere. If another mod is in the
temple's ground, say so on the Workshop page.

**How the two numbers work:**

- They are the square of the **trapdoor in**, which is the labyrinth's
  north-west corner. The labyrinth is the 256 squares east and the 256
  south of it. The hut over the way out stands 129 squares east and 120
  south of the trapdoor.
- **It moves in steps of 8 squares**, to the step nearest what you wrote:
  the labyrinth is kept by the game's chunks of eight squares.
- **All of it moves**: corridors, rests, caches, the dead, the heart and
  its reward, the hut, the labyrinth's sheet of the sewer map, and the
  annotated map that leads to it, which shows the ground round the new
  place with its X on the trapdoor. Where the game's own map has no
  ground, that sheet is blank paper with the marks on it.
- **A place on or within 24 squares of any town's sewers is refused.** The
  labyrinth stays at the mod's own place and the log says which town was
  in the way (*When something goes wrong*, below).
- **That is all the mod checks.** What else is on or under the ground
  there is yours to know. Choose ground that:
  - **exists**: on the game's map or on a mod's map. With no ground at
    street level there is nothing to put a trapdoor in;
  - **has nothing under it**: a square that already holds something below
    ground is left alone, as anywhere in the sewers, and a corridor with a
    basement through it may be a corridor with no way past. The log says
    so: `chunk ...: n squares already hold something underground`;
  - **is dry and open at the two places on the surface**: the trapdoor,
    and the hut 129 east and 120 south of it.

**When to set them.** Before the world is made is best. They are read
once, as the server (or a single player game) starts: a change while it
runs waits for the next start. **In a world where the labyrinth has
already been found**, what was built stays in the ground at the old place,
with its trapdoor and its hut, and nothing leads down to it any more; the
new one is built whole at the new place, with its own dead and caches. What
players had on their sewer maps of the old one is not carried over.

Players need nothing: each client is told by the server where it is.

**Untried in the game.** Moving it is tested in simulation: a world
started with `MazeX = 9722, MazeY = 9826`, and every check the labyrinth
has run again at the new place (`tests/test_flow.py`, `place_test`). Those
two numbers are the test's and no more than that: nobody has looked at
what stands there.

### What a setting cannot do

- **Change what is already built.** The mod's first rule is that a built
  stretch belongs to the players. Settings that fill a place (the dead,
  loot, rats, stencils, the set pieces' dead) decide it once, when that
  place is first walked into.
- **Move or remove a tunnel.** The layout is the same in every world, but
  for where the labyrinth is (above).

---

## The admin's tools

Everything in this section is on one menu. As an admin, right-click:
**Sewers (admin)**. What is under it depends on where you clicked and where
you stand. Every one is asked of the server, which does it only for an
admin and says in a line what it did, or why not.

**Who is an admin.** Anybody whose role has any of the game's admin tools:
the same test the game uses to show its own admin button. A moderator or a
game master counts; an ordinary player does not. The server asks its own
copy of the player, never the client's word for it. **Single player** has
no roles: the menu is there with `-debug`, for trying things out.

### Who may use a way down

A *way down* is anything a player climbs down through: a manhole cover, a
kerb storm drain, a trapdoor in a house, an outfall's grate, the temple's trapdoor, the
labyrinth's, and any you put in yourself.

Right-click one, *Sewers (admin)*, **This way down is**:

| | Players climb down | Players climb up |
|---|---|---|
| *Open both ways* | yes | yes |
| *A way in only* | yes | no |
| *A way out only* | no | yes |
| *Closed both ways* | no | no |

The way it stands now is greyed. Pick another and every player's menu
changes at once: a way they may not use is greyed out for them, with a
line saying it is sealed, and the server refuses it whatever a client asks.

- **Admins use every way down, whatever it is set to.**
- **The sandbox never shuts anybody in.** `Access = 2` makes every way down
  *a way out only*. A way that is no way out is only ever one you chose, on
  that one cover: *a way in only* is how you make a pit, and *closed both
  ways* seals a cover for good. Before you use either, make sure the
  tunnels under it have another way out, or mean it.
- Only the ways down that differ from the setting are remembered, so
  changing `Access` later does what you would expect.
- It changes nothing in the world: no object is added, a closed cover looks
  like any other.
- Not the labyrinth's way out, which opens from below only, for everybody.

### A way down, wherever you want one

On a street (or any ground at street level), right-click the exact square,
*Sewers (admin)*, **Put a way down here**: *a manhole cover*, *a trapdoor*
or *a storm-drain grate*.

The server puts the cover on that square, a ladder under it, and digs a
passage from its foot through the rock to the nearest tunnel, by the
shortest way, no longer than `Passage`. If a tunnel is right under the
square it needs no passage. You are told how long the passage came out.

- Refused: where there is a way down already; where no tunnel is within
  reach (*No tunnel near enough*: raise `Passage`, or draw a tunnel there
  first); in the labyrinth.
- The passage will not go through anybody's basement.
- It is a way down like any other from then on: players use it, you can set
  who may, and it is on the map of whoever has used it.
- **Take this way down away** is on the menu of one you put in: the cover
  and the ladder go; what was dug stays, as a dead end you can use again.

### Deeper levels

The sewers are one level under the street. Your own works can go two
levels further: **level 2 and level 3**. Nothing is down there until you
make it, and the map's own bunkers and basements at those depths are left
alone as they always were.

Stand in a tunnel, right-click, *Sewers (admin)*, **Put a shaft down to
the next level where I stand**. A cover appears in the tunnel's floor
under you and, below it, one square of the next level with a ladder.
Players climb down it like any cover, and up its ladder again: by the
right-click menu, or by standing at the ladder's foot and pressing their
Interact key.

From there, draw tunnels at that level on the map (next), set rooms down,
or let players dig: **a pickaxe and a bomb work at every level**, with the
same rules and the same sandbox setting.

Each level has its own map: the button at the foot of the sewer map goes
*Level 1*, *Level 2*, *Level 3*. What is drawn or dug shows in that level's
colour: blue, red, yellow. A player's map of a level is what they have
walked of it.

### Tunnels, drawn on the map

Open the sewer map (*Open the whole sewer map* on the admin menu shows all
of it, with no fog and every ladder). At its foot, an admin has a pen:

1. **Draw**: click it for *1 wide*, again for *3 wide*, again for *5 wide*,
   again to put the pen away.
2. **Joined** / **Apart**: click to change. *Joined*: where the new tunnel
   meets or crosses one that is there, the walls between come down and they
   are one. *Apart*: it is walled off from anything it runs beside, and
   refused if it would cross anything.
3. Pick the level with the level button.
4. Click on the map where the tunnel starts, then where it ends. It runs
   straight, along whichever way is further. Escape lets go of a start.
   Drag still moves the map.

One wide is a culvert, three a main, both in concrete; five wide is a
trunk, in brick. Up to 200 squares at a time; draw again from its end for
more, or to turn a corner.

- A tunnel may run through ground nobody is near. It is written down at
  once and built when somebody comes, exactly as the mod's own tunnels are.
  If it meets somebody's basement on the way, that square is left alone.
- Where you can see the ground is loaded (you are there), a run through a
  basement is refused whole instead.
- Never through the labyrinth.
- What you draw is kept exactly as what players dig is kept: it is theirs
  to dig on from, wall off and build in, and no update of the mod moves it.

### Rooms

Stand in a tunnel beside the wall you want the room behind. Right-click,
*Sewers (admin)*, **Set a room down behind the wall to the** *north*,
*east*, *south* or *west*, and choose:

- **Maintenance room**, **Pump station**, **Squat**, **Last stand**: a copy
  of one of the mod's own, with its door on the wall you chose, its
  furniture stocked as a new shelter's is (by `Loot`), and its dead, who
  come once nobody is standing there.
- or one of **your own rooms** (below).

It needs solid rock where it goes: *Something is already dug there* means
try another wall or move along.

**Your own rooms.** Build a room anywhere, at any level, with whatever you
build with: walls, floor, furniture, crates, a door.

1. Right-click one corner of it, *Sewers (admin)*, **Mark a corner here**.
2. Right-click the opposite corner, **Keep the box from the corner to here
   as a room, stocked with** and a kind of stock: *nothing*, *medical
   supplies*, *military gear*, *guns and ammunition*, *police gear*,
   *survival gear*, *food*, *tools*, *car parts*, *electronics* or
   *laboratory gear*. Up to 16 squares a side.

It is kept by its stock's name and a number (*Food 1*, *Food 2*). From
then on it is on the *Set a room down* menu beside the mod's four: a copy
goes down behind the wall, its box centred on where you stand with an
opening there, every object as it was, every container stocked with that
kind of stock (by `Loot`), and a concrete hull round the outside. **Forget
a room** takes one off the list; copies already set down stay.

- A copy is not turned: it goes down the way round it was built.
- Doors come out as doors and containers as containers. Other things that
  do something (a light switch, a generator, a window) come out as their
  picture only.

### Indoors

Below the street nothing is indoors to the game unless the map made it a
room. A basement a player dug, a bunker built by hand, a tunnel: rain wets
whoever stands in it, the air is the street's, the sounds are the open
air's. (The mod has always kept snow, wind chill and fire out of its own
tunnels, and told other mods they are indoors. This is more than that.)

Stand in the place, below ground. Right-click, *Sewers (admin)*:

- **Count this room as indoors**: every square that can be walked to from
  the one you clicked without passing a wall or a shut door, up to 600.
  Shut the door first.
- or **Mark a corner here**, then at the opposite corner **Count the box
  from the corner to here as indoors**.
- **Is this square indoors?** tells you what the game makes of a square.
- **No longer count this as indoors**, on marked ground.

What it does: the mod has the game make a real room of that ground, the
way the game's own map has rooms. To the game it is then indoors for
everything: rain, snow, wind, the air's temperature, the sounds.

**On a server, the room is made when the server next starts.** Every
client has it the moment you mark it (so the rain and the sound change at
once); the server, which is what works out who is wet and cold, counts it
from its next restart, and tells you so. Taking a mark away works the same
way round: the room goes at the next start. Rooms are never added or taken
away under a running server. That is deliberate: it is the one way this
can go wrong, and it is how servers were stopped dead in 0.7.2.

- Squares beside a door are left out, so a locked door still holds against
  the dead.
- Squares the game already has a room on are left as they are.
- Below ground only. At street level and above, the game does this itself
  for anything walled and roofed.

### Rebuild

**Rebuild the sewer round here**, below ground: the mod looks over the
tunnel for two chunks round you and puts back any floor, wall, ladder or
door frame of its own that is missing. Never furniture, never the dead,
never anything a player built or took.

---

## Recipes

**A roleplay server that wants the sewers as a place for events**

```lua
Access = 2,       -- nobody goes down until a game master opens a cover
Hatches = 2,      -- no trapdoors in players' houses
Nest = 2,         -- the nest waits for its night
Labyrinth = 2,    -- so does the labyrinth
```

Open covers as the story reaches them, or put your own way down where the
scene needs one. On the night, set `Nest = 1` or `Labyrinth = 1` and
restart; the labyrinth's trapdoor appears the next time somebody walks its
woods.

**A bunker under the town hall**

Put a trapdoor on the floor (*Put a way down here*). Climb down, put a
shaft down to level 2, and draw your corridors there on the map. Build one
room by hand, keep it as a room with the stock you want, and set copies
down along the corridor. Mark the lot as indoors and restart the server.
Make the trapdoor *closed both ways* until the night it opens.

**A pit**

Make one cover *a way in only*, and make sure the tunnels under it reach
no other ladder (draw them *apart*). Whoever goes down stays down until an
admin makes it a way out.

**A busy server worried about a thousand zombies in one maze**

```lua
MazeDead = 2,     -- about 250, a few at a time as corridors are walked
Zombies = 2,
```

**A hard server**

```lua
Zombies = 4, Outfits = 1, Loot = 2, Gas = 4, Rous = 4, ExitSigns = 1,
DrainFit = 3,     -- a kerb drain only for whoever travels light
```

**A building server**

```lua
Zombies = 1, Rats = 1, Gas = 1, Digging = 3, CultDead = 1, MazeDead = 1,
```

---

## Languages

The mod is translated into every language the game ships:

Català, Čeština, Dansk, Deutsch, Español (España, Argentina, Chile,
México), Suomi, Français, Magyar, Bahasa Indonesia, Italiano, 日本語, 한국어,
Nederlands, Norsk, Polski, Português (Portugal, Brasil), Română, Русский,
ไทย, Türkçe, Українська, 简体中文, 繁體中文.

Each player sees their own game language: menus, tooltips, messages, the
sandbox page, item names, the journals, the handwriting on the annotated
maps. Nothing needs setting on the server.

**What stays English, and why:**

- **What is painted on the walls**: EXIT, the graffiti, *THE BURROW
  PROVIDES*, the gas placards. They are pictures.
- **Street and town names**, as the game's own map has them.
- **Two names the server writes**: a *Sewer Maintenance Key (Muldraugh)* and
  the name over a rodent of unusual size are made on the server, in the
  server's language, and every player sees that.
- **The dev build's own menu**, which only the author sees.

**If a line is wrong in your language**, the texts are plain JSON, one
folder a language, in the mod under
`42/media/lua/shared/Translate/<LANG>/`. A key that is missing falls back
to English by itself, so a partial fix is safe. Corrections are welcome on
the Workshop page. A translator
needs to keep three things, which `python tests/test_translations.py`
checks:

1. `%1` and `%2` stay, and no literal percent sign is written.
2. A journal page (keys ending `_Body`) keeps its number of line breaks.
3. `%2` in a journal is a compass direction taken from that language's own
   `IGUI_SEW_Dir_*` words, so the sentence and the eight words have to work
   together.

---

## When something goes wrong

The mod's lines in `server-console.txt` and a client's `console.txt` start
`[SEW]`. A broken invariant is `[SEW] WARN`.

| Line | Means |
|---|---|
| `[SEW] Sewars 0.9.1 on a server: 33 towns` | It loaded. No such line: the mod is not on the server. |
| `[SEW] refused <player>: closed (at x,y,z)` | A player asked to climb down a closed way. |
| `[SEW] refused <player>: noexit (at x,y,z)` | A player asked to climb up a way an admin made no way out. |
| `[SEW] refused <player>: big (at x,y,z)`, `load`, `drainoff` | A kerb storm drain: the player's character is too heavy for it (`DrainFit`), is carrying too much, or the drains are bolted down (`Drains`). If somebody who should fit is refused `big` or `load`, send the line: the server's own copy of a player's weight and load is what it was judged from. |
| `[SEW] refused <player>: admin` | Somebody who is not an admin asked for something of an admin's. If it is you, your role has none of the game's admin tools. |
| `[SEW] <admin> made the way down at x,y,z in (town)` | An admin's decision, with who made it. |
| `[SEW] <admin> put a way down ...`, `ran a tunnel ...`, `set down ...`, `marked ... as indoors` | Every work, with who did it and where. |
| `[SEW] indoors: mark ... declared (n buildings, level z)` | At a start: a marked place made a room. |
| `[SEW] WARN ... the engine would not make a room of marked ground` | The game refused. Nothing is marked indoors this session; send the line. |
| `[SEW] refused <player>: level (the server has you at ...)` | The server and the client disagree about where a player is. Send this line with a report. |
| `[SEW] rooms: the engine had a room on the sewer at ...` | Harmless by itself, and worth sending with any report of a frozen server. |
| `[SEW] place: the labyrinth's trapdoor is at x,y by the sandbox (MazeX, MazeY), not the mod's own 8922,10322` | At a start: `MazeX` and `MazeY` moved it, and to which square (the nearest step of 8). |
| `[SEW] WARN place: the sandbox puts the labyrinth at x,y (MazeX, MazeY), which is on or beside <town>'s sewers: it stays at the mod's own 8922,10322` | The place was refused. Choose one further from that town. |
| `[SEW] place: this world's labyrinth was at x,y and is at x,y now; n stamp(s) of its chunks are forgotten` | The settings changed in a world that already had a labyrinth. The old one stays in the ground; the new one is built as players come to it. |

Reports with those lines are what gets things fixed: the Workshop page's
comments.

---

## What the mod does not do

- **Turn a room.** A copy of a room goes down the way round it was built.
- **Make every tunnel a room by itself.** The mod keeps the weather out of
  its own tunnels its own way (no snow, no wind chill, no fire from the
  street, other mods told they are indoors). Ground is a real room to the
  game where an admin marks it, and that includes a stretch of tunnel.
- **Go deeper than level 3**, or build above the street.
- **Move what is built.** Nothing an update or a setting does moves or
  removes a tunnel, the mod's or yours. `MazeX` and `MazeY` say where a
  labyrinth nobody has found yet will be built.
- **Move the temple, the nest or the caves.** They are part of the towns'
  sewers (*If another mod is in the way*).
