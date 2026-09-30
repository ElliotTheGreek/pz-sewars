# Sewars

A Project Zomboid build 42 mod: **every manhole in Kentucky goes somewhere.**

> Status: **0.5.0**: caves, houses with a way down, Louisville, rats and the
> nest, play-tested. Next, built and passing every static and simulated test,
> waiting on its play-test: sewer gas, locked gates and storm-drain outfalls
> (the checklist is in `DEV_GUIDE.md`, *Current state*).

## What a player gets

- **Manholes that open.** Vanilla paints 446 round cast-iron covers on its
  streets. Right-click one: **Climb down into the sewer** (a crowbar or pipe
  wrench makes quicker work of the lid). You climb down a rusted ladder into
  the dark.
- **Louisville too.** Vanilla paints just 13 covers on all of Louisville and
  none on Irvington, Brandenburg, March Ridge or Valley Station. The mod adds
  its own there, at junctions and along the long streets, and sewers under
  every street.
- **Sewers under the streets you know.** Each town's tunnels follow its road
  network, laid out from the real map, so a main road is a main trunk and a
  cul-de-sac is a dead-end culvert. Walk under Muldraugh and come up where you
  meant to.
- **Ladders out.** Every manhole has a ladder under it. Right-click a ladder:
  **Climb out to the street**, and you come up through the cover above it.
- **Vast, dark and scary.** Brick vaults and concrete tunnels, sludge
  channels, pipes, puddles, graffiti from whoever came before. The only
  daylight is what falls through the holes in the covers. The dead are down
  here too, and you will hear things in the pipes.
- **Somewhere to build.** The tunnels are yours to wall off, barricade, light
  and furnish.
- **A map you fill in yourself.** Press **K** below ground (rebindable in
  Options -> Mods; not while driving): the sewer map
  starts black and fills in as you walk. Municipal sewer plans reveal whole
  sheets of a town; shelter journals point you to the next place worth finding.
- **Broken walls and dug caves.** Somebody knocked holes through the tunnel
  walls and kept digging: winding dirt passages that end in a hideout, a
  candle still burning, a bedroll, whatever they had left.
- **Houses with a way down.** In some garages, kitchens and storerooms near
  the tunnels, a trapdoor in the floor. *Climb down through the hatch*, and
  you are in the sewer; the ladder under it brings you back up into the
  house. Not every house: one the world gave a basement has none.
- **Rats.** The game's own rats live in the tunnels now: you will hear them
  and see them run. They can be trapped, and eaten if it comes to that.
- **Something under Louisville.** People who went down there wrote the same
  four letters on the walls. Nobody believed them.
- **Random shelters.** Somewhere along the tunnels, other survivors dug out a
  refuge before you: a maintenance room, a pump station, a squat behind a
  bricked-up junction. Some are stocked. Some still have their builders.
- **Locked gates.** Half the county's maintenance rooms and pump stations sit
  behind barred grilles. Each town has one key, the *Sewer Maintenance Key*,
  in the rooms that are not locked, and on some of the dead in sanitation
  overalls. Keep it in your hands or on a key ring. The grille latches behind
  you once the room is empty; it never shuts anybody in.
- **Sewer gas.** Some narrow culverts, well away from the ladders, hold foul
  air: a yellow-green haze on the floor and the county's warning placards at
  every way in. Without a gas mask or respirator it makes you sick, and it
  costs health if you stay; with one, it uses up your filter.
- **Storm-drain outfalls.** Down on the banks of the river, the creeks and the
  lakes, an iron grate in the ground: a way into the sewers nobody on the
  street sees, and a way out of town the dead will not be waiting at.

## Sandbox options

- **The dead in the sewers**: none, few, some or many.
- **Shelter supplies**: what a shelter's or hideout's crates and shelves hold
  when found: none, scarce, normal or plenty. Journals and plans are always
  there.
- **Rats in the sewers**: none, few, some or swarming.
- **Who the dead were**: mostly ordinary people (sewer workers, drifters,
  townsfolk; hardly any with a bag), mixed, or survivors who came down with a
  full pack.
- **Sewer gas**: off, mild (queasy at worst), harmful or deadly.

Each applies to tunnels and shelters not yet found.

## Can I add it to an existing save or server?

Yes. Nothing is built ahead of time: the sewers are built a stretch at a time
as players come near, so a world that never had the mod simply fills in as
people explore it. The way in is the manhole covers the map already has; the
mod's own covers, the house hatches and the storm-drain grates are put in the
first time a player comes near. Shelters, loot, the dead and the rats go in
when a stretch is first opened up, so an old world gets the same as a new one.
Anything already underground that is not the mod's (a basement, another
mod's build) is left alone.

- On a server: add the mod and its Workshop ID (3810188405) to the server's
  config and restart. Every player needs the mod.
- A save that never had the mod uses the default sandbox settings for it; an
  admin can change them in the server's sandbox settings.
- In a house someone already lives in, a hatch's trapdoor can turn up under
  their furniture, and a cover the mod adds can turn up under something built
  on the road. Both are only pictures on the floor.
- Taking the mod out of a save is the risky direction: what it built below
  ground loses its pictures. Be up on the street before you remove it.

## Requirements

Build 42 (target **42.20.4**). Single player, hosted co-op and dedicated
servers.

## In numbers

31 towns, 1,174 manholes that open (732 of them covers the mod adds where the
map has few, Louisville above all), 16 storm-drain outfalls, 239 shelters (47
behind locked gates), 152 caves, 189 houses with a way down, 97 stretches of
sewer gas, 476,399 walkable squares of tunnel, one nest, laid out from the
game's own street map.

## For developers

`DEV_GUIDE.md` is how to build, test and update the mod. `DESIGN.md` is how
the sewers work and why.
