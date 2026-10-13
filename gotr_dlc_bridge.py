#!/usr/bin/env python3
"""Saints Row 2: Gentlemen of the Row + PC DLC compatibility bridge.

Builds a Juiced loose-file install of Gentlemen of the Row (GotR) v1.9.2 that runs
alongside the Kobraworks SR2 PC DLC, then optionally installs or removes it.

This script ships NO GotR, DLC or game files. It reads your own copies and writes
the bridge next to them.

  python gotr_dlc_bridge.py build   --game "<SR2 folder>" --gotr "<GotR folder or .rar>" [--clothing auto|keep|drop]
  python gotr_dlc_bridge.py install --game "<SR2 folder>"      (run as administrator if
  python gotr_dlc_bridge.py uninstall --game "<SR2 folder>"      the game is in Program Files)
  python gotr_dlc_bridge.py check   --game "<SR2 folder>"

See README.md for what the bridge changes and why.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

VERSION = "1.1.0"
DEFAULT_GAME = r"C:\Program Files\GOG Galaxy\Games\Saints Row 2"
HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
GOTR_DIRNAME = "Gentlemen_of_the_Row_Saints_Row_2_Super_Mod_v1.9.2"

# GotR files dropped in favour of newer versions shipped by the DLC / Juiced
EXCLUDE = {"dlc04.lua", "dlc04.cts", "dlc05.lua", "dlc05.cts", "em01.lua", "rn07.lua"}
PRELOADS = ("preload.tbl", "preload_anim.tbl")
EMPTY_OVERRIDES = ("dlc_customization_items.xtbl", "dlc_customization_outfits.xtbl",
                   "dlc_customization_stores.xtbl")
DLC_MISSIONS = ("dlc04", "dlc05")
LOOSE_LINES = ["mods/GotR/Optional", "mods/GotR"]
MARKER = "GOTR.txt"
LIMIT_ADJUSTER = "SR2.LimitAdjuster.asi"


def die(msg):
    sys.exit(f"ERROR: {msg}")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_file(root, name):
    for d, _, names in os.walk(root):
        for n in names:
            if n.lower() == name.lower():
                return os.path.join(d, n)
    return None


def check_game(game):
    if not os.path.isfile(os.path.join(game, "SR2_pc.exe")):
        die(f"SR2_pc.exe not found in {game!r} (use --game)")
    if not os.path.isfile(os.path.join(game, "juiced.ini")):
        die("Juiced Patch is not installed (juiced.ini missing). Install Juiced 9.2.0+ first.")
    dlc_missions = find_file(os.path.join(game, "DLC"), "sr2_city_missions_dlc.xtbl")
    if not dlc_missions:
        die("SR2 PC DLC is not installed (DLC folder / sr2_city_missions_dlc.xtbl missing).")
    if not os.path.isfile(os.path.join(game, "loose.txt")):
        die("loose.txt missing from the game folder; reinstall Juiced Patch.")


def has_limit_adjuster(game):
    """SR2 Limit Adjuster (Clippy95) raises the 1050 customization item cap, so the DLC
    clothing fits next to GotR. It is loaded by Ultimate ASI Loader (dinput8.dll)."""
    asi = any(os.path.isfile(os.path.join(game, d, LIMIT_ADJUSTER)) for d in ("", "scripts", "plugins"))
    return asi and os.path.isfile(os.path.join(game, "dinput8.dll"))


def clothing_mode(args):
    if args.clothing == "keep" and not has_limit_adjuster(args.game):
        die(f"--clothing keep needs SR2 Limit Adjuster ({LIMIT_ADJUSTER} + dinput8.dll) in the game folder")
    if args.clothing == "auto":
        return "keep" if has_limit_adjuster(args.game) else "drop"
    return args.clothing


def locate_gotr(path, workdir):
    """Accept the GotR .rar, the extracted top folder, or its optional_mod_stuff folder."""
    if os.path.isfile(path) and path.lower().endswith(".rar"):
        # Windows 10+ ships bsdtar (reads .rar) in System32; GNU tar from Git/MSYS does not
        win_tar = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe")
        tar = win_tar if os.path.isfile(win_tar) else shutil.which("bsdtar")
        if not tar:
            die("can't extract .rar here; extract it with 7-Zip/WinRAR and pass the folder")
        if subprocess.run([tar, "-xf", path, "-C", workdir]).returncode != 0:
            die("extracting the .rar failed; extract it yourself and pass the folder")
        path = workdir
    for cand in (path, os.path.join(path, GOTR_DIRNAME), os.path.join(path, "optional_mod_stuff")):
        root = cand if os.path.basename(cand) == "optional_mod_stuff" else os.path.join(cand, "optional_mod_stuff")
        if os.path.isdir(os.path.join(root, "modified")) and all(os.path.isfile(os.path.join(root, p)) for p in PRELOADS):
            return root
    die(f"GotR v1.9.2 not found under {path!r} (expected optional_mod_stuff/modified)")


def edit(path, fn):
    with open(path, "rb") as f:
        text = f.read().decode("utf-8", "surrogateescape")
    new = fn(text)
    if new == text:
        die(f"{os.path.basename(path)}: expected edit changed nothing (unexpected GotR version?)")
    with open(path, "wb") as f:
        f.write(new.encode("utf-8", "surrogateescape"))


def drop_missions(text):
    def keep(m):
        name = re.search(r"<Name>(.*?)</Name>", m.group(0), re.S).group(1).strip().lower()
        return "" if name in DLC_MISSIONS else m.group(0)
    out = re.sub(r"[ \t]*<Mission>.*?</Mission>[ \t]*\r?\n?", keep, text, flags=re.S)
    if re.search(r"<Name>\s*dlc0[45]\s*</Name>", out, re.I):
        die("dlc04/dlc05 mission rows still present")
    return out


def drop_navpoints(text):
    for m in DLC_MISSIONS:
        block = re.compile(r'\$Navpoint:\s*"mission_start_sr2_city_\$' + m + r'"\r?\n(?:\$[^\n]*\r?\n)*\r?\n?')
        text, n = block.subn("", text)
        if n != 1:
            die(f"navpoint {m}: expected 1 block, found {n}")
    return text


def drop_threads(text):
    text, n = re.subn(r'[ \t]*thread_new\("dlc0[45]_main"\)[^\r\n]*\r?\n', "", text)
    if n != 2:
        die(f"sr2_city.lua: expected 2 dlc thread_new lines, found {n}")
    return text


def cmd_build(args):
    check_game(args.game)
    mode = clothing_mode(args)
    with tempfile.TemporaryDirectory() as tmp:
        root = locate_gotr(args.gotr, tmp)
        modified = os.path.join(root, "modified")
        if os.path.exists(BUILD):
            shutil.rmtree(BUILD)
        out = os.path.join(BUILD, "mods", "GotR")
        os.makedirs(os.path.join(out, "Optional"))
        copied = 0
        for d, _, names in os.walk(modified):
            for n in names:
                if n.lower() in EXCLUDE:
                    continue
                dst = os.path.join(out, n)
                if os.path.exists(dst):
                    die(f"duplicate filename in GotR modified/: {n}")
                shutil.copy2(os.path.join(d, n), dst)
                copied += 1
        for n in PRELOADS:
            shutil.copy2(os.path.join(root, n), os.path.join(out, n))
    edit(os.path.join(out, "sr2_city_missions.xtbl"), drop_missions)
    edit(os.path.join(out, "mission_start_sr2_city.cts"), drop_navpoints)
    edit(os.path.join(out, "sr2_city.lua"), drop_threads)
    overrides = EMPTY_OVERRIDES if mode == "drop" else ()
    for n in overrides:
        with open(os.path.join(out, n), "w", newline="\r\n") as f:
            f.write("<root>\n<Table>\n</Table>\n</root>\n")
    with open(os.path.join(BUILD, MARKER), "w", newline="\r\n") as f:
        f.write(f"Gentlemen of the Row v1.9.2 + SR2 PC DLC bridge v{VERSION} (loose install).\n")
    manifest = {}
    for d, _, names in os.walk(BUILD):
        for n in names:
            p = os.path.join(d, n)
            manifest[os.path.relpath(p, BUILD).replace("\\", "/")] = sha256(p)
    with open(os.path.join(BUILD, "bridge_manifest.json"), "w") as f:
        json.dump({"version": VERSION, "clothing": mode, "files": manifest}, f, indent=1, sort_keys=True)
    print(f"built {copied} GotR files + {len(PRELOADS)} preload tables + {len(overrides)} overrides -> {BUILD}")
    if mode == "keep":
        print("DLC clothing: KEPT (SR2 Limit Adjuster found)")
    else:
        print("DLC clothing: DROPPED (install SR2 Limit Adjuster and rebuild to keep it)")
    print("next: python gotr_dlc_bridge.py install --game \"...\"  (as administrator for Program Files)")


def loose_lines(game):
    with open(os.path.join(game, "loose.txt"), encoding="utf-8") as f:
        return [l.rstrip("\r\n") for l in f if l.strip()]


def write_loose(game, lines):
    with open(os.path.join(game, "loose.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


def cmd_install(args):
    check_game(args.game)
    manifest_path = os.path.join(BUILD, "bridge_manifest.json")
    if not os.path.isfile(manifest_path):
        die("no build found; run the build command first")
    build = json.load(open(manifest_path))
    manifest = build["files"]
    if build.get("clothing", "drop") == "keep" and not has_limit_adjuster(args.game):
        die("this build keeps the DLC clothing, which crashes without SR2 Limit Adjuster. "
            "Install it, or rebuild with --clothing drop.")
    try:
        backup = os.path.join(args.game, "loose.txt.before_gotr_bridge")
        if not os.path.exists(backup):
            shutil.copy2(os.path.join(args.game, "loose.txt"), backup)
        for rel in manifest:
            if rel == "bridge_manifest.json":
                continue
            dst = os.path.join(args.game, *rel.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(BUILD, *rel.split("/")), dst)
        if build.get("clothing", "drop") == "keep":
            for n in EMPTY_OVERRIDES:  # left over from a previous "drop" install
                stale = os.path.join(args.game, "mods", "GotR", n)
                if os.path.isfile(stale):
                    os.remove(stale)
        os.makedirs(os.path.join(args.game, "mods", "GotR", "Optional"), exist_ok=True)
        lines = [l for l in loose_lines(args.game) if l.strip() not in LOOSE_LINES]
        write_loose(args.game, lines + LOOSE_LINES)
    except PermissionError as e:
        die(f"permission denied ({e.filename}). Re-run this command from an administrator terminal.")
    print("installed. Launch the game normally (GOG Galaxy or SR2_pc.exe).")
    cmd_check(args)


def cmd_uninstall(args):
    try:
        gotr = os.path.join(args.game, "mods", "GotR")
        if os.path.isdir(gotr):
            shutil.rmtree(gotr)
        marker = os.path.join(args.game, MARKER)
        if os.path.isfile(marker):
            os.remove(marker)
        write_loose(args.game, [l for l in loose_lines(args.game) if l.strip() not in LOOSE_LINES])
    except PermissionError as e:
        die(f"permission denied ({e.filename}). Re-run this command from an administrator terminal.")
    print("bridge removed (mods/GotR, GOTR.txt, loose.txt lines). Your saves were not touched.")


def cmd_check(args):
    problems = []
    gotr = os.path.join(args.game, "mods", "GotR")
    manifest_path = os.path.join(BUILD, "bridge_manifest.json")
    mode = "drop"
    if os.path.isfile(manifest_path):
        build = json.load(open(manifest_path))
        mode = build.get("clothing", "drop")
        for rel, digest in build["files"].items():
            p = os.path.join(args.game, *rel.split("/"))
            if rel.startswith("mods/GotR/") and (not os.path.isfile(p) or sha256(p) != digest):
                problems.append(f"{rel} missing or modified")
    if loose_lines(args.game)[-2:] != LOOSE_LINES:
        problems.append("loose.txt does not end with the GotR lines")
    missions = os.path.join(gotr, "sr2_city_missions.xtbl")
    if os.path.isfile(missions):
        names = [(r.findtext("Name") or "").strip().lower() for r in ET.parse(missions).getroot().find("Table")]
        if {"dlc04", "dlc05"} & set(names):
            problems.append("GotR mission table still registers dlc04/dlc05 (crash #2)")
    for n in EMPTY_OVERRIDES:
        p = os.path.join(gotr, n)
        if mode == "drop" and (not os.path.isfile(p) or len(ET.parse(p).getroot().find("Table"))):
            problems.append(f"{n} override missing or not empty (crash #1)")
        if mode == "keep" and os.path.isfile(p):
            problems.append(f"{n} override present, so the DLC clothing is still hidden")
    if mode == "keep" and not has_limit_adjuster(args.game):
        problems.append("DLC clothing kept but SR2 Limit Adjuster is missing (crash #1)")
    for n in EXCLUDE:
        if os.path.exists(os.path.join(gotr, n)):
            problems.append(f"{n} should not be in mods/GotR")
    if problems:
        print("CHECK FAILED:\n  " + "\n  ".join(problems))
        sys.exit(1)
    print(f"CHECK OK: bridge installed and intact (DLC clothing: {'kept' if mode == 'keep' else 'dropped'})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "install", "uninstall", "check"])
    ap.add_argument("--game", default=DEFAULT_GAME, help="Saints Row 2 folder (contains SR2_pc.exe)")
    ap.add_argument("--gotr", help="GotR v1.9.2 .rar or extracted folder (build only)")
    ap.add_argument("--clothing", choices=["auto", "keep", "drop"], default="auto",
                    help="DLC clothing: keep needs SR2 Limit Adjuster; auto detects it (build only)")
    args = ap.parse_args()
    if args.command == "build" and not args.gotr:
        ap.error("build needs --gotr")
    {"build": cmd_build, "install": cmd_install, "uninstall": cmd_uninstall, "check": cmd_check}[args.command](args)


if __name__ == "__main__":
    main()
