#!/usr/bin/env python3
"""MaaEnd cloud-Endfield web console.

Serves a static Endfield-style dashboard and a small JSON API.
No third-party web framework; only websocket-client + Pillow for live screenshots.
"""
import base64
import glob
import hashlib
import hmac
import http.client
import io
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timedelta, time as dtime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import websocket
from PIL import Image

BASE = os.environ.get("MAAEND_HOME", "/home/maa")
ROOT = os.environ.get("MAAEND_ROOT", BASE + "/maaend")
WEB = ROOT + "/web/linux"
PANEL_DIR = BASE + "/maaend-webui"
DATA_DIR = os.environ.get("MAAEND_DATA_DIR", PANEL_DIR)
STATIC = PANEL_DIR + "/static"
PY = BASE + "/venv/bin/python"
CDP = WEB + "/cdp_tool.py"
RUNNER = WEB + "/homesrv/daily_run_homesrv.sh"
LOGS = [ROOT + "/daily.log", BASE + "/full_daily.log", BASE + "/webui-run.log"]
SHOT = DATA_DIR + "/shot.jpg"
RAW = DATA_DIR + "/raw.png"
TOKEN_FILE = DATA_DIR + "/token"
AUTH_FILE = DATA_DIR + "/auth.conf"
WAYVNC_CFG_DIR = BASE + "/.config/wayvnc"
WAYVNC_CFG = WAYVNC_CFG_DIR + "/config"
VNC_TOKEN_FILE = DATA_DIR + "/vnc-token"
NOVNC_DIR = PANEL_DIR + "/novnc"
PROGRESS_FILE = DATA_DIR + "/progress.json"
PORT = int(os.environ.get("WEBUI_PORT", "8787"))
BIND = os.environ.get("WEBUI_BIND", "0.0.0.0")
FULL_DAILY = ["WebStartGame", "VisitFriends", "DijiangRewards", "CreditShoppingN2",
              "DeliveryJobs", "SellProduct", "AutoStockpile", "AutoStockStaple",
              "GearAssembly", "WeaponUpgrade", "DailyRewards"]
TASKS = list(FULL_DAILY)
_starting = {"tasks": [], "at": 0}
CATALOG_FILE = DATA_DIR + "/tasks.json"
MAA_ROOT = ROOT
MAA_CONFIG = MAA_ROOT + "/config/mxu-MaaEnd.json"
MAA_INTERFACE = MAA_ROOT + "/interface.json"
MAA_UPDATE = MAA_ROOT + "/web/linux/homesrv/auto_update.sh"
MAA_UPGRADE_LOG = MAA_ROOT + "/upgrade.log"
MAA_QUEUE_INSTANCE = "panel-queue"
MAA_PRESET_DIR = MAA_ROOT + "/tasks/preset"
MAA_LOCALE = MAA_ROOT + "/locales/interface/zh_cn.json"
STOP_MARK = ROOT + "/.manual_stop"
PRESET_ORDER = ["DailyFull", "QuickDaily", "RealtimeAssist", "AutoEssence"]
PY3 = BASE + "/venv/bin/python"
SCHEDULE_FILE = DATA_DIR + "/schedule.json"
USERS_FILE = DATA_DIR + "/users.json"
SESSION_COOKIE = "ef_sid"
SESSION_TTL = 7 * 86400
GAME_ACCOUNTS_FILE = DATA_DIR + "/game-accounts.json"
ACTIVE_PROFILE_FILE = DATA_DIR + "/active-profile"
DEFAULT_PROFILE = BASE + "/.config/endfield-web"
GAME_PROFILE_DIR = BASE + "/.config/endfield-accounts"
CLOUD_URL = "https://endfield.hypergryph.com/cloud"
SCHEDULE_MARK = "# MAAEND-SCHEDULE"
DEFAULT_TIMES = ["04:00", "16:00"]
VNC_PORT = 6080
VNC_COOKIE = "ef_vnc"
VNC_TTL = 12 * 3600
_log_cache = {"key": None, "lines": []}
_log_cache_lock = threading.Lock()
_users_cache = {"key": None, "users": []}
_users_cache_lock = threading.Lock()
_vnc_access = {}
_vnc_access_lock = threading.Lock()


def load_catalog():
    try:
        data = json.load(open(CATALOG_FILE, encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("tasks") or []
        return data if isinstance(data, list) else []
    except Exception:
        return []


CATALOG = load_catalog()
META = {t.get("name"): t for t in CATALOG if t.get("name")}
_maa_config_lock = threading.Lock()
_maa_check_cache = {"ts": 0, "data": None}
_maa_update = {"state": "idle", "started": 0, "finished": 0, "before": "",
               "after": "", "message": "", "output": ""}
_maa_update_lock = threading.Lock()


def reload_catalog():
    global CATALOG, META
    CATALOG = load_catalog()
    META = {t.get("name"): t for t in CATALOG if t.get("name")}


def load_maa_config():
    try:
        with open(MAA_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"instances": []}
    except Exception:
        return {"instances": []}


def save_maa_config(data):
    with _maa_config_lock:
        tmp = MAA_CONFIG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, MAA_CONFIG)


def _find_instance(data, instance_id):
    for inst in data.get("instances") or []:
        if inst.get("id") == instance_id:
            return inst
    return None


def maa_queue_values():
    data = load_maa_config()
    inst = _find_instance(data, MAA_QUEUE_INSTANCE)
    out = {}
    for task in (inst or {}).get("tasks") or []:
        name = task.get("taskName")
        if name:
            out[name] = task.get("optionValues") or {}
    return out


def catalog_payload():
    catalog = load_catalog()
    values = maa_queue_values()
    for task in catalog:
        if isinstance(task, dict) and task.get("name"):
            task["optionValues"] = values.get(task["name"], task.get("optionValues") or {})
    return catalog


def _maa_locale():
    try:
        with open(MAA_LOCALE, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def _maa_text(value, locale):
    if isinstance(value, str) and value.startswith("$"):
        return locale.get(value[1:], value)
    return value or ""


def maa_presets():
    """MaaEnd 自带的 DailyFull / QuickDaily / RealtimeAssist，加上基质刷取场景。"""
    locale = _maa_locale()
    found = {}
    for path in sorted(glob.glob(MAA_PRESET_DIR + "/*.json")):
        try:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception:
            continue
        for preset in data.get("preset") or []:
            if not isinstance(preset, dict) or not preset.get("name"):
                continue
            tasks = [t.get("name") for t in preset.get("task") or []
                     if isinstance(t, dict) and t.get("name")]
            name = preset["name"]
            desc = _maa_text(preset.get("description"), locale)
            if name == "RealtimeAssist":
                desc += " 长时运行，单个任务最长 2 小时；期间不要叠加其他任务。"
            notes = {
                "DailyFull": f"将执行 {len(tasks)} 项，启动游戏由 runner 自动预检。",
                "QuickDaily": f"只做 {len(tasks)} 项核心领奖，适合时间紧张时执行。",
                "RealtimeAssist": "长时任务，最长 2 小时；期间不要叠加其他任务。",
            }
            found[name] = {
                "id": "preset:" + name,
                "name": name,
                "label": _maa_text(preset.get("label"), locale) or name,
                "description": desc,
                "note": notes.get(name, desc),
                "tasks": tasks,
                "count": len(tasks),
                "kind": "maa",
                "scheduled": False,
                "long": name in ("RealtimeAssist", "AutoEssence"),
            }

    # README 的第四套场景「基质养成」在 MaaEnd 里没有 preset 文件，
    # 用 AutoEssence 任务补一套等价入口（选项沿用任务库里的默认值）。
    if "AutoEssence" not in found:
        found["AutoEssence"] = {
            "id": "preset:AutoEssence",
            "name": "AutoEssence",
            "label": _maa_text("$task.AutoEssence.label", locale) or "基质刷取",
            "description": "按任务库里的 AutoEssence 设置刷取基质，默认使用 Maa 任务默认值；长时任务，最长 1 小时。",
            "note": "长时任务，最长 1 小时；选项沿用任务库里的设置。",
            "tasks": ["AutoEssence"],
            "count": 1,
            "kind": "maa",
            "scheduled": False,
            "long": True,
        }

    found["webcloud-full"] = {
        "id": "webcloud-full",
        "name": "webcloud-full",
        "label": "定时任务",
        "description": "04:00 / 16:00 定时任务使用的 11 项；也可以手动执行。",
        "note": "将执行 11 项；跑完自动收尾，单项失败会继续下一项。",
        "tasks": list(FULL_DAILY),
        "count": len(FULL_DAILY),
        "kind": "panel",
        "scheduled": True,
        "long": False,
    }
    items = [found[name] for name in PRESET_ORDER if name in found]
    items.append(found["webcloud-full"])
    return items


def maa_current_version():
    try:
        with open(MAA_INTERFACE, encoding="utf-8-sig") as f:
            return (json.load(f) or {}).get("version") or "unknown"
    except Exception:
        return "unknown"


def maa_log_tail(lines=30):
    try:
        with open(MAA_UPGRADE_LOG, "rb") as f:
            f.seek(max(0, os.path.getsize(MAA_UPGRADE_LOG) - 60000))
            raw = f.read().decode("utf-8", "replace")
        return raw.splitlines()[-lines:]
    except Exception:
        return []


def maa_check_update(force=False):
    now = time.time()
    if not force and _maa_check_cache["data"] and now - _maa_check_cache["ts"] < 600:
        return _maa_check_cache["data"]
    env = os.environ.copy()
    env["HOME"] = BASE
    try:
        proc = subprocess.run(["bash", MAA_UPDATE, "--check"], cwd=MAA_ROOT, env=env,
                              capture_output=True, text=True, timeout=120)
    except Exception as e:
        data = {"ok": False, "current": maa_current_version(), "latest": "",
                "package": "", "error": str(e), "checked": int(time.time())}
        _maa_check_cache.update({"ts": now, "data": data})
        return data
    current = latest = package = ""
    for line in (proc.stdout or "").splitlines():
        if line.startswith("当前:"):
            current = line.split(":", 1)[1].strip()
        elif line.startswith("最新:"):
            latest = line.split(":", 1)[1].strip()
        elif line.startswith("包:"):
            package = line.split(":", 1)[1].strip()
    data = {"ok": bool(latest), "current": current or maa_current_version(),
            "latest": latest, "package": package, "checked": int(time.time()),
            "error": "" if latest else ((proc.stderr or "").strip()[-300:] or "检查失败")}
    _maa_check_cache.update({"ts": now, "data": data})
    return data


def start_maa_update():
    if busy() or takeover_active():
        return False, "Maa 正在运行，先停止任务/接管再更新"
    with _maa_update_lock:
        if _maa_update.get("state") == "running":
            return False, "更新正在进行"
        _maa_update.update({"state": "running", "started": time.time(),
                            "finished": 0, "before": maa_current_version(),
                            "after": "", "message": "正在检查/下载/替换 Maa…",
                            "output": ""})
    threading.Thread(target=_maa_update_worker, daemon=True).start()
    return True, "started"


def _maa_update_worker():
    env = os.environ.copy()
    env["HOME"] = BASE
    before = maa_current_version()
    output = ""
    try:
        proc = subprocess.run(["bash", MAA_UPDATE], cwd=MAA_ROOT, env=env,
                              capture_output=True, text=True, timeout=3600)
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    except Exception as e:
        output = "update failed: %s" % e
    after = maa_current_version()
    message = ""
    state = "done"
    if after and after != before:
        message = "已更新 %s → %s" % (before, after)
        try:
            env["MAAEND_DATA_DIR"] = DATA_DIR
            gen = subprocess.run([PY3, PANEL_DIR + "/gen_catalog.py"],
                                 cwd=PANEL_DIR, env=env,
                                 capture_output=True, text=True, timeout=300)
            output += "\n[catalog]\n" + (gen.stdout or "") + (gen.stderr or "")
            reload_catalog()
            _maa_check_cache.update({"ts": 0, "data": None})
        except Exception as e:
            message += "；任务库重建失败：%s" % e
    else:
        tail = "\n".join(maa_log_tail(12))
        if "已是最新" in tail or "无需更新" in tail:
            message = "已是最新 %s" % before
        elif "有任务正在运行" in tail:
            state = "error"
            message = "Maa 正在运行，更新被跳过"
        else:
            state = "error"
            message = "更新未完成，查看日志"
    with _maa_update_lock:
        _maa_update.update({"state": state, "finished": time.time(),
                            "before": before, "after": after,
                            "message": message, "output": output[-4000:]})


os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STATIC, exist_ok=True)
if os.path.exists(TOKEN_FILE):
    TOKEN = open(TOKEN_FILE).read().strip()
else:
    TOKEN = secrets.token_urlsafe(24)
    with open(TOKEN_FILE, "w") as f:
        f.write(TOKEN)
    os.chmod(TOKEN_FILE, 0o600)


def auth_enabled():
    try:
        return open(AUTH_FILE).read().strip() == "1"
    except Exception:
        return False


def set_auth(enabled):
    with open(AUTH_FILE, "w") as f:
        f.write("1" if enabled else "0")


_sessions = {}
_sessions_lock = threading.Lock()
_login_fail = {}
_login_fail_lock = threading.Lock()


def load_users():
    # status polling hits this path every few seconds; cache by mtime
    try:
        st = os.stat(USERS_FILE)
        key = (st.st_mtime_ns, st.st_size)
    except Exception:
        return []
    with _users_cache_lock:
        if _users_cache["key"] == key:
            return _users_cache["users"]
    try:
        data = json.load(open(USERS_FILE, encoding="utf-8"))
        users = data.get("users") if isinstance(data, dict) else []
        users = [u for u in users if isinstance(u, dict) and u.get("username")]
    except Exception:
        users = []
    with _users_cache_lock:
        _users_cache["key"] = key
        _users_cache["users"] = users
    return users


def save_users(users):
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, USERS_FILE)
    with _users_cache_lock:
        _users_cache["key"] = None
        _users_cache["users"] = []


def hash_password(password):
    salt = os.urandom(16)
    iterations = 260000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {"algo": "pbkdf2_sha256", "iterations": iterations,
            "salt": salt.hex(), "hash": digest.hex()}


def verify_password(user, password):
    try:
        rec = user.get("password") or {}
        salt = bytes.fromhex(rec["salt"])
        expected = bytes.fromhex(rec["hash"])
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                                    int(rec.get("iterations") or 260000))
        return secrets.compare_digest(digest, expected)
    except Exception:
        return False


def find_user(username):
    for user in load_users():
        if user.get("username") == username:
            return user
    return None


def accounts_exist():
    return bool(load_users())


def valid_username(username):
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]{3,24}", username or ""))


def valid_password(password):
    return isinstance(password, str) and len(password) >= 8 and len(password) <= 128


def create_user(username, password, role="user"):
    username = (username or "").strip()
    if not valid_username(username):
        return False, "用户名 3-24 位，仅字母数字 _ . -"
    if not valid_password(password):
        return False, "密码至少 8 位"
    users = load_users()
    if any(u.get("username") == username for u in users):
        return False, "用户名已存在"
    user = {"username": username, "role": role if role in ("admin", "user") else "user",
            "created": int(time.time()), "password": hash_password(password)}
    users.append(user)
    save_users(users)
    return True, "created"


def cookie_value(handler, name):
    raw = handler.headers.get("Cookie") or ""
    for part in raw.split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""


def session_principal(handler):
    sid = cookie_value(handler, SESSION_COOKIE)
    if not sid:
        return None
    now = time.time()
    with _sessions_lock:
        rec = _sessions.get(sid)
        if not rec:
            return None
        if rec.get("exp", 0) <= now:
            _sessions.pop(sid, None)
            return None
    user = find_user(rec.get("username"))
    if not user:
        return None
    return {"username": user["username"], "role": user.get("role", "user"),
            "sid": sid, "token": False}


def token_principal(handler):
    if auth_enabled() and secrets.compare_digest(handler._tok(), TOKEN):
        return {"username": "token", "role": "admin", "sid": None, "token": True}
    return None


def principal(handler):
    return session_principal(handler) or token_principal(handler)


def create_session(username):
    sid = secrets.token_urlsafe(32)
    with _sessions_lock:
        _sessions[sid] = {"username": username, "exp": time.time() + SESSION_TTL}
    return sid


def set_session_cookie(handler, sid):
    return {"Set-Cookie": "%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d" % (
        SESSION_COOKIE, sid, SESSION_TTL)}


def clear_session_cookie(handler):
    sid = cookie_value(handler, SESSION_COOKIE)
    if sid:
        with _sessions_lock:
            _sessions.pop(sid, None)
    return {"Set-Cookie": "%s=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0" % SESSION_COOKIE}


def grant_vnc_access():
    """Short-lived ticket so the noVNC page and its websocket can load."""
    now = time.time()
    with _vnc_access_lock:
        for key, exp in list(_vnc_access.items()):
            if exp <= now:
                _vnc_access.pop(key, None)
        ticket = secrets.token_urlsafe(24)
        _vnc_access[ticket] = now + VNC_TTL
    return ticket


def vnc_access_ok(handler):
    if session_principal(handler) or token_principal(handler):
        return True
    ticket = cookie_value(handler, VNC_COOKIE)
    if not ticket:
        return False
    now = time.time()
    with _vnc_access_lock:
        exp = _vnc_access.get(ticket)
        if exp and exp > now:
            return True
        _vnc_access.pop(ticket, None)
    return False


def vnc_cookie_header():
    return "%s=%s; Path=/vnc/; HttpOnly; SameSite=Lax; Max-Age=%d" % (
        VNC_COOKIE, grant_vnc_access(), VNC_TTL)


def normalize_times(times):
    out = []
    for raw in times or []:
        if not isinstance(raw, str):
            continue
        m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", raw.strip())
        if m:
            out.append("%02d:%s" % (int(m.group(1)), m.group(2)))
    return sorted(set(out))


def load_schedule():
    data = {}
    try:
        data = json.load(open(SCHEDULE_FILE, encoding="utf-8"))
    except Exception:
        pass
    enabled = bool(data.get("enabled", True))
    times = normalize_times(data.get("times")) or list(DEFAULT_TIMES)
    return {"enabled": enabled, "times": times}


def next_schedule_run(times):
    now = datetime.now()
    best = None
    for add in range(0, 8):
        day = (now + timedelta(days=add)).date()
        for raw in times:
            hh, mm = raw.split(":")
            cand = datetime.combine(day, dtime(int(hh), int(mm)))
            if cand > now and (best is None or cand < best):
                best = cand
    return best.strftime("%Y-%m-%d %H:%M") if best else None


def schedule_payload():
    s = load_schedule()
    s["next"] = next_schedule_run(s["times"]) if s["enabled"] else None
    return s


def apply_schedule(enabled, times):
    try:
        old = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        existing = old.stdout if old.returncode == 0 else ""
    except Exception as e:
        return False, "crontab unavailable: %s" % e
    keep = [line for line in existing.splitlines() if SCHEDULE_MARK not in line]
    keep = [line for line in keep if not line.startswith(("SHELL=", "PATH="))]
    content = ["SHELL=/bin/bash",
               "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"]
    content.extend(line for line in keep if line.strip())
    if enabled:
        for raw in times:
            hh, mm = raw.split(":")
            content.append("%d %d * * * /bin/bash %s >/dev/null 2>&1 %s" % (
                int(mm), int(hh), RUNNER, SCHEDULE_MARK))
    text = "\n".join(content).rstrip() + "\n"
    try:
        p = subprocess.run(["crontab", "-"], input=text, text=True,
                           capture_output=True, timeout=5)
    except Exception as e:
        return False, "crontab write failed: %s" % e
    if p.returncode != 0:
        return False, (p.stderr or "crontab write failed").strip()[:200]
    return True, "saved"


def save_schedule(enabled, times):
    times = normalize_times(times)
    if enabled and not times:
        return False, "至少保留一个启动时间"
    if len(times) > 12:
        return False, "最多 12 个启动时间"
    ok, msg = apply_schedule(enabled, times)
    if not ok:
        return False, msg
    try:
        tmp = SCHEDULE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"enabled": enabled, "times": times}, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, SCHEDULE_FILE)
    except Exception as e:
        return False, "schedule save failed: %s" % e
    return True, "saved"


_game_lock = threading.Lock()


def default_game_account():
    return {"id": "default", "name": "主账号", "profile": DEFAULT_PROFILE,
            "created": int(time.time())}


def load_game_accounts():
    data = {}
    try:
        data = json.load(open(GAME_ACCOUNTS_FILE, encoding="utf-8"))
    except Exception:
        pass
    accounts = []
    for a in data.get("accounts") or []:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        accounts.append({
            "id": str(a["id"]), "name": str(a.get("name") or a["id"]),
            "profile": str(a.get("profile") or ""), "created": a.get("created"),
        })
    if not accounts:
        accounts = [default_game_account()]
    if not any(a["id"] == "default" for a in accounts):
        accounts.insert(0, default_game_account())
    for a in accounts:
        if not a.get("profile"):
            a["profile"] = DEFAULT_PROFILE if a["id"] == "default" else os.path.join(GAME_PROFILE_DIR, a["id"])
    active = data.get("active")
    if active not in {a["id"] for a in accounts}:
        active = accounts[0]["id"]
    return {"accounts": accounts, "active": active}


def save_game_accounts(data):
    tmp = GAME_ACCOUNTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, GAME_ACCOUNTS_FILE)
    acct = next(a for a in data["accounts"] if a["id"] == data["active"])
    with open(ACTIVE_PROFILE_FILE, "w", encoding="utf-8") as f:
        f.write(acct["profile"] + "\n")
    try:
        os.chmod(ACTIVE_PROFILE_FILE, 0o600)
    except Exception:
        pass


def ensure_game_accounts():
    data = load_game_accounts()
    save_game_accounts(data)
    return data


def active_game_account():
    data = load_game_accounts()
    return next(a for a in data["accounts"] if a["id"] == data["active"])


def active_profile():
    try:
        return active_game_account().get("profile") or DEFAULT_PROFILE
    except Exception:
        return DEFAULT_PROFILE


def game_accounts_payload():
    data = load_game_accounts()
    return {
        "active": data["active"],
        "accounts": [{
            "id": a["id"], "name": a["name"], "active": a["id"] == data["active"],
            "exists": bool(a.get("profile") and os.path.isdir(a["profile"])),
        } for a in data["accounts"]],
    }


def create_game_account(name):
    name = (name or "").strip()[:24]
    if not name:
        return False, "请填写账号备注名"
    with _game_lock:
        data = load_game_accounts()
        if any(a["name"] == name for a in data["accounts"]):
            return False, "账号备注名已存在"
        aid = "acct-" + secrets.token_hex(4)
        profile = os.path.join(GAME_PROFILE_DIR, aid)
        os.makedirs(profile, exist_ok=True)
        data["accounts"].append({"id": aid, "name": name, "profile": profile,
                                 "created": int(time.time())})
        data["active"] = aid
        save_game_accounts(data)
    return True, aid


def set_game_active(aid):
    with _game_lock:
        data = load_game_accounts()
        if not any(a["id"] == aid for a in data["accounts"]):
            return False, "账号不存在"
        data["active"] = aid
        save_game_accounts(data)
    return True, "switched"


def delete_game_account(aid):
    if aid == "default":
        return False, "默认主账号不能删除"
    with _game_lock:
        data = load_game_accounts()
        victim = next((a for a in data["accounts"] if a["id"] == aid), None)
        if not victim:
            return False, "账号不存在"
        data["accounts"] = [a for a in data["accounts"] if a["id"] != aid]
        if data["active"] == aid:
            data["active"] = data["accounts"][0]["id"]
        save_game_accounts(data)
    try:
        if os.path.isdir(victim.get("profile") or ""):
            shutil.rmtree(victim["profile"])
    except Exception:
        pass
    return True, "deleted"


def cdp_call(method, params=None):
    try:
        with urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=4) as r:
            pages = json.load(r)
        pages = [p for p in pages if p.get("type") == "page"]
        page = next((p for p in pages if "endfield" in (p.get("url") or "")), pages[0] if pages else None)
        if not page:
            return False, "no chrome page"
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=8)
        try:
            ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == 1:
                    return True, msg
        finally:
            ws.close()
    except Exception as e:
        return False, str(e)


def clear_game_session():
    cdp_call("Network.enable")
    cdp_call("Network.clearBrowserCookies")
    cdp_call("Storage.clearDataForOrigin",
             {"origin": "https://endfield.hypergryph.com", "storageTypes": "all"})
    cdp_call("Page.navigate", {"url": CLOUD_URL})
    return True, "logged out"


ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_lock = threading.Lock()
_shot_cache = (0.0, None)
_live_frame = {"data": None, "ts": 0.0, "thread": None}
_live_lock = threading.Lock()
_screencast_lock = threading.Lock()
_takeover_start_lock = threading.Lock()
_takeover_proc_lock = threading.Lock()
_takeover_gen = 0
_takeover_starting = False


def run(cmd, timeout=8):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout)
    except Exception:
        return None


def pgrep(pattern):
    r = run(["pgrep", "-f", pattern], 4)
    return bool(r and r.returncode == 0 and r.stdout.strip())


def running():
    return pgrep("run_daily_linux.py")


def wrapper_running():
    return pgrep("daily_run_homesrv.sh")


def busy():
    return running() or wrapper_running()


def chrome_running():
    return pgrep("user-data-dir=" + BASE + "/.config/endfield")


def log_path():
    paths = [p for p in LOGS if os.path.exists(p)]
    return max(paths, key=os.path.getmtime) if paths else None


def log_lines():
    p = log_path()
    if not p:
        return []
    try:
        st = os.stat(p)
        key = (p, st.st_mtime_ns, st.st_size)
    except Exception:
        return []
    with _log_cache_lock:
        if _log_cache["key"] == key:
            return _log_cache["lines"]
    try:
        # Only the tail matters for the panel. Reading 8 MB on every 2.5 s
        # poll was the single biggest cost in the old console.
        with open(p, "rb") as f:
            f.seek(max(0, st.st_size - 600000))
            raw = f.read().decode("utf-8", "replace")
    except Exception:
        return []
    out = []
    for line in raw.splitlines():
        line = ANSI.sub("", line).rstrip()
        if re.match(r"^\[\d\d:\d\d:\d\d\]", line) or "Traceback" in line or "[X]" in line or "ERROR" in line:
            out.append(line[:500])
    out = out[-1200:]
    with _log_cache_lock:
        _log_cache["key"] = key
        _log_cache["lines"] = out
    return out


def hhmmss_seconds(t):
    try:
        h, m, s = [int(x) for x in t.split(":")]
        return h * 3600 + m * 60 + s
    except Exception:
        return None


def parse_progress(lines):
    run_tasks = list(TASKS)
    states = {t: "pending" for t in run_tasks}
    durations = {}
    current = None
    started = None
    for line in lines:
        if "待跑" in line:
            m = re.match(r"^\[(\d\d:\d\d:\d\d)\] 待跑 \d+ 项: (.*)$", line)
            if m:
                started = m.group(1)
                names = [x.strip() for x in m.group(2).split("/") if x.strip()]
                if names:
                    run_tasks = names
            states = {t: "pending" for t in run_tasks}
            durations = {}
            current = None
            continue
        m = re.match(r"^\[\d\d:\d\d:\d\d\] --- \(\d+/\d+\) (\S+) ->", line)
        if m:
            current = m.group(1)
            states.setdefault(current, "pending")
            states[current] = "running"
            continue
        m = re.match(r"^\[\d\d:\d\d:\d\d\]\s+=> done=True succeeded=(True|False)\s+([\d.]+)s", line)
        if m and current:
            states[current] = "success" if m.group(1) == "True" else "fail"
            try:
                durations[current] = float(m.group(2))
            except ValueError:
                pass
            current = None
    return states, durations, started, run_tasks


def meminfo():
    try:
        d = {}
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            d[k] = int(v.strip().split()[0])
        total = d.get("MemTotal", 0) // 1024
        available = d.get("MemAvailable", 0) // 1024
        return {"total_mb": total, "available_mb": available,
                "used_mb": max(0, total - available)}
    except Exception:
        return {}


def status():
    live = running()
    lines = log_lines()
    prog = None
    try:
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            prog = json.load(f)
    except Exception:
        prog = None
    started_ts = None
    started = None
    if isinstance(prog, dict) and prog.get("tasks"):
        run_tasks = [t for t in prog.get("tasks") if isinstance(t, str)]
        ps = prog.get("states") or {}
        states = {t: ps.get(t, "pending") for t in run_tasks}
        durations = prog.get("durations") or {}
        current = prog.get("current") if live else None
        started_ts = prog.get("started")
    else:
        states, durations, started, run_tasks = parse_progress(lines)
        current = next((t for t, s in states.items() if s == "running"), None) if live else None
    starting = wrapper_running() and not live
    if starting and _starting.get("tasks") and time.time() - _starting.get("at", 0) < 180:
        # Chrome/launcher boot takes ~30 s. Until the runner writes its own
        # progress, show the new task list as pending instead of stale results.
        prog_started = prog.get("started") if isinstance(prog, dict) else None
        if not prog_started or prog_started < _starting.get("at", 0) - 5:
            run_tasks = list(_starting["tasks"])
            states = {t: "pending" for t in run_tasks}
            durations = {}
            current = None
    if not live:
        for k, v in states.items():
            if v == "running":
                states[k] = "fail"
    last = ""
    for line in reversed(lines):
        if "=> done=True" in line:
            last = line
            break
    uptime = None
    if live:
        if isinstance(started_ts, (int, float)):
            uptime = max(0, int(time.time() - started_ts))
        elif started:
            sec = hhmmss_seconds(started)
            now = time.localtime()
            if sec is not None:
                delta = (now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec) - sec
                uptime = delta if delta >= 0 else delta + 86400
    return {
        "running": live, "starting": starting, "busy": busy(),
        "chrome": chrome_running(), "auth": auth_enabled(),
        "takeover": takeover_active(), "takeover_starting": _takeover_starting,
        "schedule": schedule_payload(), "game_account": active_game_account().get("name"),
        "game_account_id": active_game_account().get("id"),
        "current": current, "states": states, "durations": durations,
        "run_tasks": run_tasks, "last_result": last, "log": lines[-45:], "mem": meminfo(),
        "maa_version": maa_current_version(),
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "log_file": log_path() or "", "uptime": uptime,
    }


def _cdp_shot():
    with urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=3) as r:
        pages = json.load(r)
    page = next((p for p in pages if p.get("type") == "page" and "endfield" in (p.get("url") or "")), None)
    if page is None:
        page = next((p for p in pages if p.get("type") == "page"), None)
    if page is None:
        return None
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=12)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": "({w:innerWidth,h:innerHeight})",
                                       "returnByValue": True}}))
        vp = None
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                vp = msg.get("result", {}).get("result", {}).get("value")
                break
        params = {"format": "jpeg", "quality": 80}
        if isinstance(vp, dict) and vp.get("w") and vp.get("h"):
            w, h = float(vp["w"]), float(vp["h"])
            params["clip"] = {"x": 0, "y": 0, "width": w, "height": h,
                              "scale": min(1.0, 1280.0 / w)}
        ws.send(json.dumps({"id": 2, "method": "Page.captureScreenshot", "params": params}))
        msg = None
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 2:
                break
    finally:
        ws.close()
    raw = base64.b64decode(msg["result"]["data"])
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    if im.width > 1280:
        im.thumbnail((1280, 1280), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=78)
    return buf.getvalue()


def _chrome_page():
    try:
        with urllib.request.urlopen("http://127.0.0.1:9334/json", timeout=3) as r:
            pages = json.load(r)
    except Exception:
        return None
    pages = [p for p in pages if p.get("type") == "page"]
    return next((p for p in pages if "endfield" in (p.get("url") or "")),
                pages[0] if pages else None)


def _screencast_loop():
    """Keep the newest CDP screencast JPEG so /api/shot is O(1)."""
    ack_id = 1000
    while chrome_running():
        ws = None
        try:
            page = _chrome_page()
            if not page:
                break
            ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=10)
            ws.settimeout(10)
            ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            ws.send(json.dumps({
                "id": 2,
                "method": "Page.startScreencast",
                "params": {"format": "jpeg", "quality": 70,
                           "maxWidth": 1280, "maxHeight": 720,
                           "everyNthFrame": 6},
            }))
            while chrome_running():
                try:
                    msg = json.loads(ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                if msg.get("method") != "Page.screencastFrame":
                    continue
                params = msg.get("params") or {}
                data = params.get("data")
                if data:
                    try:
                        raw = base64.b64decode(data)
                        with _live_lock:
                            _live_frame["data"] = raw
                            _live_frame["ts"] = time.time()
                    except Exception:
                        pass
                sid = params.get("sessionId")
                if sid is not None:
                    ack_id += 1
                    try:
                        ws.send(json.dumps({"id": ack_id,
                                            "method": "Page.screencastFrameAck",
                                            "params": {"sessionId": sid}}))
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            try:
                if ws:
                    ws.close()
            except Exception:
                pass
            with _live_lock:
                _live_frame["thread"] = None
        if chrome_running():
            time.sleep(0.5)
        else:
            break


def ensure_screencast():
    with _screencast_lock:
        thread = _live_frame.get("thread")
        if thread is not None and thread.is_alive():
            return
        thread = threading.Thread(target=_screencast_loop, daemon=True)
        _live_frame["thread"] = thread
        thread.start()


def screenshot():
    global _shot_cache
    now = time.time()
    if not chrome_running():
        return None
    ensure_screencast()
    with _live_lock:
        live = _live_frame.get("data")
    if live:
        return live
    # First request: the screencast frame is not ready yet. Keep the old
    # one-shot CDP capture as a fallback.
    if _shot_cache[1] is not None and now - _shot_cache[0] < 0.18:
        return _shot_cache[1]
    if not _lock.acquire(blocking=False):
        return _shot_cache[1]
    try:
        data = None
        try:
            data = _cdp_shot()
        except Exception:
            data = None
        if data is None:
            r = run([PY, CDP, "screenshot", RAW], 8)
            if r is not None and r.returncode == 0 and os.path.exists(RAW):
                try:
                    im = Image.open(RAW).convert("RGB")
                    im.thumbnail((1280, 1280), Image.LANCZOS)
                    buf = io.BytesIO()
                    im.save(buf, "JPEG", quality=78)
                    data = buf.getvalue()
                except Exception:
                    data = None
        if data is not None:
            _shot_cache = (now, data)
        return data
    finally:
        _lock.release()


def start_daily(tasks="", instance=None, planned=None):
    if busy():
        return False, "already running"
    try:
        os.unlink(STOP_MARK)
    except OSError:
        pass
    picked = list(planned or []) or [t.strip() for t in (tasks or "").split(",") if t.strip()] or list(FULL_DAILY)
    _starting["tasks"] = picked
    _starting["at"] = time.time()
    env = os.environ.copy()
    env.update({"MAAEND_TASKS": tasks, "HOME": BASE,
                "XDG_RUNTIME_DIR": "/run/user/1000",
                "MAAEND_CHROME": "/usr/bin/google-chrome",
                "MAAEND_PROFILE": active_profile()})
    if instance:
        env["MAAEND_INSTANCE"] = instance
        if str(instance).startswith("preset:"):
            env["MAAEND_PRESET"] = "1"
    log = open(BASE + "/webui-run.log", "ab")
    subprocess.Popen(["bash", RUNNER], cwd=WEB, env=env, stdout=log, stderr=log,
                     start_new_session=True)
    return True, "started"


def stop_all():
    # 让 chrome_homesrv.sh 区分「用户主动停止」和真正的启动失败：
    # 启动窗口内点停止会写这个时间戳，脚本看到后以 rc=2 正常退出。
    try:
        with open(STOP_MARK, "w") as f:
            f.write(str(int(time.time())))
        os.chmod(STOP_MARK, 0o644)
    except OSError:
        pass
    run([PY, CDP, "navigate", "about:blank"], 6)
    run(["pkill", "-f", "daily_run_homesrv.sh"], 5)
    run(["pkill", "-f", "run_daily_linux.py"], 5)
    run(["pkill", "-x", "go-service"], 5)
    run(["pkill", "-f", "hide_cloud_ball.py --watch"], 5)
    run(["pkill", "-f", "user-data-dir=" + BASE + "/.config/endfield"], 5)
    run(["pkill", "-x", "sway"], 5)
    # a full stop must also take the manual takeover stream down; otherwise
    # noVNC stays connected to a dead Chrome window.
    kill_vnc()
    return True, "stopped"


def pgrep_exact(name):
    r = run(["pgrep", "-x", name], 4)
    if not (r and r.returncode == 0 and r.stdout.strip()):
        return False
    for raw in r.stdout.split():
        try:
            pid = raw.decode()
            stat = open("/proc/%s/stat" % pid).read()
            state = stat.rsplit(")", 1)[1].split()[0]
        except Exception:
            return True
        if state != "Z":
            return True
    return False


def vnc_token():
    try:
        first = open(VNC_TOKEN_FILE).readline().strip()
        tok = first.split(":", 1)[0].strip()
        if tok:
            return tok
    except Exception:
        pass
    tok = secrets.token_hex(16)
    try:
        with open(VNC_TOKEN_FILE, "w") as f:
            f.write(f"{tok}: 127.0.0.1:5900\n")
        os.chmod(VNC_TOKEN_FILE, 0o600)
    except Exception:
        pass
    return tok


def sync_novnc_token():
    tok = vnc_token()
    p = NOVNC_DIR + "/app/ui.js"
    try:
        s = open(p, encoding="utf-8").read()
        # The panel proxies /vnc/* to websockify, so the websocket must stay on
        # the same origin/port instead of opening :6080 on the public host.
        replacement = "const path = 'vnc/websockify?token=%s';" % tok
        s2 = re.sub(r"const path = '[^']*';", replacement, s, count=1)
        if s2 != s:
            open(p, "w", encoding="utf-8").write(s2)
    except Exception:
        pass


def ensure_takeover_files():
    try:
        os.makedirs(WAYVNC_CFG_DIR, exist_ok=True)
        with open(WAYVNC_CFG, "w") as f:
            f.write("address=127.0.0.1\nport=5900\nenable_auth=false\n")
        vnc_token()
        sync_novnc_token()
    except Exception:
        pass


def takeover_active():
    return pgrep_exact("wayvnc") and pgrep_exact("websockify")


def kill_vnc():
    # websockify keeps running with an attached noVNC client on plain SIGTERM
    for name in ("wayvnc", "websockify"):
        run(["pkill", "-x", name], 5)
    time.sleep(0.4)
    for name in ("wayvnc", "websockify"):
        run(["pkill", "-9", "-x", name], 5)
    for _ in range(10):
        if not pgrep_exact("wayvnc") and not pgrep_exact("websockify"):
            break
        time.sleep(0.2)


def port_open(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except Exception:
        return False


def takeover_env():
    env = os.environ.copy()
    env.update({"HOME": BASE, "XDG_RUNTIME_DIR": "/run/user/1000",
                "WAYLAND_DISPLAY": "wayland-1",
                "MAAEND_CHROME": "/usr/bin/google-chrome",
                "MAAEND_PROFILE": active_profile()})
    return env


def start_takeover():
    global _takeover_gen, _takeover_starting
    # a second concurrent start would kill the first one's Chrome/wayvnc
    if not _takeover_start_lock.acquire(blocking=False):
        return False, "接管正在启动或停止，请稍候"
    _takeover_gen += 1
    gen = _takeover_gen
    _takeover_starting = True

    def cancelled():
        return gen != _takeover_gen

    try:
        # manual takeover needs the automation loop out of the way
        run(["pkill", "-f", "daily_run_homesrv.sh"], 5)
        run(["pkill", "-f", "run_daily_linux.py"], 5)
        run(["pkill", "-x", "go-service"], 5)
        # stale launcher from a cancelled start would race this Chrome
        run(["pkill", "-f", "[c]hrome_homesrv.sh"], 5)
        # rebind VNC after Chrome/sway are ready; a stale wayvnc would stay blank
        kill_vnc()
        time.sleep(1)
        if cancelled():
            return False, "已取消"

        if not chrome_running():
            try:
                with open("/tmp/takeover-chrome.log", "ab") as log:
                    subprocess.Popen(["bash", WEB + "/homesrv/chrome_homesrv.sh"],
                                     cwd=WEB, env=takeover_env(), stdout=log, stderr=log,
                                     start_new_session=True)
            except Exception as e:
                return False, "chrome start failed: %s" % e

        ready = False
        for _ in range(45):
            if cancelled():
                return False, "已取消"
            if chrome_running() and port_open(9334):
                ready = True
                break
            time.sleep(1)
        if not ready:
            return False, "chrome not ready"
        time.sleep(2)
        if cancelled():
            return False, "已取消"

        ensure_takeover_files()

        # stop_takeover() bumps the generation and kills under this lock, so a
        # cancelled start can never leave a fresh wayvnc/websockify behind.
        with _takeover_proc_lock:
            if cancelled():
                return False, "已取消"
            try:
                with open("/tmp/wayvnc.log", "ab") as log:
                    # No -r: noVNC hides its local cursor and waits for VNC cursor
                    # updates, so overlay-cursor mode leaves the pointer invisible.
                    subprocess.Popen(["wayvnc", "-C", WAYVNC_CFG, "-o", "HEADLESS-1", "-L", "warning"],
                                     env=takeover_env(), stdout=log, stderr=log,
                                     start_new_session=True)
            except Exception as e:
                return False, "wayvnc start failed: %s" % e

            try:
                with open("/tmp/websockify.log", "ab") as log:
                    subprocess.Popen(["websockify",
                                      "--token-plugin=TokenFile",
                                      "--token-source=" + VNC_TOKEN_FILE,
                                      "--web=" + NOVNC_DIR,
                                      "0.0.0.0:6080"],
                                     env=takeover_env(), stdout=log, stderr=log,
                                     start_new_session=True)
            except Exception as e:
                kill_vnc()
                return False, "websockify start failed: %s" % e

        for _ in range(15):
            if cancelled():
                kill_vnc()
                return False, "已取消"
            if port_open(5900) and port_open(6080):
                return True, "started"
            time.sleep(0.5)
        kill_vnc()
        return False, "vnc ports not ready"
    finally:
        _takeover_starting = False
        _takeover_start_lock.release()


def stop_takeover():
    global _takeover_gen
    # invalidate any in-flight start before waiting for its process critical section
    _takeover_gen += 1
    with _takeover_proc_lock:
        kill_vnc()
    return True, "stopped"


def takeover_url(handler):
    # Keep the original scheme and port: noVNC is proxied under /vnc/ so the
    # browser only needs the panel port (6080 is not exposed to the internet).
    host = (handler.headers.get("X-Forwarded-Host")
            or handler.headers.get("Host") or "").strip()
    if not host:
        host = "127.0.0.1:%d" % PORT
    proto = (handler.headers.get("X-Forwarded-Proto") or "http").strip().lower()
    if proto not in ("http", "https"):
        proto = "http"
    return "%s://%s/vnc/vnc.html?v=2#autoconnect=1&resize=scale" % (proto, host)


MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".woff2": "font/woff2",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
}


def static_file(rel):
    root = os.path.realpath(STATIC)
    full = os.path.realpath(os.path.join(root, rel))
    if full != root and not full.startswith(root + os.sep):
        return None
    return full if os.path.isfile(full) else None


class Handler(BaseHTTPRequestHandler):
    server_version = "MaaEndUI/2.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _tok(self):
        qs = parse_qs(urlparse(self.path).query)
        return (qs.get("token") or [self.headers.get("X-Token", "")])[0]

    def _ok(self):
        # First-run (no accounts, token off) stays open so the setup page can
        # create the administrator. After that a session or the token is
        # required: the old code only checked the token flag, so sessions never
        # actually protected the API.
        if not accounts_exist() and not auth_enabled():
            return True
        return bool(session_principal(self) or token_principal(self))

    def _send(self, code, body, ctype="text/plain; charset=utf-8", cache="no-store", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_static(self, rel):
        full = static_file(rel)
        if full is None:
            self._send(404, b"not found")
            return
        ext = os.path.splitext(full)[1].lower()
        ctype = MIME.get(ext, "application/octet-stream")
        cache = "public, max-age=2592000, immutable" if ext == ".woff2" else "no-cache"
        try:
            data = open(full, "rb").read()
        except Exception:
            self._send(404, b"not found")
            return
        self._send(200, data, ctype, cache)

    def _proxy_vnc(self, target):
        if "websocket" in (self.headers.get("Upgrade") or "").lower():
            self._proxy_vnc_ws(target)
            return
        try:
            conn = http.client.HTTPConnection("127.0.0.1", VNC_PORT, timeout=20)
            headers = {}
            for k, v in self.headers.items():
                if k.lower() in ("host", "connection", "proxy-connection", "keep-alive"):
                    continue
                headers[k] = v
            headers["Host"] = "127.0.0.1:%d" % VNC_PORT
            conn.request("GET", target or "/", headers=headers)
            resp = conn.getresponse()
            body = resp.read()
            conn.close()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in ("connection", "transfer-encoding", "content-length", "keep-alive"):
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self._send(502, ("vnc proxy error: %s" % e).encode())

    def _proxy_vnc_ws(self, target):
        # noVNC needs a raw WebSocket tunnel. ThreadingHTTPServer gives us one
        # thread per connection, so relay both directions until either side
        # closes.
        upstream = None
        try:
            upstream = socket.create_connection(("127.0.0.1", VNC_PORT), timeout=15)
            upstream.settimeout(None)
            lines = ["GET %s HTTP/1.1" % (target or "/"),
                     "Host: 127.0.0.1:%d" % VNC_PORT]
            for k, v in self.headers.items():
                if k.lower() in ("host", "connection", "proxy-connection",
                                 "keep-alive", "upgrade"):
                    continue
                lines.append("%s: %s" % (k, v))
            lines.append("Connection: Upgrade")
            lines.append("Upgrade: websocket")
            upstream.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1", "replace"))
        except Exception:
            if upstream is not None:
                try: upstream.close()
                except Exception: pass
            self.close_connection = True
            return

        client = self.connection

        def client_to_upstream():
            try:
                while True:
                    data = self.rfile.read1(65536)
                    if not data:
                        break
                    upstream.sendall(data)
            except Exception:
                pass
            finally:
                try: upstream.shutdown(socket.SHUT_WR)
                except Exception: pass

        threading.Thread(target=client_to_upstream, daemon=True).start()
        try:
            while True:
                data = upstream.recv(65536)
                if not data:
                    break
                client.sendall(data)
        except Exception:
            pass
        finally:
            try: upstream.close()
            except Exception: pass
            try: client.shutdown(socket.SHUT_WR)
            except Exception: pass
            self.close_connection = True

    def do_GET(self):
        parsed = urlparse(self.path)
        p = parsed.path
        if p.startswith("/static/"):
            self._serve_static(p[len("/static/"):])
            return
        if p == "/favicon.ico":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if p == "/vnc":
            self.send_response(301)
            self.send_header("Location", "/vnc/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if p.startswith("/vnc/"):
            if not vnc_access_ok(self):
                self._send(401, b"unauthorized")
                return
            target = p[len("/vnc"):] or "/"
            if parsed.query:
                target += "?" + parsed.query
            self._proxy_vnc(target)
            return
        if p == "/setup" and accounts_exist():
            # Once the first administrator exists, setup is no longer a page.
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if p in ("/", "/index.html", "/login", "/setup"):
            if p == "/setup":
                name = "setup.html"
            elif p == "/login":
                name = "login.html" if accounts_exist() else "setup.html"
            elif not accounts_exist():
                name = "setup.html"
            elif self._ok():
                name = "index.html"
            else:
                name = "login.html"
            full = static_file(name)
            if full is None:
                self._send(500, b"UI files missing")
                return
            data = open(full, "rb").read()
            self._send(200, data, "text/html; charset=utf-8", "no-cache",
                       {"Content-Security-Policy":
                        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                        "script-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'"})
            return
        if not self._ok():
            self._send(401, b"unauthorized")
            return
        if p == "/api/me":
            who = principal(self) or {}
            if not who and not accounts_exist() and not auth_enabled():
                who = {"username": "operator", "role": "admin", "token": False,
                       "anonymous": True}
            self._send(200, json.dumps({"username": who.get("username"),
                                        "role": who.get("role"),
                                        "token": bool(who.get("token")),
                                        "anonymous": bool(who.get("anonymous"))},
                                       ensure_ascii=False).encode(), "application/json")
            return
        if p == "/api/users":
            who = principal(self) or {}
            if who.get("role") != "admin":
                self._send(403, b"forbidden")
                return
            users = [{"username": u.get("username"), "role": u.get("role", "user"),
                      "created": u.get("created")} for u in load_users()]
            self._send(200, json.dumps({"users": users}, ensure_ascii=False).encode(), "application/json")
            return
        if p == "/api/game-accounts":
            self._send(200, json.dumps(game_accounts_payload(), ensure_ascii=False).encode(),
                       "application/json")
            return
        if p == "/api/status":
            self._send(200, json.dumps(status(), ensure_ascii=False).encode(), "application/json")
            return
        if p == "/api/mem":
            mem = meminfo()
            self._send(200, json.dumps({"mem": mem,
                                        "server_time": time.strftime("%Y-%m-%d %H:%M:%S")},
                                       ensure_ascii=False).encode(), "application/json")
            return
        if p == "/api/settings":
            who = principal(self) or {}
            payload = {"auth": auth_enabled()}
            if who.get("role") == "admin":
                payload["token"] = TOKEN
            self._send(200, json.dumps(payload).encode(), "application/json")
            return
        if p == "/api/schedule":
            self._send(200, json.dumps(schedule_payload(), ensure_ascii=False).encode(), "application/json")
            return
        if p == "/api/tasks":
            self._send(200, json.dumps({"tasks": catalog_payload()}, ensure_ascii=False).encode(), "application/json")
            return
        if p == "/api/presets":
            self._send(200, json.dumps({"presets": maa_presets()}, ensure_ascii=False).encode(), "application/json")
            return
        if p == "/api/maa/info":
            who = principal(self) or {}
            if who.get("role") != "admin":
                self._send(403, b"forbidden")
                return
            cached = _maa_check_cache.get("data") or {}
            with _maa_update_lock:
                job = dict(_maa_update)
            payload = {
                "current": maa_current_version(),
                "latest": cached.get("latest") or "",
                "checked": cached.get("checked") or 0,
                "busy": busy(),
                "takeover": takeover_active(),
                "job": job,
                "log": maa_log_tail(20),
            }
            self._send(200, json.dumps(payload, ensure_ascii=False).encode(), "application/json")
            return
        if p == "/api/maa/update/status":
            who = principal(self) or {}
            if who.get("role") != "admin":
                self._send(403, b"forbidden")
                return
            with _maa_update_lock:
                job = dict(_maa_update)
            job["log"] = maa_log_tail(30)
            self._send(200, json.dumps(job, ensure_ascii=False).encode(), "application/json")
            return
        if p == "/api/takeover/status":
            self._send(200, json.dumps({"active": takeover_active(),
                                        "vnc": pgrep_exact("wayvnc"),
                                        "web": pgrep_exact("websockify"),
                                        "chrome": chrome_running()}).encode(), "application/json")
            return
        if p == "/api/shot":
            data = screenshot()
            if not data:
                self._send(503, b"no screenshot")
                return
            self._send(200, data, "image/jpeg")
            return
        self._send(404, b"not found")

    def do_POST(self):
        global TOKEN
        p = urlparse(self.path).path
        # Drain every request body. Leaving "{}" in a keep-alive socket makes
        # the next request line malformed and returns http.server's HTML 500.
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            n = 0
        n = min(max(n, 0), 1 << 20)
        try:
            raw_body = self.rfile.read(n) if n else b""
        except Exception:
            raw_body = b""
        if p == "/api/setup":
            if accounts_exist():
                self._send(409, json.dumps({"ok": False, "msg": "已经初始化"}).encode(), "application/json")
                return
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            ok, msg = create_user(data.get("username"), data.get("password"), "admin")
            if not ok:
                self._send(400, json.dumps({"ok": False, "msg": msg}).encode(), "application/json")
                return
            sid = create_session(data.get("username").strip())
            self._send(200, json.dumps({"ok": True, "username": data.get("username").strip(),
                                        "role": "admin"}).encode(), "application/json",
                       extra=set_session_cookie(self, sid))
            return
        if p == "/api/login":
            if not accounts_exist():
                self._send(409, json.dumps({"ok": False, "msg": "尚未初始化管理员"}).encode(), "application/json")
                return
            ip = self.client_address[0]
            now = time.time()
            with _login_fail_lock:
                rec = _login_fail.get(ip)
                if rec and rec[0] >= 8 and now - rec[1] < 300:
                    self._send(429, json.dumps({"ok": False, "msg": "尝试次数过多，请稍后再试"}).encode(),
                               "application/json")
                    return
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            username = str(data.get("username") or "").strip()
            user = find_user(username)
            if not user or not verify_password(user, data.get("password") or ""):
                with _login_fail_lock:
                    cnt = (_login_fail.get(ip) or [0, 0])[0] + 1
                    _login_fail[ip] = [cnt, now]
                time.sleep(0.25)
                self._send(401, json.dumps({"ok": False, "msg": "用户名或密码错误"}).encode(), "application/json")
                return
            with _login_fail_lock:
                _login_fail.pop(ip, None)
            sid = create_session(user["username"])
            self._send(200, json.dumps({"ok": True, "username": user["username"],
                                        "role": user.get("role", "user")}).encode(), "application/json",
                       extra=set_session_cookie(self, sid))
            return
        if p == "/api/logout":
            self._send(200, json.dumps({"ok": True}).encode(), "application/json",
                       extra=clear_session_cookie(self))
            return
        if p == "/api/auth":
            who = principal(self) or {}
            if who.get("role") != "admin":
                self._send(403, b"forbidden")
                return
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            set_auth(bool(data.get("enabled")))
            self._send(200, json.dumps({"ok": True, "auth": auth_enabled(), "token": TOKEN}).encode(),
                       "application/json")
            return
        if p == "/api/token/rotate":
            who = principal(self) or {}
            if who.get("role") != "admin":
                self._send(403, b"forbidden")
                return
            TOKEN = secrets.token_urlsafe(24)
            with open(TOKEN_FILE, "w") as f:
                f.write(TOKEN)
            os.chmod(TOKEN_FILE, 0o600)
            self._send(200, json.dumps({"ok": True, "token": TOKEN}).encode(), "application/json")
            return
        if not self._ok():
            self._send(401, b"unauthorized")
            return
        if p == "/api/task-options":
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            task = str(data.get("task") or "").strip()
            values = data.get("optionValues")
            if not task or not isinstance(values, dict):
                self._send(400, json.dumps({"ok": False, "msg": "缺少 task / optionValues"}).encode(), "application/json")
                return
            if not any(t.get("name") == task for t in load_catalog()):
                self._send(404, json.dumps({"ok": False, "msg": "任务不存在"}).encode(), "application/json")
                return
            cfg = load_maa_config()
            inst = _find_instance(cfg, MAA_QUEUE_INSTANCE)
            if inst is None:
                inst = {"id": MAA_QUEUE_INSTANCE, "name": "面板待选队列",
                        "controllerName": "Linux-Wlroots",
                        "resourceName": "官服-网页端", "tasks": []}
                cfg.setdefault("instances", []).append(inst)
            tasks = inst.setdefault("tasks", [])
            entry = next((t for t in tasks if t.get("taskName") == task), None)
            if entry is None:
                entry = {"taskName": task, "enabled": True, "optionValues": values}
                tasks.append(entry)
            else:
                entry["optionValues"] = values
                entry["enabled"] = True
            daily = _find_instance(cfg, "webcloud-full")
            if daily is not None:
                for t in daily.get("tasks") or []:
                    if t.get("taskName") == task:
                        t["optionValues"] = values
            save_maa_config(cfg)
            self._send(200, json.dumps({"ok": True, "task": task}, ensure_ascii=False).encode(),
                       "application/json")
            return
        if p == "/api/maa/check":
            who = principal(self) or {}
            if who.get("role") != "admin":
                self._send(403, b"forbidden")
                return
            data = maa_check_update(force=True)
            self._send(200, json.dumps(data, ensure_ascii=False).encode(), "application/json")
            return
        if p == "/api/maa/update":
            who = principal(self) or {}
            if who.get("role") != "admin":
                self._send(403, b"forbidden")
                return
            ok, msg = start_maa_update()
            self._send(200 if ok else 409,
                       json.dumps({"ok": ok, "msg": msg}, ensure_ascii=False).encode(),
                       "application/json")
            return
        if p == "/api/users":
            who = principal(self) or {}
            if who.get("role") != "admin":
                self._send(403, b"forbidden")
                return
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            ok, msg = create_user(data.get("username"), data.get("password"), "user")
            self._send(200 if ok else 400, json.dumps({"ok": ok, "msg": msg}).encode(), "application/json")
            return
        if p == "/api/users/delete":
            who = principal(self) or {}
            if who.get("role") != "admin":
                self._send(403, b"forbidden")
                return
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            target = str(data.get("username") or "")
            if target == who.get("username"):
                self._send(400, json.dumps({"ok": False, "msg": "不能删除当前登录账号"}).encode(), "application/json")
                return
            users = load_users()
            victim = next((u for u in users if u.get("username") == target), None)
            if not victim:
                self._send(404, json.dumps({"ok": False, "msg": "账号不存在"}).encode(), "application/json")
                return
            if victim.get("role") == "admin" and sum(1 for u in users if u.get("role") == "admin") <= 1:
                self._send(400, json.dumps({"ok": False, "msg": "至少保留一个管理员"}).encode(), "application/json")
                return
            save_users([u for u in users if u.get("username") != target])
            self._send(200, json.dumps({"ok": True}).encode(), "application/json")
            return
        if p == "/api/password":
            who = principal(self) or {}
            if who.get("token"):
                self._send(400, json.dumps({"ok": False, "msg": "token 账号不能修改密码"}).encode(),
                           "application/json")
                return
            user = find_user(who.get("username"))
            if not user:
                self._send(401, b"unauthorized")
                return
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            if not verify_password(user, data.get("old") or ""):
                self._send(400, json.dumps({"ok": False, "msg": "当前密码错误"}).encode(), "application/json")
                return
            if not valid_password(data.get("new")):
                self._send(400, json.dumps({"ok": False, "msg": "新密码至少 8 位"}).encode(), "application/json")
                return
            users = load_users()
            for u in users:
                if u.get("username") == user["username"]:
                    u["password"] = hash_password(data["new"])
            save_users(users)
            self._send(200, json.dumps({"ok": True}).encode(), "application/json")
            return
        if p == "/api/game-accounts/add":
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            ok, result = create_game_account(data.get("name"))
            if not ok:
                self._send(400, json.dumps({"ok": False, "msg": result}).encode(), "application/json")
                return
            stop_all()
            started, smsg = start_takeover()
            self._send(200 if started else 500,
                       json.dumps({"ok": started, "msg": smsg, "id": result,
                                   "url": takeover_url(self) if started else "",
                                   "active": game_accounts_payload()}, ensure_ascii=False).encode(),
                       "application/json",
                       extra={"Set-Cookie": vnc_cookie_header()} if started else None)
            return
        if p == "/api/game-accounts/switch":
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            ok, msg = set_game_active(str(data.get("id") or ""))
            if not ok:
                self._send(400, json.dumps({"ok": False, "msg": msg}).encode(), "application/json")
                return
            stop_all()
            started, smsg = start_takeover()
            self._send(200 if started else 500,
                       json.dumps({"ok": started, "msg": smsg,
                                   "url": takeover_url(self) if started else "",
                                   "active": game_accounts_payload()}, ensure_ascii=False).encode(),
                       "application/json",
                       extra={"Set-Cookie": vnc_cookie_header()} if started else None)
            return
        if p == "/api/game-accounts/logout":
            stop_all()
            started, smsg = start_takeover()
            if started:
                clear_game_session()
            self._send(200 if started else 500,
                       json.dumps({"ok": started, "msg": smsg,
                                   "url": takeover_url(self) if started else "",
                                   "active": game_accounts_payload()}, ensure_ascii=False).encode(),
                       "application/json",
                       extra={"Set-Cookie": vnc_cookie_header()} if started else None)
            return
        if p == "/api/game-accounts/delete":
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            aid = str(data.get("id") or "")
            was_active = load_game_accounts().get("active") == aid
            ok, msg = delete_game_account(aid)
            if not ok:
                self._send(400, json.dumps({"ok": False, "msg": msg}).encode(), "application/json")
                return
            started = False
            if was_active:
                stop_all()
                started, smsg = start_takeover()
            self._send(200, json.dumps({"ok": True, "msg": msg,
                                        "url": takeover_url(self) if started else "",
                                        "active": game_accounts_payload()}, ensure_ascii=False).encode(),
                       "application/json",
                       extra={"Set-Cookie": vnc_cookie_header()} if started else None)
            return
        if p == "/api/schedule":
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            ok, msg = save_schedule(bool(data.get("enabled")), data.get("times") or [])
            payload = schedule_payload()
            payload.update({"ok": ok, "msg": msg})
            self._send(200 if ok else 400, json.dumps(payload, ensure_ascii=False).encode(),
                       "application/json")
            return
        if p == "/api/start":
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            preset_id = data.get("preset") or ""
            selected = {item["id"]: item for item in maa_presets()}.get(preset_id)
            if preset_id and not selected:
                self._send(400, json.dumps({"ok": False, "msg": "unknown preset"},
                                           ensure_ascii=False).encode(), "application/json")
                return
            if selected:
                if selected["id"] == "webcloud-full":
                    ok, msg = start_daily("", instance="webcloud-full", planned=selected["tasks"])
                else:
                    ok, msg = start_daily("", instance=selected["id"], planned=selected["tasks"])
                self._send(200 if ok else 409,
                           json.dumps({"ok": ok, "msg": msg, "preset": selected["id"]},
                                      ensure_ascii=False).encode(), "application/json")
                return
            ok, msg = start_daily("")
            self._send(200 if ok else 409, json.dumps({"ok": ok, "msg": msg}).encode(), "application/json")
            return
        if p == "/api/run":
            if running():
                self._send(409, json.dumps({"ok": False, "msg": "already running"}).encode(), "application/json")
                return
            try:
                data = json.loads(raw_body.decode() or "{}")
            except Exception:
                data = {}
            allowed = {t.get("name") for t in load_catalog() if t.get("name")} | set(TASKS)
            picked = []
            for t in data.get("tasks") or []:
                if isinstance(t, str) and t in allowed and t not in picked:
                    picked.append(t)
            if not picked:
                self._send(400, json.dumps({"ok": False, "msg": "empty task list"}).encode(), "application/json")
                return
            ok, msg = start_daily(",".join(picked), instance=MAA_QUEUE_INSTANCE)
            self._send(200 if ok else 409, json.dumps({"ok": ok, "msg": msg, "tasks": picked}).encode(),
                       "application/json")
            return
        if p == "/api/stop":
            ok, msg = stop_all()
            self._send(200, json.dumps({"ok": ok, "msg": msg}).encode(), "application/json")
            return
        if p == "/api/takeover":
            ok, msg = start_takeover()
            self._send(200 if ok else 500,
                       json.dumps({"ok": ok, "msg": msg,
                                   "url": takeover_url(self) if ok else "",
                                   "active": takeover_active()}).encode(), "application/json",
                       extra={"Set-Cookie": vnc_cookie_header()} if ok else None)
            return
        if p == "/api/takeover/stop":
            ok, msg = stop_takeover()
            self._send(200, json.dumps({"ok": ok, "msg": msg, "active": takeover_active()}).encode(),
                       "application/json")
            return
        self._send(404, b"not found")


if __name__ == "__main__":
    ensure_takeover_files()
    ensure_game_accounts()
    _sched = load_schedule()
    _ok_sched, _msg_sched = apply_schedule(_sched["enabled"], _sched["times"])
    print("schedule %s: %s" % (_sched, _msg_sched), flush=True)
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    print("webui on %s:%d auth=%s" % (BIND, PORT, auth_enabled()), flush=True)
    srv.serve_forever()
