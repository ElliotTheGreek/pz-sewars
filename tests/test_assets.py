"""Every name the mod hands the game, checked against the game.

    python tests/test_assets.py

A wrong name fails silently in Project Zomboid -- a sprite draws nothing, an
item never appears, a text key shows as itself -- so every one is checked here
against the installed build (tools/pzcatalog.py) and against our own files.
Both sides of each lookup have a floor, so an empty catalogue fails loudly
instead of passing everything (pz_trekship DEV_GUIDE, "A check against an
empty set is not a passing check").
"""
import collections
import glob
import json
import os
import re
import sys
import wave

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, "Sewars", "42", "media")
LUA = os.path.join(MEDIA, "lua")
CAT = os.path.join(ROOT, "tools", "_catalog")
PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media"
sys.path.insert(0, os.path.join(ROOT, "tools"))
from gen_sewer_art import read_tiledefs, TILEDEF_NUMBER  # noqa: E402

FAILS = []


def check(cond, what):
    print(("  ok    " if cond else "  FAIL  ") + what)
    if not cond:
        FAILS.append(what)


def lua_sources(skip_data=True):
    out = {}
    for f in glob.glob(os.path.join(LUA, "**", "*.lua"), recursive=True):
        if skip_data and os.sep + "Data" + os.sep in f:
            continue
        out[f] = open(f, encoding="utf-8").read()
    return out


def main():
    tiles = json.load(open(os.path.join(CAT, "tiles.json")))["tiles"]
    check(len(tiles) > 20000, "the vanilla tile catalogue is there (%d)" % len(tiles))
    ours = read_tiledefs(os.path.join(MEDIA, "sewars.tiles"))
    our_tiles = {"%s_%d" % (n, i): p for n, ts in ours.items() for i, p in enumerate(ts["tiles"]) if p}
    check(len(our_tiles) >= 26, "our tiledef defines its tiles (%d)" % len(our_tiles))
    for k in our_tiles:
        props = our_tiles[k]
        check(not any(p in props for p in ("ladderW", "ladderN", "ladderE", "ladderS", "IsMoveAble")),
              "%s carries no climb or pick-up property" % k) if k in ("sewars_01_0", "sewars_01_1") else None

    info = open(os.path.join(ROOT, "Sewars", "42", "mod.info")).read()
    check("pack=sewars" in info and ("tiledef=sewars %d" % TILEDEF_NUMBER) in info, "mod.info names the pack and tiledef")
    check(os.path.exists(os.path.join(MEDIA, "texturepacks", "sewars.pack")), "the texture pack is built")
    # ChooseGameInfo.readModInfoAux refuses the whole mod outside this range, and the
    # mod simply does not appear on the mods screen (0.2.0, found in play).
    check(100 <= TILEDEF_NUMBER <= 8189, "the tiledef number %d is one the engine accepts (100..8189)" % TILEDEF_NUMBER)

    # Sprites named in Lua.
    src = lua_sources()
    config = src[os.path.join(LUA, "shared", "SEW", "SEW_Config.lua")]
    sprites = set(re.findall(r'"((?:[a-z]+_)+\d+_\d+)"', config))
    check(len(sprites) > 40, "sprites found in SEW_Config (%d)" % len(sprites))
    missing = [s for s in sorted(sprites) if s not in tiles and s not in our_tiles]
    check(not missing, "every sprite in the config exists (%s)" % missing)
    gen = open(os.path.join(ROOT, "tools", "gen_sewers.py"), encoding="utf-8").read()
    fsprites = set(re.findall(r'"((?:constructedobjects|carpentry|camping)_\d+_\d+)"', gen))
    missing = [s for s in sorted(fsprites) if s not in tiles]
    check(fsprites and not missing, "every furniture sprite the generator places exists (%d, %s)" % (len(fsprites), missing))
    for s in sorted(fsprites):
        if s.startswith(("constructedobjects", "carpentry_01", "carpentry_02")):
            check("container" in tiles[s], "%s is a container (%s)" % (s, tiles[s].get("CustomName")))
    for name in ("floorTunnel", "floorVault", "floorShelter", "floorRock"):
        m = re.search(r'%s\s*=\s*"([^"]+)"' % name, config)
        check(m and "solidfloor" in tiles.get(m.group(1), {}), "%s is a solid floor" % name)
    for s in ("location_sewer_01_40", "location_sewer_01_41", "location_sewer_01_42"):
        check("solidfloor" in tiles[s], "grating %s is a solid floor" % s)
    m = re.search(r'\bsludge\s*=\s*"([^"]+)"', config)
    sludge = our_tiles.get(m.group(1)) if m else None
    check(sludge is not None and "solidfloor" not in sludge and "solidtrans" in sludge,
          "the sludge is ours, not a floor (SEW_Build lays one under it) and blocks like vanilla's")
    # Vanilla's sludge draws its water 128 px up the cell and floated over the
    # walkway (0.3.2, found in play). Ours must sit on the floor diamond.
    art = Image.open(os.path.join(ROOT, "design", "art", "tiles", "sewars_01.png")).convert("RGBA")
    i = int(m.group(1).rsplit("_", 1)[1]) if m else 0
    box = art.crop(((i % 8) * 128, (i // 8) * 256, (i % 8) * 128 + 128, (i // 8) * 256 + 256)).split()[3].getbbox()
    check(box is not None and box[1] >= 188 and box[3] <= 256,
          "the sludge is drawn on the floor diamond, not up the wall (%s)" % (box,))
    # Every tile of ours that lies on the floor is drawn in the floor pass:
    # without RenderLayer=Floor a placed puddle is drawn over whoever walks on
    # it (FBORenderCell.isObjectRenderLayer_Floor; a player's report, 0.3.1).
    from gen_sewer_art import TILES_DEF
    flat = ["%s_%d" % ("sewars_01", i) for i, (_n, kind, _p) in enumerate(TILES_DEF)
            if kind == "floor" or kind.startswith(("lower:", "copyfloor:"))]
    check(len(flat) >= 6 and all(our_tiles.get(k, {}).get("RenderLayer") == "Floor" for k in flat),
          "every floor tile of ours is drawn under characters, not over them (%d: %s)"
          % (len(flat), [k for k in flat if our_tiles.get(k, {}).get("RenderLayer") != "Floor"]))

    # Caves. Their floors are floors, their stones block nothing and are not
    # floors of their own; our earth walls are walls and our breaches door
    # frames (walked through). And every one has a picture: boulders_36..39
    # are in the catalogue with none, and would have drawn nothing.
    cave_floors = re.findall(r'"(floors_exterior_natural_01_\d+)"', config)
    stones = re.findall(r'"(boulders_\d+)"', config)
    check(len(cave_floors) >= 1 and all("solidfloor" in tiles.get(f, {}) for f in cave_floors),
          "the cave floors are solid floors (%s)" % cave_floors)
    check(len(stones) >= 4 and all(s in tiles and not {"solidfloor", "solidtrans", "solid"} & set(tiles[s])
                                   for s in stones),
          "the loose stones exist and neither block nor make a floor (%d)" % len(stones))
    try:
        from gen_sewer_art import vanilla_cells
        vanilla_cells(set(cave_floors) | set(stones))
        drawn = True
    except SystemExit as e:
        drawn = str(e)
    check(drawn is True, "every cave floor and stone has a picture in the packs (%s)" % drawn)
    wall_e = re.search(r'\be = \{ N = "([^"]+)", W = "([^"]+)", NW = "([^"]+)" \}', config)
    # The walls under them are vanilla's (with vanilla's depth): a wall of ours
    # would be drawn over characters.
    check(wall_e is not None and "WallN" in tiles.get(wall_e.group(1), {}) and "WallW" in tiles.get(wall_e.group(2), {})
          and "WallNW" in tiles.get(wall_e.group(3), {}), "the earth walls stand on vanilla walls, each on its edge")
    breach = re.findall(r'\b([oq]) = \{ N = "([^"]+)", W = "([^"]+)" \}', config)
    check(len(breach) == 2 and all(n in our_tiles and w in our_tiles for _, n, w in breach),
          "the breaches are ours, laid over vanilla's door frames (%s)" % [b[0] for b in breach])

    # Every tile of ours on a wall takes the wall's depth, and none is a wall,
    # door frame or floor itself: those are vanilla's, with vanilla's depth.
    walls = [("%s_%d" % ("sewars_01", i), kind) for i, (_n, kind, _p) in enumerate(TILES_DEF)
             if kind.startswith(("wall", "copy:", "breach:", "corner:"))]
    bad = [k for k, _ in walls if "WallOverlay" not in our_tiles.get(k, {})
           or not ({"attachedW", "attachedN"} & set(our_tiles.get(k, {})))]
    check(len(walls) >= 29 and not bad, "every wall tile of ours is drawn at the wall's depth (%d, %s)" % (len(walls), bad))
    solid = [k for k, p in our_tiles.items() if {"WallN", "WallW", "WallNW", "DoorWallN", "DoorWallW", "solidfloor"} & set(p)]
    check(not solid, "no tile of ours is itself a wall, door frame or floor (%s)" % solid)
    check(tiles["fixtures_doors_01_25"].get("doorN") == "" and tiles["fixtures_doors_01_24"].get("doorW") == "",
          "the steel doors face the way the config says")
    check("DoorWallN" in tiles["location_sewer_01_19"] and "DoorWallW" in tiles["location_sewer_01_18"],
          "the door frames are door frames")
    # The locked grilles (DESIGN.md 7, Locked gates): vanilla's cell doors, bars, each facing
    # its edge, and never hoppable (ToggleDoorActual unlocks a hoppable door).
    gate = re.search(r'\bgate\s*=\s*\{ N = "([^"]+)", W = "([^"]+)" \}', config)
    gn, gw = (tiles.get(gate.group(1), {}), tiles.get(gate.group(2), {})) if gate else ({}, {})
    check(gate and "doorN" in gn and "doorW" in gw and gn.get("Material2") == gw.get("Material2") == "MetalBars"
          and "Hoppable" not in gn and "Hoppable" not in gw,
          "the gates are barred doors facing the way the config says (%s)" % (gate.groups() if gate else None,))

    # Items.
    items = json.load(open(os.path.join(CAT, "items.json")))
    known = {"%s.%s" % (m, n) for m, ns in items.items() for n in ns}
    check(len(known) > 5000, "the item catalogue is there (%d)" % len(known))
    ids = set(re.findall(r'"(Base\.[A-Za-z0-9_]+)"', config))
    check(len(ids) > 40, "item ids in the config (%d)" % len(ids))
    missing = sorted(i for i in ids if i not in known)
    check(not missing, "every item exists (%s)" % missing)
    obsolete = []
    scripts = "\n".join(open(f, encoding="utf-8", errors="replace").read()
                        for f in glob.glob(os.path.join(PZ, "scripts", "**", "*.txt"), recursive=True))
    for i in sorted(ids):
        m = re.search(r"\bitem\s+%s\s*\{(.*?)\n\s*\}" % re.escape(i.split(".")[1]), scripts, re.S)
        if m and re.search(r"Obsolete\s*=\s*true", m.group(1), re.I):
            obsolete.append(i)
    check(not obsolete, "no item is obsolete (instanceItem answers nil for those) (%s)" % obsolete)

    # Our own items: every one named in the config is declared, has its icon on
    # disk, a translated name and a translated tooltip.
    ours = {}
    for f in glob.glob(os.path.join(MEDIA, "scripts", "*.txt")):
        script = open(f, encoding="utf-8").read()
        mod = re.search(r"module\s+(\w+)", script)
        for name, body in re.findall(r"^\s*item\s+(\w+)\s*\{(.*?)\n\s*\}", script, re.M | re.S):
            ours["%s.%s" % (mod.group(1), name)] = body
    named = set(re.findall(r'"(Sewars\.\w+)"', config))
    check(len(named) >= 2 and named <= set(ours), "every mod item in the config is declared (%s)" % sorted(named - set(ours)))
    names_json = json.load(open(os.path.join(LUA, "shared", "Translate", "EN", "ItemName.json"), encoding="utf-8"))
    tips_json = json.load(open(os.path.join(LUA, "shared", "Translate", "EN", "Tooltip.json"), encoding="utf-8"))
    key = ours.get(re.search(r'C\.KeyItem\s*=\s*"([^"]+)"', config).group(1), "")
    check("ItemType = base:key" in key and "base:buildingkey" not in key,
          "the maintenance key is a key (haveThisKeyId counts it) and not a building key (loot would re-key it)")
    for full, body in sorted(ours.items()):
        icon = re.search(r"Icon\s*=\s*(\w+)", body)
        tip = re.search(r"Tooltip\s*=\s*(\w+)", body)
        check(icon and os.path.exists(os.path.join(MEDIA, "textures", "Item_%s.png" % icon.group(1))),
              "%s has its icon on disk" % full)
        check(full in names_json, "%s has a translated name" % full)
        check(not tip or tip.group(1) in tips_json, "%s's tooltip is translated" % full)

    # Outfits.
    x = open(os.path.join(PZ, "clothing", "clothing.xml"), encoding="utf-8").read()
    fem = set(re.findall(r"<m_Name>([^<]+)</m_Name>", x[x.find("<m_FemaleOutfits>"):x.find("<m_MaleOutfits>")]))
    male = set(re.findall(r"<m_Name>([^<]+)</m_Name>", x[x.find("<m_MaleOutfits>"):]))
    check(len(fem) > 50 and len(male) > 50, "both outfit lists read (%d, %d)" % (len(fem), len(male)))
    ordinary = re.findall(r'"([^"]+)"', re.search(r"C\.Outfits\s*=\s*\{([^}]*)\}", config).group(1))
    equipped = re.findall(r'"([^"]+)"', re.search(r"C\.OutfitsEquipped\s*=\s*\{([^}]*)\}", config).group(1))
    gen_dead = set(re.findall(r'dead\.append\(\(x0 \+ x, y0 \+ y, \(([^)]*)\)', gen))
    gen_dead = sorted({o for group in gen_dead for o in re.findall(r'"([^"]+)"', group)})
    check(len(gen_dead) >= 3, "the generator's shelter and hideout dead read (%s)" % gen_dead)
    outfits = ordinary + equipped + gen_dead
    bad = sorted({o for o in outfits if o not in fem or o not in male})
    check(ordinary and equipped and not bad, "every outfit is in both of vanilla's lists (%s)" % bad)
    # What each outfit can be dressed in, by the file guid table: an ordinary
    # outfit carries no bag, an equipped one does (a player's report, 0.3.2:
    # "they all carry something"), and every bag the generator's dead could
    # carry is one SEW_Build.dress can take away.
    guid = {}
    for block in open(os.path.join(PZ, "fileGuidTable.xml"), encoding="utf-8", errors="ignore").read().split("<files>")[1:]:
        p, g = re.search(r"<path>(.*?)</path>", block), re.search(r"<guid>(.*?)</guid>", block)
        if p and g:
            guid[g.group(1)] = os.path.basename(p.group(1))
    bags = collections.defaultdict(set)
    for _sex, body in re.findall(r"<m_(Male|Female)Outfits>(.*?)</m_\1Outfits>", x, re.S):
        name = re.search(r"<m_Name>(.*?)</m_Name>", body).group(1)
        for g in re.findall(r"<itemGUID>([^<]*)</itemGUID>", body):
            if guid.get(g, "").startswith("Bag_"):
                bags[name].add(guid[g])
    check(len(guid) > 1000 and bags, "the guid table and the outfits' bags read (%d, %d)" % (len(guid), len(bags)))
    carry = sorted(o for o in ordinary if bags[o])
    check(not carry, "no ordinary outfit carries a bag (%s)" % carry)
    empty = sorted(o for o in equipped if not bags[o])
    check(not empty, "every equipped outfit does (%s)" % empty)
    loose = sorted(o for o in gen_dead if bags[o] and o not in equipped)
    check(not loose, "every generator outfit with a bag is one the build can undress (%s)" % loose)

    # Sounds, both ways.
    decl = open(os.path.join(MEDIA, "scripts", "sewars_sounds.txt")).read()
    declared = set(re.findall(r"sound\s+(\w+)", decl))
    files = set(re.findall(r"file\s*=\s*media/sound/(\w+)\.wav", decl))
    for f in files:
        p = os.path.join(MEDIA, "sound", f + ".wav")
        ok = os.path.exists(p)
        if ok:
            with wave.open(p) as w:
                ok = w.getnframes() > 1000
        check(ok, "sound file %s.wav is there and not empty" % f)
    vanilla_sounds = set(re.findall(r"^\s*sound\s+(\w+)", scripts, re.M))
    used = set()
    for s in src.values():
        used |= set(re.findall(r'play(?:Sound|SoundLocal)\("(\w+)"\)', s))
        # Picked by who is coughing: `playSound(female and "VoiceFemaleCough" or ...)`.
        used |= set(re.findall(r'"(Voice\w+)"', s))
        used |= set(re.findall(r'"(SEW_\w+)"', s)) & (declared | {"SEW_Lid", "SEW_Ladder", "SEW_Drip", "SEW_Groan"})
    used |= set(re.findall(r'"([A-Z]\w+)"', re.search(r"C\.Ambience\s*=\s*\{([^}]*)\}", config).group(1)))
    unknown = sorted(u for u in used if u not in declared and u not in vanilla_sounds)
    check(used and not unknown, "every sound played is declared (%d; %s)" % (len(used), unknown))
    unused = sorted(declared - used - {"SEW_Lid", "SEW_Ladder"})
    check(not unused, "every sound declared is played (%s)" % unused)

    # Translations: keys by category, both ways.
    cats = {}
    for f in glob.glob(os.path.join(LUA, "shared", "Translate", "EN", "*.json")):
        cats[os.path.basename(f)[:-5]] = json.load(open(f, encoding="utf-8"))
    prefix = {"ContextMenu": "ContextMenu_", "Tooltip": "Tooltip_", "IG_UI": "IGUI_", "Sandbox": "Sandbox_"}
    for cat, keys in cats.items():
        if cat == "ItemName":
            # Keyed by the bare full id, no prefix (pz_trekship DEV_GUIDE, "Translations").
            bad = [k for k in keys if k not in ours]
        else:
            bad = [k for k in keys if not k.startswith(prefix.get(cat, "?"))]
        check(not bad, "%s.json holds only %s keys (%s)" % (cat, prefix.get(cat, "item id"), bad))
    allkeys = {k for keys in cats.values() for k in keys}
    used = set(ours)                                   # item names
    for body in ours.values():                         # item tooltips
        used |= set(re.findall(r"Tooltip\s*=\s*(\w+)", body))
    for s in src.values():
        # A literal ending in "_" is the front of an assembled key, not a key.
        used |= {k for k in re.findall(r'"((?:ContextMenu|Tooltip|IGUI)_SEW_\w+)"', s) if not k.endswith("_")}
    # Assembled keys, written out whole from the data they are assembled from
    # (pz_trekship DEV_GUIDE, "An id assembled from parts is invisible to a
    # static check"): SEW_StoryUI.page and SEW_Map's shelter labels.
    index = open(os.path.join(LUA, "shared", "SEW", "SEW_Index.lua"), encoding="utf-8").read()
    texts = set(re.findall(r'J\[#J\+1\]=\{[^}]*text="(\w+)"', index))
    kinds = set(re.findall(r'H\[#H\+1\]=\{[^}]*kind="(\w+)"', index))
    check(len(texts) >= 5 and len(kinds) >= 4, "journal texts and shelter kinds read from the index (%d, %d)"
          % (len(texts), len(kinds)))
    for t in texts:
        used |= {"IGUI_SEW_J_%s_Title" % t, "IGUI_SEW_J_%s_Body" % t}
    # The dev build's menu: "ContextMenu_SEW_Dev_" .. each stop it lists.
    client = src[os.path.join(LUA, "client", "SEW", "SEW_Client.lua")]
    stops = re.search(r'for _, what in ipairs\(\{([^}]*)\}\) do\s*sub:addOption', client)
    check(stops is not None, "the dev menu's stops read from SEW_Client")
    if stops:
        used |= {"ContextMenu_SEW_Dev_%s" % w for w in re.findall(r'"(\w+)"', stops.group(1))}
    used |= {"IGUI_SEW_Shelter_%s" % k for k in kinds}
    gen = open(os.path.join(ROOT, "tools", "gen_sewers.py"), encoding="utf-8").read()
    variants = dict(re.findall(r'"(\w+)": (\d+)', re.search(r"JOURNAL_VARIANTS = \{([^}]*)\}", gen).group(1)))
    for kind, n in variants.items():
        for v in range(1, int(n) + 1):
            used |= {"IGUI_SEW_J_%s_%d_Title" % (kind, v), "IGUI_SEW_J_%s_%d_Body" % (kind, v)}
    stray = sorted(k for keys in cats.values() for k, v in keys.items()
                   if re.search(r"%(?!\d)", v) or re.search(r"%\d%", v))
    check(not stray, "no text has a literal %% beside a placeholder -- the translator breaks it (%s)" % stray)
    missing = sorted(used - allkeys)
    check(used and not missing, "every text key the Lua uses is translated (%d; %s)" % (len(used), missing))
    unused = sorted(k for k in allkeys - used if not k.startswith("Sandbox_"))
    check(not unused, "every translated key is used (%s)" % unused)
    sb = open(os.path.join(MEDIA, "sandbox-options.txt")).read()
    for opt, n in re.findall(r"option\s+([\w.]+)\s*=\s*\{\s*type\s*=\s*enum,\s*numValues\s*=\s*(\d+)", sb):
        for i in range(1, int(n) + 1):
            check("Sandbox_%s_option%d" % (opt, i) in allkeys, "sandbox %s option %d has words" % (opt, i))
        check("Sandbox_%s" % opt in allkeys and "Sandbox_%s_tooltip" % opt in allkeys, "sandbox %s has a name and a tooltip" % opt)

    # Guards on line one.
    for f, s in lua_sources(skip_data=False).items():
        first = next((l for l in s.splitlines() if l.strip() and not l.startswith("--")), "")
        side = "server" if os.sep + "server" + os.sep in f else "client" if os.sep + "client" + os.sep in f else "shared"
        if side == "server":
            check("if isClient() then return end" in s.split("\n\n")[0] or first.startswith("if isClient()")
                  or "if isClient() then return end" in s[:4000],
                  "%s returns on a client" % os.path.relpath(f, LUA))
        elif side == "client":
            check("if isServer() then return end" in s[:4000], "%s returns on a server" % os.path.relpath(f, LUA))
    data = glob.glob(os.path.join(LUA, "server", "SEW", "Data", "*.lua"))
    check(len(data) >= 10, "town data is generated (%d towns)" % len(data))

    # No role-gated or debug-only calls (pz_trekship DEV_GUIDE, "The jar is not the API").
    for f, s in src.items():
        # Code only: a comment explaining why a call is not made is not the call.
        s = re.sub(r"--\[\[.*?\]\]", "", s, flags=re.S)
        s = "\n".join(line.split("--", 1)[0] for line in s.splitlines())
        for bad in ("setGodMod", "setInvincible", "setNoClip", "setInvisible", "setGodModCheat",
                    "InventoryItemFactory", "table.unpack", "math.huge", "addFloor("):
            if bad in s:
                check(False, "%s calls %s" % (os.path.relpath(f, LUA), bad))

    print()
    if FAILS:
        print("%d FAILED" % len(FAILS))
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
