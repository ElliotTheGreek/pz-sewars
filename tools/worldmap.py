"""Draws a piece of the game's own world map -- the one on M -- from the game's own data.

    python tools/worldmap.py temple            # design/art/maps/temple.png
    python tools/worldmap.py nest              # design/art/maps/nest.png

Not a picture of ours that resembles the map: the same features the game
draws (media/maps/Muldraugh, KY/worldmap.xml and worldmap-forest.xml, polygons
per 300-square cell) in the same colours (ISMapDefinitions.lua,
MapUtils.initDefaultStyleV1), with the street names from streets.xml where the
game writes them. So a place marked here is found on the in-game map by
looking, and a mark that is wrong shows as wrong.

Used to check and to show where the temple's trapdoor and the nest's manhole
are (DESIGN.md 7d), and by the annotated maps' generator for their marks.
"""
import math
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pzmap  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "design", "art", "maps")
CELL = 300          # worldmap.xml's cells, in squares (not the 256 of the lot files)

# MapUtils.initDefaultStyleV1, in the order the game lays its layers.
BACKGROUND = (219, 215, 192)
LAYERS = [
    (("natural", "forest"), (189, 197, 163)),
    (("water", "river"), (59, 141, 149)),
    (("highway", "trail"), (185, 122, 87)),
    (("highway", "tertiary"), (171, 158, 143)),
    (("highway", "secondary"), (134, 125, 113)),
    (("highway", "primary"), (134, 125, 113)),
    (("railway", "*"), (200, 191, 231)),
    (("building", "yes"), (210, 158, 105)),
    (("building", "Residential"), (210, 158, 105)),
    (("building", "CommunityServices"), (139, 117, 235)),
    (("building", "Hospitality"), (127, 206, 225)),
    (("building", "Industrial"), (56, 54, 53)),
    (("building", "Medical"), (229, 128, 151)),
    (("building", "RestaurantsAndEntertainment"), (245, 225, 60)),
    (("building", "RetailAndCommercial"), (184, 205, 84)),
]
FONT = r"C:\Windows\Fonts\arialbd.ttf"

_FILES = {}


def cell_features(name, cx, cy):
    """[(properties, [rings of world points])] for one 300-square cell of one of the game's map files."""
    if name not in _FILES:
        s = open(os.path.join(pzmap.MAP, name), encoding="utf-8").read()
        _FILES[name] = {(int(m.group(1)), int(m.group(2))): m.group(3)
                        for m in re.finditer(r'<cell x="(\d+)" y="(\d+)">(.*?)</cell>', s, re.S)}
    body = _FILES[name].get((cx, cy), "")
    out = []
    for f in re.findall(r"<feature>(.*?)</feature>", body, re.S):
        props = set(re.findall(r'<property name="(\w+)" value="([^"]*)"', f))
        rings = [[(cx * CELL + int(x), cy * CELL + int(y)) for x, y in re.findall(r'<point x="(-?\d+)" y="(-?\d+)"', ring)]
                 for ring in re.findall(r"<coordinates>(.*?)</coordinates>", f, re.S)]
        out.append((props, rings))
    return out


def streets():
    import xml.etree.ElementTree as ET
    root = ET.parse(os.path.join(pzmap.MAP, "streets.xml")).getroot()
    return [(st.get("name") or "", [(float(q.get("x")), float(q.get("y"))) for q in st.find("points")])
            for st in root.findall("street")]


def draw(x0, y0, x1, y1, scale=3, names=True):
    """The game's map of a world rectangle, `scale` pixels a square. Returns (image, to_px)."""
    W, H = (x1 - x0) * scale, (y1 - y0) * scale
    img = Image.new("RGB", (W, H), BACKGROUND)
    d = ImageDraw.Draw(img)

    def px(p):
        return ((p[0] - x0) * scale, (p[1] - y0) * scale)
    feats = []
    for cx in range(x0 // CELL, x1 // CELL + 1):
        for cy in range(y0 // CELL, y1 // CELL + 1):
            feats += cell_features("worldmap-forest.xml", cx, cy)
            feats += cell_features("worldmap.xml", cx, cy)
    if not feats:
        raise SystemExit("no map features in %d,%d..%d,%d: the reader has stopped matching" % (x0, y0, x1, y1))
    for key, colour in LAYERS:
        for props, rings in feats:
            if key in props and rings and len(rings[0]) >= 3:
                d.polygon([px(p) for p in rings[0]], fill=colour)
                for hole in rings[1:]:
                    if len(hole) >= 3:
                        d.polygon([px(p) for p in hole], fill=BACKGROUND)
    if names:
        f = ImageFont.truetype(FONT, 4 * scale + 2)
        for name, pts in streets():
            if not name or "Railroad" in name:
                continue
            # At the middle of its longest stretch inside the picture, along it.
            best = None
            for a, b in zip(pts, pts[1:]):
                mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                ln = math.hypot(b[0] - a[0], b[1] - a[1])
                if x0 + 20 < mx < x1 - 20 and y0 + 10 < my < y1 - 10 and (best is None or ln > best[0]):
                    best = (ln, mx, my, a, b)
            if not best or best[0] < 30:
                continue
            _ln, mx, my, a, b = best
            short = name.replace(" (Route 31W)", "")
            tw = int(d.textlength(short, font=f)) + 6
            label = Image.new("RGBA", (tw, 5 * scale + 6), (0, 0, 0, 0))
            ld = ImageDraw.Draw(label)
            ld.text((3, 1), short, font=f, fill=(255, 255, 255, 255), stroke_width=1, stroke_fill=(90, 84, 76, 255))
            ang = math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))
            if ang > 90 or ang <= -90:
                ang += 180
            label = label.rotate(ang, expand=True, resample=Image.BICUBIC)
            cx_, cy_ = px((mx, my))
            img.paste(label, (int(cx_ - label.width / 2), int(cy_ - label.height / 2)), label)
    return img, px


def mark(img, px, at, text, start=None, start_text=None, scale=3):
    """A red ring at `at` with its words; and from `start` (an intersection) the way to it, with the count."""
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, 5 * scale + 3)
    red, ink = (200, 24, 20), (30, 26, 22)
    x, y = px(at)
    if start:
        sx, sy = px(start)
        north, east = start[1] - at[1], at[0] - start[0]
        d.line([sx, sy, sx, y], fill=red, width=3)
        d.line([sx, y, x, y], fill=red, width=3)
        d.ellipse([sx - 7, sy - 7, sx + 7, sy + 7], outline=ink, width=3)
        d.text((sx + 12, sy + 8), start_text, font=f, fill=ink, stroke_width=3, stroke_fill=(255, 255, 255))
        d.text((sx + 10, (sy + y) / 2 - 10), "%d squares %s" % (abs(north), "north" if north > 0 else "south"), font=f,
               fill=red, stroke_width=3, stroke_fill=(255, 255, 255))
        if east:
            d.text((min(sx, x) - 4, y - 5 * scale - 22), "then %d %s" % (abs(east), "east" if east > 0 else "west"),
                   font=f, fill=red, stroke_width=3, stroke_fill=(255, 255, 255))
    r = 14
    d.ellipse([x - r, y - r, x + r, y + r], outline=red, width=5)
    d.line([x - r - 8, y, x + r + 8, y], fill=red, width=2)
    d.line([x, y - r - 8, x, y + r + 8], fill=red, width=2)
    d.text((x + r + 10, y - 12), text, font=f, fill=red, stroke_width=3, stroke_fill=(255, 255, 255))


def index_places():
    """The temple's trapdoor, and the nest's false wall and the manhole nearest it by the tunnels, from the shipped index."""
    s = open(os.path.join(ROOT, "Sewars", "42", "media", "lua", "shared", "SEW", "SEW_Index.lua"), encoding="utf-8").read()
    t = re.search(r"I\.temple=\{[^{]*?tx=(\d+),ty=(\d+)", s)
    n = re.search(r"I\.lair=\{[^{]*?tx=(\d+),ty=(\d+).*?cx=(\d+),cy=(\d+)", s)
    return (int(t.group(1)), int(t.group(2))), (int(n.group(1)), int(n.group(2))), (int(n.group(3)), int(n.group(4)))


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "temple"
    trap, wall, cover = index_places()
    os.makedirs(OUT, exist_ok=True)
    if what == "temple":
        junction = (11531, 8764)          # Frank Road's own line meets Dixie Highway's
        img, px = draw(11380, 8500, 11800, 8980)
        mark(img, px, trap, "TRAPDOOR  %d, %d" % trap, junction, "Frank Road & Dixie Highway")
    elif what == "nest":
        # The manhole on Grenadiers Row; below it the tunnel runs east to
        # Northside Lane and south under it to the false wall, on its west side.
        img, px = draw(13230, 2170, 13450, 2330, scale=6)
        d = ImageDraw.Draw(img)
        (ax, ay), (bx, by), (cx, cy) = px(cover), px((wall[0], cover[1])), px(wall)
        d.line([ax, ay, bx, by, cx, cy], fill=(200, 24, 20), width=4)
        f = ImageFont.truetype(FONT, 26)
        d.text(((ax + bx) / 2 - 90, ay - 40), "below: %d east" % (wall[0] - cover[0]), font=f, fill=(200, 24, 20),
               stroke_width=3, stroke_fill=(255, 255, 255))
        d.text((bx + 14, (by + cy) / 2 - 14), "then %d south" % (wall[1] - cover[1]), font=f, fill=(200, 24, 20),
               stroke_width=3, stroke_fill=(255, 255, 255))
        mark(img, px, cover, "", None, None, scale=5)
        d.text((ax - 60, ay + 22), "MANHOLE  %d, %d" % cover, font=f, fill=(200, 24, 20), stroke_width=3,
               stroke_fill=(255, 255, 255))
        mark(img, px, wall, "FALSE WALL, west side of the tunnel", None, None, scale=5)
    else:
        raise SystemExit(__doc__)
    path = os.path.join(OUT, what + ".png")
    img.save(path)
    print("wrote", path, img.size)


if __name__ == "__main__":
    main()
