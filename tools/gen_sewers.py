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

KINDS = ("maintenance", "pump", "squat", "laststand")
N4 = [(0, -1), (-1, 0), (1, 0), (0, 1)]


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

def lay_out(tid, holes, streets_all):
    xs, ys = [h[0] for h in holes], [h[1] for h in holes]
    x0, y0 = min(xs) - MARGIN, min(ys) - MARGIN
    x1, y1 = max(xs) + MARGIN, max(ys) + MARGIN
    road, keep = region(x0, y0, x1, y1)
    H, W = road.shape
    rng = random.Random(SEED * 7919 + h32(tid))
    keep = ndi.binary_dilation(keep, iterations=KEEP_OUT)

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
                rooms=rooms, room_id=room_id, junctions=placed, street_of=street_of)


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


# --- squares ---------------------------------------------------------------------------------
#
# Legend (SEW_Data.lua decodes it):
#   floor    . none  t tunnel  k vault  s shelter  g grating  w channel (sludge, not walkable)  r rock (outside, under a wall)
#   walls    . none  c concrete  b brick  d a door frame, with its steel door
#   fixture  . none  L ladder on the N edge  l ladder on the W edge  P pillar (concrete)  Q pillar (brick)
#   dressing . none  p pipe  e EXIT stencil  a-g graffiti  h SAFE stencil  i grime  u puddle  v debris  x light pool  y smear

GRAFFITI = "abcdefg"


def encode(t):
    """({(cx, cy): {(x, y): record}}, ladders) for every square the town touches, world coords."""
    x0, y0, W, H = t["x0"], t["y0"], t["W"], t["H"]
    tunnel, chamber, trunk, channel, room_id = t["tunnel"], t["chamber"], t["trunk"], t["channel"], t["room_id"]
    space = tunnel | (room_id > 0)
    group = np.where(tunnel, -1, room_id)
    sq = {}

    def rec(x, y):
        key = (x, y)
        if key not in sq:
            sq[key] = [str(x % 8), str(y % 8), ".", ".", ".", ".", "."]
        return sq[key]

    for y, x in zip(*np.nonzero(space)):
        r = rec(x0 + x, y0 + y)
        r[2] = "s" if room_id[y, x] else "w" if channel[y, x] else "k" if chamber[y, x] else "t"

    # Walls, on the N or W edge of the square south or east of each boundary.
    pad = lambda a, v: np.pad(a, 1, constant_values=v)  # noqa: E731
    sp, gp, br = pad(space, False), pad(group, 0), pad(chamber | trunk, False)
    doors = {}
    for rm in t["rooms"]:
        (tx, ty), (ix, iy) = rm["door"], rm["inside"]
        doors[(tx, max(ty, iy), "N") if tx == ix else (max(tx, ix), ty, "W")] = rm
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
                    r[col] = "d"
                else:
                    brick = br[y + 1, x + 1] or br[y + 1 + dy, x + 1 + dx]
                    r[col] = "b" if brick else "c"
                if not (x < W and y < H and space[y, x]) and r[2] == ".":
                    r[2] = "r"

    # Pillars where a north wall and a west wall end at the same corner from the north-west.
    for (wx, wy), r in list(sq.items()):
        if r[3] not in "cbd":
            continue
        px, py = wx + 1, wy
        north = sq.get((px, py - 1))
        here = sq.get((px, py))
        if north and north[4] in "cbd" and not (here and (here[3] != "." or here[4] != ".")):
            if r[5] == ".":
                r[5] = "Q" if "b" in (r[3], north[4]) else "P"

    # Ladders, one per shaft, on a wall of (or beside) the square under the cover.
    ladders = []
    for sx, sy in t["shafts"]:
        wx, wy = x0 + sx, y0 + sy
        here = rec(wx, wy)
        here[2] = "g"
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
            else:
                here[3], here[5], edge = "c", "L", "N"
        ladders.append((wx, wy, lx, ly, edge, t["street_of"].get((sx, sy), "")))

    # Dressing, deterministic by position.
    near_shaft = set()
    for sx, sy in t["shafts"]:
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                near_shaft.add((x0 + sx + dx, y0 + sy + dy))
    shaft_pts = [(x0 + sx, y0 + sy) for sx, sy in t["shafts"]]

    def near_ladder(x, y, reach=12):
        return any(abs(x - a) + abs(y - b) <= reach for a, b in shaft_pts)

    for (wx, wy), r in sq.items():
        if r[6] != "." or r[5] != ".":
            continue
        roll = h32("dress", wx, wy) % 1000
        walled = r[3] in "cb" or r[4] in "cb"
        if walled and r[2] in "tk":
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


# --- writing ---------------------------------------------------------------------------------

def lua_str(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_town(tid, name, chunks, furniture, dead):
    os.makedirs(DATA, exist_ok=True)
    fx = collections.defaultdict(list)
    for x, y, spr, loot, extra in furniture:
        fx[(x // 8, y // 8)].append("{%d,%d,%s,%s,%s}" % (x, y, lua_str(spr), lua_str(loot) if loot else "nil",
                                                         lua_str(extra) if extra else "nil"))
    zx = collections.defaultdict(list)
    for x, y, outfit in dead:
        zx[(x // 8, y // 8)].append("{%d,%d,%s}" % (x, y, lua_str(outfit)))
    lines = [
        "-- GENERATED by tools/gen_sewers.py -- do not edit. %s: the squares, by chunk." % name,
        "if isClient() then return end",
        "SEW = SEW or {}",
        "SEW.Data = SEW.Data or {}",
        "local T = { id = %s, name = %s, chunks = {}, furniture = {}, claimed = {} }" % (lua_str(tid), lua_str(name)),
        "SEW.Data[%s] = T" % lua_str(tid),
        "local c, f, z = T.chunks, T.furniture, T.claimed",
    ]
    for (cx, cy), squares in sorted(chunks.items()):
        lines.append('c["%d,%d"]=%s' % (cx, cy, lua_str("".join(v for _, v in sorted(squares.items())))))
    for (cx, cy), items in sorted(fx.items()):
        lines.append('f["%d,%d"]={%s}' % (cx, cy, ",".join(items)))
    for (cx, cy), items in sorted(zx.items()):
        lines.append('z["%d,%d"]={%s}' % (cx, cy, ",".join(items)))
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
        "local I = { rev = %s, towns = {}, shafts = {}, shelters = {}, journals = {}, plans = {} }" % lua_str(rev),
        "SEW.Index = I",
        "local S, H, J, P = I.shafts, I.shelters, I.journals, I.plans",
    ]
    for j in journals:
        lines.append("J[#J+1]={town=%s,x=%d,y=%d,kind=%s,text=%s,street=%s,dir=%s}"
                     % (lua_str(j["town"]), j["x"], j["y"], lua_str(j["kind"]), lua_str(j["text"]),
                        lua_str(j["street"]), lua_str(j["dir"])))
    for pl in plans:
        lines.append("P[#P+1]={town=%s,i=%d,j=%d}" % (lua_str(pl["town"]), pl["i"], pl["j"]))
    for tid, name, t, ladders in towns:
        tw, th = t["map_tiles"]
        lines.append("I.towns[%s] = { name = %s, x0 = %d, y0 = %d, x1 = %d, y1 = %d, tw = %d, th = %d, chunks = %d }"
                     % (lua_str(tid), lua_str(name), t["x0"], t["y0"], t["x0"] + t["W"] - 1, t["y0"] + t["H"] - 1,
                        tw, th, t["n_chunks"]))
        for sx, sy, lx, ly, edge, street in ladders:
            lines.append('S["%d,%d"]={town=%s,x=%d,y=%d,lx=%d,ly=%d,edge="%s",street=%s}'
                         % (sx, sy, lua_str(tid), sx, sy, lx, ly, edge, lua_str(street)))
        for r in t["rooms"]:
            rx, ry, w, h = r["rect"]
            lines.append("H[#H+1]={town=%s,kind=%s,x=%d,y=%d,w=%d,h=%d}"
                         % (lua_str(tid), lua_str(r["kind"]), t["x0"] + rx, t["y0"] + ry, w, h))
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
    space = t["tunnel"] | (t["room_id"] > 0)
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[t["road"] & ~space] = (120, 104, 80, 60)             # the streets above, faint
    outline = ndi.binary_dilation(space) & ~space
    rgba[outline] = (58, 46, 34, 255)                           # walls, in ink
    rgba[t["tunnel"]] = (226, 214, 184, 255)
    rgba[t["chamber"]] = (214, 170, 124, 255)
    rgba[t["channel"]] = (104, 140, 112, 255)
    rgba[t["room_id"] > 0] = (190, 180, 150, 255)
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
    im[t["keep"]] = (40, 26, 26)
    im[t["tunnel"]] = (120, 120, 110)
    im[t["trunk"] & t["tunnel"]] = (150, 130, 100)
    im[t["chamber"]] = (180, 90, 60)
    im[t["channel"]] = (60, 120, 60)
    im[t["room_id"] > 0] = (70, 130, 200)
    for x, y in t["shafts"]:
        im[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = (255, 210, 0)
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

    for old in glob.glob(os.path.join(DATA, "SEW_Town_*.lua")):
        os.remove(old)
    for old in glob.glob(os.path.join(MAPS_UI, "*.png")):
        os.remove(old)

    towns, used, digest, totals = [], collections.Counter(), hashlib.md5(), collections.Counter()
    journals, plans = [], []
    # The biggest cluster near a town takes its plain name; strays get a number.
    for g in sorted(groups, key=len, reverse=True):
        cx = sum(h[0] for h in g) / len(g)
        cy = sum(h[1] for h in g) / len(g)
        near = min(names, key=lambda n: (n[1] - cx) ** 2 + (n[2] - cy) ** 2)
        far = ((near[1] - cx) ** 2 + (near[2] - cy) ** 2) ** 0.5
        name = near[0] if far < 1500 else "Knox County"
        base = slug(name)
        used[base] += 1
        tid = base if used[base] == 1 else "%s_%d" % (base, used[base])
        t = lay_out(tid, g, streets_all)
        chunks, ladders = encode(t)
        extras = story(tid, t, ladders, journals, plans)
        furniture, dead = furnish(t, extras)
        write_town(tid, name, chunks, furniture, dead)
        t["map_tiles"] = map_images(tid, t)
        t["n_chunks"] = len(chunks)
        towns.append((tid, name, t, ladders))
        squares = sum(len(c) for c in chunks.values())
        for k in sorted(chunks):
            digest.update(("%s%s" % (k, "".join(v for _, v in sorted(chunks[k].items())))).encode())
        totals["squares"] += squares
        totals["shafts"] += len(ladders)
        totals["dropped"] += len(t["dropped"])
        totals["shelters"] += len(t["rooms"])
        print("  %-18s %3d manholes %7d squares %4d chunks %2d shelters %2d vaults%s"
              % (tid, len(g), squares, len(chunks), len(t["rooms"]), len(t["junctions"]),
                 ("  (%d over buildings, left shut)" % len(t["dropped"])) if t["dropped"] else ""))
        if a.plans:
            plan(t, os.path.join(PLANS, "%s.png" % tid))
    write_index(towns, digest.hexdigest()[:12], journals, plans)
    print("story: %d journals, %d plans" % (len(journals), len(plans)))
    print("total: %(squares)d squares, %(shafts)d shafts, %(shelters)d shelters, "
          "%(dropped)d manholes left shut" % totals)
    if totals["shafts"] + totals["dropped"] != len(holes):
        raise SystemExit("a manhole was neither given a shaft nor reported: %d + %d != %d"
                         % (totals["shafts"], totals["dropped"], len(holes)))


if __name__ == "__main__":
    main()
