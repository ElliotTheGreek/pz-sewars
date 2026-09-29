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
        if s.town == town:
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
    return [sq.objects._t[i].sprite.getName() for i in range(1, len(sq.objects._t) + 1)]


def count_ours(L):
    return L.execute("""
        local n = 0
        for _, sq in pairs(SIM.squares) do
            for _, o in ipairs(sq.objects._t) do if o.md and o.md.sew then n = n + 1 end end
        end
        return n
    """)


# --- single player -----------------------------------------------------------------------------

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
    notes = lua_list(sim.notes)
    check(any("Down into the dark" in n for n in notes), "the arrival note (%s)" % notes[-1:])
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
                elif msg[1] == "addObject" and late_floor:
                    held.append(msg)
                elif msg[1] == "addObject":
                    o, special = msg[2], msg[3]
                    sq = o.square
                    ck = "%d,%d" % (sq.x // 8, sq.y // 8)
                    if gc.SIM.loaded[ck]:
                        arrive(sq.x, sq.y, sq.z, o.sprite.getName(), o.north, o["class"], special, o.md.sew)
            gc.SIM.runActions()
            gc.SIM.tickN(2)
            gs.SIM.tickN(2)
        return held

    def deliver(held):
        for msg in held:
            o, special = msg[2], msg[3]
            sq = o.square
            if gc.SIM.loaded["%d,%d" % (sq.x // 8, sq.y // 8)]:
                arrive(sq.x, sq.y, sq.z, o.sprite.getName(), o.north, o["class"], special, o.md.sew)

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
