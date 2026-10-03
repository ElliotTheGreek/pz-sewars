# Digging and blasting: a player's guide

How to make room under the streets. `README.md` is everything the mod does;
this is the one feature, start to finish. (How it is built is in
`DESIGN.md` 7f and `DEV_GUIDE.md`, *Digging changes the records, not the
objects*.)

> Built and passing every offline test (0.7 work, not yet in the Workshop
> build). Where this guide says what you will *see*, that part is still to be
> confirmed in play.

---

## In one minute

1. Get a **pickaxe** (a sledgehammer works, slowly).
2. Climb down any manhole.
3. Stand next to the rock you want gone. **Right-click anywhere → Dig →** the
   direction.
4. The square beside you becomes floor. Step onto it and do it again.
5. For a room in one go: throw a **pipe bomb** down the tunnel from as far
   back as you can, and let it open the rock for two squares all round where
   it lands.

---

## Digging

### What you need

| Tool | Works | Speed |
|---|---|---|
| Pickaxe, Forged Pickaxe | yes | 320 ticks a square |
| Sledgehammer (either), Forged Sledgehammer | yes | 560 ticks a square |
| anything else | no | -- |

The tool only has to be **on you**: in your hands, your inventory or a bag
you are carrying. With no tool the *Dig* option is greyed out and says what
you need.

### How to do it

You must be **below ground, standing on a floor**.

Right-click anywhere. If there is something to dig beside you, the menu has
**Dig**, and under it one entry for each direction that can be dug from the
square you are standing on:

- **Dig into the rock to the north / east / south / west** -- there is solid
  rock that way. It becomes one new square of earth floor.
- **Knock through the wall to the north / east / south / west** -- there is a
  wall of the sewer that way with open space already behind it (another
  tunnel, a room, something you dug earlier). The wall comes down and the
  two spaces join.

The directions are compass directions. On the game's tilted view **north is
up and to the right, east is down and to the right, south is down and to the
left, west is up and to the left**. Your character turns to face the way you
picked before the first swing, so a wrong pick is easy to see and cancel
(walk away: the action stops).

### What you get

- The square you dug is **earth floor**, the same as a cave's.
- **Earth walls** stand on every side of it that still has rock behind it.
  Dig the next square and the wall between the two is simply not there.
- The **wall you dug through** is gone.
- A few **stones** are left on the floor (none, one or two a square).
- **Masonry XP**, 3 a square.

### What it costs

- **Time**: a pickaxe is nearly twice as fast as a sledgehammer.
- **It is heavy work**, the same as vanilla's own pickaxe work: it tires you.
- **It is loud**: every square is heard about 25 squares away. The dead in
  the tunnels come. The dead up on the street do not, unless the sandbox's
  *The street hears the sewer* is Yes.

### Joining two spaces

Two squares dug side by side from different sides keep the earth between
them. Stand in one, **Dig → Knock through the wall**, and they are one room.
The same goes for breaking from something you dug into a tunnel, a shelter
or a cave.

---

## Blasting

The mod adds no explosive of its own. It makes **vanilla's bombs move rock**.

### What works

| Bomb | Moves rock |
|---|---|
| Pipe Bomb (plain, with timer, remote, with sensor) | **yes** |
| Aerosol Bomb (all kinds) | **yes** |
| Flame trap, Molotov | no (fire, not a blast) |
| Smoke bomb, noise maker | no |

### How to do it

Use the bomb exactly as you would above ground.

- **A plain Pipe Bomb or Aerosol Bomb is thrown**, and goes off where it
  lands: put it in your hand (right-click it, *Equip Primary*), hold the
  right mouse button to aim, left-click to throw. It carries about ten
  squares, and vanilla's blast hurts for seven: throw it as far as it goes.
- **One with a timer, a remote or a sensor is placed**: right-click it in
  the inventory, *Arm and set*, and walk away.

It has to go off **below ground**. A bomb on the street does nothing to the
sewer under it.

### What happens

1. Vanilla's explosion: its bang, its damage, its noise. **Stand well back.**
   The mod does not soften any of it.
2. A moment later, **every square of rock within two squares of the bomb is
   open floor**, and every sewer wall inside that circle is down. One bomb
   makes a room about five squares across.
3. Earth walls stand round the edge of what was opened, and stones are left
   on the floor.
4. Anyone below ground within about thirty squares is told the ground moved.

Put the bomb on the tunnel floor next to the wall you want to widen; the
circle is centred on the bomb, so half of it is the tunnel you are already
in.

---

## What will not give

Digging and blasting both leave these alone:

- **Somebody else's underground.** A square that already holds anything the
  mod did not put there -- one of the game's basements, another mod's
  cellar -- is never dug into. Digging says *Something is already built
  behind this. Leave it.* A blast goes round it.
- **Doors and locked grilles.** They are doors. Open them.
- **The wall a ladder hangs on.** That is your way out; it is not even
  offered.
- **The rat hole's two special walls.** The loose bricks are pulled away,
  and the gnawed wall opens when what lives there is dead. Neither can be
  dug.
- **The hoard, from any side**, until its own wall has been opened.
- **Anything a player built.** The mod only ever removes its own walls.

And it only goes sideways: the sewers are one level. You cannot dig up to
the street or down to a second level.

---

## Building in what you dug

A dug square is ordinary floor to the game. Build on it as you would in the
tunnels: floors over the earth, walls, doors, crates, lights, a generator.
The mod never touches what you place.

**What you dug stays dug.** It is saved with the world, and a later update
of the mod will not put a wall back where you took one down.

---

## Where you can dig

Anywhere at the sewers' level, starting from any floor down there: out of a
tunnel, a shelter, a cave, one of the dens under Louisville, the temple.
You can keep going past the edge of a town's sewers, as far as you care to
swing.

Dug squares do not appear on the sewer map; it shows what the county built
and what its people dug before you.

---

## Sandbox option

**Digging in the sewers**

| Setting | Pick and hammer | Bombs move rock |
|---|---|---|
| Off | no | no |
| Picks and hammers | yes | no |
| Picks, hammers and explosives (default) | yes | yes |

With it off the *Dig* menu does not appear at all.

A world made before this option existed uses the default.

---

## On a server

The server does the digging and the blasting; your game only asks. Everyone
near by sees the new floor and the missing wall as it happens. The noise and
the explosion are the server's too, so they draw the dead for everybody.

---

## Messages you may see

| Message | Meaning |
|---|---|
| *The rock comes away. One more square of sewer.* | You dug a square. |
| *The wall comes down.* | You knocked through into a space. |
| *The ground jumps. Somewhere, a lot of rock has moved.* | A blast went off below, near you. |
| *You need a pickaxe or a sledgehammer.* | No digging tool on you. |
| *That will not give.* | A door, a grille, a ladder's wall, or one of the rat hole's own walls. |
| *Something is already built behind this. Leave it.* | A basement or another mod's space is there. |
| *Not while something in the nest is still breathing.* | You tried to dig into the hoard. |
| *Too far away.* / *Not from here.* | You moved off the square, or are not below ground. |
| *Something is blocking the shaft. Try again.* | That piece of ground is not loaded yet; try again in a moment. |
| *Digging is turned off on this world.* | The sandbox option is Off. |

---

## Not in yet

- Tools do not wear out from digging.
- Only stones come out of the rock: no clay, no limestone.
- Dug rooms need no propping and never cave in.
- No digging up to the surface.

---

## For testing (dev build only)

Right-click → **Sewers (dev)** → **Give me a pickaxe and pipe bombs** puts a
pickaxe and three pipe bombs in your inventory. Then go below ground and
right-click for **Dig**. The pipe bombs are the plain kind: throw them.
