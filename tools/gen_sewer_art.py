"""The sewers' own tiles: drawn here, packed into what the game loads.

    python tools/gen_sewer_art.py

Writes

  design/art/tiles/sewars_01.png          the sheet, 8 across, 128x256 a cell (2x)
  design/art/sewer_art_sheet.png          every tile over vanilla's sewer wall and floor, lit dim, to judge
  Sewars/42/media/texturepacks/sewars.pack    PZPK version 1
  Sewars/42/media/sewars.tiles                tdef version 1

and mod.info carries `pack=sewars` and `tiledef=sewars 7462`.

Everything here is drawn procedurally -- stencils, spray paint, grime, water --
and projected onto the game's own geometry, the way pz_trekship draws its
breaker box: an image model has nothing to add to a stencilled EXIT, and the
same script re-draws the whole set when a letter needs moving. The Flowdot and
Gemini passes (DEV_GUIDE, Art) are for the pieces a script cannot paint well.

The projection (pz_trekship tools/isorender.py): a square's north-west corner
sits at (64, 192) of its 128x256 cell, x runs down-right (64, 32) a square,
y down-left (-64, 32), and a storey is 192 px. So a west wall is the face from
(64, 192)-(0, 224) up to (64, 0)-(0, 32), a north wall the face from
(64, 192)-(128, 224) up.

The two ladders are vanilla's own picture (location_sewer_01_32/33) **without
`ladderW`/`ladderN` or `IsMoveAble`**: a vanilla-climbable ladder at z -1
under a solid street is a climb the engine would try and the mod does not
control (pz_trekship strips the same properties from its tiles for the same
reason), and one a player could crowbar off the wall would leave a shaft
nobody can find. *Climb out* is the mod's, validated by the server.
"""
import io
import math
import os
import random
import struct
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tilesheet  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET_PNG = os.path.join(ROOT, "design", "art", "tiles", "sewars_01.png")
REVIEW = os.path.join(ROOT, "design", "art", "sewer_art_sheet.png")
MEDIA = os.path.join(ROOT, "Sewars", "42", "media")
PACK = os.path.join(MEDIA, "texturepacks", "sewars.pack")
TILES = os.path.join(MEDIA, "sewars.tiles")
SHEET = "sewars_01"
TILEDEF_NUMBER = 7462   # the engine accepts 100..8189 (ChooseGameInfo.readModInfoAux); 7461 is the trekship
CW, CH = 128, 256
TW, TH = 256, 384          # a wall face's texture: one square wide, one storey tall, 4x
FONT_STENCIL = r"C:\Windows\Fonts\impact.ttf"
FONT_SPRAY = r"C:\Windows\Fonts\segoeprb.ttf"

# Index -> (name, kind, properties). The Lua (SEW_Config.Sprites) names these by index.
TILES_DEF = [
    ("ladder_W", "copy:location_sewer_01_32", {"attachedW": "", "Facing": "E", "BlocksPlacement": ""}),
    ("ladder_N", "copy:location_sewer_01_33", {"attachedN": "", "Facing": "S", "BlocksPlacement": ""}),
    ("exit_W", "wallW", {"attachedW": ""}),
    ("exit_N", "wallN", {"attachedN": ""}),
]
GRAFFITI = ["keepout", "theyhear", "deeper", "tally", "hands", "up", "eye"]
for g in GRAFFITI:
    TILES_DEF.append(("g_%s_W" % g, "wallW", {"attachedW": ""}))
    TILES_DEF.append(("g_%s_N" % g, "wallN", {"attachedN": ""}))
TILES_DEF += [
    ("safe_W", "wallW", {"attachedW": ""}),
    ("safe_N", "wallN", {"attachedN": ""}),
    ("grime_W", "wallW", {"attachedW": ""}),
    ("grime_N", "wallN", {"attachedN": ""}),
    ("puddle", "floor", {"attachedFloor": ""}),
    ("debris", "floor", {"attachedFloor": ""}),
    ("lightpool", "floor", {"attachedFloor": ""}),
    ("smear", "floor", {"attachedFloor": ""}),
]


# --- projection ------------------------------------------------------------------------------

def to_wall(tex, side):
    """A TWxTH face texture (u across from the N or W end, v down from the top) onto a cell."""
    if side == "W":
        # u runs from the viewer's left (the wall's south end, x 0) to the corner at x 64,
        # so writing reads left to right; the first version ran the other way and every
        # west-wall word came out mirrored (caught on the review sheet).
        coeffs = (TW / 64, 0, 0, TH / 384, TH / 192, -TH / 6)
    else:
        coeffs = (TW / 64, 0, -TW, -TH / 384, TH / 192, TH / 6)
    return tex.transform((CW, CH), Image.AFFINE, coeffs, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))


def to_floor(tex):
    """A square texture (s east, t south) onto the floor diamond."""
    s = tex.size[0]
    coeffs = (s / 128, s / 64, -3.5 * s, -s / 128, s / 64, -2.5 * s)
    return tex.transform((CW, CH), Image.AFFINE, coeffs, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))


# --- paint -----------------------------------------------------------------------------------

def rng_for(name):
    return random.Random(sum(ord(c) * (i + 1) for i, c in enumerate(name)))


def weather(img, rnd, amount=0.35, speck=2):
    """Knocks paint off: speckled alpha loss, heavier toward the bottom."""
    a = img.split()[3]
    noise = Image.effect_noise(img.size, 90).point(lambda v: 255 if v > 128 + amount * 180 else 0)
    noise = noise.filter(ImageFilter.MaxFilter(speck * 2 + 1)) if speck else noise
    from PIL import ImageChops
    a = ImageChops.multiply(a, noise.point(lambda v: 255 if v else int(255 * (1 - amount))))
    img.putalpha(a)
    return img


def spray(text, color, size, rnd, font=FONT_SPRAY, drips=True, angle=0):
    """Spray-painted text on a transparent face texture, centred in the upper middle."""
    tex = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    lines = text.split("\n")
    f = ImageFont.truetype(font, size)
    layer = Image.new("L", (TW, TH), 0)
    d = ImageDraw.Draw(layer)
    y = int(TH * 0.30)
    for line in lines:
        w = d.textlength(line, font=f)
        d.text(((TW - w) / 2 + rnd.randint(-6, 6), y), line, font=f, fill=255)
        y += int(size * 1.05)
    if drips:
        px = layer.load()
        for _ in range(10 + len(text)):
            x = rnd.randint(20, TW - 20)
            col = [yy for yy in range(TH) if px[x, yy] > 200]
            if not col:
                continue
            y0 = max(col)
            for yy in range(y0, min(TH - 1, y0 + rnd.randint(8, 50))):
                for dx in (0, 1):
                    px[min(TW - 1, x + dx), yy] = 230
    if angle:
        layer = layer.rotate(angle, resample=Image.BICUBIC)
    halo = layer.filter(ImageFilter.GaussianBlur(3)).point(lambda v: int(v * 0.35))
    from PIL import ImageChops
    alpha = ImageChops.lighter(layer.filter(ImageFilter.GaussianBlur(0.8)), halo)
    tex.paste(Image.new("RGBA", (TW, TH), color), (0, 0), alpha)
    return weather(tex, rnd, 0.25, 1)


def stencil(text, color, size, rnd, arrow=None, ladder=False):
    tex = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    d = ImageDraw.Draw(tex)
    f = ImageFont.truetype(FONT_STENCIL, size)
    w = d.textlength(text, font=f)
    y = int(TH * 0.36)
    # A dark plate behind the letters, as a municipal stencil is sprayed over a primer square.
    d.rectangle([(TW - w) / 2 - 16, y - 10, (TW + w) / 2 + 16, y + size + 18], fill=(24, 24, 22, 150))
    # Stencil bridges: the letters are cut through by thin gaps.
    d.text(((TW - w) / 2, y), text, font=f, fill=color)
    for gx in range(int((TW - w) / 2), int((TW + w) / 2), max(8, size // 3)):
        d.line([gx, y + size * 0.45, gx + 3, y + size * 0.45], fill=(0, 0, 0, 0), width=3)
    if arrow == "up":
        cx, top = TW // 2, y - 70
        d.polygon([(cx, top), (cx - 26, top + 30), (cx - 9, top + 30), (cx - 9, top + 58),
                   (cx + 9, top + 58), (cx + 9, top + 30), (cx + 26, top + 30)], fill=color)
    if ladder:
        lx, ly = TW // 2 - 14, y + size + 34
        for k in range(5):
            d.line([lx, ly + k * 14, lx + 28, ly + k * 14], fill=color, width=4)
        d.line([lx, ly - 4, lx, ly + 62], fill=color, width=4)
        d.line([lx + 28, ly - 4, lx + 28, ly + 62], fill=color, width=4)
    return weather(tex, rnd, 0.3, 1)


def graffiti(kind, rnd):
    if kind == "keepout":
        return spray("KEEP\nOUT", (170, 26, 22, 235), 64, rnd, angle=-4)
    if kind == "theyhear":
        return spray("THEY\nHEAR\nYOU", (225, 225, 215, 225), 48, rnd, angle=3)
    if kind == "deeper":
        return spray("DONT GO\nDEEPER", (200, 180, 40, 230), 44, rnd, angle=-2)
    if kind == "up":
        tex = spray("UP", (80, 190, 90, 230), 58, rnd, drips=False)
        d = ImageDraw.Draw(tex)
        cx, top = TW // 2, int(TH * 0.14)
        d.polygon([(cx, top), (cx - 30, top + 40), (cx + 30, top + 40)], fill=(80, 190, 90, 220))
        return weather(tex, rnd, 0.2, 1)
    tex = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    d = ImageDraw.Draw(tex)
    if kind == "tally":
        x0, y0 = 40, int(TH * 0.34)
        for g in range(4):
            gx = x0 + g * 48
            for k in range(4):
                d.line([gx + k * 9, y0 + rnd.randint(-3, 3), gx + k * 9 + rnd.randint(-3, 3), y0 + 60],
                       fill=(210, 210, 200, 220), width=4)
            if g < 3:
                d.line([gx - 6, y0 + 50, gx + 34, y0 + 8], fill=(210, 210, 200, 220), width=4)
        f = ImageFont.truetype(FONT_SPRAY, 30)
        d.text((52, y0 + 76), "DAY 31", font=f, fill=(210, 210, 200, 220))
        return weather(tex, rnd, 0.3, 1)
    if kind == "hands":
        for k in range(3):
            hx, hy = 50 + k * 70 + rnd.randint(-10, 10), int(TH * 0.35) + rnd.randint(-30, 50)
            col = (110 + rnd.randint(0, 30), 12, 10, 210)
            d.ellipse([hx - 18, hy - 10, hx + 18, hy + 26], fill=col)
            for fi, (fx, fl) in enumerate(((-16, 26), (-7, 34), (2, 36), (11, 32))):
                d.line([hx + fx, hy - 4, hx + fx + rnd.randint(-3, 3), hy - fl], fill=col, width=8)
            d.line([hx + 16, hy + 8, hx + 30, hy - 6], fill=col, width=8)
            d.line([hx - 8, hy + 26, hx - 10 + rnd.randint(-4, 4), hy + 26 + rnd.randint(20, 60)], fill=col, width=4)
        return weather(tex.filter(ImageFilter.GaussianBlur(0.7)), rnd, 0.35, 1)
    if kind == "eye":
        cx, cy = TW // 2, int(TH * 0.42)
        col = (230, 230, 230, 230)
        d.arc([cx - 80, cy - 60, cx + 80, cy + 60], 200, 340, fill=col, width=8)
        d.arc([cx - 80, cy - 60, cx + 80, cy + 60], 20, 160, fill=col, width=8)
        d.ellipse([cx - 24, cy - 24, cx + 24, cy + 24], fill=(170, 20, 20, 235))
        d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=(10, 10, 10, 255))
        return weather(tex, rnd, 0.25, 1)
    raise ValueError(kind)


def grime(rnd):
    """A tide line at knee height, and streaks running down from the vault."""
    tex = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    d = ImageDraw.Draw(tex)
    tide = int(TH * 0.80) + rnd.randint(-6, 6)
    # Soft and ragged: a hard band one square wide read as a box on the first render.
    for x in range(TW):
        top = tide + int(6 * math.sin(x / 11.0 + rnd.random()))
        for y in range(top, TH):
            a = int(70 * min(1, (y - top) / 40 + 0.2))
            d.point((x, y), fill=(52, 44, 26, a))
    for _ in range(9):
        x = rnd.randint(0, TW)
        length = rnd.randint(60, 260)
        for k in range(length):
            y = k
            a = int(90 * (1 - k / length))
            d.point((x + int(2 * math.sin(k / 9)), y), fill=(38, 40, 28, a))
            d.point((x + 1 + int(2 * math.sin(k / 9)), y), fill=(38, 40, 28, a))
    return tex.filter(ImageFilter.GaussianBlur(1.2))


def floor_tex(kind, rnd):
    s = 256
    tex = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(tex)
    if kind == "puddle":
        blob = Image.new("L", (s, s), 0)
        bd = ImageDraw.Draw(blob)
        for _ in range(6):
            cx, cy = rnd.randint(70, 186), rnd.randint(70, 186)
            r = rnd.randint(35, 70)
            bd.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], fill=255)
        blob = blob.filter(ImageFilter.GaussianBlur(10)).point(lambda v: 210 if v > 110 else int(v * 1.6))
        tex.paste(Image.new("RGBA", (s, s), (22, 30, 24, 255)), (0, 0), blob)
        sheen = Image.new("L", (s, s), 0)
        ImageDraw.Draw(sheen).ellipse([90, 80, 170, 110], fill=70)
        tex.paste(Image.new("RGBA", (s, s), (150, 170, 160, 255)), (0, 0),
                  Image.composite(sheen.filter(ImageFilter.GaussianBlur(12)), Image.new("L", (s, s), 0), blob))
        return tex
    if kind == "debris":
        for _ in range(26):
            x, y = rnd.randint(20, s - 20), rnd.randint(20, s - 20)
            c = rnd.choice([(58, 46, 30, 230), (80, 72, 58, 230), (140, 132, 110, 220), (40, 40, 38, 230)])
            if rnd.random() < 0.5:
                d.ellipse([x, y, x + rnd.randint(6, 16), y + rnd.randint(4, 10)], fill=c)
            else:
                d.polygon([(x, y), (x + rnd.randint(8, 22), y + rnd.randint(-6, 6)),
                           (x + rnd.randint(2, 12), y + rnd.randint(6, 16))], fill=c)
        for _ in range(3):   # a bone or two
            x, y = rnd.randint(40, s - 60), rnd.randint(40, s - 40)
            d.line([x, y, x + 34, y + 10], fill=(214, 206, 180, 235), width=5)
            d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(214, 206, 180, 235))
            d.ellipse([x + 29, y + 5, x + 39, y + 15], fill=(214, 206, 180, 235))
        return tex
    if kind == "lightpool":
        g = Image.new("L", (s, s), 0)
        gd = ImageDraw.Draw(g)
        for r in range(120, 0, -2):
            gd.ellipse([s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r], fill=int(200 * (1 - r / 120) ** 1.2))
        # The cover's holes, a ring of brighter spots.
        for k in range(8):
            a = k * math.pi / 4
            x, y = s / 2 + 40 * math.cos(a), s / 2 + 40 * math.sin(a)
            gd.ellipse([x - 7, y - 7, x + 7, y + 7], fill=230)
        tex.paste(Image.new("RGBA", (s, s), (205, 215, 225, 255)), (0, 0), g.filter(ImageFilter.GaussianBlur(4)))
        return tex
    if kind == "smear":
        for k in range(40):
            t = k / 40
            x, y = 50 + t * 150, 120 + 30 * math.sin(t * 3) + rnd.randint(-3, 3)
            r = 14 * (1 - t) + 3
            d.ellipse([x - r, y - r * 0.6, x + r, y + r * 0.6], fill=(84, 10, 8, int(200 * (1 - t * 0.6))))
        return tex.filter(ImageFilter.GaussianBlur(1.5))
    raise ValueError(kind)


def draw(name, kind, rnd, vanilla):
    if kind.startswith("copy:"):
        return vanilla[kind[5:]]
    side = kind[-1] if kind.startswith("wall") else None
    base = name.rsplit("_", 1)[0]
    if base == "exit":
        tex = stencil("EXIT", (232, 196, 40, 240), 64, rnd, arrow="up", ladder=True)
    elif base == "safe":
        tex = spray("SAFE\nKNOCK 3", (90, 200, 110, 235), 46, rnd, angle=2)
    elif base == "grime":
        tex = grime(rnd)
    elif base.startswith("g_"):
        tex = graffiti(base[2:], rnd)
    else:
        return to_floor(floor_tex(name, rnd))
    return to_wall(tex, side)


# --- the formats (as pz_trekship's gen_adirondack_pack.py writes and reads them) -------------

def write_tiledefs(path, tilesets):
    out = io.BytesIO()
    out.write(b"tdef")
    out.write(struct.pack("<ii", 1, len(tilesets)))
    for ts in tilesets:
        out.write((ts["name"] + "\n").encode("latin1"))
        out.write((ts["image"] + "\n").encode("latin1"))
        out.write(struct.pack("<iiii", ts["cols"], ts["rows"], ts["id"], len(ts["tiles"])))
        for props in ts["tiles"]:
            out.write(struct.pack("<i", len(props)))
            for k, v in props:
                out.write(("%s\n%s\n" % (k, v)).encode("latin1"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(out.getvalue())


def read_tiledefs(path):
    b = open(path, "rb").read()
    o = 12
    n = struct.unpack_from("<i", b, 8)[0]
    out = {}

    def i32():
        nonlocal o
        v = struct.unpack_from("<i", b, o)[0]
        o += 4
        return v

    def line():
        nonlocal o
        e = b.index(b"\n", o)
        v = b[o:e].decode("latin1")
        o = e + 1
        return v

    for _ in range(n):
        name, img = line(), line()
        cols, rows, tid, count = i32(), i32(), i32(), i32()
        out[name] = dict(image=img, cols=cols, rows=rows, id=tid,
                         tiles=[dict((line(), line()) for _ in range(i32())) for _ in range(count)])
    if o != len(b):
        raise SystemExit("%s: read %d of %d bytes" % (path, o, len(b)))
    return out


def write_pack(path, pages):
    out = io.BytesIO()
    out.write(b"PZPK")

    def i32(v):
        out.write(struct.pack("<i", v))

    def s(v):
        v = v.encode("latin1")
        i32(len(v))
        out.write(v)

    i32(1)
    i32(len(pages))
    for pg in pages:
        s(pg["name"])
        i32(len(pg["entries"]))
        i32(1)
        for name, vals in pg["entries"]:
            s(name)
            for v in vals:
                i32(v)
        buf = io.BytesIO()
        pg["image"].save(buf, "PNG", optimize=True)
        i32(len(buf.getvalue()))
        out.write(buf.getvalue())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(out.getvalue())


def pack_pages(items, page=2048):
    items = sorted(items, key=lambda t: -t[1].height)
    pages, pg, x, y, shelf = [], None, 0, 0, 0
    for name, img, ox, oy in items:
        w, h = img.size
        if pg is None or x + w > page:
            x, y, shelf = 0, y + shelf, 0
        if pg is None or y + h > page:
            pg = dict(name="sewars%d" % len(pages), image=Image.new("RGBA", (page, page)), entries=[])
            pages.append(pg)
            x, y, shelf = 0, 0, 0
        pg["image"].paste(img, (x, y))
        pg["entries"].append((name, [x, y, w, h, ox, oy, CW, CH]))
        x += w + 1
        shelf = max(shelf, h + 1)
    for p in pages:
        box = p["image"].getbbox()
        if box:
            p["image"] = p["image"].crop((0, 0, page, box[3]))
    return pages


# --- vanilla pictures ------------------------------------------------------------------------

def vanilla_cells(names):
    found = {}
    for p in sorted(os.listdir(tilesheet.PACKS)):
        if not p.startswith("Tiles2x") or not p.endswith(".pack"):
            continue
        for pg in tilesheet.read_pack(os.path.join(tilesheet.PACKS, p)):
            hit = [e for e in pg["entries"] if e[0] in names and e[0] not in found]
            if not hit:
                continue
            img = Image.open(io.BytesIO(pg["png"])).convert("RGBA")
            for name, (x, y, w, h, ox, oy, fw, fh) in hit:
                cell = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
                cell.alpha_composite(img.crop((x, y, x + w, y + h)), (ox, oy))
                found[name] = cell.resize((CW, CH)) if cell.size != (CW, CH) else cell
    missing = set(names) - set(found)
    if missing:
        raise SystemExit("vanilla tiles not found in the packs: %s" % ", ".join(sorted(missing)))
    return found


def review(cells, vanilla):
    """Each tile standing where it will: on vanilla's sewer wall and floor, in the dark."""
    wallW, wallN = vanilla["location_sewer_01_8"], vanilla["location_sewer_01_9"]
    floor = vanilla["floors_interior_tilesandwood_01_24"]
    cols = 8
    rows = (len(cells) + cols - 1) // cols
    out = Image.new("RGBA", (cols * CW, rows * (CH + 16)), (12, 12, 14, 255))
    d = ImageDraw.Draw(out)
    for i, ((name, kind, _), cell) in enumerate(zip(TILES_DEF, cells)):
        X, Y = (i % cols) * CW, (i // cols) * (CH + 16)
        base = Image.new("RGBA", (CW, CH), (12, 12, 14, 255))
        base.alpha_composite(floor)
        if name.endswith("_W") or name == "ladder_W":
            base.alpha_composite(wallW)
        elif name.endswith("_N") or name == "ladder_N":
            base.alpha_composite(wallN)
        base.alpha_composite(cell)
        # Dim, as it will be read by torchlight.
        dim = Image.eval(base.convert("RGB"), lambda v: int(v * 0.72)).convert("RGBA")
        out.alpha_composite(dim, (X, Y + 16))
        d.text((X + 2, Y + 2), "%d %s" % (i, name), fill=(255, 220, 0))
    os.makedirs(os.path.dirname(REVIEW), exist_ok=True)
    out.save(REVIEW)


def main():
    vanilla = vanilla_cells({"location_sewer_01_32", "location_sewer_01_33", "location_sewer_01_8",
                             "location_sewer_01_9", "floors_interior_tilesandwood_01_24"})
    cells = []
    for name, kind, _ in TILES_DEF:
        cells.append(draw(name, kind, rng_for(name), vanilla))
    rows = (len(cells) + 7) // 8
    sheet = Image.new("RGBA", (8 * CW, rows * CH), (0, 0, 0, 0))
    for i, c in enumerate(cells):
        sheet.alpha_composite(c, ((i % 8) * CW, (i // 8) * CH))
    os.makedirs(os.path.dirname(SHEET_PNG), exist_ok=True)
    sheet.save(SHEET_PNG)

    tiles = [sorted(p.items()) for _, _, p in TILES_DEF] + [[] for _ in range(rows * 8 - len(TILES_DEF))]
    write_tiledefs(TILES, [dict(name=SHEET, image=SHEET + ".png", cols=8, rows=rows, id=1, tiles=tiles)])
    items = []
    for i, c in enumerate(cells):
        box = c.split()[3].getbbox()
        if not box:
            raise SystemExit("tile %d (%s) drew nothing" % (i, TILES_DEF[i][0]))
        items.append(("%s_%d" % (SHEET, i), c.crop(box), box[0], box[1]))
    write_pack(PACK, pack_pages(items))

    back = read_tiledefs(TILES)
    got = tilesheet.read_pack(PACK)
    named = sum(len(p["entries"]) for p in got)
    if named != len(items):
        raise SystemExit("pack round trip lost sprites: %d of %d" % (named, len(items)))
    review(cells, vanilla)
    print("sewars_01: %d tiles, pack %d KB on %d page(s); tiledef %d (%s)"
          % (len(items), os.path.getsize(PACK) // 1024, len(got), TILEDEF_NUMBER,
             ", ".join("%d=%s" % (i, n) for i, (n, _, _) in enumerate(TILES_DEF))))
    if list(back) != [SHEET]:
        raise SystemExit("tiledef round trip: %s" % list(back))


if __name__ == "__main__":
    main()
