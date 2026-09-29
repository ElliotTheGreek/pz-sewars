"""Reads the vanilla map: where the roads are, where the manholes are.

    python tools/pzmap.py census                         # manholes and sewer tiles, whole map
    python tools/pzmap.py town 10540 9300 11000 10300 design/art/map_muldraugh.png

The sewers follow the streets above them (DESIGN.md 3), so the layout starts
from the real map, read off disk. This parses the two files every map cell is
made of --

  <x>_<y>.lotheader      "LOTH", int version, the tile names used (one per
                         line), int width, height, min and max level, then
                         the rooms (name, level, rectangles, objects) and the
                         buildings (lists of room indices)
  world_<x>_<y>.lotpack  "LOTP", int version, int chunk count, then a table of
                         8-byte chunk offsets; per chunk, per level, per square
                         (x outer, y inner): an int count, -1 and a skip, or a
                         room id and count-1 tile indices

-- the reader is pz_trekship's tools/fieldstation_site.py, which took the
format out of IsoMetaGrid$MetaGridLoaderThread.loadCell and IsoLot.load with
tools/javadis.py. Cells are 256 squares, chunks 8.
"""
import collections
import glob
import os
import re
import struct
import sys

MAP = os.environ.get("PZ_MAP", r"C:/Program Files (x86)/Steam/steamapps/common/ProjectZomboid/media/maps/Muldraugh, KY")
CELL = 256

# What a manhole and a road are, by sprite. Checked against the tile sheet by
# eye (design/art/vanilla_street_tiles.png): street_decoration_01_15 is the
# round cast-iron cover; 13, 14 and 30-31 are the kerb storm drains.
MANHOLE = "street_decoration_01_15"
DRAINS = ("street_decoration_01_13", "street_decoration_01_14",
          "street_decoration_01_30", "street_decoration_01_31")
ROAD = ("blends_street_01", "floors_exterior_street_01")


def header(cx, cy):
    b = open(os.path.join(MAP, "%d_%d.lotheader" % (cx, cy)), "rb").read()
    if b[:4] != b"LOTH":
        raise SystemExit("%d_%d.lotheader is not a version-1 header" % (cx, cy))
    p = 8
    n = struct.unpack_from("<i", b, p)[0]
    p += 4
    tiles = []
    for _ in range(n):
        e = b.index(b"\n", p)
        tiles.append(b[p:e].decode("latin1").strip())
        p = e + 1
    _w, _h, lo, hi = struct.unpack_from("<iiii", b, p)
    return tiles, lo, hi


def rooms(cx, cy):
    """Every room of one cell: [(name, level, [(x, y, w, h), ...])], in world squares."""
    b = open(os.path.join(MAP, "%d_%d.lotheader" % (cx, cy)), "rb").read()
    p = 8
    n = struct.unpack_from("<i", b, p)[0]
    p += 4
    for _ in range(n):
        p = b.index(b"\n", p) + 1
    p += 16

    def i32():
        nonlocal p
        v = struct.unpack_from("<i", b, p)[0]
        p += 4
        return v

    def line():
        nonlocal p
        e = b.index(b"\n", p)
        v = b[p:e].decode("latin1")
        p = e + 1
        return v

    out = []
    for _ in range(i32()):
        name, level = line(), i32()
        rects = [(i32() + cx * CELL, i32() + cy * CELL, i32(), i32()) for _ in range(i32())]
        for _ in range(i32()):
            i32(), i32(), i32()
        out.append((name, level, rects))
    return out


def cell_squares(cx, cy, z=0):
    """Every square of one cell at level z: {(x, y): [tile names]}."""
    return cell_levels(cx, cy, want=lambda lz: lz == z).get(z, {})


def cell_levels(cx, cy, want=lambda lz: True):
    """Every square of one cell, by level, in one pass: {z: {(x, y): [tiles]}}."""
    tiles, lo, hi = header(cx, cy)
    out = collections.defaultdict(dict)
    b = open(os.path.join(MAP, "world_%d_%d.lotpack" % (cx, cy)), "rb").read()
    base = 8 if b[:4] == b"LOTP" else 0
    for idx in range(32 * 32):
        wx, wy = cx * 32 + idx // 32, cy * 32 + idx % 32
        p = struct.unpack_from("<i", b, base + 4 + idx * 8)[0]
        skip = 0
        for lz in range(max(lo, -32), min(hi, 31) + 1):
            for i in range(8):
                for j in range(8):
                    if skip > 0:
                        skip -= 1
                        continue
                    c = struct.unpack_from("<i", b, p)[0]
                    p += 4
                    if c == -1:
                        skip = struct.unpack_from("<i", b, p)[0] - 1
                        p += 4
                        continue
                    if c > 1:
                        p += 4
                        if want(lz):
                            out[lz][(wx * 8 + i, wy * 8 + j)] = [
                                tiles[struct.unpack_from("<i", b, p + 4 * k)[0]] for k in range(c - 1)]
                        p += 4 * (c - 1)
    return out


def cells():
    for h in glob.glob(os.path.join(MAP, "*.lotheader")):
        m = re.match(r"(\d+)_(\d+)\.lotheader$", os.path.basename(h))
        if m:
            yield int(m.group(1)), int(m.group(2)), h


def census():
    levels = collections.Counter()
    manholes, drains, sewer_z = [], 0, collections.Counter()
    for cx, cy, h in cells():
        raw = open(h, "rb").read()
        _, lo, hi = header(cx, cy)
        levels[lo] += 1
        if MANHOLE.encode() not in raw and b"location_sewer_01" not in raw:
            continue
        for z in range(lo, hi + 1):
            for (x, y), ts in cell_squares(cx, cy, z).items():
                for t in ts:
                    if t.startswith("location_sewer_01"):
                        sewer_z[z] += 1
                    elif z == 0 and t == MANHOLE:
                        manholes.append((x, y))
                    elif z == 0 and t in DRAINS:
                        drains += 1
    print("cells by lowest level:", sorted(levels.items()))
    print("manhole covers at street level:", len(manholes))
    print("storm drains at street level:  ", drains)
    print("location_sewer_01 tiles by z:  ", sorted(sewer_z.items()))
    if not manholes:
        raise SystemExit("no manholes found: the sprite name or the reader has stopped matching")


def town(x0, y0, x1, y1, png=None):
    road, holes = set(), []
    for cx in range(x0 // CELL, x1 // CELL + 1):
        for cy in range(y0 // CELL, y1 // CELL + 1):
            if not os.path.exists(os.path.join(MAP, "%d_%d.lotheader" % (cx, cy))):
                continue
            for (x, y), ts in cell_squares(cx, cy).items():
                if not (x0 <= x <= x1 and y0 <= y <= y1):
                    continue
                if any(t.startswith(ROAD) for t in ts):
                    road.add((x, y))
                if MANHOLE in ts:
                    holes.append((x, y))
    print("road squares:", len(road), " manholes:", len(holes))
    for h in sorted(holes):
        print("  manhole", h)
    if len(road) < 100:
        raise SystemExit("fewer than 100 road squares: wrong box, or the road sprites stopped matching")
    if png:
        from PIL import Image
        im = Image.new("RGB", (x1 - x0 + 1, y1 - y0 + 1), (18, 18, 22))
        px = im.load()
        for x, y in road:
            px[x - x0, y - y0] = (90, 90, 96)
        for x, y in holes:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if 0 <= x - x0 + dx <= x1 - x0 and 0 <= y - y0 + dy <= y1 - y0:
                        px[x - x0 + dx, y - y0 + dy] = (255, 200, 0)
        os.makedirs(os.path.dirname(os.path.abspath(png)), exist_ok=True)
        im.save(png)
        print("wrote", png)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["census"]:
        census()
    elif a[:1] == ["town"] and len(a) >= 5:
        town(*map(int, a[1:5]), png=a[5] if len(a) > 5 else None)
    else:
        print(__doc__)
