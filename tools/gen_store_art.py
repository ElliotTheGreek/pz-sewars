"""The Steam store images, cut from the author's in-game screenshots.

    python tools/gen_store_art.py

Reads design/art/screens/ (the raw screenshots, kept as taken) and writes
workshop/store/:

    the_way_down.jpg     the four in one, numbered: above the cover, the foot
                         of the ladder, the tunnels, a shelter
    1_manhole.jpg ...    each shot on its own, captioned

JPEG, to stay well under Steam's upload size for gallery images.

These go on the Steam page by hand (the item's page -> "Add/edit images &
videos"): the in-game uploader sends only preview.png. The mods-screen poster
and the Workshop preview are cut from the ladder shot by tools/gen_poster.py.

Every panel gets its caption in a band across the top, which also covers the
"- Game Paused -" the engine prints there (4_shelter.png).
"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENS = os.path.join(ROOT, "design", "art", "screens")
OUT = os.path.join(ROOT, "workshop", "store")
FONT = r"C:\Windows\Fonts\impact.ttf"
BODY = r"C:\Windows\Fonts\bahnschrift.ttf"
YELLOW = (232, 196, 40)
BG = (12, 12, 11)

# (file, caption, focus): focus is where the crop centres, as fractions of the shot.
SHOTS = [
    ("1_manhole.png", "Climb down into the sewer", (0.45, 0.50)),
    ("2_ladder.png", "Light through the cover, and the only way up", (0.55, 0.50)),
    ("3_tunnel.png", "Tunnels under every street", (0.45, 0.50)),
    ("4_shelter.png", "Safe. Knock 3.", (0.50, 0.55)),
]
PANEL = (960, 720)
BAND = 76


def cover(img, size, focus):
    """Scale to fill `size`, cropping round `focus`."""
    w, h = size
    s = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    cx, cy = img.width * focus[0], img.height * focus[1]
    left = int(max(0, min(img.width - w, cx - w / 2)))
    top = int(max(0, min(img.height - h, cy - h / 2)))
    return img.crop((left, top, left + w, top + h))


def panel(name, caption, focus, number=None):
    img = cover(Image.open(os.path.join(SCREENS, name)).convert("RGB"), PANEL, focus)
    band = Image.new("RGBA", (PANEL[0], BAND), BG + (225,))
    img.paste(band, (0, 0), band)
    d = ImageDraw.Draw(img)
    x = 28
    if number is not None:
        fn = ImageFont.truetype(FONT, 54)
        d.text((x, BAND / 2), str(number), font=fn, fill=YELLOW, anchor="lm")
        x += d.textlength(str(number), font=fn) + 22
    d.text((x, BAND / 2), caption, font=ImageFont.truetype(BODY, 36), fill=(236, 232, 220), anchor="lm")
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    panels = []
    for i, (name, caption, focus) in enumerate(SHOTS, 1):
        panel(name, caption, focus).save(os.path.join(OUT, name[:-4] + ".jpg"), quality=90)
        panels.append(panel(name, caption, focus, i))

    gap, head = 16, 150
    W = PANEL[0] * 2 + gap * 3
    H = head + PANEL[1] * 2 + gap * 3
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    d.text((W / 2, head / 2 + 4), "EVERY MANHOLE GOES SOMEWHERE", font=ImageFont.truetype(FONT, 96),
           fill=YELLOW, anchor="mm")
    for i, p in enumerate(panels):
        sheet.paste(p, (gap + (i % 2) * (PANEL[0] + gap), head + gap + (i // 2) * (PANEL[1] + gap)))
    sheet.save(os.path.join(OUT, "the_way_down.jpg"), quality=90)
    print("store art -> %s (%d images)" % (OUT, len(panels) + 1))


if __name__ == "__main__":
    main()
