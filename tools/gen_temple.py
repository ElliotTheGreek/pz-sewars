"""The temple of the rat cult: one in the world, between two towns (DESIGN.md 7d).

Called by tools/gen_sewers.py after every town is laid out and encoded, and
before anything is written. Nothing here moves a square a save holds: the
temple is a town of its own in chunks no town has, and the only records of
another town it touches are the wall its passages break through and the rock
beside it.

  the site      under the fields between two small networks on the road from
                Muldraugh to West Point (TEMPLE_NEAR), the nearest spot clear
                of every building, basement, pond and tunnel
  the temple    built: brick and concrete, a rectangle of rooms each with a
                square of rock round it -- a pillared hall with the idol at its
                north end, a sanctum and a reliquary behind it, a dormitory,
                a vestry, pens, a refectory, a scriptorium, stores, an
                offering pit, and a postern with a ladder up to a trapdoor in
                the field (nobody is ever shut in: DESIGN.md 2)
  the passages  dug: from each of its two gates a winding earth tunnel out to
                the nearest plain wall of a different town's sewer, broken
                through from the cult's side (floor `p`, breach `O` / `Q`)
  what is in it furniture, the cult's dead standing where they stood, pictures
                hung on its walls, its lights, and three writings that mark
                the rats' nest under Louisville on the reader's map

Returns an entry shaped like a town's, for gen_sewers to write.
"""
import collections
import heapq
import random

import numpy as np
from scipy import ndimage as ndi

N4 = [(0, -1), (-1, 0), (1, 0), (0, 1)]

TEMPLE_ID = "temple"
TEMPLE_NAME = "the Knox fields"
TEMPLE_NEAR = (11530, 8570)     # the middle of where it should be
TEMPLE_SEARCH = 140             # how far from there a site may be
TEMPLE_REGION = 460             # the world looked at round it, each way
PASSAGE_MAX = 420               # the longest passage, in squares
W, H = 63, 57                   # the plan's box, local squares

# Our tiles (tools/gen_sewer_art.py TILES_DEF, by index; SEW_Config.Sprites.cult names the same).
OURS = {
    "sigil": {"W": "sewars_01_48", "N": "sewars_01_49"},
    "burrow": {"W": "sewars_01_50", "N": "sewars_01_51"},
    "torch": {"W": "sewars_01_52", "N": "sewars_01_53"},
    "banner": {"W": "sewars_01_54", "N": "sewars_01_55"},
    "mural": ["sewars_01_56", "sewars_01_57", "sewars_01_58"],      # a triptych, on a north wall
    "idol": "sewars_01_59",
    "brazier": "sewars_01_60",
    "candles": "sewars_01_61",
    "circle": ["sewars_01_%d" % i for i in range(62, 71)],          # 3x3, row by row from the north-west
    "offering": "sewars_01_71",
    "bones": "sewars_01_40",
}
# Vanilla's, each checked against tools/_catalog/tiles.json by tests/test_assets.py.
V = {
    "pewN": ["location_community_church_small_01_56", "location_community_church_small_01_57",
             "location_community_church_small_01_58"],
    "altar": ["location_community_church_small_01_40", "location_community_church_small_01_41"],
    "lectern": "location_community_church_small_01_44",
    "slab": ["location_community_medical_01_79", "location_community_medical_01_78"],      # north end, south end
    "table": ["camping_01_9", "camping_01_11", "camping_01_8", "camping_01_10"],          # 2x2: nw, ne, sw, se
    "angelE": "location_community_cemetary_01_12",
    "angelW": "location_community_cemetary_01_14",
    "angelS": "location_community_cemetary_01_11",
    "cairn": "location_community_cemetary_01_30",
    "picket": "location_community_cemetary_01_31",
    "grave": ["location_community_cemetary_01_16", "location_community_cemetary_01_17"],
    "hide": ["rugs_animals_74", "rugs_animals_75", "rugs_animals_72", "rugs_animals_73"],  # 2x2: nw, ne, sw, se
    "bagS": ["camping_02_84", "camping_02_85"],
    "blood": ["overlay_blood_floor_01_0", "overlay_blood_floor_01_8", "overlay_blood_floor_01_16"],
    "crate_metal": "constructedobjects_01_46",
    "crate_wood": "carpentry_01_16",
    "shelves": "carpentry_02_64",
}
CULTIST = "Cultist"
PRISONERS = ("Generic01", "Generic03", "Hobbo", "Redneck")

# The rooms: (kind, x, y, w, h, floor, wall). A square of rock stands between
# any two; `kind` is the room's name on the sewer map (IGUI_SEW_Shelter_<kind>).
ROOMS = [
    ("temple_pilgrims", 6, 3, 19, 8, "h", "c"),
    ("temple_sanctum", 28, 3, 9, 8, "a", "b"),
    ("temple_reliquary", 38, 3, 9, 8, "q", "b"),
    ("temple_hall", 22, 12, 19, 33, "h", "b"),
    ("temple_dormitory", 6, 12, 15, 11, "q", "c"),
    ("temple_vestry", 6, 24, 15, 7, "q", "c"),
    ("temple_pens", 15, 32, 6, 13, "h", "c"),
    ("temple_refectory", 42, 12, 15, 11, "q", "c"),
    ("temple_scriptorium", 42, 24, 15, 7, "q", "c"),
    ("temple_stores", 42, 32, 15, 7, "h", "c"),
    ("temple_postern", 42, 40, 7, 5, "h", "c"),
    ("temple_pit", 50, 40, 7, 5, "h", "c"),
    ("temple_narthex", 24, 46, 15, 7, "h", "b"),
]
# The pens' three cells, off the west side of their corridor: no name of their own.
CELLS = [(6, 32, 8, 4), (6, 37, 8, 4), (6, 42, 8, 3)]
# A door cell stands in the rock between two rooms: (x, y, the neighbour its
# door is toward). The door hangs on the edge between the two.
DOORS = [
    (23, 11, (23, 10)),                      # pilgrims' hall -> the hall
    (29, 11, (29, 10)), (35, 11, (35, 10)),  # the hall -> the sanctum, either side of the idol
    (37, 6, (36, 6)),                        # the sanctum -> the reliquary
    (21, 17, (20, 17)), (21, 27, (20, 27)), (21, 38, (20, 38)),      # the west wing
    (41, 17, (40, 17)), (41, 27, (40, 27)), (41, 35, (40, 35)), (41, 42, (40, 42)),   # the east wing
    (14, 33, (13, 33)), (14, 38, (13, 38)), (14, 43, (13, 43)),      # the cells
    (53, 39, (53, 38)),                      # the stores -> the pit
]
ARCH = [(30, 45), (31, 45), (32, 45)]        # the hall -> the narthex, open
# The two gates: (the door cell, the way out). Three squares straight out, then the digging.
GATES = [((15, 2), (0, -1)), ((31, 53), (0, 1))]
COLUMNS = [(x, y) for x in (26, 36) for y in range(16, 41, 4)]
TRAP = (45, 40)                              # the foot of the ladder up to the field
IDOL = (31, 12)


def h32(*v):
    import hashlib
    return int(hashlib.md5(",".join(map(str, v)).encode()).hexdigest()[:8], 16)


def plan():
    """The temple, local squares: ({(x, y): floor}, {(x, y): wall style}, {edge: 'd'}, rooms)."""
    floor, style, doors = {}, {}, {}
    for kind, x, y, w, h, f, wall in ROOMS:
        for cx in range(x, x + w):
            for cy in range(y, y + h):
                floor[(cx, cy)] = f
                style[(cx, cy)] = wall
    for x, y, w, h in CELLS:
        for cx in range(x, x + w):
            for cy in range(y, y + h):
                floor[(cx, cy)] = "h"
                style[(cx, cy)] = "c"
    for p in COLUMNS:
        del floor[p]
        del style[p]
    # The nave's runner, the dais, and on through the arch to the south gate.
    for cy in range(12, 53):
        for cx in (30, 31, 32):
            if (cx, cy) in floor or (cx, cy) in ARCH:
                floor[(cx, cy)] = "a"
                style.setdefault((cx, cy), "b")
    for cx in range(27, 36):
        for cy in range(12, 16):
            floor[(cx, cy)] = "a"

    def edge(a, b):
        return (max(a[0], b[0]), max(a[1], b[1]), 3 if a[0] == b[0] else 4)
    for x, y, toward in DOORS:
        # The style of whichever room it leads from, so its frame matches the wall it is in.
        other = (2 * x - toward[0], 2 * y - toward[1])
        floor[(x, y)] = "h"
        style[(x, y)] = style.get(other, style.get(toward, "c"))
        doors[edge((x, y), toward)] = "d"
    for (gx, gy), (dx, dy) in GATES:
        floor[(gx, gy)] = "h"
        style[(gx, gy)] = style[(gx - dx, gy - dy)]
        doors[edge((gx, gy), (gx + dx, gy + dy))] = "d"
    floor[TRAP] = "g"
    return floor, style, doors, edge


def furnish():
    """What stands in the temple: (furniture, pictures, dead, lights), local
    squares. Furniture is (x, y, sprite, loot, extra-slot); a slot ("j1" ..)
    is filled with a journal's code by dig()."""
    F, P, D, L = [], [], [], []

    def put(x, y, sprite, loot=None, slot=None):
        F.append((x, y, sprite, loot, slot))

    def grid(x, y, sprites, across):
        for i, s in enumerate(sprites):
            put(x + i % across, y + i // across, s)

    def cult(x, y, fx=None, fy=None):
        D.append((x, y, CULTIST, fx, fy))

    def torchN(x, y):
        P.append((x, y, OURS["torch"]["N"]))
        L.append((x, y))

    def torchW(x, y):
        P.append((x, y, OURS["torch"]["W"]))
        L.append((x, y))

    def brazier(x, y):
        put(x, y, OURS["brazier"])
        L.append((x, y))

    def candles(x, y):
        put(x, y, OURS["candles"])
        L.append((x, y))

    # The hall. The idol against the north wall with its triptych behind it,
    # a brazier either side, the altar on the dais, the slab in the circle.
    ix, iy = IDOL
    put(ix, iy, OURS["idol"])
    for i, s in enumerate(OURS["mural"]):
        P.append((ix - 1 + i, iy, s))
    brazier(ix - 3, iy)
    brazier(ix + 3, iy)
    grid(ix - 1, iy + 2, V["altar"], 2)
    candles(ix + 1, iy + 2)
    candles(ix - 2, iy + 2)
    put(ix - 2, iy + 3, OURS["offering"])
    cx, cy = ix, iy + 6
    for i, s in enumerate(OURS["circle"]):
        put(cx - 1 + i % 3, cy - 1 + i // 3, s)
    put(cx, cy - 1, V["slab"][0])
    put(cx, cy, V["slab"][1])
    put(cx - 1, cy, V["blood"][0])
    put(cx + 1, cy + 1, V["blood"][1])
    put(cx, cy + 2, V["blood"][2])
    # The circle of them, standing round the slab, turned to it.
    for dx, dy in ((-3, 0), (3, 0), (0, 3), (-2, -2), (2, -2), (-2, 2), (2, 2)):
        cult(cx + dx, cy + dy, cx, cy)
    cult(ix, iy + 3, cx, cy)                       # and whoever led them, at the altar
    for py in range(23, 39, 3):                    # the pews, either side of the runner
        grid(27, py, V["pewN"], 3)
        grid(33, py, V["pewN"], 3)
    for py in (14, 22, 31, 40):                    # hooded angels down the side walls
        put(22, py, V["angelE"])
        put(40, py, V["angelW"])
    for px in (24, 38):
        torchN(px, 12)
    for py in (18, 26, 34, 42):
        torchW(22, py)
    for x, y in COLUMNS[::2]:                      # candles at the feet of the columns
        candles(x + (-1 if x < 31 else 1), y)
    for px in (26, 36):
        P.append((px, 12, OURS["banner"]["N"]))
    for py in (20, 30, 40):
        P.append((22, py, OURS["banner"]["W"]))

    # The narthex: the south gate's hall.
    brazier(25, 47)
    brazier(37, 47)
    for px in (26, 28, 34, 36):
        P.append((px, 46, OURS["banner"]["N"]))
    torchW(24, 49)
    grid(26, 50, V["hide"], 2)
    grid(35, 50, V["hide"], 2)
    cult(29, 49, 31, 52)
    cult(33, 49, 31, 52)

    # The pilgrims' hall: the north gate's. What they brought, heaped by the wall.
    for px in (8, 12, 18, 22):
        torchN(px, 3)
    P.append((10, 3, OURS["banner"]["N"]))
    P.append((20, 3, OURS["banner"]["N"]))
    P.append((6, 6, OURS["sigil"]["W"]))
    P.append((14, 3, OURS["burrow"]["N"]))
    put(6, 3, V["crate_wood"], "cultOfferings", "j4")
    put(7, 3, V["crate_wood"], "cultOfferings")
    put(6, 9, V["cairn"])
    put(7, 10, OURS["offering"])
    candles(6, 10)
    candles(24, 3)
    grid(10, 7, V["hide"], 2)
    grid(18, 7, V["hide"], 2)
    cult(13, 8, 15, 3)
    cult(19, 5, 15, 3)

    # The sanctum: whoever spoke for the rats, their book and their bed.
    torchN(29, 3)
    torchN(35, 3)
    P.append((32, 3, OURS["sigil"]["N"]))
    put(30, 3, V["shelves"], "cultScripture", "j1")
    put(34, 3, V["shelves"], "cultRelics")
    put(32, 5, V["lectern"])
    candles(31, 5)
    candles(33, 5)
    grid(28, 9, V["bagS"], 2)
    put(36, 10, V["crate_metal"], "cultRelics")
    cult(32, 7, 32, 5)

    # The reliquary.
    torchN(42, 3)
    P.append((40, 3, OURS["banner"]["N"]))
    P.append((44, 3, OURS["banner"]["N"]))
    put(39, 3, V["shelves"], "cultRelics")
    put(41, 3, V["crate_metal"], "cultRelics")
    put(43, 3, V["crate_metal"], "cultArms")
    put(45, 3, V["shelves"], "cultRelics")
    put(46, 6, V["angelW"])
    candles(46, 5)
    candles(46, 7)
    put(42, 8, OURS["offering"])

    # The dormitory: bedrolls in two rows.
    torchN(8, 12)
    torchN(18, 12)
    for px in (7, 10, 13, 16):
        grid(px, 13, V["bagS"], 2)
        grid(px, 21, V["bagS"], 2)
    put(6, 12, V["crate_wood"], "cultRobes")
    put(20, 12, V["crate_wood"], "survival", "j3")
    P.append((6, 17, OURS["sigil"]["W"]))
    for x, y in ((8, 16), (12, 18), (15, 16), (18, 19), (10, 19)):
        cult(x, y)

    # The vestry: where they robed.
    torchN(13, 24)
    for px in (7, 9, 11):
        put(px, 24, V["shelves"], "cultRobes")
    put(17, 24, V["crate_wood"], "cultRobes")
    put(19, 24, V["crate_metal"], "cultArms")
    P.append((15, 24, OURS["banner"]["N"]))
    grid(12, 27, V["hide"], 2)

    # The pens: a corridor and three cells, and what was kept for the slab.
    torchN(17, 32)
    torchW(15, 40)
    P.append((19, 32, OURS["burrow"]["N"]))
    put(20, 44, V["crate_wood"], "hardware")
    for i, (x, y, w, h) in enumerate(CELLS):
        put(x, y, OURS["bones"])
        grid(x + 2, y, V["bagS"], 2)
        D.append((x + 5, y + 1, PRISONERS[i % len(PRISONERS)], None, None))
        if i != 1:
            D.append((x + 3, y + 2, PRISONERS[(i + 2) % len(PRISONERS)], None, None))

    # The refectory: three tables and the larder.
    torchN(44, 12)
    torchN(54, 12)
    for px in (44, 48, 52):
        grid(px, 16, V["table"], 2)
    put(42, 12, V["shelves"], "cultLarder")
    put(46, 12, V["shelves"], "cultLarder")
    put(50, 12, V["crate_wood"], "food")
    put(52, 12, V["crate_wood"], "cultLarder")
    P.append((48, 12, OURS["banner"]["N"]))
    for x, y in ((45, 19), (49, 15), (53, 19)):
        cult(x, y)

    # The scriptorium: the shelves, a lectern, and the ledger.
    torchN(49, 24)
    for i, px in enumerate((43, 45, 47, 51, 53, 55)):
        # The ledger; and beside it somebody's map of the way to the nest (m2: SEW_Maps).
        put(px, 24, V["shelves"], "cultScripture", "j2" if i == 0 else "m2" if i == 1 else None)
    put(49, 27, V["lectern"])
    candles(48, 27)
    candles(50, 27)
    P.append((42, 25, OURS["sigil"]["W"]))
    cult(49, 28, 49, 27)
    cult(53, 28)

    # The stores.
    torchN(49, 32)
    for px, piece, loot in ((43, "crate_wood", "food"), (45, "crate_wood", "cultLarder"), (47, "crate_metal", "tools"),
                            (51, "crate_metal", "hardware"), (53, "crate_wood", "survival"), (55, "crate_wood", "fuel")):
        put(px, 32, V[piece], loot)
    put(42, 38, V["crate_wood"], "food")
    put(56, 38, V["crate_metal"], "medical")

    # The postern: the ladder, and a lamp left burning by it.
    candles(42, 44)
    put(48, 40, V["crate_wood"], "survival")
    P.append((43, 40, OURS["sigil"]["N"]))

    # The pit: what was left of what they gave.
    torchN(51, 40)
    for i, (px, py) in enumerate(((51, 42), (53, 42), (55, 42))):
        put(px, py, V["grave"][i % 2])
        put(px, py + 1, V["picket"])
    put(56, 40, V["cairn"])
    put(52, 41, OURS["bones"])
    put(54, 43, OURS["bones"])
    put(50, 44, OURS["offering"])
    candles(56, 44)
    return F, P, D, L


def dig(built, journals, region_fn, room_mask_fn, under_fn, water_fn):
    """Sites and digs the temple. `built` is every town so far: dicts with
    tid, t (the town's arrays) and chunks ({(cx, cy): {(x, y): record}},
    world squares), whose records this may add to and patch. Returns the
    temple's own entry."""
    nx, ny = TEMPLE_NEAR
    R = TEMPLE_REGION
    rx0, ry0 = nx - R, ny - R
    S = 2 * R + 1
    road, _keep = region_fn(rx0, ry0, rx0 + S - 1, ry0 + S - 1)
    rooms = room_mask_fn(rx0, ry0, rx0 + S - 1, ry0 + S - 1)
    under = under_fn(rx0, ry0, rx0 + S - 1, ry0 + S - 1)
    water, ground = water_fn(rx0, ry0, rx0 + S - 1, ry0 + S - 1)
    blocked = ndi.binary_dilation(rooms | under, iterations=2) | water
    blocked[:4, :] = blocked[-4:, :] = blocked[:, :4] = blocked[:, -4:] = True

    # Every town's squares in the region: what is space, what is plain
    # walkway, what a breach must keep clear of, and whose chunk is whose.
    space = np.zeros((S, S), bool)
    plain = np.zeros((S, S), bool)
    avoid = np.zeros((S, S), bool)
    any_rec = np.zeros((S, S), bool)
    host_of = np.full((S, S), -1, int)
    owner = {}
    recs = {}
    for i, b in enumerate(built):
        for ck, rows in b["chunks"].items():
            owner[ck] = i
            if ck[0] * 8 + 7 < rx0 or ck[0] * 8 >= rx0 + S or ck[1] * 8 + 7 < ry0 or ck[1] * 8 >= ry0 + S:
                continue
            for (wx, wy), r in rows.items():
                x, y = wx - rx0, wy - ry0
                if not (0 <= x < S and 0 <= y < S):
                    continue
                recs[(wx, wy)] = r
                any_rec[y, x] = True
                if r[2] not in ".r":
                    space[y, x] = True
                    host_of[y, x] = i
                    plain[y, x] = r[2] == "t" and r[5] == "." and r[6] == "."
                if r[5] in "Ll" or r[2] in "wg" or any(c in "djoqxyz" for c in r[3:5]):
                    avoid[y, x] = True
        t = b["t"]
        for g in t.get("gas", []):
            for gx, gy in g["squares"]:
                x, y = t["x0"] + gx - rx0, t["y0"] + gy - ry0
                if 0 <= x < S and 0 <= y < S:
                    avoid[y, x] = True
        for hh in t.get("hatches", []):
            for gx, gy in hh["path"] + [hh["hatch"]]:
                x, y = t["x0"] + gx - rx0, t["y0"] + gy - ry0
                if 0 <= x < S and 0 <= y < S:
                    avoid[y, x] = True
    avoid = ndi.binary_dilation(avoid, structure=np.ones((9, 9), bool))
    near_space = ndi.binary_dilation(space, structure=np.ones((5, 5), bool))

    # The site: the nearest origin to TEMPLE_NEAR whose box is clear of
    # everything by six squares, in chunks no town has, with open ground over
    # the trapdoor.
    floor, style, doors, edge = plan()
    clear = ~(blocked | ndi.binary_dilation(any_rec, structure=np.ones((13, 13), bool)))
    best = None
    for dy in range(-TEMPLE_SEARCH, TEMPLE_SEARCH + 1, 2):
        for dx in range(-TEMPLE_SEARCH, TEMPLE_SEARCH + 1, 2):
            ox, oy = nx - W // 2 + dx - rx0, ny - H // 2 + dy - ry0
            if ox < 12 or oy < 12 or ox + W + 12 >= S or oy + H + 12 >= S:
                continue
            d = dx * dx + dy * dy
            if best is not None and d >= best[0]:
                continue
            if not clear[oy - 6:oy + H + 6, ox - 6:ox + W + 6].all():
                continue
            tx, ty = ox + TRAP[0], oy + TRAP[1]
            if not ground[ty, tx] or road[ty, tx]:
                continue
            chunks = {((rx0 + x) // 8, (ry0 + y) // 8) for x in range(ox - 2, ox + W + 3, 4)
                      for y in range(oy - 2, oy + H + 3, 4)}
            if any(c in owner for c in chunks):
                continue
            best = (d, ox, oy)
    if best is None:
        raise SystemExit("the temple: no clear site within %d of %s" % (TEMPLE_SEARCH, TEMPLE_NEAR))
    _d, ox, oy = best
    wx0, wy0 = rx0 + ox, ry0 + oy                      # the plan's origin, world
    cells = {(ox + x, oy + y): f for (x, y), f in floor.items()}          # region squares
    foot = np.zeros((S, S), bool)
    foot[oy + 2:oy + 54, ox + 5:ox + 58] = True          # the rooms and the rock round them
    near_temple = ndi.binary_dilation(foot, structure=np.ones((5, 5), bool))

    # Where a passage may break into a sewer: a plain walkway square A with
    # rock for three squares straight out from one of its walls, that wall a
    # plain one with nothing hung on it.
    def wall_of(a, e):
        hx, hy, col = edge(a, e)
        r = recs.get((rx0 + hx, ry0 + hy))
        return r[col] if r else "."
    targets = {}
    ys, xs = np.nonzero(plain & ~avoid)
    for ax, ay in zip(xs.tolist(), ys.tolist()):
        for dx, dy in N4:
            e, e2, e3 = [(ax + dx * k, ay + dy * k) for k in (1, 2, 3)]
            if not (4 <= e3[0] < S - 4 and 4 <= e3[1] < S - 4):
                continue
            if space[e[1], e[0]] or blocked[e[1], e[0]] or blocked[e2[1], e2[0]] or blocked[e3[1], e3[0]]:
                continue
            if wall_of((ax, ay), e) not in "cb":
                continue
            holder = recs.get((rx0 + max(ax, e[0]), ry0 + max(ay, e[1])))
            if holder and (holder[5] != "." or holder[6] != "."):
                continue
            if any(space[e[1] + b, e[0] + a] for a, b in N4 if (e[0] + a, e[1] + b) != (ax, ay)):
                continue
            if any(space[e2[1] + b, e2[0] + a] for a, b in N4):
                continue
            # From here on, two squares of rock from every sewer.
            if near_space[e3[1], e3[0]]:
                continue
            targets.setdefault(e3, ((ax, ay), e, e2, int(host_of[ay, ax])))

    passages, taken_hosts = [], set()
    dug = np.zeros((S, S), bool)
    for gi, ((gx, gy), (dx, dy)) in enumerate(GATES):
        g = [(ox + gx + dx * k, oy + gy + dy * k) for k in (1, 2, 3)]
        ok = ~blocked & ~near_space & ~near_temple & ~ndi.binary_dilation(dug, structure=np.ones((7, 7), bool))
        start = g[2]
        best_c = {start: 0.0}
        prev = {start: None}
        q = [(0.0, start[0], start[1])]
        end = None
        while q:
            c, x, y = heapq.heappop(q)
            if c > best_c.get((x, y), 1e18):
                continue
            tg = targets.get((x, y))
            if tg and tg[3] not in taken_hosts and (x, y) != start:
                end = (x, y)
                break
            if c > PASSAGE_MAX * 2.2:
                continue
            for a, b in N4:
                n = (x + a, y + b)
                if not (4 <= n[0] < S - 4 and 4 <= n[1] < S - 4):
                    continue
                if not ok[n[1], n[0]]:
                    continue
                nc = c + 1 + (h32("cult", gi, rx0 + n[0], ry0 + n[1]) % 7) / 3.0
                if nc < best_c.get(n, 1e18):
                    best_c[n] = nc
                    prev[n] = (x, y)
                    heapq.heappush(q, (nc, n[0], n[1]))
        if not end:
            raise SystemExit("the temple: gate %d reaches no sewer within %d squares" % (gi, PASSAGE_MAX))
        a, e, e2, host = targets[end]
        path, cur = [], end
        while cur:
            path.append(cur)
            cur = prev[cur]
        path = [e, e2] + path + [g[1], g[0]]                 # from the sewer to the gate
        if len(path) > PASSAGE_MAX:
            raise SystemExit("the temple: gate %d's passage is %d squares" % (gi, len(path)))
        taken_hosts.add(host)
        for x, y in path:
            dug[y, x] = True
        passages.append(dict(a=a, path=path, host=host, gate=(ox + gx, oy + gy), wide=[]))

    # Dug by hand: a square wider here and there, never near either end.
    rng = random.Random(1993 * 9001 + h32("temple"))
    for p in passages:
        ok = ~blocked & ~near_space & ~near_temple
        for i in range(5, len(p["path"]) - 6):
            if rng.random() >= 0.3:
                continue
            (x, y), (px, py) = p["path"][i], p["path"][i - 1]
            sx, sy = (y - py, x - px) if rng.random() < 0.5 else (py - y, px - x)
            n = (x + sx, y + sy)
            mine = set(p["path"]) | set(p["wide"])
            if ok[n[1], n[0]] and not dug[n[1], n[0]] and \
                    all((n[0] + a, n[1] + b) in mine or not dug[n[1] + b, n[0] + a]
                        for a in (-2, -1, 0, 1, 2) for b in (-2, -1, 0, 1, 2)):
                p["wide"].append(n)
                dug[n[1], n[0]] = True

    # --- records ------------------------------------------------------------------------------
    # Every square of ours (region coords): its floor and the walls it shows.
    for p in passages:
        for c in p["path"] + p["wide"]:
            cells[c] = "p"
    styles = {(ox + x, oy + y): s for (x, y), s in style.items()}
    door_edges = {(ox + x, oy + y, col): code for (x, y, col), code in doors.items()}
    breach = {}
    for p in passages:
        e = p["path"][0]
        breach[edge(p["a"], e)] = "Q" if wall_of(p["a"], e) == "b" else "O"
    out = {}          # (wx, wy) -> record as a list; a town's own record is copied in before it is changed
    patched = set()

    def rec(x, y):
        k = (rx0 + x, ry0 + y)
        if k not in out:
            if k in recs:
                out[k] = list(recs[k])
                patched.add(k)
            else:
                out[k] = [str(k[0] % 8), str(k[1] % 8), ".", ".", ".", ".", "."]
        return out[k]

    for (x, y), f in cells.items():
        rec(x, y)[2] = f
    for (x, y), f in cells.items():
        for a, b in N4:
            n = (x + a, y + b)
            hx, hy, col = edge((x, y), n)
            if n in cells:
                code = door_edges.get((hx, hy, col), ".")
            elif space[n[1], n[0]]:
                code = breach.get((hx, hy, col))
                if code is None:
                    raise SystemExit("the temple: %s touches a sewer at %d,%d off its breach" % (f, rx0 + x, ry0 + y))
            else:
                code = "e" if f == "p" else styles[(x, y)]
            r = rec(hx, hy)
            r[col] = code
            if r[2] == ".":
                r[2] = "r"
    # Pillars, as gen_sewers.encode stands them: where a north wall and a
    # west wall end at the same corner. On our own squares only.
    hard = "cbd"
    for (wx, wy), r in list(out.items()):
        if (wx, wy) in patched or r[3] not in hard or r[5] != ".":
            continue
        north, here = out.get((wx + 1, wy - 1)), out.get((wx + 1, wy))
        if north and north[4] in hard and not (here and (here[3] != "." or here[4] != ".")):
            r[5] = "Q" if "b" in (r[3], north[4]) else "P"
    # The ladder up to the trapdoor, on the wall north of its square.
    tx, ty = ox + TRAP[0], oy + TRAP[1]
    tr = rec(tx, ty)
    if tr[3] not in "cb":
        raise SystemExit("the temple: no wall for the postern's ladder")
    tr[5] = "L"
    # What came down in the digging, and what they left at the hole.
    for p in passages:
        for i, (x, y) in enumerate(p["path"] + p["wide"]):
            r = rec(x, y)
            if r[5] != "." or r[6] != ".":
                continue
            roll = h32("cultdress", rx0 + x, ry0 + y) % 1000
            if i < 2 or roll < 90:
                r[6] = "z"
            elif roll < 120:
                r[6] = "v"
            elif roll < 145:
                r[6] = "u"

    # --- what is in it ------------------------------------------------------------------------
    F, P, D, lights = furnish()
    lair = next((b for b in built if b["t"].get("lair")), None)
    codes = {}
    if lair:
        lt = lair["t"]
        lx, ly = lt["x0"] + lt["lair"]["entry"][0], lt["y0"] + lt["lair"]["entry"][1]
        streets = [(sx, sy, st) for sx, sy, _lx, _ly, _e, st in lair["ladders"] if st]
        street = min(streets, key=lambda s: abs(s[0] - lx) + abs(s[1] - ly))[2] if streets else ""
        import math
        ang = math.atan2(ly - (wy0 + IDOL[1]), lx - (wx0 + IDOL[0]))
        compass = ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"]
        way = compass[int(round(ang / (math.pi / 4))) % 8]
        for n in (1, 2, 3):
            journals.append(dict(town=lair["tid"], x=lx, y=ly, kind="lair", text="cult_%d" % n, street=street, dir=way))
            codes["j%d" % n] = "j%d" % len(journals)
        # The pilgrims' way: the house whose hatch is nearest the nest by the tunnels.
        hx, hy = lt["lair_access"][0][1]
        journals.append(dict(town=lair["tid"], x=lt["x0"] + hx, y=lt["y0"] + hy, kind="hatch", text="cult_4",
                             street=street, dir=way))
        codes["j4"] = "j%d" % len(journals)
    furniture = [(wx0 + x, wy0 + y, s, loot, codes.get(slot, slot)) for x, y, s, loot, slot in F]
    for x, y, _s, _l, _e in F:
        if floor.get((x, y)) is None:
            raise SystemExit("the temple: furniture off its floor at %d,%d" % (x, y))
    pictures = []
    for x, y, s in P:
        r = out[(wx0 + x, wy0 + y)]
        col = 3 if s in [v["N"] for v in OURS.values() if isinstance(v, dict)] + OURS["mural"] else 4
        if r[col] not in "cb":
            raise SystemExit("the temple: a picture with no wall behind it at %d,%d (%s)" % (x, y, s))
        pictures.append((wx0 + x, wy0 + y, s))
    dead = [(wx0 + x, wy0 + y, o) + ((wx0 + fx, wy0 + fy) if fx is not None else ()) for x, y, o, fx, fy in D]
    taken_sq = {(x, y) for x, y, _s, _l, _e in F}
    for x, y, _o, _fx, _fy in D:
        if floor.get((x, y)) is None or (x, y) in taken_sq:
            raise SystemExit("the temple: one of the dead on no floor, or on furniture, at %d,%d" % (x, y))
    lights = sorted({(wx0 + x, wy0 + y) for x, y in lights})

    # The cult's marks: along each passage on its earth, and in the sewer by
    # the breach, on plain walls with nothing on them yet.
    signs = []
    for pi, p in enumerate(passages):
        for i, (x, y) in enumerate(p["path"]):
            if i < 6 or i % 14 != 6:
                continue
            r = out[(rx0 + x, ry0 + y)]
            side = "N" if r[3] == "e" else "W" if r[4] == "e" else None
            if side:
                pictures.append((rx0 + x, ry0 + y, OURS["sigil" if (i // 14) % 3 else "burrow"][side]))
                if (i // 14) % 2 == 0:
                    lights.append((rx0 + x, ry0 + y))
                    furniture.append((rx0 + x, ry0 + y, OURS["candles"], None, None))
        ax, ay = p["a"]
        near = sorted((abs(wx - rx0 - ax) + abs(wy - ry0 - ay), wx, wy) for (wx, wy), r in recs.items()
                      if r[2] == "t" and r[5] == "." and r[6] == "." and (wx, wy) not in out
                      and (r[3] in "cb" or r[4] in "cb") and 2 <= abs(wx - rx0 - ax) + abs(wy - ry0 - ay) <= 9)
        for k, (_dd, wx, wy) in enumerate(near[:2]):
            r = recs[(wx, wy)]
            signs.append((wx, wy, OURS["sigil" if k == 0 else "burrow"]["N" if r[3] in "cb" else "W"]))

    # --- whose chunk is whose -----------------------------------------------------------------
    mine = collections.defaultdict(dict)
    for (wx, wy), r in out.items():
        ck = (wx // 8, wy // 8)
        if ck in owner:
            built[owner[ck]]["chunks"][ck][(wx, wy)] = "".join(r)
            built[owner[ck]]["touched"] = True
        else:
            if (wx, wy) in patched:
                raise SystemExit("the temple: a town's record at %d,%d outside its chunks" % (wx, wy))
            mine[ck][(wx, wy)] = "".join(r)
    host_pictures = collections.defaultdict(list)
    own_pictures = []
    for wx, wy, s in pictures + signs:
        ck = (wx // 8, wy // 8)
        (host_pictures[owner[ck]] if ck in owner else own_pictures).append((wx, wy, s))
    for i, items in host_pictures.items():
        built[i].setdefault("pictures", []).extend(items)
    own_furniture = []
    for item in furniture:
        ck = (item[0] // 8, item[1] // 8)
        if ck in owner:
            built[owner[ck]]["cave_furniture"] = list(built[owner[ck]]["cave_furniture"]) + [item]
        else:
            own_furniture.append(item)
    # On the towns' own maps too, where a passage runs under their sheets.
    for p in passages:
        t = built[p["host"]]["t"]
        for x, y in p["path"] + p["wide"]:
            lx, ly = rx0 + x - t["x0"], ry0 + y - t["y0"]
            if 0 <= lx < t["W"] and 0 <= ly < t["H"]:
                t.setdefault("cult", []).append((lx, ly))

    # --- the temple as a town -----------------------------------------------------------------
    xs = [k[0] for k in out]
    ys = [k[1] for k in out]
    bx0, by0, bx1, by1 = min(xs), min(ys), max(xs), max(ys)
    BW, BH = bx1 - bx0 + 1, by1 - by0 + 1
    hall = np.zeros((BH, BW), bool)
    carpet = np.zeros((BH, BW), bool)
    quarters = np.zeros((BH, BW), int)
    passage = np.zeros((BH, BW), int)
    for (x, y), f in cells.items():
        lx, ly = rx0 + x - bx0, ry0 + y - by0
        if f == "p":
            passage[ly, lx] = 1
        elif f == "a":
            carpet[ly, lx] = True
        elif f == "q":
            quarters[ly, lx] = 1
        else:
            hall[ly, lx] = True
    broad, keep = region_fn(bx0, by0, bx1, by1)
    t = dict(x0=bx0, y0=by0, W=BW, H=BH, road=broad, keep=keep, tunnel=hall | carpet, chamber=carpet,
             trunk=np.zeros((BH, BW), bool), channel=np.zeros((BH, BW), bool), room_id=quarters, cave_id=passage,
             shafts=[], dropped=[], junctions=[], street_of={}, caves=[], hatches=[], gas=[], outfalls=[],
             made=False, tid=TEMPLE_ID, lair=None, gated=set(), gates=[], keys=[],
             rooms=[dict(id=i + 1, kind=kind, rect=(wx0 + x - bx0, wy0 + y - by0, w, h))
                    for i, (kind, x, y, w, h, _f, _w) in enumerate(ROOMS)])
    t["temple"] = dict(
        idol=(wx0 + IDOL[0], wy0 + IDOL[1]), trap=(rx0 + tx, ry0 + ty),
        # Where the dev build arrives: in the south passage, a short walk from
        # its gate -- never in the hall, where the dead would not be put down
        # beside whoever had just arrived (SEW_Build.spawn).
        hall=(rx0 + passages[1]["path"][-20][0], ry0 + passages[1]["path"][-20][1]),
        lights=lights,
        breaches=[dict(town=built[p["host"]]["tid"], a=(rx0 + p["a"][0], ry0 + p["a"][1]),
                       e=(rx0 + p["path"][0][0], ry0 + p["path"][0][1]),
                       gate=(rx0 + p["gate"][0], ry0 + p["gate"][1]), length=len(p["path"])) for p in passages])
    return dict(tid=TEMPLE_ID, name=TEMPLE_NAME, t=t, chunks=dict(mine), ladders=[], furniture=own_furniture,
                dead=dead, cave_furniture=[], cave_dead=[], pictures=own_pictures, warren=([], []))


def cross(built, journals, temple):
    """What the warren under Louisville says of the temple (ROADMAP 0.6): three
    writings left in its dens -- a pilgrim's last pages (the trapdoor in the
    field), a map on a hymn sheet (where the cult broke into West Point's
    sewer) and a county flood crew's log (where it broke into Muldraugh's) --
    each a journal that marks its place on the reader's map. Fills the slots
    gen_sewers.furnish_warren left in the dens' crates."""
    import math
    T = temple["t"]["temple"]
    host = next((b for b in built if b["t"].get("warren")), None)
    if not host:
        return
    lt = host["t"]
    fx, fy = lt["x0"] + lt["lair"]["centre"][0], lt["y0"] + lt["lair"]["centre"][1]
    compass = ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"]

    def way(x, y):
        return compass[int(round(math.atan2(y - fy, x - fx) / (math.pi / 4))) % 8]

    def street(town, x, y):
        b = next(q for q in built if q["tid"] == town)
        named = [(sx, sy, st) for sx, sy, _lx, _ly, _e, st in b["ladders"] if st]
        return min(named, key=lambda q: abs(q[0] - x) + abs(q[1] - y))[2] if named else ""

    north, south = T["breaches"][0], T["breaches"][1]
    marks = {
        "warren_1": dict(town=TEMPLE_ID, x=T["trap"][0], y=T["trap"][1], kind="temple", street=""),
        "warren_2": dict(town=north["town"], x=north["a"][0], y=north["a"][1], kind="breach",
                         street=street(north["town"], *north["a"])),
        "warren_3": dict(town=south["town"], x=south["a"][0], y=south["a"][1], kind="breach",
                         street=street(south["town"], *south["a"])),
    }
    codes = {}
    for text, m in sorted(marks.items()):
        journals.append(dict(m, text=text, dir=way(m["x"], m["y"])))
        codes[text] = "j%d" % len(journals)
    wf, wd = host["warren"]
    left = [slot for _x, _y, _s, _l, slot in wf if slot and slot not in codes and not slot.startswith("m")]
    if left:
        raise SystemExit("the warren: writings with no text: %s" % left)
    host["warren"] = ([(x, y, spr, loot, codes.get(slot, slot)) for x, y, spr, loot, slot in wf], wd)
