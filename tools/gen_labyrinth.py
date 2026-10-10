"""The labyrinth: one in the world, under woods nobody has a reason to cross (DESIGN.md 7g).

Called by tools/gen_sewers.py after the temple, and before anything is
written. Nothing here touches a square any town has: the labyrinth is a town
of its own in chunks no town has, and no tunnel leads to it.

  the site      under the woods west of Muldraugh (LAB_NEAR), the nearest spot
                clear of every building, basement, pond and tunnel by a long
                way, with open ground over its two shafts
  the maze      a grid of CELLS x CELLS cells (128: 256 squares a side), each PITCH squares across, with
                thin brick walls on the cells' edges: one way from the gate
                to the heart, long and winding, a few loops so the dead can
                come round behind, and dead ends everywhere
  the gate      the way in: a trapdoor under the weeds at the maze's
                north-west corner, over a ladder. It is a way back out too
                (nobody is ever shut in: DESIGN.md 2)
  the rests     sixteen small rooms behind steel doors, off the way: a bedroll,
                a crate, a candle
  the caches    in one dead end in three, what somebody carried this far: a
                torch, batteries, water, tins
  the dead      everybody who came in before, standing in the dark
  the heart     the room in the middle, behind one steel door at the far end
                of the longest way there is: the reward, and a ladder up
  the way out   that ladder comes up inside a small brick blockhouse in the
                woods, through a hatch with no handle on top: out, never in
                (SEW_Build.blockhouse, SEW_Server.grant)

Returns an entry shaped like a town's, for gen_sewers to write.
"""
import collections
import os
import random

import numpy as np
from scipy import ndimage as ndi

N4 = [(0, -1), (-1, 0), (1, 0), (0, 1)]

LAB_ID = "labyrinth"
LAB_NAME = "the deep woods"
LAB_NEAR = (9050, 10450)        # the middle of where it should be
LAB_SEARCH = 200                # how far from there a site may be
LAB_REGION = 440                # the world looked at round it, each way
LAB_CLEAR = 40                  # squares it keeps from anything built, wet or dug
CELLS = 128                     # cells each way
PITCH = 2                       # squares a cell: the width of a corridor
SIZE = CELLS * PITCH            # squares each way
SEEDS = 40                      # mazes tried; the one with the longest way to the heart is kept
SOLUTION_MIN = 2000             # cells: a way shorter than this is refused
BRAID = 0.06                    # the share of dead ends opened into a loop
CACHE_EVERY = 3                 # one dead end in so many holds a cache
DEAD_PER_CELLS = 17             # one of the dead for so many cells of corridor
DEAD_CLEAR = 7                  # none within this many cells' walk of the gate
GUARD = 20                      # and this many more on the last stretch before the heart's door

# The rooms, in cells: (kind, cx, cy, w, h). `kind` is the room's name on the
# sewer map (IGUI_SEW_Shelter_<kind>).
GATE = ("labyrinth_gate", 0, 0, 2, 2)
HEART = ("labyrinth_heart", 60, 60, 8, 8)
# Sixteen rests, one to each sixteenth of the maze, each a little off its middle.
RESTS = [("labyrinth_rest", 16 + 32 * i + (i * 7 + j * 3) % 9 - 4, 16 + 32 * j + (i * 5 + j * 11) % 9 - 4, 2, 2)
         for j in range(4) for i in range(4)]
ENTRY = (0, 0)                  # the square under the trapdoor, local
EXIT = (HEART[1] * PITCH + 9, HEART[2] * PITCH)       # the foot of the ladder out, on the heart's north wall

# Ours (tools/gen_sewer_art.py TILES_DEF, by index) and vanilla's, each
# checked against the catalogue by tests/test_assets.py.
OURS = {"brazier": "sewars_01_60", "candles": "sewars_01_61"}
V = {
    "crate_metal": "constructedobjects_01_46",
    "crate_wood": "carpentry_01_16",
    "shelves": "carpentry_02_64",
    "bagS": ["camping_02_84", "camping_02_85"],
    "angelE": "location_community_cemetary_01_12",
    "angelW": "location_community_cemetary_01_14",
}
# Who came in before: mostly whoever, and a few who came equipped for it
# (SEW_Build.dress leaves those their packs by the sandbox's share).
LOST = ("Hobbo", "Generic01", "Generic02", "Generic03", "Generic04", "Generic05", "Redneck", "Grunge",
        "Trucker", "Resident", "Survivalist", "Camper")


def h32(*v):
    import hashlib
    return int(hashlib.md5(",".join(map(str, v)).encode()).hexdigest()[:8], 16)


def room_cells(room):
    _k, cx, cy, w, h = room
    return {(x, y) for x in range(cx, cx + w) for y in range(cy, cy + h)}


def maze(seed):
    """One maze, in cells. Returns dict(open, doors, dist, dead_ends, heart_door, length):
    `open` the pairs of cells with nothing between them, `doors` those with a
    steel door between them, `dist` each cell's walk from the gate in cells."""
    rng = random.Random(1993 * 7919 + seed)
    rooms = [GATE, HEART] + RESTS
    room_of = {}
    for i, r in enumerate(rooms):
        for c in room_cells(r):
            room_of[c] = i
    free = {(x, y) for x in range(CELLS) for y in range(CELLS)} - set(room_of)

    def pair(a, b):
        return (a, b) if a < b else (b, a)

    # A way through every free cell and no loops: the recursive backtracker,
    # which makes long winding corridors -- the kind a person gets lost in.
    start = (GATE[1] + GATE[3], GATE[2] + GATE[4] - 1)
    opened, seen, stack = set(), {start}, [start]
    while stack:
        x, y = stack[-1]
        nxt = [(x + dx, y + dy) for dx, dy in N4 if (x + dx, y + dy) in free and (x + dx, y + dy) not in seen]
        if not nxt:
            stack.pop()
            continue
        n = nxt[rng.randrange(len(nxt))]
        opened.add(pair((x, y), n))
        seen.add(n)
        stack.append(n)
    if seen != free:
        raise SystemExit("the labyrinth: %d cells of corridor cannot be walked to" % len(free - seen))

    def degree(c):
        return sum(1 for dx, dy in N4 if pair(c, (c[0] + dx, c[1] + dy)) in opened)

    # A few loops, so that what follows a player can come round behind them.
    for c in sorted(free):
        if degree(c) == 1 and c != start and rng.random() < BRAID:
            walls = [(c[0] + dx, c[1] + dy) for dx, dy in N4
                     if (c[0] + dx, c[1] + dy) in free and pair(c, (c[0] + dx, c[1] + dy)) not in opened]
            if walls:
                opened.add(pair(c, walls[rng.randrange(len(walls))]))

    # The walk from the gate, in cells.
    dist, q = {start: 1}, collections.deque([start])
    while q:
        c = q.popleft()
        for dx, dy in N4:
            n = (c[0] + dx, c[1] + dy)
            if n in free and n not in dist and pair(c, n) in opened:
                dist[n] = dist[c] + 1
                q.append(n)

    # The heart's one door: on the cell of its edge that is furthest to walk to.
    doors = set()
    best = None
    for c in sorted(room_cells(HEART)):
        for dx, dy in N4:
            n = (c[0] + dx, c[1] + dy)
            if n in free and (best is None or dist[n] > best[0]):
                best = (dist[n], c, n)
    length, hin, hout = best
    doors.add(pair(hin, hout))
    # Each rest's door: on its south or east side (its furniture stands
    # against the north and west walls), wherever the seed says.
    rest_doors = []
    for r in RESTS:
        _k, cx, cy, w, h = r
        sides = [((cx + i, cy + h - 1), (cx + i, cy + h)) for i in range(w)] + \
                [((cx + w - 1, cy + i), (cx + w, cy + i)) for i in range(h)]
        sides = [s for s in sides if s[1] in free]
        a, b = sides[rng.randrange(len(sides))]
        doors.add(pair(a, b))
        rest_doors.append((a, b))
    # The gate's hall opens straight into the maze.
    gate_in = (start[0] - 1, start[1])
    opened.add(pair(gate_in, start))
    dead_ends = sorted(c for c in free if degree(c) == 1 and c != start
                       and not any(c in d for d in doors))
    return dict(open=opened, doors=doors, dist=dist, dead_ends=dead_ends, heart_door=(hin, hout), length=length,
                room_of=room_of, rooms=rooms, free=free, start=start, rest_doors=rest_doors, seed=seed)


def best_maze():
    """The maze, of SEEDS tried, whose heart is furthest to walk to."""
    best = None
    for seed in range(SEEDS):
        m = maze(seed)
        if best is None or m["length"] > best["length"]:
            best = m
    if best["length"] < SOLUTION_MIN:
        raise SystemExit("the labyrinth: the longest way to the heart is %d cells, under %d" % (best["length"], SOLUTION_MIN))
    return best


def squares(m):
    """The maze in squares, local: ({(x, y): floor}, {(x, y, col): wall code})
    -- a wall on the north (col 3) or west (col 4) edge of the square that holds it."""
    room_of, rooms = m["room_of"], m["rooms"]
    floor, walls = {}, {}

    def cell(x, y):
        return (x // PITCH, y // PITCH)

    def pair(a, b):
        return (a, b) if a < b else (b, a)

    heart = rooms.index(HEART)
    for x in range(SIZE):
        for y in range(SIZE):
            floor[(x, y)] = "u" if room_of.get(cell(x, y)) == heart else "y"
    for x in range(SIZE + 1):
        for y in range(SIZE + 1):
            for col, (dx, dy) in ((3, (0, -1)), (4, (-1, 0))):
                a_in = x < SIZE and y < SIZE
                bx, by = x + dx, y + dy
                b_in = 0 <= bx < SIZE and 0 <= by < SIZE
                if not a_in and not b_in:
                    continue
                if a_in != b_in:
                    walls[(x, y, col)] = "b"            # the rock outside
                    continue
                ca, cb = cell(x, y), cell(bx, by)
                if ca == cb or (ca in room_of and room_of.get(ca) == room_of.get(cb)):
                    continue
                p = pair(ca, cb)
                if p in m["open"]:
                    continue
                if p in m["doors"]:
                    # One door in a wall two squares long: on the first of them.
                    along = x if col == 3 else y
                    walls[(x, y, col)] = "d" if along % PITCH == 0 else "b"
                    continue
                walls[(x, y, col)] = "b"
    return floor, walls


def furnish(m, floor, walls):
    """What is in it, local squares: (furniture, dead, lights, dressing).
    Furniture is (x, y, sprite, loot, slot); dressing {(x, y): code}."""
    rng = random.Random(1993 * 104729 + m["seed"])
    F, D, L, dress = [], [], [], {}
    taken = set()

    def put(x, y, sprite, loot=None):
        F.append((x, y, sprite, loot, None))
        taken.add((x, y))

    def candles(x, y):
        put(x, y, OURS["candles"])
        L.append((x, y))

    def brazier(x, y):
        put(x, y, OURS["brazier"])
        L.append((x, y))

    # The gate's hall: what the last one to turn back left by the ladder.
    put(2, 0, V["crate_wood"], "labyrinth")
    dress[(1, 0)] = "c"                    # DONT GO DEEPER, on the north wall
    dress[(0, 2)] = "d"                    # a tally of days, on the west wall
    dress[(1, 1)] = "j"

    # The rests: a bedroll, two crates and a candle, against the north and west walls.
    for _k, cx, cy, _w, _h in RESTS:
        x, y = cx * PITCH, cy * PITCH
        put(x, y, V["crate_wood"], "labyrinthRest")
        put(x + 1, y, V["bagS"][0])
        put(x + 2, y, V["bagS"][1])
        put(x, y + 1, V["crate_metal"], "medical")
        candles(x, y + 2)

    # The heart: what all of it was for. Nothing on its outermost squares --
    # its door may be on any side.
    hx, hy = HEART[1] * PITCH, HEART[2] * PITCH
    for dx, dy in ((2, 2), (13, 2), (2, 13), (13, 13), (7, 10), (8, 10)):
        brazier(hx + dx, hy + dy)
    for i, loot in enumerate(("hoardArms", "hoardAmmo", "hoardValuables", "hoardMedical",
                              "hoardArms", "hoardAmmo", "hoardTools", "hoardSurvival")):
        put(hx + 4 + i, hy + 2, V["crate_metal"], loot)
    for (dx, dy), loot in zip(((3, 6), (12, 6), (3, 8), (12, 8)),
                              ("hoardFood", "hoardSurvival", "hoardFood", "hoardMedical")):
        put(hx + dx, hy + dy, V["crate_wood"], loot)
    for i, loot in enumerate(("hoardTools", "hoardValuables", "hoardValuables", "hoardMedical")):
        put(hx + 6 + i, hy + 13, V["shelves"], loot)
    put(hx + 1, hy + 7, V["angelE"])
    put(hx + 14, hy + 7, V["angelW"])
    put(hx + 1, hy + 9, V["angelE"])
    put(hx + 14, hy + 9, V["angelW"])
    for dx, dy in ((6, 6), (9, 6), (6, 8), (9, 8)):
        candles(hx + dx, hy + dy)

    # The caches: in one dead end in three, in the corner furthest from the
    # way in, with whoever carried it this far beside it.
    opened = m["open"]

    def pair(a, b):
        return (a, b) if a < b else (b, a)
    caches = 0
    for i, c in enumerate(m["dead_ends"]):
        if m["dist"][c] <= DEAD_CLEAR or rng.randrange(CACHE_EVERY) != 0:
            continue
        way = next((dx, dy) for dx, dy in N4 if pair(c, (c[0] + dx, c[1] + dy)) in opened)
        x = c[0] * PITCH + (0 if way[0] > 0 else PITCH - 1 if way[0] < 0 else rng.randrange(PITCH))
        y = c[1] * PITCH + (0 if way[1] > 0 else PITCH - 1 if way[1] < 0 else rng.randrange(PITCH))
        put(x, y, V["crate_wood"], "labyrinth")
        caches += 1
        side = [(c[0] * PITCH + a, c[1] * PITCH + b) for a in range(PITCH) for b in range(PITCH)
                if (c[0] * PITCH + a, c[1] * PITCH + b) != (x, y)]
        dress[side[rng.randrange(len(side))]] = "j"

    # The dead: through all of it but the first stretch from the gate, never
    # in a room; and a knot of them on the last stretch before the heart's door.
    def stand(c):
        spots = [(c[0] * PITCH + a, c[1] * PITCH + b) for a in range(PITCH) for b in range(PITCH)]
        spots = [s for s in spots if s not in taken]
        if not spots:
            return
        s = spots[rng.randrange(len(spots))]
        taken.add(s)
        D.append((s[0], s[1], LOST[rng.randrange(len(LOST))]))
    for c in sorted(m["free"]):
        if m["dist"][c] > DEAD_CLEAR and rng.randrange(DEAD_PER_CELLS) == 0:
            stand(c)
    last = sorted((c for c in m["free"] if m["length"] - GUARD < m["dist"][c] <= m["length"]),
                  key=lambda c: -m["dist"][c])
    near = set()
    cur = m["heart_door"][1]
    while cur is not None and len(near) < GUARD:          # back down the way from the door
        near.add(cur)
        cur = next((n for n in ((cur[0] + dx, cur[1] + dy) for dx, dy in N4)
                    if n in m["free"] and pair(cur, n) in opened and m["dist"][n] == m["dist"][cur] - 1), None)
    for c in sorted(near):
        stand(c)
    del last

    # What time and people did to the walls and the floor.
    for (x, y), f in sorted(floor.items()):
        if (x, y) in dress or (x, y) in taken or f != "y" or m["room_of"].get((x // PITCH, y // PITCH)) is not None:
            continue
        roll = h32("labdress", x, y) % 1000
        walled = walls.get((x, y, 3)) == "b" or walls.get((x, y, 4)) == "b"
        if roll < 30:
            dress[(x, y)] = "v"
        elif roll < 55:
            dress[(x, y)] = "u"
        elif roll < 85:
            dress[(x, y)] = "y"
        elif roll < 100:
            dress[(x, y)] = "j"
        elif walled and roll < 150:
            dress[(x, y)] = "i"
        elif walled and roll < 170:
            dress[(x, y)] = "bcdg"[h32("labword", x, y) % 4]
    return F, D, L, dress, caches


def dig(built, region_fn, room_mask_fn, under_fn, water_fn, plan_path=None):
    """Sites and lays out the labyrinth. `built` is every town so far (and the
    temple): nothing of theirs is touched, and all of it is kept away from.
    Returns the labyrinth's own entry."""
    nx, ny = LAB_NEAR
    R = LAB_REGION
    rx0, ry0 = nx - R, ny - R
    S = 2 * R + 1
    road, _keep = region_fn(rx0, ry0, rx0 + S - 1, ry0 + S - 1)
    rooms = room_mask_fn(rx0, ry0, rx0 + S - 1, ry0 + S - 1)
    under = under_fn(rx0, ry0, rx0 + S - 1, ry0 + S - 1)
    water, ground = water_fn(rx0, ry0, rx0 + S - 1, ry0 + S - 1)
    owner, any_rec = set(), np.zeros((S, S), bool)
    for b in built:
        for ck, rows in b["chunks"].items():
            owner.add(ck)
            if ck[0] * 8 + 7 < rx0 or ck[0] * 8 >= rx0 + S or ck[1] * 8 + 7 < ry0 or ck[1] * 8 >= ry0 + S:
                continue
            for (wx, wy) in rows:
                if 0 <= wx - rx0 < S and 0 <= wy - ry0 < S:
                    any_rec[wy - ry0, wx - rx0] = True
    k = 2 * LAB_CLEAR + 1
    clear = ~ndi.binary_dilation(rooms | under | water | road | any_rec, structure=np.ones((k, k), bool))

    # The site: the nearest origin to LAB_NEAR whose box is clear of
    # everything by LAB_CLEAR squares, in chunks no town has, with open ground
    # over the trapdoor and under the whole of the blockhouse.
    best = None
    for dy in range(-LAB_SEARCH, LAB_SEARCH + 1, 2):
        for dx in range(-LAB_SEARCH, LAB_SEARCH + 1, 2):
            ox, oy = nx - SIZE // 2 + dx - rx0, ny - SIZE // 2 + dy - ry0
            if ox < 8 or oy < 8 or ox + SIZE + 8 >= S or oy + SIZE + 8 >= S:
                continue
            d = dx * dx + dy * dy
            if best is not None and d >= best[0]:
                continue
            if not clear[oy:oy + SIZE + 1, ox:ox + SIZE + 1].all():
                continue
            ex, ey = ox + EXIT[0], oy + EXIT[1]
            if not ground[oy + ENTRY[1], ox + ENTRY[0]] or not ground[ey - 2:ey + 3, ex - 2:ex + 3].all():
                continue
            chunks = {((rx0 + x) // 8, (ry0 + y) // 8) for x in range(ox - 2, ox + SIZE + 3, 4)
                      for y in range(oy - 2, oy + SIZE + 3, 4)}
            if any(c in owner for c in chunks):
                continue
            best = (d, ox, oy)
    if best is None:
        raise SystemExit("the labyrinth: no clear site within %d of %s" % (LAB_SEARCH, LAB_NEAR))
    _d, ox, oy = best
    wx0, wy0 = rx0 + ox, ry0 + oy                      # the maze's origin, world

    m = best_maze()
    floor, walls = squares(m)
    F, D, lights, dress, caches = furnish(m, floor, walls)

    # --- records ------------------------------------------------------------------------------
    out = {}

    def rec(x, y):
        key = (wx0 + x, wy0 + y)
        if key not in out:
            out[key] = [str(key[0] % 8), str(key[1] % 8), ".", ".", ".", ".", "."]
        return out[key]
    for (x, y), f in floor.items():
        rec(x, y)[2] = f
    for (x, y, col), code in walls.items():
        r = rec(x, y)
        r[col] = code
        if r[2] == ".":
            r[2] = "r"
    # Pillars, as gen_sewers.encode stands them: where a north wall and a
    # west wall end at the same corner.
    hard = "bd"
    for (wx, wy), r in list(out.items()):
        if r[3] not in hard:
            continue
        north, here = out.get((wx + 1, wy - 1)), out.get((wx + 1, wy))
        if north and north[4] in hard and not (here and (here[3] != "." or here[4] != ".")) and r[5] == ".":
            r[5] = "Q"
    # The two ladders, each on the wall north of its square: in, and out.
    for (x, y), what in ((ENTRY, "the gate's"), (EXIT, "the heart's")):
        r = rec(x, y)
        if r[3] != "b":
            raise SystemExit("the labyrinth: no wall for %s ladder" % what)
        r[2], r[5] = "g", "L"
    for (x, y), code in dress.items():
        r = rec(x, y)
        if r[2] not in "yu":
            continue
        # A word on a wall needs the wall; what lies on the floor needs nothing.
        if code in "bcdgi" and r[3] != "b" and r[4] != "b":
            continue
        r[6] = code

    for x, y, _s, _l, _e in F:
        if floor.get((x, y)) is None or (x, y) in (ENTRY, EXIT):
            raise SystemExit("the labyrinth: furniture off its floor at %d,%d" % (x, y))
    stood = {(x, y) for x, y, _s, _l, _e in F}
    for x, y, _o in D:
        if (x, y) in stood or m["room_of"].get((x // PITCH, y // PITCH)) is not None:
            raise SystemExit("the labyrinth: one of the dead on furniture or in a room at %d,%d" % (x, y))
    # A door must open onto floor somebody can stand on, both sides.
    for (x, y, col), code in walls.items():
        if code == "d":
            other = (x, y - 1) if col == 3 else (x - 1, y)
            if (x, y) in stood or other in stood:
                raise SystemExit("the labyrinth: a door at %d,%d opens onto furniture" % (x, y))

    furniture = [(wx0 + x, wy0 + y, s, loot, slot) for x, y, s, loot, slot in F]
    dead = [(wx0 + x, wy0 + y, o) for x, y, o in D]
    lights = sorted({(wx0 + x, wy0 + y) for x, y in lights})

    mine = collections.defaultdict(dict)
    for (wx, wy), r in out.items():
        ck = (wx // 8, wy // 8)
        if ck in owner:
            raise SystemExit("the labyrinth: a square at %d,%d in a town's chunk" % (wx, wy))
        mine[ck][(wx, wy)] = "".join(r)

    # --- the labyrinth as a town --------------------------------------------------------------
    xs = [p[0] for p in out]
    ys = [p[1] for p in out]
    bx0, by0, bx1, by1 = min(xs), min(ys), max(xs), max(ys)
    BW, BH = bx1 - bx0 + 1, by1 - by0 + 1
    # On the sewer map (gen_sewers.map_images, a pixel a square) its walls are
    # drawn in ink, under the fog: a player sees the walls of what they have
    # walked, chunk by chunk, and nothing of the rest. A wall is on an edge
    # and a pixel is a square, so a wall inks the square that holds it and
    # the corner it runs to: a cell is two pixels, one of wall and one of way.
    box = np.zeros((BH, BW), bool)
    box[wy0 - by0:wy0 - by0 + SIZE, wx0 - bx0:wx0 - bx0 + SIZE] = True
    ink = np.zeros((BH, BW), bool)
    door_px = np.zeros((BH, BW), bool)
    for (x, y, col), code in walls.items():
        px, py = wx0 + x - bx0, wy0 + y - by0
        if code == "d":
            door_px[py, px] = True
            continue
        ink[py, px] = True
        qx, qy = (px + 1, py) if col == 3 else (px, py + 1)
        if qx < BW and qy < BH:
            ink[qy, qx] = True
    broad, keep = region_fn(bx0, by0, bx1, by1)
    zero = np.zeros((BH, BW), bool)
    hin, hout = m["heart_door"]
    door_sq = (wx0 + hout[0] * PITCH, wy0 + hout[1] * PITCH)
    t = dict(x0=bx0, y0=by0, W=BW, H=BH, road=broad, keep=keep, tunnel=box, chamber=zero, trunk=zero, channel=zero,
             room_id=np.zeros((BH, BW), int), cave_id=np.zeros((BH, BW), int),
             shafts=[], dropped=[], junctions=[], street_of={}, caves=[], hatches=[], gas=[], outfalls=[],
             made=False, tid=LAB_ID, lair=None, gated=set(), gates=[], keys=[],
             rooms=[dict(id=i + 1, kind=kind, rect=(wx0 + cx * PITCH - bx0, wy0 + cy * PITCH - by0, w * PITCH, h * PITCH))
                    for i, (kind, cx, cy, w, h) in enumerate(m["rooms"])])
    t["labyrinth"] = dict(
        entry=(wx0 + ENTRY[0], wy0 + ENTRY[1]), exit=(wx0 + EXIT[0], wy0 + EXIT[1]),
        heart=(wx0 + HEART[1] * PITCH + HEART[3] * PITCH // 2, wy0 + HEART[2] * PITCH + HEART[4] * PITCH // 2),
        door=door_sq, origin=(wx0, wy0), size=SIZE, lights=lights, length=m["length"] * PITCH,
        dead_ends=len(m["dead_ends"]), caches=caches, dead=len(dead), seed=m["seed"])
    t["map_ink"], t["map_door"] = ink, door_px
    if plan_path:
        draw_plan(m, floor, walls, F, D, plan_path)
    return dict(tid=LAB_ID, name=LAB_NAME, t=t, chunks=dict(mine), ladders=[], furniture=furniture, dead=dead,
                cave_furniture=[], cave_dead=[], pictures=[], warren=([], []))


def draw_plan(m, floor, walls, F, D, path, scale=6):
    """The whole labyrinth, for whoever works on it (never shipped: the
    players' map shows only what they have walked). The way from the gate to the heart
    in green, caches in yellow, the dead in red, doors in cyan."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (SIZE * scale + 1, SIZE * scale + 1), (22, 22, 26))
    d = ImageDraw.Draw(img)
    for (x, y), f in floor.items():
        d.rectangle([x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1],
                    fill=(86, 70, 52) if f == "u" else (58, 58, 62))
    # The way: back from the heart's door by the walk from the gate.
    def pair(a, b):
        return (a, b) if a < b else (b, a)
    cur = m["heart_door"][1]
    while cur is not None:
        d.rectangle([cur[0] * PITCH * scale + 3, cur[1] * PITCH * scale + 3,
                     (cur[0] + 1) * PITCH * scale - 4, (cur[1] + 1) * PITCH * scale - 4], fill=(40, 120, 60))
        cur = next((n for n in ((cur[0] + dx, cur[1] + dy) for dx, dy in N4)
                    if n in m["free"] and pair(cur, n) in m["open"] and m["dist"][n] == m["dist"][cur] - 1), None)
    for x, y, s, loot, _e in F:
        d.rectangle([x * scale + 2, y * scale + 2, (x + 1) * scale - 3, (y + 1) * scale - 3],
                    fill=(230, 200, 40) if loot else (150, 110, 60))
    for x, y, _o in D:
        d.ellipse([x * scale + 2, y * scale + 2, (x + 1) * scale - 3, (y + 1) * scale - 3], fill=(210, 40, 40))
    for (x, y, col), code in walls.items():
        ink = (0, 230, 230) if code == "d" else (232, 226, 210)
        if col == 3:
            d.line([x * scale, y * scale, (x + 1) * scale, y * scale], fill=ink, width=3 if code == "d" else 2)
        else:
            d.line([x * scale, y * scale, x * scale, (y + 1) * scale], fill=ink, width=3 if code == "d" else 2)
    for (x, y), ink in ((ENTRY, (255, 255, 255)), (EXIT, (255, 140, 0))):
        d.rectangle([x * scale + 1, y * scale + 1, (x + 1) * scale - 2, (y + 1) * scale - 2], outline=ink, width=2)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


if __name__ == "__main__":
    # The maze alone, without the three-minute run: its numbers, and its plan.
    import sys
    m = best_maze()
    floor, walls = squares(m)
    F, D, L, dress, caches = furnish(m, floor, walls)
    print("seed %d: the way to the heart is %d cells (%d squares); %d dead ends, %d caches, %d dead, %d lights"
          % (m["seed"], m["length"], m["length"] * PITCH, len(m["dead_ends"]), caches, len(D), len(L)))
    if len(sys.argv) > 1:
        draw_plan(m, floor, walls, F, D, sys.argv[1])
        print("wrote", sys.argv[1])
