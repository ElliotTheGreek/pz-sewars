"""Breaks the mod on purpose, one guard at a time, and checks the tests notice.

    python tests/mutate.py

Each mutation is applied, **asserted to have changed the file** (a mutation
that does not apply proves nothing -- pz_trekship DEV_GUIDE), the flow tests
run, and the file is put back byte for byte in a `finally`. One at a time:
two runs at once would restore each other's mutations.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "Sewars", "42", "media", "lua")

MUTATIONS = [
    ("unwall on revision", "server/SEW/SEW_Build.lua",
     "    if not first then B.unwall(sq, walls, n, w, fix) end\n", ""),
    ("discovery", "server/SEW/SEW_Server.lua",
     'if S.below(p) then U.try("discover", SEW.Discovery.look, p) end', ""),
    ("ladder on the map", "server/SEW/SEW_Server.lua",
     "        SEW.Discovery.ladder(player, x, y)\n        U.log(\"%s climbs down", "        U.log(\"%s climbs down"),
    ("map clip", "client/SEW/SEW_Map.lua",
     "self:setStencilRect(0, top, self.width, bottom - top)", ""),
    ("journals stocked", "server/SEW/SEW_Build.lua",
     "if extra and SEW.Story then SEW.Story.stockExtras(c, extra) end", ""),
    ("journal marks", "server/SEW/SEW_Story.lua",
     'return SEW.Discovery.mark(player, "j" .. idx, j.x, j.y, j.kind)', "return false"),
    ("plan reveals", "server/SEW/SEW_Story.lua",
     "local n = SEW.Discovery.reveal(player, plan.town, x0, y0, x0 + C.MapTile - 1, y0 + C.MapTile - 1)",
     "local n = 0"),
    ("fog cache", "client/SEW/SEW_Map.lua",
     "if cached and cached.v == M.version then return cached.rects end", "if cached then return cached.rects end"),
    ("no next in Kahlua", "client/SEW/SEW_Client.lua",
     "        if anyLamp() then Client.clearLamps() end", "        if next(lamps) then Client.clearLamps() end"),
    ("reach refusal", "server/SEW/SEW_Server.lua",
     'if not S.within(player, x, y, C.Reach + 1.0) then return refuse(player, "reach") end', ""),
    ("level refusal (up)", "server/SEW/SEW_Server.lua",
     '        if not S.below(player) then return refuse(player, "level") end\n        if not (S.within', '        if not (S.within'),
    ("grant before build", "server/SEW/SEW_Server.lua",
     "local done, left = B.around(x, y, C.EntryRadiusChunks)", "local done, left = 0, 0"),
    ("foreign squares", "server/SEW/SEW_Build.lua",
     'if first and foreign(sq) then return "foreign" end', ""),
    ("stock once", "server/SEW/SEW_Build.lua",
     "        s.first[key] = B.rev()\n", ""),
    # Set in one place only, B.furnish, for every container stocked or not: a
    # second copy in U.fill hid this mutation, and was taken out.
    ("explored", "server/SEW/SEW_Build.lua",
     '        U.try("explored", function() c:setExplored(true) end)\n', ""),
    ("spawn clearance", "server/SEW/SEW_Build.lua",
     "if nearAPlayer(x, y, C.SpawnClearance) then return false end", ""),
    ("door as special", "server/SEW/SEW_Build.lua",
     "if isServer() then door:transmitCompleteItemToClients() end", ""),
    ("vault off", "client/SEW/SEW_Client.lua",
     'U.try("vault.off", function() p:setIgnoreAutoVault(false) end)', ""),
    ("wait for the floor", "client/SEW/SEW_Client.lua",
     "    if not arrivable(m.x, m.y, m.z) then", "    if false then"),
    ("lamps down", "client/SEW/SEW_Client.lua",
     "        Client.clearLamps()\n    elseif m.mode == \"rescue\"", "    elseif m.mode == \"rescue\""),
    ("action parameter names", "shared/SEW/SEW_Actions.lua",
     "    o.x = x\n", "    o.cx = x\n"),
    ("rescue", "client/SEW/SEW_Client.lua",
     '    Net.send(p, "rescue", {})', ""),
    ("client guard", "client/SEW/SEW_Client.lua",
     "if isServer() then return end", ""),
    ("server guard", "server/SEW/SEW_Server.lua",
     "if isClient() then return end", ""),
    ("shut cover", "client/SEW/SEW_Client.lua",
     '    if S.shaftAt(sq:getX(), sq:getY()) then return "down", sq end\n    return "shut", sq',
     '    return "down", sq'),
]


def main():
    missed = []
    for name, rel, old, new in MUTATIONS:
        path = os.path.join(LUA, rel)
        orig = open(path, "rb").read()
        text = orig.decode("utf-8")
        if old not in text:
            print("  NOAPPLY  %s: the search text is not in %s" % (name, rel))
            missed.append(name)
            continue
        mutated = text.replace(old, new, 1)
        assert mutated != text
        try:
            open(path, "wb").write(mutated.encode("utf-8"))
            r = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "test_flow.py")],
                               capture_output=True, text=True)
            caught = r.returncode != 0
            first = next((l.strip() for l in r.stdout.splitlines() if "FAIL" in l), r.stderr.strip()[-120:])
            print("  %s  %-24s %s" % ("caught" if caught else "MISSED", name, first if caught else ""))
            if not caught:
                missed.append(name)
        finally:
            open(path, "wb").write(orig)
        if open(path, "rb").read() != orig:
            sys.exit("could not restore " + rel)
    print()
    if missed:
        print("MISSED: %s" % ", ".join(missed))
        sys.exit(1)
    print("every mutation caught")


if __name__ == "__main__":
    main()
