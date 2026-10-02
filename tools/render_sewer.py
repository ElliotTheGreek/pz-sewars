"""Draws a stretch of the generated sewers with the game's own tiles, lit dim.

    python tools/render_sewer.py muldraugh               # round the town's middle shaft
    python tools/render_sewer.py muldraugh 10592 9800 24 # round a square, radius 24

Writes design/art/render_<town>.png. It reads the shipped data
(server/SEW/Data/SEW_Town_*.lua) and decodes it the way SEW_Build.lua does --
a second reading of the same legend, kept beside the first on purpose: if the
two ever disagree, the picture looks wrong, which is the cheapest way to find
out. Render it and look (pz_trekship DEV_GUIDE, four times over).

Also used by tools/dev.py to make the mod's poster and Workshop preview.
"""
import io
import math
import os
import re
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tilesheet  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "Sewars", "42", "media", "lua")
OURS = os.path.join(ROOT, "design", "art", "tiles", "sewars_01.png")
CONFIG = os.path.join(LUA, "shared", "SEW", "SEW_Config.lua")


def config_sprites():
    s = open(CONFIG, encoding="utf-8").read()

    def one(k):
        return re.search(r"\b%s\s*=\s*\"([^\"]+)\"" % k, s).group(1)

    def pair(block):
        m = re.search(r"\b%s\s*=\s*\{\s*N\s*=\s*\"([^\"]+)\",\s*W\s*=\s*\"([^\"]+)\"" % block, s)
        return {"N": m.group(1), "W": m.group(2)}

    sp = {k: one(k) for k in ("floorTunnel", "floorVault", "floorShelter", "floorRock", "sludge",
                              "puddle", "debris", "lightpool", "smear", "bones", "litter", "haze",
                              "floorTemple", "floorCarpet", "floorBoards")}
    for k in ("doorFrame", "door", "gate", "ladder", "exit", "safe", "grime", "cracks", "claws", "rousWarning", "gasSign"):
        sp[k] = pair(k)
    sp["graffiti"] = {c: {"N": n, "W": w} for c, n, w in
                      re.findall(r"\b([a-g])\s*=\s*\{\s*N\s*=\s*\"([^\"]+)\",\s*W\s*=\s*\"([^\"]+)\"", s)}
    sp["wall"] = {}
    for style in ("c", "b"):
        m = re.search(r"\b%s\s*=\s*\{\s*N\s*=\s*\"([^\"]+)\",\s*W\s*=\s*\"([^\"]+)\",\s*NW\s*=\s*\"([^\"]+)\",\s*"
                      r"pillar\s*=\s*\"([^\"]+)\"" % style, s)
        sp["wall"][style] = dict(zip(("N", "W", "NW", "pillar"), m.groups()))
    sp["variants"] = {}
    block = s[s.index("wallVariants"):]
    for style in ("c", "b"):
        m = re.search(r"\b" + style + r" = \{ N = \{([^}]*)\},\s*W = \{([^}]*)\}", block)
        sp["variants"][style] = {"N": re.findall(r'"([^"]+)"', m.group(1)),
                                 "W": re.findall(r'"([^"]+)"', m.group(2))}
    m = re.search(r"\be\s*=\s*\{\s*N\s*=\s*\"([^\"]+)\",\s*W\s*=\s*\"([^\"]+)\",\s*NW\s*=\s*\"([^\"]+)\"", s)
    sp["wall"]["e"] = dict(zip(("N", "W", "NW"), m.groups()))
    sp["earthFace"] = pair("earthFace")
    sp["breach"] = {k: {"N": n, "W": w} for k, n, w in
                    re.findall(r"\b([oq])\s*=\s*\{\s*N\s*=\s*\"([^\"]+)\",\s*W\s*=\s*\"([^\"]+)\"", s)}
    sp["floorCave"] = re.findall(r"\"(floors_exterior_natural_01_\d+)\"", s)
    sp["stones"] = re.findall(r"\"(boulders_\d+)\"", s)
    sp["grating"] = re.findall(r"\"(location_sewer_01_4[0-2])\"", s)
    sp["pipes"] = re.findall(r"\"(location_sewer_01_3[4-7])\"", s)
    return sp


def lua_hash(a, b, c=0):
    h = (a * 73856093 + b * 19349663 + c * 83492791) % 2147483647
    return -h if h < 0 else h


# The nest's walls that open, as a new world has them: shut (SEW_Build GATE).
GATE_SHUT = {"x": "c", "y": "b", "z": "b"}
# Where the cult broke into a sewer: the breach of the wall it went through (SEW_Build BREACH).
CULT_BREACH = {"O": "o", "Q": "q"}


def lua_rng1(seed, n):
    """The first roll of SEW.Util.rng(seed)(n): Park-Miller, as the Lua has it."""
    state = seed % 2147483646 + 1
    state = (state * 48271) % 2147483647
    return state % n + 1


def decode(x, y, rec, sp):
    """The sprites SEW_Build.square puts on this square, in the order it puts them."""
    f, n, w, fix, dress = rec[2], rec[3], rec[4], rec[5], rec[6]
    gate_edge = "N" if n in GATE_SHUT else "W" if w in GATE_SHUT else None
    n, w = GATE_SHUT.get(n, n), GATE_SHUT.get(w, w)
    n, w = CULT_BREACH.get(n, n), CULT_BREACH.get(w, w)
    out = []
    floor = {"t": sp["floorTunnel"], "k": sp["floorVault"], "s": sp["floorShelter"], "r": sp["floorRock"],
             "w": sp["floorVault"], "g": sp["grating"][lua_hash(x, y) % len(sp["grating"])],
             "m": sp["floorCave"][1 if lua_hash(x, y, 5) % 5 == 0 else 0] if f == "m" else None,
             "n": sp["floorCave"][1 if lua_rng1(lua_hash(x, y, 5), 4) == 1 else 0] if f == "n" else None,
             "p": sp["floorCave"][1 if lua_rng1(lua_hash(x, y, 5), 4) == 1 else 0] if f == "p" else None,
             "h": sp["floorTemple"], "a": sp["floorCarpet"], "q": sp["floorBoards"],
             "v": sp["floorVault"]}.get(f)
    if floor:
        out.append(floor)
    if f == "w":
        out.append(sp["sludge"])
    nw = n if n in "cbe" else None
    ww = w if w in "cbe" else None
    if nw and ww and nw == ww:
        out.append(sp["wall"][nw]["NW"])
    else:
        if nw:
            v = sp["variants"].get(nw, {}).get("N") or [sp["wall"][nw]["N"]]
            out.append(v[lua_hash(x, y, 11) % len(v)])
        if ww:
            v = sp["variants"].get(ww, {}).get("W") or [sp["wall"][ww]["W"]]
            out.append(v[lua_hash(x, y, 13) % len(v)])
    if n == "d":
        out += [sp["doorFrame"]["N"], sp["door"]["N"]]
    if w == "d":
        out += [sp["doorFrame"]["W"], sp["door"]["W"]]
    # A county room's locked grille (DESIGN.md 7, Locked gates), in the same frame.
    if n == "j":
        out += [sp["doorFrame"]["N"], sp["gate"]["N"]]
    if w == "j":
        out += [sp["doorFrame"]["W"], sp["gate"]["W"]]
    # Ours over vanilla's, as SEW_Build puts them: a breach over a door frame,
    # an earth face over a concrete wall.
    if n in "oq":
        out += [sp["doorFrame"]["N"], sp["breach"][n]["N"]]
    if w in "oq":
        out += [sp["doorFrame"]["W"], sp["breach"][w]["W"]]
    if n == "e":
        out.append(sp["earthFace"]["N"])
    if w == "e":
        out.append(sp["earthFace"]["W"])
    out += {"L": [sp["ladder"]["N"]], "l": [sp["ladder"]["W"]], "P": [sp["wall"]["c"]["pillar"]],
            "Q": [sp["wall"]["b"]["pillar"]]}.get(fix, [])
    side = "N" if n in "cb" else "W"
    if dress == "p":
        out.append(sp["pipes"][lua_hash(x, y, 7) % len(sp["pipes"])])
    elif dress in "ehi":
        out.append({"e": sp["exit"], "h": sp["safe"], "i": sp["grime"]}[dress][side])
    elif dress in "abcdefg":
        out.append(sp["graffiti"][dress][side])
    elif dress in "uvxy":
        out.append({"u": sp["puddle"], "v": sp["debris"], "x": sp["lightpool"], "y": sp["smear"]}[dress])
    elif dress == "z":
        out.append(sp["stones"][lua_hash(x, y, 17) % len(sp["stones"])])
    elif dress in "jk":
        out.append(sp["bones"] if dress == "j" else sp["litter"])
    elif dress == "l":
        out.append(sp["claws"][gate_edge or ("N" if n == "e" else "W")])
    elif dress == "n":
        out.append(sp["cracks"][gate_edge or side])
    elif dress == "o":
        out.append(sp["rousWarning"][side])
    return out


def read_town(tid):
    s = open(os.path.join(LUA, "server", "SEW", "Data", "SEW_Town_%s.lua" % tid), encoding="utf-8").read()
    sq = {}
    for cx, cy, body in re.findall(r'c\["(-?\d+),(-?\d+)"\]="([^"]*)"', s):
        for i in range(0, len(body), 7):
            r = body[i:i + 7]
            sq[(int(cx) * 8 + int(r[0]), int(cy) * 8 + int(r[1]))] = r
    furn = [(int(x), int(y), spr) for x, y, spr in re.findall(r'\{(\d+),(\d+),"([^"]+_\d+)",', s)]
    # The cult's pictures (T.pictures): hung on the wall of their square, after everything else.
    for body in re.findall(r'^h\["-?\d+,-?\d+"\]=\{(.*)\}$', s, re.M):
        furn += [(int(x), int(y), spr) for x, y, spr in re.findall(r'\{(\d+),(\d+),"([^"]+)"\}', body)]
    # Sewer gas (SEW_Gas.dress): the haze on its squares, the placards at its ways in.
    gas = set()
    for cx, cy, body in re.findall(r'g\["(-?\d+),(-?\d+)"\]="([^"]*)"', s):
        for i in range(0, len(body), 3):
            gas.add((int(cx) * 8 + int(body[i]), int(cy) * 8 + int(body[i + 1])))
    signs = [(int(x), int(y), e) for x, y, e in re.findall(r'\{(\d+),(\d+),"([NW])"\}', s)]
    return sq, furn, gas, signs


def temple_lights():
    """The temple's sconces, braziers and candles, from the index."""
    s = open(os.path.join(LUA, "shared", "SEW", "SEW_Index.lua"), encoding="utf-8").read()
    m = re.search(r"I\.temple=\{.*?lights=\{([\d,]*)\}", s)
    v = [int(n) for n in m.group(1).split(",")] if m else []
    return set(zip(v[0::2], v[1::2]))


def images(names):
    ours = Image.open(OURS).convert("RGBA")
    out, want = {}, set()
    for n in names:
        if n.startswith("sewars_01_"):
            i = int(n.rsplit("_", 1)[1])
            out[n] = ours.crop(((i % 8) * 128, (i // 8) * 256, (i % 8) * 128 + 128, (i // 8) * 256 + 256))
        else:
            want.add(n)
    for p in sorted(os.listdir(tilesheet.PACKS)):
        if not want - set(out):
            break
        if not p.startswith("Tiles2x") or not p.endswith(".pack"):
            continue
        for pg in tilesheet.read_pack(os.path.join(tilesheet.PACKS, p)):
            hit = [e for e in pg["entries"] if e[0] in want and e[0] not in out]
            if not hit:
                continue
            img = Image.open(io.BytesIO(pg["png"])).convert("RGBA")
            for name, (x, y, w, h, ox, oy, fw, fh) in hit:
                cell = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
                cell.alpha_composite(img.crop((x, y, x + w, y + h)), (ox, oy))
                out[name] = cell.resize((128, 256)) if cell.size != (128, 256) else cell
    return out


def render(tid, cx=None, cy=None, r=22, dark=0.42, shafts=None):
    sq, furn, gas, signs = read_town(tid)
    if cx is None:
        pts = sorted(sq)
        cx, cy = pts[len(pts) // 2]
    sp = config_sprites()
    area = {p: rec for p, rec in sq.items() if abs(p[0] - cx) <= r and abs(p[1] - cy) <= r}
    fur = {}
    for x, y, spr in furn:
        if (x, y) in area:
            fur.setdefault((x, y), []).append(spr)
    per = {p: decode(p[0], p[1], rec, sp) + fur.get(p, []) for p, rec in area.items()}
    for p in gas:
        if p in per:
            per[p].append(sp["haze"])
    for x, y, e in signs:
        if (x, y) in per:
            per[(x, y)].append(sp["gasSign"][e])
    imgs = images({n for v in per.values() for n in v})
    xs = [64 * (x - y) for x, y in per]
    ys = [32 * (x + y) for x, y in per]
    ox, oy = -min(xs) + 64, -min(ys) + 256
    W, H = max(xs) - min(xs) + 256, max(ys) - min(ys) + 320
    canvas = Image.new("RGBA", (W, H), (6, 6, 8, 255))
    # The game cuts walls away round the player; a still picture has to do it by
    # hand or every corridor's south wall hides its floor (the first render).
    # A wall standing on a square outside the tunnel is drawn as a stub.
    stub = {}
    for n, im in imgs.items():
        s = im.copy()
        px = s.load()
        for col in range(128):
            top = 192 + abs(col - 64) // 2 - 44     # along the wall slope
            for row in range(0, max(0, top)):
                px[col, row] = (0, 0, 0, 0)
        stub[n] = s
    walls = ({v for style in sp["wall"].values() for v in style.values()} | set(sp["doorFrame"].values())
             | {v for b in sp["breach"].values() for v in b.values()}
             | {v for style in sp["variants"].values() for e in style.values() for v in e})
    for (x, y) in sorted(per, key=lambda p: (p[0] + p[1], p[0])):
        outside = area[(x, y)][2] == "r"
        for n in per[(x, y)]:
            if n in imgs:
                im = stub[n] if outside and n in walls else imgs[n]
                canvas.alpha_composite(im, (ox + 64 * (x - y) - 64, oy + 32 * (x + y) - 192))
    # Torchlight: dark everywhere, a pool of light round each shaft and each light pool.
    light = Image.new("L", (W, H), int(255 * dark))
    d = ImageDraw.Draw(light)
    fires = temple_lights()
    for (x, y), rec in area.items():
        if rec[6] == "x" or rec[2] == "s" or (x, y) in fires:
            px, py = ox + 64 * (x - y), oy + 32 * (x + y) + 16
            rad = 260 if rec[6] == "x" else 300 if (x, y) in fires else 90
            for k in range(12, 0, -1):
                v = int(255 * (dark + (1 - dark) * (1 - k / 12)))
                d.ellipse([px - rad * k / 12, py - rad * k / 24 - 40, px + rad * k / 12, py + rad * k / 24 - 40], fill=v)
    light = light.filter(ImageFilter.GaussianBlur(30))
    from PIL import ImageChops
    rgb = canvas.convert("RGB")
    lit = ImageChops.multiply(rgb, Image.merge("RGB", (light, light, light)))
    lit = ImageEnhance.Color(lit).enhance(0.85)
    return lit, (cx, cy)


def main():
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    tid = a[0]
    cx = int(a[1]) if len(a) > 2 else None
    cy = int(a[2]) if len(a) > 2 else None
    r = int(a[3]) if len(a) > 3 else 22
    img, (cx, cy) = render(tid, cx, cy, r)
    out = os.path.join(ROOT, "design", "art", "render_%s.png" % tid)
    img.save(out)
    print("rendered %s round %d,%d (r %d) -> %s %s" % (tid, cx, cy, r, out, img.size))


if __name__ == "__main__":
    main()
