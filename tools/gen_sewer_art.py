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

# What every tile of ours that lies on the floor carries. `RenderLayer=Floor`
# is what puts a placed object in the floor pass: FBORenderCell
# .isObjectRenderLayer_Floor is `solidfloor or renderLayer == 1`, and
# IsoWorld.LoadTileDefinitions sets renderLayer 1 from RenderLayer=Floor.
# Without it a puddle is drawn in the object pass, over whoever walks across
# it (a player's report on a dedicated server, 0.3.1). Vanilla's own decals
# never need it: the map loads them as part of the floor, not as objects.
FLOOR_DECAL = {"attachedFloor": "", "RenderLayer": "Floor"}
# And every tile of ours on a wall. A sprite of ours has no depth texture, so
# IsoSprite.setupTileDepth gives it the wall's depth only for `WallOverlay`
# with attachedW / attachedN (bci 560-661); otherwise the default depth, and
# it can be drawn over a character beside the wall (the same report).
WALL_W = {"attachedW": "", "WallOverlay": ""}
WALL_N = {"attachedN": "", "WallOverlay": ""}
# A thing of ours that stands on its square: it blocks the square the way
# vanilla's statues and furniture do, and can be seen and shot past.
STANDING = {"solidtrans": "", "BlocksPlacement": ""}
# The raws the image model painted for the cult (DEV_GUIDE, Art: keep the raw),
# each on a flat key colour that `keyed` measures rather than assumes.
CULT = os.path.join(ROOT, "design", "art", "cult")

# Index -> (name, kind, properties). The Lua (SEW_Config.Sprites) names these by index.
TILES_DEF = [
    ("ladder_W", "copy:location_sewer_01_32", dict(WALL_W, Facing="E", BlocksPlacement="")),
    ("ladder_N", "copy:location_sewer_01_33", dict(WALL_N, Facing="S", BlocksPlacement="")),
    ("exit_W", "wallW", WALL_W),
    ("exit_N", "wallN", WALL_N),
]
GRAFFITI = ["keepout", "theyhear", "deeper", "tally", "hands", "up", "eye"]
for g in GRAFFITI:
    TILES_DEF.append(("g_%s_W" % g, "wallW", WALL_W))
    TILES_DEF.append(("g_%s_N" % g, "wallN", WALL_N))
TILES_DEF += [
    ("safe_W", "wallW", WALL_W),
    ("safe_N", "wallN", WALL_N),
    ("grime_W", "wallW", WALL_W),
    ("grime_N", "wallN", WALL_N),
    ("puddle", "floor", FLOOR_DECAL),
    ("debris", "floor", FLOOR_DECAL),
    ("lightpool", "floor", FLOOR_DECAL),
    ("smear", "floor", FLOOR_DECAL),
    # Vanilla's sludge (location_sewer_01_26) is drawn 128 px up its cell -- a
    # water line two thirds of a storey above its square, for a channel one
    # level below the walkway. Laid on our walkway it floated up against the
    # wall, over squares that looked like floor and would not let you on
    # (found in play, 0.3.2). This is its picture put down on the floor
    # diamond, still solidtrans: the channel is crossed by its bridges.
    ("sludge", "lower:location_sewer_01_26", dict(FLOOR_DECAL, BlocksPlacement="", solidtrans="")),
    # Caves (ROADMAP 0.4). Earth: vanilla has no such wall, and a wall of ours
    # would have no depth texture (drawn over characters). So the wall is
    # vanilla's concrete one -- its collision, its depth -- and this is the
    # earth face laid over it (SEW_Build). earth_NW is not placed: a corner is
    # vanilla's corner with both faces over it.
    ("earth_W", "wallW", WALL_W),
    ("earth_N", "wallN", WALL_N),
    ("earth_NW", "corner:earth", WALL_W),
    # Breaches: over vanilla's door frame (location_sewer_01_18/19, walked
    # through, with its depth), vanilla's wall with a hole knocked through it,
    # the hole cut inside the frame's own doorway so the frame never shows.
    ("breach_c_W", "breach:location_sewer_01_8", WALL_W),
    ("breach_c_N", "breach:location_sewer_01_9", WALL_N),
    ("breach_b_W", "breach:location_sewer_01_0", WALL_W),
    ("breach_b_N", "breach:location_sewer_01_1", WALL_N),
    # Houses with a way down (ROADMAP 0.4): a trapdoor in a house's floor, laid
    # over the floor the house has. No property that blocks or can be picked up.
    ("hatch", "floor", FLOOR_DECAL),
    # A manhole cover of ours, for the towns the map gives few (ROADMAP 0.4):
    # vanilla's own picture, but as a floor tile -- vanilla's sprite placed as
    # an object would be drawn over whoever stands on it.
    ("cover", "copyfloor:street_decoration_01_15", FLOOR_DECAL),
    # The rats' nest under Louisville (0.5). The false wall's tell: loose
    # brickwork cracked round a gnawed hole at its foot, hung on the wall it
    # is part of until it is pulled away.
    ("cracks_W", "wallW", WALL_W),
    ("cracks_N", "wallN", WALL_N),
    # Gouges from claws the size of a hand, on the nest's earth and the wall
    # they have gnawed half through into the hoard.
    ("claws_W", "wallW", WALL_W),
    ("claws_N", "wallN", WALL_N),
    # The nest's floor: bones, and the litter they sleep in.
    ("bones", "floor", FLOOR_DECAL),
    ("litter", "floor", FLOOR_DECAL),
    # Somebody's warning, a few squares from the false wall.
    ("g_rous_W", "wallW", WALL_W),
    ("g_rous_N", "wallN", WALL_N),
    # Sewer gas (ROADMAP 0.5): the county's placard at the way into a gassy
    # stretch, and the haze lying on its floor.
    ("gas_W", "wallW", WALL_W),
    ("gas_N", "wallN", WALL_N),
    ("haze", "floor", FLOOR_DECAL),
    # Storm-drain outfalls (ROADMAP 0.4; DESIGN.md 7c): the grate at the top of
    # an outfall's ladder, set into a riverbank -- a concrete apron with iron
    # bars over the dark, laid on the ground the bank has.
    ("outfall", "floor", FLOOR_DECAL),
    # The temple of the rat cult (ROADMAP 0.6; DESIGN.md 7d). On walls, hung
    # like every picture of ours: their sigil, their creed, a lit sconce, a
    # banner, and the triptych behind the idol (a north wall, three squares).
    ("sigil_W", "wallW", WALL_W),
    ("sigil_N", "wallN", WALL_N),
    ("burrow_W", "wallW", WALL_W),
    ("burrow_N", "wallN", WALL_N),
    ("torch_W", "wallW", WALL_W),
    ("torch_N", "wallN", WALL_N),
    ("banner_W", "wallW", WALL_W),
    ("banner_N", "wallN", WALL_N),
    ("mural0_N", "wallN", WALL_N),
    ("mural1_N", "wallN", WALL_N),
    ("mural2_N", "wallN", WALL_N),
    # Standing: the idol and a brazier. Each fills its square and nobody walks
    # through it (solidtrans, as vanilla's own statues), so the default depth
    # the engine gives a tile of ours never has a character to be wrong about.
    ("idol", "prop", STANDING),
    ("brazier", "prop", STANDING),
    # Low, and walked past in the cult's one-wide passages: drawn in the floor
    # pass, under whoever stands there, like every decal of ours.
    ("candles", "floor", FLOOR_DECAL),
    # The circle round the slab: one drawing, three squares by three, row by
    # row from its north-west square.
    ("circle0", "floor", FLOOR_DECAL), ("circle1", "floor", FLOOR_DECAL), ("circle2", "floor", FLOOR_DECAL),
    ("circle3", "floor", FLOOR_DECAL), ("circle4", "floor", FLOOR_DECAL), ("circle5", "floor", FLOOR_DECAL),
    ("circle6", "floor", FLOOR_DECAL), ("circle7", "floor", FLOOR_DECAL), ("circle8", "floor", FLOOR_DECAL),
    # What was left for the Great Ones: a bowl, small skulls, coins.
    ("offering", "floor", FLOOR_DECAL),
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
    if kind == "rous":
        tex = spray("R.O.U.S.", (196, 40, 30, 235), 50, rnd, angle=-3)
        tex.alpha_composite(spray("\n\nTHEY EXIST", (225, 220, 205, 225), 27, rnd, drips=False, angle=1))
        return tex
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


def earth(rnd):
    """A dug face: packed brown earth in rough strata, stones bedded in it, roots
    near the top, the bottom dark with damp, and a ragged top edge where the
    digging stopped."""
    import numpy as np
    h, w = TH, TW
    ys = np.linspace(0, 1, h)[:, None]
    base = np.array([92, 70, 48], float) * (1 - ys * 0.35)[..., None] * np.ones((h, w, 1))
    # Strata: wavy bands a shade apart.
    xs = np.arange(w)[None, :]
    band = np.sin((np.arange(h)[:, None] + 7 * np.sin(xs / 23.0 + rnd.random() * 6)) / 17.0)
    base *= (1 + 0.07 * band)[..., None]
    grain = Image.effect_noise((w, h), 60).filter(ImageFilter.GaussianBlur(1.2))
    base *= (0.82 + 0.36 * np.asarray(grain, float) / 255)[..., None]
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(img)
    for _ in range(26):
        x, y = rnd.randint(4, w - 4), rnd.randint(30, h - 10)
        r = rnd.randint(4, 13)
        g = rnd.randint(88, 128)
        d.ellipse([x - r, y - r * 0.7, x + r, y + r * 0.7], fill=(g, g - 6, g - 16, 255))
        d.arc([x - r, y - r * 0.7, x + r, y + r * 0.7], 200, 320, fill=(g + 40, g + 34, g + 22, 255), width=2)
        d.arc([x - r, y - r * 0.7, x + r, y + r * 0.7], 20, 150, fill=(40, 30, 22, 255), width=2)
    for _ in range(5):          # roots
        x, y = rnd.randint(10, w - 10), rnd.randint(20, 90)
        for k in range(rnd.randint(20, 60)):
            nx, ny = x + rnd.randint(-3, 3), y + rnd.randint(1, 3)
            d.line([x, y, nx, ny], fill=(46, 32, 20, 255), width=2)
            x, y = nx, ny
    for _ in range(8):          # pick marks
        x, y = rnd.randint(10, w - 30), rnd.randint(60, h - 40)
        d.line([x, y, x + rnd.randint(8, 22), y + rnd.randint(-4, 10)], fill=(50, 36, 24, 255), width=3)
    # Damp at the foot.
    a = img.split()
    damp = Image.linear_gradient("L").resize((w, h)).point(lambda v: int(max(0, v - 170) * 1.6))
    img = Image.composite(Image.new("RGBA", (w, h), (30, 24, 18, 255)), img, damp)
    # Opaque to the top: it lies over vanilla's concrete wall, and a ragged
    # top let the concrete show through (the first overlay sheet).
    img.putalpha(255)
    del a
    return img


def breach(cell, side, rnd, frame):
    """Vanilla's own wall with a hole knocked through it: a ragged arch from the
    floor to two thirds up, its edge broken and dark. What came out of it lies
    on the floor either side (loose stones, placed by the builder).

    Laid over vanilla's door frame `frame` (which gives it collision and
    depth), so the hole is kept inside the frame's doorway: everywhere else
    this picture covers the frame, and inside the hole the frame is empty."""
    import numpy as np
    from scipy import ndimage as ndi
    doorway = (np.asarray(cell.split()[3]) > 0) & (np.asarray(frame.split()[3]) == 0)
    # Ragged: a few pixels in from the doorway's edge, by a wandering amount.
    depth = ndi.distance_transform_edt(doorway)
    wobble = np.asarray(Image.effect_noise((CW, CH), 60).filter(ImageFilter.GaussianBlur(3)), float)
    inside = depth > 1.5 + 5 * np.clip((wobble - 100) / 60, 0, 1)
    hole = Image.new("L", (TW, TH), 0)
    hd = ImageDraw.Draw(hole)
    pts = []
    cx, left, right, top = TW / 2, TW * 0.1, TW * 0.9, TH * 0.24
    n = 26
    for k in range(n + 1):
        a = math.pi * k / n            # left foot, over the top, right foot
        x = cx - (cx - left) * math.cos(a) + rnd.randint(-9, 9)
        # A round, broken top rather than a pointed arch (the first sheet).
        y = TH - (TH - top) * max(0.0, math.sin(a)) ** 0.35 + rnd.randint(-12, 12)
        pts.append((x, min(TH, y)))
    pts = [(left + rnd.randint(-4, 4), TH)] + pts + [(right + rnd.randint(-4, 4), TH)]
    hd.polygon(pts, fill=255)
    rim = hole.filter(ImageFilter.MaxFilter(19))
    from PIL import ImageChops
    rim = ImageChops.subtract(rim, hole).filter(ImageFilter.GaussianBlur(2))

    def project(m):
        rgba = Image.new("RGBA", (TW, TH), (255, 255, 255, 0))
        rgba.putalpha(m)
        return to_wall(rgba, side).split()[3]
    ph = Image.fromarray(((np.asarray(project(hole)) > 127) & inside).astype(np.uint8) * 255, "L")
    pr = Image.fromarray(np.asarray(ph.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(2))), "L")
    pr = ImageChops.subtract(pr, ph)
    out = cell.copy()
    r, g, b, a = out.split()
    a = ImageChops.multiply(a, ImageChops.invert(ph))
    dark = pr.point(lambda v: 255 - int(v * 0.55))
    r, g, b = (ImageChops.multiply(ch, dark) for ch in (r, g, b))
    return Image.merge("RGBA", (r, g, b, a))


def cracks(rnd):
    """Loose brickwork: a gnawed hole at the wall's foot, dark inside with a
    ragged, lighter rim, and cracks running up from it through the mortar,
    a few bricks round it outlined where the mortar has gone."""
    tex = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    d = ImageDraw.Draw(tex)
    cx, foot = TW // 2 + rnd.randint(-20, 20), TH
    for row in range(5):
        y0 = TH - 40 - row * 30
        off = 0 if row % 2 else 32
        for bx in range(-2, 3):
            x0 = cx - 64 + bx * 64 + off
            if rnd.random() < 0.55:
                d.rectangle([x0 + 2, y0, x0 + 60, y0 + 26], outline=(18, 14, 12, 210), width=3)
    for _ in range(7):
        x, y = cx + rnd.randint(-40, 40), TH - 60
        for _k in range(rnd.randint(8, 16)):
            nx, ny = x + rnd.randint(-16, 16), y - rnd.randint(8, 20)
            d.line([x, y, nx, ny], fill=(14, 12, 10, 230), width=rnd.choice((2, 3, 3, 4)))
            x, y = nx, ny
    w, h = 68, 56
    rim = [(cx - w // 2 - 10 + rnd.randint(-4, 4), foot)]
    hole = [(cx - w // 2, foot)]
    for k in range(13):
        a = math.pi * k / 12
        rx, ry = math.cos(a), math.sin(a)
        rim.append((cx - (w // 2 + 10) * rx + rnd.randint(-5, 5), foot - (h + 10) * ry + rnd.randint(-5, 5)))
        hole.append((cx - (w // 2) * rx + rnd.randint(-4, 4), foot - h * ry + rnd.randint(-4, 4)))
    rim.append((cx + w // 2 + 10, foot))
    hole.append((cx + w // 2, foot))
    d.polygon(rim, fill=(120, 100, 84, 230))
    d.polygon(hole, fill=(6, 5, 5, 255))
    for _ in range(14):       # gnaw marks round the rim
        a = rnd.uniform(0.1, math.pi - 0.1)
        x, y = cx - (w // 2 + 5) * math.cos(a), foot - (h + 5) * math.sin(a)
        d.line([x, y, x + rnd.randint(-5, 5), y + rnd.randint(3, 9)], fill=(40, 30, 24, 240), width=2)
    return weather(tex, rnd, 0.12, 1)


def claws(rnd):
    """Three or four gouges together, pale in the middle and dark along their
    lips; two or three sets across the face at different heights."""
    tex = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    d = ImageDraw.Draw(tex)
    for _set in range(rnd.randint(2, 3)):
        x0, y0 = rnd.randint(30, TW - 110), rnd.randint(int(TH * 0.35), int(TH * 0.8))
        ang = rnd.uniform(-0.5, 0.5)
        length = rnd.randint(70, 130)
        for k in range(rnd.randint(3, 4)):
            sx, sy = x0 + k * 18, y0 + k * 4
            ex, ey = sx + length * math.sin(ang), sy + length * math.cos(ang) * 0.9
            d.line([sx - 2, sy, ex - 2, ey], fill=(22, 16, 12, 230), width=7)
            d.line([sx, sy, ex, ey], fill=(176, 160, 138, 235), width=3)
    return weather(tex, rnd, 0.1, 1)


def placard(rnd):
    """The county's warning, screwed to the wall at chest height: a yellow
    enamel plate, a black hazard triangle with a skull-less exclamation, and
    DANGER / SEWER GAS / MASK REQUIRED in stencil capitals. Rust at the
    screws, paint chipped off the edges."""
    tex = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    d = ImageDraw.Draw(tex)
    x0, y0, x1, y1 = 34, int(TH * 0.20), TW - 34, int(TH * 0.70)
    d.rectangle([x0 + 4, y0 + 6, x1 + 4, y1 + 6], fill=(10, 10, 8, 120))             # its shadow
    d.rectangle([x0, y0, x1, y1], fill=(214, 172, 36, 245), outline=(28, 26, 20, 255), width=5)
    cx, top = TW // 2, y0 + 18
    d.polygon([(cx, top), (cx - 40, top + 66), (cx + 40, top + 66)], fill=(24, 22, 18, 255))
    d.polygon([(cx, top + 14), (cx - 28, top + 58), (cx + 28, top + 58)], fill=(214, 172, 36, 255))
    d.rectangle([cx - 4, top + 26, cx + 4, top + 46], fill=(24, 22, 18, 255))
    d.ellipse([cx - 4, top + 50, cx + 4, top + 56], fill=(24, 22, 18, 255))
    f = ImageFont.truetype(FONT_STENCIL, 38)
    fs = ImageFont.truetype(FONT_STENCIL, 22)
    for text, font, y in (("DANGER", f, top + 72), ("SEWER GAS", fs, top + 116), ("MASK REQUIRED", fs, top + 142)):
        w = d.textlength(text, font=font)
        d.text(((TW - w) / 2, y), text, font=font, fill=(24, 22, 18, 255))
    for sx, sy in ((x0 + 12, y0 + 12), (x1 - 12, y0 + 12), (x0 + 12, y1 - 12), (x1 - 12, y1 - 12)):
        d.ellipse([sx - 5, sy - 5, sx + 5, sy + 5], fill=(90, 52, 26, 255))
        for _ in range(3):                  # rust run down from the screw
            d.line([sx, sy, sx + rnd.randint(-2, 2), sy + rnd.randint(8, 26)], fill=(110, 58, 26, 170), width=2)
    return weather(tex, rnd, 0.18, 1)


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
    if kind == "hatch":
        # A trapdoor cut into the floor: planks in a dark frame, two iron
        # straps, a ring to pull it by.
        m = 34
        d.rectangle([m - 8, m - 8, s - m + 8, s - m + 8], fill=(34, 26, 18, 255))
        boards = 4
        bw = (s - 2 * m) / boards
        for k in range(boards):
            x0 = m + k * bw
            tone = rnd.randint(-10, 10)
            d.rectangle([x0 + 2, m, x0 + bw - 2, s - m], fill=(112 + tone, 80 + tone, 50 + tone, 255))
            for _ in range(5):          # grain
                gx = x0 + rnd.uniform(6, bw - 6)
                d.line([gx, m + 4, gx + rnd.uniform(-3, 3), s - m - 4], fill=(90 + tone, 62 + tone, 38 + tone, 255), width=1)
        for sy in (m + 26, s - m - 26):  # iron straps with rivets
            d.rectangle([m - 2, sy - 7, s - m - 30, sy + 7], fill=(58, 56, 54, 255))
            for rx in range(m + 8, s - m - 34, 28):
                d.ellipse([rx - 3, sy - 3, rx + 3, sy + 3], fill=(120, 116, 110, 255))
        cx, cy = s - m - 30, s // 2      # the ring
        d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=(70, 66, 60, 255), width=5)
        d.rectangle([cx - 4, cy - 18, cx + 4, cy - 10], fill=(70, 66, 60, 255))
        return tex.filter(ImageFilter.GaussianBlur(0.6))
    if kind == "bones":
        bone = (214, 206, 180, 240)
        for _ in range(9):
            x, y = rnd.randint(30, s - 70), rnd.randint(30, s - 50)
            ln, ang = rnd.randint(22, 48), rnd.uniform(0, math.pi)
            ex, ey = x + ln * math.cos(ang), y + ln * math.sin(ang)
            d.line([x, y, ex, ey], fill=bone, width=5)
            for px, py in ((x, y), (ex, ey)):
                d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=bone)
        rx, ry = rnd.randint(70, 150), rnd.randint(70, 150)      # a ribcage
        d.line([rx, ry, rx + 60, ry], fill=bone, width=5)
        for k in range(5):
            d.arc([rx + k * 12 - 10, ry - 22, rx + k * 12 + 10, ry + 22], 180, 360, fill=bone, width=3)
        sx, sy = rnd.randint(50, 200), rnd.randint(50, 200)      # and a small skull
        d.ellipse([sx - 14, sy - 11, sx + 14, sy + 11], fill=bone)
        d.ellipse([sx - 8, sy - 4, sx - 2, sy + 2], fill=(30, 26, 20, 255))
        d.ellipse([sx + 2, sy - 4, sx + 8, sy + 2], fill=(30, 26, 20, 255))
        return tex.filter(ImageFilter.GaussianBlur(0.6))
    if kind == "litter":
        # Shredded cloth, paper and straw, dragged into a heap.
        for _ in range(140):
            cx, cy = s / 2 + rnd.gauss(0, 50), s / 2 + rnd.gauss(0, 45)
            ang, ln = rnd.uniform(0, math.pi), rnd.randint(8, 26)
            c = rnd.choice([(96, 84, 60, 235), (120, 104, 70, 235), (70, 62, 52, 235), (140, 132, 116, 230),
                            (84, 40, 34, 230), (52, 58, 66, 230)])
            d.line([cx, cy, cx + ln * math.cos(ang), cy + ln * math.sin(ang)], fill=c, width=rnd.choice((2, 3, 4)))
        return tex.filter(ImageFilter.GaussianBlur(0.5))
    if kind == "haze":
        # A sickly yellow-green mist lying low on the floor: soft blobs, more
        # at the middle than the edges so neighbouring squares run together.
        g = Image.new("L", (s, s), 0)
        gd = ImageDraw.Draw(g)
        for _ in range(16):
            cx, cy = rnd.gauss(s / 2, 50), rnd.gauss(s / 2, 50)
            r = rnd.randint(40, 90)
            gd.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], fill=rnd.randint(40, 80))
        g = g.filter(ImageFilter.GaussianBlur(22))
        # Judged in the dark on a render (render_sewer.py): paler was invisible.
        tex.paste(Image.new("RGBA", (s, s), (186, 212, 70, 255)), (0, 0), g.point(lambda v: min(190, v * 4)))
        return tex
    if kind == "outfall":
        # A cast concrete apron, stained and chipped, with a barred grate over
        # the dark of the shaft; mud washed up over one edge from the water.
        d.rectangle([22, 22, s - 22, s - 22], fill=(118, 116, 106, 255))
        for _ in range(40):                              # stain and chips
            x, y = rnd.randint(26, s - 40), rnd.randint(26, s - 40)
            r = rnd.randint(4, 14)
            c = rnd.choice([(96, 94, 84, 255), (132, 128, 116, 255), (88, 92, 70, 255)])
            d.ellipse([x, y, x + r, y + r * 0.7], fill=c)
        d.rectangle([58, 58, s - 58, s - 58], fill=(12, 12, 12, 255))
        for k in range(9):                               # the bars
            bx = 64 + k * 16
            d.rectangle([bx, 58, bx + 6, s - 58], fill=(70, 50, 36, 255))
            d.line([bx + 1, 58, bx + 1, s - 58], fill=(120, 84, 56, 255), width=2)
        for by in (96, s - 96):
            d.rectangle([58, by - 4, s - 58, by + 4], fill=(62, 44, 32, 255))
        d.rectangle([58, 58, s - 58, s - 58], outline=(58, 56, 50, 255), width=6)
        mud = Image.new("L", (s, s), 0)
        md = ImageDraw.Draw(mud)
        for _ in range(12):
            x, y = rnd.randint(0, s), rnd.randint(s - 70, s)
            r = rnd.randint(20, 50)
            md.ellipse([x - r, y - r * 0.6, x + r, y + r * 0.6], fill=rnd.randint(120, 200))
        tex.paste(Image.new("RGBA", (s, s), (72, 58, 40, 255)), (0, 0), mud.filter(ImageFilter.GaussianBlur(8)))
        return tex.filter(ImageFilter.GaussianBlur(0.6))
    if kind == "smear":
        for k in range(40):
            t = k / 40
            x, y = 50 + t * 150, 120 + 30 * math.sin(t * 3) + rnd.randint(-3, 3)
            r = 14 * (1 - t) + 3
            d.ellipse([x - r, y - r * 0.6, x + r, y + r * 0.6], fill=(84, 10, 8, int(200 * (1 - t * 0.6))))
        return tex.filter(ImageFilter.GaussianBlur(1.5))
    raise ValueError(kind)


# --- the cult's (painted by the image model, cut and placed here) ----------------------------

_KEYED = {}


def keyed(name):
    """design/art/cult/<name>_raw.png with its key colour taken out, cropped
    to what is left. The model paints on "flat magenta" and delivers a pink
    with a vignette and sometimes a shadow, so the key is measured off the
    border and taken out by hue, not by value: a pixel is background when its
    colour points the same way as the border's, however dark. Black has no
    hue and is kept."""
    if name in _KEYED:
        return _KEYED[name].copy()
    import numpy as np
    im = np.asarray(Image.open(os.path.join(CULT, name + "_raw.png")).convert("RGB"), float)
    border = np.concatenate([im[:8].reshape(-1, 3), im[-8:].reshape(-1, 3),
                             im[:, :8].reshape(-1, 3), im[:, -8:].reshape(-1, 3)])
    key = np.median(border, axis=0)
    if not (key[0] > 120 and key[1] < 110 and key[2] > key[1] + 20):
        raise SystemExit("%s_raw.png: the border is %s, not a magenta key" % (name, key))
    ku = key / np.linalg.norm(key)
    mag = np.linalg.norm(im, axis=2)
    d = np.linalg.norm(im / np.maximum(mag, 1)[..., None] - ku, axis=2)
    a = np.clip((d - 0.10) / 0.10, 0, 1)
    a[mag < 45] = 1
    out = Image.fromarray(np.dstack([im, a * 255]).astype(np.uint8), "RGBA")
    # Cropped to the body of it: a stray speck of off-key pink would stretch the box.
    solid = out.split()[3].point(lambda v: 255 if v > 128 else 0).filter(ImageFilter.MinFilter(5))
    box = solid.getbbox()
    if not box:
        raise SystemExit("%s_raw.png: nothing left after keying" % name)
    out = out.crop((max(0, box[0] - 4), max(0, box[1] - 4), box[2] + 4, box[3] + 4))
    _KEYED[name] = out
    return out.copy()


def fit(img, w=None, h=None):
    """Scaled to a width or a height, keeping its shape."""
    k = (w / img.width) if w else (h / img.height)
    return img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)


def standing(name, height, base=250):
    """A raw stood on its square: centred, its foot `base` px down the cell
    (the floor diamond runs 192..256; its middle is 224)."""
    img = fit(keyed(name), h=height)
    if img.width > CW:
        img = fit(img, w=CW)
    cell = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    cell.alpha_composite(img, ((CW - img.width) // 2, base - img.height))
    return cell


def tint(img, color):
    """The shape of a keyed raw in one colour: the sigil as paint, or as thread."""
    out = Image.new("RGBA", img.size, color)
    out.putalpha(img.split()[3].point(lambda v: v * color[3] // 255))
    return out


def cult_wall(base, rnd):
    """The cult's pictures, as face textures (TW x TH)."""
    tex = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    if base == "sigil":
        s = fit(tint(keyed("sigil"), (150, 16, 14, 235)), w=190)
        tex.alpha_composite(s, ((TW - s.width) // 2, int(TH * 0.26)))
        return weather(tex, rnd, 0.18, 1)
    if base == "burrow":
        return spray("THE\nBURROW\nPROVIDES", (160, 22, 18, 235), 40, rnd, angle=-2)
    if base == "torch":
        t = fit(keyed("torch"), h=230)
        glow = Image.new("L", (TW, TH), 0)
        gx, gy = TW // 2, int(TH * 0.20)
        gd = ImageDraw.Draw(glow)
        for r in range(110, 0, -4):
            gd.ellipse([gx - r, gy - r, gx + r, gy + r], fill=int(120 * (1 - r / 110) ** 1.5))
        tex.paste(Image.new("RGBA", (TW, TH), (255, 150, 50, 255)), (0, 0), glow.filter(ImageFilter.GaussianBlur(6)))
        tex.alpha_composite(t, ((TW - t.width) // 2, int(TH * 0.12)))
        return tex
    if base == "banner":
        d = ImageDraw.Draw(tex)
        x0, x1, y0, y1 = int(TW * 0.20), int(TW * 0.80), int(TH * 0.10), int(TH * 0.74)
        d.rectangle([x0 - 10, y0 - 8, x1 + 10, y0], fill=(52, 38, 26, 255))                 # the pole
        hem = [(x0, y0)] + [(x0 + (x1 - x0) * k / 8, y1 + (14 if k % 2 else -6) + rnd.randint(-4, 4)) for k in range(9)]
        d.polygon(hem + [(x1, y0)], fill=(22, 20, 22, 250))
        for k in range(6):                                                                   # folds
            fx = x0 + (x1 - x0) * (k + 0.5) / 6
            d.line([fx, y0 + 4, fx + rnd.randint(-4, 4), y1 - 16], fill=(36, 33, 36, 255), width=3)
        d.rectangle([x0, y0 + 10, x1, y0 + 16], fill=(120, 16, 14, 255))
        s = fit(tint(keyed("sigil"), (170, 24, 18, 245)), w=int((x1 - x0) * 0.86))
        tex.alpha_composite(s, ((TW - s.width) // 2, y0 + 34))
        return tex
    raise ValueError(base)


def cult_mural():
    """The triptych: one painting three squares wide, cut into its faces."""
    wide = Image.new("RGBA", (TW * 3, TH), (0, 0, 0, 0))
    m = fit(keyed("mural"), w=int(TW * 3 * 0.94))
    if m.height > TH * 0.9:
        m = fit(m, h=int(TH * 0.9))
    wide.alpha_composite(m, ((wide.width - m.width) // 2, int(TH * 0.94) - m.height))
    return [wide.crop((i * TW, 0, (i + 1) * TW, TH)) for i in range(3)]


def cult_circle():
    """The circle: one drawing three squares across, cut into nine floor textures."""
    c = keyed("circle").resize((768, 768), Image.LANCZOS)
    return [c.crop(((i % 3) * 256, (i // 3) * 256, (i % 3) * 256 + 256, (i // 3) * 256 + 256)) for i in range(9)]


def offering(rnd):
    """A wooden bowl of something dark, small skulls round it, a few coins."""
    s = 256
    tex = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(tex)
    d.ellipse([84, 92, 172, 164], fill=(74, 50, 30, 255))
    d.ellipse([92, 98, 164, 156], fill=(40, 26, 16, 255))
    d.ellipse([98, 104, 158, 150], fill=(96, 10, 10, 255))
    d.ellipse([112, 110, 136, 122], fill=(150, 30, 26, 200))
    bone = (214, 206, 180, 245)
    for _ in range(5):
        a = rnd.uniform(0, 2 * math.pi)
        r = rnd.randint(70, 96)
        x, y = s / 2 + r * math.cos(a), s / 2 + r * math.sin(a)
        d.ellipse([x - 13, y - 10, x + 13, y + 10], fill=bone)
        d.polygon([(x + 8, y - 5), (x + 24, y), (x + 8, y + 5)], fill=bone)
        d.ellipse([x - 8, y - 5, x - 2, y + 1], fill=(30, 26, 20, 255))
        d.ellipse([x + 1, y - 5, x + 7, y + 1], fill=(30, 26, 20, 255))
    for _ in range(9):
        x, y = rnd.randint(40, 216), rnd.randint(40, 216)
        d.ellipse([x - 5, y - 4, x + 5, y + 4], fill=(198, 160, 52, 255))
        d.arc([x - 5, y - 4, x + 5, y + 4], 200, 340, fill=(246, 222, 130, 255), width=2)
    for _ in range(6):
        x, y = rnd.randint(40, 200), rnd.randint(40, 200)
        ln, ang = rnd.randint(18, 34), rnd.uniform(0, math.pi)
        d.line([x, y, x + ln * math.cos(ang), y + ln * math.sin(ang)], fill=bone, width=4)
    return tex.filter(ImageFilter.GaussianBlur(0.6))


def draw(name, kind, rnd, vanilla):
    if kind == "prop":
        return standing(name, 204 if name == "idol" else 104)
    if name == "candles":
        return standing("candles", 58, base=238)
    if name.startswith("circle"):
        return to_floor(cult_circle()[int(name[6:])])
    if name == "offering":
        return to_floor(offering(rnd))
    if name.startswith("mural"):
        return to_wall(cult_mural()[int(name[5])], "N")
    if name.rsplit("_", 1)[0] in ("sigil", "burrow", "torch", "banner"):
        return to_wall(cult_wall(name.rsplit("_", 1)[0], rnd), kind[-1])
    if kind.startswith("copy:"):
        return vanilla[kind[5:]]
    if kind.startswith("copyfloor:"):
        return vanilla[kind[10:]]
    if kind.startswith("lower:"):
        # Down from where vanilla draws it (oy 64) to the floor diamond (oy 192).
        cell = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        cell.alpha_composite(vanilla[kind[6:]].crop((0, 0, CW, CH - 128)), (0, 128))
        return cell
    if kind.startswith("breach:"):
        src = kind[7:]
        side = "W" if src in ("location_sewer_01_8", "location_sewer_01_0") else "N"
        # Over the door frame the builder puts under it (SEW_Config doorFrame).
        return breach(vanilla[src], side, rnd, vanilla["location_sewer_01_18" if side == "W" else "location_sewer_01_19"])
    if kind == "corner:earth":
        cell = to_wall(earth(rng_for("earth_W")), "W")
        cell.alpha_composite(to_wall(earth(rng_for("earth_N")), "N"))
        return cell
    side = kind[-1] if kind.startswith("wall") else None
    base = name.rsplit("_", 1)[0]
    if base == "exit":
        tex = stencil("EXIT", (232, 196, 40, 240), 64, rnd, arrow="up", ladder=True)
    elif base == "safe":
        tex = spray("SAFE\nKNOCK 3", (90, 200, 110, 235), 46, rnd, angle=2)
    elif base == "grime":
        tex = grime(rnd)
    elif base == "cracks":
        tex = cracks(rnd)
    elif base == "claws":
        tex = claws(rnd)
    elif base == "gas":
        tex = placard(rnd)
    elif base == "earth":
        # Exactly the shape of the concrete wall it covers, to the last pixel:
        # the projection's soft edge let a line of concrete show round it.
        face = to_wall(earth(rnd), side)
        wall = vanilla["location_sewer_01_8" if side == "W" else "location_sewer_01_9"].split()[3]
        out = Image.new("RGBA", (CW, CH), (58, 42, 28, 0))
        out.putalpha(wall)
        out.alpha_composite(face)
        r, g, b, _a = out.split()
        return Image.merge("RGBA", (r, g, b, wall))
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
    vanilla = vanilla_cells({"location_sewer_01_32", "location_sewer_01_33", "location_sewer_01_26",
                             "location_sewer_01_0", "location_sewer_01_1", "location_sewer_01_8",
                             "location_sewer_01_18", "location_sewer_01_19", "street_decoration_01_15",
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
