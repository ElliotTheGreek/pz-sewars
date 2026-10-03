"""The local dev build: one command for everything between an edit and the game.

    python tools/dev.py                 # check + deploy: the usual loop after an edit
    python tools/dev.py build           # regenerate everything generated (layout, tiles, sounds, poster, store art)
    python tools/dev.py check           # every static test (seconds to a minute)
    python tools/dev.py mutate          # break each guard on purpose; every one must be caught (minutes)
    python tools/dev.py deploy          # install as SewarsDev into ~/Zomboid/mods and verify the copy
    python tools/dev.py run             # launch the game (returns at once); run --debug for the debug console
    python tools/dev.py log             # the mod's lines out of console.txt, and every WARN
    python tools/dev.py package         # stage the Workshop upload in workshop/Sewars (validated)
    python tools/dev.py package --install   # and into ~/Zomboid/Workshop/Sewars for the in-game uploader
    python tools/dev.py all             # build + check + deploy

The deployed copy is **SewarsDev** ("Sewers [DEV]" on the mods screen), so a
subscribed Workshop copy can sit beside it without the game confusing the two.
Enable SewarsDev, not Sewars, to test. Nothing here uploads anything: the
upload is the in-game Workshop screen, by hand, after `package --install`.
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
GAME = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\ProjectZomboid64.exe"
LOG = os.path.join(os.path.expanduser("~"), "Zomboid", "console.txt")


def run(*args, what=None):
    print("\n== %s" % (what or " ".join(args)))
    r = subprocess.run([PY] + list(args), cwd=ROOT)
    if r.returncode != 0:
        sys.exit("FAILED: %s" % (what or " ".join(args)))


def build():
    run("tools/pzcatalog.py", "build", what="catalogue the installed game")
    run("tools/gen_sewers.py", "--plans", what="lay out the sewers from the map")
    run("tools/gen_sewer_art.py", what="draw and pack the tiles")
    run("tools/gen_sewer_sounds.py", what="synthesise the sounds")
    run("tools/gen_poster.py", what="poster and preview")
    run("tools/gen_store_art.py", what="Steam store images")


def check():
    run("tools/luacheck.py", "Sewars/42/media/lua", what="Lua syntax")
    run("tests/test_assets.py", what="every name against the game")
    run("tests/test_layout.py", what="the tunnels, walked")
    run("tests/test_flow.py", what="the loop, single player and multiplayer")


def log():
    if not os.path.exists(LOG):
        sys.exit("no console.txt yet: run the game first")
    lines = open(LOG, encoding="utf-8", errors="replace").read().splitlines()
    print("== console.txt: %d lines, written %s" % (len(lines), time.ctime(os.path.getmtime(LOG))))
    print("   (overwritten every launch: check the time before believing it)")
    ours = [l for l in lines if "[SEW]" in l]
    print("\n-- the mod's own lines (%d) --" % len(ours))
    for l in ours[-60:]:
        print(l)
    warns = [l for l in ours if "WARN" in l]
    print("\n-- WARN (%d) --" % len(warns))
    for l in warns:
        print(l)
    errs = [l for l in lines if ("ERROR" in l or "Exception" in l) and ("SEW" in l or "Sewars" in l)]
    print("\n-- errors naming the mod (%d) --" % len(errs))
    for l in errs[:40]:
        print(l)


def main():
    a = sys.argv[1:] or ["dev"]
    cmd = a[0]
    if cmd == "build":
        build()
    elif cmd == "check":
        check()
    elif cmd == "mutate":
        run("tests/mutate.py", what="mutations")
    elif cmd == "deploy":
        run("tools/deploy_windows.py", what="deploy SewarsDev")
    elif cmd == "dev":
        check()
        run("tools/deploy_windows.py", what="deploy SewarsDev")
        print("\nready: start the game (python tools/dev.py run), enable 'Sewers [DEV]', new world.")
    elif cmd == "all":
        build()
        check()
        run("tools/deploy_windows.py", what="deploy SewarsDev")
    elif cmd == "run":
        if not os.path.exists(GAME):
            sys.exit("game not found at " + GAME)
        # Not -debug by default: under -debug the game halts on every Lua error,
        # even one the mod catches and survives, which made 0.2.0 unplayable
        # for the author. Errors still reach console.txt; `dev.py log` reads them.
        # `run --debug` for the debug console (SEW_Here and friends).
        args = [GAME] + (["-debug"] if "--debug" in a else [])
        subprocess.Popen(args, cwd=os.path.dirname(GAME))
        print("launched%s. When done: python tools/dev.py log" % (" with -debug" if "--debug" in a else ""))
    elif cmd == "log":
        log()
    elif cmd == "package":
        run("tools/package_workshop.py", *a[1:], what="Workshop package")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
