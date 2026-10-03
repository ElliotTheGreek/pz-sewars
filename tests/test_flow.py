"""The whole loop, run for real against the simulated engine (tests/sim.lua).

    python tests/test_flow.py

Single player, then a server with a client over a simulated network:

  * a cover in Muldraugh offers *Climb down*; choosing it walks, runs the
    timed action, the server builds the tunnel under the cover and only then
    sends `go`, and the client steps down onto a floor its own world has;
  * the vault switch is on below and off above;
  * the tunnel round the player is built as they stand there; nothing is
    placed twice on a second pass; furniture is stocked and explored; the dead
    are put down, none of them on top of the player;
  * a ladder offers *Climb out*, which brings them up on the cover;
  * a cover over a building offers a greyed option and moves nobody;
  * a player below with no floor is rescued to the nearest ladder;
  * a square underground that already holds somebody else's object is left
    alone;
  * on a server: the client edits nothing, the guards keep each side's files
    to their side, and the timed action survives being rebuilt by name.

It fails on any WARN the mod logs that the test did not provoke on purpose,
any sprite or text key the game does not have, and any outfit or item the
build does not know.
"""
import glob
import json
import os
import re
import sys

from lupa import LuaRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "Sewars", "42", "media", "lua")
CAT = os.path.join(ROOT, "tools", "_catalog")
PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media"
sys.path.insert(0, os.path.join(ROOT, "tools"))

FAILS = []


def check(cond, what):
    print(("  ok    " if cond else "  FAIL  ") + what)
    if not cond:
        FAILS.append(what)


# --- what the game has -----------------------------------------------------------------------

def facts():
    from gen_sewer_art import read_tiledefs
    tiles = json.load(open(os.path.join(CAT, "tiles.json")))["tiles"]
    ours = read_tiledefs(os.path.join(ROOT, "Sewars", "42", "media", "sewars.tiles"))
    for name, ts in ours.items():
        for i, props in enumerate(ts["tiles"]):
            if props:
                tiles["%s_%d" % (name, i)] = props
    items = set()
    for mod, names in json.load(open(os.path.join(CAT, "items.json"))).items():
        items |= {"%s.%s" % (mod, n) for n in names}
    # And our own, from our scripts: an id the game would not know stays unknown.
    for f in glob.glob(os.path.join(ROOT, "Sewars", "42", "media", "scripts", "*.txt")):
        src = open(f, encoding="utf-8").read()
        mod = re.search(r"module\s+(\w+)", src)
        if mod:
            items |= {"%s.%s" % (mod.group(1), n) for n in re.findall(r"^\s*item\s+(\w+)", src, re.M)}
    x = open(os.path.join(PZ, "clothing", "clothing.xml"), encoding="utf-8").read()
    fem = set(re.findall(r"<m_Name>([^<]+)</m_Name>", x[x.find("<m_FemaleOutfits>"):x.find("<m_MaleOutfits>")]))
    male = set(re.findall(r"<m_Name>([^<]+)</m_Name>", x[x.find("<m_MaleOutfits>"):]))
    text = {}
    for f in glob.glob(os.path.join(LUA, "shared", "Translate", "EN", "*.json")):
        text.update(json.load(open(f, encoding="utf-8")))
    return tiles, items, fem & male, text


TILES, ITEMS, OUTFITS, TEXT = facts()


def lua_files():
    out = []
    for side in ("shared", "client", "server"):
        for f in sorted(glob.glob(os.path.join(LUA, side, "**", "*.lua"), recursive=True)):
            if os.sep + "Translate" + os.sep in f:
                continue
            out.append(os.path.relpath(f, os.path.join(LUA, side))[:-4].replace(os.sep, "/"))
    return out


def process(role):
    L = LuaRuntime(unpack_returned_tuples=True)
    g = L.globals()
    g.SIM_ROLE = role
    L.execute("SIM = {}")
    sim = g.SIM
    sim.root = LUA.replace("\\", "/")
    sim.pzLua = (PZ + "/lua").replace("\\", "/")
    sim.tiles = L.table_from({k: L.table_from(v) for k, v in TILES.items()})
    sim.items = L.table_from({k: True for k in ITEMS})
    sim.outfits = L.table_from({k: True for k in OUTFITS})
    sim.text = L.table_from(TEXT)
    L.execute(open(os.path.join(ROOT, "tests", "sim.lua"), encoding="utf-8").read())
    for name in lua_files():
        g.require(name)
    return L


def warns(L, allowed=()):
    out = []
    log = L.globals().SIM.log
    for i in range(1, len(log) + 1):
        line = log[i]
        if "WARN" in line and not any(a in line for a in allowed):
            out.append(line)
    return out


def lua_list(t):
    return [t[i] for i in range(1, len(t) + 1)] if t else []


# --- the world ---------------------------------------------------------------------------------

def pick_shafts(L, town="muldraugh"):
    shafts = L.globals().SEW.Index.shafts
    out = []
    for k in shafts.keys():
        s = shafts[k]
        if s.town == town and not s.hatch:
            out.append((s.x, s.y, s.lx, s.ly, s.street))
    return sorted(out)


def street(L, x, y, r, manhole=True):
    """The street at z 0 round a cover: floor everywhere near, the cover on it."""
    sim = L.globals().SIM
    for cx in range((x - 80) // 8, (x + 80) // 8 + 1):
        for cy in range((y - 80) // 8, (y + 80) // 8 + 1):
            sim.load(cx, cy)
    L.execute("""
        local x, y, r, manhole = ...
        for dx = -r, r do for dy = -r, r do
            local sq = getCell():getOrCreateGridSquare(x + dx, y + dy, 0)
            if #sq.objects._t == 0 then
                sq.objects:add(IsoObject.new(sq, "floors_exterior_street_01_0", ""))
            end
        end end
        if manhole then
            local sq = getCell():getGridSquare(x, y, 0)
            sq.objects:add(IsoObject.new(sq, "street_decoration_01_15", ""))
        end
    """.replace("local x, y, r, manhole = ...", "local x, y, r, manhole = %d, %d, %d, %s" % (x, y, r, "true" if manhole else "false")))
    sim.violations = L.table()


def menu(L, player_index, x, y):
    sim = L.globals().SIM
    m = sim.newMenu(x, y)
    sim.fire("OnFillWorldObjectContextMenu", player_index, m, L.table(), False)
    return m


def options(m):
    return [(o.name, o) for o in lua_list(m.options)]


def choose(m, name):
    for n, o in options(m):
        if n == name:
            args = o.args
            o.onSelect(o.target, args[1], args[2], args[3])
            return True
    return False


def objects_at(L, x, y, z):
    sq = L.globals().SIM.squares["%d,%d,%d" % (x, y, z)]
    if not sq:
        return []
    out = []
    for i in range(1, len(sq.objects._t) + 1):
        o = sq.objects._t[i]
        out.append(o.sprite.getName())
        # and what hangs on it (SEW_Build, "Pictures on walls")
        if o.attached is not None:
            out += [o.attached._t[j].getParentSprite().getName() for j in range(1, len(o.attached._t) + 1)]
    return out


def count_ours(L):
    return L.execute("""
        local n = 0
        for _, sq in pairs(SIM.squares) do
            for _, o in ipairs(sq.objects._t) do if o.md and o.md.sew then n = n + 1 end end
        end
        return n
    """)


# --- single player -----------------------------------------------------------------------------

def lair_test(L, p):
    """The rats' nest under Louisville (0.5): built with its town, found by
    its false wall, the rodents of unusual size in it, the hoard shut until
    the last of them is dead."""
    g = L.globals()
    sim, SEW = g.SIM, g.SEW
    lair = SEW.Index.lair
    check(lair is not None, "the index has the rats' nest")
    if lair is None:
        return
    check(SEW.Rats.defined is True, "the ROUS is defined on vanilla's rat")
    d = g.AnimalDefinitions.animals.rous
    # The rat's own animation set: a mod's action group is never loaded, and an
    # animal without one stands still (found in play, 0.5).
    check(d is not None and d.animset == "rat" and d.wild is False and d.alwaysFleeHumans is False
          and d.minSize > 2 and d.hungerMultiplier == 0,
          "a ROUS moves as a rat, stands its ground and is large (%s)" % ((d.animset, d.minSize) if d else None,))
    check(g.AnimalDefinitions.animals.rat.animset == "rat" and g.AnimalDefinitions.animals.rat.minSize < 1,
          "vanilla's rat is left as it was")
    tx, ty, ex, ey, gx, gy, vx, vy = lair.tx, lair.ty, lair.ex, lair.ey, lair.gx, lair.gy, lair.vx, lair.vy
    cx, cy = lair.x, lair.y
    # A fresh world: everything round the nest loaded and built, as walking
    # there would. Rats off, so only the nest's own are counted.
    L.execute("SandboxVars.Sewars.Rats = 1")
    keys = L.execute("""
        local x0, y0, x1, y1 = ...
        local B = SEW.Build
        local keys = {}
        for kx = math.floor(x0 / 8) - 2, math.floor(x1 / 8) + 2 do
            for ky = math.floor(y0 / 8) - 2, math.floor(y1 / 8) + 2 do
                SIM.load(kx, ky)
                local k = kx .. "," .. ky
                if B.townOf(k) then keys[#keys + 1] = k end
            end
        end
        for _, k in ipairs(keys) do B.chunk(k) end
        return keys
    """, min(tx, cx, vx) - 8, min(ty, cy, vy) - 8, max(tx, cx, vx) + 8, max(ty, cy, vy) + 8)

    def rous():
        return L.execute("""
            local n, alive = 0, 0
            for _, a in ipairs(SIM.animals) do
                if a.kind == "rous" then
                    n = n + 1
                    if not a.dead then alive = alive + 1 end
                end
            end
            return n, alive
        """)
    n, alive = rous()
    want = len(lua_list(lair.rous)) // 2
    check(n == want and alive == want, "the nest's rodents are put down, %d of %d" % (n, want))
    placed = L.execute("""
        local ok = true
        for _, a in ipairs(SIM.animals) do
            if a.kind == "rous" then ok = ok and a.inWorld and a.size == SEW.Config.Rous.size and a.z == -1 end
        end
        return ok
    """)
    check(placed is True, "each handed to the world, at its size, below ground")
    ex_rec = max(tx, ex), max(ty, ey)
    here = objects_at(L, ex_rec[0], ex_rec[1], -1)
    C = SEW.Config
    cracks = [C.Sprites.cracks.N, C.Sprites.cracks.W]
    frames = [C.Sprites.doorFrame.N, C.Sprites.doorFrame.W]
    check(any(c in here for c in cracks) and not any(f in here for f in frames),
          "the false wall is a wall, with its cracks and gnawed hole (%s)" % here)
    hoard = L.execute("""
        local x, y, w, h = ...
        local pieces, stocked, gold = 0, 0, false
        for px = x, x + w - 1 do for py = y, y + h - 1 do
            local sq = SIM.squares[px .. "," .. py .. ",-1"]
            for _, o in ipairs(sq and sq.objects._t or {}) do
                local c = SEW.Util.containerOf(o)
                if c then
                    pieces = pieces + 1
                    if c:getItems():size() > 0 then stocked = stocked + 1 end
                    for _, it in ipairs(c:getItems()._t) do
                        local t = it:getType()
                        if t == "GoldBar" or t == "SilverBar" or t == "Diamond" or t == "GoldCoin" then gold = true end
                    end
                end
            end
        end end
        return pieces, stocked, gold
    """, lair.hoard[1], lair.hoard[2], lair.hoard[3], lair.hoard[4])
    check(hoard[0] >= 6 and hoard[1] == hoard[0] and hoard[2],
          "the hoard: %d pieces, %d stocked, something that glitters %s" % hoard)

    # Below, at the false wall: it offers to be pulled away.
    p.x, p.y, p.z = tx + 0.5, ty + 0.5, -1
    sim.players = L.table(p)
    m = menu(L, 0, ex, ey)
    names = [nm for nm, _ in options(m)]
    check(TEXT["ContextMenu_SEW_PryWall"] in names, "the false wall offers Pull at the loose bricks (%s)" % names)
    m2 = menu(L, 0, tx + 6, ty + 6)
    check(TEXT["ContextMenu_SEW_PryWall"] not in [nm for nm, _ in options(m2)], "and nowhere else does")
    # From too far, the server says no (the action's own reach check aside).
    far = L.execute("""
        local p = SIM.players[1]
        local x, y = p.x, p.y
        p.x, p.y = x + 8, y + 8
        local ok = SEW.Nest.pry(p, "wall")
        p.x, p.y = x, y
        return ok, SEW.Build.gateOpen("wall")
    """)
    check(far[0] is False and far[1] is False, "the server refuses a pull from out of reach")
    choose(m, TEXT["ContextMenu_SEW_PryWall"])
    sim.runActions()
    sim.tickN(2)
    here = objects_at(L, ex_rec[0], ex_rec[1], -1)
    breach = [C.Sprites.breach.o.N, C.Sprites.breach.o.W, C.Sprites.breach.q.N, C.Sprites.breach.q.W]
    check(any(f in here for f in frames) and any(b in here for b in breach) and not any(c in here for c in cracks),
          "pulled away: a breach where the wall was, the cracks gone with it (%s)" % here)
    check(TEXT["ContextMenu_SEW_PryWall"] not in [nm for nm, _ in options(menu(L, 0, ex, ey))],
          "an open wall offers nothing more")
    notes = lua_list(sim.notes)
    check(any("bricks come away" in nt for nt in notes), "and says what is behind it (%s)" % notes[-1:])

    # Into the nest: they wake and come for whoever is there. The sim's engine
    # path does nothing below ground, so they are walked by hand -- and never
    # through a wall.
    p.x, p.y = cx + 0.5, cy + 3.5
    before = L.execute("""
        local t = 0
        for _, a in ipairs(SIM.animals) do
            if a.kind == "rous" then t = t + math.sqrt((a.x - SIM.players[1].x)^2 + (a.y - SIM.players[1].y)^2) end
        end
        return t
    """)
    p.wounds, p.damage = L.table(), 0
    walls = L.execute("""
        local bad = 0
        for _ = 1, 600 do
            SIM.tickN(1)
            for _, a in ipairs(SIM.animals) do
                if a.kind == "rous" and not (a.square and SEW.Util.floorOf(a.square)) then bad = bad + 1 end
            end
        end
        return bad
    """)
    hunted = L.execute("""
        local t, near, pathed = 0, 0, 0
        for _, a in ipairs(SIM.animals) do
            if a.kind == "rous" then
                local d = math.sqrt((a.x - SIM.players[1].x)^2 + (a.y - SIM.players[1].y)^2)
                t = t + d
                if d <= SEW.Config.Rous.reach + 0.05 then near = near + 1 end
                if (a.pathed or 0) > 0 then pathed = pathed + 1 end
            end
        end
        return t, near, pathed
    """)
    check(hunted[2] == want, "each is sent after the player on the engine's path first (%d)" % hunted[2])
    check(hunted[0] < before * 0.4 and hunted[1] >= 1,
          "then walked to them by hand (%.1f squares between them all, from %.1f; %d at their heels)"
          % (hunted[0], before, hunted[1]))
    check(walls == 0, "and never off the floor, through a wall (%d)" % walls)
    wounds = len(lua_list(p.wounds))
    check(wounds >= 2 and (p.damage or 0) > 0, "they bite: %d wounds, %s damage" % (wounds, p.damage))
    notes = lua_list(sim.notes)
    check(any("bites" in nt for nt in notes), "and the player is told (%s)" % notes[-1:])

    # A wall stops them: a player in the hoard, behind the gnawed wall that is
    # still shut, draws them straight at it -- and not one goes through. (The
    # chase above never met a wall; this guard went untested until 0.5's
    # full mutation run said so.)
    # At the back of it: right behind the wall they would stop to bite.
    far = max(((x, y) for x in range(lair.hoard[1], lair.hoard[1] + lair.hoard[3])
               for y in range(lair.hoard[2], lair.hoard[2] + lair.hoard[4])),
              key=lambda q: abs(q[0] - gx) + abs(q[1] - gy))
    p.x, p.y = far[0] + 0.5, far[1] + 0.5
    through = L.execute("""
        local hx, hy, hw, hh = ...
        local n = 0
        for _ = 1, 400 do
            SIM.tickN(1)
            for _, a in ipairs(SIM.animals) do
                if a.kind == "rous" and a.x >= hx and a.x < hx + hw and a.y >= hy and a.y < hy + hh then n = n + 1 end
            end
        end
        return n
    """, lair.hoard[1], lair.hoard[2], lair.hoard[3], lair.hoard[4])
    check(through == 0, "a shut wall stops them: none walks through the gnawed wall into the hoard (%d)" % through)
    # Every weapon hit in the game comes through the hit logger: a zombie or a
    # player has no getAnimalType, and asking threw (found in play: a stack
    # trace under -debug on every swing at a zombie).
    hits = L.execute("""
        local before = #SIM.log
        local z = SIM.newZombie(0, 0, 0, "Hobbo")
        local weapon = { getType = function() return "Crowbar" end }
        SIM.fire("OnWeaponHitCharacter", SIM.players[1], z, weapon, 1)
        SIM.fire("OnWeaponHitCharacter", SIM.players[1], SIM.players[1], weapon, 1)
        local rous
        for _, a in ipairs(SIM.animals) do if a.kind == "rous" then rous = a break end end
        SIM.fire("OnWeaponHitCharacter", SIM.players[1], rous, weapon, 1)
        local warn, logged = 0, 0
        for i = before + 1, #SIM.log do
            if SIM.log[i]:find("WARN") then warn = warn + 1 end
            if SIM.log[i]:find("a ROUS was hit") then logged = logged + 1 end
        end
        return warn, logged
    """)
    check(hits[0] == 0 and hits[1] == 1,
          "a hit on a zombie or a player is let be; a hit on a ROUS is logged (%d WARN, %d logged)" % tuple(hits))
    # And right behind it, a step away: no bite through brick.
    p.x, p.y = vx + 0.5, vy + 0.5
    p.wounds = L.table()
    sim.tickN(300)
    check(len(lua_list(p.wounds)) == 0, "nor bites through it (%d wounds)" % len(lua_list(p.wounds)))

    # The gnawed wall: not while any of them lives.
    p.x, p.y = gx + 0.5, gy + 0.5
    m = menu(L, 0, vx, vy)
    check(TEXT["ContextMenu_SEW_PryGate"] in [nm for nm, _ in options(m)], "the gnawed wall offers to be torn through")
    choose(m, TEXT["ContextMenu_SEW_PryGate"])
    sim.runActions()
    sim.tickN(2)
    check(L.execute("return SEW.Build.gateOpen('gate')") is False, "and will not give while they live")
    notes = lua_list(sim.notes)
    check(any("still breathing" in nt for nt in notes), "the player is told why (%s)" % notes[-1:])
    # One dead is not all of them.
    L.execute("for _, a in ipairs(SIM.animals) do if a.kind == 'rous' then a.dead = true break end end")
    check(L.execute("return SEW.Nest.pry(SIM.players[1], 'gate')") is False, "nor with one of them still alive")
    L.execute("for _, a in ipairs(SIM.animals) do if a.kind == 'rous' then a.dead = true end end")
    p.x, p.y = cx + 0.5, cy + 0.5
    sim.tickN(SEW.Config.Rous.every * 2)
    notes = lua_list(sim.notes)
    check(any("nest is still" in nt for nt in notes), "the last one dead, the nest goes quiet (%s)" % notes[-1:])
    p.x, p.y = gx + 0.5, gy + 0.5
    choose(menu(L, 0, vx, vy), TEXT["ContextMenu_SEW_PryGate"])
    sim.runActions()
    sim.tickN(2)
    gate = objects_at(L, max(gx, vx), max(gy, vy), -1)
    check(L.execute("return SEW.Build.gateOpen('gate')") is True and any(f in gate for f in frames)
          and any(b in gate for b in breach), "then it gives, into the hoard (%s)" % gate)

    # A later revision puts back no rodent and no crate, and shuts nothing.
    L.execute("""
        local keys = ...
        local s = SEW.Build.state()
        for _, k in ipairs(keys) do s.built[k] = "older" end
        for _, k in ipairs(keys) do SEW.Build.chunk(k) end
    """, keys)
    n2, _ = rous()
    hoard2 = L.execute("""
        local x, y, w, h = ...
        local pieces = 0
        for px = x, x + w - 1 do for py = y, y + h - 1 do
            local sq = SIM.squares[px .. "," .. py .. ",-1"]
            for _, o in ipairs(sq and sq.objects._t or {}) do if SEW.Util.containerOf(o) then pieces = pieces + 1 end end
        end end
        return pieces
    """, lair.hoard[1], lair.hoard[2], lair.hoard[3], lair.hoard[4])
    here = objects_at(L, ex_rec[0], ex_rec[1], -1)
    check(n2 == want and hoard2 == hoard[0] and any(f in here for f in frames),
          "a later pass: no second rodent (%d), no second crate (%d), the walls stay open" % (n2, hoard2))
    # And asked again directly -- the chunk's caves-done mark would otherwise
    # hide the rodents' own record (DEV_GUIDE, "Two guards that cover each other").
    again = L.execute("""
        local L, made = SEW.Index.lair, 0
        for i = 1, #L.rous, 2 do
            made = made + SEW.Nest.lairChunk(math.floor(L.rous[i] / 8) .. "," .. math.floor(L.rous[i + 1] / 8))
        end
        return made
    """)
    check(again == 0, "a nest chunk visited again puts down no rodent twice (%d)" % again)
    L.execute("SandboxVars.Sewars.Rats = nil")


def dev_menu_test(L, p):
    """The dev build's right-click menu: the author never types in the debug
    console, so every place a test needs is a click away -- and none of it
    outside the dev build."""
    g = L.globals()
    sim, SEW = g.SIM, g.SEW
    C = SEW.Config
    p.x, p.y, p.z = 10700.5, 9900.5, 0
    street(L, 10700, 9900, 2, manhole=False)
    check(TEXT["ContextMenu_SEW_Dev"] not in [n for n, _ in options(menu(L, 0, 10700, 9900))],
          "no dev menu outside the dev build")
    SEW.Dev = True
    m = menu(L, 0, 10700, 9900)
    top = [o for n, o in options(m) if n == TEXT["ContextMenu_SEW_Dev"]]
    check(len(top) == 1 and top[0].subMenu is not None, "the dev build's right-click menu has Sewers (dev)")
    if not top or top[0].subMenu is None:
        SEW.Dev = None
        return
    sub = top[0].subMenu
    names = [n for n, _ in options(sub)]
    check(len(names) == 12, "with its twelve stops (%s)" % names)

    # As the game does it: nothing is loaded where a trip lands until the
    # player is there (found in play: every trip was rescued to a ladder).
    L.execute("""
        for _, key in ipairs({ "gas", "gates" }) do
            for _, g in ipairs(SEW.Index[key]) do
                if g.town == SEW.Config.DevStartTown then
                    for dx = -3, 3 do for dy = -3, 3 do SIM.unload(math.floor(g.x / 8) + dx, math.floor(g.y / 8) + dy) end end
                end
            end
        end
        SIM.streamRadius = 3
    """)
    log0 = len(lua_list(sim.log))

    def pick(key):
        choose(sub, TEXT["ContextMenu_SEW_Dev_" + key])
        sim.tickN(120)
    pick("gas")
    check(p.z == -1 and L.execute("return SEW.Gas.at(%f, %f) ~= nil" % (p.x, p.y))
          and L.execute("return SEW.Util.floorOf(SIM.players[1]:getCurrentSquare()) ~= nil"),
          "Go into sewer gas puts you in a stretch, on its floor (%.1f,%.1f,%.1f)" % (p.x, p.y, p.z))
    first = (p.x, p.y)
    pick("gas")
    check((p.x, p.y) != first and L.execute("return SEW.Gas.at(%f, %f) ~= nil" % (p.x, p.y)),
          "and again, the next stretch")
    L.execute("SIM.players[1].stats = { POISON = 7 }")
    pick("poison")
    check(any("poison 7" in n for n in lua_list(sim.notes)[-2:]), "How poisoned am I says so (%s)" % lua_list(sim.notes)[-1:])
    pick("gate")
    near = L.execute("""
        local p = SIM.players[1]
        for _, g in ipairs(SEW.Index.gates) do
            if math.abs(g.x - p.x) <= 2 and math.abs(g.y - p.y) <= 2 then return true end
        end
        return false
    """)
    check(p.z == -1 and near, "Go to a locked gate puts you beside one (%.1f,%.1f)" % (p.x, p.y))
    pick("key")
    has = L.execute("""
        for _, it in ipairs(SIM.players[1].inv.items._t) do
            if it:getFullType() == SEW.Config.KeyItem and it:getKeyId() == SEW.Index.towns[SEW.Config.DevStartTown].key then
                return true
            end
        end
        return false
    """)
    check(has, "Give me this town's key does")
    pick("outfall")
    o = L.execute("local o = SEW.Client.devOutfall(); return o.x, o.y")
    check(p.z == 0 and int(p.x) == o[0] and int(p.y) == o[1], "Go to the outfall puts you on its bank")
    # The temple: into the passage a short walk from its south gate (never the
    # hall itself: the cult's dead are not put down beside a player), to where
    # it broke into a sewer, and to the field over its trapdoor.
    T = SEW.Index.temple
    pick("temple")
    gate = T.breaches[2]
    check(p.z == -1 and L.execute("return SEW.Util.floorOf(SIM.players[1]:getCurrentSquare()) ~= nil")
          and 12 <= abs(p.x - gate.gx) + abs(p.y - gate.gy) <= 40,
          "Go into the temple puts you in the passage short of its south gate (%.1f,%.1f,%.1f)" % (p.x, p.y, p.z))
    pick("breach")
    at = [(int(b.tx), int(b.ty)) for b in lua_list(T.breaches)]
    check(p.z == -1 and (int(p.x), int(p.y)) in at, "Go to a cult breach puts you at one (%.1f,%.1f)" % (p.x, p.y))
    first = (int(p.x), int(p.y))
    pick("breach")
    check((int(p.x), int(p.y)) in at and (int(p.x), int(p.y)) != first, "and again, the other")
    pick("trapdoor")
    check(p.z == 0 and int(p.x) == T.tx and int(p.y) == T.ty + 1, "Go to the temple's trapdoor puts you in the field by it")
    pick("dig")
    check(p.inv.containsTypeRecurse(p.inv, "PickAxe") and p.inv.containsTypeRecurse(p.inv, "PipeBomb"),
          "Give me a pickaxe and pipe bombs does")
    pick("maps")
    held = L.execute("""
        local n = {}
        for _, it in ipairs(SIM.players[1].inv.items._t) do if it:getStashMap() then n[it:getStashMap()] = true end end
        return n[SEW.Config.Maps.temple.stash] == true and n[SEW.Config.Maps.nest.stash] == true
    """)
    check(held is True, "Give me the annotated maps puts both in your inventory")
    # The nest: the sewer side of its false wall, and the first of its dens.
    Ln, Wn = SEW.Index.lair, SEW.Index.warren
    pick("nest")
    check(p.z == -1 and (int(p.x), int(p.y)) == (Ln.tx, Ln.ty), "Go to the nest's false wall puts you beside it")
    pick("warren")
    check(p.z == -1 and (int(p.x), int(p.y)) == (Wn.dens[1], Wn.dens[2])
          and L.execute("return SEW.Util.floorOf(SIM.players[1]:getCurrentSquare()) ~= nil"),
          "Go into the warren puts you in its first den, on its earth")
    rescued = [line for line in lua_list(sim.log)[log0:] if "rescue" in line]
    check(not rescued, "no trip ends in a rescue to some ladder (%s)" % rescued[:1])
    L.execute("SIM.streamRadius = nil")
    SEW.Dev = None
    p.stats = L.table()


def gas_test(L, p):
    """Sewer gas (DESIGN.md 7b): the haze and placards laid once, in a new chunk and
    in one built before there was gas; breathing it unmasked (poison, to the
    sandbox's cap), masked (a filter used up instead), not at all when it is
    off; the note, the cough and the map."""
    g = L.globals()
    sim, SEW = g.SIM, g.SEW
    C = SEW.Config
    stretches = [s for s in lua_list(SEW.Index.gas) if s.town == "muldraugh"]
    check(len(stretches) >= 3, "Muldraugh has sewer gas in the index (%d stretches)" % len(stretches))
    if len(stretches) < 3:
        return
    load_build = """
        local x, y, r = ...
        local B = SEW.Build
        local keys = {}
        for kx = math.floor((x - r) / 8), math.floor((x + r) / 8) do
            for ky = math.floor((y - r) / 8), math.floor((y + r) / 8) do
                SIM.load(kx, ky)
                local k = kx .. "," .. ky
                if B.townOf(k) then keys[#keys + 1] = k end
            end
        end
        for _, k in ipairs(keys) do B.chunk(k) end
        return keys
    """
    count = """
        local keys, sprite = ...
        local n = 0
        for _, k in ipairs(keys) do
            local cx, cy = k:match("(-?%d+),(-?%d+)")
            for x = cx * 8, cx * 8 + 7 do for y = cy * 8, cy * 8 + 7 do
                local sq = SIM.squares[x .. "," .. y .. ",-1"]
                for _, o in ipairs(sq and sq.objects._t or {}) do
                    if o.sprite:getName() == sprite then n = n + 1 end
                    for _, a in ipairs(o.attached and o.attached._t or {}) do
                        if a:getParentSprite():getName() == sprite then n = n + 1 end
                    end
                end
            end end
        end
        return n
    """
    want = """
        local keys = ...
        local T = SEW.Data.muldraugh
        local haze, signs = 0, 0
        for _, k in ipairs(keys) do
            haze = haze + #(T.gas[k] or "") / 3
            signs = signs + #(T.gasSigns[k] or {})
        end
        return haze, signs
    """
    s1 = stretches[0]
    keys = L.execute(load_build, s1.x, s1.y, 24)
    haze = L.execute(count, keys, C.Sprites.haze)
    signs = L.execute(count, keys, C.Sprites.gasSign.N) + L.execute(count, keys, C.Sprites.gasSign.W)
    w = L.execute(want, keys)
    check(w[0] >= s1.n and haze == w[0], "the haze lies on every gas square of the chunks built (%d of %d)" % (haze, w[0]))
    check(w[1] >= 1 and signs == w[1], "a placard hangs on a wall at every way in (%d of %d)" % (signs, w[1]))
    # A player scrubs a square of it away; a later pass puts none back.
    L.execute("""
        local sprite = ...
        for _, sq in pairs(SIM.squares) do
            for _, o in ipairs(sq.objects._t) do
                if o.sprite:getName() == sprite then sq.objects:remove(o) return end
            end
        end
    """, C.Sprites.haze)
    L.execute("local keys = ...; for _, k in ipairs(keys) do SEW.Build.state().built[k] = 'older' end; "
              "for _, k in ipairs(keys) do SEW.Build.chunk(k) end", keys)
    check(L.execute(count, keys, C.Sprites.haze) == haze - 1,
          "a later pass lays no second haze, nor puts back what a player scrubbed")

    # A save from 0.5.0: its chunks built before there was gas, and here with
    # the sandbox's gas off -- nothing goes down, and nothing is recorded, so
    # turning it on later (or the next version's pass) lays it once.
    s2 = stretches[1]
    L.execute("SandboxVars.Sewars.Gas = 1")
    keys2 = L.execute(load_build, s2.x, s2.y, 24)
    check(L.execute(count, keys2, C.Sprites.haze) == 0, "with the gas off, no haze goes down")
    L.execute("SandboxVars.Sewars.Gas = nil")
    L.execute("local keys = ...; for _, k in ipairs(keys) do SEW.Build.state().built[k] = 'old' end; "
              "for _, k in ipairs(keys) do SEW.Build.chunk(k) end", keys2)
    w2 = L.execute(want, keys2)
    check(w2[0] > 0 and L.execute(count, keys2, C.Sprites.haze) == w2[0],
          "a chunk built before gas gets its haze on the next pass (%d)" % w2[0])

    # Breathing it.
    p.x, p.y, p.z = s1.x + 0.5, s1.y + 0.5, -1
    p.stats, p.worn = L.table(), None
    sim.players = L.table(p)
    before = len(lua_list(sim.notes))
    sim.tickN(C.Gas.lookEvery * 2)
    notes = lua_list(sim.notes)[before:]
    check(any("thick and sour" in n for n in notes), "walking into it: the note (%s)" % notes[-1:])
    check("VoiceMaleCough" in lua_list(sim.sounds)[-3:], "and a cough")
    idx = [i + 1 for i, s in enumerate(lua_list(SEW.Index.gas)) if s.x == s1.x and s.y == s1.y][0]
    check(SEW.Map.state.g[idx] is not None and L.execute("return SEW.Discovery.record(SIM.players[1]).g[%d]" % idx) == 1,
          "and it is on the player's sewer map, recorded by the server")
    sim.tickN(C.Gas.lookEvery * 3)
    check(not any("thick and sour" in n for n in lua_list(sim.notes)[before + 1:]), "standing in it does not nag")
    for _ in range(15):
        sim.fire("EveryOneMinute")
    poison = L.execute("return SIM.players[1]:getStats():get(CharacterStat.POISON)")
    check(poison == C.Gas.cap[3], "each game minute adds poison, up to Harmful's cap (%s of %s)" % (poison, C.Gas.cap[3]))
    # Out of it -- onto a built square of walkway with clean air, not an
    # unbuilt one (a player below with no floor is rescued) -- nothing more.
    clean = L.execute("""
        local keys = ...
        for _, k in ipairs(keys) do
            local cx, cy = k:match("(-?%d+),(-?%d+)")
            for x = cx * 8, cx * 8 + 7 do for y = cy * 8, cy * 8 + 7 do
                local sq = SIM.squares[x .. "," .. y .. ",-1"]
                local f = sq and SEW.Util.floorOf(sq)
                if f and f.sprite:getName() == SEW.Config.Sprites.floorTunnel and not SEW.Gas.at(x, y) then
                    return x, y
                end
            end end
        end
    """, keys)
    check(clean is not None, "clean air near the gas to step out into")
    L.execute("SIM.players[1].stats.POISON = 5")
    p.x, p.y = clean[0] + 0.5, clean[1] + 0.5
    sim.fire("EveryOneMinute")
    check(L.execute("return SIM.players[1]:getStats():get(CharacterStat.POISON)") == 5,
          "out of it, the air adds nothing")
    # Mild never passes 10.
    p.x, p.y = s1.x + 0.5, s1.y + 0.5
    L.execute("SIM.players[1].stats.POISON = 0; SandboxVars.Sewars.Gas = 2")
    for _ in range(30):
        sim.fire("EveryOneMinute")
    check(L.execute("return SIM.players[1]:getStats():get(CharacterStat.POISON)") == C.Gas.cap[2],
          "Mild stops at %d, where poison starts to cost health" % C.Gas.cap[2])
    L.execute("SIM.players[1].stats.POISON = 0; SandboxVars.Sewars.Gas = 1")
    sim.fire("EveryOneMinute")
    check(L.execute("return SIM.players[1]:getStats():get(CharacterStat.POISON)") == 0, "Off does nothing")
    L.execute("SandboxVars.Sewars.Gas = nil")

    # With a gas mask on: no poison, and the filter is used up.
    mask = L.execute("local m = SIM.newClothing(true, true); SIM.players[1].worn = { SIM.newClothing(false, false), m }; return m")
    p.x, p.y = clean[0] + 0.5, clean[1] + 0.5
    sim.tickN(C.Gas.lookEvery * 2)
    before = len(lua_list(sim.notes))
    p.x, p.y = s1.x + 0.5, s1.y + 0.5
    sim.tickN(C.Gas.lookEvery * 2)
    notes = lua_list(sim.notes)[before:]
    check(any("mask hisses" in n for n in notes) and "VoiceMaleMuffledCough" in lua_list(sim.sounds)[-3:],
          "masked, the note says so and the cough is muffled (%s)" % notes[-1:])
    for _ in range(10):
        sim.fire("EveryOneMinute")
    check(L.execute("return SIM.players[1]:getStats():get(CharacterStat.POISON)") == 0 and mask.usedDelta < 1,
          "masked, no poison, and the filter is used (%.2f left)" % mask.usedDelta)
    L.execute("SIM.players[1].worn[2].usedDelta = 0")
    sim.fire("EveryOneMinute")
    check(L.execute("return SIM.players[1]:getStats():get(CharacterStat.POISON)") > 0,
          "a spent filter keeps nothing out")
    p.worn, p.stats = None, L.table()

    # A plan of the sheet marks the gas on it: the county knew.
    t = SEW.Index.towns.muldraugh
    s3 = stretches[2]
    sheet = ((s3.x - t.x0) // 256, (s3.y - t.y0) // 256)
    idx3 = [i + 1 for i, s in enumerate(lua_list(SEW.Index.gas)) if s.x == s3.x and s.y == s3.y][0]
    L.execute("SEW.Discovery.record(SIM.players[1]).g[%d] = nil" % idx3)
    plan = L.execute("""
        local i, j = ...
        local P = SEW.Index.plans
        P[#P + 1] = { town = "muldraugh", i = i, j = j }
        local it = instanceItem("Sewars.SewerPlan")
        it:getModData().SewarsPlan = #P
        SIM.players[1].inv.items:add(it)
        return it
    """, sheet[0], sheet[1])
    SEW.Story.readPlan(p, plan.getID(plan))
    L.execute("table.remove(SEW.Index.plans)")
    check(L.execute("return SEW.Discovery.record(SIM.players[1]).g[%d]" % idx3) == 1 and SEW.Map.state.g[idx3] is not None,
          "a plan of the sheet marks the gas on it")


GATE_DOOR = """
    local x, y, north = ...
    local sq = SIM.squares[x .. "," .. y .. ",-1"]
    local doors, frame = {}, false
    for _, o in ipairs(sq and sq.specials._t or {}) do
        if o.class == "IsoDoor" and o.north == north then doors[#doors + 1] = o end
    end
    local want = north and SEW.Config.Sprites.doorFrame.N or SEW.Config.Sprites.doorFrame.W
    for _, o in ipairs(sq and sq.objects._t or {}) do
        if o.sprite:getName() == want then frame = true end
    end
    local d = doors[1]
    return #doors, d and d.sprite:getName(), d and d:getKeyId(), d and d:isLockedByKey(), d and d.md.CustomLock,
           d and d.md.sew, frame, d and d.health
"""


def gates_test(L, p):
    """Locked gates (DESIGN.md 7, Locked gates): the grille on a county room, keyed and locked;
    the key in an unlocked county room's crate; kept by a revision pass; a
    0.5.0 save's rooms keep their steel doors; the key and a plan on the
    county's dead."""
    g = L.globals()
    sim, SEW = g.SIM, g.SEW
    C = SEW.Config
    town = SEW.Index.towns.muldraugh
    gates = [x for x in lua_list(SEW.Index.gates) if x.town == "muldraugh"]
    check(town.key is not None and len(gates) >= 2, "Muldraugh has locked gates and a key (%d, %s)" % (len(gates), town.key))
    if len(gates) < 2:
        return
    build = """
        local x, y, r = ...
        local B = SEW.Build
        local keys = {}
        for kx = math.floor((x - r) / 8), math.floor((x + r) / 8) do
            for ky = math.floor((y - r) / 8), math.floor((y + r) / 8) do
                SIM.load(kx, ky)
                local k = kx .. "," .. ky
                if B.townOf(k) then keys[#keys + 1] = k end
            end
        end
        for _, k in ipairs(keys) do B.chunk(k) end
        return keys
    """
    g1 = gates[0]
    north = g1.edge == "N"
    keys = L.execute(build, g1.x, g1.y, 10)
    n, sprite, key, locked, custom, ours, frame, health = L.execute(GATE_DOOR, g1.x, g1.y, north)
    want_sprite = C.Sprites.gate.N if north else C.Sprites.gate.W
    check(n == 1 and sprite == want_sprite and ours, "a county room's door is a grille of bars (%s)" % sprite)
    # Not CustomLock: that asks everybody for the key, from inside too.
    check(key == town.key and locked is True and not custom,
          "keyed to its town and locked by key -- not CustomLock, which would shut a player in (%s, %s, %s)"
          % (key, locked, custom))
    check(health == 2000, "made from its sprite: a steel gate's 2000 health, not a string door's 500 (%s)" % health)
    # The same frame object, not one taken out and put back: in the game a
    # door whose frame is removed is left hanging in nothing.
    same = L.execute("""
        local x, y, north, keys, door = ...
        local sq = SIM.squares[x .. "," .. y .. ",-1"]
        local want = north and SEW.Config.Sprites.doorFrame.N or SEW.Config.Sprites.doorFrame.W
        local function frame()
            for _, o in ipairs(sq.objects._t) do if o.sprite:getName() == want then return o end end
        end
        local before = frame()
        for _, k in ipairs(keys) do SEW.Build.state().built[k] = "older" end
        for _, k in ipairs(keys) do SEW.Build.chunk(k) end
        return before ~= nil and frame() == before
    """ + "", g1.x, g1.y, north, keys)
    n2 = L.execute(GATE_DOOR, g1.x, g1.y, north)[0]
    check(frame and same is True and n2 == 1,
          "a revision pass leaves its frame standing (the same one) and puts in no second gate")

    # The latch: a key-holder opened it (the engine unlocks it) and shut it
    # again; with a player below nearby, it locks itself -- but not while it
    # stands open, and never a door that is not ours.
    outside = L.execute("""
        local x, y, north = ...
        -- The tunnel side of the edge: the one of the two squares not in a shelter.
        local ox, oy = x, y
        if north then oy = y - 1 else ox = x - 1 end
        if SEW.Sewer.shelterAt(ox, oy) then return x, y, ox, oy end
        return ox, oy, x, y
    """, g1.x, g1.y, north)
    latch = L.execute("""
        local x, y, north, tx, ty = ...
        local sq = SIM.squares[x .. "," .. y .. ",-1"]
        local d
        for _, o in ipairs(sq.specials._t) do if o.class == "IsoDoor" and o.north == north then d = o end end
        local p = SIM.players[1]
        p.x, p.y, p.z = tx + 0.5, ty + 0.5, -1
        d.lockedByKey, d.locked, d.open = false, false, true
        SIM.tickN(SEW.Config.Gates.latchEvery * 2)
        local whileOpen = d:isLockedByKey()
        d.open = false
        SIM.tickN(SEW.Config.Gates.latchEvery * 2)
        local shut = d:isLockedByKey()
        d.md.sew = nil
        d.lockedByKey, d.locked = false, false
        SIM.tickN(SEW.Config.Gates.latchEvery * 2)
        local theirs = d:isLockedByKey()
        d.md.sew = 1
        d.lockedByKey, d.locked = true, true
        return whileOpen, shut, theirs
    """, g1.x, g1.y, north, outside[0], outside[1])
    check(latch[0] is False and latch[1] is True and latch[2] is False,
          "a grille shut behind a key-holder locks itself again, not while it stands open, and never a door "
          "that is not ours (%s)" % (tuple(latch),))
    # The handle on the inside: somebody without the key followed a key-holder
    # in and the grille was shut behind them. Nobody below is "inside" to the
    # engine, so the grille must be unlocked while anybody is in the room --
    # and locked again once they are out and it is shut.
    handle = L.execute("""
        local x, y, north, ix, iy, tx, ty = ...
        local sq = SIM.squares[x .. "," .. y .. ",-1"]
        local d
        for _, o in ipairs(sq.specials._t) do if o.class == "IsoDoor" and o.north == north then d = o end end
        local p = SIM.players[1]
        d.open = false
        d.lockedByKey, d.locked = true, true
        p.x, p.y, p.z = ix + 0.5, iy + 0.5, -1
        SIM.tickN(SEW.Config.Gates.latchEvery * 2)
        local free = not d:isLockedByKey()
        p.x, p.y = tx + 0.5, ty + 0.5
        SIM.tickN(SEW.Config.Gates.latchEvery * 2)
        return free, d:isLockedByKey()
    """, g1.x, g1.y, north, outside[2], outside[3], outside[0], outside[1])
    check(handle[0] is True and handle[1] is True,
          "a grille has a handle on the inside: unlocked while anybody is in its room, locked once they are out "
          "(%s)" % (tuple(handle),))
    p.x, p.y, p.z = g1.x + 40.5, g1.y + 40.5, 0

    # The key, in an unlocked county room's first crate.
    spot = L.execute("""
        for key, list in pairs(SEW.Data.muldraugh.keys) do return list[1][1], list[1][2] end
    """)
    check(spot is not None, "Muldraugh leaves its key somewhere")
    if spot is not None:
        L.execute(build, spot[0], spot[1], 12)
        found = L.execute("""
            local x, y = ...
            local sq = SIM.squares[x .. "," .. y .. ",-1"]
            for _, o in ipairs(sq and sq.objects._t or {}) do
                if o.container then
                    for _, it in ipairs(o.container.items._t) do
                        if it:getFullType() == SEW.Config.KeyItem then return it:getKeyId(), it:getName() end
                    end
                end
            end
        """, spot[0], spot[1])
        check(found is not None and found[0] == town.key and "Muldraugh" in str(found[1]),
              "an unlocked county room's crate holds the town's key, named for it (%s)" % (found,))

    # A 0.5.0 save built this room with its steel door: no grille goes in, and
    # the door the player had is left alone.
    g2 = gates[1]
    north2 = g2.edge == "N"
    L.execute("""
        local x, y, north = ...
        local B = SEW.Build
        local s = B.state()
        for kx = math.floor(x / 8) - 1, math.floor(x / 8) + 1 do
            for ky = math.floor(y / 8) - 1, math.floor(y / 8) + 1 do
                SIM.load(kx, ky)
                local k = kx .. "," .. ky
                if B.townOf(k) then s.first[k], s.built[k], s.caves[k] = "old", "old", "old" end
            end
        end
        local sq = getCell():getOrCreateGridSquare(x, y, -1)
        local door = IsoDoor.new(getCell(), sq, north and SEW.Config.Sprites.door.N or SEW.Config.Sprites.door.W, north)
        door.md.sew = 1
        sq:AddSpecialObject(door)
        for kx = math.floor(x / 8) - 1, math.floor(x / 8) + 1 do
            for ky = math.floor(y / 8) - 1, math.floor(y / 8) + 1 do
                local k = kx .. "," .. ky
                if B.townOf(k) then B.chunk(k) end
            end
        end
    """, g2.x, g2.y, north2)
    n3, sprite3, _, _, _, _, frame3, _ = L.execute(GATE_DOOR, g2.x, g2.y, north2)
    check(n3 == 1 and sprite3 in (C.Sprites.door.N, C.Sprites.door.W) and frame3,
          "a room a 0.5.0 save built keeps its steel door; no grille is forced on it (%s)" % sprite3)

    # The county's dead: a sanitation worker killed below a town with gates
    # may carry its key, and one of its plans.
    res = L.execute("""
        local x, y, tid = ...
        local keys, plans, good = 0, 0, true
        for i = 1, 200 do
            local z = SIM.newZombie(x + 0.5, y + 0.5, -1, SEW.Config.Gates.outfit)
            SIM.fire("OnZombieDead", z)
            for _, it in ipairs(z.inv.items._t) do
                if it:getFullType() == SEW.Config.KeyItem then
                    keys = keys + 1
                    good = good and it:getKeyId() == SEW.Index.towns[tid].key
                elseif it:getFullType() == SEW.Config.PlanItem then
                    plans = plans + 1
                    local pl = SEW.Index.plans[it:getModData().SewarsPlan]
                    good = good and pl ~= nil and pl.town == tid
                end
            end
        end
        local none = 0
        for _, case in ipairs({ { 0, SEW.Config.Gates.outfit }, { -1, "Hobbo" } }) do
            for _ = 1, 40 do
                local z = SIM.newZombie(x + 0.5, y + 0.5, case[1], case[2])
                SIM.fire("OnZombieDead", z)
                -- (A map to the temple or the nest is another matter: SEW_Maps, any of the dead below.)
                for _, it in ipairs(z.inv.items._t) do
                    local full = it:getFullType()
                    if full == SEW.Config.KeyItem or full == SEW.Config.PlanItem then none = none + 1 end
                end
            end
        end
        return keys, plans, good, none
    """, g1.x, g1.y, "muldraugh")
    check(40 <= res[0] <= 110 and 15 <= res[1] <= 70 and res[2],
          "of 200 sanitation workers killed below: %d carry the key, %d a plan of the town" % (res[0], res[1]))
    check(res[3] == 0, "one on the street, or in other clothes, carries neither")
    lone = L.execute("""
        for tid, t in pairs(SEW.Index.towns) do
            if not t.key then
                for key in pairs(SEW.Data[tid].chunks) do
                    local cx, cy = key:match("(-?%d+),(-?%d+)")
                    local n = 0
                    for i = 1, 60 do
                        local z = SIM.newZombie(cx * 8 + 4.5, cy * 8 + 4.5, -1, SEW.Config.Gates.outfit)
                        SIM.fire("OnZombieDead", z)
                        for _, it in ipairs(z.inv.items._t) do
                            if it:getFullType() == SEW.Config.KeyItem then n = n + 1 end
                        end
                    end
                    return tid, n
                end
            end
        end
    """)
    check(lone is not None and lone[1] == 0, "below a town with no gates they carry no key (%s)" % (lone,))


def outfall_test(L, p):
    """Storm-drain outfalls (DESIGN.md 7c): the grate set into the bank as a
    player comes near; down it, and back up onto the bank; blue on the map."""
    g = L.globals()
    sim, SEW = g.SIM, g.SEW
    out = L.execute("""
        local out = {}
        for _, s in pairs(SEW.Index.shafts) do if s.outfall then out[#out + 1] = s end end
        table.sort(out, function(a, b) return a.x < b.x or (a.x == b.x and a.y < b.y) end)
        return out[1], #out
    """)
    o, n = out
    check(o is not None and n >= 10 and o.made, "the index has outfalls, set in by the server like our covers (%s)" % n)
    if o is None:
        return
    ox, oy = int(o.x), int(o.y)
    q = sim.newPlayer("bank", ox + 2.5, oy + 0.5, 0)
    q.hours = 50
    sim.players = L.table(q)
    street(L, ox, oy, 3, manhole=False)
    check(TEXT["ContextMenu_SEW_OutfallDown"] not in [nm for nm, _ in options(menu(L, 0, ox, oy))],
          "no grate in the bank before the server has set it in")
    sim.tickN(20)
    check(L.execute("return SEW.Build.state().covers['%d,%d']" % (ox, oy)) == "placed"
          and SEW.Config.Sprites.outfall in objects_at(L, ox, oy, 0),
          "a player on the bank: the grate goes in (%s)" % objects_at(L, ox, oy, 0))
    m = menu(L, 0, ox, oy)
    names = [nm for nm, _ in options(m)]
    check(TEXT["ContextMenu_SEW_OutfallDown"] in names and TEXT["ContextMenu_SEW_Enter"] not in names,
          "it offers Climb into the storm drain (%s)" % names)
    before = len(lua_list(sim.notes))
    choose(m, TEXT["ContextMenu_SEW_OutfallDown"])
    sim.runActions()
    sim.tickN(3)
    check(abs(q.z + 1) < 1e-6 and int(q.x) == ox and int(q.y) == oy,
          "down to the foot of its ladder (%.1f,%.1f,%.1f)" % (q.x, q.y, q.z))
    check(any("storm drain" in nt for nt in lua_list(sim.notes)[before:]), "with the outfall's note")
    check("SEW_Lid" not in lua_list(sim.sounds)[-3:], "and no iron lid scraping")
    lobjs = objects_at(L, int(o.lx), int(o.ly), -1)
    check(any(x in ("sewars_01_0", "sewars_01_1") for x in lobjs), "a ladder hangs under the grate (%s)" % lobjs)
    m = menu(L, 0, ox, oy)
    check(TEXT["ContextMenu_SEW_OutfallUp"] in [nm for nm, _ in options(m)], "below, it offers Climb out onto the bank")
    before = len(lua_list(sim.notes))
    choose(m, TEXT["ContextMenu_SEW_OutfallUp"])
    sim.runActions()
    sim.tickN(3)
    check(q.z == 0 and int(q.x) == ox and int(q.y) == oy and any("bank" in nt for nt in lua_list(sim.notes)[before:]),
          "and up onto the bank (%.1f,%.1f,%.1f)" % (q.x, q.y, q.z))
    check(SEW.Map.state.l["%d,%d" % (ox, oy)] is not None, "the outfall used is on the sewer map")
    win = SEW.Map.open(q)
    if win is not None:
        win.tid = o.town
        win.cx, win.cy = ox, oy
        sim.draws = L.table()
        win.prerender(win)
        win.render(win)
        blue = [d for d in lua_list(sim.draws) if d.kind == "rect" and d.extra and abs(d.extra[1] - 0.22) < 1e-6]
        check(len(blue) >= 1, "drawn in the river's blue")
        win.close(win)


def mine_test(L, p):
    """Digging (SEW_Mine): with a pick, a square of rock dug out from where
    the player stands -- floor, earth walls round it, the wall between gone --
    and still dug after a revision pass; a wall between two spaces knocked
    through; what never gives; and a bomb going off below ground, which opens
    the rock round it."""
    g = L.globals()
    sim, SEW = g.SIM, g.SEW
    C = SEW.Config
    # A straight east-west culvert in Muldraugh with solid rock north of it:
    # A, its east neighbour, and four squares of nothing north of both.
    spot = L.execute("""
        local B, T = SEW.Build, SEW.Data.muldraugh
        local keys = {}
        for k in pairs(T.chunks) do if B.state().first[k] then keys[#keys + 1] = k end end
        table.sort(keys)
        local Mi = SEW.Mine
        for _, k in ipairs(keys) do
            local cx, cy = k:match("(-?%d+),(-?%d+)")
            for ax = cx * 8, cx * 8 + 7 do for ay = cy * 8, cy * 8 + 7 do
                if Mi.floor(ax, ay) == "t" and Mi.floor(ax + 1, ay) == "t" and Mi.floor(ax - 1, ay) == "t" then
                    local clear = Mi.edgeCode(ax, ay, ax, ay - 1) == "c" and Mi.edgeCode(ax + 1, ay, ax + 1, ay - 1) == "c"
                    for dx = -4, 5 do for dy = -6, -1 do
                        if Mi.isSpace(ax + dx, ay + dy) then clear = false end
                    end end
                    local r, r2 = B.recordAt(ax, ay), B.recordAt(ax, ay - 1)
                    if clear and r:sub(6, 7) == ".." and (not r2 or r2:sub(6, 7) == "..") then
                        for kx = math.floor((ax - 8) / 8), math.floor((ax + 8) / 8) do
                            for ky = math.floor((ay - 10) / 8), math.floor((ay + 8) / 8) do SIM.load(kx, ky) end
                        end
                        B.around(ax, ay, 1)
                        return ax, ay
                    end
                end
            end end
        end
    """)
    check(spot is not None, "a culvert with rock north of it to dig into (%s)" % (spot,))
    if spot is None:
        return
    ax, ay = spot
    bx, by = ax, ay - 1
    p.x, p.y, p.z = ax + 0.5, ay + 0.5, -1
    sim.players = L.table(p)
    L.execute("SIM.players[1].inv = SIM.Container(50)")

    def dig_menu(px=None, py=None):
        m = menu(L, 0, ax, ay)
        top = [o for nm, o in options(m) if nm == TEXT["ContextMenu_SEW_Mine"]]
        return top[0] if top else None

    def blocked(x1, y1, x2, y2):
        return L.execute("local a, b = SIM.squares['%d,%d,-1'], SIM.squares['%d,%d,-1']; "
                         "if not a or not b then return nil end; return a:isBlockedTo(b)" % (x1, y1, x2, y2))

    def floor_at(x, y):
        return L.execute("local sq = SIM.squares['%d,%d,-1']; local f = sq and sq:getFloor(); "
                         "return f and f.sprite:getName()" % (x, y))

    # No tool: the menu says so, and the server says no.
    top = dig_menu()
    check(top is not None and top.notAvailable is True and top.toolTip.description == TEXT["Tooltip_SEW_MineNoTool"],
          "below ground, with rock beside you and nothing to dig with: Dig is greyed, and says what you need")
    check(L.execute("return SEW.Mine.dig(SIM.players[1], %d, %d, 0, -1)" % (ax, ay)) is False
          and floor_at(bx, by) in (None, C.Sprites.floorRock), "the server refuses a dig without a pick or a hammer")
    L.execute("SIM.players[1].inv:AddItem(instanceItem('Base.Sledgehammer'))")
    slow = L.execute("return SEWMine:new(SIM.players[1], %d, %d, 0, -1).maxTime" % (ax, ay))
    L.execute("SIM.players[1].inv:AddItem(instanceItem('Base.PickAxe'))")
    fast = L.execute("return SEWMine:new(SIM.players[1], %d, %d, 0, -1).maxTime" % (ax, ay))
    check(fast == C.Mine.ticks.pick and slow == C.Mine.ticks.hammer and fast < slow,
          "a pick is quicker than a sledgehammer (%s ticks, %s)" % (fast, slow))

    # With one: Dig offers the rock to the north; choosing it digs it out.
    top = dig_menu()
    names = [nm for nm, _ in options(top.subMenu)] if top is not None and top.subMenu is not None else []
    check(TEXT["ContextMenu_SEW_Dig_N"] in names and TEXT["ContextMenu_SEW_Dig_E"] not in names
          and TEXT["ContextMenu_SEW_Break_E"] not in names,
          "Dig offers the rock to the north, and nothing where the tunnel is open (%s)" % names)
    notes0, xp0, snd0 = len(lua_list(sim.notes)), L.execute("return #SIM.xp"), L.execute("return #SIM.worldSounds")
    count0 = count_ours(L)
    choose(top.subMenu, TEXT["ContextMenu_SEW_Dig_N"])
    sim.runActions()
    sim.tickN(3)
    check(floor_at(bx, by) in lua_list(C.Sprites.floorCave) and blocked(ax, ay, bx, by) is False,
          "the rock north is dug out: earth to stand on, and the wall between gone (%s)" % floor_at(bx, by))
    # (West and north of it there is no square at all: nothing was ever raised there.)
    sides = [blocked(bx, by, bx - 1, by), blocked(bx, by, bx + 1, by), blocked(bx, by, bx, by - 1)]
    check(sides[1] is True and sides[0] in (True, None) and sides[2] in (True, None)
          and C.Sprites.wall.e.NW in objects_at(L, bx, by, -1),
          "with earth walls on its other three sides, where the rock still is (%s)" % sides)
    faces = objects_at(L, bx, by, -1) + objects_at(L, bx + 1, by, -1) + objects_at(L, bx, by + 1, -1)
    check(C.Sprites.earthFace.N in faces and C.Sprites.earthFace.W in faces, "and they are earth to look at")
    check(blocked(ax, ay, ax + 1, ay) is False and blocked(ax + 1, ay, ax + 1, ay - 1) is True,
          "the tunnel either side is as it was")
    check(any(n == TEXT["IGUI_SEW_MineDug"] for n in lua_list(sim.notes)[notes0:])
          and L.execute("return #SIM.xp") == xp0 + 1 and L.execute("return #SIM.worldSounds") == snd0 + 1,
          "it says so, it is heard, and it is masonry")
    check(p.metabolic == "HeavyWork", "and it is heavy work")

    # A revision pass, and then the builder asked for the square outright:
    # what was dug stays dug, and what the generator never had is put back.
    again = L.execute("""
        local B, ax, ay = SEW.Build, ...
        local s = B.state()
        local key = math.floor(ax / 8) .. "," .. math.floor((ay - 1) / 8)
        local before = 0
        for _, sq in pairs(SIM.squares) do before = before + #sq.objects._t end
        s.built[key] = "older"
        s.built[math.floor(ax / 8) .. "," .. math.floor(ay / 8)] = "older"
        B.around(ax, ay, 1)
        local after = 0
        for _, sq in pairs(SIM.squares) do after = after + #sq.objects._t end
        return before, after
    """, ax, ay)
    check(blocked(ax, ay, bx, by) is False and floor_at(bx, by) in lua_list(C.Sprites.floorCave) and again[0] == again[1],
          "a revision pass leaves it dug: no wall put back, nothing placed twice (%d objects, %d)" % (again[0], again[1]))
    # Two squares further: ground the generator never had a record for.
    p.x, p.y = bx + 0.5, by + 0.5
    ok1 = L.execute("return SEW.Mine.dig(SIM.players[1], %d, %d, 0, -1)" % (bx, by))
    p.y = by - 1 + 0.5
    ok2 = L.execute("return SEW.Mine.dig(SIM.players[1], %d, %d, 0, -1)" % (bx, by - 1))
    deep = (bx, by - 2)
    check(ok1 is True and ok2 is True and L.execute("return SEW.Build.dataAt(%d, %d)" % deep) is None
          and floor_at(*deep) in lua_list(C.Sprites.floorCave),
          "and on, into ground the generator never had a record for (%d,%d)" % deep)
    back = L.execute("""
        local B, x, y = SEW.Build, ...
        local sq = SIM.squares[x .. "," .. y .. ",-1"]
        sq.objects:remove(sq:getFloor())
        local key = math.floor(x / 8) .. "," .. math.floor(y / 8)
        -- No town has this chunk: it is the players' own, and still revisited.
        B.state().built[key] = "older"
        local listed = false
        for _, pend in ipairs(B.pending(x, y, 1)) do if pend.key == key then listed = true end end
        B.around(x, y, 1)
        return sq:getFloor() ~= nil, B.townOf(key) == nil, listed, B.isCurrent(key)
    """, *deep)
    check(back[0] is True and back[2] is True and back[3] is True,
          "a pass over that chunk -- no town's, the players' own -- puts its floor back (%s)" % (tuple(back),))

    # And in a town's own chunk, a square the generator has no record of: out
    # of the tunnel's far side, two squares into the rock.
    far = L.execute("""
        local Mi, B, p, ax, ay = SEW.Mine, SEW.Build, SIM.players[1], ...
        local y = ay
        while Mi.floor(ax, y + 1) == "t" do y = y + 1 end          -- the tunnel's southern edge
        for dy = 1, 5 do if Mi.isSpace(ax, y + dy) then return nil end end
        local px, py = p.x, p.y
        p.x, p.y = ax + 0.5, y + 0.5
        local one = Mi.dig(p, ax, y, 0, 1)
        p.y = y + 1.5
        local two = Mi.dig(p, ax, y + 1, 0, 1)
        p.x, p.y = px, py
        local x2, y2 = ax, y + 2
        local key = math.floor(x2 / 8) .. "," .. math.floor(y2 / 8)
        local sq = SIM.squares[x2 .. "," .. y2 .. ",-1"]
        if not (one and two and sq and sq:getFloor()) then return false end
        sq.objects:remove(sq:getFloor())
        B.state().built[key] = "older"
        B.chunk(key)
        return sq:getFloor() ~= nil, B.townOf(key) ~= nil, B.dataAt(x2, y2) == nil
    """, ax, ay)
    check(far is not None and far is not False and far[0] is True and far[1] is True and far[2] is True,
          "in a town's own chunk, a square dug that the generator never had is put back by a pass too (%s)"
          % (far if far in (None, False) else tuple(far),))

    # Knocking through: dig out the square east of B from the tunnel, and
    # there is earth between the two; from B, it comes down.
    p.x, p.y = ax + 1.5, ay + 0.5
    L.execute("SEW.Mine.dig(SIM.players[1], %d, %d, 0, -1)" % (ax + 1, ay))
    check(blocked(bx, by, bx + 1, by) is True, "two squares dug side by side have the earth between them still")
    p.x, p.y = bx + 0.5, by + 0.5
    top = L.execute("return SEW.Client.mineOffers(SIM.players[1])")
    kinds = {o.dir: o.kind for o in lua_list(top)}
    check(kinds.get("E") == "break" and kinds.get("W") == "dig" and "S" not in kinds,
          "from one of them: rock to dig one way, a wall to knock through the other (%s)" % kinds)
    notes0 = len(lua_list(sim.notes))
    m = menu(L, 0, bx, by)
    top = [o for nm, o in options(m) if nm == TEXT["ContextMenu_SEW_Mine"]][0]
    choose(top.subMenu, TEXT["ContextMenu_SEW_Break_E"])
    sim.runActions()
    sim.tickN(3)
    check(blocked(bx, by, bx + 1, by) is False and any(n == TEXT["IGUI_SEW_MineBroke"] for n in lua_list(sim.notes)[notes0:]),
          "Knock through the wall to the east: it comes down")

    # What never gives.
    refused = L.execute("""
        local Mi, B, p = SEW.Mine, SEW.Build, SIM.players[1]
        local bx, by = ...
        local out = {}
        local function try(x, y, dx, dy)
            local px, py = p.x, p.y
            p.x, p.y = x + 0.5, y + 0.5
            local n = #SIM.log
            local ok = Mi.dig(p, x, y, dx, dy)
            p.x, p.y = px, py
            return ok, SIM.log[#SIM.log]
        end
        -- Something not ours behind the rock: left alone.
        local sq = getCell():getOrCreateGridSquare(bx - 1, by, -1)
        local theirs = IsoObject.new(sq, "location_sewer_01_34", "")
        sq.objects:add(theirs)
        out[1], out[2] = try(bx, by, -1, 0)
        sq.objects:remove(theirs)
        -- From too far, and from the street.
        local px = p.x
        p.x = px + 6
        out[3] = Mi.dig(p, bx, by, -1, 0)
        p.x, p.z = px, 0
        out[4] = Mi.dig(p, bx, by, -1, 0)
        p.z = -1
        -- With the sandbox's digging off.
        SandboxVars.Sewars.Digging = 1
        out[5] = Mi.dig(p, bx, by, -1, 0)
        out[6] = #SEW.Client.mineOffers(p)
        SandboxVars.Sewars.Digging = nil
        -- A steel door, a ladder's wall, and the nest's own walls.
        for _, sh in pairs(SEW.Index.shafts) do
            if sh.town == "muldraugh" and not sh.hatch and B.isCurrent(math.floor(sh.lx / 8) .. "," .. math.floor(sh.ly / 8)) then
                local ox, oy = sh.lx, sh.ly
                if sh.edge == "N" then out[7] = try(sh.lx, sh.ly, 0, -1) else out[7] = try(sh.lx, sh.ly, -1, 0) end
                break
            end
        end
        local L = SEW.Index.lair
        local was = B.state().lair.open.gate
        B.state().lair.open.gate = nil
        out[8] = try(L.gx, L.gy, L.vx - L.gx, L.vy - L.gy)
        B.state().lair.open.gate = was
        -- The false wall is pulled away, not dug: it has its own way of opening.
        out[9] = try(L.tx, L.ty, L.ex - L.tx, L.ey - L.ty)
        -- A steel door is not a wall to knock through: the menu offers none, the server refuses.
        local T = SEW.Data.muldraugh
        for key, body in pairs(T.chunks) do
            if B.isCurrent(key) and not out[10] then
                local cx, cy = key:match("(-?%d+),(-?%d+)")
                for i = 1, #body, 7 do
                    local r = body:sub(i, i + 6)
                    local x, y = cx * 8 + tonumber(r:sub(1, 1)), cy * 8 + tonumber(r:sub(2, 2))
                    local ox, oy
                    if r:sub(4, 4) == "d" then ox, oy = x, y - 1 elseif r:sub(5, 5) == "d" then ox, oy = x - 1, y end
                    if ox then
                        local px, py = p.x, p.y
                        p.x, p.y = x + 0.5, y + 0.5
                        local offered = false
                        for _, o in ipairs(SEW.Client.mineOffers(p)) do
                            if x + o.dx == ox and y + o.dy == oy then offered = true end
                        end
                        p.x, p.y = px, py
                        out[10], out[11] = offered, try(x, y, ox - x, oy - y)
                        break
                    end
                end
            end
        end
        return out[1], out[2], out[3], out[4], out[5], out[6], out[7], out[8], out[9], out[10], out[11]
    """, bx, by)
    check(refused[0] is False and "foreign" in (refused[1] or ""),
          "rock with something not ours behind it is left alone (%s)" % (refused[1],))
    check(refused[2] is False and refused[3] is False, "not from out of reach, not from the street")
    check(refused[4] is False and refused[5] == 0, "not with the sandbox's digging off, and the menu offers none")
    check(refused[6] is False and refused[7] is False, "a ladder's wall does not give, nor the nest's own wall into the hoard")
    check(refused[8] is False, "nor the false wall: that one is pulled away")
    check(refused[9] is False and refused[10] is False, "a steel door is not a wall: not offered, and refused (%s, %s)"
          % (refused[9], refused[10]))

    # Blasting. A bomb at B: the rock for two squares round it is opened,
    # the walls of ours inside the round are gone, earth stands at its rim.
    def rock_open(cx, cy):
        return L.execute("""
            local cx, cy = ...
            local n = 0
            for x = cx - 3, cx + 3 do for y = cy - 3, cy + 3 do
                local sq = SIM.squares[x .. "," .. y .. ",-1"]
                local f = sq and sq:getFloor()
                if f and f.sprite:getName() ~= SEW.Config.Sprites.floorRock then n = n + 1 end
            end end
            return n
        """, cx, cy)
    cx, cy = bx - 3, by - 1                      # in the rock, west of what was dug: stand a bomb in a dug square
    p.x, p.y = bx + 0.5, by + 0.5
    before = rock_open(bx, by)
    for z, rng, level, what in ((0, 7, None, "on the street"), (-1, 0, None, "a smoke bomb"), (-1, 7, 2, "with explosives off")):
        L.execute("SandboxVars.Sewars.Digging = %s" % ("nil" if level is None else level))
        L.execute("local t, sq = SIM.newTrap(%d, %d, %d, %d); SIM.fire('OnThrowableExplode', t, sq)" % (bx, by, z, rng))
        sim.tickN(C.Mine.blastDelay + 3)
        check(rock_open(bx, by) == before, "a bomb %s moves no rock" % what)
    L.execute("SandboxVars.Sewars.Digging = nil")
    L.execute("local t, sq = SIM.newTrap(%d, %d, -1, 7); SIM.fire('OnThrowableExplode', t, sq)" % (bx, by))
    check(rock_open(bx, by) == before, "a bomb below ground: not on the instant")
    notes0 = len(lua_list(sim.notes))
    sim.tickN(C.Mine.blastDelay + 3)
    after = rock_open(bx, by)
    check(after >= before + 6, "and then the rock round it is open (%d squares stood on, %d before)" % (after, before))
    inside = all(blocked(bx, by, bx + dx, by + dy) is False for dx, dy in ((-1, 0), (1, 0), (0, -1)))
    rim = L.execute("""
        local Mi, bx, by, r = SEW.Mine, ...
        local leaks, edges = 0, 0
        for x = bx - r - 1, bx + r + 1 do for y = by - r - 1, by + r + 1 do
            if Mi.isSpace(x, y) then
                for _, n in ipairs({ { 0, -1 }, { -1, 0 }, { 1, 0 }, { 0, 1 } }) do
                    local nx, ny = x + n[1], y + n[2]
                    if not Mi.isSpace(nx, ny) then
                        edges = edges + 1
                        local a, b = SIM.squares[x .. "," .. y .. ",-1"], SIM.squares[nx .. "," .. ny .. ",-1"]
                        if not (a and b and a:isBlockedTo(b)) and b and b:getFloor() then leaks = leaks + 1 end
                        if not b or not a:isBlockedTo(b) then
                            -- No square beyond: nothing to walk onto. A square with a floor and no wall: a leak.
                            if b and b:getFloor() and b:getFloor().sprite:getName() ~= SEW.Config.Sprites.floorRock then leaks = leaks + 1 end
                        end
                    end
                end
            end
        end end
        return leaks, edges
    """, bx, by, C.Mine.blast)
    check(inside and rim[0] == 0 and rim[1] >= 8, "open inside the round, earth at its rim (%d edges, %d leaks)" % (rim[1], rim[0]))
    walled = L.execute("""
        local Mi, bx, by, r = SEW.Mine, ...
        local bad = 0
        for x = bx - r - 1, bx + r + 1 do for y = by - r - 1, by + r + 1 do
            if Mi.isSpace(x, y) then
                for _, n in ipairs({ { 0, -1 }, { -1, 0 }, { 1, 0 }, { 0, 1 } }) do
                    local nx, ny = x + n[1], y + n[2]
                    if not Mi.isSpace(nx, ny) and Mi.edgeCode(x, y, nx, ny) == "." then bad = bad + 1 end
                end
            end
        end end
        return bad
    """, bx, by, C.Mine.blast)
    check(walled == 0, "every edge between what is open and the rock has a wall (%d without)" % walled)
    check(any(n == TEXT["IGUI_SEW_MineBlast"] for n in lua_list(sim.notes)[notes0:]), "and whoever is below near by feels it")
    stones = L.execute("local n = 0; for _, sq in pairs(SIM.squares) do n = n + #(sq.dropped or {}) end; return n")
    check(stones >= 3, "the rock leaves stones to pick up (%d)" % stones)


def maps_test(L, p):
    """Annotated maps to the temple and to the nest (SEW_Maps): the game's own
    kind of map, marked where the places are, shown on a sheet that holds its
    marks; found in the game's own loot now and then, in a shelter's crate,
    on one of the dead below ground; and one of each placed where the other
    place's people would have had it."""
    g = L.globals()
    sim, SEW = g.SIM, g.SEW
    C = SEW.Config
    T, Ln = SEW.Index.temple, SEW.Index.lair
    made = L.execute("""
        local out = {}
        for _, which in ipairs(SEW.Maps.WHICH) do
            local it = SEW.Maps.make(which)
            local ui = SIM.mapUI()
            local f = it and LootMaps.Init[it:getStashMap()]
            if f then f(ui) end
            local inside, x, texts = true, nil, 0
            for _, s in ipairs(it and it.symbols or {}) do
                local b = ui.bounds
                if not b or s.x < b[1] or s.x > b[3] or s.y < b[2] or s.y > b[4] then inside = false end
                if s.symbol == "X" then x = { s.x, s.y } end
                if s.text then
                    texts = texts + 1
                    if not SIM.text[s.text] then inside = false end
                end
            end
            out[#out + 1] = { it and it:getStashMap(), it and it:getName(), it and #it.symbols, inside, x and x[1], x and x[2],
                              texts, ui.bounds ~= nil }
        end
        return out[1], out[2]
    """)
    t, n = [list(lua_list(m)) for m in made]
    check(t[0] == C.Maps.temple.stash and n[0] == C.Maps.nest.stash and t[1] == "Stash_AnnotedMap",
          "each is one of the game's annotated maps, by the game's own stash system (%s, %s)" % (t[0], n[0]))
    check((t[4], t[5]) == (T.tx, T.ty) and (n[4], n[5]) == (Ln.cx, Ln.cy),
          "the temple's has its X on the trapdoor, the nest's on the manhole nearest it by the tunnels")
    check(t[2] >= 5 and n[2] >= 4 and t[6] >= 2 and n[6] >= 2 and t[3] is True and n[3] is True and t[7] and n[7],
          "every mark and word is on the sheet the map shows, and every word is translated (%d, %d marks)" % (t[2], n[2]))
    check(L.execute("return StashSystem.getStash(SEW.Config.Maps.temple.stash).item") == C.Maps.never
          and C.Maps.never not in ITEMS and L.execute("return StashSystem.getStash(SEW.Config.Maps.nest.stash).buildingX") is None,
          "the engine's own roll cannot hand one out, and reading one touches no building")

    # In the game's own loot: a plain map, now and then; never one already
    # annotated, never anything that is not a map, never with the sandbox's
    # annotated maps off.
    fill = L.execute("""
        local function crate(ids)
            local c = SIM.Container(50)
            for _, id in ipairs(ids) do c:AddItem(instanceItem(id)) end
            return c
        end
        local C, M = SEW.Config, SEW.Maps
        local was = C.Maps.loot
        C.Maps.loot = 1
        local c = crate({ "Base.MuldraughMap", "Base.Hammer", "Base.WestpointMap" })
        local theirs = c.items._t[3]
        theirs:setStashMap("MulStashMap1")
        local n = M.onFill("bedroom", "wardrobe", c)
        local first, hammer = c.items._t[1]:getStashMap(), c.items._t[2]:getStashMap()
        C.Maps.loot = 0
        local c0 = crate({ "Base.MuldraughMap" })
        local none = M.onFill("bedroom", "wardrobe", c0)
        C.Maps.loot = 1
        SandboxVars.AnnotatedMapChance = 1
        local off = M.onFill("bedroom", "wardrobe", crate({ "Base.MuldraughMap" }))
        SandboxVars.AnnotatedMapChance = nil
        -- And as the game fires it.
        local c2 = crate({ "Base.RosewoodMap" })
        SIM.fire("OnFillContainer", "kitchen", "counter", c2)
        local fired = c2.items._t[1]:getStashMap()
        C.Maps.loot = was
        return n, first, hammer, theirs:getStashMap(), none, off, fired
    """)
    ours = (C.Maps.temple.stash, C.Maps.nest.stash)
    check(fill[0] == 1 and fill[1] in ours and fill[2] is None and fill[3] == "MulStashMap1",
          "a plain map in the game's loot becomes one of ours; a hammer and somebody else's annotated map do not (%s)"
          % (fill[1],))
    check(fill[4] == 0 and fill[5] == 0 and fill[6] in ours,
          "not when the dice say no, not with the sandbox's annotated maps off; and on the game's own event")

    # On the dead below ground, never above; in a crate as it is stocked.
    dead = L.execute("""
        local C, M = SEW.Config, SEW.Maps
        local was = C.Maps.dead
        C.Maps.dead = 1
        local below, above = SIM.newZombie(10600, 9400, -1, "Hobbo"), SIM.newZombie(10600, 9400, 0, "Hobbo")
        SIM.fire("OnZombieDead", below)
        SIM.fire("OnZombieDead", above)
        local function maps(z)
            local n = 0
            for _, it in ipairs(z.inv.items._t) do if it:getStashMap() then n = n + 1 end end
            return n
        end
        local a, b = maps(below), maps(above)
        C.Maps.dead = 0
        local never = SIM.newZombie(10600, 9400, -1, "Hobbo")
        SIM.fire("OnZombieDead", never)
        C.Maps.dead = was
        return a, b, maps(never)
    """)
    check(tuple(dead) == (1, 0, 0), "one of the dead below ground may carry one; nobody above, and not every time %s"
          % (tuple(dead),))
    crates = L.execute("""
        local C, M = SEW.Config, SEW.Maps
        local was, got, tries = C.Maps.crate, 0, 400
        for i = 1, tries do
            local c = SIM.Container(50)
            if M.crate(c, 10000 + i * 3, 9000 + i * 7) then got = got + 1 end
        end
        C.Maps.crate = 0
        local none = M.crate(SIM.Container(50), 10003, 9007)
        C.Maps.crate = was
        return got, tries, none
    """)
    check(5 <= crates[0] <= 50 and crates[2] is False,
          "a shelter's crate holds one now and then, by where it stands (%d of %d)" % (crates[0], crates[1]))
    # Placed: the nest's in the temple's scriptorium, the temple's in the warren.
    placed = L.execute("""
        -- The crate the generator named for each (its extra: m2 in the temple, m1 in the warren).
        local function holds(tables, code, stash)
            for _, items in pairs(tables) do
                for _, e in ipairs(items) do
                    if e[5] == code then
                        local sq = SIM.squares[e[1] .. "," .. e[2] .. ",-1"]
                        local o = sq and SEW.Util.findSprite(sq, e[3])
                        local c = o and SEW.Util.containerOf(o)
                        for _, it in ipairs(c and c:getItems()._t or {}) do
                            if it.getStashMap and it:getStashMap() == stash then return true end
                        end
                        return false
                    end
                end
            end
            return nil
        end
        return holds(SEW.Data.temple.furniture, "m2", SEW.Config.Maps.nest.stash),
               holds(SEW.Data[SEW.Index.warren.town].warren, "m1", SEW.Config.Maps.temple.stash)
    """)
    check(placed[0] is True and placed[1] is True,
          "the way to the nest is in the temple's scriptorium, the way to the temple in the warren %s" % (tuple(placed),))


def warren_test(L, p):
    """The warren (ROADMAP 0.6): the dens dug off the nest. Their caches,
    relics and dead are put down once, in a chunk a save built with the nest
    before there were dens as much as in a new one; the cult's marks go up on
    their earth; and the pages left there mark the temple's trapdoor."""
    g = L.globals()
    sim, SEW = g.SIM, g.SEW
    C = SEW.Config
    Wn = SEW.Index.warren
    check(Wn is not None and len(lua_list(Wn.dens)) >= 9, "the index has the warren and its dens")
    if Wn is None:
        return
    dens = lua_list(Wn.dens)
    dens = list(zip(dens[0::3], dens[1::3], dens[2::3]))
    p.x, p.y, p.z = SEW.Index.lair.tx + 0.5, SEW.Index.lair.ty + 0.5, -1
    sim.players = L.table(p)
    res = L.execute("""
        local B, s, T = SEW.Build, SEW.Build.state(), SEW.Data[SEW.Index.warren.town]
        local keys, old = {}, nil
        for k in pairs(T.warren) do keys[#keys + 1] = k end
        for k in pairs(T.warrenDead) do if not T.warren[k] then keys[#keys + 1] = k end end
        table.sort(keys)
        for _, k in ipairs(keys) do
            local cx, cy = k:match("(-?%d+),(-?%d+)")
            for dx = -1, 1 do for dy = -1, 1 do SIM.load(tonumber(cx) + dx, tonumber(cy) + dy) end end
        end
        -- One of them as a save from 0.5 has it: built, its caves done, no dens.
        old = keys[1]
        s.first[old], s.built[old], s.caves[old], s.warren[old] = "old", "old", "old", nil
        -- The dev menu's trip into the first den has been here already; whoever
        -- it put down is counted by where they stand.
        for _, k in ipairs(keys) do B.chunk(k) end
        local function standing()
            local at, n = {}, 0
            for _, z in ipairs(SIM.zombies) do at[z.x .. "," .. z.y .. "," .. z.outfit] = (at[z.x .. "," .. z.y .. "," .. z.outfit] or 0) + 1 end
            for _, k in ipairs(keys) do
                for _, e in ipairs(T.warrenDead[k] or {}) do n = n + (at[e[1] .. "," .. e[2] .. "," .. e[3]] or 0) end
            end
            return n
        end
        local function count()
            local pieces, stocked, relics, inOld = 0, 0, 0, 0
            for _, k in ipairs(keys) do
                for _, e in ipairs(T.warren[k] or {}) do
                    local sq = SIM.squares[e[1] .. "," .. e[2] .. ",-1"]
                    local o = sq and SEW.Util.findSprite(sq, e[3])
                    if o then
                        if k == old then inOld = inOld + 1 end
                        local c = SEW.Util.containerOf(o)
                        if c then
                            pieces = pieces + 1
                            if c:getItems():size() > 0 then stocked = stocked + 1 end
                        else
                            relics = relics + 1
                        end
                    end
                end
            end
            return pieces, stocked, relics, inOld
        end
        local pieces, stocked, relics, inOld = count()
        local want, wantDead = 0, 0
        for _, k in ipairs(keys) do want = want + #(T.warren[k] or {}); wantDead = wantDead + #(T.warrenDead[k] or {}) end
        B.settle()
        local dead = standing()
        -- And again, as the next revision would: nobody twice.
        for _, k in ipairs(keys) do s.built[k] = "older"; B.chunk(k) end
        B.settle()
        return pieces, stocked, relics, inOld, want, dead, wantDead, standing(), #(T.warren[old] or {})
    """)
    pieces, stocked, relics, in_old, want, dead, want_dead, dead2, old_n = res
    check(pieces >= 8 and stocked == pieces and pieces + relics == want,
          "the dens' caches are put down and stocked, their relics laid (%d crates, %d relics of %d)" % (pieces, relics, want))
    check(old_n >= 1 and in_old == old_n, "in a chunk a save built with the nest before there were dens, too (%d of %d)"
          % (in_old, old_n))
    check(dead == want_dead and want_dead >= 4, "the dead in the dens: %d of %d" % (dead, want_dead))
    check(dead2 == dead, "and nobody twice on a later pass (%d)" % dead2)
    marks = L.execute("""
        local T = SEW.Data[SEW.Index.warren.town]
        local n, hung = 0, 0
        for _, items in pairs(T.pictures) do
            for _, e in ipairs(items) do
                n = n + 1
                local sq = SIM.squares[e[1] .. "," .. e[2] .. ",-1"]
                if sq and SEW.Build.hasPicture(sq, e[3]) then hung = hung + 1 end
            end
        end
        return n, hung
    """)
    check(marks[0] >= 2 and marks[1] == marks[0], "the cult's marks are on the dens' earth (%d of %d)" % (marks[1], marks[0]))
    # Somebody arrives right beside where one of them should stand (through the
    # dev menu, or any way a chunk is first built round a player): that one is
    # owed, not lost, and is there once they have walked away.
    owed = L.execute("""
        local B, s, T = SEW.Build, SEW.Build.state(), SEW.Data[SEW.Index.warren.town]
        local p = SIM.players[1]
        local key, z
        for k, items in pairs(T.warrenDead) do key, z = k, items[1] end
        local function here()
            local n = 0
            for _, q in ipairs(SIM.zombies) do if q.x == z[1] and q.y == z[2] and not q.gone then n = n + 1 end end
            return n
        end
        for _, q in ipairs(SIM.zombies) do if q.x == z[1] and q.y == z[2] then q.x, q.gone = -1, true end end
        local px, py = p.x, p.y
        p.x, p.y = z[1] + 2.5, z[2] + 0.5
        s.warren[key], s.built[key] = nil, "older"
        B.chunk(key)
        local beside, waiting = here(), s.owed[key] and #s.owed[key] or 0
        SIM.tickN(40)
        local still = here()
        p.x, p.y = z[1] + 40.5, z[2] + 0.5
        SIM.tickN(40)
        local after, left = here(), s.owed[key]
        SIM.tickN(40)
        local again = here()
        p.x, p.y = px, py
        return beside, waiting, still, after, left == nil, again
    """)
    check(owed[0] == 0 and owed[1] >= 1 and owed[2] == 0,
          "one of the dead is not put down beside a player, and is owed (%d there, %d owed)" % (owed[0], owed[1]))
    check(owed[3] == 1 and owed[4] is True and owed[5] == 1,
          "and is there once they have walked away, once (%d, then %d)" % (owed[3], owed[5]))
    # Brother Amos's pages: in a den's cache, and they mark the temple's trapdoor.
    T = SEW.Index.temple
    page = L.execute("""
        for _, sq in pairs(SIM.squares) do
            for _, o in ipairs(sq.objects._t) do
                local c = SEW.Util.containerOf(o)
                for _, it in ipairs(c and c:getItems()._t or {}) do
                    if it:getFullType() == SEW.Config.JournalItem then
                        local j = SEW.Index.journals[it:getModData().SewarsJournal]
                        if j and j.text == "warren_1" then
                            SIM.players[1].inv:AddItem(it)
                            return it:getID(), j.x, j.y, j.town, sq.x, sq.y
                        end
                    end
                end
            end
        end
    """)
    check(page is not None and (page[1], page[2], page[3]) == (T.tx, T.ty, "temple"),
          "a pilgrim's last pages are in a den, and point at the temple's trapdoor")
    if page is not None:
        in_den = any(abs(page[4] - x) <= r + 1 and abs(page[5] - y) <= r + 1 for x, y, r in dens)
        marked = L.execute("return SEW.Story.readJournal(SIM.players[1], %d)" % page[0])
        check(in_den and marked is True, "reading them marks it on the reader's map")
    # A candle left burning in a den lights it for whoever is there.
    lx, ly = Wn.lights[1], Wn.lights[2]
    p.x, p.y = lx + 1.5, ly + 0.5
    sim.tickN(100)
    lit = L.execute("for l in pairs(SIM.lamps) do if l.x == %d and l.y == %d then return true end end return false" % (lx, ly))
    check(lit is True, "the pilgrims' candles are lit")


def temple_test(L, p):
    """The temple of the rat cult (DESIGN.md 7d): the trapdoor in the field
    over it, down to its postern; the hall built -- floors, the idol and its
    triptych, pictures hung on their walls, the cult's dead turned to the
    slab, rats let loose in it, its lights; the book that marks the nest
    under Louisville; and the breach into a town's sewer, with the cult's
    marks reaching a chunk a save built before there was a temple."""
    g = L.globals()
    sim, SEW = g.SIM, g.SEW
    C = SEW.Config
    T = SEW.Index.temple
    check(T is not None and SEW.Data.temple is not None and len(lua_list(T.breaches)) >= 2,
          "the index has the temple and its passages")
    if T is None:
        return
    tx, ty, ix, iy = int(T.tx), int(T.ty), int(T.x), int(T.y)
    shaft = SEW.Index.shafts["%d,%d" % (tx, ty)]
    check(shaft is not None and shaft.trapdoor is True and shaft.made is True and shaft.town == "temple",
          "its way out is a shaft of its own, under a trapdoor")

    # In the field over it: the trapdoor goes into the ground as somebody comes near.
    q = sim.newPlayer("field", tx + 0.5, ty + 1.5, 0)
    q.hours = 50
    sim.players = L.table(q)
    street(L, tx, ty, 3, manhole=False)
    check(TEXT["ContextMenu_SEW_HatchDown"] not in [nm for nm, _ in options(menu(L, 0, tx, ty))],
          "no trapdoor in the field before the server has set it in")
    L.execute("SandboxVars.Sewars.Rats = 4")
    sim.tickN(20)
    here = objects_at(L, tx, ty, 0)
    check(L.execute("return SEW.Build.state().covers['%d,%d']" % (tx, ty)) == "placed"
          and C.Sprites.hatch in here and C.Sprites.cover not in here,
          "a player in the field: a trapdoor, not an iron cover (%s)" % here)
    m = menu(L, 0, tx, ty)
    opt = [o for nm, o in options(m) if nm == TEXT["ContextMenu_SEW_HatchDown"]]
    check(len(opt) == 1 and opt[0].toolTip.description == TEXT["Tooltip_SEW_Trap"],
          "it offers Climb down through the hatch, and says it is a trapdoor in a field")
    sounds0 = len(lua_list(sim.sounds))
    choose(m, TEXT["ContextMenu_SEW_HatchDown"])
    sim.runActions()
    sim.tickN(3)
    check(abs(q.z + 1) < 1e-6 and int(q.x) == tx and int(q.y) == ty,
          "down to the foot of the postern's ladder (%.1f,%.1f,%.1f)" % (q.x, q.y, q.z))
    check("SEW_Lid" not in lua_list(sim.sounds)[sounds0:], "and no iron lid scraping")
    lobjs = objects_at(L, tx, ty, -1)
    check(any(x in ("sewars_01_0", "sewars_01_1") for x in lobjs), "a ladder hangs under the trapdoor (%s)" % lobjs)
    up = [o for nm, o in options(menu(L, 0, tx, ty)) if nm == TEXT["ContextMenu_SEW_HatchUp"]]
    check(len(up) == 1 and up[0].toolTip.description == TEXT["Tooltip_SEW_TrapUp"],
          "below, it offers the way back up into the field")

    # The whole of it built, as walking it would: every chunk of the temple
    # that is loaded (the far ends of its passages are not) -- with somebody
    # standing at the slab as the hall is built round them. Those who stand
    # round it are owed, not lost: they are there once that somebody has left.
    q.x, q.y = ix + 0.5, iy + 6.5
    built = L.execute("""
        local B, n, left = SEW.Build, 0, 0
        for k in pairs(SEW.Data.temple.chunks) do
            if B.chunk(k) then n = n + 1 else left = left + 1 end
        end
        local owed, near = 0, 0
        for _, list in pairs(B.state().owed) do owed = owed + #list end
        local p = SIM.players[1]
        for _, z in ipairs(SIM.zombies) do
            if z.outfit == SEW.Config.Temple.outfit and math.abs(z.x - p.x) < 8 and math.abs(z.y - p.y) < 8 then near = near + 1 end
        end
        return n, left, owed, near
    """)
    check(built[0] >= 60, "the temple's chunks are built (%d, %d of its passages not loaded)" % (built[0], built[1]))
    # (Some of the circle were put down before, by the trips above; the rest are owed.)
    check(built[2] >= 3, "built round somebody at the slab, those of the circle not yet there are owed (%d)" % built[2])
    q.x, q.y = tx + 0.5, ty + 0.5
    sim.tickN(30)
    check(L.execute("local n = 0; for _ in pairs(SEW.Build.state().owed) do n = n + 1 end; return n") == 0,
          "and stands there once they have gone")
    S = C.Sprites
    check(S.floorTemple in objects_at(L, ix - 6, iy + 8, -1) and S.floorCarpet in objects_at(L, ix, iy + 8, -1),
          "stone under the hall, the red runner down its nave")
    at = objects_at(L, ix, iy, -1)
    check(S.cult.idol in at and S.cult.mural[2] in at,
          "the idol at the head of the hall, the middle of its triptych on the wall behind (%s)" % at)
    loose = L.execute("""
        local wall, loose, hung = {}, 0, 0
        local Sp = SEW.Config.Sprites.cult
        for _, k in ipairs({ "sigil", "burrow", "torch", "banner" }) do wall[Sp[k].N], wall[Sp[k].W] = true, true end
        for _, v in ipairs(Sp.mural) do wall[v] = true end
        for _, items in pairs(SEW.Data.temple.pictures) do
            for _, e in ipairs(items) do
                local sq = SIM.squares[e[1] .. "," .. e[2] .. ",-1"]
                if sq then
                    for _, o in ipairs(sq.objects._t) do if wall[o.sprite:getName()] then loose = loose + 1 end end
                    if SEW.Build.hasPicture(sq, e[3]) then hung = hung + 1 end
                end
            end
        end
        return loose, hung
    """)
    check(loose[0] == 0 and loose[1] >= 40, "its pictures are hung on their walls, none loose (%d hung, %d loose)"
          % (loose[1], loose[0]))
    dead = L.execute("""
        local want, faced_want, got, faced, strangers = 0, 0, 0, 0, 0
        local mine = {}
        for _, items in pairs(SEW.Data.temple.claimed) do
            for _, e in ipairs(items) do
                want = want + 1
                if e[4] then faced_want = faced_want + 1 end
                mine[e[1] .. "," .. e[2]] = e[3]
            end
        end
        for _, z in ipairs(SIM.zombies) do
            if SEW.Build.townOf(math.floor(z.x / 8) .. "," .. math.floor(z.y / 8)) == "temple" then
                if mine[z.x .. "," .. z.y] == z.outfit then got = got + 1 else strangers = strangers + 1 end
                if z.facing then faced = faced + 1 end
            end
        end
        return want, faced_want, got, faced, strangers
    """)
    check(dead[0] >= 20 and dead[2] == dead[0] and dead[4] == 0,
          "the cult's dead are put down where they stood, and none of the tunnels' (%d of %d, %d strangers)"
          % (dead[2], dead[0], dead[4]))
    check(dead[1] >= 8 and dead[3] == dead[1], "those round the slab are turned to it (%d of %d)" % (dead[3], dead[1]))
    cultists = L.execute("local n = 0; for _, z in ipairs(SIM.zombies) do if z.outfit == SEW.Config.Temple.outfit then n = n + 1 end end; return n")
    check(cultists >= 15 and C.Temple.outfit in OUTFITS, "in the cult's robes, an outfit the game has (%d)" % cultists)
    rats = L.execute("""
        local n = 0
        for _, a in ipairs(SIM.animals) do
            if not a.removed and a.kind ~= "rous" and SEW.Build.townOf(math.floor(a.x / 8) .. "," .. math.floor(a.y / 8)) == "temple" then
                n = n + 1
            end
        end
        return n
    """)
    check(rats >= 3, "rats run loose in it (%d)" % rats)
    L.execute("SandboxVars.Sewars.Rats = 1")

    # Its book: in the sanctum's shelves, and it marks the nest under Louisville.
    book = L.execute("""
        for _, sq in pairs(SIM.squares) do
            if sq.z == -1 and SEW.Build.townOf(math.floor(sq.x / 8) .. "," .. math.floor(sq.y / 8)) == "temple" then
                for _, o in ipairs(sq.objects._t) do
                    local c = SEW.Util.containerOf(o)
                    for _, it in ipairs(c and c:getItems()._t or {}) do
                        if it:getFullType() == SEW.Config.JournalItem then
                            local j = SEW.Index.journals[it:getModData().SewarsJournal]
                            if j and j.text == "cult_1" then
                                SIM.players[1].inv:AddItem(it)
                                return it:getID(), j.x, j.y, j.kind, j.town
                            end
                        end
                    end
                end
            end
        end
    """)
    lair = SEW.Index.lair
    check(book is not None and book[1] == lair.tx and book[2] == lair.ty and book[3] == "lair" and book[4] == lair.town,
          "the Book of the Burrow is on its shelf, and points at the nest's false wall")
    if book is not None:
        title, lines = SEW.StoryUI.page(L.execute("return SEW.Index.journals"
                                                  "[SIM.players[1].inv:getItemWithID(%d):getModData().SewarsJournal] and "
                                                  "SIM.players[1].inv:getItemWithID(%d):getModData().SewarsJournal"
                                                  % (book[0], book[0])))
        check(title == TEXT["IGUI_SEW_J_cult_1_Title"] and len(lua_list(lines)) > 5, "it reads (%s)" % title)
        marked = L.execute("return SEW.Story.readJournal(SIM.players[1], %d)" % book[0])
        mark = L.execute("""
            for _, m in pairs(SEW.Discovery.record(SIM.players[1]).m) do
                if m.x == SEW.Index.lair.tx and m.y == SEW.Index.lair.ty then return true end
            end
            return false
        """)
        check(marked is True and mark is True, "reading it marks the nest on the reader's map")

    # In the hall: firelight, and a word the first time.
    q.x, q.y = ix + 0.5, iy + 20.5
    notes0 = len(lua_list(sim.notes))
    sim.tickN(100)
    check(any(n == TEXT["IGUI_SEW_TempleHall"] for n in lua_list(sim.notes)[notes0:]),
          "the first sight of the hall is worth a word (%s)" % lua_list(sim.notes)[notes0:][:2])
    lamps = L.execute("""
        local T = SEW.Index.temple
        local fire, trap, n = {}, false, 0
        for i = 1, #T.lights, 2 do fire[T.lights[i] .. "," .. T.lights[i + 1]] = true end
        for l in pairs(SIM.lamps) do
            if fire[l.x .. "," .. l.y] then n = n + 1 end
            if l.x == T.tx and l.y == T.ty then trap = true end
        end
        return n, trap, #T.lights / 2
    """)
    check(lamps[0] >= 10, "its sconces, braziers and candles are lit round the player (%d of %d)" % (lamps[0], lamps[2]))
    q.x, q.y = tx + 0.5, ty + 0.5
    sim.tickN(100)
    trap = L.execute("for l in pairs(SIM.lamps) do if l.x == %d and l.y == %d then return true end end return false" % (tx, ty))
    check(trap is False, "and no daylight comes through a trapdoor")

    # Where the cult broke into a town's sewer -- in a chunk a save built
    # before there was a temple: the breach is knocked through, and their
    # marks go up on walls that were already there.
    b = T.breaches[1]
    bx, by, ex, ey = int(b.tx), int(b.ty), int(b.ex), int(b.ey)
    q.x, q.y, q.z = bx + 0.5, by + 0.5, 0
    street(L, bx, by, 2, manhole=False)
    res = L.execute("""
        local town, bx, by = ...
        local B, s = SEW.Build, SEW.Build.state()
        local keys, pics = {}, 0
        for kx = math.floor(bx / 8) - 2, math.floor(bx / 8) + 2 do
            for ky = math.floor(by / 8) - 2, math.floor(by / 8) + 2 do
                local k = kx .. "," .. ky
                if B.townOf(k) == town then keys[#keys + 1] = k end
            end
        end
        for _, k in ipairs(keys) do B.chunk(k) end
        local old = nil
        for _, k in ipairs(keys) do
            if SEW.Data[town].pictures[k] then old = k end
        end
        if not old then return nil end
        -- As a save from before the temple has it: built, with nothing hung.
        for _, e in ipairs(SEW.Data[town].pictures[old]) do
            local sq = SIM.squares[e[1] .. "," .. e[2] .. ",-1"]
            for _, o in ipairs(sq.objects._t) do o.attached = nil end
        end
        s.hung[old], s.built[old] = nil, "old"
        B.chunk(old)
        local hung = 0
        for _, e in ipairs(SEW.Data[town].pictures[old]) do
            pics = pics + 1
            if B.hasPicture(SIM.squares[e[1] .. "," .. e[2] .. ",-1"], e[3]) then hung = hung + 1 end
        end
        return pics, hung, s.hung[old] ~= nil
    """, b.town, bx, by)
    check(res is not None and res[0] >= 1 and res[1] == res[0] and res[2] is True,
          "the cult's marks by the breach reach a chunk built before the temple (%s)" % (res,))
    hold = objects_at(L, max(bx, ex), max(by, ey), -1)
    frames = [S.doorFrame.N, S.doorFrame.W]
    holes = [S.breach.o.N, S.breach.o.W, S.breach.q.N, S.breach.q.W]
    check(any(f in hold for f in frames) and any(h in hold for h in holes),
          "the sewer's wall is broken through where the passage meets it (%s)" % hold)
    check(any(f in objects_at(L, ex, ey, -1) for f in lua_list(S.floorCave)), "onto dug earth")
    # The temple's sheet lies over the end of this town's: in its sewer, the map is the town's.
    t0, tt = SEW.Index.towns[b.town], SEW.Index.towns.temple
    over = tt.x0 <= ex <= tt.x1 and tt.y0 <= ey <= tt.y1 and t0.x0 <= ex <= t0.x1 and t0.y0 <= ey <= t0.y1
    # Whichever of the two the table happens to hand over first: pairs() is in
    # no order, so the towns are walked temple first, then temple last.
    ans = L.execute("""
        local town, ex, ey = ...
        local real, out = SEW.Index.towns, {}
        for _, order in ipairs({ { "temple", town }, { town, "temple" } }) do
            SEW.Index.towns = setmetatable({}, { __index = real, __pairs = function()
                local i = 0
                return function()
                    i = i + 1
                    if order[i] then return order[i], real[order[i]] end
                end
            end })
            out[#out + 1] = SEW.Map.townAt(ex, ey)
        end
        SEW.Index.towns = real
        return out[1], out[2]
    """, b.town, ex, ey)
    check(over and ans[0] == b.town and ans[1] == b.town and SEW.Map.townAt(ix, iy) == "temple",
          "through the breach the sewer map is still %s's, in the hall the temple's (%s, %s)"
          % (b.town, ans, SEW.Map.townAt(ix, iy)))
    q.z = 0


def rooms_test(L, p, server):
    """No square of the sewer's keeps a room on a server (SEW_Rooms): a room the
    engine has blanked, under a player, stops the whole server. Taken off at
    load, at build, at a climb's foot and round a player -- each asked alone --
    and never off a square that is not ours, and never in single player."""
    g = L.globals()
    sim = g.SIM
    # Two squares of built tunnel side by side, in Muldraugh.
    x, y, x2, y2 = L.execute("""
        local B, T, U = SEW.Build, SEW.Data.muldraugh, SEW.Util
        local function tunnel(ax, ay)
            local sq = SIM.squares[ax .. "," .. ay .. ",-1"]
            local f = sq and U.floorOf(sq)
            return f and U.isOurs(f) and f.sprite:getName() == SEW.Config.Sprites.floorTunnel
        end
        local keys = {}
        for k in pairs(T.chunks) do if B.state().first[k] then keys[#keys + 1] = k end end
        table.sort(keys)
        for _, k in ipairs(keys) do
            local cx, cy = k:match("(-?%d+),(-?%d+)")
            for ax = cx * 8 + 1, cx * 8 + 5 do for ay = cy * 8 + 1, cy * 8 + 6 do
                if tunnel(ax, ay) and tunnel(ax + 1, ay) then return ax, ay, ax + 1, ay end
            end end
        end
    """)
    blank = L.eval("""function(x, y)
        local sq = SIM.squares[x .. "," .. y .. ",-1"]
        sq.room, sq.roomId = { building = nil }, 7
    end""")
    room = L.eval('function(x, y) return SIM.squares[x .. "," .. y .. ",-1"]:getRoom() ~= nil end')
    tick = L.eval("function(n) return (pcall(SIM.tickN, n)) end")
    old = p.x, p.y, p.z
    p.x, p.y, p.z = x + 0.5, y + 0.5, -1
    check(tick(3), "a player in the sewer, and the world goes on")

    if not server:
        # Single player: the engine keeps a square's room in step itself.
        blank(x2, y2)
        sim.unload(x2 // 8, y2 // 8)
        sim.load(x2 // 8, y2 // 8)
        L.execute("SEW.Build.square(%d, %d, SEW.Build.recordAt(%d, %d), false, false)" % (x2, y2, x2, y2))
        tick(3)
        n = L.execute("return SEW.Rooms.around(%d, %d, 3)" % (x, y))
        check(room(x2, y2) and n == 0, "in single player a square's room is the engine's to keep (%s)" % n)
        L.execute('local sq = SIM.squares["%d,%d,-1"]; sq.room, sq.roomId = nil, nil' % (x2, y2))
        p.x, p.y, p.z = old
        return

    # The simulation first: a blanked room under a player stops the tick.
    blank(x, y)
    L.execute("SEW_on = SEW.Rooms.on; SEW.Rooms.on = function() return false end")
    stopped = not tick(1)
    L.execute("SEW.Rooms.on = SEW_on")
    check(stopped, "a room with no building under a player stops the server (the simulation's engine)")

    # Load: the chunk is read in, and its squares get the map's rooms back.
    p.x, p.y, p.z = old
    sim.unload(x // 8, y // 8)
    sim.load(x // 8, y // 8)
    check(not room(x, y), "a chunk loads on a server: no square of ours keeps a room")
    p.x, p.y, p.z = x + 0.5, y + 0.5, -1
    check(tick(2), "and a player stands there with the server running")

    # Walk: a room that turns up one square ahead of a player is gone before they step.
    blank(x2, y2)
    tick(1)
    check(not room(x2, y2), "a room one square from a player in the sewer comes off within a tick")
    p.x = x2 + 0.5
    check(tick(2), "and they walk on to it")

    # Build: the builder revisits the square.
    p.x, p.y, p.z = old
    blank(x, y)
    L.execute("SEW.Build.square(%d, %d, SEW.Build.recordAt(%d, %d), false, false)" % (x, y, x, y))
    check(not room(x, y), "a square the builder revisits keeps no room")

    # A climb: the foot of the ladder, before anybody is sent there.
    mx, my = L.execute("""
        local keys = {}
        for k, s in pairs(SEW.Index.shafts) do
            if s.town == "muldraugh" and not s.hatch and not s.made and not s.outfall then keys[#keys + 1] = k end
        end
        table.sort(keys)
        for _, k in ipairs(keys) do
            local s = SEW.Index.shafts[k]
            if SIM.squares[s.x .. "," .. s.y .. ",-1"] and SEW.Build.isCurrent(math.floor(s.x / 8) .. "," .. math.floor(s.y / 8)) then
                return s.x, s.y
            end
        end
    """)
    blank(mx, my)
    p.x, p.y, p.z = mx + 0.5, my + 0.5, 0
    granted = L.execute("return SEW.Server.grant(SIM.players[1], %d, %d, 'down')" % (mx, my))
    check(granted and not room(mx, my), "a climb down is granted on to squares with no room (%s)" % granted)

    # Somebody's basement at the same level keeps its rooms.
    kept = L.execute("""
        local x, y = ...
        local sq = SIM.squares[x .. "," .. y .. ",-1"]
        local theirs = {}
        for _, o in ipairs(sq.objects._t) do theirs[#theirs + 1] = { o, o.md.sew } o.md.sew = nil end
        sq.room, sq.roomId = { building = {} }, 9
        SIM.unload(math.floor(x / 8), math.floor(y / 8))
        SIM.load(math.floor(x / 8), math.floor(y / 8))
        local n = SEW.Rooms.around(x, y, 0)
        local kept = sq:getRoom() ~= nil
        for _, t in ipairs(theirs) do t[1].md.sew = t[2] end
        sq.room, sq.roomId = nil, nil
        return kept and n == 0
    """, x, y)
    check(kept, "a square with nothing of ours on it keeps its room")
    check(L.execute("return SEW.Rooms.cleared") == 4, "four rooms taken off, and each said so once (%s)"
          % L.execute("return SEW.Rooms.cleared"))
    p.x, p.y, p.z = old


def street_test(L, p):
    """The street does not hear the sewer (SEW_Street): a zombie on the road
    on its way to a player's sound under it is stopped -- and nobody else's
    zombie, no other sound, no other place, and not with the sandbox's Yes."""
    g = L.globals()
    sim, SEW = g.SIM, g.SEW
    C = SEW.Config
    # A square of tunnel that is built, in Muldraugh.
    x, y = L.execute("""
        local B, T = SEW.Build, SEW.Data.muldraugh
        local keys = {}
        for k in pairs(T.chunks) do if B.state().first[k] then keys[#keys + 1] = k end end
        table.sort(keys)
        for _, k in ipairs(keys) do
            local cx, cy = k:match("(-?%d+),(-?%d+)")
            for ax = cx * 8, cx * 8 + 7 do for ay = cy * 8, cy * 8 + 7 do
                local sq = SIM.squares[ax .. "," .. ay .. ",-1"]
                local f = sq and SEW.Util.floorOf(sq)
                if f and SEW.Util.isOurs(f) and f.sprite:getName() == SEW.Config.Sprites.floorTunnel then return ax, ay end
            end end
        end
    """)
    L.execute("""
        function SIM.streetCase(zx, zy, zz, tx, ty, tz, remote, moving)
            local zed = SIM.hearingZombie(zx, zy, zz, tx, ty, tz, remote)
            if moving == false then zed.vars.bPathfind = false end
            SIM.updateZombie(zed)
            return zed.path == nil, zed.vars.bPathfind, zed.vars.bMoving
        end
    """)

    def case(zx, zy, zz, tx, ty, tz, remote=False, moving=True):
        return L.execute("return SIM.streetCase(%f, %f, %f, %d, %d, %d, %s, %s)"
                         % (zx, zy, zz, tx, ty, tz, "true" if remote else "false", "true" if moving else "false"))

    p.x, p.y, p.z = x + 0.5, y + 0.5, -1
    sim.tickN(C.Street.every)
    check(len(lua_list(SEW.Street.below)) == 1, "a player in the sewer is written down (%d)" % len(lua_list(SEW.Street.below)))
    stopped, pathfind, moving = case(x + 6.5, y + 0.5, 0, x + 2, y + 1, -1)
    check(stopped and pathfind is False and moving is False,
          "a zombie on the street going to a player's sound under it is stopped, as the engine stops one (%s, %s, %s)"
          % (stopped, pathfind, moving))
    check(not case(x + 6.5, y + 0.5, -1, x + 2, y + 1, -1)[0], "one in the sewer still comes")
    check(not case(x + 6.5, y + 0.5, 0, x + 2, y + 1, 0)[0], "and one on the street still goes to a sound on the street")
    check(not case(x + 6.5, y + 0.5, 0, x + 2 + C.Street.reach * 3, y + 1, -1)[0],
          "and to one below ground that is nowhere near a player in the sewer")
    check(not case(x + 6.5, y + 0.5, 0, x + 2, y + 1, -1, remote=True)[0], "another client's zombie is left to its owner")
    check(not case(x + 6.5, y + 0.5, 0, x + 2, y + 1, -1, moving=False)[0],
          "a zombie not on its way to a player's sound is not touched")

    # The sandbox's Yes: the game's own rule.
    L.execute("SandboxVars.Sewars.StreetHears = 2")
    sim.tickN(C.Street.every)
    check(not case(x + 6.5, y + 0.5, 0, x + 2, y + 1, -1)[0], "with the sandbox's Yes the street hears as the game has it")
    L.execute("SandboxVars.Sewars.StreetHears = nil")

    # Somebody else's basement at the same level: the house over it hears.
    bx, by = x + 400, y + 400
    sim.load(bx // 8, by // 8)
    L.execute("""
        local sq = getCell():getOrCreateGridSquare(%d, %d, -1)
        sq.objects._t = {}
        sq.objects:add(IsoObject.new(sq, "floors_interior_tilesandwood_01_0", ""))
    """ % (bx, by))
    p.x, p.y, p.z = bx + 0.5, by + 0.5, -1
    sim.tickN(C.Street.every)
    check(not case(bx + 6.5, by + 0.5, 0, bx + 1, by + 1, -1)[0],
          "over a basement that is not ours, the house still hears what is done in it")
    # And a player on the street, standing on something of ours (a cover).
    L.execute("""
        local sq = getCell():getOrCreateGridSquare(%d, %d, 0)
        sq.objects._t = {}
        local o = IsoObject.new(sq, "floors_exterior_street_01_0", "")
        o:getModData()[SEW.Config.Tag] = true
        sq.objects:add(o)
    """ % (bx, by))
    p.x, p.y, p.z = bx + 0.5, by + 0.5, 0
    sim.tickN(C.Street.every)
    check(not case(bx + 6.5, by + 0.5, 0, bx + 1, by + 1, -1)[0], "nor is a player up on the street in the sewer")
    # The sewer's sounds belong to the sewer (found by a player: drips, rats
    # and a groan in every basement). Still in that basement, with a sound
    # long overdue each time it is asked (the client asks every 30 ticks):
    p.x, p.y, p.z = bx + 0.5, by + 0.5, -1
    ours = set(lua_list(C.Ambience))
    n0 = len(lua_list(sim.sounds))
    for i in range(1, 6):
        SEW.Client.ambience(p, 10000000 * i)
    heard = [s for s in lua_list(sim.sounds)[n0:] if s in ours]
    check(not heard, "in a basement that is not ours the sewer's sounds are not played (%s)" % heard[:2])
    p.x, p.y, p.z = x + 0.5, y + 0.5, -1
    n0 = len(lua_list(sim.sounds))
    for i in range(6, 11):
        SEW.Client.ambience(p, 10000000 * i)
    heard = [s for s in lua_list(sim.sounds)[n0:] if s in ours]
    check(len(heard) == 5, "and in the sewer they are (%d of 5)" % len(heard))
    sim.tickN(C.Street.every)


def single_player():
    print("single player")
    L = process("sp")
    g = L.globals()
    sim, SEW = g.SIM, g.SEW
    check(SEW.Build is not None and SEW.Server is not None and SEW.Client is not None,
          "single player loads the server's files and the client's")
    shafts = pick_shafts(L)
    check(len(shafts) > 50, "Muldraugh has shafts in the index (%d)" % len(shafts))
    mx, my, lx, ly, st = shafts[len(shafts) // 2]
    street(L, mx, my, 6)
    p = sim.newPlayer("sp", mx + 3.5, my + 0.5, 0)
    sim.players = L.table(p)
    sim.fire("OnGameStart")
    # Just standing on the street for a few seconds, the most ordinary state
    # there is -- and the one 0.2.0 never ticked, so a per-90-tick call to a
    # function Kahlua lacks (next) froze the game and passed here.
    sim.tickN(400)
    check(not warns(L), "a few seconds on the street log nothing (%s)" % warns(L)[:2])

    # The dev build's kit: nothing without the flag, once with it, never twice.
    sim.fire("OnCreatePlayer", 0, p)
    check(not p.inv.containsTypeRecurse(p.inv, "HandTorch"), "no test kit outside the dev build")
    SEW.Dev = True
    sim.fire("OnCreatePlayer", 0, p)
    sim.fire("OnCreatePlayer", 0, p)
    torches = L.execute("local n = 0; for _, it in ipairs(SIM.players[1].inv.items._t) do if it:getType() == 'HandTorch' then n = n + 1 end end; return n")
    check(torches == 1 and p.inv.containsTypeRecurse(p.inv, "Crowbar"),
          "the dev build gives the kit once (%d torch)" % torches)
    SEW.Dev = None

    # Above ground, the engine's answer stands.
    check(SEW.Compat.wrapped == 3, "isOutside is wrapped on squares, players and characters (%s)" % SEW.Compat.wrapped)
    check(L.execute("return getPlayer():isOutside() and getCell():getGridSquare(%d, %d, 0):isOutside()" % (mx, my)) is True,
          "on the street the player and the square are outside")

    # Climbing down.
    m = menu(L, 0, mx, my)
    names = [n for n, _ in options(m)]
    check(TEXT["ContextMenu_SEW_Enter"] in names, "a cover offers Climb down (%s)" % names)
    m = menu(L, 0, mx + 1, my)
    check(TEXT["ContextMenu_SEW_Enter"] in [n for n, _ in options(m)], "a click one square off still finds it")
    m = menu(L, 0, mx + 4, my + 4)
    check(not options(m), "a click nowhere near offers nothing")
    choose(menu(L, 0, mx, my), TEXT["ContextMenu_SEW_Enter"])
    check(len(sim.queue) == 1, "choosing it queues the climb")
    sim.runActions()
    check(any("SEW_Lid" == s for s in lua_list(sim.sounds)), "the lid scrapes")
    sim.tickN(3)
    check(abs(p.z - (-1)) < 1e-6 and int(p.x) == mx and int(p.y) == my,
          "the player is at the foot of the shaft (%.1f, %.1f, %.1f)" % (p.x, p.y, p.z))
    objs = objects_at(L, mx, my, -1)
    check(any(o.startswith("location_sewer_01_4") for o in objs), "the shaft floor is grating (%s)" % objs)
    ladder_objs = objects_at(L, lx, ly, -1)
    check(any(o in ("sewars_01_0", "sewars_01_1") for o in ladder_objs), "the ladder hangs at %d,%d" % (lx, ly))
    sim.tickN(20)
    check(p.noVault is True, "the vault switch is on below")
    rats = L.execute("""
        local n, bad, kinds = 0, 0, {}
        for _, a in ipairs(SIM.animals) do
            if a.kind == "rat" or a.kind == "ratfemale" then
                n = n + 1
                kinds[a.kind .. "/" .. a.breed] = true
                -- In the middle of the square, not on its corner (the wall line).
                if a.x % 1 ~= 0.5 or a.y % 1 ~= 0.5 then bad = bad + 1 end
                local sq = SIM.squares[math.floor(a.x) .. "," .. math.floor(a.y) .. "," .. a.z]
                if a.z ~= -1 or not (sq and SEW.Util.floorOf(sq)) or not a.inWorld then bad = bad + 1 end
            end
        end
        local k = 0
        for _ in pairs(kinds) do k = k + 1 end
        return n, bad, k
    """)
    check(rats[0] > 0 and rats[1] == 0,
          "vanilla's rats are down here, in the middle of walkway squares (%d, %d misplaced, %d kinds)" % rats)
    # The leash: one that has got through a wall is put back, one with no
    # walkway near is taken away.
    leash = L.execute("""
        local rat
        for _, a in ipairs(SIM.animals) do if a.kind == "rat" or a.kind == "ratfemale" then rat = a break end end
        local x, y = math.floor(rat.x), math.floor(rat.y)
        local rock
        for dx = -3, 3 do for dy = -3, 3 do
            local sq = SIM.squares[(x + dx) .. "," .. (y + dy) .. ",-1"]
            local f = sq and SEW.Util.floorOf(sq)
            if f and f.sprite:getName() == SEW.Config.Sprites.floorRock then rock = { x + dx, y + dy } end
        end end
        SEW.Nest.place(rat, rock[1] + 0.5, rock[2] + 0.5)
        local lost = SEW.Nest.addAnimal(x, y, "rat", "grey")
        SEW.Nest.place(lost, x + 40.5, y + 40.5)
        -- On its own clock, not asked: the server's tick does it.
        SIM.tickN(SEW.Config.LeashEvery)
        local back = rat.square and SEW.Util.floorOf(rat.square)
        return back ~= nil
            and back.sprite:getName() ~= SEW.Config.Sprites.floorRock and lost.removed == true
    """)
    check(leash is True, "a rat that got through a wall is put back on the walkway, one far off it taken away")
    notes = lua_list(sim.notes)
    check(any("Down into the dark" in n for n in notes), "the arrival note (%s)" % notes[-1:])

    # Below ground is indoors to anybody who asks from Lua (Flying Birds flew
    # its flocks over the sewer: the engine calls a tunnel square outdoors).
    below = L.execute("""
        local sq = getCell():getGridSquare(%d, %d, -1)
        local street = getCell():getGridSquare(%d, %d, 0)
        local engine = rawget(getmetatable(sq).__index, "SEW_isOutsideEngine")
        return engine ~= nil and engine(sq), getPlayer():isOutside(), sq:isOutside(),
               SIM.newCharacter(sq):isOutside(), SIM.newCharacter(street):isOutside()
    """ % (mx, my, mx, my))
    check(below[0] is True, "the engine's own answer for a tunnel square is outdoors (the sim is not being kind)")
    check(below[1] is False and below[2] is False and below[3] is False,
          "below, the player, the square and a zombie are not outside (%s)" % (below[1:4],))
    check(below[4] is True, "a zombie on the street still is")
    check(L.execute("""
        local index = getmetatable(getPlayer()).__index
        local engine = rawget(index, "SEW_isOutsideEngine")
        SEW.Compat.install()
        return engine ~= nil and rawget(index, "SEW_isOutsideEngine") == engine and getPlayer():isOutside() == false
    """) is True, "a second install wraps the engine's method, not its own wrapper")
    sim.tickN(100)
    check(len([k for k in sim.lamps.keys()]) > 0, "a lamp hangs at the shaft")

    # The map: what was walked is recorded by the server and mirrored here.
    key = "%d,%d" % (mx // 8, my // 8)
    rec = L.execute("return SEW.Discovery.record(SIM.players[1])")
    check(rec.c[key] is not None, "walking below records the chunk on the server (%s)" % key)
    check(SEW.Map.state.c[key] is not None, "and the client's map knows it")
    check(rec.l["%d,%d" % (mx, my)] is not None and SEW.Map.state.l["%d,%d" % (mx, my)] is not None,
          "the ladder climbed is on both")
    m = menu(L, 0, mx, my)
    check(TEXT["ContextMenu_SEW_Map"] in [n for n, _ in options(m)], "below, the menu offers the sewer map")
    choose(m, TEXT["ContextMenu_SEW_Map"])
    win = SEW.Map.window
    check(win is not None and sim.ui[win], "the map opens")
    if win is not None:
        sim.draws = L.table()
        win.prerender(win)
        win.render(win)
        draws = lua_list(sim.draws)
        tex = [d for d in draws if d.kind == "texture"]
        fog = [d for d in draws if d.kind == "rect" and d.extra and abs(d.extra[1] - 0.16) < 1e-6]
        gold = [d for d in draws if d.kind == "rect" and d.extra and abs(d.extra[1] - 0.85) < 1e-6]
        # Clipped to the map's own view, under the title bar -- not merely to the
        # window, which vanilla's prerender already does and which would let the
        # map paint over its own title bar and footer.
        top = win.titleBarHeight(win)
        in_view = lambda d: d.stencil is not None and d.stencil[2] >= top and d.stencil[2] + d.stencil[4] < win.height
        check(len(tex) > 0 and all(in_view(d) for d in tex), "the plan's tiles are drawn, clipped to the map's view (%d)" % len(tex))
        check(0 < len(fog) < 3000 and all(in_view(d) for d in fog), "the fog is drawn as merged runs, in the view (%d rects)" % len(fog))
        check(len(gold) >= 1, "the ladder used is marked")
        W, H = win.width, win.height
        out = [d for d in draws if not d.clipped and (d.x < -1 or d.y < -1 or d.x + d.w > W + 1 or d.y + d.h > H + 1)]
        check(not out, "nothing unclipped is drawn outside the panel (%s)" % [(d.kind, d.x, d.y) for d in out][:3])
        covered = L.execute('''
            local tid, cx, cy = ...
            for _, r in ipairs(SEW.Map.fog(tid)) do
                if r[2] == cy and cx >= r[1] and cx <= r[3] then return true end
            end
            return false
        '''.replace("local tid, cx, cy = ...", 'local tid, cx, cy = "%s", %d, %d' % (win.tid, mx // 8, my // 8)))
        check(covered is False, "the chunk the player walked is not under the fog")
        z0 = win.zoomIdx
        win._mx, win._my = win.width / 2, win.height / 2
        win.onMouseWheel(win, -1)
        check(win.zoomIdx == z0 + 1, "the wheel zooms in")
        # What the author hit in play: a "B" on a PC, text like "2$s%", no way to close.
        check(not win.closeButton.isJoypad, "no controller prompt on the close button with a mouse")
        win.onGainJoypadFocus(win, L.table())
        check(win.closeButton.isJoypad, "a controller gets its B prompt")
        win.onLoseJoypadFocus(win, L.table())
        check(not win.closeButton.isJoypad, "and loses it again")
        foot = [d.extra for d in draws if d.kind == "text" and d.extra and "walked" in str(d.extra)]
        check(foot and "$" not in foot[0] and foot[0].count("%") == 1,
              "the footer reads cleanly (%s)" % (foot[0] if foot else None))
        x0, y0, cx0 = win.x, win.y, win.cx
        win.onMouseDown(win, 50, 5)                      # the title bar
        win.onMouseMove(win, 30, 20)
        win.onMouseUp(win, 50, 5)
        check(win.x == x0 + 30 and win.y == y0 + 20 and win.cx == cx0, "the title bar moves the window")
        win._mx, win._my = 200, 200
        win.onMouseDown(win, 200, 200)                   # the map
        win._mx, win._my = 260, 200
        win.onMouseMove(win, 60, 0)
        win.onMouseUp(win, 260, 200)
        check(win.x == x0 + 30 and win.cx != cx0, "dragging the map pans it and leaves the window where it is")
        win.setWidth(win, 480)
        win.setHeight(win, 320)
        sim.draws = L.table()
        win.prerender(win)
        win.render(win)
        out = [d for d in lua_list(sim.draws)
               if not d.clipped and (d.x < -1 or d.y < -1 or d.x + d.w > 481 or d.y + d.h > 321)]
        check(not out, "resized smaller, it still draws inside itself (%s)" % [(d.kind, d.x, d.y) for d in out][:3])
        check(win.isKeyConsumed(win, L.globals().Keyboard.KEY_ESCAPE), "Escape is the map's, not the pause menu's")
        win.onKeyRelease(win, L.globals().Keyboard.KEY_ESCAPE)
        check(SEW.Map.window is None and not sim.ui[win], "Escape closes the map")
        win2 = SEW.Map.open(p)
        check(win2 is not None and win2.width == 480 and win2.x == x0 + 30, "it reopens where it was left, the size it was")
        win2.closeButton.click(win2.closeButton)
        check(SEW.Map.window is None and not sim.ui[win2], "and the X closes it")
    # The key: K, not vanilla's Start/Stop Engine (N) -- even for a player
    # whose ModOptions.ini saved 0.3.1's N -- and never at the wheel.
    KB = L.globals().Keyboard
    check(SEW.Map.keyOption is not None and SEW.Map.keyOption.getValue(SEW.Map.keyOption) == KB.KEY_K,
          "the map's key is K, whatever 0.3.1 saved")
    sim.fire("OnKeyPressed", KB.KEY_N)
    check(SEW.Map.window is None, "N (the engine) does not open the map")
    sim.fire("OnKeyPressed", KB.KEY_K)
    check(SEW.Map.window is not None, "K opens it")
    sim.fire("OnKeyPressed", KB.KEY_K)
    check(SEW.Map.window is None, "and K closes it")
    p.vehicle = True
    sim.fire("OnKeyPressed", KB.KEY_K)
    check(SEW.Map.window is None, "not in a car")
    p.vehicle = None
    tunk = [k for k in sim.unknownText.keys()]
    check(not tunk, "every text the map uses exists (%s)" % tunk[:3])


    # The tunnel round them.
    nb = len(list(SEW.Build.state().built.keys()))
    sim.tickN(900)
    nb2 = len(list(SEW.Build.state().built.keys()))
    left = len(SEW.Build.pending(p.x, p.y, 5))
    check(nb2 >= nb > 0 and left == 0,
          "the tunnel round the player is built a slice at a time until none is left (%d -> %d, %d left)" % (nb, nb2, left))
    first_count = count_ours(L)
    SEW.Build.around(mx, my, 2)
    check(count_ours(L) == first_count, "a second pass places nothing twice (%d)" % first_count)
    L.execute("SEW.Build.state().built = {}")
    SEW.Build.around(mx, my, 2)
    check(count_ours(L) == first_count, "a revision pass puts back nothing that is already there")

    # A revised layout that opens an edge (0.3 joined streets that stopped
    # short): the revision pass takes our wall away, and leaves a player's.
    mig = L.execute("""
        local T = SEW.Data.muldraugh
        for key, body in pairs(T.chunks) do
            if SEW.Build.state().first[key] then
                local cx, cy = key:match("(-?%d+),(-?%d+)")
                for i = 1, #body, 7 do
                    local rec = body:sub(i, i + 6)
                    local n, w = rec:sub(4, 4), rec:sub(5, 5)
                    if rec:sub(3, 3) == "t" and (n == "c" or n == "b") and w == "." and rec:sub(6, 6) == "." then
                        local x, y = cx * 8 + tonumber(rec:sub(1, 1)), cy * 8 + tonumber(rec:sub(2, 2))
                        local sq = SIM.squares[x .. "," .. y .. ",-1"]
                        local wall
                        for _, o in ipairs(sq.objects._t) do
                            local nm = o.sprite:getName()
                            if o.md.sew and nm:find("location_sewer_01_") then wall = nm end
                        end
                        if wall then
                            -- A player's own copy of the same wall on the next square along.
                            local nsq = SIM.squares[(x + 1) .. "," .. y .. ",-1"]
                            local theirs = IsoObject.new(nsq, wall, "")
                            nsq.objects:add(theirs)
                            T.chunks[key] = body:sub(1, i + 2) .. "." .. body:sub(i + 4)
                            SEW.Build.state().built[key] = "old"
                            SEW.Build.around(x, y, 0)
                            local still = false
                            for _, o in ipairs(sq.objects._t) do
                                if o.md.sew and o.sprite:getName() == wall then still = true end
                            end
                            local kept = false
                            for _, o in ipairs(nsq.objects._t) do if o == theirs then kept = true end end
                            T.chunks[key] = body
                            return still, kept
                        end
                    end
                end
            end
        end
    """)
    check(mig is not None and mig[0] is False, "a revised layout that opens an edge takes our wall away")
    check(mig is not None and mig[1] is True, "and leaves a wall a player built")

    # A chunk built before 0.3.2 wears vanilla's floating sludge: a revision
    # pass swaps ours in, and leaves a player's copy of the old tile alone.
    sl = L.execute("""
        local C = SEW.Config
        -- The same chunk every run: pairs() walks a table of string keys in an
        -- order that changes from run to run, and one run in sixty this built
        -- the chunk a later check needs untouched (the cave's, or the first
        -- shaft's) and failed it. Sorted, and never one of those.
        local keys = {}
        for key in pairs(SEW.Data.muldraugh.chunks) do keys[#keys + 1] = key end
        table.sort(keys)
        for _, key in ipairs(keys) do
            local body = SEW.Data.muldraugh.chunks[key]
            do
                local cx, cy = key:match("(-?%d+),(-?%d+)")
                cx, cy = tonumber(cx), tonumber(cy)
                for i = 1, #body, 7 do
                    local rec = body:sub(i, i + 6)
                    if rec:sub(3, 3) == "w" then
                        local x, y = cx * 8 + tonumber(rec:sub(1, 1)), cy * 8 + tonumber(rec:sub(2, 2))
                        SIM.load(cx, cy)
                        SEW.Build.around(x, y, 0)
                        local sq = SIM.squares[x .. "," .. y .. ",-1"]
                        for _, o in ipairs(sq.objects._t) do
                            if o.md.sew and o.sprite:getName() == C.Sprites.sludge then sq.objects:remove(o) break end
                        end
                        local old = IsoObject.new(sq, C.Sprites.sludgeOld, "")
                        old.md.sew = 1
                        sq.objects:add(old)
                        local theirs = IsoObject.new(sq, C.Sprites.sludgeOld, "")
                        sq.objects:add(theirs)
                        SEW.Build.state().built[key] = "old"
                        SEW.Build.around(x, y, 0)
                        local oldLeft, new, kept = false, 0, false
                        for _, o in ipairs(sq.objects._t) do
                            local nm = o.sprite:getName()
                            if o == theirs then kept = true
                            elseif o.md.sew and nm == C.Sprites.sludgeOld then oldLeft = true
                            elseif o.md.sew and nm == C.Sprites.sludge then new = new + 1 end
                        end
                        sq.objects:remove(theirs)
                        return oldLeft, new, kept
                    end
                end
            end
        end
    """)
    check(sl is not None and sl[0] is False and sl[1] == 1,
          "a revision pass swaps the old floating sludge for ours (%s)" % (sl,))
    check(sl is not None and sl[2] is True, "and leaves a player's own copy of it")

    walk_ok = L.execute("""
        local T = SEW.Data.muldraugh
        local bad, n = 0, 0
        for key, body in pairs(T.chunks) do
            if SEW.Build.state().first[key] then
                local cx, cy = key:match("(-?%d+),(-?%d+)")
                for i = 1, #body, 7 do
                    local rec = body:sub(i, i + 6)
                    local x, y = cx * 8 + tonumber(rec:sub(1,1)), cy * 8 + tonumber(rec:sub(2,2))
                    local f = rec:sub(3,3)
                    if f ~= "." then
                        n = n + 1
                        local sq = SIM.squares[x .. "," .. y .. ",-1"]
                        if not sq or not sq:getFloor() then bad = bad + 1 end
                    end
                end
            end
        end
        return bad, n
    """)
    check(walk_ok[0] == 0 and walk_ok[1] > 200, "every square with a floor code has a floor (%d of %d missing)" % walk_ok)

    zs = lua_list(sim.zombies)
    check(len(zs) > 0, "the dead are down here (%d)" % len(zs))
    near = [z for z in zs if abs(z.x - mx) + abs(z.y - my) < 10]
    check(not near, "none put down on top of the player")
    check(all(z.z == -1 for z in zs), "all of them below")

    # Shelters in reach: stocked and explored.
    stocked = L.execute("""
        local full, empty = 0, 0
        for _, sq in pairs(SIM.squares) do
            for _, o in ipairs(sq.objects._t) do
                if o.md.sew and o.container then
                    if o.container:getItems():size() > 0 and o.container:isExplored() then full = full + 1 else empty = empty + 1 end
                end
            end
        end
        return full, empty
    """)
    print("        shelter containers in reach: %d stocked, %d empty" % stocked)
    if stocked[0] + stocked[1] == 0:
        # Walk the player to the nearest shelter so one is checked.
        h = L.execute("""
            local best, bd
            for _, h in ipairs(SEW.Index.shelters) do
                if h.town == "muldraugh" then
                    local d = math.abs(h.x - %d) + math.abs(h.y - %d)
                    if not bd or d < bd then best, bd = h, d end
                end
            end
            return best.x, best.y
        """ % (mx, my))
        street(L, h[0], h[1], 1, manhole=False)
        SEW.Build.around(h[0], h[1], 2)
        stocked = L.execute("""
            local full, empty = 0, 0
            for _, sq in pairs(SIM.squares) do
                for _, o in ipairs(sq.objects._t) do
                    if o.md.sew and o.container then
                        if o.container:getItems():size() > 0 and o.container:isExplored() then full = full + 1 else empty = empty + 1 end
                    end
                end
            end
            return full, empty
        """)
    check(stocked[0] > 0, "shelter containers are stocked and explored (%d, %d empty)" % stocked)
    # A player's report (0.3.2): every crate full and every one of the dead
    # carrying a pack. At the default, a crate holds a few things plus any
    # journal and plan, and the equipped are a few of the dead.
    most = L.execute("""
        local most = 0
        for _, sq in pairs(SIM.squares) do
            for _, o in ipairs(sq.objects._t) do
                if o.md.sew and o.container then most = math.max(most, o.container:getItems():size()) end
            end
        end
        return most
    """)
    check(0 < most <= 6, "a shelter's container holds a few things, not a crate full (%d at most)" % most)
    mix = L.execute("""
        local B, C = SEW.Build, SEW.Config
        local eq = {}
        for _, o in ipairs(C.OutfitsEquipped) do eq[o] = true end
        local out = {}
        for opt = 1, 3 do
            SandboxVars.Sewars.Outfits = opt
            local n, kept = 0, 0
            for i = 1, 2000 do
                if eq[B.outfit(10000 + i * 7, 9000 + i * 3, i % 5 + 1)] then n = n + 1 end
                if B.dress("Survivalist", 10000 + i * 5, 9000 + i) == "Survivalist" then kept = kept + 1 end
            end
            out[#out + 1] = n
            out[#out + 1] = kept
        end
        SandboxVars.Sewars.Outfits = nil
        local ordinary = B.dress("Hobbo", 1, 2) == "Hobbo" and B.option("Outfits", 2, 3) == 2
        return out[1], out[2], out[3], out[4], out[5], out[6], ordinary
    """)
    check(mix[0] < 250 and mix[2] < 450 and mix[4] > 550, "equipped dead by the sandbox: %d, %d, %d in 2000" % (mix[0], mix[2], mix[4]))
    check(mix[1] < 700 and 700 < mix[3] < 1300 and mix[5] == 2000,
          "a shelter's own dead keep their pack by the sandbox: %d, %d, %d in 2000" % (mix[1], mix[3], mix[5]))
    check(mix[6], "an ordinary one is left as it is; no option in the save means Mixed")
    loot = L.execute("""
        local U, C = SEW.Util, SEW.Config
        local function crate()
            local items = {}
            local c = { getCapacity = function() return 50 end, getContentsWeight = function() return 0 end,
                        getItems = function() return { size = function() return #items end } end,
                        AddItem = function(_, it) items[#items + 1] = it end }
            return { getContainer = function() return c end }, items
        end
        local obj, items = crate()
        local n = U.fill(obj, C.Loot.arms, 4, 12345)
        local none = U.fill(crate(), C.Loot.arms, 0, 1)
        local seen = {}
        local roll = U.rng(777)
        for _ = 1, 400 do seen[roll(10)] = true end
        local all = 0
        for i = 1, 10 do if seen[i] then all = all + 1 end end
        return n, #items, none, all
    """)
    check(loot[0] == 4 and loot[1] == 4, "a crate gets its count, not the whole list (%d added, %d in it)" % (loot[0], loot[1]))
    check(loot[2] == 0, "None puts nothing in")
    check(loot[3] == 10, "the generator reaches every pick (%d of 10)" % loot[3])
    hi = L.execute("""
        for i, h in ipairs(SEW.Index.shelters) do
            if h.town == "muldraugh" and SIM.squares[(h.x + 1) .. "," .. (h.y + 1) .. ",-1"] then return i, h.x, h.y end
        end
    """)
    if hi and hi[0]:
        i, hx, hy = hi
        p.x, p.y, p.z = hx + 1.5, hy + 1.5, -1
        sim.tickN(40)
        check(SEW.Map.state.s[i] is not None, "walking into a shelter marks it on the map (%d)" % i)
    else:
        check(False, "a built shelter to walk into")

    # The story: the shelter's container holds a journal; read it from the inventory.
    jitem = L.execute("""
        for _, sq in pairs(SIM.squares) do for _, o in ipairs(sq.objects._t) do
            if o.container then for _, it in ipairs(o.container.items._t) do
                if it:getFullType() == "Sewars.SewerJournal" then return it end
            end end
        end end
    """)
    check(jitem is not None, "a shelter's container holds a journal")
    if jitem is not None:
        idx = jitem.getModData(jitem).SewarsJournal
        L.globals().SIM_it = jitem
        L.execute("SIM.players[1].inv.items:add(SIM_it)")
        m = sim.newMenu(0, 0)
        sim.fire("OnFillInventoryObjectContextMenu", 0, m, L.table(jitem))
        check(TEXT["ContextMenu_SEW_ReadJournal"] in [n for n, _ in options(m)], "a journal offers Read")
        m2 = sim.newMenu(0, 0)
        L.globals().SIM_it = jitem
        sim.fire("OnFillInventoryObjectContextMenu", 0, m2, L.execute("return { { items = { SIM_it, SIM_it } } }"))
        check(TEXT["ContextMenu_SEW_ReadJournal"] in [n for n, _ in options(m2)], "and so does a stack of them")
        choose(m, TEXT["ContextMenu_SEW_ReadJournal"])
        win = SEW.StoryUI.window
        check(win is not None and sim.ui[win], "the journal's page opens")
        if win is not None:
            check(win.title and not str(win.title).startswith("IGUI_"), "with its title (%s)" % win.title)
            body = " ".join(lua_list(win.lines))
            check("%" not in body and len(body) > 60, "and its text, filled in (%s...)" % body[:60])
            check(not win.closeButton.isJoypad, "the journal shows no controller prompt with a mouse")
            win.closeButton.click(win.closeButton)
            check(SEW.StoryUI.window is None and not sim.ui[win], "its X closes it")
        check(SEW.Map.state.m["j%d" % idx] is not None, "reading it puts its mark on the map")
        before = len(lua_list(sim.notes))
        choose(m, TEXT["ContextMenu_SEW_ReadJournal"])
        jw = SEW.StoryUI.window
        jw.onKeyRelease(jw, L.globals().Keyboard.KEY_ESCAPE)
        check(SEW.StoryUI.window is None, "and so does Escape")
        check(not any("Marked" in n for n in lua_list(sim.notes)[before:]), "reading it again marks nothing new")

    # A plan: reveals its sheet; twice reveals nothing; one not carried reveals nothing.
    pidx = L.execute('for i, pl in ipairs(SEW.Index.plans) do if pl.town == "muldraugh" then return i end end')
    plan = L.execute('local it = instanceItem("Sewars.SewerPlan"); it:getModData().SewarsPlan = %d; return it' % pidx)
    check(plan is not None, "a plan can be made")
    stray = L.execute('local it = instanceItem("Sewars.SewerPlan"); it:getModData().SewarsPlan = %d; return it' % pidx)
    count = lambda: len(list(SEW.Map.state.c.keys()))
    c0 = count()
    SEW.Story.readPlan(p, stray.getID(stray))
    check(count() == c0, "a plan the player is not carrying reveals nothing")
    L.globals().SIM_it = plan
    L.execute("SIM.players[1].inv.items:add(SIM_it)")
    m = sim.newMenu(0, 0)
    sim.fire("OnFillInventoryObjectContextMenu", 0, m, L.table(plan))
    choose(m, TEXT["ContextMenu_SEW_ReadPlan"])
    c1 = count()
    # Exactly the town's chunks on that sheet, counted from the data -- not a guess.
    want = L.execute('''
        local pl = SEW.Index.plans[%d]
        local t = SEW.Index.towns[pl.town]
        local x0, y0 = t.x0 + pl.i * 256, t.y0 + pl.j * 256
        local n = 0
        for k in pairs(SEW.Data[pl.town].chunks) do
            local cx, cy = k:match("(-?%%d+),(-?%%d+)")
            cx, cy = tonumber(cx), tonumber(cy)
            if cx >= math.floor(x0 / 8) and cx <= math.floor((x0 + 255) / 8)
               and cy >= math.floor(y0 / 8) and cy <= math.floor((y0 + 255) / 8) then n = n + 1 end
        end
        return n
    ''' % pidx)
    check(want > 0 and c1 - c0 <= want and c1 - c0 >= want - 40,
          "reading the plan reveals its sheet on the map (%d new of the sheet's %d chunks)" % (c1 - c0, want))
    check(any("fills in" in n for n in lua_list(sim.notes)), "and says so")
    # The fog was drawn (and cached) before the plan was read: it has to lift.
    fogged = L.execute('''
        local pl = SEW.Index.plans[%d]
        local covered, total = 0, 0
        for k in pairs(SEW.Map.state.c) do
            local cx, cy = k:match("(-?%%d+),(-?%%d+)")
            cx, cy = tonumber(cx), tonumber(cy)
            total = total + 1
            for _, r in ipairs(SEW.Map.fog(pl.town)) do
                if r[2] == cy and cx >= r[1] and cx <= r[3] then covered = covered + 1 end
            end
        end
        return covered, total
    ''' % pidx)
    check(fogged[0] == 0 and fogged[1] > 100,
          "the fog lifts from everything found since it was first drawn (%d of %d still fogged)" % tuple(fogged))
    choose(m, TEXT["ContextMenu_SEW_ReadPlan"])
    check(count() == c1 and "don't already know" in lua_list(sim.notes)[-1], "a second reading reveals nothing new")

    # Up another ladder.
    others = [s for s in shafts if (s[0], s[1]) != (mx, my) and abs(s[0] - mx) + abs(s[1] - my) < 60]
    check(bool(others), "another shaft within walking distance")
    if others:
        ox, oy, olx, oly, ost = others[0]
        street(L, ox, oy, 3)
        SEW.Build.around(ox, oy, 1)
        p.x, p.y, p.z = ox + 0.5, oy + 0.5, -1
        m = menu(L, 0, olx, oly)
        names = [n for n, _ in options(m)]
        check(TEXT["ContextMenu_SEW_Exit"] in names, "the ladder offers Climb out (%s)" % names)
        choose(m, TEXT["ContextMenu_SEW_Exit"])
        sim.runActions()
        sim.tickN(12)
        check(abs(p.z) < 1e-6 and int(p.x) == ox and int(p.y) == oy, "up on the cover at %d,%d (%.1f,%.1f,%.1f)" % (ox, oy, p.x, p.y, p.z))
        check(p.noVault is False, "the vault switch is off again above")
        check(len(list(sim.lamps.keys())) == 0, "the lamps are taken down on the way up")

    # A cover left shut.
    # A manhole not in the index: any street square with a cover the index does not know.
    sx, sy = mx + 200, my + 200
    street(L, sx, sy, 2)
    p.x, p.y, p.z = sx + 1.5, sy + 0.5, 0
    if not SEW.Sewer.shaftAt(sx, sy):
        m = menu(L, 0, sx, sy)
        opts = options(m)
        check(len(opts) == 1 and opts[0][1].notAvailable is True, "a cover that leads nowhere is greyed out")

    # Refused from too far away.
    p.x, p.y, p.z = mx + 9.5, my + 0.5, 0
    before = len(lua_list(sim.notes))
    SEW.Server.grant(p, mx, my, "down")
    sim.tickN(5)
    check(abs(p.z) < 1e-6, "a climb from nine squares away is refused")
    check(any("Too far" in n for n in lua_list(sim.notes)[before:]), "and says so")

    # Up a ladder that is not below you: the server refuses by itself, whatever
    # the action's own isValid says (the two cover each other, so ask each).
    p.x, p.y, p.z = mx + 0.5, my + 0.5, 0
    before = len(lua_list(sim.notes))
    SEW.Server.grant(p, mx, my, "up")
    sim.tickN(5)
    check(abs(p.z) < 1e-6 and any("Not from here" in n for n in lua_list(sim.notes)[before:]),
          "the server refuses a climb out from the street")

    # Rescue.
    p.x, p.y, p.z = mx + 30.5, my + 30.5, -1
    L.execute("for k, sq in pairs(SIM.squares) do if sq.x == %d and sq.y == %d and sq.z == -1 then SIM.squares[k] = nil end end" % (mx + 30, my + 30))
    sim.tickN(40)
    check(abs(p.z + 1) < 1e-6 and L.execute("return SIM.squares[math.floor(%f)..','..math.floor(%f)..',-1'] ~= nil" % (p.x, p.y)),
          "a player below with no floor is put where there is one (%.1f,%.1f)" % (p.x, p.y))

    # Below ground is not all ours (found by players: a bunker's stairs at
    # -2 sent one to the nearest sewer, the military base at -14 sent another
    # up to the street). Each place is asked twice -- the client's own check,
    # then the server's with the client's taken out of the way -- because the
    # two cover each other.
    L.execute("""
        local function sq(x, y, z, sprite)
            local s = getCell():getOrCreateGridSquare(x, y, z)
            s.objects._t = {}
            if sprite and sprite ~= "" then s.objects:add(IsoObject.new(s, sprite, "")) end
            return s
        end
        function SIM.rescueAsked(p, x, y, z)
            p.x, p.y, p.z = x, y, z
            local log0 = #SIM.log
            SIM.tickN(400)
            local asked = false
            for i = log0 + 1, #SIM.log do if SIM.log[i]:find("asking for a rescue", 1, true) then asked = true end end
            local kept = p.x == x and p.y == y and p.z == z
            -- And the server by itself, whatever the client thinks.
            p.x, p.y, p.z = x, y, z
            SEW.Net.serverHandlers.rescue(p, {})
            SIM.tickN(40)
            local server = p.x == x and p.y == y and p.z == z
            return asked, kept, server
        end
        SIM.mkSquare = sq
    """)
    bx_, by_ = mx + 3, my + 3
    places = [
        # A bunker's floor two levels down, and the base fourteen down.
        ("on a floor at -2", bx_ + 0.5, by_ + 0.5, -2, (bx_, by_, -2, "floors_interior_tilesandwood_01_0")),
        ("on a floor at -14", bx_ + 0.5, by_ + 0.5, -14, (bx_, by_, -14, "floors_interior_tilesandwood_01_0")),
        # Stairs with no floor under them: down to -2 (the character is
        # between the levels, its square the one below), and a basement's at -1.
        ("on stairs down to -2", bx_ + 0.5, by_ + 1.5, -1.4, (bx_, by_ + 1, -2, "fixtures_stairs_01_0")),
        ("on a basement's stairs at -1", bx_ + 60.5, by_ + 60.5, -0.8, (bx_ + 60, by_ + 60, -1, "fixtures_stairs_01_0")),
        # Between the levels over a bare square at -2: the level alone says no.
        ("over a bare square at -2", bx_ + 0.5, by_ + 2.5, -1.4, (bx_, by_ + 2, -2, "")),
        # In the air at -2 and -14: no square at all.
        ("with no square at -2", bx_ + 62.5, by_ + 60.5, -2, None),
        ("with no square at -14", bx_ + 62.5, by_ + 60.5, -14, None),
    ]
    for what, x, y, z, made in places:
        if made:
            sim.load(made[0] // 8, made[1] // 8)
            L.execute("SIM.mkSquare(%d, %d, %d, '%s')" % made)
        asked, kept, server = L.execute("return SIM.rescueAsked(SIM.players[1], %f, %f, %f)" % (x, y, z))
        check(not asked and kept, "a player %s is somebody else's: the client asks for no rescue" % what)
        check(server, "and asked anyway, the server moves nobody %s" % what)
    check(not SEW.Sewer.below(p), "fourteen levels down is not the sewer")
    p.z = -2
    check(not SEW.Sewer.below(p) and not options(menu(L, 0, int(p.x), int(p.y))),
          "nor is two: no sewer map or dig on the menu there")
    # A bare square at -1, far from any town: not the sewer's either.
    far = L.execute("""
        local p = SIM.players[1]
        local x, y = 300.5, 300.5
        SIM.load(math.floor(x / 8), math.floor(y / 8))
        SIM.mkSquare(math.floor(x), math.floor(y), -1, nil)
        -- A street over it, so a wrong "sent up" has somewhere to arrive.
        SIM.mkSquare(math.floor(x), math.floor(y), 0, "floors_exterior_street_01_0")
        p.x, p.y, p.z = x, y, -1
        SEW.Net.serverHandlers.rescue(p, {})
        SIM.tickN(40)
        return p.x == x and p.y == y and p.z == -1
    """)
    check(far, "and at -1 with no sewer in the chunks round it, the server moves nobody")
    p.x, p.y, p.z = mx + 1.5, my + 0.5, 0
    sim.tickN(12)

    # A menu that kept no click (another mod's): the mouse says where.
    m = sim.newMenu(mx + 40, my + 40)
    m.requestX, m.requestY = None, None
    sim.mouse.x, sim.mouse.y = mx, my
    sim.fire("OnFillWorldObjectContextMenu", 0, m, L.table(), False)
    check(len(options(m)) == 1, "a menu with no click of its own is read from the mouse (%s)" % [n for n, _ in options(m)])
    sim.mouse.x, sim.mouse.y = 0, 0

    # Somebody else's underground.
    fx, fy = shafts[0][0], shafts[0][1]
    street(L, fx, fy, 2)
    L.execute("""
        local sq = getCell():getOrCreateGridSquare(%d, %d, -1)
        sq.objects:add(IsoObject.new(sq, "location_sewer_01_34", ""))
    """ % (fx + 1, fy))
    SEW.Build.around(fx, fy, 1)
    objs = objects_at(L, fx + 1, fy, -1)
    check(objs == ["location_sewer_01_34"] or not any(o.startswith("floors_") for o in objs),
          "a square already holding something is left alone (%s)" % objs)

    # A cave (ROADMAP 0.4), the Muldraugh one the dev build starts at, in
    # chunks built before caves existed: a save from 0.3. Our rock is already
    # on the square the breach opens onto, as it would be under an outside wall.
    cave = L.execute("local v = SEW.Client.devCave(); return v.bx, v.by, v.x, v.y, v.sx, v.sy")
    check(cave is not None, "the dev build has a Muldraugh cave to start at")
    bx, by, hx, hy, sx, sy = cave
    res = L.execute("""
        local bx, by, hx, hy = ...
        local C, B = SEW.Config, SEW.Build
        local s = B.state()
        local keys = {}
        for cx = math.floor(math.min(bx, hx) / 8) - 1, math.floor(math.max(bx, hx) / 8) + 1 do
            for cy = math.floor(math.min(by, hy) / 8) - 1, math.floor(math.max(by, hy) / 8) + 1 do
                SIM.load(cx, cy)
                local key = cx .. "," .. cy
                if B.townOf(key) then
                    keys[#keys + 1] = key
                    s.first[key], s.built[key], s.caves[key] = "old", "old", nil
                end
            end
        end
        -- The square through the breach: find it from the breach's record.
        local T = SEW.Data.muldraugh
        local function rec(x, y)
            local body = T.chunks[math.floor(x / 8) .. "," .. math.floor(y / 8)] or ""
            for i = 1, #body, 7 do
                local r = body:sub(i, i + 6)
                if tonumber(r:sub(1, 1)) == x % 8 and tonumber(r:sub(2, 2)) == y % 8 then return r end
            end
        end
        local entry
        for _, d in ipairs({ { 0, -1 }, { -1, 0 }, { 1, 0 }, { 0, 1 } }) do
            local r = rec(bx + d[1], by + d[2])
            if r and r:sub(3, 3) == "m" then entry = { bx + d[1], by + d[2] } end
        end
        local esq = getCell():getOrCreateGridSquare(entry[1], entry[2], -1)
        local rock = IsoObject.new(esq, C.Sprites.floorRock, "")
        rock.md.sew = 1
        esq.objects:add(rock)
        for _, key in ipairs(keys) do B.chunk(key) end

        local function sprites(x, y)
            local out = {}
            local sq = SIM.squares[x .. "," .. y .. ",-1"]
            for _, o in ipairs(sq and sq.objects._t or {}) do
                out[o.sprite:getName()] = (out[o.sprite:getName()] or 0) + 1
                for _, a in ipairs(o.attached and o.attached._t or {}) do
                    local n = a:getParentSprite():getName()
                    out[n] = (out[n] or 0) + 1
                end
            end
            return out
        end
        local breach = false
        for _, set in pairs(C.Sprites.breach) do
            for _, v in pairs(set) do
                if sprites(bx, by)[v] or sprites(entry[1], entry[2])[v] then breach = true end
            end
        end
        local e = sprites(entry[1], entry[2])
        local rockGone = e[C.Sprites.floorRock] == nil and (e[C.Sprites.floorCave[1]] or e[C.Sprites.floorCave[2]]) == 1
        -- The hideout: crates, stocked.
        local crates, full = 0, 0
        for x = hx - 4, hx + 4 do for y = hy - 4, hy + 4 do
            local sq = SIM.squares[x .. "," .. y .. ",-1"]
            for _, o in ipairs(sq and sq.objects._t or {}) do
                if o.sprite:getName() == "carpentry_01_16" then
                    crates = crates + 1
                    local c = SEW.Util.containerOf(o)
                    if c and c:getItems():size() > 0 then full = full + 1 end
                end
            end
        end end
        local done = true
        for _, key in ipairs(keys) do
            if B.hasCave(T.chunks[key]) and s.caves[key] == nil then done = false end
        end
        -- And again, as the next revision would: nothing twice.
        for _, key in ipairs(keys) do s.built[key] = "older" end
        for _, key in ipairs(keys) do B.chunk(key) end
        local crates2 = 0
        for x = hx - 4, hx + 4 do for y = hy - 4, hy + 4 do
            local sq = SIM.squares[x .. "," .. y .. ",-1"]
            for _, o in ipairs(sq and sq.objects._t or {}) do
                if o.sprite:getName() == "carpentry_01_16" then crates2 = crates2 + 1 end
            end
        end end
        return breach, rockGone, crates, full, done, crates2
    """, bx, by, hx, hy)
    breach, rock_gone, crates, full, done, crates2 = res
    check(breach, "the cave's breach is knocked through the tunnel wall (%d,%d)" % (bx, by))
    check(rock_gone, "our rock where the cave now runs gives way to the cave's floor, one floor, not two")
    check(crates >= 1 and full == crates, "the hideout's crates are there and stocked (%d, %d full)" % (crates, full))
    check(done, "caves reach chunks built before there were any, and are recorded done")
    check(crates2 == crates, "a later pass puts in no second crate (%d)" % crates2)

    # Pictures on walls (found in play, 0.3.2: earth floating by a breach). The
    # cutaway cuts a wall and what is attached to it, so every picture of ours
    # with a wall of ours on its edge hangs on that wall, not beside it.
    hung = L.execute("""
        local B = SEW.Build
        local loose, attached, kinds = 0, 0, {}
        for _, sq in pairs(SIM.squares) do
            for _, o in ipairs(sq.objects._t) do
                if o.md.sew and B.overlayEdge(o.sprite:getName()) then loose = loose + 1 end
                for _, a in ipairs(o.attached and o.attached._t or {}) do
                    attached = attached + 1
                    kinds[a:getParentSprite():getName()] = true
                end
            end
        end
        local C = SEW.Config
        local earth = kinds[C.Sprites.earthFace.N] or kinds[C.Sprites.earthFace.W]
        local ladder = kinds[C.Sprites.ladder.N] or kinds[C.Sprites.ladder.W]
        local breach = false
        for _, set in pairs(C.Sprites.breach) do if kinds[set.N] or kinds[set.W] then breach = true end end
        return loose, attached, earth == true, ladder == true, breach
    """)
    check(hung[1] > 0 and hung[2] and hung[3] and hung[4],
          "earth, breaches and ladders hang on their walls (%d attached; earth %s, ladder %s, breach %s)"
          % (hung[1], hung[2], hung[3], hung[4]))
    check(hung[0] == 0, "and none is an object of its own beside a wall it could hang on (%d)" % hung[0])
    # A save from before: the picture an object of its own. The next revision
    # pass takes it off the square and hangs it, once.
    moved = L.execute("""
        local B, C, U = SEW.Build, SEW.Config, SEW.Util
        for k, sq in pairs(SIM.squares) do
            for _, o in ipairs(sq.objects._t) do
                local a = o.attached and o.attached._t[1]
                local name = a and a:getParentSprite():getName()
                if o.md.sew and (name == C.Sprites.earthFace.N or name == C.Sprites.earthFace.W) then
                    table.remove(o.attached._t, 1)
                    local old = IsoObject.new(sq, name, "")
                    old.md.sew = 1
                    sq.objects:add(old)
                    local before = B.hasPicture(sq, name) and U.findSprite(sq, name) ~= nil
                    -- A revision pass over its chunk, twice.
                    local ck = math.floor(sq.x / 8) .. "," .. math.floor(sq.y / 8)
                    for _ = 1, 2 do
                        B.state().built[ck] = "old"
                        B.chunk(ck)
                    end
                    local n = 0
                    for _, a2 in ipairs(o.attached._t) do if a2:getParentSprite():getName() == name then n = n + 1 end end
                    return before, U.findSprite(sq, name) == nil, n
                end
            end
        end
    """)
    check(moved is not None and moved[0] and moved[1] and moved[2] == 1,
          "an old save's loose earth is taken off the square and hung on its wall, once (%s)" % (moved,))

    # Houses with a way down (ROADMAP 0.4). Two Muldraugh hatches: one clear,
    # one with a random basement stamped under its house.
    hl = L.execute("""
        local out = {}
        for _, s in pairs(SEW.Index.shafts) do
            if s.hatch and s.town == "muldraugh" then out[#out + 1] = s end
        end
        table.sort(out, function(a, b) return a.x < b.x end)
        return out[1], out[#out]
    """)
    hs, hb = hl
    hx, hy = int(hs.x), int(hs.y)
    q = sim.newPlayer("hatch", hx + 1.5, hy + 0.5, 0)
    q.hours = 50
    sim.players = L.table(q)
    street(L, hx, hy, 3, manhole=False)
    check(TEXT["ContextMenu_SEW_HatchDown"] not in [n for n, _ in options(menu(L, 0, hx, hy))],
          "a house not yet looked at has no hatch in its floor")
    sim.tickN(20)
    check(L.execute("return SEW.Build.state().hatches['%d,%d']" % (hx, hy)) == "open"
          and "sewars_01_34" in objects_at(L, hx, hy, 0),
          "a player on the street near it: the house is looked at, nothing is under it, the trapdoor goes in")
    m = menu(L, 0, hx, hy)
    check(TEXT["ContextMenu_SEW_HatchDown"] in [n for n, _ in options(m)], "the hatch offers Climb down through the hatch")
    choose(m, TEXT["ContextMenu_SEW_HatchDown"])
    sim.runActions()
    sim.tickN(3)
    check(abs(q.z + 1) < 1e-6 and int(q.x) == hx and int(q.y) == hy,
          "down through the hatch to the foot of its ladder (%.1f,%.1f,%.1f)" % (q.x, q.y, q.z))
    lobjs = objects_at(L, int(hs.lx), int(hs.ly), -1)
    check(any(o in ("sewars_01_0", "sewars_01_1") for o in lobjs), "a ladder hangs under the hatch (%s)" % lobjs)
    m = menu(L, 0, hx, hy)
    check(TEXT["ContextMenu_SEW_HatchUp"] in [n for n, _ in options(m)], "below, the ladder offers Climb up through the hatch")
    choose(m, TEXT["ContextMenu_SEW_HatchUp"])
    sim.runActions()
    sim.tickN(3)
    check(q.z == 0 and int(q.x) == hx and int(q.y) == hy, "and back up into the house (%.1f,%.1f,%.1f)" % (q.x, q.y, q.z))

    bx2, by2 = int(hb.x), int(hb.y)
    q.x, q.y, q.z = bx2 + 1.5, by2 + 0.5, 0
    street(L, bx2, by2, 3, manhole=False)
    L.execute("""
        local s = ...
        local u = s.under
        local sq = getCell():getOrCreateGridSquare(u[#u - 1], u[#u], -1)
        sq.objects:add(IsoObject.new(sq, "floors_interior_tilesandwood_01_24", ""))
    """.replace("local s = ...", "local s = SEW.Index.shafts['%d,%d']" % (bx2, by2)))
    sim.tickN(20)
    check(L.execute("return SEW.Build.state().hatches['%d,%d']" % (bx2, by2)) == "blocked"
          and "sewars_01_34" not in objects_at(L, bx2, by2, 0),
          "a house with a basement under it is left shut: no trapdoor")
    check(not options(menu(L, 0, bx2, by2)), "and its floor offers nothing")
    check(L.execute("return SEW.Server.grant(getPlayer(), %d, %d, 'down')" % (bx2, by2)) is False,
          "and the server refuses a climb down it whatever the client asks")
    check(L.execute("local s = SEW.Sewer.nearestShaft(%d, %d); return s ~= nil and s.hatch == nil" % (bx2, by2)),
          "a rescue is never sent to a hatch's ladder, even standing on it")

    # A town the map gives few covers (ROADMAP 0.4): covers of ours, put into
    # the road when a player on the street first comes near.
    made = L.execute("""
        local out = {}
        for _, s in pairs(SEW.Index.shafts) do if s.made and s.town:find("^louisville") then out[#out + 1] = s end end
        table.sort(out, function(a, b) return a.x < b.x or (a.x == b.x and a.y < b.y) end)
        return out[1], #out
    """)
    ms, n_made = made
    check(ms is not None and n_made >= 50, "Louisville has covers of ours (%s)" % n_made)
    cx_, cy_ = int(ms.x), int(ms.y)
    q.x, q.y, q.z = cx_ + 1.5, cy_ + 0.5, 0
    sim.players = L.table(q)
    street(L, cx_, cy_, 3, manhole=False)
    L.execute("local sq = getCell():getGridSquare(%d, %d, 0); for i = #sq.objects._t, 1, -1 do sq.objects._t[i] = nil end"
              % (cx_, cy_))
    check(L.execute("return SEW.Server.grant(getPlayer(), %d, %d, 'down')" % (cx_, cy_)) is False,
          "a cover of ours not yet in the road leads nowhere, whatever the client asks")
    street(L, cx_, cy_, 3, manhole=False)
    check(not options(menu(L, 0, cx_, cy_)), "and there is nothing in the road to offer")
    sim.tickN(20)
    check("sewars_01_35" in objects_at(L, cx_, cy_, 0), "a player comes near: the cover goes into the road (%s)"
          % objects_at(L, cx_, cy_, 0))
    m = menu(L, 0, cx_, cy_)
    check(TEXT["ContextMenu_SEW_Enter"] in [n for n, _ in options(m)], "and offers Climb down")
    choose(m, TEXT["ContextMenu_SEW_Enter"])
    sim.runActions()
    sim.tickN(3)
    check(abs(q.z + 1) < 1e-6 and int(q.x) == cx_ and int(q.y) == cy_,
          "down a cover of ours to the foot of its ladder (%.1f,%.1f,%.1f)" % (q.x, q.y, q.z))
    q.z = 0
    sim.players = L.table(p)

    # The dev build starts a new character on the cover over that cave; one
    # that has lived is left where it stands, and without the flag nobody moves.
    hx, hy = SEW.Index.lair.hx, SEW.Index.lair.hy
    check(SEW.Index.shafts["%d,%d" % (hx, hy)] is not None and SEW.Index.shafts["%d,%d" % (hx, hy)].hatch is not None,
          "the nest names a hatch to start by (%d,%d)" % (hx, hy))
    fo = L.execute("local o = SEW.Client.devOutfall(); return o and o.x, o and o.y")
    check(fo is not None and fo[0] is not None, "Muldraugh has an outfall for the dev build to start by")
    started = SEW.Config.DevStart
    gas_kit = L.execute("""
        local p = SIM.newPlayer("kit", 0, 0, 0)
        SEW.Dev = true
        SEW.Client.devKit(p)
        SEW.Client.devKit(p)
        SEW.Dev = nil
        local n = 0
        for _, it in ipairs(p.inv.items._t) do if it:getType() == "Hat_GasMask" then n = n + 1 end end
        return n
    """)
    check(gas_kit == 1, "the dev kit has a gas mask, once (%d)" % gas_kit)
    for hours, dev, moved_wanted, what, start, tx_, ty_ in (
            (0, False, False, "without the dev flag, a new character stays put", "lair", hx, hy),
            (0, True, True, "the dev build puts a new character by the hatch nearest the rats' nest", "lair", hx, hy),
            (0, True, True, "or, set to caves, on the cover over a cave", "cave", sx, sy),
            (0, True, True, "or, set to outfalls, on the bank by an outfall's grate", "outfall", fo[0], fo[1]),
            (0, True, True, "or, set to the temple, in the field by its trapdoor", "temple",
             SEW.Index.temple.tx, SEW.Index.temple.ty + 1),
            (40, True, False, "and leaves a character that has lived where it stands", "lair", hx, hy)):
        SEW.Config.DevStart = start
        sx, sy = tx_, ty_
        q = sim.newPlayer("dev", mx + 3.5, my + 0.5, 0)
        q.hours = hours
        sim.players = L.table(q)
        SEW.Dev = True if dev else None
        sim.fire("OnCreatePlayer", 0, q)
        sim.tickN(60)
        moved = abs(q.x - (sx + 0.5)) < 1e-6 and abs(q.y - (sy + 0.5)) < 1e-6 and q.z == 0
        check(moved == moved_wanted, "%s (%.1f,%.1f)" % (what, q.x, q.y))
    SEW.Dev = None
    SEW.Config.DevStart = started
    sim.players = L.table(p)

    lair_test(L, p)
    sim.players = L.table(p)
    gas_test(L, p)
    p.x, p.y, p.z = mx + 0.5, my + 0.5, 0
    sim.players = L.table(p)
    gates_test(L, p)
    sim.players = L.table(p)
    outfall_test(L, p)
    sim.players = L.table(p)
    dev_menu_test(L, p)
    sim.players = L.table(p)
    temple_test(L, p)
    sim.players = L.table(p)
    warren_test(L, p)
    sim.players = L.table(p)
    maps_test(L, p)
    sim.players = L.table(p)
    mine_test(L, p)
    sim.players = L.table(p)
    street_test(L, p)
    rooms_test(L, p, False)
    sim.players = L.table(p)

    unknown = [k for k in sim.unknownSprites.keys()]
    check(not unknown, "every sprite placed exists in the game (%s)" % unknown[:5])
    unk = [k for k in sim.unknownText.keys()]
    check(not unk, "every text key exists (%s)" % unk[:5])
    w = warns(L, allowed=("left alone",))
    check(not w, "no WARN logged (%s)" % w[:3])
    return L


# --- a server and a client ---------------------------------------------------------------------

def copy(L_to, v):
    """A value from one Lua runtime, rebuilt in another."""
    if hasattr(v, "keys") and not isinstance(v, (str, bytes)):
        t = L_to.table()
        for k in list(v.keys()):
            t[k] = copy(L_to, v[k])
        return t
    return v


def multiplayer():
    print("a server and a client")
    Ls, Lc = process("server"), process("client")
    gs, gc = Ls.globals(), Lc.globals()
    check(gs.SEW.Client is None, "the client's files do nothing on the server")
    check(gc.SEW.Build is None and gc.SEW.Server is None, "the server's files do nothing on a client")
    check(gc.SEW.Data is None or len(list(gc.SEW.Data.keys())) == 0, "the town data stays on the server")
    check(gs.SEW.Compat.wrapped == 3 and gc.SEW.Compat.wrapped == 3,
          "below ground is indoors on the server and on the client")

    shafts = pick_shafts(Ls)
    # The shaft nearest a shelter, so a door is among what has to reach the client.
    hx, hy = Ls.execute('''
        for _, h in ipairs(SEW.Index.shelters) do if h.town == "muldraugh" then return h.x, h.y end end
    ''')
    mx, my, lx, ly, st = min(shafts, key=lambda s: abs(s[0] - hx) + abs(s[1] - hy))
    for L in (Ls, Lc):
        street(L, mx, my, 6)
    Ls.execute('SEW.Build.around(%d, %d, 4)' % (hx, hy))
    ps = gs.SIM.newPlayer("alice", mx + 3.5, my + 0.5, 0)
    pc = gc.SIM.newPlayer("alice", mx + 3.5, my + 0.5, 0)
    gs.SIM.players = Ls.table(ps)
    gc.SIM.players = Lc.table(pc)
    gs.SIM.fire("OnGameStart")
    gc.SIM.fire("OnGameStart")
    gs.SIM.tickN(400)
    gc.SIM.tickN(400)

    # What an AddItemToMapPacket does on the client: the same object, made there.
    arrive = Lc.eval('''function(x, y, z, name, north, class, special, sew, keyId, lockedByKey, customLock)
        local sq = getCell():getOrCreateGridSquare(x, y, z)
        -- Made by the packet, not by the mod: not the client's edit.
        local n = #SIM.violations
        local o = IsoObject.new(sq, name, "")
        while #SIM.violations > n do table.remove(SIM.violations) end
        o.md.sew, o.north, o.class = sew, north, class
        -- What save() carries (AddItemToMap): a door's key id, its locks, its mod data.
        o.keyId, o.lockedByKey, o.md.CustomLock = keyId, lockedByKey, customLock
        sq.objects:add(o)
        if special then sq.specials:add(o) end
    end''')

    # What an updated-sprite packet does: the object's attached sprites, as the
    # server has them now, on the client's copy (found by square and sprite).
    resprite = Lc.eval('''function(x, y, z, name, names)
        local sq = SIM.squares[x .. "," .. y .. "," .. z]
        for _, o in ipairs(sq and sq.objects._t or {}) do
            if o.sprite:getName() == name then
                o.attached = SIM.List()
                for _, n in ipairs(names) do
                    local spr = getSprite(n)
                    o.attached:add({ getParentSprite = function() return spr end })
                end
                return true
            end
        end
        return false
    end''')

    def land(msg):
        o = msg[2]
        sq = o.square
        if not gc.SIM.loaded["%d,%d" % (sq.x // 8, sq.y // 8)]:
            return
        if msg[1] == "addObject":
            arrive(sq.x, sq.y, sq.z, o.sprite.getName(), o.north, o["class"], msg[3], o.md.sew,
                   o.keyId, o.lockedByKey, o.md.CustomLock)
        else:
            names = [o.attached._t[j].getParentSprite().getName() for j in range(1, len(o.attached._t) + 1)]
            resprite(sq.x, sq.y, sq.z, o.sprite.getName(), Lc.table(*names))

    # What a remove-item packet does: the client's copy of the object goes.
    remove = Lc.eval('''function(x, y, z, name)
        local sq = SIM.squares[x .. "," .. y .. "," .. z]
        for _, o in ipairs(sq and sq.objects._t or {}) do
            if o.sprite:getName() == name then sq.objects:remove(o) return true end
        end
        return false
    end''')

    def unland(msg):
        o = msg[2]
        sq = o.square
        if gc.SIM.loaded["%d,%d" % (sq.x // 8, sq.y // 8)]:
            remove(sq.x, sq.y, sq.z, o.sprite.getName())

    def pump(late_floor=False):
        held = []
        for _ in range(4):
            ps.x, ps.y, ps.z = pc.x, pc.y, pc.z
            out, gc.SIM.outbox = lua_list(gc.SIM.outbox), Lc.table()
            for msg in out:
                if msg[1] == "clientCommand":
                    gs.SIM.fire("OnClientCommand", msg[3], msg[4], ps, copy(Ls, msg[5]))
                elif msg[1] == "netAction":
                    gs.SIM.serverAction(ps, msg[3], copy(Ls, msg[4]))
            out, gs.SIM.outbox = lua_list(gs.SIM.outbox), Ls.table()
            for msg in out:
                if msg[1] == "serverCommand":
                    gc.SIM.fire("OnServerCommand", msg[3], msg[4], copy(Lc, msg[5]))
                elif msg[1] == "removeObject":
                    unland(msg)
                elif msg[1] in ("addObject", "updateSprite") and late_floor:
                    held.append(msg)
                elif msg[1] in ("addObject", "updateSprite"):
                    land(msg)
            gc.SIM.runActions()
            gc.SIM.tickN(2)
            gs.SIM.tickN(2)
        return held

    def deliver(held):
        for msg in held:
            land(msg)

    m = menu(Lc, 0, mx, my)
    check(TEXT["ContextMenu_SEW_Enter"] in [n for n, _ in options(m)], "the client offers Climb down")
    gc.SIM.violations = Lc.table()
    choose(m, TEXT["ContextMenu_SEW_Enter"])
    held = pump(late_floor=True)
    check(bool(held) and abs(pc.z) < 1e-6,
          "with the move in and the floor not yet, the client waits on the street (%.1f)" % pc.z)
    deliver(held)
    gc.SIM.tickN(3)
    pump()
    check(abs(pc.z + 1) < 1e-6, "the client's player is below once the floor arrives (%.1f)" % pc.z)
    pump()
    key = "%d,%d" % (mx // 8, my // 8)
    check(gc.SEW.Map.state.c[key] is not None and gs.SEW.Discovery.record(ps).c[key] is not None,
          "on a server the walk is recorded there and reaches the client's map")
    check(Lc.execute("local sq = SIM.squares['%d,%d,-1']; return sq ~= nil and sq:getFloor() ~= nil" % (mx, my)),
          "the floor reached the client before the player did")
    v = lua_list(gc.SIM.violations)
    check(not v, "the client edited nothing (%s)" % v[:3])
    doors_client = Lc.execute("""
        local n = 0
        for _, sq in pairs(SIM.squares) do for _, o in ipairs(sq.specials._t) do if o.class == "IsoDoor" then n = n + 1 end end end
        return n
    """)
    doors_server = Ls.execute("""
        local n = 0
        for _, sq in pairs(SIM.squares) do for _, o in ipairs(sq.specials._t) do if o.class == "IsoDoor" then n = n + 1 end end end
        return n
    """)
    pics = [L.execute("""
        local n = 0
        for _, sq in pairs(SIM.squares) do
            for _, o in ipairs(sq.objects._t) do n = n + (o.attached and #o.attached._t or 0) end
        end
        return n
    """) for L in (Ls, Lc)]
    check(pics[0] > 0 and pics[1] == pics[0], "every picture the server hung on a wall reached the client on it (%d/%d)"
          % (pics[1], pics[0]))
    check(doors_server > 0 and doors_client == doors_server, "every door the server hung reached the client as a door (%d/%d)" % (doors_client, doors_server))

    # Digging on a server: the client asks by its timed action, the server
    # digs on its own records, and the rock opened and the wall gone reach
    # the client -- which edits nothing itself.
    for LL in (Ls, Lc):
        LL.execute("SIM.players[1].inv:AddItem(instanceItem('Base.PickAxe'))")
    offers = lua_list(Lc.execute("return SEW.Client.mineOffers(SIM.players[1])"))
    way = next((o for o in offers if o.kind == "dig"), None)
    ladder_dir = "N" if (lx, ly) == (mx, my) and Ls.execute("return SEW.Index.shafts['%d,%d'].edge" % (mx, my)) == "N"         else "W" if (lx, ly) == (mx, my) else None
    check(way is not None and ladder_dir not in [o.dir for o in offers],
          "the client is offered rock to dig beside the ladder, and not the ladder's own wall (%s; ladder %s)"
          % ([o.dir for o in offers], ladder_dir))
    if way is not None:
        tx_, ty_ = int(pc.x) + way.dx, int(pc.y) + way.dy
        gc.SIM.violations = Lc.table()
        m = menu(Lc, 0, int(pc.x), int(pc.y))
        top = [o for n, o in options(m) if n == TEXT["ContextMenu_SEW_Mine"]][0]
        choose(top.subMenu, TEXT["ContextMenu_SEW_Dig_" + way.dir])
        pump()
        pump()
        there = Lc.execute("local a, b = SIM.squares['%d,%d,-1'], SIM.squares['%d,%d,-1']; "
                           "return b ~= nil and b:getFloor() ~= nil and b:getFloor().sprite:getName() ~= SEW.Config.Sprites.floorRock, "
                           "a ~= nil and b ~= nil and a:isBlockedTo(b)" % (int(pc.x), int(pc.y), tx_, ty_))
        check(there[0] is True and there[1] is False,
              "on a server a dig reaches the client: the floor is there and the wall is gone %s" % (tuple(there),))
        v = lua_list(gc.SIM.violations)
        check(not v, "and the client edited nothing (%s)" % v[:3])
        check(any(n == TEXT["IGUI_SEW_MineDug"] for n in lua_list(gc.SIM.notes)),
              "and is told (%s; %s)" % (lua_list(gc.SIM.notes)[-2:], [l for l in lua_list(gs.SIM.log) if "refused" in l or "SIM" in l][-3:]))

    # Up again.
    pc.x, pc.y = lx + 0.5, ly + 0.5
    m = menu(Lc, 0, lx, ly)
    check(TEXT["ContextMenu_SEW_Exit"] in [n for n, _ in options(m)], "the client's ladder offers Climb out")
    choose(m, TEXT["ContextMenu_SEW_Exit"])
    pump()
    pump()
    check(abs(pc.z) < 1e-6, "the client's player is back on the street (%.1f)" % pc.z)

    # Sewer gas on a server: the server doses its own copy of the player and
    # syncs it; the client is told, and gets it on its map -- and writes no
    # stat of its own (the server's would overwrite it within a second).
    g0 = lua_list(gs.SEW.Index.gas)[0]
    ps.x, ps.y, ps.z = g0.x + 0.5, g0.y + 0.5, -1
    gs.SIM.outbox = Ls.table()
    gs.SIM.tickN(gs.SEW.Config.Gas.lookEvery * 2)
    gs.SIM.fire("EveryOneMinute")
    sent = [m for m in lua_list(gs.SIM.outbox) if m[1] == "serverCommand"]
    for m in sent:
        gc.SIM.fire("OnServerCommand", m[3], m[4], copy(Lc, m[5]))
    check(any(m[4] == "gas" for m in sent) and any("thick and sour" in n for n in lua_list(gc.SIM.notes)),
          "on a server, the client of a player walking into gas is told")
    check(gc.SEW.Map.state.g[1] is not None, "and the gas is on the client's map")
    syncs = lua_list(gs.SIM.statSyncs)
    check(Ls.execute("return SIM.players[1]:getStats():get(CharacterStat.POISON)") > 0
          and any(s.mask == gs.SEW.Config.Gas.syncMask for s in syncs),
          "the server poisons its own copy and syncs the stat (%d syncs)" % len(syncs))
    check(Lc.execute("return SIM.players[1].stats == nil"), "the client writes no stat")
    ps.x, ps.y, ps.z = pc.x, pc.y, pc.z

    # A locked grille built on the server reaches the client keyed and locked:
    # everything is set before transmitCompleteItemToClients, which carries it.
    gate = [x for x in lua_list(gs.SEW.Index.gates) if x.town == "muldraugh"][0]
    for cx in range(gate.x // 8 - 1, gate.x // 8 + 2):
        for cy in range(gate.y // 8 - 1, gate.y // 8 + 2):
            gs.SIM.load(cx, cy)
            gc.SIM.load(cx, cy)
    gs.SIM.outbox = Ls.table()
    Ls.execute("SEW.Build.around(%d, %d, 1)" % (gate.x, gate.y))
    for m in lua_list(gs.SIM.outbox):
        if m[1] in ("addObject", "updateSprite"):
            land(m)
    got = Lc.execute(GATE_DOOR, gate.x, gate.y, gate.edge == "N")
    check(got[0] == 1 and got[2] == gs.SEW.Index.towns.muldraugh.key and got[3] is True,
          "a locked grille reaches the client as a door, keyed and locked (%s)" % (tuple(got),))
    # And the latch, on a server, is sent the way vanilla's lock action sends it.
    latched = Ls.execute("""
        local x, y, north = ...
        local sq = SIM.squares[x .. "," .. y .. ",-1"]
        for _, o in ipairs(sq.specials._t) do
            if o.class == "IsoDoor" and o.north == north then o.lockedByKey, o.locked = false, false end
        end
        local p = SIM.players[1]
        local px, py, pz = p.x, p.y, p.z
        p.x, p.y, p.z = x + 0.5, y + 2.5, -1
        SIM.outbox = {}
        local n = SEW.Keys.latch()
        p.x, p.y, p.z = px, py, pz
        local sent = 0
        for _, m in ipairs(SIM.outbox) do if m[1] == "syncObject" then sent = sent + 1 end end
        return n, sent
    """, gate.x, gate.y, gate.edge == "N")
    check(latched[0] == 1 and latched[1] == 1, "on a server the latch locks the grille and sends it (%s)" % (tuple(latched),))

    rooms_test(Ls, ps, True)

    check(not warns(Ls), "no WARN on the server (%s)" % warns(Ls)[:3])
    check(not warns(Lc), "no WARN on the client (%s)" % warns(Lc)[:3])
    check(not list(gc.SIM.unknownText.keys()), "every text key the client used exists")


if __name__ == "__main__":
    single_player()
    multiplayer()
    print()
    if FAILS:
        print("%d FAILED" % len(FAILS))
        sys.exit(1)
    print("all passed")
