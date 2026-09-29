"""Deploy Sewars to the current Windows user's Project Zomboid mods folder.

Installed as SewarsDev, so a subscribed Workshop copy with id=Sewars cannot be
confused with the one under test (the trekship learned this the hard way:
Project Zomboid cannot reliably tell two providers of one id apart).
"""
import hashlib
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Sewars"
DESTINATION = Path.home() / "Zomboid" / "mods" / "Sewars"

if DESTINATION.exists():
    shutil.rmtree(DESTINATION)
DESTINATION.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(SOURCE, DESTINATION)

info = DESTINATION / "42" / "mod.info"
lines = info.read_text(encoding="utf-8").splitlines()
lines = [
    "name=Sewars [DEV]" if line == "name=Sewars" else
    "id=SewarsDev" if line == "id=Sewars" else
    line + "-dev" if line.startswith("modversion=") and not line.endswith("-dev") else
    line
    for line in lines
]
info.write_text("\n".join(lines) + "\n", encoding="utf-8")
if "id=SewarsDev" not in lines or "name=Sewars [DEV]" not in lines:
    raise SystemExit("development mod identity was not written")

source_files = sorted(p.relative_to(SOURCE) for p in SOURCE.rglob("*") if p.is_file())
deployed_files = sorted(p.relative_to(DESTINATION) for p in DESTINATION.rglob("*") if p.is_file())
if source_files != deployed_files:
    raise SystemExit("deployed file list does not match source")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Files whose absence would be silent in game. Add to this as the mod grows:
# a model that does not arrive draws nothing and says nothing.
critical = [
    Path("42/media/lua/shared/SEW/SEW_Config.lua"),
    Path("42/media/lua/shared/SEW/SEW_Index.lua"),
    Path("42/media/lua/shared/SEW/SEW_Actions.lua"),
    Path("42/media/lua/server/SEW/SEW_Build.lua"),
    Path("42/media/lua/server/SEW/SEW_Server.lua"),
    Path("42/media/lua/client/SEW/SEW_Client.lua"),
    # The layout: without it every cover says it leads nowhere.
    Path("42/media/lua/server/SEW/Data/SEW_Town_muldraugh.lua"),
    # The tiles: without the pack every ladder, stencil and puddle draws nothing.
    Path("42/media/texturepacks/sewars.pack"),
    Path("42/media/sewars.tiles"),
    Path("42/media/scripts/sewars_sounds.txt"),
    Path("42/media/sound/SEW_Lid.wav"),
    Path("42/poster.png"),
    # The map and the story: a missing tile draws a hole in the plan, a missing
    # icon an invisible item, a missing script an item that never exists.
    Path("42/media/lua/client/SEW/SEW_Map.lua"),
    Path("42/media/lua/client/SEW/SEW_StoryUI.lua"),
    Path("42/media/lua/server/SEW/SEW_Discovery.lua"),
    Path("42/media/lua/server/SEW/SEW_Story.lua"),
    Path("42/media/ui/sewermap/muldraugh_0_0.png"),
    Path("42/media/scripts/sewars_items.txt"),
    Path("42/media/textures/Item_SEW_Plan.png"),
    Path("42/media/textures/Item_SEW_Journal.png"),
]
for rel in critical:
    if digest(SOURCE / rel) != digest(DESTINATION / rel):
        raise SystemExit("hash mismatch: " + str(rel))
    print(rel, "ok")

# The dev build's flag, written into the installed copy only, after the copy
# is verified against the source: it turns on the test kit (C.DevKit, a torch,
# batteries and a crowbar, once per character in single player). The source
# tree and the Workshop package never have this file.
dev_flag = DESTINATION / "42" / "media" / "lua" / "shared" / "SEW" / "SEW_Dev.lua"
dev_flag.write_text("-- Written by tools/deploy_windows.py into the dev install only.\n"
                    "SEW = SEW or {}\nSEW.Dev = true\n", encoding="utf-8")
if (SOURCE / dev_flag.relative_to(DESTINATION)).exists():
    raise SystemExit("SEW_Dev.lua is in the source tree; it must only ever be written here")
print("dev build: SEW_Dev.lua written (test kit on)")

print("deployed", len(deployed_files), "files ->", DESTINATION)
