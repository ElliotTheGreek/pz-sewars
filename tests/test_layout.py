"""The generated sewers, read back from the Lua the game loads, and walked.

    python tests/test_layout.py

Reads every Data/SEW_Town_*.lua and SEW_Index.lua exactly as shipped (not the
generator's own arrays -- a check of the generator's memory is a check of the
generator) and asserts, per town:

  * every shaft has a grating floor under its cover and a ladder where the
    index says, on the edge it says;
  * **every walkable square can be walked to from a ladder**: walls block,
    door frames and breaches pass, the sludge channel does not hold you. A
    pocket nobody can leave is a player dying in the dark;
  * every cave meets the sewer by exactly one breach, its hideout is its own
    earth, and there is no way into it but that breach;
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
REC = re.compile(r'^[0-7][0-7][.tksgwrmnv][.cbdeoqxyz][.cbdeoqxyz][.LlPQ][.peabcdefghijklnouvxyz]$')
FLOORS = "tksgmnv"    # stood on (m: a cave's earth; n: the rats' nest and its run; v: their hoard)
OPEN = ".doqxyz"      # edges walked through: none, a door frame, a breach, the nest's walls once opened


def check(cond, what):
    print(("  ok    " if cond else "  FAIL  ") + what)
    if not cond:
        FAILS.append(what)


def read_caves():
    s = open(os.path.join(LUA, "shared", "SEW", "SEW_Index.lua"), encoding="utf-8").read()
    return [dict(zip(("town", "x", "y", "bx", "by", "sx", "sy"), (m[0],) + tuple(int(v) for v in m[1:])))
            for m in re.findall(r'V\[#V\+1\]=\{town="(\w+)",x=(\d+),y=(\d+),bx=(\d+),by=(\d+),sx=(\d+),sy=(\d+)\}', s)]


def read_lair():
    s = open(os.path.join(LUA, "shared", "SEW", "SEW_Index.lua"), encoding="utf-8").read()
    m = re.search(r'I\.lair=\{town="(\w+)",([^{]*)hoard=\{([\d,]+)\},rous=\{([\d,]*)\}\}', s)
    if not m:
        return None
    L = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', m[2])}
    L["town"] = m[1]
    L["hoard"] = [int(v) for v in m[3].split(",")]
    v = [int(n) for n in m[4].split(",") if n]
    L["rous"] = list(zip(v[0::2], v[1::2]))
    return L


def read_index():
    s = open(os.path.join(LUA, "shared", "SEW", "SEW_Index.lua"), encoding="utf-8").read()
    shafts = []
    for line in s.splitlines():
        m = re.match(r'S\["-?\d+,-?\d+"\]=\{town="(\w+)",x=(\d+),y=(\d+),lx=(\d+),ly=(\d+),edge="(\w)"', line)
        if not m:
            continue
        sh = dict(zip(("town", "x", "y", "lx", "ly", "edge"), (m[1], int(m[2]), int(m[3]), int(m[4]), int(m[5]), m[6])))
        h = re.search(r'hatch="(\w+)",under=\{([\d,]*)\}', line)
        if h:
            v = [int(n) for n in h[2].split(",") if n]
            sh["hatch"], sh["under"] = h[1], list(zip(v[0::2], v[1::2]))
        sh["made"] = ",made=true" in line
        shafts.append(sh)
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
    if r is None or r[2] not in FLOORS:
        return False
    (ax, ay), (bx, by) = a, b
    if bx == ax and by == ay + 1:
        e = sq.get(b)
        return e[3] in OPEN
    if bx == ax and by == ay - 1:
        e = sq.get(a)
        return not e or e[3] in OPEN
    if by == ay and bx == ax + 1:
        return sq.get(b)[4] in OPEN
    if by == ay and bx == ax - 1:
        e = sq.get(a)
        return not e or e[4] in OPEN
    return False


def walk(sq, starts):
    """Squares reachable from `starts` on foot."""
    def open_between(a, b):
        (ax, ay), (bx, by) = a, b
        if bx == ax and by == ay + 1:      # b south of a: b's north edge
            e = sq.get(b)
            return not e or e[3] in OPEN
        if bx == ax and by == ay - 1:
            e = sq.get(a)
            return not e or e[3] in OPEN
        if by == ay and bx == ax + 1:      # b east of a: b's west edge
            e = sq.get(b)
            return not e or e[4] in OPEN
        if by == ay and bx == ax - 1:
            e = sq.get(a)
            return not e or e[4] in OPEN
        return False

    def standable(p):
        r = sq.get(p)
        return r is not None and r[2] in FLOORS

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
    caves = read_caves()
    n_caves, n_hatches, n_made, n_lairs = 0, 0, 0, 0
    lair = read_lair()
    for path in towns:
        tid = os.path.basename(path)[9:-4]
        sq, furniture, bad = read_town(path)
        check(not bad, "%s: every record is well formed (%s)" % (tid, bad[:3]))
        mine = [s for s in shafts if s["town"] == tid]
        ok_shaft = all(sq.get((s["x"], s["y"]), "  .")[2] == "g" for s in mine)
        ok_ladder = all(sq.get((s["lx"], s["ly"]), "      ")[5] == ("L" if s["edge"] == "N" else "l") for s in mine)
        # From the covers in the street only: a hatch has to be reached, not assumed.
        streets_in = [(s["x"], s["y"]) for s in mine if "hatch" not in s]
        reach = walk(sq, streets_in)
        walkable = [p for p, r in sq.items() if r[2] in FLOORS]
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
        on_floor = all(sq.get((x, y), "  .")[2] in "smv" for x, y, _ in furniture)

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
        # Once: a min() per square was quadratic, and Louisville took minutes.
        mnx, mny, mxx, mxy = min(xs), min(ys), max(xs), max(ys)
        road, keep = gen_sewers.region(mnx, mny, mxx, mxy)
        # Every room, whichever cell's header lists it: region() alone misses a
        # building's half across a cell edge, and the first caves and hatches
        # went under three of them unseen (gen_sewers.room_mask, 0.4).
        keep = keep | gen_sewers.room_mask(mnx, mny, mxx, mxy)
        # Except the squares each hatch declares (the server checks those in
        # game, and opens the hatch only if no random basement is there).
        hatches = [s for s in mine if "hatch" in s]
        declared = {p for s in hatches for p in s["under"]}
        under = [p for p, r in sq.items() if r[2] in "tksgwmnv" and keep[p[1] - mny, p[0] - mnx]
                 and p not in declared]
        check(not under, "%s: no tunnel square under a building or a basement but a hatch's own (%d, e.g. %s)"
              % (tid, len(under), under[:3]))
        umap = gen_sewers.under_map(mnx, mny, mxx, mxy)
        on_map = [p for p in declared if umap[p[1] - mny, p[0] - mnx]]
        ok = all((s["x"], s["y"]) in reach and (s["x"], s["y"]) in s["under"]
                 and keep[s["y"] - mny, s["x"] - mnx] and len(s["under"]) <= gen_sewers.HATCH_UNDER
                 and all(p in sq for p in s["under"]) for s in hatches)
        check(ok and not on_map, "%s: %d hatches, each in a house, reached from a street cover, no more than %d "
              "squares under it, none over the map's own underground (%d)"
              % (tid, len(hatches), gen_sewers.HATCH_UNDER, len(on_map)))
        n_hatches += len(hatches)

        # Covers of ours (the towns the map gives few): each on painted road
        # with nothing else on it, a cover's shaft like any other.
        made = [s for s in mine if s.get("made")]
        if made:
            bad = []
            for s in made:
                c = gen_sewers.clear_road(s["x"] // gen_sewers.CELL, s["y"] // gen_sewers.CELL)
                if not c[s["y"] % gen_sewers.CELL, s["x"] % gen_sewers.CELL]:
                    bad.append((s["x"], s["y"]))
            check(not bad, "%s: %d covers of ours, every one on clear painted road (%d not, e.g. %s)"
                  % (tid, len(made), len(bad), bad[:3]))
            n_made += len(made)

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
                lx, ly = px - mnx, py - mny
                if not (0 <= lx < road.shape[1] and 0 <= ly < road.shape[0]) or not road[ly, lx] \
                        or keep[ly, lx] or (px, py) in near_room or (px, py) in near_shaft:
                    break
                if (px, py) in sq and sq[(px, py)][2] in "tksgw":
                    walled.append((x, y))
                    break
        check(not walled, "%s: no tunnel ends in a wall with the road running on to more tunnel (%d, e.g. %s)"
              % (tid, len(walled), walled[:3]))

        # Caves: each hideout on its own earth, each breach off a tunnel square,
        # and no other way in -- with the breaches walled up again, not one cave
        # square can be walked to.
        mine_caves = [c for c in caves if c["town"] == tid]
        cave_sq = [p for p, r in sq.items() if r[2] == "m"]
        breaches = [p for p, r in sq.items() for col in (3, 4) if r[col] in "oq"]
        ok_hide = all(sq.get((c["x"], c["y"]), "  .")[2] == "m" for c in mine_caves)
        ok_breach = all(sq.get((c["bx"], c["by"]), "  .")[2] in "tk" for c in mine_caves)
        sealed = {p: r[:3] + ("c" if r[3] in "oq" else r[3]) + ("c" if r[4] in "oq" else r[4]) + r[5:]
                  for p, r in sq.items()}
        leak = [p for p in walk(sealed, streets_in) if sq[p][2] == "m"]
        check(len(breaches) == len(mine_caves) and ok_hide and ok_breach and not leak
              and bool(cave_sq) == bool(mine_caves),
              "%s: %d caves, %d cave squares, %d breaches; hideouts on earth %s, breaches off the tunnel %s, "
              "%d cave squares reached without a breach"
              % (tid, len(mine_caves), len(cave_sq), len(breaches), "ok" if ok_hide else "BAD",
                 "ok" if ok_breach else "BAD", len(leak)))
        n_caves += len(mine_caves)

        # The rats' nest: in its town only; its false wall is the only way in
        # from the sewer and the gnawed wall the only way into the hoard --
        # with either shut, what lies behind it cannot be walked to.
        nest_sq = [p for p, r in sq.items() if r[2] in "nv"]
        if lair and lair["town"] == tid:
            n_lairs += 1

            def edges(codes):
                return [(p, col) for p, r in sq.items() for col in (3, 4) if r[col] in codes]
            wall, gate = edges("xy"), edges("z")

            def shut(codes):
                return {p: r[:3] + ("c" if r[3] in codes else r[3]) + ("c" if r[4] in codes else r[4]) + r[5:]
                        for p, r in sq.items()}
            behind_wall = [p for p in walk(shut("xy"), streets_in) if sq[p][2] in "nv"]
            behind_gate = [p for p in walk(shut("z"), streets_in) if sq[p][2] == "v"]
            L = lair
            ok_sides = (sq.get((L["tx"], L["ty"]), "  .")[2] in "tk" and sq.get((L["ex"], L["ey"]), "  .")[2] == "n"
                        and sq.get((L["gx"], L["gy"]), "  .")[2] == "n" and sq.get((L["vx"], L["vy"]), "  .")[2] == "v")
            # Each wall on the north or west edge of the square it is found
            # from (the sewer's, the nest's), where its picture faces the camera.
            ok_sides = ok_sides and ((L["ex"], L["ey"]) in ((L["tx"], L["ty"] - 1), (L["tx"] - 1, L["ty"]))
                                     and (L["vx"], L["vy"]) in ((L["gx"], L["gy"] - 1), (L["gx"] - 1, L["gy"])))
            ok_rous = len(L["rous"]) >= 3 and all(sq.get(p, "  .")[2] == "n" for p in L["rous"])
            hatch = [s for s in mine if "hatch" in s and (s["x"], s["y"]) == (L["hx"], L["hy"])]
            ok_access = bool(hatch) and (L["tx"], L["ty"]) in reach and (L["cx"], L["cy"]) in [(s["x"], s["y"]) for s in mine]
            hoard = [f for f in furniture if sq.get((f[0], f[1]), "  .")[2] == "v"]
            check(len(wall) == 1 and len(gate) == 1 and not behind_wall and not behind_gate and ok_sides and ok_rous
                  and ok_access and len(hoard) >= 6 and all(p in reach for p in nest_sq),
                  "%s: the rats' nest -- %d squares, one false wall (%d) and one gnawed wall (%d); %d behind the "
                  "false wall and %d in the hoard walked to with them shut; sides %s, %d rodents on its floor, "
                  "the hatch %d,%d and cover by it %s, %d pieces in the hoard"
                  % (tid, len(nest_sq), len(wall), len(gate), len(behind_wall), len(behind_gate),
                     "ok" if ok_sides else "BAD", len(L["rous"]) // 1, L["hx"], L["hy"],
                     "ok" if ok_access else "BAD", len(hoard)))
        else:
            check(not nest_sq, "%s: no rats' nest here (%d squares)" % (tid, len(nest_sq)))
    check(n_lairs == 1, "one rats' nest in the world, under %s (%d)" % (lair and lair["town"], n_lairs))
    check(n_hatches >= 30, "houses with a way down, all towns (%d)" % n_hatches)
    check(n_made >= 400, "covers of ours in the towns the map gives few (%d)" % n_made)
    check(n_caves == len(caves) and len(caves) >= 30,
          "every cave in the index is in its town's data (%d of %d)" % (n_caves, len(caves)))
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
