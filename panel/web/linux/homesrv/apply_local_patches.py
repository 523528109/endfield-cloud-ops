#!/usr/bin/env python3
"""Re-apply local MaaEnd pipeline compatibility patches after an update.

The 2026-10 cloud UI uses an outlined yellow menu button. MaaEnd v2.35.0's
CheckMenuListColor expects a much larger filled color area, so InMenuList
fails even though its two OCR checks succeed. Removing that color assertion
lets SceneAnyEnterWorld leave the menu and keeps the daily tasks running.

The patch is idempotent and only touches InMenuList. The original
nodes.json is copied to backups/ before the first rewrite.
"""
import json
import os
import shutil
import sys
import time

ROOT = os.environ.get("MAAEND_ROOT", os.path.expanduser("~/maaend"))
NODES = os.path.join(ROOT, "resource", "pipeline", "nodes.json")
BACKUPS = os.path.join(ROOT, "backups")


def main():
    try:
        with open(NODES, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print("menu patch: cannot read %s: %s" % (NODES, exc))
        return 1

    node = data.get("InMenuList") or {}
    all_of = node.get("all_of") or []
    if "CheckMenuListColor" not in all_of:
        print("menu patch: not needed")
        return 0

    os.makedirs(BACKUPS, exist_ok=True)
    backup = os.path.join(
        BACKUPS, "nodes.json.pre-menu-patch-" + time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(NODES, backup)
    node["all_of"] = [name for name in all_of if name != "CheckMenuListColor"]
    with open(NODES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("menu patch: removed CheckMenuListColor from InMenuList")
    print("menu patch: backup %s" % backup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
