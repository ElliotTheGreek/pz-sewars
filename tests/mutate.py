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
    # Sewer gas (0.5, DESIGN.md 7b).
    ("gas: the dose", "server/SEW/SEW_Gas.lua",
     "        if give > 0 then stats:add(CharacterStat.POISON, give) end\n", ""),
    ("gas: the cap", "server/SEW/SEW_Gas.lua",
     "local give = math.max(0, math.min(dose, cap - now))", "local give = dose"),
    ("gas: a mask keeps it out", "server/SEW/SEW_Gas.lua", "    if G.protected(p) then\n", "    if false then\n"),
    ("gas: the filter is used", "server/SEW/SEW_Gas.lua",
     "            call(function() it:drainGasMask(C.Gas.filterDrain) end)\n", ""),
    ("gas: the stat synced", "server/SEW/SEW_Gas.lua",
     'U.try("gas.sync", function() syncPlayerStats(p, C.Gas.syncMask) end)', "local _ = p"),
    ("gas: dressed once", "server/SEW/SEW_Build.lua", "        s.gas[key] = B.rev()\n", ""),
    ("gas: not while off", "server/SEW/SEW_Build.lua",
     "if s.gas[key] == nil and SEW.Gas and SEW.Gas.strength() > 1 and", "if s.gas[key] == nil and SEW.Gas and"),
    ("gas: placards hung", "server/SEW/SEW_Gas.lua",
     "        if sq and B.hang(sq, C.Sprites.gasSign[s[3]]) then n = n + 1 end\n", ""),
    ("gas: on the map", "server/SEW/SEW_Gas.lua", "            if i then SEW.Discovery.gas(p, i) end\n", ""),
    ("gas: the note", "server/SEW/SEW_Gas.lua",
     '            Net.toClient(p, "gas", { protected = G.protected(p) })\n', ""),
    ("gas: no nagging", "server/SEW/SEW_Gas.lua",
     "        if here and G.inside[name] ~= here then", "        if here then"),
    ("gas: a plan knows", "server/SEW/SEW_Story.lua",
     "            SEW.Discovery.gas(player, i)\n", ""),
    # Locked gates (0.5, DESIGN.md 7, Locked gates).
    ("gates: keyed", "server/SEW/SEW_Build.lua", "            door:setKeyId(key)\n", ""),
    ("gates: locked", "server/SEW/SEW_Build.lua", "            door:setLockedByKey(true)\n", ""),
    ("gates: made from the sprite", "server/SEW/SEW_Build.lua",
     "IsoDoor.new(getCell(), sq, getSprite(sprite), north)", "IsoDoor.new(getCell(), sq, sprite, north)"),
    ("gates: a grille, not a door", "server/SEW/SEW_Build.lua",
     "            elseif n == \"j\" then putDoor(sq, true, key)", "            elseif n == \"j\" then putDoor(sq, true)"),
    ("gates: frame kept on revision", "server/SEW/SEW_Build.lua",
     '    if n == "d" or n == "j" then want[C.Sprites.doorFrame.N] = true end\n'
     '    if w == "d" or w == "j" then want[C.Sprites.doorFrame.W] = true end\n',
     '    if n == "d" then want[C.Sprites.doorFrame.N] = true end\n'
     '    if w == "d" then want[C.Sprites.doorFrame.W] = true end\n'),
    ("gates: the key in the crate", "server/SEW/SEW_Build.lua",
     'for _, k in ipairs(T.keys and T.keys[key] or {}) do U.try("key", SEW.Keys.stock, k[1], k[2], tid) end', ""),
    ("gates: the key's id", "server/SEW/SEW_Keys.lua", '    U.try("key.id", function() item:setKeyId(t.key) end)\n', ""),
    ("gates: the key on the dead", "server/SEW/SEW_Keys.lua",
     'if key and U.try("z.key", function() inv:AddItem(key); return true end) then added[#added + 1] = "key" end',
     "local _ = key"),
    ("gates: only the county's dead", "server/SEW/SEW_Keys.lua",
     '    if U.try("z.outfit", function() return z:getOutfitName() end) ~= C.Gates.outfit then return nil end\n', ""),
    ("gates: only below", "server/SEW/SEW_Keys.lua",
     '    if (U.try("z.z", function() return z:getZ() end) or 0) > -0.5 then return nil end\n', ""),
    ("gates: the latch", "server/SEW/SEW_Keys.lua",
     '    if ticks % C.Gates.latchEvery == 0 then U.try("keys.latch", K.latch) end\n', ""),
    ("gates: latched only shut", "server/SEW/SEW_Keys.lua",
     "elseif not inside and not d:IsOpen() and not d:isLockedByKey() then",
     "elseif not inside and not d:isLockedByKey() then"),
    ("gates: latch only ours", "server/SEW/SEW_Keys.lua",
     'if instanceof(d, "IsoDoor") and U.isOurs(d) and', 'if instanceof(d, "IsoDoor") and'),
    ("gates: a handle on the inside", "server/SEW/SEW_Keys.lua",
     "                if inside and d:isLockedByKey() then", "                if false then"),
    ("gates: not latched on anyone", "server/SEW/SEW_Keys.lua",
     "                elseif not inside and not d:IsOpen() and not d:isLockedByKey() then",
     "                elseif not d:IsOpen() and not d:isLockedByKey() then"),
    ("only an animal is asked its type", "server/SEW/SEW_Nest.lua",
     '    if not instanceof(a, "IsoAnimal") then return false end\n', ""),
    ("dev trips go down only onto a built floor", "client/SEW/SEW_Client.lua",
     "        U.teleport(p, x, y, 0)\n        Client.vault(p)\n        return true",
     "        Client.devTravel = nil\n        U.teleport(p, x, y, C.Z)\n        return true"),
    ("no bite through a wall", "server/SEW/SEW_Nest.lua",
     "    if d <= C.Rous.reach and not walled then", "    if d <= C.Rous.reach then"),
    ("gates: latch sent", "server/SEW/SEW_Keys.lua",
     "                    if isServer() then d:syncIsoObject(false, 0, nil, nil) end\n", ""),
    # Storm-drain outfalls (0.5, DESIGN.md 7c).
    ("outfalls: the grate", "server/SEW/SEW_Build.lua",
     "    local sprite = shaft.outfall and C.Sprites.outfall or C.Sprites.cover\n",
     "    local sprite = C.Sprites.cover\n"),
    ("outfalls: a grate is a way down", "shared/SEW/SEW_Sewer.lua",
     "\n                          or U.findSprite(sq, C.Sprites.outfall) ~= nil)", ")"),
    ("outfalls: on the menu", "client/SEW/SEW_Client.lua",
     '    if shaft and shaft.outfall then return "outfall", sq end\n', ""),
    ("outfalls: the note", "server/SEW/SEW_Server.lua",
     'mode = "down",\n                                     hatch = shaft.hatch ~= nil, outfall = shaft.outfall == true })',
     'mode = "down",\n                                     hatch = shaft.hatch ~= nil })'),
    ("outfalls: no lid", "shared/SEW/SEW_Actions.lua",
     "    o.outfall = shaft ~= nil and shaft.outfall == true\n", "    o.outfall = false\n"),
    ("outfalls: blue on the map", "client/SEW/SEW_Map.lua",
     "            if sh.outfall then\n                self:drawRect(sx - mk, sy - mk, mk * 2, mk * 2, 1, 0.22, 0.48, 0.74)",
     "            if false then\n                self:drawRect(sx - mk, sy - mk, mk * 2, mk * 2, 1, 0.22, 0.48, 0.74)"),
    # The rats and the nest (0.5).
    ("rats on the first build", "server/SEW/SEW_Build.lua",
     '        if SEW.Nest then U.try("rats", SEW.Nest.rats, open, cx, cy) end\n', ""),
    ("rodents put down with the nest", "server/SEW/SEW_Build.lua",
     '        if nest > 0 and SEW.Nest then U.try("rous", SEW.Nest.lairChunk, key) end\n', ""),
    ("each rodent once", "server/SEW/SEW_Nest.lua",
     "if not st.rous[k] and math.floor(x / 8)", "if math.floor(x / 8)"),
    ("the gate waits for the last of them", "server/SEW/SEW_Nest.lua",
     'if which == "gate" and (not N.allSpawned() or #N.living(L.x, L.y, C.Rous.range) > 0) then',
     'if which == "gate" and not N.allSpawned() then'),
    ("the living are the living", "server/SEW/SEW_Nest.lua",
     'if a and isRous(a) and not U.try("rous.dead", function() return a:isDead() end) then',
     'if a and isRous(a) then'),
    ("a pull within reach", "server/SEW/SEW_Nest.lua",
     '        return refuse(player, "reach")\n', '        local _ = 0\n'),
    ("the bite", "server/SEW/SEW_Nest.lua", "            N.bite(a, p)\n", ""),
    ("walked by hand when the path fails", "server/SEW/SEW_Nest.lua",
     "            if h.lx and U.dist(ax, ay, h.lx, h.ly) < 0.5 then", "            if false then"),
    ("never through a wall", "server/SEW/SEW_Nest.lua",
     'if not U.floorOf(there) or U.try("blocked", function() return here:isBlockedTo(there) end) ~= false then',
     "if not U.floorOf(there) then"),
    ("rats in the middle of their square", "server/SEW/SEW_Nest.lua",
     "            N.place(a, x + 0.5, y + 0.5)\n", ""),
    ("the leash", "server/SEW/SEW_Nest.lua",
     '    if ticks % C.LeashEvery == 0 then U.try("leash", N.leash) end\n', ""),
    ("an open gate is a breach", "server/SEW/SEW_Build.lua",
     "    if GATE[n] then n = B.gateOpen(GATE[n].which) and GATE[n].open or GATE[n].shut end\n"
     "    if GATE[w] then w = B.gateOpen(GATE[w].which) and GATE[w].open or GATE[w].shut end\n",
     "    if GATE[n] then n = GATE[n].shut end\n    if GATE[w] then w = GATE[w].shut end\n"),
    ("the false wall on the menu", "client/SEW/SEW_Client.lua",
     '        if which then return "pry", which end\n', ""),
    ("the ROUS moves as a rat", "shared/SEW/SEW_Rats.lua", '    d.animset = "rat"\n', '    d.animset = "rous"\n'),
    ("the dev build starts by the nest", "client/SEW/SEW_Client.lua",
     '    local h = C.DevStart == "lair" and Client.devLairHatch()', "    local h = nil"),
    ("unwall on revision", "server/SEW/SEW_Build.lua",
     "    if not first then B.unwall(sq, walls, n, w, fix) end\n", ""),
    ("old sludge swapped", "server/SEW/SEW_Build.lua",
     'U.try("unsludge", function() sq:transmitRemoveItemFromSquare(o) end)', ""),
    ("breach knocked through", "server/SEW/SEW_Build.lua",
     "    if BREACH[n] then hang(sq, C.Sprites.breach[n].N) end\n"
     "    if BREACH[w] then hang(sq, C.Sprites.breach[w].W) end\n", ""),
    ("rock gives way to a cave", "server/SEW/SEW_Build.lua",
     'U.try("unrock", function() sq:transmitRemoveItemFromSquare(floor) end)', ""),
    ("hideout furnished", "server/SEW/SEW_Build.lua",
     "for _, e in ipairs(T.caveFurniture and T.caveFurniture[key] or {}) do B.furnish(e, seed) end", ""),
    ("caves recorded done", "server/SEW/SEW_Build.lua",
     "        s.caves[key] = B.rev()\n", ""),
    ("dev start only in the dev build", "client/SEW/SEW_Client.lua",
     "if not SEW.Dev or isClient() or not p then devStartAt = nil return false end",
     "if isClient() or not p then devStartAt = nil return false end"),
    ("dev start only for a new character", "client/SEW/SEW_Client.lua",
     "    if isNew(p) then devStartPlayer = p end", "    devStartPlayer = p"),
    ("hatch gate on the server", "server/SEW/SEW_Server.lua",
     'if shaft.hatch and B.hatch(shaft) ~= "open" then return refuse(player, "shut") end', ""),
    ("hatch basement check", "server/SEW/SEW_Build.lua",
     "        if sq and foreign(sq) then\n            s.hatches[key] = \"blocked\"",
     "        if false then\n            s.hatches[key] = \"blocked\""),
    ("hatch surface pass", "server/SEW/SEW_Server.lua",
     ' else U.try("hatches", Server.hatches, p) end', " end"),
    ("hatch on the menu", "client/SEW/SEW_Client.lua",
     'if h and S.shaftAt(h:getX(), h:getY()) then return "hatch", h end', ""),
    ("no rescue to a hatch", "shared/SEW/SEW_Sewer.lua",
     "        if not s.hatch then\n            local d = U.dist(x, y, s.x, s.y)",
     "        if true then\n            local d = U.dist(x, y, s.x, s.y)"),
    ("covers of ours go in", "server/SEW/SEW_Server.lua",
     "            elseif s.made and not st.covers[key] then B.cover(s) end", "            end"),
    ("cover gate on the server", "server/SEW/SEW_Server.lua",
     'if shaft.made and B.cover(shaft) ~= "placed" then return refuse(player, "shut") end', ""),
    ("a cover of ours is a cover", "shared/SEW/SEW_Sewer.lua",
     " or U.findSprite(sq, C.Sprites.cover) ~= nil\n", "\n"),
    ("only our old sludge", "server/SEW/SEW_Build.lua",
     "if U.isOurs(o) and U.spriteName(o) == C.Sprites.sludgeOld then", "if U.spriteName(o) == C.Sprites.sludgeOld then"),
    ("discovery", "server/SEW/SEW_Server.lua",
     'if S.below(p) then U.try("discover", SEW.Discovery.look, p) else', 'if S.below(p) then local _ = p else'),
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
     'if fresh and foreign(sq) then return "foreign" end', ""),
    ("stock once", "server/SEW/SEW_Build.lua",
     "        s.first[key] = B.rev()\n", ""),
    # Set in one place only, B.furnish, for every container stocked or not: a
    # second copy in U.fill hid this mutation, and was taken out.
    ("explored", "server/SEW/SEW_Build.lua",
     '        U.try("explored", function() c:setExplored(true) end)\n', ""),
    ("map key off the engine", "client/SEW/SEW_Map.lua",
     'addKeyBind("sewerMapKey", getText("IGUI_SEW_MapKey"), Keyboard.KEY_K,',
     'addKeyBind("sewerMapKey", getText("IGUI_SEW_MapKey"), Keyboard.KEY_N,'),
    ("0.3.1's saved key", "client/SEW/SEW_Map.lua",
     'addKeyBind("sewerMapKey",', 'addKeyBind("sewerMap",'),
    ("map key at the wheel", "client/SEW/SEW_Map.lua",
     '    if U.try("map.vehicle", function() return p:getVehicle() end) then return end\n', ""),
    ("loot count", "shared/SEW/SEW_Util.lua",
     "    for _ = 1, count or 0 do", "    for _ = 1, #list do"),
    ("equipped share", "server/SEW/SEW_Build.lua",
     "if roll(100) <= C.EquippedShare[mix] * 100 then", "if roll(100) <= 36 then"),
    ("shelter dead undressed", "server/SEW/SEW_Build.lua",
     "    if not EQUIPPED[outfit] then return outfit end\n", "    do return outfit end\n"),
    ("pictures hang on walls", "server/SEW/SEW_Build.lua",
     "    if not host then return put(sq, sprite) end\n", "    do return put(sq, sprite) end\n"),
    ("hung pictures reach clients", "server/SEW/SEW_Build.lua",
     "        if isServer() then host:transmitUpdatedSpriteToClients() end\n", ""),
    ("old saves rehung", "server/SEW/SEW_Build.lua",
     "    if not first then B.rehang(sq) end\n", ""),
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
    ("below is indoors", "shared/SEW/SEW_Compat.lua",
     "        if P.below(self) then return false end\n", ""),
    ("the street stays outside", "shared/SEW/SEW_Compat.lua",
     "return z ~= nil and z < 0", "return z ~= nil and z <= 0"),
    ("wrap the engine's method", "shared/SEW/SEW_Compat.lua",
     "local engine = rawget(index, ORIGINAL) or index.isOutside", "local engine = index.isOutside"),
    ("shut cover", "client/SEW/SEW_Client.lua",
     '    if shaft then return "down", sq end\n    return "shut", sq',
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
