"""Compares two generated layouts: what a save built from the old one would see move.

    python tools/layout_diff.py OLD_DIR              # OLD_DIR against the layout in the tree
    python tools/layout_diff.py OLD_DIR NEW_DIR

A layout directory holds SEW_Index.lua and Data/SEW_Town_*.lua, as the tree
does under Sewars/42/media/lua/{shared/SEW,server/SEW}. Copy the tree's pair
aside before regenerating, then run this.

DEV_GUIDE, *The street list is not the road*: before shipping any layout
change, shafts, shelters, journals, plans, caves, the nest and every piece of
furniture must be identical unless moving them is the point -- a save has
built them, stocked them and pointed journals at them. This prints what moved
and exits 1 if any of those did. New squares are fine (a later pass adds
them); an existing square whose record changed is listed by field, because a
revision pass rebuilds hull only and never dressing or doors.
"""
import collections
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "Sewars", "42", "media", "lua")
FIELDS = ("x", "y", "floor", "north wall", "west wall", "fixture", "dressing")


def read(d):
    """(index lines by kind, squares {(x, y): record}, furniture lines by table)."""
    idx_path = os.path.join(d, "SEW_Index.lua")
    if not os.path.exists(idx_path):
        idx_path = os.path.join(d, "shared", "SEW", "SEW_Index.lua")
    data = os.path.join(d, "Data")
    if not os.path.isdir(data):
        data = os.path.join(d, "server", "SEW", "Data")
    index = collections.defaultdict(list)
    for line in open(idx_path, encoding="utf-8"):
        line = line.strip()
        m = re.match(r"^(S\[|H\[|J\[|P\[|V\[|I\.lair|I\.towns)", line)
        if m:
            index[m.group(1)].append(line)
    squares, furn = {}, collections.defaultdict(set)
    for path in sorted(glob.glob(os.path.join(data, "SEW_Town_*.lua"))):
        tid = os.path.basename(path)[9:-4]
        for line in open(path, encoding="utf-8"):
            m = re.match(r'c\["(-?\d+),(-?\d+)"\]="([^"]*)"', line)
            if m:
                cx, cy, body = int(m[1]), int(m[2]), m[3]
                for i in range(0, len(body), 7):
                    r = body[i:i + 7]
                    squares[(cx * 8 + int(r[0]), cy * 8 + int(r[1]))] = r
                continue
            m = re.match(r'(\w)\["(-?\d+,-?\d+)"\]=\{(.*)\}$', line.strip())
            if m and m[1] != "c":
                for item in re.findall(r"\{[^{}]*\}", m[3]):
                    furn[m[1]].add((tid, item))
    return index, squares, furn


NAMES = {"S[": "shafts", "H[": "shelters", "J[": "journals", "P[": "plans", "V[": "caves",
         "I.lair": "the rats' nest", "I.towns": "towns"}
TABLES = {"f": "shelter furniture", "z": "shelter dead", "v": "cave and hoard furniture", "u": "cave dead"}
# Towns may grow (a larger map box); everything else that a save holds must not move.
MUST_HOLD = ("S[", "H[", "J[", "P[", "V[", "I.lair")
# Named in saves by index (a shelter found, a journal or plan item's mod data,
# a cave by number): appended to, never reordered.
ORDERED = ("H[", "J[", "P[", "V[")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    old = read(sys.argv[1])
    new = read(sys.argv[2] if len(sys.argv) > 2 else LUA)
    bad = False
    for k, name in NAMES.items():
        o, n = old[0][k], new[0][k]
        if k in ORDERED:
            # Saves name these by their place in the list: the old list must be
            # the start of the new one, in order.
            gone = [line for i, line in enumerate(o) if i >= len(n) or n[i] != line]
            came = n[len(o):] if not gone else [line for line in n if line not in set(o)]
        else:
            gone, came = set(o) - set(n), set(n) - set(o)
        if gone or came:
            held = k in MUST_HOLD and gone
            bad |= bool(held)
            print("%-6s %-16s %d gone, %d new%s" % ("MOVED" if held else "", name, len(gone), len(came),
                                                    ("  e.g. " + sorted(gone)[0][:110]) if gone else ""))
        else:
            print("       %-16s identical (%d)" % (name, len(n)))
    for k, name in TABLES.items():
        gone, came = old[2][k] - new[2][k], new[2][k] - old[2][k]
        bad |= bool(gone)
        print("%-6s %-16s %s" % ("MOVED" if gone else "", name, "%d gone, %d new" % (len(gone), len(came))
                                 if gone or came else "identical (%d)" % len(new[2][k])))
    os_, ns = old[1], new[1]
    removed = [p for p in os_ if p not in ns]
    added = [p for p in ns if p not in os_]
    changed = collections.Counter()
    examples = {}
    for p, r in os_.items():
        n = ns.get(p)
        if n and n != r:
            for i in range(2, 7):
                if r[i] != n[i]:
                    key = "%s %s->%s" % (FIELDS[i], r[i], n[i])
                    changed[key] += 1
                    examples.setdefault(key, p)
    print("squares: %d in the old, %d in the new: %d added, %d removed, %d changed"
          % (len(os_), len(ns), len(added), len(removed), sum(1 for p in os_ if p in ns and ns[p] != os_[p])))
    for key, n in changed.most_common(40):
        print("    %6d  %s  (e.g. %d,%d)" % (n, key, examples[key][0], examples[key][1]))
    if removed:
        print("    removed, e.g. %s" % removed[:5])
    print()
    print("nothing a save holds has moved" if not bad else "SOMETHING A SAVE HOLDS HAS MOVED")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
