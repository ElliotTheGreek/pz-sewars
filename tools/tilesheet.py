"""Contact sheet of vanilla tiles, cut straight out of the game's texture packs.

    python tools/tilesheet.py design/art/vanilla_sewer_tiles.png location_sewer_01_
    python tools/tilesheet.py out.png street_decoration_01_ blends_street_01_

New art is judged beside the vanilla tiles it will stand next to (DEV_GUIDE,
Art). Pack format (PZPK version 1) as read by pz_trekship's
tools/gen_adirondack_pack.py.
"""
import glob
import io
import os
import struct
import sys

from PIL import Image, ImageDraw

PACKS = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media\texturepacks"


def read_pack(path):
    b = open(path, "rb").read()
    o = 4

    def i32():
        nonlocal o
        v = struct.unpack_from("<i", b, o)[0]
        o += 4
        return v

    def s():
        nonlocal o
        n = i32()
        v = b[o:o + n].decode("latin1")
        o += n
        return v

    if b[:4] != b"PZPK" or i32() != 1:
        raise SystemExit("%s is not a PZPK version 1 pack" % path)
    pages = []
    for _ in range(i32()):
        name, n, mask = s(), i32(), i32()
        entries = [(s(), [i32() for _ in range(8)]) for _ in range(n)]
        size = i32()
        png = b[o:o + size]
        o += size
        pages.append(dict(name=name, mask=mask, entries=entries, png=png))
    return pages


def main(out, prefixes):
    found = {}
    # Tiles2x first, so a tile present at both sizes is shown at game size.
    for p in sorted(glob.glob(os.path.join(PACKS, "*.pack")), key=lambda p: "2x" not in p):
        try:
            pages = read_pack(p)
        except SystemExit:
            continue
        for pg in pages:
            hit = [e for e in pg["entries"] if e[0].startswith(tuple(prefixes))]
            if not hit:
                continue
            img = Image.open(io.BytesIO(pg["png"])).convert("RGBA")
            for name, v in hit:
                if name in found:
                    continue
                x, y, w, h, ox, oy, fw, fh = v
                cell = Image.new("RGBA", (fw, fh), (40, 40, 48, 255))
                cell.alpha_composite(img.crop((x, y, x + w, y + h)), (ox, oy))
                found[name] = cell
    if not found:
        raise SystemExit("no tile matched: check the prefix")
    names = sorted(found, key=lambda n: (n.rsplit("_", 1)[0], int(n.rsplit("_", 1)[1])))
    cols, cw, ch = 8, 128, 256
    sheet = Image.new("RGBA", (cols * cw, ((len(names) + cols - 1) // cols) * (ch + 14)), (20, 20, 24, 255))
    d = ImageDraw.Draw(sheet)
    for i, n in enumerate(names):
        c = found[n]
        if c.size != (cw, ch):
            c = c.resize((cw, ch))
        X, Y = (i % cols) * cw, (i // cols) * (ch + 14)
        sheet.alpha_composite(c, (X, Y + 14))
        d.text((X + 2, Y), n, fill=(255, 255, 0, 255))
    sheet.save(out)
    print(len(names), "tiles ->", out)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2:])
