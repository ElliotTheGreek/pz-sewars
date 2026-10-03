"""Builds, and optionally stages, the Steam Workshop upload.

    python tools/package_workshop.py              # workshop/Sewars, validated
    python tools/package_workshop.py --install    # and ~/Zomboid/Workshop/Sewars, for the in-game uploader

The Build 42 layout the in-game uploader expects:

    Sewars/
      workshop.txt
      preview.png                   256x256 (tools/gen_poster.py)
      Contents/mods/Sewars/42/...   and common/

Adapted from pz_trekship's, and its two hard lessons are kept:

  * **WORKSHOP_ID is the whole difference between updating the mod and
    publishing a second copy of it.** Empty until the first upload; after
    it, paste the id Steam gives here and never change it. The uploader has
    no other way to know which item it is updating.
  * **The first upload is private.** Look at the item on Steam, then set
    VISIBILITY = "public" and upload again.
"""
import argparse
import shutil
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "Sewars"
BUILD = ROOT / "workshop" / "Sewars"
INSTALLED = Path.home() / "Zomboid" / "Workshop" / "Sewars"

WORKSHOP_ID = "3810188405"          # set after the first upload, then never change it
VISIBILITY = "public"       # "public" once the first upload has been checked
TITLE = "Sewers Under Every Town (Build 42)"
DESCRIPTION = (ROOT / "workshop" / "description.txt").read_text(encoding="utf-8").splitlines()
DESCRIPTION_LIMIT = 8000


def png_dimensions(path):
    with path.open("rb") as f:
        if f.read(8) != b"\x89PNG\r\n\x1a\n":
            raise SystemExit("not a PNG: " + str(path))
        f.read(8)
        return struct.unpack(">II", f.read(8))


def workshop_text():
    lines = ["version=1"]
    if WORKSHOP_ID:
        lines.append("id=" + WORKSHOP_ID)
    lines.append("title=" + TITLE)
    lines += ["description=" + line for line in DESCRIPTION]
    lines += ["tags=Build 42;Map;Misc", "visibility=" + VISIBILITY]
    return "\n".join(lines) + "\n"


def published_id(text):
    for line in text.splitlines():
        if line.startswith("id="):
            return line[3:].strip()
    return None


def validate(package):
    mod = package / "Contents" / "mods" / "Sewars"
    required = [package / "workshop.txt", package / "preview.png", mod / "42" / "mod.info",
                mod / "42" / "poster.png", mod / "42" / "media" / "sewars.tiles",
                mod / "42" / "media" / "texturepacks" / "sewars.pack",
                mod / "42" / "media" / "lua" / "shared" / "SEW" / "SEW_Index.lua",
                mod / "42" / "media" / "lua" / "server" / "SEW" / "Data" / "SEW_Town_muldraugh.lua"]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise SystemExit("Workshop package is missing:\n  " + "\n  ".join(missing))
    if png_dimensions(package / "preview.png") != (256, 256):
        raise SystemExit("preview.png must be exactly 256x256")
    info = (mod / "42" / "mod.info").read_text(encoding="utf-8")
    if "id=Sewars\n" not in info + "\n" or "[DEV]" in info:
        raise SystemExit("the packaged mod.info is not the release identity")
    length = len("\n".join(DESCRIPTION))
    if length > DESCRIPTION_LIMIT:
        raise SystemExit("description is %d characters; Steam allows %d" % (length, DESCRIPTION_LIMIT))
    staged = published_id((package / "workshop.txt").read_text(encoding="utf-8"))
    if WORKSHOP_ID and staged != WORKSHOP_ID:
        raise SystemExit("workshop.txt does not carry id=%s; uploading it would publish a new item" % WORKSHOP_ID)
    n = sum(1 for p in package.rglob("*") if p.is_file())
    print("validated %d files; item %s; visibility %s; description %d/%d"
          % (n, staged or "UNPUBLISHED (a new item will be created)", VISIBILITY, length, DESCRIPTION_LIMIT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="also copy to ~/Zomboid/Workshop/Sewars")
    a = ap.parse_args()
    if BUILD.exists():
        shutil.rmtree(BUILD)
    shutil.copytree(MOD, BUILD / "Contents" / "mods" / "Sewars")
    (BUILD / "workshop.txt").write_text(workshop_text(), encoding="utf-8")
    shutil.copy(ROOT / "workshop" / "preview.png", BUILD / "preview.png")
    validate(BUILD)
    print("package ->", BUILD)
    if a.install:
        existing = INSTALLED / "workshop.txt"
        if existing.is_file():
            staged = published_id(existing.read_text(encoding="utf-8"))
            if staged and staged != WORKSHOP_ID:
                raise SystemExit("%s is staged as item %s but WORKSHOP_ID is %r. Fix WORKSHOP_ID first: "
                                 "uploading the wrong one cannot be undone." % (INSTALLED, staged, WORKSHOP_ID))
        if INSTALLED.exists():
            shutil.rmtree(INSTALLED)
        shutil.copytree(BUILD, INSTALLED)
        validate(INSTALLED)
        print("uploader staging ->", INSTALLED)


if __name__ == "__main__":
    main()
