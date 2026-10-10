# Sewers changelog

What changed in each release on the Workshop, newest first. Written for
players: what you will see, not how it was done.

Every update is safe for an existing save or server. Nothing already built
below ground moves; new parts appear as you walk into them.

---

## 0.9.0 (10 October 2026)

**New: the labyrinth**

- Somewhere in the deep woods west of Muldraugh there is a trapdoor under
  the weeds. Under it is a brick labyrinth 256 squares a side: no light,
  one way through, and a great many ways that are not. It is a long walk
  even if you never take a wrong turn. Bring a torch, water and a weapon.
- Everybody who went in before you is still in there.
- In its dead ends you will find what they carried: torches, batteries,
  water, tins. Here and there is a small room with a steel door that
  shuts, a bedroll and a couple of crates, to rest in. These are stocked
  whatever your sandbox's loot setting.
- At the heart of it: crates of the best things in the mod, and a ladder.
  The ladder comes up inside a small brick hut in the woods. That hut is
  the way out and only the way out: its hatch has no handle on top, and
  will not open from above.
- Your sewer map draws the labyrinth's walls as you walk them, a little at
  a time, and nothing ahead of you.
- Nothing in the labyrinth can be dug or blasted through. *Dig* is not on
  the menu there.
- A third kind of annotated map now turns up in the game's loot, showing
  the way to its trapdoor.
- You can turn back: the trapdoor you came down is also a way out, if you
  can find it again.

**New: 26 more languages**

- The mod now speaks every language the game does: Spanish (Spain,
  Argentina, Chile and Mexico), Portuguese (Portugal and Brazil), French,
  German, Italian, Dutch, Catalan, Russian, Ukrainian, Polish, Czech,
  Hungarian, Romanian, Danish, Norwegian, Finnish, Turkish, Indonesian,
  Thai, Korean, Japanese and Chinese (Simplified and Traditional). Menus,
  tooltips, messages, the sandbox page, item names, the journals and the
  handwriting on the annotated maps. You see your own game language;
  nothing needs setting.
- What is painted on the walls (EXIT, the graffiti) is a picture and stays
  as it is. Street names are the game's own.
- If a line reads wrong in your language, say so in the comments: they
  were not all written by native speakers.

**New: for servers, an admin's tools**

Everything here is on one menu: as an admin (a moderator or game master
counts), right-click and choose *Sewers (admin)*. `SERVERS.md`, in the
mod's own folder, explains each one, with settings to copy.

- **Who may use a way down.** Any manhole cover, trapdoor or grate can be
  open both ways, a way in only, a way out only, or closed both ways.
  Players see one they may not use greyed out.
- **A way down wherever you want one.** Right-click a square of street:
  a manhole cover, a trapdoor or a storm-drain grate goes in there, with a
  ladder under it and a passage dug to the nearest tunnel.
- **Tunnels drawn on the sewer map.** One, three or five squares wide,
  joined to the tunnels they meet or walled off from them. Click where it
  starts and where it ends.
- **Two more levels.** A shaft from any tunnel goes down to level 2, and
  from there to level 3, for tunnels of your own. The sewer map has a
  button for each level, and each has its own colour.
- **Rooms.** Set down a copy of a maintenance room, a pump station, a squat
  or a last stand behind any tunnel wall, furnished, stocked and occupied.
  Or build a room of your own anywhere, keep it with a kind of stock
  (medical, military, guns, police, survival, food, tools, car parts,
  electronics, laboratory), and set copies of that down.
- **Indoors.** Mark a basement or a bunker somebody built below ground,
  or a stretch of tunnel, as indoors: by the room, or by a box. The game
  then treats it as a room: no rain, indoor air, indoor sounds. On a
  server it takes effect at the next restart.
- **And:** the whole sewer map with no fog, a rebuild of the tunnel round
  you, and a check of what the game makes of a square.
- What an admin makes is kept exactly as what a player digs: nothing in
  any later update moves it.

**New: for players**

- What you dig with a pick now shows on your sewer map.
- Standing at the foot of a ladder, your Interact key (E) climbs it. The
  right-click menu still does too.
- On a server with deeper levels, a pickaxe and a bomb work down there too.

**New: sandbox settings**

- **Ways into the sewers**: open, or closed until an admin opens them. A
  setting never closes a way *out*: a ladder always takes a player back up
  unless an admin made that one cover no way out on purpose.
- *Trapdoors in houses*: yes or no. No: a player's house never gets a
  trapdoor into the sewers.
- *Storm-drain outfalls*: yes or no.
- *The rats' nest*: open or sealed. Sealed, its false wall will not come
  away until you say so.
- *Rodents of unusual size*: weak, normal, tough or monstrous. Normal is
  the fight as it was.
- *The dead in the temple* and *The dead in the labyrinth*: none, a few,
  half or all. The labyrinth's thousand can be thinned for a busy server.
- *The labyrinth*: yes or no. No: its trapdoor is not put in and its map
  is not handed out.
- *Longest passage to a new way down*: 20, 40 or 80 squares.
- *The labyrinth's place*, east and south: if another mod has something in
  the woods the labyrinth is under, these two numbers put the labyrinth
  somewhere else, all of it, map and hut included. Set them before the
  world is made. `SERVERS.md` has where everything of the mod's is.
- Every one of them is as it was unless you change it.

**For an existing save or server**

- Safe to add. The labyrinth is in ground no sewer used, and it is built
  as somebody walks into it. Nothing you have already found moves.
- Nothing else changes until you change a setting. A world from before
  this update has every way down open and everything else as it was.

## 0.7.6 (9 October 2026)

**Changed, from your comments (thank you)**

- The sounds in the pipes (the drip, the scuttling in the wall, the groan)
  are off. If you liked them, tick **Sounds in the pipes** under Options ->
  Mods -> Sewers, and they come back far less often: one every few minutes,
  not every twenty seconds.
- The sewer map has no key any more. K was other mods' key too. Right-click
  anywhere below ground and choose **Sewer map**, as before. If you had
  bound it to another key, that binding is gone as well.
- No wind chill in the sewers. The game took a tunnel for open ground and
  chilled you with the street's wind. Below ground you now get the still
  air's temperature: as cold as the day is, and no colder. It does not warm
  you. Works with mods that make the weather colder, as long as they use
  the game's own temperature. A room you walled off and roofed yourself is
  the game's to judge, as it always was.

## 0.7.5 (6 October 2026)

**Fixed, from your comments (thank you)**

- An error box about `getItems` popped up while the game was filling bags
  with loot. The mod was looking for maps in something that was not a
  container. It no longer looks there.
- Burning corpses on a street set the sewer under it alight: the game
  spreads fire to the level below as if there were no road in between. A
  fire that comes down through the street is now put out at once, and so is
  one that comes up out of the tunnel. A fire you light down there yourself
  (a molotov, a campfire) burns as before.
- Snow lay on the tunnel floors in winter. The game took the sewer for open
  ground. It no longer does, and rain puddles go the same way. One thing to
  know: the two squares either side of a door below ground can still show
  it. That is on purpose, so that a locked door keeps the dead out.
- The rodents of unusual size could not be hit reliably. A swing or a shot
  at one now lands whenever it is in reach, in front of you, and there is no
  wall between, and three hits kill one (two bullets). A shove hurts nothing
  but throws one back and stops it for a couple of seconds. They also bite less often, and not the instant
  they reach you.
- Multiplayer: a player could be left below with a ladder that would not
  take them up. Climbing out no longer needs the game to find a path to the
  ladder first: stand at it and it works. If the server does not answer the
  climb, the game asks it again, and if it still hears nothing it takes you
  up anyway. If a ladder ever refuses you, the reason is now written in
  your console.txt; please post that line.

**New**

- Sandbox option, EXIT stencils: none, few, or by every ladder (as before).
  For tunnels you have not opened up yet; the ones already found keep
  theirs. The sewer map still shows every ladder you have used.

## 0.7.4 (3 October 2026)

**Fixed, from your comments (thank you)**

- The dead in the sewer came to the noise of a player up on the street, and
  stood under them. They no longer do: the street and the sewer are out of
  earshot of each other, both ways.
- A zombie that was chasing you when you climbed down a manhole (or out of
  one) went on standing over the spot. It gives up now.
- The sandbox option, The street hears the sewer, covers all of it: Yes puts
  the game's own rule back.

## 0.7.3 (3 October 2026)

**Fixed, from your comments (thank you)**

- Multiplayer: a server could stop dead for everyone as soon as a player
  went down into the sewer, and stay stopped while they were there (nobody
  able to do anything, a ladder that would not be climbed, the same again on
  rejoining). The server's log filled with one error about a room with no
  building. The mod now makes sure no square of the sewer is ever taken for
  a room on a server. If your server still does it on 0.7.3, please post the
  error from the log again: it will say whether this was the whole of it.
- The name. It is spelled Sewers now, on the mods screen, the sandbox page
  and the Workshop. Nothing changes for a save or a server: the mod's id is
  the same, so your mod list still finds it.

## 0.7.2 (2 October 2026)

**New**

- Digging. With a pickaxe (or, slowly, a sledgehammer), right-click below
  ground and Dig: the rock beside you becomes one more square of floor, and
  a wall with a space behind it comes down. It is loud, and it leaves stones.
- Blasting. A pipe bomb or aerosol bomb that goes off in a tunnel opens the
  rock for two squares round it. Doors, a ladder's wall and anybody's
  basement never give.
- What you dig stays dug, and is yours to build on.
- Sandbox option, Digging in the sewers: off, picks and hammers, or picks,
  hammers and explosives.
- The dead on the street no longer come to the noise you make in the sewer
  under them. The dead in the tunnels still hear everything. Sandbox option,
  The street hears the sewer, puts the game's own rule back.

**Fixed, from your comments (thank you)**

- Going down to level -2 in a bunker or a base of your own teleported you
  to the nearest sewer ladder, and the military base's deep levels sent you
  up to the surface. The mod now leaves every basement and bunker alone.
- Drips, rat noises and a distant groan played in every basement. The
  sewer's sounds now play in the sewers only.
- Right-clicking a manhole cover or a ladder near the edge of the screen
  could miss it. The click is now read from where you clicked.
- The sewer map and Dig no longer appear on the right-click menu two or
  more levels down.

## 0.6.0 (1 October 2026)

**New**

- The rat hole under Louisville is bigger than it was, with more than one
  cache in it.
- The cult has somewhere of its own, under the fields. There is more than
  one way in.
- What is written down in each place will lead you to the other.
- Annotated maps to both turn up where maps turn up: in a drawer, in a
  glovebox, on the dead.

**Fixed**

- Arriving on top of a place's dead no longer leaves it empty: they are
  there once you have stepped away and come back.

## 0.5.0 (30 September 2026)

**New**

- Broken walls and dug caves: somebody knocked through the tunnel wall and
  kept digging. A winding dirt passage, and a hideout at the end of it.
- Houses with a way down: a trapdoor in the floor of some garages, kitchens
  and storerooms, and a ladder to the sewer under the street. A house with
  a basement under it has none.
- Louisville, and the towns the map gave no covers: Irvington, Brandenburg,
  March Ridge, Valley Station and more. The mod adds its own covers there,
  with sewers under every street.
- Rats in the tunnels. Sandbox option: none, few, some or swarming.
- Somewhere under Louisville, a rat hole, and what lives in it.
- Locked gates: half the county's maintenance rooms and pump stations sit
  behind barred grilles. One Sewer Maintenance Key per town, in the
  unlocked rooms and on some of the dead in sanitation overalls. A grille
  latches behind you once the room is empty and never shuts anybody in.
- Sewer gas: some narrow culverts hold foul air behind the county's warning
  placards. A gas mask keeps it out and uses up its filter. Sandbox option:
  off, mild, harmful or deadly.
- Storm-drain outfalls: an iron grate in the bank of the river, the creeks
  and the lakes. A way in nobody on the street sees.
- Two more sandbox options: Shelter supplies (none, scarce, normal, plenty)
  and Who the dead were (mostly ordinary people, mixed, or survivors with
  full packs).

**Fixed, from your comments and from play**

- The sewer map's key was N, which is the game's Start/Stop Engine. It is K
  now, rebindable in Options, Mods, and never opens while driving.
- Every one of the dead carried a pack and every crate was full. Most of
  the dead are ordinary now, and a crate holds a few things.
- The mod's tiles were drawn over your character (puddles, graffiti,
  ladders). You are drawn over them now.
- By a cave's breach the earth hung in the air when the camera cut the wall
  away. Pictures on walls are cut away with their walls.
- The sludge channel floated against the wall. It lies flat in the walkway;
  the bridges are the way across.
- A tunnel on Harris St in Muldraugh, and two more like it, ended in a wall
  with the road running on. They run through now.
- Other mods took the sewer for outdoors: Flying Birds flew its flocks
  through the tunnels. Below ground now answers as indoors to every mod,
  and to the game's own rain barrels, crops, campfires and foraging.

## 0.3.1 (29 September 2026)

The first release.

- Every manhole cover the map paints opens: Climb down into the sewer. A
  crowbar or a pipe wrench makes quicker work of the lid.
- Sewers under the streets of every town, laid out from the game's own
  street map: trunk sewers under highways, mains under streets, culverts
  under back lanes.
- A ladder under every cover: Climb out to the street.
- Dark, with daylight through the holes in the covers. The dead are down
  there too.
- Shelters other survivors dug out: maintenance rooms, pump stations, squats
  and last stands behind steel doors, some stocked, some still occupied.
- The sewer map: starts black and fills in as you walk. Municipal sewer
  plans reveal whole sheets of a town; shelter journals point you to the
  next place worth finding.
- Sandbox option, The dead in the sewers: none, few, some or many.
- Single player, hosted co-op and dedicated servers.
