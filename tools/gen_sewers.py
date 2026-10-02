"""Lays out every town's sewers under the streets above them, and writes them as Lua.

    python tools/gen_sewers.py              # every town (a few minutes the first time; cached after)
    python tools/gen_sewers.py --plans      # and a plan of each town in design/art/plans/

DESIGN.md 4 is the why. The game ships 446 manhole covers and no sewers, so
the tunnels are made to fit the covers and the streets they sit on, offline,
from the map on disk, and the server builds what this writes. Nothing in the
game reads a map file.

For each town (a cluster of manholes):

  1. keep-out      building footprints (every room rectangle, any level),
                   dilated -- random basements are stamped under buildings
                   at world generation and a tunnel must never meet one --
                   and anything the map already has below ground
  2. centre lines  vanilla's own streets (maps/Muldraugh, KY/streets.xml:
                   1,098 named polylines with widths), rasterised and made
                   4-connected -- a diagonal step between walls cannot be
                   walked, so every diagonal gets an elbow
  3. width         from the street's width: a highway is a 5-wide trunk with
                   a sludge channel down it, a street a 3-wide main, a lane a
                   1-wide culvert
  4. shafts        every manhole gets a ladder on the square under it; one
                   off the named streets (a car park, an alley) is joined to
                   the network by a culvert that keeps under the road
  5. vaults        brick chambers at some junctions
  6. shelters      rooms off the tunnels behind a steel door (DESIGN.md 7)
  7. walls         on every edge between inside and out, and between a room
                   and the tunnel it opens off
  8. dressing      pipes, grime, graffiti, stencils, puddles, light pools

and the checks that make it shippable: every piece of tunnel reaches a ladder,
nothing is under a building, every manhole is either given a shaft or
reported as left shut.

Output (all generated, never hand-edited):

  Sewars/42/media/lua/shared/SEW/SEW_Index.lua          towns, shafts, shelters: small, every process
  Sewars/42/media/lua/server/SEW/Data/SEW_Town_<id>.lua the squares, by chunk: large, server only

A square is seven characters -- x and y in its chunk, floor, north wall, west
wall, fixture, dressing -- and SEW_Data.lua decodes it; the legend is there.
"""
import argparse
import collections
import glob
import hashlib
import heapq
import os
import random
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pzmap  # noqa: E402
import gen_temple  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "Sewars", "42", "media", "lua")
INDEX = os.path.join(LUA, "shared", "SEW", "SEW_Index.lua")
DATA = os.path.join(LUA, "server", "SEW", "Data")
PLANS = os.path.join(ROOT, "design", "art", "plans")
CACHE = os.path.join(ROOT, "tools", "_cache")
MAPS = os.path.dirname(pzmap.MAP)
CELL = pzmap.CELL

LINK = 220          # manholes closer than this along a chain are one town
MARGIN = 40         # tunnels reach this far past a town's outermost manholes
KEEP_OUT = 2        # squares kept clear round every building footprint
TRUNK_W = 10        # street width at or above which the tunnel is a 5-wide trunk
MAIN_W = 6          # ... a 3-wide main; below it, a 1-wide culvert
JOIN = 70           # how far a stray manhole's culvert may run to the network
SNAP = 16           # how far a street's loose end is carried on to meet another street
ROAD_RUN = 80       # how far a dead end is carried on under painted road to meet the network
CHAMBER_GAP = 45    # squares between brick vaults
SHELTER_GAP = 40    # squares between shelters
SEED = 1993
CAVE_PER_SHAFTS = 8   # one cave for so many shafts in a town (at least one where one fits)
CAVE_GAP = 50         # squares between breaches
CAVE_CLEAR = 4        # squares a breach keeps from a shaft or a shelter's door
# Houses with a way down (ROADMAP 0.4): a hatch in the floor of a room like
# these, joined to the network by a short culvert.
HATCH_ROOMS = ("garage", "garagestorage", "laundry", "kitchen", "shed", "storage", "storageunit", "janitor")
HATCH_PER_SHAFTS = 6  # one hatch for so many shafts in a town
HATCH_GAP = 40        # squares between hatches
HATCH_REACH = 30      # the longest culvert from a hatch to the network
HATCH_UNDER = 8       # the most squares of it under the house (and its margin)
# Towns the map gives few covers (ROADMAP 0.4: Louisville has 13 for ten times
# Muldraugh's buildings). A cell with this many street-level building squares
# is built up; built-up cells that touch are a district; a district with at
# least DISTRICT_MIN building squares and fewer than SPARSE vanilla covers per
# 10,000 of them gets covers of our own. The towns with covers have 10-30.
URBAN_CELL = 1500
DISTRICT_MIN = 5000
SPARSE = 5
COVER_GAP = 45        # squares between the covers we add, at junctions first
COVER_RUN = 70        # and along a long run of street with no junction

KINDS = ("maintenance", "pump", "squat", "laststand")
# The rats' nest (dig_lair): one, under Louisville's district, nearest this
# point with room for it -- the park south of downtown. LAIR_ORIGIN is the
# town's own origin (its x0, y0), checked when it is dug.
LAIR_TOWN = "louisville_3"
LAIR_NEAR = (12950, 2290)
LAIR_ORIGIN = (11776, 1024)
LAIR_CLEAR = 14       # rock round the nest's middle, clear of everything by two squares
LAIR_NEST_R = 6
LAIR_ROUS = 4
# The warren (dig_warren, 0.6): dens dug off the nest, each a rough round of
# earth this wide at the end of a run this long; this many wanted, at least
# WARREN_MIN or the layout is refused.
WARREN_DENS = 4
WARREN_MIN = 3
WARREN_R = (4, 5)
WARREN_RUN = (4, 7)
# Sewer gas (vent_gas): one stretch for so many shafts in a town, this many
# squares of culvert each, this far apart, and this far from any street ladder.
GAS_PER_SHAFTS = 12
GAS_MIN, GAS_MAX = 16, 48
GAS_GAP = 60
GAS_CLEAR = 10
# Storm-drain outfalls (dig_outfalls): a body of water this big or more (a
# swimming pool is smaller), culverts this long, banks this far apart, and at
# most this many to a town.
OUTFALL_WATER = 300
OUTFALL_MIN, OUTFALL_REACH = 8, 80
OUTFALL_GAP = 120
OUTFALL_MAX = 4
# Locked gates (gate_shelters): every town's key id is this plus a hash below
# 90,000,000 -- clear of vanilla's ids, which stay under 100,000,000.
GATE_KEY_BASE = 1900000000
N4 =[(0, -1), (-1, 0), (1, 0), (0, 1)]


# --- reading the map ------------------------------------------------------------------------

def cell_facts(cx, cy):
    """(road, keep, manholes) for one cell, cached: road and keep are 256x256 bool [y, x]."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "cell_%d_%d.npz" % (cx, cy))
    if os.path.exists(path):
        z = np.load(path)
        return z["road"], z["keep"], [tuple(int(v) for v in m) for m in z["holes"]]
    road = np.zeros((CELL, CELL), bool)
    keep = np.zeros((CELL, CELL), bool)
    holes = []
    ox, oy = cx * CELL, cy * CELL
    if os.path.exists(os.path.join(pzmap.MAP, "%d_%d.lotheader" % (cx, cy))):
        levels = pzmap.cell_levels(cx, cy, want=lambda lz: lz <= 0)
        for (x, y), ts in levels.get(0, {}).items():
            if any(t.startswith(pzmap.ROAD) for t in ts):
                road[y - oy, x - ox] = True
            if pzmap.MANHOLE in ts:
                holes.append((x, y))
        for z, sq in levels.items():
            if z < 0:
                for (x, y) in sq:
                    keep[y - oy, x - ox] = True
        for _name, _level, rects in pzmap.rooms(cx, cy):
            for (x, y, w, h) in rects:
                keep[max(0, y - oy):max(0, y - oy + h), max(0, x - ox):max(0, x - ox + w)] = True
    np.savez_compressed(path, road=road, keep=keep, holes=np.array(holes, int).reshape(-1, 2))
    return road, keep, holes


def clear_floor(cx, cy):
    """256x256 bool [y, x] for one cell, cached: squares at street level that
    hold floor and nothing else -- no wall, fixture, furniture or stairs --
    where a hatch can lie."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "clear_%d_%d.npz" % (cx, cy))
    if os.path.exists(path):
        return np.load(path)["clear"]
    clear = np.zeros((CELL, CELL), bool)
    if os.path.exists(os.path.join(pzmap.MAP, "%d_%d.lotheader" % (cx, cy))):
        for (x, y), ts in pzmap.cell_squares(cx, cy, 0).items():
            if ts and all(t.startswith("floors_") for t in ts):
                clear[y - cy * CELL, x - cx * CELL] = True
    np.savez_compressed(path, clear=clear)
    return clear


def under_map(x0, y0, x1, y1):
    """bool [y, x] for a world rectangle: squares the map itself has below
    street level (vanilla basements, the bunker), cached per cell."""
    os.makedirs(CACHE, exist_ok=True)
    out = np.zeros((y1 - y0 + 1, x1 - x0 + 1), bool)
    for cx in range(x0 // CELL, x1 // CELL + 1):
        for cy in range(y0 // CELL, y1 // CELL + 1):
            path = os.path.join(CACHE, "under_%d_%d.npz" % (cx, cy))
            if os.path.exists(path):
                u = np.load(path)["under"]
            else:
                u = np.zeros((CELL, CELL), bool)
                if os.path.exists(os.path.join(pzmap.MAP, "%d_%d.lotheader" % (cx, cy))):
                    for z, sq in pzmap.cell_levels(cx, cy, want=lambda lz: lz < 0).items():
                        for (x, y) in sq:
                            u[y - cy * CELL, x - cx * CELL] = True
                np.savez_compressed(path, under=u)
            ax0, ay0 = max(x0, cx * CELL), max(y0, cy * CELL)
            ax1, ay1 = min(x1, cx * CELL + CELL - 1), min(y1, cy * CELL + CELL - 1)
            if ax0 <= ax1 and ay0 <= ay1:
                out[ay0 - y0:ay1 - y0 + 1, ax0 - x0:ax1 - x0 + 1] = \
                    u[ay0 - cy * CELL:ay1 - cy * CELL + 1, ax0 - cx * CELL:ax1 - cx * CELL + 1]
    return out


def room_mask(x0, y0, x1, y1):
    """bool [y, x]: every room rectangle, any level, over a world rectangle --
    **including rooms listed by a neighbouring cell** that reach into this
    one. cell_facts marks a room only in the cell whose header lists it, so a
    building across a cell edge is half missing from `keep`; the 0.3 tunnels
    never met one, but the first caves and hatches did (found by
    test_layout, 0.4). The 0.3 layout keeps its own keep so nothing in a
    save moves; everything laid since plans against this."""
    out = np.zeros((y1 - y0 + 1, x1 - x0 + 1), bool)
    for cx in range(x0 // CELL - 1, x1 // CELL + 2):
        for cy in range(y0 // CELL - 1, y1 // CELL + 2):
            if not os.path.exists(os.path.join(pzmap.MAP, "%d_%d.lotheader" % (cx, cy))):
                continue
            for _name, _level, rects in pzmap.rooms(cx, cy):
                for rx, ry, w, h in rects:
                    a, b, c, d = max(rx, x0), max(ry, y0), min(rx + w - 1, x1), min(ry + h - 1, y1)
                    if a <= c and b <= d:
                        out[b - y0:d - y0 + 1, a - x0:c - x0 + 1] = True
    return out


def hatch_rooms(x0, y0, x1, y1):
    """[(name, [(x, y, w, h)])] of the street-level rooms a hatch may be in,
    within a world rectangle."""
    out = []
    for cx in range(x0 // CELL, x1 // CELL + 1):
        for cy in range(y0 // CELL, y1 // CELL + 1):
            if not os.path.exists(os.path.join(pzmap.MAP, "%d_%d.lotheader" % (cx, cy))):
                continue
            for name, level, rects in pzmap.rooms(cx, cy):
                if level == 0 and name in HATCH_ROOMS:
                    out.append((name, rects))
    return out


def clear_road(cx, cy):
    """256x256 bool [y, x] for one cell, cached: painted road at street level
    with nothing on it but road and its markings -- where a cover of ours can
    go. Not a kerb drain or a cover already there."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "road_%d_%d.npz" % (cx, cy))
    if os.path.exists(path):
        return np.load(path)["clear"]
    clear = np.zeros((CELL, CELL), bool)
    if os.path.exists(os.path.join(pzmap.MAP, "%d_%d.lotheader" % (cx, cy))):
        not_ok = set(pzmap.DRAINS) | {pzmap.MANHOLE}
        for (x, y), ts in pzmap.cell_squares(cx, cy, 0).items():
            if (ts and any(t.startswith(pzmap.ROAD) for t in ts)
                    and all((t.startswith(pzmap.ROAD) or t.startswith("street_decoration_01_")) and t not in not_ok
                            for t in ts)):
                clear[y - cy * CELL, x - cx * CELL] = True
    np.savez_compressed(path, clear=clear)
    return clear


WATER_TILES = ("blends_natural_02_0", "blends_natural_02_5", "blends_natural_02_6", "blends_natural_02_7")


def water_facts(cx, cy):
    """(water, ground) for one cell, cached, 256x256 bool [y, x] at street
    level: `water`, a square whose floor is one of vanilla's water tiles (the
    only four with the `water` property: tools/_catalog/tiles.json);
    `ground`, a dry square holding nothing but natural ground and its shore
    blends -- no tree, rock, fence or anything built -- where an outfall's
    grate can lie (DESIGN.md 7c)."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "water_%d_%d.npz" % (cx, cy))
    if os.path.exists(path):
        z = np.load(path)
        return z["water"], z["ground"]
    water = np.zeros((CELL, CELL), bool)
    ground = np.zeros((CELL, CELL), bool)
    if os.path.exists(os.path.join(pzmap.MAP, "%d_%d.lotheader" % (cx, cy))):
        for (x, y), ts in pzmap.cell_squares(cx, cy, 0).items():
            if not ts:
                continue
            if any(t in WATER_TILES for t in ts):
                water[y - cy * CELL, x - cx * CELL] = True
            elif all(t.startswith(("blends_natural_", "blends_grassoverlays_")) for t in ts):
                ground[y - cy * CELL, x - cx * CELL] = True
    np.savez_compressed(path, water=water, ground=ground)
    return water, ground


def water_region(x0, y0, x1, y1):
    """(water, ground) for a world rectangle (inclusive), as [y, x] arrays."""
    w, h = x1 - x0 + 1, y1 - y0 + 1
    water = np.zeros((h, w), bool)
    ground = np.zeros((h, w), bool)
    for cx in range(x0 // CELL, x1 // CELL + 1):
        for cy in range(y0 // CELL, y1 // CELL + 1):
            wa, gr = water_facts(cx, cy)
            ax0, ay0 = max(x0, cx * CELL), max(y0, cy * CELL)
            ax1, ay1 = min(x1, cx * CELL + CELL - 1), min(y1, cy * CELL + CELL - 1)
            if ax0 > ax1 or ay0 > ay1:
                continue
            sl = (slice(ay0 - cy * CELL, ay1 - cy * CELL + 1), slice(ax0 - cx * CELL, ax1 - cx * CELL + 1))
            water[ay0 - y0:ay1 - y0 + 1, ax0 - x0:ax1 - x0 + 1] = wa[sl]
            ground[ay0 - y0:ay1 - y0 + 1, ax0 - x0:ax1 - x0 + 1] = gr[sl]
    return water, ground


def sparse_districts(holes, names):
    """[(name, (cx0, cy0, cx1, cy1), set of cells)] -- built-up districts the
    map gives few covers, each a town of covers of our own."""
    built = {}
    for cx, cy, _h in pzmap.cells():
        built[(cx, cy)] = sum(w * h for _n, level, rects in pzmap.rooms(cx, cy) if level == 0
                              for _x, _y, w, h in rects)
    urban = {c for c, n in built.items() if n >= URBAN_CELL}
    per_cell = collections.Counter((x // CELL, y // CELL) for x, y in holes)
    seen, out = set(), []
    for start in sorted(urban):
        if start in seen:
            continue
        group, todo = set(), [start]
        while todo:
            c = todo.pop()
            if c in seen:
                continue
            seen.add(c)
            group.add(c)
            todo += [(c[0] + dx, c[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                     if (c[0] + dx, c[1] + dy) in urban]
        b = sum(built[c] for c in group)
        covers = sum(per_cell[c] for c in group)
        if b < DISTRICT_MIN or covers * 10000 / b >= SPARSE:
            continue
        xs, ys = [c[0] for c in group], [c[1] for c in group]
        mx = (sum(xs) / len(xs) + 0.5) * CELL
        my = (sum(ys) / len(ys) + 0.5) * CELL
        near = min(names, key=lambda n: (n[1] - mx) ** 2 + (n[2] - my) ** 2)
        out.append((near[0], (min(xs), min(ys), max(xs), max(ys)), group))
    return sorted(out, key=lambda d: -len(d[2]))


def all_manholes():
    out = []
    for cx, cy, h in pzmap.cells():
        if pzmap.MANHOLE.encode() in open(h, "rb").read():
            out += cell_facts(cx, cy)[2]
    return sorted(set(out))


def town_names():
    """Vanilla's town folders each list spawn points; their centre names a town."""
    names = []
    for f in glob.glob(os.path.join(MAPS, "*", "spawnpoints.lua")):
        town = os.path.basename(os.path.dirname(f)).split(",")[0]
        pts = [(int(a), int(b)) for a, b in
               re.findall(r"posX\s*=\s*(\d+),\s*posY\s*=\s*(\d+)", open(f, encoding="utf-8", errors="replace").read())]
        if pts:
            names.append((town, sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))
    # Louisville has no folder of its own; vanilla's regions.lua places it here.
    names.append(("Louisville", 13000, 2750))
    return names


def streets():
    """Vanilla's own street centre lines: [(name, width, [(x, y), ...])]."""
    out = []
    root = ET.parse(os.path.join(pzmap.MAP, "streets.xml")).getroot()
    for st in root.findall("street"):
        pts = [(float(q.get("x")), float(q.get("y"))) for q in st.find("points")]
        out.append((st.get("name") or "", float(st.get("width") or 6), pts))
    if len(out) < 500:
        raise SystemExit("only %d streets in streets.xml: the reader has stopped matching" % len(out))
    return out


def clusters(holes):
    parent = list(range(len(holes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, a in enumerate(holes):
        for j in range(i + 1, len(holes)):
            b = holes[j]
            if abs(a[0] - b[0]) <= LINK and abs(a[1] - b[1]) <= LINK:
                parent[find(i)] = find(j)
    groups = collections.defaultdict(list)
    for i, h in enumerate(holes):
        groups[find(i)].append(h)
    return sorted(groups.values(), key=lambda g: (min(h[0] for h in g), min(h[1] for h in g)))


def region(x0, y0, x1, y1):
    """road, keep for a world rectangle (inclusive), as [y, x] arrays."""
    w, h = x1 - x0 + 1, y1 - y0 + 1
    road = np.zeros((h, w), bool)
    keep = np.zeros((h, w), bool)
    for cx in range(x0 // CELL, x1 // CELL + 1):
        for cy in range(y0 // CELL, y1 // CELL + 1):
            r, k, _ = cell_facts(cx, cy)
            ax0, ay0 = max(x0, cx * CELL), max(y0, cy * CELL)
            ax1, ay1 = min(x1, cx * CELL + CELL - 1), min(y1, cy * CELL + CELL - 1)
            if ax0 > ax1 or ay0 > ay1:
                continue
            sl = (slice(ay0 - cy * CELL, ay1 - cy * CELL + 1), slice(ax0 - cx * CELL, ax1 - cx * CELL + 1))
            road[ay0 - y0:ay1 - y0 + 1, ax0 - x0:ax1 - x0 + 1] = r[sl]
            keep[ay0 - y0:ay1 - y0 + 1, ax0 - x0:ax1 - x0 + 1] = k[sl]
    return road, keep


# --- geometry --------------------------------------------------------------------------------

def h32(*v):
    return int(hashlib.md5(",".join(map(str, v)).encode()).hexdigest()[:8], 16)


def rasterise(pts, x0, y0, W, H):
    """The squares a polyline passes through, local coords."""
    out = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        n = max(1, int(max(abs(bx - ax), abs(by - ay)) * 2))
        for i in range(n + 1):
            x = int(ax + (bx - ax) * i / n) - x0
            y = int(ay + (by - ay) * i / n) - y0
            if 0 <= x < W and 0 <= y < H:
                out.append((x, y))
    return out


def four_connect(sk):
    """Adds an elbow to every diagonal step, so the line can be walked between walls."""
    out = sk.copy()
    H, W = sk.shape
    ys, xs = np.nonzero(sk)
    for x, y in zip(xs, ys):
        for dx, dy in ((1, 1), (1, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and sk[ny, nx] and not sk[y, nx] and not sk[ny, x]:
                out[y, nx] = True
    return out


def degree4(mask, x, y):
    H, W = mask.shape
    return sum(1 for dx, dy in N4 if 0 <= x + dx < W and 0 <= y + dy < H and mask[y + dy, x + dx])


def join_to(tunnel, keep, road, sx, sy, limit):
    """The cheapest 4-connected path from (sx, sy) to the tunnel, keeping under the
    road where it can (a square off the road costs three), or None."""
    H, W = tunnel.shape
    best = {(sx, sy): 0}
    prev = {(sx, sy): None}
    q = [(0, sx, sy)]
    while q:
        d, x, y = heapq.heappop(q)
        if d > best.get((x, y), 1e9):
            continue
        if tunnel[y, x]:
            path, cur = [], (x, y)
            while cur:
                path.append(cur)
                cur = prev[cur]
            return path
        if d >= limit * 3:
            continue
        for dx, dy in N4:
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and not keep[ny, nx]:
                nd = d + (1 if road[ny, nx] else 3)
                if nd < best.get((nx, ny), 1e9):
                    best[(nx, ny)] = nd
                    prev[(nx, ny)] = (x, y)
                    heapq.heappush(q, (nd, nx, ny))
    return None


def close_gaps(tunnel, keep, reach=6):
    """Joins every 1-wide dead end to tunnel within `reach` squares ahead of it.

    A dead end is a tunnel square with exactly one tunnel neighbour; ahead is
    away from that neighbour, and the two diagonals either side of it. The join
    is a 4-connected culvert (straight, or an L for a diagonal), never through
    a building. Returns how many were joined. Mutates `tunnel`.
    """
    H, W = tunnel.shape
    joined = 0
    ys, xs = np.nonzero(tunnel)
    for x, y in zip(xs.tolist(), ys.tolist()):
        nb = [(dx, dy) for dx, dy in N4 if 0 <= x + dx < W and 0 <= y + dy < H and tunnel[y + dy, x + dx]]
        if len(nb) != 1:
            continue
        fx, fy = -nb[0][0], -nb[0][1]
        side = (fy, fx) if fx == 0 else (fy, fx)
        best = None
        for k in range(2, reach + 1):
            for sdx, sdy in ((0, 0), (fy * 1, fx * 1), (-fy * 1, -fx * 1)):
                for lat in range(0, k):
                    tx = x + fx * k + sdx * lat
                    ty = y + fy * k + sdy * lat
                    if 0 <= tx < W and 0 <= ty < H and tunnel[ty, tx]:
                        best = (tx, ty)
                        break
                if best:
                    break
            if best:
                break
        if not best:
            continue
        tx, ty = best
        # Along the dead end's own direction first, then across: an L.
        path, cx, cy = [], x, y
        while (cx, cy) != (tx, ty):
            if fx and cx != tx:
                cx += 1 if tx > cx else -1
            elif fy and cy != ty:
                cy += 1 if ty > cy else -1
            elif cx != tx:
                cx += 1 if tx > cx else -1
            else:
                cy += 1 if ty > cy else -1
            path.append((cx, cy))
        if any(keep[py, px] for px, py in path):
            continue
        for px, py in path:
            tunnel[py, px] = True
        joined += 1
    return joined


def run_on_road(tunnel, keep, road, rooms_near, shafts, reach=ROAD_RUN):
    """Carries every 1-wide dead end straight on under painted road until it
    meets tunnel, within `reach` squares; never off the road, through a
    building, beside a shelter or beside a shaft (whose walls hold its ladder).
    Returns the squares added. Mutates `tunnel`.

    The street list has gaps the painted road does not: Harris St stops 49
    squares short of Irma Dr in Muldraugh, and its culvert ended in a wall
    under a road that carried on (found in play, 0.3.1). Run after the
    shelters are placed, because their placement is drawn from the tunnel's
    shape and must not move under a save.
    """
    H, W = tunnel.shape
    added = []
    by_shaft = set((sx + dx, sy + dy) for sx, sy in shafts for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    ys, xs = np.nonzero(tunnel)
    for x, y in zip(xs.tolist(), ys.tolist()):
        nb = [(dx, dy) for dx, dy in N4 if 0 <= x + dx < W and 0 <= y + dy < H and tunnel[y + dy, x + dx]]
        if len(nb) != 1 or (x, y) in by_shaft:
            continue
        fx, fy = -nb[0][0], -nb[0][1]
        path = []
        for k in range(1, reach + 1):
            px, py = x + fx * k, y + fy * k
            if (not (0 <= px < W and 0 <= py < H) or keep[py, px] or rooms_near[py, px]
                    or not road[py, px] or (px, py) in by_shaft):
                path = None
                break
            if tunnel[py, px]:
                break
            path.append((px, py))
        else:
            path = None
        if path:
            for px, py in path:
                tunnel[py, px] = True
            added += path
    return added


def reachable(walk, shafts):
    lab, _ = ndi.label(walk)
    good = {lab[y, x] for x, y in shafts if walk[y, x]}
    return np.isin(lab, list(good)) & walk


def bridge(tunnel, channel, shafts):
    """Turns channel into bridge until every walkable square can reach a ladder."""
    while True:
        walk = tunnel & ~channel
        stranded = walk & ~reachable(walk, shafts)
        if not stranded.any():
            return channel
        touch = ndi.binary_dilation(stranded) & channel
        if not touch.any():
            return np.zeros_like(channel)
        channel = channel & ~touch


# --- one town --------------------------------------------------------------------------------

def pick_covers(tid, x0, y0, sk, tunnel, keep):
    """Covers of our own for a district the map gives none: on the street's
    centre line, over clear painted road, at junctions first (COVER_GAP apart)
    and then along any run left with none for COVER_RUN squares. Local coords."""
    H, W = sk.shape
    clear = np.zeros((H, W), bool)
    for cx in range(x0 // CELL, (x0 + W - 1) // CELL + 1):
        for cy in range(y0 // CELL, (y0 + H - 1) // CELL + 1):
            c = clear_road(cx, cy)
            ax0, ay0 = max(x0, cx * CELL), max(y0, cy * CELL)
            ax1, ay1 = min(x0 + W - 1, cx * CELL + CELL - 1), min(y0 + H - 1, cy * CELL + CELL - 1)
            if ax0 <= ax1 and ay0 <= ay1:
                clear[ay0 - y0:ay1 - y0 + 1, ax0 - x0:ax1 - x0 + 1] = \
                    c[ay0 - cy * CELL:ay1 - cy * CELL + 1, ax0 - cx * CELL:ax1 - cx * CELL + 1]
    # On the tunnel's edge, within two squares of the street's centre: a shaft
    # needs a side with rock behind it for its ladder, and in a trunk the centre
    # line has none.
    edge = tunnel & ~ndi.binary_erosion(tunnel)
    ok = edge & ndi.binary_dilation(sk, iterations=2) & clear & ~keep
    # Not on the frame of the district: a shaft there has half a tunnel.
    ok[:3, :] = ok[-3:, :] = ok[:, :3] = ok[:, -3:] = False
    rng = random.Random(SEED * 31337 + h32("covers", tid))
    near_junction = np.zeros((H, W), bool)
    near_any = np.zeros((H, W), bool)
    out = []
    ys, xs = np.nonzero(ok)
    pts = list(zip(xs.tolist(), ys.tolist()))
    rng.shuffle(pts)
    jy, jx = np.nonzero(sk)
    jmask = np.zeros((H, W), bool)
    for x, y in zip(jx.tolist(), jy.tolist()):
        if degree4(sk, x, y) >= 3:
            jmask[y, x] = True
    jmask = ndi.binary_dilation(jmask, iterations=2)
    junctions = [(x, y) for x, y in pts if jmask[y, x]]
    for x, y in junctions:
        if not near_junction[y, x]:
            out.append((x, y))
            near_junction[max(0, y - COVER_GAP):y + COVER_GAP + 1, max(0, x - COVER_GAP):x + COVER_GAP + 1] = True
            near_any[max(0, y - COVER_RUN):y + COVER_RUN + 1, max(0, x - COVER_RUN):x + COVER_RUN + 1] = True
    for x, y in pts:
        if not near_any[y, x]:
            out.append((x, y))
            near_any[max(0, y - COVER_RUN):y + COVER_RUN + 1, max(0, x - COVER_RUN):x + COVER_RUN + 1] = True
    return sorted(out)


def lay_out(tid, holes, streets_all, district=None, forbid=frozenset()):
    """One town's tunnels. `holes` are its manholes (world coords); or, for a
    district the map gives few (`district`: (box of cells, set of cells)),
    none, and the covers are chosen here (pick_covers). `forbid` is chunks
    already another town's: never entered, so no chunk has two towns."""
    if district:
        (cx0, cy0, cx1, cy1), cells = district
        x0, y0, x1, y1 = cx0 * CELL, cy0 * CELL, cx1 * CELL + CELL - 1, cy1 * CELL + CELL - 1
    else:
        xs, ys = [h[0] for h in holes], [h[1] for h in holes]
        x0, y0 = min(xs) - MARGIN, min(ys) - MARGIN
        x1, y1 = max(xs) + MARGIN, max(ys) + MARGIN
    road, keep = region(x0, y0, x1, y1)
    H, W = road.shape
    rng = random.Random(SEED * 7919 + h32(tid))
    keep = ndi.binary_dilation(keep, iterations=KEEP_OUT)
    if district:
        # Only under the district's own cells, and every room counts, whichever
        # cell lists it (room_mask): nothing here is in a save to keep still.
        keep |= ndi.binary_dilation(room_mask(x0, y0, x1, y1), iterations=KEEP_OUT)
        inside = np.zeros((H, W), bool)
        for cx, cy in cells:
            inside[cy * CELL - y0:cy * CELL - y0 + CELL, cx * CELL - x0:cx * CELL - x0 + CELL] = True
        keep |= ~inside
    for kx, ky in forbid:
        lx, ly = kx * 8 - x0, ky * 8 - y0
        if -8 < lx < W and -8 < ly < H:
            keep[max(0, ly):ly + 8, max(0, lx):lx + 8] = True

    # Centre lines from the streets above, and how wide each tunnel is.
    sk = np.zeros((H, W), bool)
    rad = np.full((H, W), -1, int)
    names = {}
    kept = []
    for name, width, pts in streets_all:
        # By overlap, not by point: a highway can cross a whole town in one segment
        # whose ends are both outside it (Dixie Highway through Muldraugh).
        if (max(x for x, _ in pts) < x0 or min(x for x, _ in pts) > x1
                or max(y for _, y in pts) < y0 or min(y for _, y in pts) > y1):
            continue
        r = 2 if width >= TRUNK_W else 1 if width >= MAIN_W else 0
        kept.append((name, r, pts))
        for x, y in rasterise(pts, x0, y0, W, H):
            sk[y, x] = True
            rad[y, x] = max(rad[y, x], r)
            if name:
                names[(x, y)] = name
    # Snap loose ends. A side street in streets.xml ends at the *edge* of the
    # road it meets, not at that road's centre line, so its tunnel stopped a few
    # squares short of the trunk: a dead end beside the tunnel it was meant to
    # join (found in play, 0.3 -- "a dead end that says UP"). Each end is carried
    # on along its own direction until it meets another street's line, within
    # SNAP squares and never through a building.
    snapped = 0
    for name, r, pts in kept:
        own = set(rasterise(pts, x0, y0, W, H))
        for a, b in ((pts[-2], pts[-1]), (pts[1], pts[0])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            n = max(abs(dx), abs(dy))
            if n == 0:
                continue
            dx, dy = dx / n, dy / n
            path = []
            for k in range(1, SNAP + 1):
                px, py = int(b[0] + dx * k) - x0, int(b[1] + dy * k) - y0
                if not (0 <= px < W and 0 <= py < H) or keep[py, px]:
                    path = None
                    break
                if sk[py, px] and (px, py) not in own:
                    break
                path.append((px, py))
            else:
                path = None
            if path is not None:
                for px, py in path:
                    sk[py, px] = True
                    rad[py, px] = max(rad[py, px], r)
                snapped += 1
    t_snapped = snapped
    sk = four_connect(sk)
    rad[sk & (rad < 0)] = 0
    sk &= ~keep
    rad[~sk] = -1

    tunnel = np.zeros((H, W), bool)
    trunk = np.zeros((H, W), bool)
    for r in (0, 1, 2):
        m = rad == r
        if not m.any():
            continue
        grown = ndi.binary_dilation(m, structure=np.ones((2 * r + 1, 2 * r + 1), bool)) if r else m
        tunnel |= grown
        if r == 2:
            trunk |= grown
    tunnel &= ~keep

    if district:
        holes = [(x0 + x, y0 + y) for x, y in pick_covers(tid, x0, y0, sk, tunnel, keep)]

    # Shafts: the square under each manhole, joined to the network.
    shafts, dropped = [], []
    for hx, hy in holes:
        lx, ly = hx - x0, hy - y0
        if keep[ly, lx]:
            dropped.append((hx, hy))
            continue
        if not tunnel[ly, lx]:
            path = join_to(tunnel, keep, road, lx, ly, JOIN)
            if path is None:
                # Nothing near: a shaft to a small cellar of its own.
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if 0 <= lx + dx < W and 0 <= ly + dy < H and not keep[ly + dy, lx + dx]:
                            tunnel[ly + dy, lx + dx] = True
            else:
                for px, py in path:
                    tunnel[py, px] = True
        shafts.append((lx, ly))

    # Close what snapping could not: any 1-wide end with tunnel within a few
    # squares ahead of it (straight or diagonally) gets a short culvert across.
    closed = close_gaps(tunnel, keep)

    # Brick vaults at junctions of the wider tunnels.
    chamber = np.zeros((H, W), bool)
    junctions = [(int(x), int(y)) for y, x in zip(*np.nonzero(sk & (rad >= 1))) if degree4(sk, x, y) >= 3]
    rng.shuffle(junctions)
    placed = []
    for x, y in junctions:
        if all(abs(x - a) + abs(y - b) >= CHAMBER_GAP for a, b in placed):
            chamber[max(0, y - 3):y + 4, max(0, x - 3):x + 4] = True
            placed.append((x, y))
    chamber &= ~keep
    tunnel |= chamber

    # Only what a ladder can reach.
    tunnel = reachable(tunnel, shafts)
    chamber &= tunnel
    trunk &= tunnel

    # The channel: down the middle of the trunks, bridged often.
    shaft_zone = np.zeros((H, W), bool)
    for x, y in shafts:
        shaft_zone[max(0, y - 3):y + 4, max(0, x - 3):x + 4] = True
    # Bridges wherever a side tunnel meets a trunk: a culvert that came out onto
    # the sludge had the walkway in sight and out of reach (west_point, 0.3).
    side_joins = ndi.binary_dilation(tunnel & ~trunk, iterations=3)
    channel = (sk & (rad == 2) & tunnel & ~ndi.binary_dilation(chamber, iterations=2) & ~shaft_zone
               & ~side_joins)
    H_, W_ = sk.shape
    for y, x in zip(*np.nonzero(channel)):
        # Straight runs only. On a diagonal trunk the channel is a staircase that
        # cuts the walkways into pockets ending against the sludge (brandenburg,
        # west_point, 0.3); there the trunk is just a wide tunnel.
        ew = 0 < x < W_ - 1 and sk[y, x - 1] and sk[y, x + 1]
        ns = 0 < y < H_ - 1 and sk[y - 1, x] and sk[y + 1, x]
        if degree4(sk, x, y) != 2 or not (ew or ns) or (x + y) % 9 == 0:
            channel[y, x] = False
    # And no stub of channel shorter than a few squares: a lone sludge square is
    # a hole in the floor, not a channel.
    lab, n = ndi.label(channel)
    if n:
        sizes = ndi.sum(channel, lab, range(1, n + 1))
        channel &= np.isin(lab, [i + 1 for i, v in enumerate(sizes) if v >= 5])
    channel = bridge(tunnel, channel, shafts)

    rooms, room_id = shelters(tid, tunnel, keep, shafts, rng)

    # Dead ends under road that carries on: run them on to the network. After
    # the shelters, so none of them moves; the channel gives way where a new
    # culvert comes out, as it does for every side join.
    ran = run_on_road(tunnel, keep, road, ndi.binary_dilation(room_id > 0, iterations=2), shafts)
    if ran:
        near = np.zeros((H, W), bool)
        for px, py in ran:
            near[py, px] = True
        channel &= ~ndi.binary_dilation(near, iterations=3)

    # Caves, last of all and from a generator of their own: nothing above
    # moves for them, so a save's shelters, ladders and journals stay put.
    # Both plan against every room, whichever cell lists it (room_mask).
    keep_all = keep | ndi.binary_dilation(room_mask(x0, y0, x1, y1), iterations=KEEP_OUT)
    caves, cave_id = dig_caves(tid, tunnel, channel, keep_all, room_id, rooms, shafts)
    # Houses with a way down, after the caves and from a generator of their
    # own again: the culverts they add are new squares, nothing else moves.
    hatches = house_links(tid, x0, y0, tunnel, channel, keep_all, room_id, rooms, cave_id, caves, shafts)
    # The rats' nest, in one town only, last again: nothing above moves for it.
    lair, lair_id = None, np.zeros((H, W), int)
    if tid == LAIR_TOWN:
        if (x0, y0) != LAIR_ORIGIN:
            raise SystemExit("%s starts at %d,%d, not LAIR_ORIGIN %s" % (tid, x0, y0, LAIR_ORIGIN))
        lair, lair_id = dig_lair(tid, tunnel, channel, keep_all, room_id, rooms, cave_id, caves, hatches, shafts,
                                 chamber, trunk)
        if not lair:
            raise SystemExit("%s: no room for the rats' nest near %s" % (tid, LAIR_NEAR))
    if district:
        # A dead end that stops against the channel had the walkway across in
        # sight and out of reach (one in Louisville's grid, test_layout): the
        # channel gives way round it. Only here, so no older town moves.
        walk = tunnel & ~channel
        deg = sum(np.roll(walk, s, a) for s, a in ((1, 0), (-1, 0), (1, 1), (-1, 1)))
        dead = walk & (deg == 1) & ndi.binary_dilation(channel)
        channel &= ~ndi.binary_dilation(dead, iterations=3)

    # Storm-drain outfalls, after the nest and from a generator of their own:
    # culverts out to a creek, river or lake bank, each a new way in and out.
    # New squares only; nothing above moves.
    outfalls = dig_outfalls(tid, x0, y0, tunnel, channel, keep_all, room_id, rooms, cave_id, caves, hatches,
                            lair, lair_id, shafts)
    # Sewer gas, last of all and from a generator of its own: it adds no
    # square and moves nothing, it only says which squares are foul. Clear of
    # every ladder, the outfalls' too.
    gas = vent_gas(tid, tunnel, channel, chamber, room_id, rooms, cave_id, caves, hatches, lair,
                   list(shafts) + [o["bank"] for o in outfalls])

    # The warren: dens dug off the nest, last of all and from a generator of
    # its own. New squares only, and the nest's own stay where they are.
    warren = dig_warren(tid, lair, lair_id, tunnel, keep_all, room_id, cave_id) if lair else []

    # The street each shaft is under, for the note on the way down.
    street_of = {}
    if names:
        pts = np.array(list(names.keys()))
        for x, y in shafts:
            d = np.abs(pts[:, 0] - x) + np.abs(pts[:, 1] - y)
            i = int(d.argmin())
            if d[i] <= 20:
                street_of[(x, y)] = names[tuple(int(v) for v in pts[i])]

    return dict(snapped=t_snapped, x0=x0, y0=y0, W=W, H=H, road=road, keep=keep, tunnel=tunnel, chamber=chamber,
                trunk=trunk, channel=channel, sk=sk, shafts=shafts, dropped=dropped,
                rooms=rooms, room_id=room_id, junctions=placed, street_of=street_of,
                caves=caves, cave_id=cave_id, hatches=hatches, made=bool(district), tid=tid,
                lair=lair, lair_id=lair_id, gas=gas, outfalls=outfalls, warren=warren)


def dig_outfalls(tid, x0, y0, tunnel, channel, keep, room_id, rooms, cave_id, caves, hatches, lair, lair_id, shafts):
    """Storm-drain outfalls (ROADMAP 0.4; DESIGN.md 7c): a culvert from the
    network out to the bank of a creek, river or lake, ending under a grate
    in the bank with a ladder up to it -- a way in and out that no street
    cover shows. Mutates `tunnel` (the culverts join it).

    A bank is a dry square of natural ground and nothing else, beside a body
    of water of at least OUTFALL_WATER squares (not a swimming pool), clear of
    every building and of anything the map has below ground. The culvert is
    the shortest way from a bank to plain walkway, OUTFALL_MIN..OUTFALL_REACH
    squares, never under water, a building, a shelter, a cave, the nest or a
    hatch's culvert, and with a square of rock between it and every other
    space until it meets the tunnel end-on. Banks are taken shortest first,
    one per body of water before a second on any, OUTFALL_GAP apart, up to
    min(OUTFALL_MAX, 1 + shafts // 40). Returns [{bank, path, body}], local
    coords, the path from the bank to the square before the tunnel.
    """
    H, W = tunnel.shape
    water, ground = water_region(x0, y0, x0 + W - 1, y0 + H - 1)
    lab, n = ndi.label(water)
    if not n:
        return []
    sizes = ndi.sum(water, lab, range(1, n + 1))
    big = np.isin(lab, [i + 1 for i, v in enumerate(sizes) if v >= OUTFALL_WATER])
    if not big.any():
        return []
    under = ndi.binary_dilation(under_map(x0, y0, x0 + W - 1, y0 + H - 1), iterations=2)
    others = (room_id > 0) | (cave_id > 0) | (lair_id > 0)
    blocked = keep | water | under | ndi.binary_dilation(others, iterations=2)
    for h in hatches:
        for (x, y) in h["path"] + [h["hatch"]]:
            blocked[max(0, y - 2):y + 3, max(0, x - 2):x + 3] = True
    blocked[:3, :] = blocked[-3:, :] = blocked[:, :3] = blocked[:, -3:] = True
    # Met end-on on plain walkway: away from the channel, the ladders, the
    # shelters' doors, the caves' breaches and the nest's false wall.
    target = tunnel & ~ndi.binary_dilation(channel, iterations=3)
    marks = list(shafts) + [r["door"] for r in rooms] + [r["inside"] for r in rooms] + [c["breach"] for c in caves]
    if lair:
        marks.append(lair["entry"])
    for (x, y) in marks:
        target[max(0, y - 3):y + 4, max(0, x - 3):x + 4] = False
    near_tunnel = ndi.binary_dilation(tunnel) & ~tunnel
    # Breadth first, out from every square that touches exactly one target
    # square and no other tunnel (the culvert's last square), through rock
    # that touches no tunnel at all.
    dist = np.full((H, W), -1, int)
    prev = {}
    q = collections.deque()
    ys, xs = np.nonzero(near_tunnel & ~blocked)
    for x, y in sorted(zip(xs.tolist(), ys.tolist())):
        touch = [(x + dx, y + dy) for dx, dy in N4 if tunnel[y + dy, x + dx]]
        if len(touch) == 1 and target[touch[0][1], touch[0][0]]:
            dist[y, x] = 1
            prev[(x, y)] = None
            q.append((x, y))
    ok = ~blocked & ~tunnel & ~near_tunnel
    while q:
        x, y = q.popleft()
        if dist[y, x] >= OUTFALL_REACH:
            continue
        for dx, dy in N4:
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and ok[ny, nx] and dist[ny, nx] < 0:
                dist[ny, nx] = dist[y, x] + 1
                prev[(nx, ny)] = (x, y)
                q.append((nx, ny))
    bank = ground & ~blocked & ndi.binary_dilation(big) & (dist >= OUTFALL_MIN)
    ys, xs = np.nonzero(bank)
    if not len(xs):
        return []
    rng = random.Random(SEED * 3571 + h32("outfalls", tid))
    cands = []
    for x, y in zip(xs.tolist(), ys.tolist()):
        body = max(int(lab[y + dy, x + dx]) for dx, dy in N4)
        cands.append((int(dist[y, x]), rng.random(), x, y, body))
    cands.sort()
    want = min(OUTFALL_MAX, 1 + len(shafts) // 40)
    out, bodies = [], set()
    for second in (False, True):
        for d, _r, x, y, body in cands:
            if len(out) >= want:
                break
            if (body in bodies) != second:
                continue
            if any(abs(x - o["bank"][0]) + abs(y - o["bank"][1]) < OUTFALL_GAP for o in out):
                continue
            path, cur = [], (x, y)
            while cur:
                path.append(cur)
                cur = prev[cur]
            # Two culverts must not touch either.
            if any(abs(px - qx) + abs(py - qy) <= 2 for o in out for qx, qy in o["path"] for px, py in path):
                continue
            out.append(dict(bank=(x, y), path=path, body=body, length=d))
            bodies.add(body)
    for o in out:
        for x, y in o["path"]:
            tunnel[y, x] = True
    return out


def vent_gas(tid, tunnel, channel, chamber, room_id, rooms, cave_id, caves, hatches, lair, shafts):
    """Stretches of sewer gas (ROADMAP 0.5): foul air lying in the narrow
    culverts, away from the ladders, where nothing moves it on.

    Each is a run of 1-wide walkway grown out from a seed a square at a time,
    GAS_MIN..GAS_MAX squares, kept GAS_CLEAR squares from every street ladder
    (a player who climbs down never lands in it, and the way out is always
    clean air), off every shelter, cave, hatch culvert and the rats' nest.
    Returns [{id, squares: [(x, y)], signs: [(x, y, edge-less spot outside,
    entrance square inside)]}], local coords; `encode` hangs the county's
    placard on a wall at each way in and lays the haze.
    """
    H, W = tunnel.shape
    rng = random.Random(SEED * 7727 + h32("gas", tid))
    walk = tunnel & ~channel & ~chamber
    # 1-wide: in no 2x2 block of walkway. (Not "one square from the rock":
    # that is every edge square of a wide tunnel too -- the first try laid gas
    # down the side of a main, with a way in at every square.)
    block = walk[:-1, :-1] & walk[1:, :-1] & walk[:-1, 1:] & walk[1:, 1:]
    in_block = np.zeros((H, W), bool)
    in_block[:-1, :-1] |= block
    in_block[1:, :-1] |= block
    in_block[:-1, 1:] |= block
    in_block[1:, 1:] |= block
    narrow = walk & ~in_block
    # Where a player can stand, vaults included: the ways in are counted on it.
    stand = tunnel & ~channel
    near_ladder = np.zeros((H, W), bool)
    for x, y in shafts:
        near_ladder[max(0, y - GAS_CLEAR):y + GAS_CLEAR + 1, max(0, x - GAS_CLEAR):x + GAS_CLEAR + 1] = True
    avoid = near_ladder | ndi.binary_dilation((room_id > 0) | (cave_id > 0), iterations=3)
    for r in rooms:
        (x, y) = r["door"]
        avoid[max(0, y - 3):y + 4, max(0, x - 3):x + 4] = True
    for c in caves:
        (x, y) = c["breach"]
        avoid[max(0, y - 3):y + 4, max(0, x - 3):x + 4] = True
    for h in hatches:
        for (x, y) in h["path"] + [h["hatch"]]:
            avoid[max(0, y - 2):y + 3, max(0, x - 2):x + 3] = True
    if lair:
        (x, y) = lair["entry"]
        avoid[max(0, y - 6):y + 7, max(0, x - 6):x + 7] = True
    ok = narrow & ~avoid
    want = round(len(shafts) / GAS_PER_SHAFTS)
    ys, xs = np.nonzero(ok)
    seeds = sorted(zip(xs.tolist(), ys.tolist()))
    rng.shuffle(seeds)
    taken = np.zeros((H, W), bool)
    out = []
    for sx, sy in seeds:
        if len(out) >= want:
            break
        if taken[sy, sx] or any(abs(sx - g["seed"][0]) + abs(sy - g["seed"][1]) < GAS_GAP for g in out):
            continue
        size = rng.randint(GAS_MIN, GAS_MAX)
        region, frontier, seen = [], [(sx, sy)], {(sx, sy)}
        while frontier and len(region) < size:
            x, y = frontier.pop(0)
            region.append((x, y))
            nbrs = [(x + dx, y + dy) for dx, dy in N4]
            rng.shuffle(nbrs)
            for nx, ny in nbrs:
                if (nx, ny) not in seen and 0 <= nx < W and 0 <= ny < H and ok[ny, nx] and not taken[ny, nx]:
                    seen.add((nx, ny))
                    frontier.append((nx, ny))
        if len(region) < GAS_MIN:
            continue
        mine = set(region)
        # The ways in: a walkway square outside, beside a square of the gas.
        signs = sorted({(x + dx, y + dy, x, y) for x, y in region for dx, dy in N4
                        if (x + dx, y + dy) not in mine and 0 <= x + dx < W and 0 <= y + dy < H
                        and stand[y + dy, x + dx]})
        for x, y in region:
            taken[y, x] = True
        out.append(dict(id=len(out) + 1, seed=(sx, sy), squares=sorted(region), signs=signs))
    return out


def house_links(tid, x0, y0, tunnel, channel, keep, room_id, rooms, cave_id, caves, shafts):
    """Hatches in the floors of some houses near the network (ROADMAP 0.4),
    each a ladder down to a culvert that runs out from under the house to the
    tunnel. Mutates `tunnel` (the culverts join it).

    Tunnels never go under a building, because B42 stamps random basements
    under buildings when a world is made. These few squares do, on purpose;
    so the server checks them in game and opens the hatch only if nothing is
    there (SEW_Server, surface pass). Returns [{hatch: (x, y), under: [squares
    under the house or its margin], path: [...]}], local coords.
    """
    H, W = tunnel.shape
    rng = random.Random(SEED * 15485863 + h32("hatches", tid))
    want = max(1, round(len(shafts) / HATCH_PER_SHAFTS))
    # The network is met on plain walkway: not the channel or near it (a
    # culvert that came out onto sludge), not a shaft's walls (its ladder), not
    # a shelter's door, not a cave's breach.
    target = tunnel & ~ndi.binary_dilation(channel, iterations=3)
    for (x, y) in list(shafts) + [r["door"] for r in rooms] + [r["inside"] for r in rooms] + \
            [c["breach"] for c in caves]:
        target[max(0, y - 3):y + 4, max(0, x - 3):x + 4] = False
    if not target.any():
        return []
    dist = ndi.distance_transform_cdt(~target, metric="taxicab")
    blocked = (room_id > 0) | ndi.binary_dilation(cave_id > 0, iterations=2)
    for (x, y) in shafts:
        blocked[max(0, y - 2):y + 3, max(0, x - 2):x + 3] = True
    lab, _ = ndi.label(keep)
    # A house the map already gives a basement is left alone, and no culvert
    # passes within a square of anything the map has below ground.
    under = under_map(x0, y0, x0 + W - 1, y0 + H - 1)
    blocked |= ndi.binary_dilation(under)
    has_basement = set(np.unique(lab[under & (lab > 0)]).tolist())
    clear = {}
    cands = []
    for name, rects in hatch_rooms(x0, y0, x0 + W - 1, y0 + H - 1):
        best = None
        for rx, ry, rw, rh in rects:
            for wy in range(ry, ry + rh):
                for wx in range(rx, rx + rw):
                    lx, ly = wx - x0, wy - y0
                    if not (1 <= lx < W - 1 and 1 <= ly < H - 1) or tunnel[ly, lx] or blocked[ly, lx]:
                        continue
                    if lab[ly, lx] in has_basement:
                        continue
                    ck = (wx // CELL, wy // CELL)
                    if ck not in clear:
                        clear[ck] = clear_floor(*ck)
                    if not clear[ck][wy % CELL, wx % CELL]:
                        continue
                    d = int(dist[ly, lx])
                    if d <= HATCH_REACH and (best is None or d < best[0]):
                        best = (d, lx, ly)
        if best:
            cands.append((name,) + best)
    cands.sort(key=lambda c: (c[1], c[2], c[3]))
    rng.shuffle(cands)
    out = []
    for name, _d, hx, hy in cands:
        if len(out) >= want:
            break
        if any(abs(hx - o["hatch"][0]) + abs(hy - o["hatch"][1]) < HATCH_GAP for o in out):
            continue
        home = lab[hy, hx]
        # Cheapest way to the network: out from under this house as soon as it
        # can (a square under it costs four), never under another building.
        best = {(hx, hy): 0}
        prev = {(hx, hy): None}
        q = [(0, hx, hy)]
        end = None
        while q:
            d, x, y = heapq.heappop(q)
            if d > best.get((x, y), 1e9):
                continue
            if target[y, x] and (x, y) != (hx, hy):
                end = (x, y)
                break
            if d > HATCH_REACH * 4:
                continue
            for dx, dy in N4:
                nx, ny = x + dx, y + dy
                if not (1 <= nx < W - 1 and 1 <= ny < H - 1) or blocked[ny, nx]:
                    continue
                if tunnel[ny, nx] and not target[ny, nx]:
                    continue
                if keep[ny, nx] and lab[ny, nx] != home:
                    continue
                nd = d + (4 if keep[ny, nx] else 1)
                if nd < best.get((nx, ny), 1e9):
                    best[(nx, ny)] = nd
                    prev[(nx, ny)] = (x, y)
                    heapq.heappush(q, (nd, nx, ny))
        if not end:
            continue
        path, cur = [], prev[end]
        while cur:
            path.append(cur)
            cur = prev[cur]
        path.reverse()                                   # hatch first, the tunnel's square excluded
        under = [p for p in path if keep[p[1], p[0]]]
        # Only into the tunnel at its end: a culvert running alongside it would
        # open its wall all the way (and onto whatever hangs there).
        side = [p for p in path[:-1] if any(tunnel[p[1] + dy, p[0] + dx] for dx, dy in N4)]
        if len(path) > HATCH_REACH or len(under) > HATCH_UNDER or side:
            continue
        for x, y in path:
            tunnel[y, x] = True
        out.append(dict(hatch=(hx, hy), under=under, path=path, room=name))
    return out


def dig_caves(tid, tunnel, channel, keep, room_id, rooms, shafts):
    """Broken walls into dug-out caves (ROADMAP 0.4): somebody broke through a
    tunnel wall and dug. A winding dirt passage from the breach, maybe a short
    side branch, and a hideout at the end.

    Returns (caves, cave_id): cave_id is 0 outside a cave, else its number;
    each cave is {id, breach: tunnel square, entry: the first cave square,
    hideout: [squares], centre, mouth: the hideout square the passage enters}.
    A cave keeps a square of rock between itself and any other space, except
    where it breaks through, so it meets the sewer only at its breach.
    """
    H, W = tunnel.shape
    rng = random.Random(SEED * 104729 + h32("caves", tid))
    space = tunnel | (room_id > 0)
    cave_id = np.zeros((H, W), int)
    near_space = ndi.binary_dilation(space, structure=np.ones((5, 5), bool))
    want = max(1, round(len(shafts) / CAVE_PER_SHAFTS))
    avoid = [(x, y) for x, y in shafts] + [r["door"] for r in rooms] + [r["inside"] for r in rooms]
    walk = tunnel & ~channel
    cand = []
    for y, x in zip(*np.nonzero(walk)):
        x, y = int(x), int(y)
        if any(abs(x - a) + abs(y - b) <= CAVE_CLEAR for a, b in avoid):
            continue
        for dx, dy in N4:
            ox, oy = x + dx, y + dy
            if 3 <= ox < W - 3 and 3 <= oy < H - 3 and not space[oy, ox] and not keep[oy, ox]:
                cand.append((x, y, dx, dy))
    rng.shuffle(cand)
    caves = []

    def free(x, y, early):
        if not (2 <= x < W - 2 and 2 <= y < H - 2) or keep[y, x] or space[y, x] or cave_id[y, x]:
            return False
        if early:
            return True
        # A square of rock from the sewer and from every other cave.
        if near_space[y, x]:
            return False
        others = cave_id[max(0, y - 2):y + 3, max(0, x - 2):x + 3]
        return not ((others > 0) & (others != len(caves) + 1)).any()

    for bx, by, dx, dy in cand:
        if len(caves) >= want:
            break
        if any(abs(bx - c["breach"][0]) + abs(by - c["breach"][1]) < CAVE_GAP for c in caves):
            continue
        k = len(caves) + 1
        dug = []
        # Straight out through the wall for three squares, the lateral squares
        # rock, then winding.
        x, y, ok = bx, by, True
        for step in range(3):
            x, y = x + dx, y + dy
            lat = [(x + dy, y + dx), (x - dy, y - dx)]
            if not free(x, y, True) or any(space[ly, lx] for lx, ly in lat if 0 <= lx < W and 0 <= ly < H):
                ok = False
                break
            if step == 2 and not free(x, y, False):
                ok = False
                break
            dug.append((x, y))
        if not ok:
            continue
        for p in dug:
            cave_id[p[1], p[0]] = k
        length = rng.randint(18, 40)
        hx, hy = dx, dy
        branch_at = rng.randint(6, 14) if rng.random() < 0.5 else -1
        path = list(dug)
        for step in range(length):
            if rng.random() < 0.3:
                hx, hy = rng.choice([(hy, hx), (-hy, -hx)])     # a turn, left or right
            moved = False
            for tx, ty in ((hx, hy), (hy, hx), (-hy, -hx)):
                nx, ny = x + tx, y + ty
                if free(nx, ny, False):
                    x, y, hx, hy, moved = nx, ny, tx, ty, True
                    break
            if not moved:
                break
            cave_id[y, x] = k
            path.append((x, y))
            # Dug by hand: a square wider here and there.
            if rng.random() < 0.35:
                sx, sy = rng.choice([(hy, hx), (-hy, -hx)])
                if free(x + sx, y + sy, False):
                    cave_id[y + sy, x + sx] = k
            if step == branch_at:
                bhx, bhy = rng.choice([(hy, hx), (-hy, -hx)])
                cx_, cy_ = x, y
                for _ in range(rng.randint(5, 10)):
                    nx, ny = cx_ + bhx, cy_ + bhy
                    if not free(nx, ny, False):
                        break
                    cx_, cy_ = nx, ny
                    cave_id[cy_, cx_] = k
                    if rng.random() < 0.3:
                        bhx, bhy = rng.choice([(bhy, bhx), (-bhy, -bhx), (bhx, bhy)])
        # The hideout: a rough chamber grown out from the end of the passage,
        # a square at a time, so it stays in one piece.
        rx, ry = rng.randint(2, 3), rng.randint(2, 3)
        ex, ey = x, y
        hide = []
        frontier = [(ex, ey)]
        seen = {(ex, ey)}
        while frontier:
            px, py = frontier.pop(0)
            for tx, ty in N4:
                nx, ny = px + tx, py + ty
                if (nx, ny) in seen:
                    continue
                seen.add((nx, ny))
                d = ((nx - ex) / (rx + 0.5)) ** 2 + ((ny - ey) / (ry + 0.5)) ** 2
                if d <= 1.0 + (h32("hide", tid, nx, ny) % 100) / 400 and free(nx, ny, False):
                    cave_id[ny, nx] = k
                    hide.append((nx, ny))
                    frontier.append((nx, ny))
        if len(path) < 14 or len(hide) < 10:
            cave_id[cave_id == k] = 0
            continue
        hide.append((ex, ey))
        caves.append(dict(id=k, breach=(bx, by), entry=dug[0], hideout=sorted(hide), centre=(ex, ey),
                          mouth=path[-2] if len(path) > 1 else (ex, ey)))
    return caves, cave_id


def dig_lair(tid, tunnel, channel, keep, room_id, rooms, cave_id, caves, hatches, shafts, chamber, trunk):
    """The rats' nest under Louisville (ROADMAP 0.5): one per world, hidden.

    A plain tunnel wall that is not a wall -- loose brickwork with a gnawed
    hole at its foot, pulled away by hand (a false wall, `x` concrete / `y`
    brick) -- then a winding rat run through the rock, a great round nest of
    bones and litter where the rodents of unusual size live, and at the far
    side of it a bricked-up room, older than the sewer, holding a hoard. Its
    one way in from the nest is a wall they have gnawed half through (`z`),
    and it gives only once the last of them is dead (SEW_Server.pry).

    Made last, from a generator of its own, so nothing else in the town moves.
    Returns (lair, lair_id): lair_id 1 on the run and the nest, 2 in the
    hoard; lair is {entry: tunnel square, first: the run's first square,
    centre, gate: (nest square, hoard square), hoard: rect, rous: [squares],
    furniture spots...}, local coords, or (None, zeros) if nothing fits.
    """
    H, W = tunnel.shape
    lair_id = np.zeros((H, W), int)
    space = tunnel | (room_id > 0) | (cave_id > 0)
    margin2 = keep | ndi.binary_dilation(space, structure=np.ones((5, 5), bool))
    clear = ndi.distance_transform_edt(~margin2)
    # Where the run may come off the sewer: plain walkway, away from ladders,
    # doors, breaches, hatches and the channel.
    target = tunnel & ~ndi.binary_dilation(channel, iterations=2)
    for (x, y) in list(shafts) + [r["door"] for r in rooms] + [r["inside"] for r in rooms] + \
            [c["breach"] for c in caves] + [h["hatch"] for h in hatches] + \
            [h["path"][-1] for h in hatches if h["path"]]:
        target[max(0, y - 4):y + 5, max(0, x - 4):x + 5] = False
    # Never off a hatch's culvert: part of it is under a house the game may
    # have given a basement, and all of it is somebody's way home.
    for h in hatches:
        for (x, y) in h["path"] + [h["hatch"]]:
            target[max(0, y - 2):y + 3, max(0, x - 2):x + 3] = False
    if not target.any():
        return None, lair_id
    to_target = ndi.distance_transform_edt(~target)
    ox, oy = LAIR_NEAR[0] - LAIR_ORIGIN[0], LAIR_NEAR[1] - LAIR_ORIGIN[1]
    ys, xs = np.nonzero((clear >= LAIR_CLEAR) & (to_target >= 18) & (to_target <= 34))
    if not len(xs):
        return None, lair_id
    # Near a house with a way down (the dev build starts a character there),
    # and of those, nearest LAIR_NEAR.
    hs = [h["hatch"] for h in hatches] or [(ox, oy)]
    near_h = np.min([np.hypot(xs - hx, ys - hy) for hx, hy in hs], axis=0)
    k = int(np.argmin(near_h + 0.05 * np.hypot(xs - ox, ys - oy)))
    cx, cy = int(xs[k]), int(ys[k])

    # The hoard lies on the far side of the nest from the sewer.
    ty, tx = np.unravel_index(np.argmin(np.where(target, (np.indices((H, W))[1] - cx) ** 2
                                                  + (np.indices((H, W))[0] - cy) ** 2, 1 << 30)), (H, W))
    vx, vy = cx - int(tx), cy - int(ty)
    # And north or west of it: from inside a square only its north and west
    # walls face the camera, so the gnawed wall's claw marks are seen only
    # from the nest square south or east of it (found in play, 0.5: both
    # walls were on the south, their pictures on the far side of them).
    d = (-1, 0) if -vx >= -vy else (0, -1)
    R = LAIR_NEST_R
    for y in range(cy - R - 1, cy + R + 2):
        for x in range(cx - R - 1, cx + R + 2):
            wob = (h32("nest", tid, x, y) % 100) / 160.0
            if ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 <= R + 0.3 - wob:
                lair_id[y, x] = 1
    # The row (or column) through the centre runs out to R, so the gate is
    # where the nest meets the hoard's wall square-on.
    gx, gy = cx + d[0] * R, cy + d[1] * R
    for s in range(R + 1):
        lair_id[cy + d[1] * s, cx + d[0] * s] = 1
    hw, hd = 7, 5                                   # across the gate, and deep
    if d[0]:
        rx = gx + 1 if d[0] > 0 else gx - hd
        ry, rw, rh = gy - hw // 2, hd, hw
    else:
        ry = gy + 1 if d[1] > 0 else gy - hd
        rx, rw, rh = gx - hw // 2, hw, hd
    # Where the nest presses against the hoard elsewhere, the old room's brick
    # stands between them (encode walls any edge between the two).
    lair_id[ry:ry + rh, rx:rx + rw] = 2
    hoard_ring = ndi.binary_dilation(lair_id == 2, structure=np.ones((5, 5), bool))

    # The run: from the sewer wall to the nest, a square of rock either side,
    # winding (a noisy cost), never along the hoard.
    near1 = ndi.binary_dilation(space, structure=np.ones((3, 3), bool))
    nest = lair_id == 1
    ok = ~keep & ~near1 & ~hoard_ring & ~nest
    starts = []
    for y, x in zip(*np.nonzero(target)):
        x, y = int(x), int(y)
        # Through the tunnel square's own north or west wall only: the one
        # whose face, cracks and all, is seen from the sewer (as the gate).
        for dx, dy in ((0, -1), (-1, 0)):
            ex, ey = x + dx, y + dy
            if not (2 <= ex < W - 2 and 2 <= ey < H - 2) or space[ey, ex] or keep[ey, ex] or lair_id[ey, ex]:
                continue
            # The square through the wall touches the sewer at the hole only.
            if any(space[ey + a, ex + b] for b, a in N4 if (ex + b, ey + a) != (x, y)):
                continue
            if space[ey + dx, ex + dy] or space[ey - dx, ex - dy]:
                continue
            starts.append((x, y, ex, ey))
    if not starts:
        return None, lair_id
    best, prev, q = {}, {}, []
    for x, y, ex, ey in starts:
        best[(ex, ey)] = 0
        prev[(ex, ey)] = ("sewer", x, y)
        heapq.heappush(q, (0, ex, ey))
    end = None
    while q:
        dd, x, y = heapq.heappop(q)
        if dd > best.get((x, y), 1e9):
            continue
        if any(nest[y + b, x + a] for a, b in N4):
            end = (x, y)
            break
        for a, b in N4:
            nx, ny = x + a, y + b
            if not (2 <= nx < W - 2 and 2 <= ny < H - 2) or not ok[ny, nx]:
                continue
            nd = dd + 1 + (h32("run", tid, nx, ny) % 7) / 3.0
            if nd < best.get((nx, ny), 1e9):
                best[(nx, ny)] = nd
                prev[(nx, ny)] = (x, y)
                heapq.heappush(q, (nd, nx, ny))
    if not end:
        return None, lair_id
    run, cur = [], end
    while not (isinstance(prev[cur], tuple) and prev[cur][0] == "sewer"):
        run.append(cur)
        cur = prev[cur]
    run.append(cur)
    entry = (prev[cur][1], prev[cur][2])
    run.reverse()                                        # the first square through the wall first
    if len(run) < 10:
        return None, lair_id
    for x, y in run:
        lair_id[y, x] = 1

    # The nest's own: the rodents where they sleep, round the middle; bones
    # and litter everywhere else (encode); the hoard's crates round its walls.
    rng = random.Random(SEED * 31337 + h32("lair", tid))
    nest_sq = sorted((int(x), int(y)) for y, x in zip(*np.nonzero(lair_id == 1))
                     if ((int(x) - cx) ** 2 + (int(y) - cy) ** 2) <= (R - 1) ** 2)
    rng.shuffle(nest_sq)
    rous = []
    for p in nest_sq:
        if len(rous) >= LAIR_ROUS:
            break
        if all(abs(p[0] - r[0]) + abs(p[1] - r[1]) >= 3 for r in rous):
            rous.append(p)
    return dict(entry=entry, first=run[0], run=run, centre=(cx, cy), gate=((gx, gy), (gx + d[0], gy + d[1])),
                hoard=(rx, ry, rw, rh), facing=d, rous=rous, trunk=bool(trunk[entry[1], entry[0]]
                                                                          or chamber[entry[1], entry[0]])), lair_id


def dig_warren(tid, lair, lair_id, tunnel, keep, room_id, cave_id):
    """The warren (ROADMAP 0.6): the nest was one round of earth; it is a few
    now. Dens dug off it and off one another, each at the end of a short run
    through the rock, where the rats dragged what they took and where those
    who came looking for them ended up.

    Made after everything else in its town, from a generator of its own, and
    only ever added to the nest: every square here is new, and the one record
    of the old nest that changes is the earth wall a run leaves by. The dens
    are nest to the code (`lair_id` 1, floor `n`): no wall between them and
    it, and no way to them but through it -- so the false wall is still the
    only way in (tests/test_layout.py). Mutates `lair_id`. Returns
    [{centre, r, cells: [squares], mouth: the den square its run enters by}],
    in the order they were dug, local coords.
    """
    import math
    H, W = tunnel.shape
    rng = random.Random(SEED * 2741 + h32("warren", tid))
    hoard = lair_id == 2
    other = tunnel | (room_id > 0) | (cave_id > 0) | hoard
    shut = keep | ndi.binary_dilation(other, structure=np.ones((5, 5), bool))
    # The run in from the false wall stays a run: nothing opens off it.
    run = np.zeros((H, W), bool)
    for x, y in lair["run"]:
        run[y, x] = True
    shut |= ndi.binary_dilation(run, structure=np.ones((7, 7), bool))
    cx, cy = lair["centre"]
    nest = [(int(x), int(y)) for y, x in zip(*np.nonzero((lair_id == 1) & ~run))]
    owner = np.zeros((H, W), int)                   # 1 the nest, 2.. the dens
    for x, y in nest:
        owner[y, x] = 1
    anchors = [dict(id=1, centre=(cx, cy), r=LAIR_NEST_R)]
    dens = []
    for _try in range(4000):
        if len(dens) >= WARREN_DENS:
            break
        # Off the nest first, then off whichever den is newest as often as not:
        # a chain with a branch, not a star.
        base = anchors[-1] if (len(anchors) > 1 and rng.random() < 0.6) else rng.choice(anchors)
        ang = rng.uniform(0, 2 * math.pi)
        r = rng.randint(*WARREN_R)
        reach = base["r"] + rng.randint(*WARREN_RUN) + r
        nx, ny = int(round(base["centre"][0] + reach * math.cos(ang))), int(round(base["centre"][1] + reach * math.sin(ang)))
        if not (r + 4 <= nx < W - r - 4 and r + 4 <= ny < H - r - 4):
            continue
        k = len(dens) + 2
        cells = set()
        for y in range(ny - r - 1, ny + r + 2):
            for x in range(nx - r - 1, nx + r + 2):
                wob = (h32("den", tid, x, y) % 100) / 180.0
                if ((x - nx) ** 2 + (y - ny) ** 2) ** 0.5 <= r + 0.3 - wob:
                    cells.add((x, y))
        cells.add((nx, ny))
        # Its run: from the base's middle to this one's, a step at a time, the
        # long way first so it bends once.
        line, (x, y) = [], base["centre"]
        horizontal = abs(nx - x) >= abs(ny - y)
        while (x, y) != (nx, ny):
            if (horizontal and x != nx) or y == ny:
                x += 1 if nx > x else -1
            else:
                y += 1 if ny > y else -1
            line.append((x, y))
        path = [c for c in line if owner[c[1], c[0]] != base["id"] and c not in cells]
        if len(path) < 2 or any(owner[y, x] for x, y in path) or any(owner[y, x] for x, y in cells):
            continue
        new = cells | set(path)
        if any(shut[y, x] for x, y in new):
            continue
        # Rock all round: nothing dug within two squares of a den, and nothing
        # but the two things it joins beside its run.
        ok = True
        for x, y in cells:
            if (owner[y - 2:y + 3, x - 2:x + 3] > 0).any():
                ok = False
                break
        for x, y in path if ok else ():
            near = owner[y - 1:y + 2, x - 1:x + 2]
            if ((near > 0) & (near != base["id"])).any():
                ok = False
                break
        if not ok:
            continue
        for x, y in new:
            owner[y, x] = k
            lair_id[y, x] = 1
        mouth = next(c for c in reversed(line) if c in cells and any((c[0] + a, c[1] + b) in path for a, b in N4))
        dens.append(dict(id=k, centre=(nx, ny), r=r, cells=sorted(cells), mouth=mouth))
        anchors.append(dict(id=k, centre=(nx, ny), r=r))
    if len(dens) < WARREN_MIN:
        raise SystemExit("%s: only %d dens fit round the rats' nest" % (tid, len(dens)))
    return dens


# What is in each den, in the order they are dug: (pieces, the dead, relics).
# A piece is (sprite kind, loot list, the writing left in it or None); the
# writings are filled in by gen_temple.cross once the temple is sited.
WARREN = [
    # The larder: what they dragged down.
    dict(pieces=[("crate_wood", "hoardFood", None), ("crate_wood", "food", None)], dead=[], relics=["bones"]),
    # Where the cult's pilgrims got to: what they carried, and what is left of them.
    # (m1: an annotated map of the way back to the temple, SEW_Maps.)
    dict(pieces=[("crate_metal", "cultRelics", "warren_1"), ("crate_wood", "cultRobes", "m1"),
                 ("crate_wood", "cultOfferings", None)],
         dead=["Cultist", "Cultist"], relics=["offering", "candles", "candles", "offering", "sigil", "burrow"]),
    # A county flood crew, with their tools: the first to find it, and the last log they wrote.
    dict(pieces=[("crate_metal", "hoardTools", "warren_3"), ("crate_metal", "tools", None),
                 ("crate_wood", "hardware", None)],
         dead=["Sanitation", "Sanitation"], relics=["bones"]),
    # The deepest: what glitters, and a map on a hymn sheet.
    dict(pieces=[("crate_metal", "hoardValuables", "warren_2"), ("crate_metal", "hoardMedical", None),
                 ("crate_wood", "hoardSurvival", None)],
         dead=["Cultist"], relics=["offering", "candles", "sigil"]),
]


def furnish_warren(t):
    """What is in the dens: ([(x, y, sprite, loot, slot)], [(x, y, outfit)],
    [(x, y, sprite)] pictures, [(x, y)] lights), world coords. Crates against
    the earth, away from the den's mouth; the dead in the open; relics --
    offerings, candles, the cult's marks on the earth -- wherever is left."""
    x0, y0 = t["x0"], t["y0"]
    out, dead, pictures, lights = [], [], [], []
    for den, plan in zip(t["warren"], WARREN):
        cells = set(den["cells"])
        mx, my = den["mouth"]
        used = {(mx, my)} | {(mx + a, my + b) for a, b in N4}

        def rock(p, a, b):
            return (p[0] + a, p[1] + b) not in cells and (p[0] + a, p[1] + b) not in used

        # Against the north earth, front to the south, furthest from the mouth first.
        north = sorted((p for p in cells if rock(p, 0, -1) and p not in used),
                       key=lambda p: (-(abs(p[0] - mx) + abs(p[1] - my)), p))
        for kind, loot, slot in plan["pieces"]:
            spot = next((p for p in north if p not in used and all(abs(p[0] - u[0]) + abs(p[1] - u[1]) > 1
                                                                 for u in used - {(mx, my)})), None)
            if spot is None:
                raise SystemExit("the warren: no room for a %s in den %d" % (kind, den["id"]))
            out.append((x0 + spot[0], y0 + spot[1], SPRITES[kind]["S"], loot, slot))
            used.add(spot)
        free = sorted(p for p in cells if p not in used)
        rng = random.Random(SEED * 97 + h32("warren-in", den["id"]))
        rng.shuffle(free)
        for outfit in plan["dead"]:
            p = next(q for q in free if q not in used)
            dead.append((x0 + p[0], y0 + p[1], outfit))
            used.add(p)
        for what in plan["relics"]:
            if what in ("sigil", "burrow"):
                # On the earth: a den square with rock north (or west) of it and nothing in front.
                spot = next(((p, "N") for p in free if p not in used and rock(p, 0, -1)), None) or \
                    next(((p, "W") for p in free if p not in used and rock(p, -1, 0)), None)
                if spot:
                    pictures.append((x0 + spot[0][0], y0 + spot[0][1], gen_temple.OURS[what][spot[1]]))
                    used.add(spot[0])
                continue
            p = next(q for q in free if q not in used)
            out.append((x0 + p[0], y0 + p[1], gen_temple.OURS[what], None, None))
            used.add(p)
            if what == "candles":
                lights.append((x0 + p[0], y0 + p[1]))
    return out, dead, pictures, lights


def shelters(tid, tunnel, keep, shafts, rng):
    H, W = tunnel.shape
    want = max(1, round(len(shafts) / 5))
    taken = np.zeros_like(tunnel)
    room_id = np.zeros(tunnel.shape, int)
    edge = tunnel & ~ndi.binary_erosion(tunnel)
    ys, xs = np.nonzero(edge)
    cand = list(zip(xs.tolist(), ys.tolist()))
    rng.shuffle(cand)
    rooms = []
    for x, y in cand:
        if len(rooms) >= want:
            break
        if any(abs(x - r["door"][0]) + abs(y - r["door"][1]) < SHELTER_GAP for r in rooms):
            continue
        for dx, dy in rng.sample(N4, 4):
            ox, oy = x + dx, y + dy
            if not (0 <= ox < W and 0 <= oy < H) or tunnel[oy, ox]:
                continue
            w, h = rng.randint(5, 8), rng.randint(4, 6)
            if dx:
                rx = ox if dx > 0 else ox - w + 1
                ry = oy - rng.randint(1, h - 2)
            else:
                ry = oy if dy > 0 else oy - h + 1
                rx = ox - rng.randint(1, w - 2)
            if rx < 1 or ry < 1 or rx + w >= W - 1 or ry + h >= H - 1:
                continue
            box = (slice(ry, ry + h), slice(rx, rx + w))
            if tunnel[box].any() or keep[box].any() or taken[ry - 1:ry + h + 1, rx - 1:rx + w + 1].any():
                continue
            k = len(rooms) + 1
            taken[box] = True
            room_id[box] = k
            rooms.append(dict(id=k, rect=(rx, ry, w, h), door=(x, y), inside=(ox, oy),
                              kind=KINDS[h32(tid, k) % len(KINDS)]))
            break
    return rooms, room_id


# --- locked gates ----------------------------------------------------------------------------

COUNTY = ("maintenance", "pump")


def gate_shelters(tid, rooms):
    """The county rooms behind a locked grille (ROADMAP 0.5; DESIGN.md 7, Locked gates): in a
    town with at least two maintenance rooms and pump stations, half of them
    (at least one), chosen by a generator of its own. A town with one keeps
    it open: the key has to be somewhere a player can reach. Returns the
    set of room ids. Squats and last stands never: nobody locked those."""
    county = [r["id"] for r in rooms if r["kind"] in COUNTY]
    if len(county) < 2:
        return set()
    rng = random.Random(SEED * 6007 + h32("gates", tid))
    rng.shuffle(county)
    return set(county[:max(1, len(county) // 2)])


def gate_key(tid):
    """The town's key id: above anything vanilla hands out (Rand.Next(100000000)
    for a building's or a car's key), stable per town."""
    return GATE_KEY_BASE + h32("key", tid) % 90000000


def key_spots(t, furniture):
    """[(x, y)] world coords: the first stocked container of every unlocked
    county room, in a town with gates -- where the town's key is left."""
    if not t.get("gated"):
        return []
    x0, y0 = t["x0"], t["y0"]
    out = []
    for r in t["rooms"]:
        if r["kind"] not in COUNTY or r["id"] in t["gated"]:
            continue
        rx, ry, w, h = r["rect"]
        for fx, fy, _spr, loot, _extra in furniture:
            if loot and x0 + rx <= fx < x0 + rx + w and y0 + ry <= fy < y0 + ry + h:
                out.append((fx, fy))
                break
    return out


# --- squares ---------------------------------------------------------------------------------
#
# Legend (SEW_Data.lua decodes it):
#   floor    . none  t tunnel  k vault  s shelter  g grating  w channel (sludge, not walkable)  r rock (outside, under a wall)
#            m cave (dug earth)  n the rats' nest  v their hoard
#            p a passage the cult dug  h the temple's stone floor  a its carpet  q its boards (gen_temple.py)
#   walls    . none  c concrete  b brick  d a door frame, with its steel door  e earth (a cave's)
#            j a door frame, with a locked grille (a county room: gate_shelters)
#            o a breach, broken through concrete  q a breach, broken through brick (both walked through)
#            O Q the same, broken through from the cult's side (gen_temple.py)
#   fixture  . none  L ladder on the N edge  l ladder on the W edge  P pillar (concrete)  Q pillar (brick)
#   dressing . none  p pipe  e EXIT stencil  a-g graffiti  h SAFE stencil  i grime  u puddle  v debris  x light pool  y smear
#            z loose stones (rubble)

GRAFFITI = "abcdefg"


def encode(t):
    """({(cx, cy): {(x, y): record}}, ladders) for every square the town touches, world coords."""
    x0, y0, W, H = t["x0"], t["y0"], t["W"], t["H"]
    tunnel, chamber, trunk, channel, room_id = t["tunnel"], t["chamber"], t["trunk"], t["channel"], t["room_id"]
    cave_id = t["cave_id"]
    lair_id = t.get("lair_id")
    if lair_id is None:
        lair_id = np.zeros_like(cave_id)
    lair = t.get("lair")
    space = tunnel | (room_id > 0) | (cave_id > 0) | (lair_id > 0)
    group = np.where(tunnel, -1, np.where(cave_id > 0, -100 - cave_id, np.where(lair_id > 0, -1000 - lair_id, room_id)))
    sq = {}

    def rec(x, y):
        key = (x, y)
        if key not in sq:
            sq[key] = [str(x % 8), str(y % 8), ".", ".", ".", ".", "."]
        return sq[key]

    for y, x in zip(*np.nonzero(space)):
        r = rec(x0 + x, y0 + y)
        r[2] = ("s" if room_id[y, x] else "m" if cave_id[y, x] else "n" if lair_id[y, x] == 1
                else "v" if lair_id[y, x] == 2 else "w" if channel[y, x] else "k" if chamber[y, x] else "t")

    # Walls, on the N or W edge of the square south or east of each boundary.
    pad = lambda a, v: np.pad(a, 1, constant_values=v)  # noqa: E731
    sp, gp, br = pad(space, False), pad(group, 0), pad(chamber | trunk, False)
    cv = pad(cave_id > 0, False)
    doors = {}
    for rm in t["rooms"]:
        (tx, ty), (ix, iy) = rm["door"], rm["inside"]
        doors[(tx, max(ty, iy), "N") if tx == ix else (max(tx, ix), ty, "W")] = rm
    breaches = {}
    for c in t["caves"]:
        (tx, ty), (ix, iy) = c["breach"], c["entry"]
        breaches[(tx, max(ty, iy), "N") if tx == ix else (max(tx, ix), ty, "W")] = "q" if br[ty + 1, tx + 1] else "o"
    # The rats' nest: the false wall into it from the sewer (x concrete, y
    # brick, as the tunnel's own wall there), and the gnawed wall between the
    # nest and the hoard (z).
    gates = {}
    if lair:
        for (tx, ty), (ix, iy), code in ((lair["entry"], lair["first"], "y" if lair["trunk"] else "x"),
                                         (lair["gate"][0], lair["gate"][1], "z")):
            gates[(tx, max(ty, iy), "N") if tx == ix else (max(tx, ix), ty, "W")] = code
    nest, hoard = pad(lair_id == 1, False), pad(lair_id == 2, False)
    for edge, (dx, dy), col in (("N", (0, -1), 3), ("W", (-1, 0), 4)):
        # Every (x, y) in 0..W x 0..H against its neighbour across the edge; the
        # padding makes x = -1 and y = -1 read as outside.
        for y in range(0, H + 1):
            row_h = sp[y + 1, 1:W + 2]
            row_a = sp[y + 1 + dy, 1 + dx:W + 2 + dx]
            g_h = gp[y + 1, 1:W + 2]
            g_a = gp[y + 1 + dy, 1 + dx:W + 2 + dx]
            wall = (row_h != row_a) | (row_h & row_a & (g_h != g_a))
            for x in np.nonzero(wall)[0]:
                x = int(x)
                r = rec(x0 + x, y0 + y)
                if (x, y, edge) in doors:
                    # A county room behind a locked grille (gate_shelters): j.
                    r[col] = "j" if doors[(x, y, edge)]["id"] in t.get("gated", ()) else "d"
                elif (x, y, edge) in breaches:
                    r[col] = breaches[(x, y, edge)]
                elif (x, y, edge) in gates:
                    r[col] = gates[(x, y, edge)]
                elif hoard[y + 1, x + 1] or hoard[y + 1 + dy, x + 1 + dx]:
                    r[col] = "b"
                elif cv[y + 1, x + 1] or cv[y + 1 + dy, x + 1 + dx] or nest[y + 1, x + 1] or nest[y + 1 + dy, x + 1 + dx]:
                    r[col] = "e"
                else:
                    brick = br[y + 1, x + 1] or br[y + 1 + dy, x + 1 + dx]
                    r[col] = "b" if brick else "c"
                if not (x < W and y < H and space[y, x]) and r[2] == ".":
                    r[2] = "r"

    # Pillars where a north wall and a west wall end at the same corner from the north-west.
    for (wx, wy), r in list(sq.items()):
        if r[3] not in "cbdjxyz":
            continue
        px, py = wx + 1, wy
        north = sq.get((px, py - 1))
        here = sq.get((px, py))
        if north and north[4] in "cbdjxyz" and not (here and (here[3] != "." or here[4] != ".")):
            if r[5] == ".":
                r[5] = "Q" if (r[3] in "byz" or north[4] in "byz") else "P"

    # Ladders, one per shaft, on a wall of (or beside) the square under the cover.
    def hang(sx, sy, light):
        wx, wy = x0 + sx, y0 + sy
        here = rec(wx, wy)
        here[2] = "g"
        if light:
            here[6] = "x"
        lx, ly = wx, wy
        if here[3] in "cb" and here[5] == ".":
            here[5], edge = "L", "N"
        elif here[4] in "cb" and here[5] == ".":
            here[5], edge = "l", "W"
        else:
            east, south = sq.get((wx + 1, wy)), sq.get((wx, wy + 1))
            if east and east[4] in "cb" and east[5] == ".":
                east[5], edge, lx = "l", "W", wx + 1
            elif south and south[3] in "cb" and south[5] == ".":
                south[5], edge, ly = "L", "N", wy + 1
            elif t.get("made"):
                # No wall to hang it on: build one, but only on a side with rock
                # behind it. The old fallback walled the north edge whatever was
                # there, and at a cover of ours on a junction that cut off the
                # street running north (131 squares stranded in Louisville).
                # Vanilla's covers keep the old fallback, so their towns do not move.
                def open_(x, y):
                    return 0 <= x < W and 0 <= y < H and bool(space[y, x])
                if not open_(sx, sy - 1):
                    here[3], here[5], edge = "c", "L", "N"
                elif not open_(sx - 1, sy):
                    here[4], here[5], edge = "c", "l", "W"
                elif not open_(sx + 1, sy):
                    east = rec(wx + 1, wy)
                    east[4], east[5], edge, lx = "c", "l", "W", wx + 1
                    if east[2] == ".":
                        east[2] = "r"
                elif not open_(sx, sy + 1):
                    south = rec(wx, wy + 1)
                    south[3], south[5], edge, ly = "c", "L", "N", wy + 1
                    if south[2] == ".":
                        south[2] = "r"
                else:
                    # Open all round (a vault was laid over it after the cover
                    # was chosen): a wall on one edge cuts nothing off here.
                    here[3], here[5], edge = "c", "L", "N"
            else:
                here[3], here[5], edge = "c", "L", "N"
        return wx, wy, lx, ly, edge

    ladders = [hang(sx, sy, True) + (t["street_of"].get((sx, sy), ""),) for sx, sy in t["shafts"]]
    # A hatch's ladder: the same, but no daylight through a wooden hatch.
    t["hatch_ladders"] = [hang(h["hatch"][0], h["hatch"][1], False) + (h,) for h in t["hatches"]]
    # An outfall's ladder: daylight through its grate, like a cover's.
    t["outfall_ladders"] = [hang(o["bank"][0], o["bank"][1], True) + (o,) for o in t.get("outfalls", [])]

    # Dressing, deterministic by position.
    near_shaft = set()
    for sx, sy in t["shafts"]:
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                near_shaft.add((x0 + sx + dx, y0 + sy + dy))
    shaft_pts = [(x0 + sx, y0 + sy) for sx, sy in t["shafts"]]

    def near_ladder(x, y, reach=12):
        return any(abs(x - a) + abs(y - b) <= reach for a, b in shaft_pts)

    hideouts = set((x0 + x, y0 + y) for c in t["caves"] for x, y in c["hideout"])
    for (wx, wy), r in sq.items():
        if r[6] != "." or r[5] != ".":
            continue
        roll = h32("dress", wx, wy) % 1000
        walled = r[3] in "cb" or r[4] in "cb"
        if r[2] == "m":
            # Dug earth: stones that came down, bones, standing water. The
            # hideout is kept clear for its furniture.
            if (wx, wy) in hideouts:
                continue
            if roll < 110:
                r[6] = "z"
            elif roll < 140:
                r[6] = "v"
            elif roll < 170:
                r[6] = "u"
        elif walled and r[2] in "tk":
            if (wx, wy) in near_shaft and roll < 450:
                r[6] = "e"
            elif roll < 60:
                r[6] = "p"
            elif roll < 100:
                g = GRAFFITI[h32("g", wx, wy) % len(GRAFFITI)]
                # "UP" is a promise: only where a ladder really is close. Anywhere
                # else it pointed at nothing, once at a dead end (found in play, 0.3).
                if g == "f" and not near_ladder(wx, wy):
                    g = "a"
                r[6] = g
            elif roll < 320:
                r[6] = "i"
        elif r[2] in "tk" and not walled:
            if roll < 45:
                r[6] = "u"
            elif roll < 70:
                r[6] = "v"
            elif roll < 78:
                r[6] = "y"
    for rm in t["rooms"]:
        tx, ty = rm["door"]
        for dx, dy in N4:
            s = sq.get((x0 + tx + dx, y0 + ty + dy))
            if s and s[2] in "tk" and (s[3] in "cb" or s[4] in "cb") and s[5] == ".":
                s[6] = "h"
                break
    # What came out of the wall lies either side of the hole.
    for c in t["caves"]:
        for px, py in (c["breach"], c["entry"]):
            s = sq.get((x0 + px, y0 + py))
            if s and s[5] == ".":
                s[6] = "z"
    # The rats' nest: bones and litter over its floor (never under where they
    # sleep), claw marks on its walls, and the only signs in the sewer that
    # anything is there -- the gnawed hole at the foot of the false wall, and
    # somebody's warning a few squares along.
    if lair:
        rous = set((x0 + x, y0 + y) for x, y in lair["rous"])
        for (wx, wy), r in sq.items():
            if r[2] != "n" or (wx, wy) in rous or r[5] != ".":
                continue
            roll = h32("nest", wx, wy) % 1000
            walled = r[3] == "e" or r[4] == "e"
            if walled and roll < 260:
                r[6] = "l"
            elif roll < 180:
                r[6] = "j"
            elif roll < 330:
                r[6] = "k"
            elif roll < 380:
                r[6] = "z"
            else:
                r[6] = "."
        for (tx, ty), (ix, iy), code in ((lair["entry"], lair["first"], "n"), (lair["gate"][0], lair["gate"][1], "l")):
            s = sq[(x0 + tx, y0 + max(ty, iy))] if tx == ix else sq[(x0 + max(tx, ix), y0 + ty)]
            s[6] = code
        # The warning: on a tunnel wall 2-6 squares from the false wall.
        ex, ey = x0 + lair["entry"][0], y0 + lair["entry"][1]
        spots = sorted(((abs(wx - ex) + abs(wy - ey), wx, wy) for (wx, wy), r in sq.items()
                        if r[2] in "tk" and (r[3] in "cb" or r[4] in "cb") and r[5] == "."
                        and 2 <= abs(wx - ex) + abs(wy - ey) <= 6))
        if spots:
            sq[(spots[0][1], spots[0][2])][6] = "o"

    by_chunk = collections.defaultdict(dict)
    for (wx, wy), r in sq.items():
        by_chunk[(wx // 8, wy // 8)][(wx, wy)] = "".join(r)
    return by_chunk, ladders


FURNITURE = {
    "maintenance": [("crate_metal", "tools"), ("shelves", "hardware"), ("crate_metal", "tools")],
    "pump": [("crate_metal", "mechanic"), ("shelves", "hardware"), ("crate_wood", "fuel")],
    "squat": [("bag", None), ("crate_wood", "food"), ("shelves", "survival")],
    "laststand": [("crate_metal", "arms"), ("crate_wood", "food"), ("bag", None), ("shelves", "medical")],
}
# By which way the front faces. Checked against tools/_catalog/tiles.json (Facing).
SPRITES = {
    "crate_metal": {"S": "constructedobjects_01_46", "E": "constructedobjects_01_47",
                    "N": "constructedobjects_01_44", "W": "constructedobjects_01_45"},
    "crate_wood": {f: "carpentry_01_16" for f in "SENW"},
    "shelves": {"S": "carpentry_02_64", "E": "carpentry_02_65", "N": "carpentry_02_67", "W": "carpentry_02_66"},
    # Two squares each: (first, second, dx, dy) -- SpriteGridPos 0,0 then 1,0 (or 0,1).
    "bag": {"S": ("camping_02_4", "camping_02_5", 1, 0), "N": ("camping_02_0", "camping_02_1", 1, 0),
            "E": ("camping_02_3", "camping_02_2", 0, 1), "W": ("camping_02_7", "camping_02_6", 0, 1)},
}


def furnish(t, extras=None):
    """[(x, y, sprite, loot|None, extra|None)] and [(x, y, outfit)] for the claimed,
    world coords. `extra` ("j3;p1": journal 3, plan 1) goes in the room's first
    stocked container."""
    x0, y0 = t["x0"], t["y0"]
    out, dead = [], []
    extras = extras or {}
    for r in t["rooms"]:
        extra = extras.get(r["id"])
        rx, ry, w, h = r["rect"]
        ix, iy = r["inside"]
        used = {(ix, iy)}
        walls = {"S": [(x, ry) for x in range(rx, rx + w)],
                 "N": [(x, ry + h - 1) for x in range(rx, rx + w)],
                 "E": [(rx, y) for y in range(ry, ry + h)],
                 "W": [(rx + w - 1, y) for y in range(ry, ry + h)]}
        # Nothing on the squares either side of the way in, or the door is blocked.
        for dx, dy in N4:
            used.add((ix + dx, iy + dy))
        order = sorted(walls, key=lambda f: -min(abs(px - ix) + abs(py - iy) for px, py in walls[f]))
        pending = list(FURNITURE[r["kind"]])
        for facing in order:
            spots = [p for p in walls[facing] if p not in used]
            while pending and spots:
                piece, loot = pending[0]
                if piece == "bag":
                    a, b, dx, dy = SPRITES["bag"][facing]
                    pair = next(((px, py) for px, py in spots if (px + dx, py + dy) in spots), None)
                    if not pair:
                        break
                    px, py = pair
                    out.append((x0 + px, y0 + py, a, None, None))
                    out.append((x0 + px + dx, y0 + py + dy, b, None, None))
                    used |= {(px, py), (px + dx, py + dy)}
                else:
                    px, py = spots[len(spots) // 2]
                    out.append((x0 + px, y0 + py, SPRITES[piece][facing], loot, extra if loot else None))
                    if loot:
                        extra = None
                    used.add((px, py))
                pending.pop(0)
                spots = [p for p in spots if p not in used and min(abs(p[0] - u[0]) + abs(p[1] - u[1]) for u in used) > 1]
        n = {"laststand": 2, "squat": 1}.get(r["kind"], h32("claim", r["id"], rx) % 2)
        free = [(x, y) for x in range(rx, rx + w) for y in range(ry, ry + h) if (x, y) not in used]
        for j in range(min(n, len(free))):
            x, y = free[h32("z", rx, ry, j) % len(free)]
            dead.append((x0 + x, y0 + y, ("Survivalist", "Hobbo", "Bandit")[h32("o", x, y) % 3]))
    return out, dead


def furnish_caves(t):
    """The hideouts' furniture and their dead, world coords, kept apart from the
    shelters' (SEW_Build furnishes a cave the first time its chunk is visited
    with caves in it, even a chunk built before caves existed).

    A bedroll, a crate of food, a crate of whatever kept them going; against
    the earth walls, off the square the passage comes in by."""
    x0, y0 = t["x0"], t["y0"]
    out, dead = [], []
    cave_id = t["cave_id"]
    H, W = cave_id.shape
    for c in t["caves"]:
        hide = set(c["hideout"])
        ex, ey = c["centre"]
        mx, my = c["mouth"]
        # The way in stays clear: the square the passage enters by and those round it.
        used = {(ex, ey), (mx, my)} | {(ex + dx, ey + dy) for dx, dy in N4}

        def walled(p):
            return any(not (0 <= p[0] + dx < W and 0 <= p[1] + dy < H) or cave_id[p[1] + dy, p[0] + dx] != c["id"]
                       for dx, dy in N4)
        spots = sorted((p for p in hide if p not in used and walled(p)),
                       key=lambda p: (-(abs(p[0] - mx) + abs(p[1] - my)), p))
        bag = next(((px, py) for px, py in spots if (px + 1, py) in spots), None)
        if bag:
            a, b, _dx, _dy = SPRITES["bag"]["S"]
            out.append((x0 + bag[0], y0 + bag[1], a, None, None))
            out.append((x0 + bag[0] + 1, y0 + bag[1], b, None, None))
            used |= {bag, (bag[0] + 1, bag[1])}
        for loot in ("food", "survival"):
            free = [p for p in spots if p not in used and all(abs(p[0] - u[0]) + abs(p[1] - u[1]) > 1 for u in used)]
            if not free:
                break
            px, py = free[0]
            out.append((x0 + px, y0 + py, SPRITES["crate_wood"]["S"], loot, None))
            used.add((px, py))
        if h32("cave-claim", t["x0"], c["id"]) % 2 == 0:
            rest = sorted(p for p in hide if p not in used)
            if rest:
                x, y = rest[h32("cz", x0, y0, c["id"]) % len(rest)]
                dead.append((x0 + x, y0 + y, ("Hobbo", "Survivalist", "Grunge")[h32("co", x, y) % 3]))
    return out, dead


LAIR_HOARD = [("crate_metal", "hoardArms"), ("crate_metal", "hoardAmmo"), ("shelves", "hoardMedical"),
              ("crate_metal", "hoardTools"), ("crate_wood", "hoardFood"), ("shelves", "hoardSurvival"),
              ("crate_metal", "hoardValuables"), ("crate_wood", "hoardFood")]


def furnish_lair(t):
    """The hoard's crates and shelves round the walls of its room, world coords,
    with the caves' (SEW_Build furnishes them the first time the chunk is
    built with its caves), and the way in from the gate kept clear."""
    lair = t.get("lair")
    if not lair:
        return []
    x0, y0 = t["x0"], t["y0"]
    rx, ry, w, h = lair["hoard"]
    ix, iy = lair["gate"][1]
    used = {(ix, iy)} | {(ix + dx, iy + dy) for dx, dy in N4}
    walls = {"S": [(x, ry) for x in range(rx, rx + w)],
             "N": [(x, ry + h - 1) for x in range(rx, rx + w)],
             "E": [(rx, y) for y in range(ry, ry + h)],
             "W": [(rx + w - 1, y) for y in range(ry, ry + h)]}
    out = []
    pending = list(LAIR_HOARD)
    order = sorted(walls, key=lambda f: -min(abs(px - ix) + abs(py - iy) for px, py in walls[f]))
    for facing in order:
        for px, py in walls[facing]:
            if not pending:
                break
            if (px, py) in used:
                continue
            piece, loot = pending.pop(0)
            out.append((x0 + px, y0 + py, SPRITES[piece][facing], loot, None))
            used.add((px, py))
    return out


def lair_access(t, ladders):
    """The hatch and the street cover nearest the false wall by walking the
    tunnels, for the index (the dev build starts a character by that hatch)."""
    lair = t["lair"]
    walk = t["tunnel"] & ~t["channel"]
    H, W = walk.shape
    sx, sy = lair["entry"]
    dist = {(sx, sy): 0}
    q = collections.deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        for dx, dy in N4:
            n = (x + dx, y + dy)
            if 0 <= n[0] < W and 0 <= n[1] < H and walk[n[1], n[0]] and n not in dist:
                dist[n] = dist[(x, y)] + 1
                q.append(n)
    x0, y0 = t["x0"], t["y0"]
    hatch = min(((dist[h["hatch"]], h["hatch"]) for h in t["hatches"] if h["hatch"] in dist), default=None)
    cover = min(((dist[(a - x0, b - y0)], (a - x0, b - y0)) for a, b, *_ in ladders if (a - x0, b - y0) in dist),
                default=None)
    if not hatch or not cover:
        raise SystemExit("the rats' nest is walked to from no hatch or no cover")
    return hatch, cover


# --- the story: journals and plans ------------------------------------------------------------
#
# ROADMAP: story told through the map. Every shelter holds one journal, and
# every journal points at somewhere else worth finding -- reading it puts a
# mark on the reader's sewer map (SEW_Discovery.mark), with the street and the
# direction written into the text. Maintenance rooms and pump stations also
# hold a Municipal Sewer Plan: one sheet (a 256-square tile of the map) of the
# town, a different sheet from the one the room is on where there is one, so a
# plan always shows you somewhere you have not been.
#
# The texts are keyed by what they point at (IGUI_SEW_J_<kind>_<n>_Title /
# _Body in IG_UI.json); `JOURNAL_VARIANTS` must match how many each kind has.

JOURNAL_VARIANTS = {"maintenance": 2, "pump": 2, "squat": 2, "laststand": 2, "shaft": 2}
COMPASS = ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"]


def compass(fx, fy, tx, ty):
    import math
    a = math.atan2(ty - fy, tx - fx)
    return COMPASS[int(round(a / (math.pi / 4))) % 8]


def story(tid, t, ladders, journals, plans):
    """Assigns a journal (and maybe a plan) to each shelter. Appends to the global
    journals / plans lists and returns {room id: "j<n>;p<m>"} for furnish()."""
    x0, y0 = t["x0"], t["y0"]
    streets = [(sx, sy, st) for sx, sy, _lx, _ly, _e, st in ladders if st]

    def street_near(x, y):
        if not streets:
            return ""
        return min(streets, key=lambda s: abs(s[0] - x) + abs(s[1] - y))[2]

    pois = []
    for r in t["rooms"]:
        rx, ry, w, h = r["rect"]
        pois.append(("room", r["id"], x0 + rx + w // 2, y0 + ry + h // 2, r["kind"]))
    extras = {}
    # Sheets worth finding: a plan of a corner with four chunks of culvert on it
    # was the first thing the exact-count test turned up. Only sheets with at
    # least a fifth as much tunnel as the town's busiest sheet are drawn up.
    ys, xs = np.nonzero(t["tunnel"])
    per_sheet = collections.Counter((int(x) // MAP_TILE, int(y) // MAP_TILE) for x, y in zip(xs, ys))
    busiest = max(per_sheet.values()) if per_sheet else 0
    tiles_with_tunnel = sorted(k for k, n in per_sheet.items() if n >= max(200, busiest // 5))
    for r in t["rooms"]:
        rx, ry, w, h = r["rect"]
        here = (x0 + rx + w // 2, y0 + ry + h // 2)
        others = [p for p in pois if p[1] != r["id"]]
        if others:
            # The nearest other place, so the chain leads on through the town.
            target = min(others, key=lambda p: abs(p[2] - here[0]) + abs(p[3] - here[1]))
            kind, tx, ty = target[4], target[2], target[3]
        else:
            far = max(ladders, key=lambda s: abs(s[0] - here[0]) + abs(s[1] - here[1]))
            kind, tx, ty = "shaft", far[0], far[1]
        variant = h32("jv", tid, r["id"]) % JOURNAL_VARIANTS[kind] + 1
        journals.append(dict(town=tid, x=tx, y=ty, kind=kind, text="%s_%d" % (kind, variant),
                             street=street_near(tx, ty), dir=compass(here[0], here[1], tx, ty)))
        codes = ["j%d" % len(journals)]
        if r["kind"] in ("maintenance", "pump") and tiles_with_tunnel:
            mine = ((here[0] - x0) // MAP_TILE, (here[1] - y0) // MAP_TILE)
            choice = [s for s in tiles_with_tunnel if s != mine] or tiles_with_tunnel
            i, j = choice[h32("plan", tid, r["id"]) % len(choice)]
            plans.append(dict(town=tid, i=int(i), j=int(j)))
            codes.append("p%d" % len(plans))
        extras[r["id"]] = ";".join(codes)
    return extras


# --- sewer gas, written ----------------------------------------------------------------------

GAS_IDS = "123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def place_gas(t, chunks):
    """({(cx, cy): "xyi..."}, {(cx, cy): [(x, y, edge)]}) -- world coords.

    The gas's squares, three characters each: x and y in the chunk and the
    stretch's id in GAS_IDS. And the county's placard at each way in: on a
    wall of ours on the north or west edge of the walkway square just outside
    (seen as you come up to it), or failing that of the first square inside;
    a way in with no such wall gets none. One placard per way in."""
    x0, y0 = t["x0"], t["y0"]
    sq = {}
    for rows in chunks.values():
        sq.update(rows)
    gas_rows = collections.defaultdict(list)
    signs = collections.defaultdict(list)
    if len(t["gas"]) >= len(GAS_IDS):
        raise SystemExit("%s: %d gas stretches, more than GAS_IDS can name" % (t["tid"], len(t["gas"])))
    for g in t["gas"]:
        code = GAS_IDS[g["id"] - 1]
        for x, y in g["squares"]:
            wx, wy = x0 + x, y0 + y
            gas_rows[(wx // 8, wy // 8)].append("%d%d%s" % (wx % 8, wy % 8, code))
        for ox, oy, ix, iy in g["signs"]:
            for (px, py) in ((ox, oy), (ix, iy)):
                r = sq.get((x0 + px, y0 + py))
                edge = "N" if r and r[3] in "cb" else "W" if r and r[4] in "cb" else None
                if edge:
                    wx, wy = x0 + px, y0 + py
                    signs[(wx // 8, wy // 8)].append((wx, wy, edge))
                    break
    return {k: "".join(v) for k, v in gas_rows.items()}, signs


# --- writing ---------------------------------------------------------------------------------

def lua_str(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_town(tid, name, chunks, furniture, dead, cave_furniture=(), cave_dead=(), gas=None, keys=(), pictures=(),
               warren=((), ())):
    os.makedirs(DATA, exist_ok=True)

    def furn(items):
        out = collections.defaultdict(list)
        for x, y, spr, loot, extra in items:
            out[(x // 8, y // 8)].append("{%d,%d,%s,%s,%s}" % (x, y, lua_str(spr), lua_str(loot) if loot else "nil",
                                                              lua_str(extra) if extra else "nil"))
        return out

    def zeds(items):
        out = collections.defaultdict(list)
        for x, y, outfit, *face in items:
            # `face`: the square one of the temple's dead is turned to (gen_temple.py).
            out[(x // 8, y // 8)].append("{%d,%d,%s%s}" % (x, y, lua_str(outfit), "".join(",%d" % v for v in face)))
        return out
    fx, zx, vx, ux = furn(furniture), zeds(dead), furn(cave_furniture), zeds(cave_dead)
    # The warren (dig_warren): what is in its dens and who, placed once in a
    # chunk whatever that chunk's history -- a save that has the nest gets them.
    wx, dx = furn(warren[0]), zeds(warren[1])
    lines = [
        "-- GENERATED by tools/gen_sewers.py -- do not edit. %s: the squares, by chunk." % name,
        "if isClient() then return end",
        "SEW = SEW or {}",
        "SEW.Data = SEW.Data or {}",
        "local T = { id = %s, name = %s, chunks = {}, furniture = {}, claimed = {}, caveFurniture = {}, "
        "caveClaimed = {}, gas = {}, gasSigns = {}, keys = {}, pictures = {}, warren = {}, warrenDead = {} }"
        % (lua_str(tid), lua_str(name)),
        "SEW.Data[%s] = T" % lua_str(tid),
        "local c, f, z, v, u = T.chunks, T.furniture, T.claimed, T.caveFurniture, T.caveClaimed",
        "local g, p, k, h, w, d = T.gas, T.gasSigns, T.keys, T.pictures, T.warren, T.warrenDead",
    ]
    for (cx, cy), squares in sorted(chunks.items()):
        lines.append('c["%d,%d"]=%s' % (cx, cy, lua_str("".join(v for _, v in sorted(squares.items())))))
    for letter, table in (("f", fx), ("z", zx), ("v", vx), ("u", ux), ("w", wx), ("d", dx)):
        for (cx, cy), items in sorted(table.items()):
            lines.append('%s["%d,%d"]={%s}' % (letter, cx, cy, ",".join(items)))
    # Sewer gas (place_gas): its squares, and the placards at its ways in.
    gas_rows, signs = gas or ({}, {})
    for (cx, cy), body in sorted(gas_rows.items()):
        lines.append('g["%d,%d"]=%s' % (cx, cy, lua_str(body)))
    for (cx, cy), items in sorted(signs.items()):
        lines.append('p["%d,%d"]={%s}' % (cx, cy, ",".join("{%d,%d,%s}" % (x, y, lua_str(e))
                                                           for x, y, e in sorted(items))))
    # The town's maintenance key (gate_shelters): the containers it is left in.
    by = collections.defaultdict(list)
    for x, y in keys:
        by[(x // 8, y // 8)].append("{%d,%d}" % (x, y))
    for (cx, cy), items in sorted(by.items()):
        lines.append('k["%d,%d"]={%s}' % (cx, cy, ",".join(items)))
    # The cult's pictures (gen_temple.py): hung on the wall of their square, once.
    by = collections.defaultdict(list)
    for x, y, spr in pictures:
        by[(x // 8, y // 8)].append("{%d,%d,%s}" % (x, y, lua_str(spr)))
    for (cx, cy), items in sorted(by.items()):
        lines.append('h["%d,%d"]={%s}' % (cx, cy, ",".join(items)))
    lines.append("return T")
    path = os.path.join(DATA, "SEW_Town_%s.lua" % tid)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def write_index(towns, rev, journals=(), plans=()):
    lines = [
        "-- GENERATED by tools/gen_sewers.py -- do not edit.",
        "-- Every town's sewers in brief: where the shafts and shelters are. Small, and",
        "-- loaded everywhere: the client lights the shafts and names the street, the",
        "-- server knows which manhole leads where. The squares are server-only (Data/).",
        "SEW = SEW or {}",
        "local I = { rev = %s, towns = {}, shafts = {}, shelters = {}, journals = {}, plans = {}, caves = {}, lair = nil, "
        "gas = {}, gates = {}, temple = nil, warren = nil }" % lua_str(rev),
        "SEW.Index = I",
        "local S, H, J, P, V, G, K = I.shafts, I.shelters, I.journals, I.plans, I.caves, I.gas, I.gates",
    ]
    for j in journals:
        lines.append("J[#J+1]={town=%s,x=%d,y=%d,kind=%s,text=%s,street=%s,dir=%s}"
                     % (lua_str(j["town"]), j["x"], j["y"], lua_str(j["kind"]), lua_str(j["text"]),
                        lua_str(j["street"]), lua_str(j["dir"])))
    for pl in plans:
        lines.append("P[#P+1]={town=%s,i=%d,j=%d}" % (lua_str(pl["town"]), pl["i"], pl["j"]))
    for tid, name, t, ladders in towns:
        tw, th = t["map_tiles"]
        # `key`: the id of the town's maintenance key, where it has locked gates.
        key = (", key = %d" % gate_key(tid)) if t.get("gated") else ""
        lines.append("I.towns[%s] = { name = %s, x0 = %d, y0 = %d, x1 = %d, y1 = %d, tw = %d, th = %d, chunks = %d%s }"
                     % (lua_str(tid), lua_str(name), t["x0"], t["y0"], t["x0"] + t["W"] - 1, t["y0"] + t["H"] - 1,
                        tw, th, t["n_chunks"], key))
        # Each locked gate: the square holding the door edge, and which edge.
        for x, y, edge in t.get("gates", []):
            lines.append('K[#K+1]={town=%s,x=%d,y=%d,edge="%s"}' % (lua_str(tid), x, y, edge))
        # `made`: a cover of ours, in a district the map gives few; the server
        # puts it into the road when a player first comes near (SEW_Build.cover).
        made = ",made=true" if t.get("made") else ""
        for sx, sy, lx, ly, edge, street in ladders:
            lines.append('S["%d,%d"]={town=%s,x=%d,y=%d,lx=%d,ly=%d,edge="%s",street=%s%s}'
                         % (sx, sy, lua_str(tid), sx, sy, lx, ly, edge, lua_str(street), made))
        # Hatches: shafts too, up through a house's floor rather than a street's
        # cover. `under` is every square of the culvert under the house (x, y,
        # x, y, ...): the server opens the hatch only if none holds a basement.
        for sx, sy, lx, ly, edge, h in t.get("hatch_ladders", []):
            under = ",".join("%d,%d" % (t["x0"] + x, t["y0"] + y) for x, y in h["under"])
            lines.append('S["%d,%d"]={town=%s,x=%d,y=%d,lx=%d,ly=%d,edge="%s",street="",hatch=%s,under={%s}}'
                         % (sx, sy, lua_str(tid), sx, sy, lx, ly, edge, lua_str(h["room"]), under))
        # Outfalls: shafts too, up through a grate in a riverbank. `made` like a
        # cover of ours: the server sets the grate into the bank when a player
        # up there first comes near (SEW_Build.cover).
        for sx, sy, lx, ly, edge, o in t.get("outfall_ladders", []):
            lines.append('S["%d,%d"]={town=%s,x=%d,y=%d,lx=%d,ly=%d,edge="%s",street="",made=true,outfall=true}'
                         % (sx, sy, lua_str(tid), sx, sy, lx, ly, edge))
        for r in t["rooms"]:
            rx, ry, w, h = r["rect"]
            lines.append("H[#H+1]={town=%s,kind=%s,x=%d,y=%d,w=%d,h=%d}"
                         % (lua_str(tid), lua_str(r["kind"]), t["x0"] + rx, t["y0"] + ry, w, h))
        # Each cave: its hideout, its breach, and the shaft nearest the breach
        # (the way to it from the street; the dev build starts a character there).
        for c in t["caves"]:
            bx, by = c["breach"]
            sx, sy = min(t["shafts"], key=lambda s: abs(s[0] - bx) + abs(s[1] - by))
            (hx, hy) = c["centre"]
            lines.append("V[#V+1]={town=%s,x=%d,y=%d,bx=%d,by=%d,sx=%d,sy=%d}"
                         % (lua_str(tid), t["x0"] + hx, t["y0"] + hy, t["x0"] + bx, t["y0"] + by,
                            t["x0"] + sx, t["y0"] + sy))
        # Each stretch of sewer gas (vent_gas): its id in the town's data, the
        # square nearest its middle (where the map marks it), and its size.
        for g in t.get("gas", []):
            mx = sum(x for x, _ in g["squares"]) / len(g["squares"])
            my = sum(y for _, y in g["squares"]) / len(g["squares"])
            cx, cy = min(g["squares"], key=lambda q: (q[0] - mx) ** 2 + (q[1] - my) ** 2)
            lines.append("G[#G+1]={town=%s,id=%s,x=%d,y=%d,n=%d}"
                         % (lua_str(tid), lua_str(GAS_IDS[g["id"] - 1]), t["x0"] + cx, t["y0"] + cy, len(g["squares"])))
    # The rats' nest (dig_lair): the tunnel square at its false wall (tx, ty)
    # and the first square through it (ex, ey), the middle of the nest, the
    # gnawed wall into the hoard (nest side gx, gy; hoard side vx, vy), where
    # its rodents sleep, and the hatch and cover nearest it by the tunnels.
    for tid, name, t, ladders in towns:
        L = t.get("lair")
        if not L:
            continue
        o = lambda p: (t["x0"] + p[0], t["y0"] + p[1])  # noqa: E731
        (tx, ty), (ex, ey), (cx, cy) = o(L["entry"]), o(L["first"]), o(L["centre"])
        (gx, gy), (vx, vy) = o(L["gate"][0]), o(L["gate"][1])
        rx, ry, w, h = L["hoard"]
        (hx, hy), (sx, sy) = o(t["lair_access"][0][1]), o(t["lair_access"][1][1])
        rous = ",".join("%d,%d" % o(p) for p in L["rous"])
        lines.append("I.lair={town=%s,tx=%d,ty=%d,ex=%d,ey=%d,x=%d,y=%d,gx=%d,gy=%d,vx=%d,vy=%d,"
                     "hx=%d,hy=%d,cx=%d,cy=%d,hoard={%d,%d,%d,%d},rous={%s}}"
                     % (lua_str(tid), tx, ty, ex, ey, cx, cy, gx, gy, vx, vy, hx, hy, sx, sy,
                        t["x0"] + rx, t["y0"] + ry, w, h, rous))
    # The warren (dig_warren): each den's middle and its size (x, y, r, ...),
    # and the candles the cult's pilgrims left burning in it (x, y, ...).
    for tid, name, t, ladders in towns:
        if t.get("warren"):
            lines.append("I.warren={town=%s,dens={%s},lights={%s}}"
                         % (lua_str(tid), ",".join("%d,%d,%d" % (t["x0"] + d["centre"][0], t["y0"] + d["centre"][1], d["r"])
                                                   for d in t["warren"]),
                            ",".join("%d,%d" % q for q in t["warren_lights"])))
    # The temple (gen_temple.py): its trapdoor's shaft -- a cover of ours to the
    # code, a trapdoor in a field to look at -- the idol, where the dev build
    # arrives, its lights (x, y, x, y, ...), and where each passage breaks
    # into a town's sewer (tunnel side tx, ty; passage side ex, ey).
    for tid, name, t, ladders in towns:
        T = t.get("temple")
        if not T:
            continue
        (tx, ty), (ix, iy), (hx, hy) = T["trap"], T["idol"], T["hall"]
        lines.append('S["%d,%d"]={town=%s,x=%d,y=%d,lx=%d,ly=%d,edge="N",street="",made=true,trapdoor=true}'
                     % (tx, ty, lua_str(tid), tx, ty, tx, ty))
        lines.append("I.temple={town=%s,x=%d,y=%d,hx=%d,hy=%d,tx=%d,ty=%d,lights={%s},breaches={%s}}"
                     % (lua_str(tid), ix, iy, hx, hy, tx, ty, ",".join("%d,%d" % q for q in T["lights"]),
                        ",".join("{town=%s,tx=%d,ty=%d,ex=%d,ey=%d,gx=%d,gy=%d,n=%d}"
                                 % (lua_str(b["town"]), b["a"][0], b["a"][1], b["e"][0], b["e"][1],
                                    b["gate"][0], b["gate"][1], b["length"]) for b in T["breaches"])))
    lines.append("return I")
    with open(INDEX, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


MAPS_UI = os.path.join(ROOT, "Sewars", "42", "media", "ui", "sewermap")
MAP_TILE = 256


def map_images(tid, t):
    """The sewer map's picture of one town, one pixel a square, in 256x256 tiles.

    What the player's map panel draws (SEW_Map.lua), under a fog it lifts chunk
    by chunk as they walk. Tiled from the start so no texture is ever larger
    than 256 on a side (whatever the engine's limit) and the panel draws only
    the tiles on screen. Transparent where there is nothing; the panel lays
    paper under it. Returns (tiles across, tiles down).
    """
    from PIL import Image
    W, H = t["W"], t["H"]
    space = t["tunnel"] | (t["room_id"] > 0) | (t["cave_id"] > 0)
    for x, y in t.get("cult", ()):
        space[y, x] = True
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[t["road"] & ~space] = (120, 104, 80, 60)             # the streets above, faint
    water = water_region(t["x0"], t["y0"], t["x0"] + W - 1, t["y0"] + H - 1)[0]
    rgba[water & ~space] = (70, 96, 120, 90)                    # creeks, rivers and lakes above, fainter
    outline = ndi.binary_dilation(space) & ~space
    rgba[outline] = (58, 46, 34, 255)                           # walls, in ink
    rgba[t["tunnel"]] = (226, 214, 184, 255)
    rgba[t["chamber"]] = (214, 170, 124, 255)
    rgba[t["channel"]] = (104, 140, 112, 255)
    rgba[t["room_id"] > 0] = (190, 180, 150, 255)
    rgba[t["cave_id"] > 0] = (150, 118, 82, 255)                 # dug earth
    for x, y in t.get("cult", ()):                              # a passage the cult dug under this town's sheet
        rgba[y, x] = (150, 118, 82, 255)
    os.makedirs(MAPS_UI, exist_ok=True)
    tw, th = (W + MAP_TILE - 1) // MAP_TILE, (H + MAP_TILE - 1) // MAP_TILE
    for i in range(tw):
        for j in range(th):
            tile = np.zeros((MAP_TILE, MAP_TILE, 4), np.uint8)
            part = rgba[j * MAP_TILE:(j + 1) * MAP_TILE, i * MAP_TILE:(i + 1) * MAP_TILE]
            tile[:part.shape[0], :part.shape[1]] = part
            Image.fromarray(tile, "RGBA").save(os.path.join(MAPS_UI, "%s_%d_%d.png" % (tid, i, j)), optimize=True)
    return tw, th


def plan(t, path):
    from PIL import Image
    W, H = t["W"], t["H"]
    im = np.zeros((H, W, 3), np.uint8)
    im[:] = (14, 14, 18)
    im[t["road"]] = (48, 48, 54)
    im[water_region(t["x0"], t["y0"], t["x0"] + W - 1, t["y0"] + H - 1)[0]] = (20, 40, 90)
    im[t["keep"]] = (40, 26, 26)
    im[t["tunnel"]] = (120, 120, 110)
    im[t["trunk"] & t["tunnel"]] = (150, 130, 100)
    im[t["chamber"]] = (180, 90, 60)
    im[t["channel"]] = (60, 120, 60)
    im[t["room_id"] > 0] = (70, 130, 200)
    im[t["cave_id"] > 0] = (170, 120, 60)
    for c in t["caves"]:
        x, y = c["breach"]
        im[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = (255, 120, 255)
    for x, y in t.get("cult", ()):
        im[y, x] = (220, 60, 160)
    for g in t.get("gas", []):
        for x, y in g["squares"]:
            im[y, x] = (190, 230, 40)
    for h in t["hatches"]:
        x, y = h["hatch"]
        im[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = (0, 255, 255)
    if t.get("lair") is not None:
        im[t["lair_id"] == 1] = (200, 60, 60)
        im[t["lair_id"] == 2] = (255, 215, 0)
        for d in t.get("warren", []):
            for x, y in d["cells"]:
                im[y, x] = (240, 110, 60)
    for x, y in t["shafts"]:
        im[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = (255, 210, 0)
    for o in t.get("outfalls", []):
        x, y = o["bank"]
        im[max(0, y - 2):y + 3, max(0, x - 2):x + 3] = (255, 255, 255)
    for a, b in t["dropped"]:
        x, y = a - t["x0"], b - t["y0"]
        im[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = (255, 0, 0)
    img = Image.fromarray(im)
    if max(W, H) < 700:
        img = img.resize((W * 2, H * 2), Image.NEAREST)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plans", action="store_true")
    a = ap.parse_args()

    holes = all_manholes()
    if len(holes) < 400:
        raise SystemExit("only %d manholes found: the reader or the sprite name has stopped matching" % len(holes))
    names = town_names()
    streets_all = streets()
    groups = clusters(holes)
    print("%d manholes in %d towns, %d streets" % (len(holes), len(groups), len(streets_all)))

    towns, used, digest, totals = [], collections.Counter(), hashlib.md5(), collections.Counter()
    built = []
    journals, plans = [], []
    # The biggest cluster near a town takes its plain name; strays get a number.
    taken = set()          # chunks some town already has

    def town(name, g, district=None):
        base = slug(name)
        used[base] += 1
        tid = base if used[base] == 1 else "%s_%d" % (base, used[base])
        # A district keeps a chunk clear of every town before it.
        forbid = {(kx + dx, ky + dy) for kx, ky in taken for dx in (-1, 0, 1) for dy in (-1, 0, 1)} if district else ()
        t = lay_out(tid, g, streets_all, district, forbid)
        if district and not t["shafts"]:
            used[base] -= 1          # no clear road for a cover: no town, and no name used up
            print("  (%s: no cover of ours fits; left out)" % name)
            return
        t["gated"] = gate_shelters(tid, t["rooms"])
        chunks, ladders = encode(t)
        taken.update(chunks)
        extras = story(tid, t, ladders, journals, plans)
        furniture, dead = furnish(t, extras)
        t["keys"] = key_spots(t, furniture)
        t["gates"] = sorted((x, y, "N" if r[3] == "j" else "W") for rows in chunks.values()
                            for (x, y), r in rows.items() if "j" in (r[3], r[4]))
        cave_furniture, cave_dead = furnish_caves(t)
        if t.get("lair"):
            cave_furniture = list(cave_furniture) + furnish_lair(t)
            t["lair_access"] = lair_access(t, ladders)
        # Not written yet: the temple's passages break into two towns' tunnels
        # (gen_temple.py), and those towns' records are patched first.
        b = dict(tid=tid, name=name, t=t, chunks=chunks, ladders=ladders, furniture=furniture, dead=dead,
                 cave_furniture=cave_furniture, cave_dead=cave_dead, pictures=[], warren=([], []))
        if t.get("warren"):
            wf, wd, wp, t["warren_lights"] = furnish_warren(t)
            b["warren"] = (wf, wd)
            b["pictures"] += wp
        built.append(b)

    def finish(b):
        tid, name, t, chunks, ladders = b["tid"], b["name"], b["t"], b["chunks"], b["ladders"]
        write_town(tid, name, chunks, b["furniture"], b["dead"], b["cave_furniture"], b["cave_dead"],
                   place_gas(t, chunks), t["keys"], b["pictures"], b["warren"])
        t["map_tiles"] = map_images(tid, t)
        t["n_chunks"] = len(chunks)
        towns.append((tid, name, t, ladders))
        squares = sum(len(c) for c in chunks.values())
        for k in sorted(chunks):
            digest.update(("%s%s" % (k, "".join(v for _, v in sorted(chunks[k].items())))).encode())
        totals["squares"] += squares
        totals["made" if t["made"] else "shafts"] += len(ladders)
        totals["dropped"] += len(t["dropped"])
        totals["shelters"] += len(t["rooms"])
        totals["caves"] += len(t["caves"])
        totals["hatches"] += len(t["hatches"])
        totals["gas"] += len(t["gas"])
        totals["gates"] += len(t["gates"])
        totals["outfalls"] += len(t["outfalls"])
        print("  %-18s %3d %s %7d squares %4d chunks %3d shelters %3d vaults %3d caves %3d hatches %2d gas %d outfalls%s"
              % (tid, len(ladders), "covers ours" if t["made"] else "manholes   ", squares, len(chunks),
                 len(t["rooms"]), len(t["junctions"]), len(t["caves"]), len(t["hatches"]), len(t["gas"]), len(t["outfalls"]),
                 ("  (%d over buildings, left shut)" % len(t["dropped"])) if t["dropped"] else ""))
        if a.plans:
            plan(t, os.path.join(PLANS, "%s.png" % tid))

    for g in sorted(groups, key=len, reverse=True):
        cx = sum(h[0] for h in g) / len(g)
        cy = sum(h[1] for h in g) / len(g)
        near = min(names, key=lambda n: (n[1] - cx) ** 2 + (n[2] - cy) ** 2)
        far = ((near[1] - cx) ** 2 + (near[2] - cy) ** 2) ** 0.5
        town(near[0] if far < 1500 else "Knox County", g)
    # Then the built-up districts the map gives few covers (ROADMAP 0.4), after
    # every town above so none of those moves, each with covers of our own.
    for name, box, cells in sparse_districts(holes, names):
        town(name, [], (box, cells))
    # The temple, last of all and from a generator of its own: a town in
    # chunks no town has, and two passages out to the sewers either side.
    temple = gen_temple.dig(built, journals, region, room_mask, under_map, water_region)
    # What each of the two places says of the other (ROADMAP 0.6): the
    # writings left in the dens, pointing at the temple and its breaches.
    gen_temple.cross(built, journals, temple)
    # Only now is the old layout taken away: everything that can fail has not.
    # (It went first once, and a temple that would not fit left the tree with
    # no sewers at all until the next good run.)
    for old in glob.glob(os.path.join(DATA, "SEW_Town_*.lua")):
        os.remove(old)
    for old in glob.glob(os.path.join(MAPS_UI, "*.png")):
        os.remove(old)
    for b in built:
        finish(b)
    finish(temple)
    T = temple["t"]["temple"]
    print("the temple: idol at %d,%d, trapdoor at %d,%d; passages %s"
          % (T["idol"] + T["trap"] + (", ".join("%s %d squares from %d,%d" % (b["town"], b["length"], b["a"][0], b["a"][1])
                                                for b in T["breaches"]),)))
    write_index(towns, digest.hexdigest()[:12], journals, plans)
    print("story: %d journals, %d plans" % (len(journals), len(plans)))
    print("total: %(squares)d squares, %(shafts)d shafts under the map's covers and %(made)d under ours, "
          "%(shelters)d shelters (%(gates)d locked), %(caves)d caves, %(hatches)d hatches, %(outfalls)d outfalls, "
          "%(gas)d stretches of gas, "
          "%(dropped)d manholes left shut" % totals)
    if totals["shafts"] + totals["dropped"] != len(holes):
        raise SystemExit("a manhole was neither given a shaft nor reported: %d + %d != %d"
                         % (totals["shafts"], totals["dropped"], len(holes)))


if __name__ == "__main__":
    main()
