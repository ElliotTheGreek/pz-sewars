"""The maintenance key's inventory icon, drawn: a worn brass key on a ring
with the county's red card tag.

    python tools/gen_key_icon.py

Writes design/art/items/key_raw.png (the 256px drawing, kept as the raw) and
Sewars/42/media/textures/Item_SEW_Key.png (64x64, transparent, the size of the
mod's other Item_ icons). Drawn rather than painted by an image model: a key
is a few shapes, and a script re-draws it exactly when it needs a change.
Judge it at 32px beside vanilla's keys, on the dark inventory.
"""
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "design", "art", "items", "key_raw.png")
OUT = os.path.join(ROOT, "Sewars", "42", "media", "textures", "Item_SEW_Key.png")

BRASS = (196, 158, 70, 255)
BRASS_DARK = (120, 92, 36, 255)
BRASS_LIGHT = (236, 206, 128, 255)
TAG = (168, 44, 36, 255)
TAG_DARK = (98, 22, 18, 255)
INK = (240, 228, 206, 255)


def draw():
    s = 256
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # The ring, top left.
    d.ellipse([18, 14, 104, 100], outline=(150, 150, 150, 255), width=9)
    d.arc([18, 14, 104, 100], 200, 300, fill=(215, 215, 215, 255), width=4)
    # The key: bow (round, with a hole), shank running down-right, bit.
    d.ellipse([58, 58, 132, 132], fill=BRASS_DARK)
    d.ellipse([62, 62, 128, 128], fill=BRASS)
    d.ellipse([82, 82, 108, 108], fill=(0, 0, 0, 0))
    d.arc([66, 66, 124, 124], 200, 290, fill=BRASS_LIGHT, width=5)
    shank = [(118, 112), (128, 102), (222, 196), (212, 206)]
    d.polygon(shank, fill=BRASS)
    d.line([(124, 106), (216, 198)], fill=BRASS_LIGHT, width=3)
    d.line([(116, 114), (210, 206)], fill=BRASS_DARK, width=3)
    # The bit: three teeth off the end.
    for k, (ox, oy) in enumerate(((176, 178), (192, 194), (206, 208))):
        h = (22, 14, 26)[k]
        d.polygon([(ox, oy), (ox + 10, oy - 10), (ox + 10 + h * 0.7, oy - 10 + h * 0.7),
                   (ox + h * 0.7, oy + h * 0.7)], fill=BRASS_DARK)
    # The tag on its string, hanging from the ring.
    d.line([(34, 92), (40, 150)], fill=(210, 200, 170, 255), width=3)
    d.rounded_rectangle([12, 146, 92, 232], radius=8, fill=TAG_DARK)
    d.rounded_rectangle([16, 150, 88, 228], radius=7, fill=TAG)
    d.ellipse([46, 156, 58, 168], fill=(0, 0, 0, 0))
    # "DPW" in heavy strokes (no font: it is read at 32px as three marks).
    x0, y0 = 26, 180
    for i, glyph in enumerate(("D", "P", "W")):
        gx = x0 + i * 20
        if glyph == "D":
            d.line([(gx, y0), (gx, y0 + 30)], fill=INK, width=5)
            d.arc([gx - 12, y0, gx + 14, y0 + 30], 270, 90, fill=INK, width=5)
        elif glyph == "P":
            d.line([(gx, y0), (gx, y0 + 30)], fill=INK, width=5)
            d.arc([gx - 8, y0, gx + 12, y0 + 16], 270, 90, fill=INK, width=5)
        else:
            d.line([(gx - 2, y0), (gx + 3, y0 + 30), (gx + 8, y0 + 12), (gx + 13, y0 + 30), (gx + 18, y0)],
                   fill=INK, width=4)
    return im


def main():
    im = draw()
    # A dark outline, as the mod's other icons and vanilla's have.
    edge = im.split()[3].point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(9))
    outlined = Image.new("RGBA", im.size, (26, 20, 14, 0))
    outlined.putalpha(edge)
    outlined.alpha_composite(im)
    im = outlined
    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    im.save(RAW)
    icon = im.filter(ImageFilter.GaussianBlur(0.6)).resize((64, 64), Image.LANCZOS)
    if not icon.split()[3].getbbox():
        raise SystemExit("the key icon drew nothing")
    icon.save(OUT)
    print("key icon -> %s" % OUT)


if __name__ == "__main__":
    main()
