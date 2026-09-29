"""The generated sewers, read back from the Lua the game loads, and walked.

    python tests/test_layout.py

Reads every Data/SEW_Town_*.lua and SEW_Index.lua exactly as shipped (not the
generator's own arrays -- a check of the generator's memory is a check of the
generator) and asserts, per town:

  * every shaft has a grating floor under its cover and a ladder where the
    index says, on the edge it says;
  * **every walkable square can be walked to from a ladder**: walls block,
    door frames pass, the sludge channel does not hold you. A pocket nobody
    can leave is a player dying in the dark;
  * no square the tunnels use is under a building footprint or over the
    map's own underground (tools/gen_sewers.py cell cache);
  * every shelter has exactly one door, and every piece of its furniture
    stands on its floor;
  * the records are well formed.
"""
import glob
import os
import re
import sys
from collections import deque

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "Sewars", "42", "media", "lua")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_sewers  # noqa: E402

FAILS = []
REC = re.compile(r'^[0-7][0-7][.tksgwr][.cbd][.cbd][.LlPQ][.peabcdefghiuvxy]$')


def check(cond, what):
    print(("  ok    " if cond else "  FAIL  ") + what)
    if not cond:
        FAILS.append(what)


def read_index():
    s = open(os.path.join(LUA, "shared", "SEW", "SEW_Index.lua"), encoding="utf-8").read()
    shafts = [dict(zip(("town", "x", "y", "lx", "ly", "edge"), (m[0], int(m[1]), int(m[2]), int(m[3]), int(m[4]), m[5])))
              for m in re.findall(r'S\["-?\d+,-?\d+"\]=\{town="(\w+)",x=(\d+),y=(\d+),lx=(\d+),ly=(\d+),edge="(\w)"', s)]
    shelters = [dict(zip(("town", "kind", "x", "y", "w", "h"), (m[0], m[1]) + tuple(int(v) for v in m[2:])))
                for m in re.findall(r'H\[#H\+1\]=\{town="(\w+)",kind="(\w+)",x=(\d+),y=(\d+),w=(\d+),h=(\d+)\}', s)]
    return shafts, shelters


def read_town(path):
    s = open(path, encoding="utf-8").read()
    sq, bad = {}, []
    for cx, cy, body in re.findall(r'c\["(-?\d+),(-?\d+)"\]="([^"]*)"', s):
        cx, cy = int(cx), int(cy)
        for i in range(0, len(body), 7):
            r = body[i:i + 7]
            if not REC.match(r):
                bad.append(r)
                continue
            sq[(cx * 8 + int(r[0]), cy * 8 + int(r[1]))] = r
    furniture = [(int(x), int(y), spr) for x, y, spr in re.findall(r'\{(\d+),(\d+),"([^"]+)",', s)]
    return sq, furniture, bad


def step_open(sq, a, b):
    """True when a player can step from square a to the next square b."""
    r = sq.get(b)
    if r is None or r[2] not in "tksg":
        return False
    (ax, ay), (bx, by) = a, b
    if bx == ax and by == ay + 1:
        e = sq.get(b)
        return e[3] in ".d"
    if bx == ax and by == ay - 1:
        e = sq.get(a)
        return not e or e[3] in ".d"
    if by == ay and bx == ax + 1:
        return sq.get(b)[4] in ".d"
    if by == ay and bx == ax - 1:
        e = sq.get(a)
        return not e or e[4] in ".d"
    return False


def walk(sq, starts):
    """Squares reachable from `starts` on foot."""
    def open_between(a, b):
        (ax, ay), (bx, by) = a, b
        if bx == ax and by == ay + 1:      # b south of a: b's north edge
            e = sq.get(b)
            return not e or e[3] in ".d"
        if bx == ax and by == ay - 1:
            e = sq.get(a)
            return not e or e[3] in ".d"
        if by == ay and bx == ax + 1:      # b east of a: b's west edge
            e = sq.get(b)
            return not e or e[4] in ".d"
        if by == ay and bx == ax - 1:
            e = sq.get(a)
            return not e or e[4] in ".d"
        return False

    def standable(p):
        r = sq.get(p)
        return r is not None and r[2] in "tksg"

    seen = set(p for p in starts if standable(p))
    q = deque(seen)
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n not in seen and standable(n) and open_between((x, y), n):
                seen.add(n)
                q.append(n)
    return seen


def main():
    shafts, shelters = read_index()
    check(len(shafts) > 400, "the index lists the shafts (%d)" % len(shafts))
    towns = sorted(glob.glob(os.path.join(LUA, "server", "SEW", "Data", "SEW_Town_*.lua")))
    check(len(towns) >= 10, "towns generated (%d)" % len(towns))
    total_walk, total_stranded = 0, 0
    for path in towns:
        tid = os.path.basename(path)[9:-4]
        sq, furniture, bad = read_town(path)
        check(not bad, "%s: every record is well formed (%s)" % (tid, bad[:3]))
        mine = [s for s in shafts if s["town"] == tid]
        ok_shaft = all(sq.get((s["x"], s["y"]), "  .")[2] == "g" for s in mine)
        ok_ladder = all(sq.get((s["lx"], s["ly"]), "      ")[5] == ("L" if s["edge"] == "N" else "l") for s in mine)
        reach = walk(sq, [(s["x"], s["y"]) for s in mine])
        walkable = [p for p, r in sq.items() if r[2] in "tksg"]
        stranded = [p for p in walkable if p not in reach]
        total_walk += len(walkable)
        total_stranded += len(stranded)
        rooms = [h for h in shelters if h["town"] == tid]
        one_door = True
        for h in rooms:
            doors = 0
            for x in range(h["x"] - 1, h["x"] + h["w"] + 1):
                for y in range(h["y"] - 1, h["y"] + h["h"] + 1):
                    r = sq.get((x, y))
                    if r and "d" in (r[3], r[4]):
                        doors += (r[3] == "d") + (r[4] == "d")
            one_door &= doors == 1
        on_floor = all(sq.get((x, y), "  .")[2] == "s" for x, y, _ in furniture)

        # Near misses: a 1-wide tunnel that ends, walled, within a few squares of
        # other tunnel straight ahead -- a street that stopped at the edge of the
        # road it meets (0.3, "a dead end that says UP"). Should be none.
        near_miss = []
        for (x, y), r in sq.items():
            if r[2] not in "tk":
                continue
            opens = [(dx, dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                     if step_open(sq, (x, y), (x + dx, y + dy))]
            if len(opens) != 1:
                continue
            fx, fy = -opens[0][0], -opens[0][1]
            for k in range(2, 6):
                ahead = sq.get((x + fx * k, y + fy * k))
                if ahead and ahead[2] in "tksg":
                    near_miss.append((x, y))
                    break
        check(not near_miss, "%s: no tunnel stops just short of another (%d, e.g. %s)"
              % (tid, len(near_miss), near_miss[:3]))
        far_up = [(x, y) for (x, y), r in sq.items() if r[6] == "f"
                  and not any(abs(x - s["x"]) + abs(y - s["y"]) <= 12 for s in mine)]
        check(not far_up, "%s: every UP on a wall has a ladder near it (%d far)" % (tid, len(far_up)))
        check(ok_shaft and ok_ladder and not stranded and one_door and on_floor,
              "%-14s %3d shafts, %6d walkable, %2d shelters: ladders %s, stranded %d, doors %s, furniture %s"
              % (tid, len(mine), len(walkable), len(rooms), "ok" if ok_shaft and ok_ladder else "BAD",
                 len(stranded), "ok" if one_door else "BAD", "ok" if on_floor else "BAD"))

        # Nothing under a building, nothing over the map's own underground.
        xs = [p[0] for p in sq]
        ys = [p[1] for p in sq]
        road, keep = gen_sewers.region(min(xs), min(ys), max(xs), max(ys))
        under = [p for p, r in sq.items() if r[2] in "tksgw" and keep[p[1] - min(ys), p[0] - min(xs)]]
        check(not under, "%s: no tunnel square under a building or a basement (%d)" % (tid, len(under)))

        # No tunnel ends in a wall under a road that runs on to the network: the
        # street list has gaps the painted road does not (Harris St, Muldraugh,
        # 0.3.1: "I am here at a dead end"). Walk straight on under the road; if
        # that reaches tunnel within gen_sewers.ROAD_RUN, the end should be open.
        # Ends by a shaft or a shelter are left alone on purpose (they would move
        # a ladder or a shelter under a save).
        near_shaft = set((s["x"] + dx, s["y"] + dy) for s in mine for dx in (-1, 0, 1) for dy in (-1, 0, 1))
        near_room = set((x, y) for h in rooms for x in range(h["x"] - 3, h["x"] + h["w"] + 3)
                        for y in range(h["y"] - 3, h["y"] + h["h"] + 3))
        walled = []
        for (x, y), r in sq.items():
            if r[2] not in "tk" or (x, y) in near_shaft:
                continue
            opens = [(dx, dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                     if step_open(sq, (x, y), (x + dx, y + dy))]
            if len(opens) != 1:
                continue
            fx, fy = -opens[0][0], -opens[0][1]
            for k in range(1, gen_sewers.ROAD_RUN + 1):
                px, py = x + fx * k, y + fy * k
                lx, ly = px - min(xs), py - min(ys)
                if not (0 <= lx < road.shape[1] and 0 <= ly < road.shape[0]) or not road[ly, lx] \
                        or keep[ly, lx] or (px, py) in near_room or (px, py) in near_shaft:
                    break
                if (px, py) in sq and sq[(px, py)][2] in "tksgw":
                    walled.append((x, y))
                    break
        check(not walled, "%s: no tunnel ends in a wall with the road running on to more tunnel (%d, e.g. %s)"
              % (tid, len(walled), walled[:3]))
    check(total_walk > 50000 and total_stranded == 0,
          "all towns: %d walkable squares, %d stranded" % (total_walk, total_stranded))

    # The walker must not be kind: with every door shut, every shelter floor
    # has to become unreachable. If it does not, walls are not being read.
    sq, _, _ = read_town(os.path.join(LUA, "server", "SEW", "Data", "SEW_Town_muldraugh.lua"))
    shut = {p: r[:3] + ("c" if r[3] == "d" else r[3]) + ("c" if r[4] == "d" else r[4]) + r[5:] for p, r in sq.items()}
    reach = walk(shut, [(s["x"], s["y"]) for s in shafts if s["town"] == "muldraugh"])
    rooms = [p for p, r in shut.items() if r[2] == "s"]
    check(rooms and not any(p in reach for p in rooms),
          "the walker reads walls: with the doors shut, none of %d shelter squares is reachable" % len(rooms))
    print()
    if FAILS:
        print("%d FAILED" % len(FAILS))
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
