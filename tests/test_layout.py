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
  * the temple (tools/gen_temple.py): one in the world, in chunks of its own,
    walked to from the street covers of two different towns by the passages
    the cult dug and from the trapdoor in the field over it, and by no other
    way; its pictures on walls, its lights and its dead on its floors;
  * the records are well formed.
"""
import glob
import os
import re
import sys
from collections import deque

import numpy as np
from scipy import ndimage as ndi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "Sewars", "42", "media", "lua")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_sewers  # noqa: E402

FAILS = []
REC = re.compile(r'^[0-7][0-7][.tksgwrmnvphaq][.cbdejoqxyzOQ][.cbdejoqxyzOQ][.LlPQ][.peabcdefghijklnouvxyz]$')
FLOORS = "tksgmnvphaq"  # stood on (m: a cave's earth; n: the rats' nest and its run; v: their hoard;
                        # p: a passage the cult dug; h a q: the temple's stone, carpet and boards)
OPEN = ".djoqxyzOQ"   # edges walked through: none, a door frame (a locked grille: with its key), a breach,
                      # the nest's walls once opened, the cult's breaches
TEMPLE = "phaq"


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
        sh["outfall"] = ",outfall=true" in line
        sh["trapdoor"] = ",trapdoor=true" in line
        shafts.append(sh)
    shelters = [dict(zip(("town", "kind", "x", "y", "w", "h"), (m[0], m[1]) + tuple(int(v) for v in m[2:])))
                for m in re.findall(r'H\[#H\+1\]=\{town="(\w+)",kind="(\w+)",x=(\d+),y=(\d+),w=(\d+),h=(\d+)\}', s)]
    return shafts, shelters


def read_temple():
    """The temple's entry in the index, or None."""
    s = open(os.path.join(LUA, "shared", "SEW", "SEW_Index.lua"), encoding="utf-8").read()
    m = re.search(r'I\.temple=\{town="(\w+)",([^{]*)lights=\{([\d,]*)\},breaches=\{(.*)\}\}', s)
    if not m:
        return None
    T = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', m[2])}
    T["town"] = m[1]
    v = [int(n) for n in m[3].split(",") if n]
    T["lights"] = list(zip(v[0::2], v[1::2]))
    T["breaches"] = [dict(town=b[0], **{k: int(n) for k, n in re.findall(r'(\w+)=(\d+)', b[1])})
                     for b in re.findall(r'\{town="(\w+)",([^}]*)\}', m[4])]
    return T


def read_pictures(path):
    """[(x, y, sprite)] from a town's pictures table."""
    s = open(path, encoding="utf-8").read()
    out = []
    for body in re.findall(r'^h\["-?\d+,-?\d+"\]=\{(.*)\}$', s, re.M):
        out += [(int(x), int(y), spr) for x, y, spr in re.findall(r'\{(\d+),(\d+),"([^"]+)"\}', body)]
    return out


def read_dead(path):
    """[(x, y, outfit)] from a town's claimed tables."""
    s = open(path, encoding="utf-8").read()
    out = []
    for body in re.findall(r'^[zu]\["-?\d+,-?\d+"\]=\{(.*)\}$', s, re.M):
        out += [(int(x), int(y), o) for x, y, o in re.findall(r'\{(\d+),(\d+),"(\w+)"', body)]
    return out


def read_warren():
    """The warren's entry in the index, or None: dens [(x, y, r)], lights [(x, y)]."""
    s = open(os.path.join(LUA, "shared", "SEW", "SEW_Index.lua"), encoding="utf-8").read()
    m = re.search(r'I\.warren=\{town="(\w+)",dens=\{([\d,]*)\},lights=\{([\d,]*)\}\}', s)
    if not m:
        return None
    d = [int(n) for n in m[2].split(",") if n]
    v = [int(n) for n in m[3].split(",") if n]
    return dict(town=m[1], dens=list(zip(d[0::3], d[1::3], d[2::3])), lights=list(zip(v[0::2], v[1::2])))


def read_journals():
    """Every journal in the index, in order: [{town, x, y, kind, text}]."""
    s = open(os.path.join(LUA, "shared", "SEW", "SEW_Index.lua"), encoding="utf-8").read()
    return [dict(town=m[0], x=int(m[1]), y=int(m[2]), kind=m[3], text=m[4]) for m in
            re.findall(r'J\[#J\+1\]=\{town="(\w+)",x=(\d+),y=(\d+),kind="(\w+)",text="(\w+)"', s)]


def read_table(path, letter):
    """[(x, y, name, rest)] from one of a town's tables of {x, y, "name", ...}."""
    s = open(path, encoding="utf-8").read()
    out = []
    for body in re.findall(r'^%s\["-?\d+,-?\d+"\]=\{(.*)\}$' % letter, s, re.M):
        out += [(int(x), int(y), n, rest) for x, y, n, rest in re.findall(r'\{(\d+),(\d+),"([^"]+)"([^}]*)\}', body)]
    return out


def read_gas():
    s = open(os.path.join(LUA, "shared", "SEW", "SEW_Index.lua"), encoding="utf-8").read()
    return [dict(town=m[0], id=m[1], x=int(m[2]), y=int(m[3]), n=int(m[4]))
            for m in re.findall(r'G\[#G\+1\]=\{town="(\w+)",id="(\w)",x=(\d+),y=(\d+),n=(\d+)\}', s)]


def read_gates():
    """({town: key id}, [gates]) from the index."""
    s = open(os.path.join(LUA, "shared", "SEW", "SEW_Index.lua"), encoding="utf-8").read()
    keys = {m[0]: int(m[1]) for m in re.findall(r'I\.towns\["(\w+)"\] = \{[^}]*key = (\d+) \}', s)}
    gates = [dict(town=m[0], x=int(m[1]), y=int(m[2]), edge=m[3])
             for m in re.findall(r'K\[#K\+1\]=\{town="(\w+)",x=(\d+),y=(\d+),edge="([NW])"\}', s)]
    return keys, gates


def read_town_keys(path):
    s = open(path, encoding="utf-8").read()
    out = []
    for body in re.findall(r'k\["-?\d+,-?\d+"\]=\{(.*)\}', s):
        out += [(int(x), int(y)) for x, y in re.findall(r'\{(\d+),(\d+)\}', body)]
    return out


def read_town_gas(path):
    """({(x, y): stretch id}, [(x, y, edge)]) from a town's g and p tables."""
    s = open(path, encoding="utf-8").read()
    gas = {}
    for cx, cy, body in re.findall(r'g\["(-?\d+),(-?\d+)"\]="([^"]*)"', s):
        for i in range(0, len(body), 3):
            gas[(int(cx) * 8 + int(body[i]), int(cy) * 8 + int(body[i + 1]))] = body[i + 2]
    signs = [(int(x), int(y), e) for x, y, e in re.findall(r'\{(\d+),(\d+),"([NW])"\}', s)]
    return gas, signs


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
    # A sprite, by its name: one of the temple's dead is written {x, y, "Cultist", fx, fy}.
    furniture = [(int(x), int(y), spr) for x, y, spr in re.findall(r'\{(\d+),(\d+),"([^"]+_\d+)",', s)]
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


def temple_checks(T, world, shafts, shelters, pictures, dead):
    """The temple (tools/gen_temple.py), over every town's squares at once:
    its passages cross from one town's chunks into its own."""
    check(T is not None and len(T["breaches"]) >= 2, "the index has the temple, and its passages (%s)"
          % (T and len(T["breaches"])))
    if not T:
        return
    own = [p for p, r in world.items() if r[2] in "haq"]
    dug = [p for p, r in world.items() if r[2] == "p"]
    check(len(own) >= 1500 and len(dug) >= 100, "the temple: %d squares of floor, %d squares of passage"
          % (len(own), len(dug)))
    idol = (T["x"], T["y"])
    trap = [s for s in shafts if s.get("trapdoor")]
    check(len(trap) == 1 and (trap[0]["x"], trap[0]["y"]) == (T["tx"], T["ty"]) and trap[0]["town"] == T["town"]
          and world.get((T["tx"], T["ty"]), "  .")[2] == "g",
          "one trapdoor, the temple's, over a ladder at %d,%d" % (T["tx"], T["ty"]))
    # Under open ground: nothing built, no road, no water over the trapdoor.
    R = 4
    water, ground = gen_sewers.water_region(T["tx"] - R, T["ty"] - R, T["tx"] + R, T["ty"] + R)
    road, keep = gen_sewers.region(T["tx"] - R, T["ty"] - R, T["tx"] + R, T["ty"] + R)
    check(bool(ground[R, R]) and not road[R, R] and not keep[R, R], "the trapdoor opens in a field: natural ground, "
          "no road, nothing built")
    towns = sorted({b["town"] for b in T["breaches"]})
    check(len(towns) == len(T["breaches"]) and T["town"] not in towns,
          "each passage breaks into a different town's sewer (%s)" % ", ".join(towns))
    edges = [(p, col) for p, r in world.items() for col in (3, 4) if r[col] in "OQ"]
    ok_edges = True
    for b in T["breaches"]:
        a, e = (b["tx"], b["ty"]), (b["ex"], b["ey"])
        holder = (max(a[0], e[0]), max(a[1], e[1]))
        col = 3 if a[0] == e[0] else 4
        ok_edges &= (world.get(a, "  .")[2] == "t" and world.get(e, "  .")[2] == "p"
                     and world.get(holder, "       ")[col] in "OQ" and abs(a[0] - e[0]) + abs(a[1] - e[1]) == 1)
    check(len(edges) == len(T["breaches"]) and ok_edges,
          "%d breaches, each between a plain square of sewer and the first square of a passage" % len(edges))
    # From the street covers of each town alone, and from the trapdoor alone:
    # the idol. With the breaches and the trapdoor shut: nothing of the cult's.
    street = {t: [(s["x"], s["y"]) for s in shafts if s["town"] == t and "hatch" not in s and not s.get("trapdoor")]
              for t in towns}
    for t in towns:
        reach = walk(world, street[t])
        check(idol in reach, "from %s's street covers, down its sewer and the cult's passage: the idol" % t)
    reach = walk(world, [(T["tx"], T["ty"])])
    lost = [p for p in own + dug if p not in reach]
    check(idol in reach and not lost, "from the trapdoor: the idol, and every square of the temple and its passages "
          "(%d not)" % len(lost))
    sealed = {p: r[:3] + ("c" if r[3] in "OQ" else r[3]) + ("c" if r[4] in "OQ" else r[4]) + r[5:]
              for p, r in world.items()}
    leak = [p for p in walk(sealed, [q for t in towns for q in street[t]]) if world[p][2] in TEMPLE]
    check(not leak, "with the breaches walled up again, nothing of the cult's is walked to from a sewer (%d)" % len(leak))
    # Its rooms, on its own floors; the hall the biggest.
    rooms = [h for h in shelters if h["kind"].startswith("temple_")]
    off = [h["kind"] for h in rooms if any(world.get((x, y), "  .")[2] not in "haqg"
                                           for x in (h["x"], h["x"] + h["w"] - 1) for y in (h["y"], h["y"] + h["h"] - 1))]
    hall = next((h for h in rooms if h["kind"] == "temple_hall"), None)
    check(len(rooms) >= 10 and not off and hall is not None and hall["x"] <= idol[0] < hall["x"] + hall["w"]
          and hall["y"] <= idol[1] < hall["y"] + hall["h"],
          "the temple's %d rooms are on its floors, and the idol stands in its hall (%s off)" % (len(rooms), off))
    # Pictures on a wall of ours, on the edge they are painted for; lights and the dead on floor.
    bad = []
    for tid, x, y, spr in pictures:
        i = int(spr.rsplit("_", 1)[1])
        north = (i % 2 == 1) if i <= 55 else True          # W, N pairs; the triptych is north only
        r = world.get((x, y))
        if not r or r[2] not in FLOORS or r[3 if north else 4] not in "cbe":
            bad.append((x, y, spr))
    check(len(pictures) >= 40 and not bad, "%d pictures of the cult's, each on a wall on its own edge (%s)"
          % (len(pictures), bad[:3]))
    dark = [p for p in T["lights"] if world.get(p, "  .")[2] not in TEMPLE]
    # What each place says of the other: the temple's writings mark the nest's
    # false wall and the house with the way down to it; the warren's mark the
    # temple's trapdoor and where each passage breaks into a sewer.
    J = {j["text"]: j for j in read_journals()}
    L = read_lair()
    to_nest = all(J.get(k) and (J[k]["x"], J[k]["y"], J[k]["town"]) == (L["tx"], L["ty"], L["town"])
                  for k in ("cult_1", "cult_2", "cult_3"))
    way = J.get("cult_4") and (J["cult_4"]["x"], J["cult_4"]["y"]) == (L["hx"], L["hy"])
    back = J.get("warren_1") and (J["warren_1"]["x"], J["warren_1"]["y"], J["warren_1"]["town"]) == (T["tx"], T["ty"], T["town"])
    holes = {(b["tx"], b["ty"], b["town"]) for b in T["breaches"]}
    found = {(J[k]["x"], J[k]["y"], J[k]["town"]) for k in ("warren_2", "warren_3") if J.get(k)}
    check(bool(to_nest and way and back) and found == holes,
          "the two places tell of each other: the temple's writings mark the nest and the house by it, the warren's "
          "the temple's trapdoor and both breaches")
    check(len(T["lights"]) >= 30 and not dark, "%d lights, each on the cult's floor (%s)" % (len(T["lights"]), dark[:3]))
    cult = [(x, y) for tid, x, y, o in dead if o == "Cultist"]
    astray = [p for p in cult if world.get(p, "  .")[2] not in "haq"]
    check(len(cult) >= 15 and not astray, "%d of the cult's dead, each on the temple's floor (%s)"
          % (len(cult), astray[:3]))


def main():
    shafts, shelters = read_index()
    check(len(shafts) > 400, "the index lists the shafts (%d)" % len(shafts))
    towns = sorted(glob.glob(os.path.join(LUA, "server", "SEW", "Data", "SEW_Town_*.lua")))
    check(len(towns) >= 10, "towns generated (%d)" % len(towns))
    total_walk, total_stranded = 0, 0
    caves = read_caves()
    n_caves, n_hatches, n_made, n_lairs, n_gas, n_gates, n_outfalls = 0, 0, 0, 0, 0, 0, 0
    lair = read_lair()
    temple = read_temple()
    world, pictures_all, dead_all = {}, [], []
    gas_index = read_gas()
    town_keys, gates_index = read_gates()
    for path in towns:
        tid = os.path.basename(path)[9:-4]
        sq, furniture, bad = read_town(path)
        check(not bad, "%s: every record is well formed (%s)" % (tid, bad[:3]))
        clash = [p for p in sq if p in world]
        check(not clash, "%s: no square of it is another town's too (%d)" % (tid, len(clash)))
        world.update(sq)
        pictures_all += [(tid,) + q for q in read_pictures(path)]
        dead_all += [(tid,) + q for q in read_dead(path)]
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
        # The temple's rooms are named on the map like shelters, and are not: a
        # hall has as many doors as it needs. They are checked with the temple.
        rooms = [h for h in shelters if h["town"] == tid and not h["kind"].startswith("temple_")]
        one_door = True
        for h in rooms:
            doors = 0
            for x in range(h["x"] - 1, h["x"] + h["w"] + 1):
                for y in range(h["y"] - 1, h["y"] + h["h"] + 1):
                    r = sq.get((x, y))
                    if r and ("d" in (r[3], r[4]) or "j" in (r[3], r[4])):
                        doors += (r[3] in "dj") + (r[4] in "dj")
            one_door &= doors == 1
        on_floor = all(sq.get((x, y), "  .")[2] in "smvn" + TEMPLE for x, y, _ in furniture)

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
        under = [p for p, r in sq.items() if r[2] in "tksgwmnv" + TEMPLE and keep[p[1] - mny, p[0] - mnx]
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
        made = [s for s in mine if s.get("made") and not s.get("outfall") and not s.get("trapdoor")]
        if made:
            bad = []
            for s in made:
                c = gen_sewers.clear_road(s["x"] // gen_sewers.CELL, s["y"] // gen_sewers.CELL)
                if not c[s["y"] % gen_sewers.CELL, s["x"] % gen_sewers.CELL]:
                    bad.append((s["x"], s["y"]))
            check(not bad, "%s: %d covers of ours, every one on clear painted road (%d not, e.g. %s)"
                  % (tid, len(made), len(bad), bad[:3]))
            n_made += len(made)

        # Outfalls (DESIGN.md 7c): each grate on dry natural ground beside a
        # body of water big enough not to be a pool, and walked to from a
        # street cover -- a way out, not a pocket of its own.
        outfalls = [s for s in mine if s.get("outfall")]
        if outfalls:
            covers = walk(sq, [(s["x"], s["y"]) for s in mine if "hatch" not in s and not s.get("outfall")])
            bad = []
            for s in outfalls:
                # The water round it, wide: a lake cut off at the edge of the
                # tunnels' extent would count as a pond (the first run of this).
                R = 300
                water, ground = gen_sewers.water_region(s["x"] - R, s["y"] - R, s["x"] + R, s["y"] + R)
                lab, _ = ndi.label(water)
                sizes = np.bincount(lab.ravel())
                lx, ly = R, R
                wet = [lab[ly + dy, lx + dx] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
                if not (ground[ly, lx] and any(w and sizes[w] >= gen_sewers.OUTFALL_WATER for w in wet)
                        and (s["x"], s["y"]) in covers and sq.get((s["x"], s["y"]), "  .")[2] == "g"):
                    bad.append((s["x"], s["y"]))
            check(not bad, "%s: %d outfalls, every grate on dry ground by big water and walked to from a street "
                  "cover (%d not, e.g. %s)" % (tid, len(outfalls), len(bad), bad[:3]))
            n_outfalls += len(outfalls)

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
            # The warren (0.6): dens dug off the nest, nest to the walker -- so
            # the false wall is still the only way to any of them (above) -- each
            # with a cache of its own, the dead and the relics on its earth, and
            # the three writings that point at the temple.
            Wn = read_warren()
            check(Wn is not None and Wn["town"] == tid and len(Wn["dens"]) >= gen_sewers.WARREN_MIN,
                  "%s: the warren, %s dens off the nest" % (tid, Wn and len(Wn["dens"])))
            if Wn:
                caches = read_table(path, "w")
                wdead = read_table(path, "d")

                def den_of(x, y):
                    return next((i for i, (dx, dy, r) in enumerate(Wn["dens"])
                                 if abs(x - dx) <= r + 1 and abs(y - dy) <= r + 1), None)
                crates = [c for c in caches if c[2].startswith(("carpentry", "constructedobjects"))]
                stocked = {den_of(x, y) for x, y, _n, rest in crates if rest.split(",")[1] != "nil"}
                def gap(a, b):
                    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
                apart = all(gap(a, b) >= a[2] + b[2] + 3 for i, a in enumerate(Wn["dens"]) for b in Wn["dens"][i + 1:])
                far = all(gap(d, (L["x"], L["y"])) >= gen_sewers.LAIR_NEST_R + d[2] + 3 for d in Wn["dens"])
                check(apart and far and all(sq.get((dx, dy), "  .")[2] == "n" and (dx, dy) in reach for dx, dy, _r in Wn["dens"]),
                      "%s: each den is its own round of earth, apart from the nest and from the others, and walked to" % tid)
                check(None not in stocked and len(stocked) == len(Wn["dens"]) and len(crates) >= 8
                      and all(sq.get((x, y), "  .")[2] == "n" for x, y, _n, _r in caches),
                      "%s: a cache in every den (%d crates in %d dens), every piece on its earth"
                      % (tid, len(crates), len(stocked)))
                where = {(x, y) for x, y, _n, _r in caches}
                check(len(wdead) >= 4 and all(sq.get((x, y), "  .")[2] == "n" and den_of(x, y) is not None
                                              and (x, y) not in where for x, y, _n, _r in wdead)
                      and {"Cultist", "Sanitation"} <= {n for _x, _y, n, _r in wdead},
                      "%s: %d dead in the dens -- the cult's pilgrims and a county crew -- none on a crate" % (tid, len(wdead)))
                relics = [c for c in caches if c[2].startswith("sewars_01_")]
                check(len(relics) >= 6 and len(Wn["lights"]) >= 2 and all(p in where for p in Wn["lights"]),
                      "%s: %d relics on the dens' floors, %d candles lit" % (tid, len(relics), len(Wn["lights"])))
                J = read_journals()
                extras = [rest.split(",")[2].strip('"') for _x, _y, _n, rest in crates]
                slots = [int(e[1:]) for e in extras if e.startswith("j")]
                check("m1" in extras, "%s: and a map of the way to the temple, in the pilgrims' den" % tid)
                texts = sorted(J[i - 1]["text"] for i in slots)
                check(texts == ["warren_1", "warren_2", "warren_3"],
                      "%s: three writings left in the dens' caches (%s)" % (tid, texts))
        else:
            check(not nest_sq, "%s: no rats' nest here (%d squares)" % (tid, len(nest_sq)))

        # Sewer gas (DESIGN.md 7b): only on plain walkway, never near a street ladder,
        # every placard on a wall of ours on its edge, and the index agrees.
        gas, signs = read_town_gas(path)
        mine_gas = [g for g in gas_index if g["town"] == tid]
        ladders = [(s["x"], s["y"]) for s in mine if "hatch" not in s]
        off_walk = [p for p in gas if sq.get(p, "  .")[2] != "t"]
        by_ladder = [p for p in gas if any(max(abs(p[0] - a), abs(p[1] - b)) <= gen_sewers.GAS_CLEAR
                                           for a, b in ladders)]
        bad_sign = [(x, y, e) for x, y, e in signs
                    if sq.get((x, y), "  .")[2] not in "tkg" or sq[(x, y)][3 if e == "N" else 4] not in "cb"]
        ids = set(gas.values())
        agree = (len(ids) == len(mine_gas)
                 and all(gas.get((g["x"], g["y"])) == g["id"] and sum(1 for v in gas.values() if v == g["id"]) == g["n"]
                         for g in mine_gas))
        signed = all(any(abs(x - a) + abs(y - b) <= 1 for x, y, _ in signs for (a, b), v in gas.items() if v == i)
                     for i in ids)
        check(not off_walk and not by_ladder and not bad_sign and agree and signed,
              "%s: %d stretches of gas, %d squares, %d placards: off plain walkway %d, within %d of a ladder %d, "
              "placards off a wall %d, index agrees %s, every stretch signed %s"
              % (tid, len(ids), len(gas), len(signs), len(off_walk), gen_sewers.GAS_CLEAR, len(by_ladder),
                 len(bad_sign), agree, signed))
        n_gas += len(ids)

        # Locked gates (DESIGN.md 7, Locked gates): every j edge is the door of a county room,
        # a town has gates only if it has a key, and then every unlocked county
        # room's first crate holds it -- and there is at least one.
        gate_edges = [(p, col) for p, r in sq.items() for col in (3, 4) if r[col] == "j"]
        mine_gates = [g for g in gates_index if g["town"] == tid]

        def room_of(p):
            return next((h for h in rooms if h["x"] <= p[0] < h["x"] + h["w"] and h["y"] <= p[1] < h["y"] + h["h"]), None)
        county_doors = True
        for (x, y), col in gate_edges:
            other = (x, y - 1) if col == 3 else (x - 1, y)
            h = room_of((x, y)) or room_of(other)
            county_doors &= h is not None and h["kind"] in ("maintenance", "pump")
        key_spots = read_town_keys(path)
        crates = {(x, y) for x, y, _ in furniture}
        unlocked_county = [h for h in rooms if h["kind"] in ("maintenance", "pump")
                           and not any(room_of((x, y)) is h or room_of((x, y - 1) if col == 3 else (x - 1, y)) is h
                                       for (x, y), col in gate_edges)]
        keyed = all(any(h["x"] <= kx < h["x"] + h["w"] and h["y"] <= ky < h["y"] + h["h"] for kx, ky in key_spots)
                    for h in unlocked_county)
        ok = (county_doors and len(mine_gates) == len(gate_edges)
              and (tid in town_keys) == bool(gate_edges)
              and (not gate_edges or (key_spots and keyed and all(k in crates for k in key_spots)))
              and all(sq.get(k, "  .")[2] == "s" for k in key_spots))
        check(ok, "%s: %d locked gates, all on county rooms %s, key %s, the key in %d crates of unlocked county rooms"
              % (tid, len(gate_edges), county_doors, town_keys.get(tid, "none"), len(key_spots)))
        n_gates += len(gate_edges)
    temple_checks(temple, world, shafts, shelters, pictures_all, dead_all)
    check(n_gas == len(gas_index) and n_gas >= 50,
          "every stretch of gas in the index is in its town's data (%d of %d)" % (n_gas, len(gas_index)))
    check(n_gates == len(gates_index) and n_gates >= 30 and len(town_keys) >= 10
          and len(set(town_keys.values())) == len(town_keys) and all(k >= 100000000 for k in town_keys.values()),
          "locked gates, all towns: %d (the index lists %d); %d towns with a key, every key its own and clear of "
          "vanilla's ids" % (n_gates, len(gates_index), len(town_keys)))
    check(n_outfalls >= 10, "storm-drain outfalls, all towns (%d)" % n_outfalls)
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
    shut = {p: r[:3] + ("c" if r[3] in "dj" else r[3]) + ("c" if r[4] in "dj" else r[4]) + r[5:] for p, r in sq.items()}
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
