"""Every language the mod is translated into, held against the English.

    python tests/test_translations.py            # every language folder
    python tests/test_translations.py ES FR      # only these
    python tests/test_translations.py --source   # print what a translator translates (JSON)

English (Translate/EN) is the source. The game falls back to it key by key
(Translator.forLanguageStack: the language, its base, then the default), so
a language may leave a key out and still work -- which is how the dev
build's own lines stay English, on purpose. Everything else must be there:

  * a folder is one of the game's own languages, and holds only files EN has;
  * every file is UTF-8 JSON with no BOM, and holds only keys EN's file has;
  * every key a player can see is translated, and none is empty;
  * none of the dev build's keys are (nobody but the author reads them);
  * each text has exactly EN's placeholders (%1, %2), and no literal %
    (DEV_GUIDE, "A translation's %1 is a format placeholder");
  * a journal's page has EN's number of lines: the page is drawn line by line.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TR = os.path.join(ROOT, "Sewars", "42", "media", "lua", "shared", "Translate")
PZ_TR = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media\lua\shared\Translate"

# Every language the mod ships. A language taken off this list fails the
# test rather than quietly going missing from a release.
LANGS = ["AR", "CA", "CH", "CN", "CS", "DA", "DE", "ES", "ES_CL", "ES_MX", "FI", "FR", "HU", "ID", "IT", "JP",
         "KO", "NL", "NO", "PL", "PT", "PTBR", "RO", "RU", "TH", "TR", "UA"]

FAILS = []


def check(cond, what):
    if not cond:
        print("  FAIL  " + what)
        FAILS.append(what)
    return cond


def is_dev(key):
    """The dev build's own lines: its menu and what it says. English only."""
    return key.startswith("ContextMenu_SEW_Dev") or key.startswith("IGUI_SEW_Dev")


def english():
    out = {}
    for f in sorted(glob.glob(os.path.join(TR, "EN", "*.json"))):
        out[os.path.basename(f)] = json.load(open(f, encoding="utf-8"))
    return out


def source():
    """What a translator is given: every file's player-facing keys, in order."""
    return {name: {k: v for k, v in keys.items() if not is_dev(k)} for name, keys in english().items()}


def placeholders(text):
    return sorted(set(re.findall(r"%(\d)", text)))


def language(lang, en):
    d = os.path.join(TR, lang)
    if not check(os.path.isdir(d), "%s: the folder is there" % lang):
        return 0
    if os.path.isdir(PZ_TR):
        check(os.path.isdir(os.path.join(PZ_TR, lang)), "%s is one of the game's languages" % lang)
    files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(d, "*")))
    check(not [f for f in files if f not in en], "%s holds only files EN has (%s)" % (lang, [f for f in files if f not in en]))
    n = 0
    for name, keys in en.items():
        path = os.path.join(d, name)
        if not check(os.path.isfile(path), "%s/%s is there" % (lang, name)):
            continue
        raw = open(path, "rb").read()
        check(not raw.startswith(b"\xef\xbb\xbf"), "%s/%s has no BOM" % (lang, name))
        try:
            got = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            check(False, "%s/%s is UTF-8 JSON (%s)" % (lang, name, e))
            continue
        strange = [k for k in got if k not in keys]
        check(not strange, "%s/%s holds only EN's keys (%s)" % (lang, name, strange))
        dev = [k for k in got if is_dev(k)]
        check(not dev, "%s/%s leaves the dev build's lines in English (%s)" % (lang, name, dev))
        missing = [k for k in keys if not is_dev(k) and k not in got]
        check(not missing, "%s/%s translates every key a player sees (%d missing: %s)"
              % (lang, name, len(missing), missing[:6]))
        for k, v in got.items():
            if k not in keys:
                continue
            n += 1
            if not check(isinstance(v, str) and v.strip() != "", "%s %s is not empty" % (lang, k)):
                continue
            check(placeholders(v) == placeholders(keys[k]),
                  "%s %s has EN's placeholders (%s, not %s)" % (lang, k, placeholders(keys[k]), placeholders(v)))
            check(not re.search(r"%(?!\d)", v) and not re.search(r"%\d%", v),
                  "%s %s has no literal %% (the translator breaks on it)" % (lang, k))
            if k.endswith("_Body"):
                check(v.count("\n") == keys[k].count("\n"),
                      "%s %s has EN's %d line breaks (not %d)" % (lang, k, keys[k].count("\n"), v.count("\n")))
    return n


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--source" in sys.argv:
        sys.stdout.reconfigure(encoding="utf-8")
        json.dump(source(), sys.stdout, ensure_ascii=False, indent=4)
        return
    en = english()
    total = sum(len([k for k in keys if not is_dev(k)]) for keys in en.values())
    check(len(en) >= 6 and total >= 200, "the English is read (%d files, %d keys a player sees)" % (len(en), total))
    langs = args or LANGS
    if not args:
        there = sorted(os.path.basename(p) for p in glob.glob(os.path.join(TR, "*")) if os.path.isdir(p))
        check(there == sorted(LANGS + ["EN"]), "the language folders are EN and the %d listed (%s)"
              % (len(LANGS), sorted(set(there) ^ set(LANGS + ["EN"]))))
    for lang in langs:
        before = len(FAILS)
        n = language(lang, en)
        if len(FAILS) == before:
            print("  ok    %s: %d texts, every one EN has, placeholders and line counts alike" % (lang, n))
    print()
    if FAILS:
        print("%d FAILED" % len(FAILS))
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
