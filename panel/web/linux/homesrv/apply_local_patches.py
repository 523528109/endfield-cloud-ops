#!/usr/bin/env python3
"""Re-apply local MaaEnd pipeline compatibility patches after an update.

The 2026-10 cloud UI uses an outlined yellow menu button. MaaEnd v2.35.0's
CheckMenuListColor expects a much larger filled color area, so InMenuList
fails even though its two OCR checks succeed. Removing that color assertion
lets SceneAnyEnterWorld leave the menu and keeps the daily tasks running.

It also adds small "nothing to do" skip nodes for the current game/account
states (shop refresh exhausted, delivery equipment cooling, outpost limit,
purchase limit). These stop a single task instead of idling until the cloud
session expires.

The patch is idempotent. The original nodes.json is copied to backups/
before the first rewrite.
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

    changed = False
    node = data.get("InMenuList") or {}
    all_of = node.get("all_of") or []
    if "CheckMenuListColor" in all_of:
        node["all_of"] = [name for name in all_of if name != "CheckMenuListColor"]
        changed = True
        print("menu patch: removed CheckMenuListColor from InMenuList")

    # Current game screens expose several "nothing to do" states that make
    # MaaEnd idle until the cloud session expires. Stop the task cleanly.
    skips = {
        "DeliveryJobsEquipmentCooling": {
            "desc": "装箱设备冷却中，跳过本次送货任务",
            "recognition": "OCR",
            "expected": ["装箱设备冷却中", "裝箱設備冷卻中", "冷却中", "冷卻中"],
            "roi": [0, 500, 1280, 220],
            "action": "StopTask",
        },
        "CreditShoppingRefreshUsedUpSkip": {
            "desc": "今日刷新次数已用完，跳过信用购物",
            "recognition": "OCR",
            "expected": ["今日刷新次数已用完", "刷新次数已用完", "用完"],
            "roi": [850, 550, 430, 170],
            "action": "StopTask",
        },
        "OutpostTradingDevelopmentLimitSkip": {
            "desc": "据点发展值已达上限，跳过本次据点交易",
            "recognition": "OCR",
            "expected": ["据点发展值已达当前据点上限", "据点发展值已达上限",
                         "已达当前据点上限"],
            "roi": [760, 600, 520, 120],
            "action": "StopTask",
        },
        "AutoStockPurchaseLimitSkip": {
            "desc": "剩余可购买数量为 0，跳过本次囤货/稳定物资任务",
            "recognition": "OCR",
            "expected": ["剩余可购买数量\\s*0/400", "剩余可购买数量0/400",
                         "20小时后.*200", "20小时后\\+200"],
            "roi": [0, 120, 700, 80],
            "action": "StopTask",
        },
    }
    skip_targets = {
        "DeliveryJobsLoop": ["DeliveryJobsEquipmentCooling"],
        "CreditShoppingMain": ["CreditShoppingRefreshUsedUpSkip"],
        "CreditShoppingInShop": ["CreditShoppingRefreshUsedUpSkip"],
        "CreditShoppingShopping": ["CreditShoppingRefreshUsedUpSkip"],
        "OutpostTradingAtSell": ["OutpostTradingDevelopmentLimitSkip"],
        "AutoStockpileStart": ["AutoStockPurchaseLimitSkip"],
        "AutoStockStapleMain": ["AutoStockPurchaseLimitSkip"],
    }
    for name, spec in skips.items():
        if data.get(name) != spec:
            data[name] = spec
            changed = True
            print("skip patch: added %s" % name)
    for parent, children in skip_targets.items():
        target = data.get(parent)
        if not target:
            continue
        next_list = target.setdefault("next", [])
        for child in children:
            if child not in next_list:
                next_list.insert(0, child)
                changed = True
                print("skip patch: %s -> %s" % (parent, child))

    if not changed:
        print("local patches: not needed")
        return 0

    os.makedirs(BACKUPS, exist_ok=True)
    backup = os.path.join(
        BACKUPS, "nodes.json.pre-local-patches-" + time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(NODES, backup)
    with open(NODES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("local patches: backup %s" % backup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
