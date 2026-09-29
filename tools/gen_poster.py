"""The mod's poster (mods screen, 480x320) and Workshop preview (256x256).

    python tools/gen_poster.py

Both are cut from the author's in-game screenshot at the foot of a ladder
(design/art/screens/2_ladder.png: EXIT stencils, light through the cover),
with the name stencilled over it. Without that file they fall back to a
render of the real generated tunnels (tools/render_sewer.py), the first
shelter under Muldraugh, which re-makes itself when the layout or tiles change.

design/art/poster_source.png is the full render, to judge.
"""
import os
import re
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_sewer  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTER = os.path.join(ROOT, "Sewars", "42", "poster.png")
PREVIEW = os.path.join(ROOT, "workshop", "preview.png")
SOURCE = os.path.join(ROOT, "design", "art", "poster_source.png")
SHOT = os.path.join(ROOT, "design", "art", "screens", "2_ladder.png")
FONT = r"C:\Windows\Fonts\impact.ttf"


def shelter():
    s = open(os.path.join(ROOT, "Sewars", "42", "media", "lua", "shared", "SEW", "SEW_Index.lua"),
             encoding="utf-8").read()
    m = re.search(r'H\[#H\+1\]=\{town="muldraugh",kind="\w+",x=(\d+),y=(\d+),w=(\d+),h=(\d+)', s)
    x, y, w, h = map(int, m.groups())
    return x + w // 2, y + h // 2


def titled(img, size, at=None):
    """The name over `img`: centred near the top, or with its top-left `at` (x, y),
    where negative x and y count from the right and bottom edges."""
    img = ImageEnhance.Brightness(img).enhance(1.35)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, size)
    text = "SEWARS"
    w = d.textlength(text, font=f)
    if at is None:
        x, y = (img.width - w) / 2, img.height * 0.08
    else:
        x = at[0] if at[0] >= 0 else img.width - w + at[0]
        y = at[1] if at[1] >= 0 else img.height - size * 1.25 + at[1]
    glow = Image.new("L", img.size, 0)
    ImageDraw.Draw(glow).text((x, y), text, font=f, fill=255)
    img.paste((0, 0, 0), (0, 0), glow.filter(ImageFilter.GaussianBlur(size / 8)))
    d.text((x, y), text, font=f, fill=(232, 196, 40))
    return img


def crop_to(img, cx, cy, w, h):
    left = max(0, min(img.width - w, cx - w // 2))
    top = max(0, min(img.height - h, cy - h // 2))
    return img.crop((left, top, left + w, top + h))


def main():
    x, y = shelter()
    img, _ = render_sewer.render("muldraugh", x, y, 14, dark=0.5)
    img.save(SOURCE)
    os.makedirs(os.path.dirname(PREVIEW), exist_ok=True)
    if os.path.isfile(SHOT):
        # Brighter already than a render, so titled()'s lift is kept small by
        # darkening first; the crops keep the player, the EXITs and the ladder.
        shot = ImageEnhance.Brightness(Image.open(SHOT).convert("RGB")).enhance(0.8)
        poster = crop_to(shot, 380, 290, 646, 431).resize((480, 320), Image.LANCZOS)
        preview = crop_to(shot, 355, 270, 470, 470).resize((256, 256), Image.LANCZOS)
        what = "from " + os.path.relpath(SHOT, ROOT)
    else:
        cx, cy = img.width // 2, img.height // 2
        poster = crop_to(img, cx, cy, 1440, 960).resize((480, 320), Image.LANCZOS)
        preview = crop_to(img, cx, cy, 960, 960).resize((256, 256), Image.LANCZOS)
        what = "from a render round the shelter at %d,%d" % (x, y)
    # The shot is black above the tunnel wall and below its floor: the name
    # goes there, clear of the EXITs.
    shot = os.path.isfile(SHOT)
    titled(poster, 64, (-16, -10) if shot else None).save(POSTER)
    titled(preview, 50, (-10, -6) if shot else None).save(PREVIEW)
    print("poster %s, preview %s, %s" % (POSTER, PREVIEW, what))


if __name__ == "__main__":
    main()
