#!/usr/bin/env python3
"""Regenerate the panel task catalog (with MXU option definitions) from MaaEnd."""
import json
import os
import sys
import time

MAA_ROOT = os.environ.get("MAAEND_ROOT", "/home/maa/maaend")
PANEL_DIR = os.environ.get("MAAEND_WEBUI_DIR", os.environ.get("MAAEND_HOME", "/home/maa") + "/maaend-webui")
CATALOG = os.path.join(PANEL_DIR, "tasks.json")
CONFIG = os.path.join(MAA_ROOT, "config", "mxu-MaaEnd.json")
LOCALE = os.path.join(MAA_ROOT, "locales", "interface", "zh_cn.json")
QUEUE_INSTANCE = "panel-queue"

os.environ["MAAEND_ROOT"] = MAA_ROOT
sys.path.insert(0, os.path.join(MAA_ROOT, "web", "linux"))
import resolve_preset as rp  # noqa: E402


def load_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def dump_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


INTERFACE = load_json(os.path.join(MAA_ROOT, "interface.json"), {})
LOCALE_DATA = load_json(LOCALE, {})
TASKS, OPTIONS = rp.load_all()
CONFIG_DATA = load_json(CONFIG, {"instances": []})
VERSION = INTERFACE.get("version") or "unknown"


def tr(value, fallback=""):
    if not isinstance(value, str) or not value:
        return fallback
    if value.startswith("$"):
        key = value[1:]
        text = LOCALE_DATA.get(key)
        if isinstance(text, str) and text:
            return text
        return key.split(".")[-1]
    return value


def build_option(key, seen):
    opt = OPTIONS.get(key) or {}
    node = {
        "key": key,
        "type": opt.get("type") or "unknown",
        "label": tr(opt.get("label"), key),
        "description": tr(opt.get("description"), ""),
        "default": opt.get("default_case"),
        "cases": [],
        "inputs": [],
    }
    for case in opt.get("cases") or []:
        cname = case.get("name")
        child = {
            "name": cname,
            "label": tr(case.get("label"), cname or ""),
            "description": tr(case.get("description"), ""),
            "options": [],
        }
        for sub in case.get("option") or []:
            if sub in seen:
                child["options"].append({"key": sub, "type": "cycle", "label": sub, "cases": [], "inputs": []})
            else:
                child["options"].append(build_option(sub, seen | {sub}))
        node["cases"].append(child)
    for inp in opt.get("inputs") or []:
        node["inputs"].append({
            "name": inp.get("name"),
            "label": tr(inp.get("label"), inp.get("name") or ""),
            "description": tr(inp.get("description"), ""),
            "default": inp.get("default"),
            "pipeline_type": inp.get("pipeline_type") or "string",
            "verify": inp.get("verify") or "",
        })
    return node


# current values: panel-queue first, then webcloud-full
def instance_tasks(inst_id):
    for inst in CONFIG_DATA.get("instances") or []:
        if inst.get("id") == inst_id:
            return inst, inst.get("tasks") or []
    return None, []


queue_inst, queue_tasks = instance_tasks(QUEUE_INSTANCE)
daily_inst, daily_tasks = instance_tasks("webcloud-full")
queue_values = {t.get("taskName"): t.get("optionValues") or {} for t in queue_tasks}
daily_values = {t.get("taskName"): t.get("optionValues") or {} for t in daily_tasks}

if queue_inst is None:
    queue_inst = {
        "id": QUEUE_INSTANCE,
        "name": "面板待选队列",
        "controllerName": "Linux-Wlroots",
        "resourceName": "官服-网页端",
        "tasks": [],
    }
    CONFIG_DATA.setdefault("instances", []).append(queue_inst)
    queue_tasks = queue_inst["tasks"]

catalog = []
new_queue_tasks = []
for name in sorted(TASKS):
    task = TASKS[name]
    opts = []
    for key in task.get("option") or []:
        if key in OPTIONS:
            opts.append(build_option(key, {key}))
    values = queue_values.get(name)
    if values is None:
        values = daily_values.get(name) or {}
    groups = task.get("group") or []
    controllers = task.get("controller") or task.get("controllers") or []
    catalog.append({
        "name": name,
        "entry": task.get("entry"),
        "label": tr(task.get("label"), name),
        "description": tr(task.get("description"), ""),
        "group": groups[0] if groups else "other",
        "controllers": controllers,
        "options": opts,
        "optionValues": values,
    })
    new_queue_tasks.append({
        "taskName": name,
        "enabled": True,
        "optionValues": values,
    })

# Preserve any custom entries not present upstream at the end.
known = {t["taskName"] for t in new_queue_tasks}
for old in queue_tasks:
    if old.get("taskName") not in known:
        new_queue_tasks.append(old)
queue_inst["tasks"] = new_queue_tasks

dump_json(CONFIG, CONFIG_DATA)
dump_json(CATALOG, {
    "version": VERSION,
    "generated": int(time.time()),
    "queue_instance": QUEUE_INSTANCE,
    "tasks": catalog,
})
print("catalog: %s tasks, %s options, version %s" % (len(catalog), len(OPTIONS), VERSION))
