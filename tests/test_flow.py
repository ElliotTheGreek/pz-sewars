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
        for key, body in pairs(SEW.Data.muldraugh.chunks) do
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
    for hours, dev, moved_wanted, what, start, tx_, ty_ in (
            (0, False, False, "without the dev flag, a new character stays put", "lair", hx, hy),
            (0, True, True, "the dev build puts a new character by the hatch nearest the rats' nest", "lair", hx, hy),
            (0, True, True, "or, set to caves, on the cover over a cave", "cave", sx, sy),
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
    SEW.Config.DevStart = "lair"
    sim.players = L.table(p)

    lair_test(L, p)
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
    arrive = Lc.eval('''function(x, y, z, name, north, class, special, sew)
        local sq = getCell():getOrCreateGridSquare(x, y, z)
        -- Made by the packet, not by the mod: not the client's edit.
        local n = #SIM.violations
        local o = IsoObject.new(sq, name, "")
        while #SIM.violations > n do table.remove(SIM.violations) end
        o.md.sew, o.north, o.class = sew, north, class
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
            arrive(sq.x, sq.y, sq.z, o.sprite.getName(), o.north, o["class"], msg[3], o.md.sew)
        else:
            names = [o.attached._t[j].getParentSprite().getName() for j in range(1, len(o.attached._t) + 1)]
            resprite(sq.x, sq.y, sq.z, o.sprite.getName(), Lc.table(*names))

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

    # Up again.
    pc.x, pc.y = lx + 0.5, ly + 0.5
    m = menu(Lc, 0, lx, ly)
    check(TEXT["ContextMenu_SEW_Exit"] in [n for n, _ in options(m)], "the client's ladder offers Climb out")
    choose(m, TEXT["ContextMenu_SEW_Exit"])
    pump()
    pump()
    check(abs(pc.z) < 1e-6, "the client's player is back on the street (%.1f)" % pc.z)

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
