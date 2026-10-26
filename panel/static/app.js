(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const DAILY = ["WebStartGame", "VisitFriends", "DijiangRewards", "CreditShoppingN2",
                 "DeliveryJobs", "SellProduct", "AutoStockpile", "AutoStockStaple",
                 "GearAssembly", "WeaponUpgrade", "DailyRewards"];

  const GROUP_LABELS = {
    web: "网页端 / WEB",
    regional_development: "地区发展 / REGION",
    valuables_vault: "贵重品库 / VAULT",
    open_world: "大世界 / OPEN WORLD",
    sanity_sink: "理智消耗 / SANITY",
    dijiang_ship: "帝江号 / DIJIANG",
    other_menu: "其他菜单 / MENU",
    realtime: "实时辅助 / REALTIME",
    backpack: "背包制造 / BACKPACK",
    other: "其他 / OTHER"
  };

  const STATE_META = {
    pending: { code: "STBY", label: "待执行" },
    running: { code: "RUN", label: "执行中" },
    success: { code: "OK", label: "完成" },
    fail: { code: "ERR", label: "失败" }
  };

  const NAV_TITLES = {
    live: "CONSOLE",
    library: "TASK LIBRARY",
    history: "RUN HISTORY",
    log: "SYSTEM LOG",
    settings: "SYSTEM"
  };

  const params = new URLSearchParams(location.search);
  const TOKEN = params.get("token") || "";
  const closeTimers = new WeakMap();

  const state = {
    status: null,
    me: null,
    settings: null,
    schedule: null,
    gameAccounts: { accounts: [], active: "" },
    users: [],
    catalog: [],
    meta: {},
    history: [],
    historyTimer: 0,
    queue: loadQueue(),
    optionTask: null,
    optionValues: {},
    maa: null,
    maaVersion: "",
    maaPoll: 0,
    activeModal: null,
    lastFocus: null,
    confirmResolve: null,
    menuOpen: false,
    menuFocus: null,
    takeoverBusy: false,
    takeoverCancelled: false,
    takeoverPopup: null,
    takeoverTimer: 0,
    takeoverStart: 0,
    lastTakeoverOpts: null,
    takeoverUrl: "",
    shotBusy: false,
    shotRate: loadShotRate(),
    presets: [],
    preset: loadPresetId(),
    hasFrame: false,
    lastTasksSig: "",
    lastLogSig: "",
    lastQueueSig: "",
    navLock: false,
    apiOk: true,
    pollTimer: 0,
    shotTimer: 0,
    memTimer: 0,
    cloudTimer: 0
  };

  /* ---------------- helpers ---------------- */
  const pad = (n) => String(n).padStart(2, "0");
  const fmtClock = (d = new Date()) => `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  const basename = (p) => (p || "").replace(/\\/g, "/").split("/").pop() || "—";
  const taskCode = (name) => String(name || "").replace(/[^A-Za-z0-9]/g, "").slice(0, 8).toUpperCase();
  const EMOJI_RE = /[\p{Extended_Pictographic}\uFE0F\u200D]/gu;
  const taskLabel = (name) => {
    const raw = (state.meta[name] && state.meta[name].label) || name;
    const clean = String(raw).replace(EMOJI_RE, "").replace(/\s+/g, " ").trim();
    return clean || String(name);
  };
  const hasOptions = (task) => !!(task && Array.isArray(task.options) && task.options.length);
  const clone = (value) => {
    try { return JSON.parse(JSON.stringify(value || {})); } catch (e) { return {}; }
  };
  const icon = (name, cls = "") => `<svg class="icon ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

  function setText(id, text) {
    const el = $(id);
    if (!el) return;
    const value = text == null ? "—" : String(text);
    if (el.textContent !== value) el.textContent = value;
  }

  function fmtDuration(sec) {
    if (sec == null || sec === "" || isNaN(Number(sec))) return "—";
    const n = Number(sec);
    if (n < 60) return n.toFixed(1) + "s";
    const m = Math.floor(n / 60);
    const s = Math.round(n % 60);
    return m + "m" + pad(s) + "s";
  }

  function shortNext(value) {
    if (!value) return "—";
    return String(value).replace(/^\d{4}-/, "").replace(" ", "　");
  }

  function loadQueue() {
    try {
      const raw = JSON.parse(localStorage.getItem("ef-queue") || "[]");
      return Array.isArray(raw) ? raw.filter((x) => typeof x === "string") : [];
    } catch (e) {
      return [];
    }
  }

  function saveQueue() {
    try { localStorage.setItem("ef-queue", JSON.stringify(state.queue)); } catch (e) { /* ignore */ }
  }

  const SHOT_RATES = [2000, 1000, 333, 200];

  function loadShotRate() {
    try {
      const saved = Number(localStorage.getItem("ef-shot-rate"));
      if (SHOT_RATES.includes(saved)) return saved;
    } catch (e) { /* ignore */ }
    return 1000;
  }

  function saveShotRate(rate) {
    try { localStorage.setItem("ef-shot-rate", String(rate)); } catch (e) { /* ignore */ }
  }

  function loadPresetId() {
    try { return localStorage.getItem("ef-preset") || "webcloud-full"; } catch (e) { return "webcloud-full"; }
  }

  function savePresetId(id) {
    try { localStorage.setItem("ef-preset", id); } catch (e) { /* ignore */ }
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  function apiUrl(path) {
    const url = new URL(path, location.origin);
    if (TOKEN) url.searchParams.set("token", TOKEN);
    return url;
  }

  async function api(path, options = {}) {
    let response;
    try {
      response = await fetch(apiUrl(path), { cache: "no-store", ...options });
    } catch (e) {
      throw new Error("网络不可达");
    }
    if (response.status === 401) {
      location.replace("/");
      throw new Error("AUTH");
    }
    if (!response.ok) {
      let msg = "HTTP " + response.status;
      try {
        const data = await response.json();
        if (data && data.msg) msg = data.msg;
      } catch (e) { /* keep status */ }
      throw new Error(msg);
    }
    return response.json();
  }

  function post(path, body) {
    return api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : "{}"
    });
  }

  let toastTimer = 0;
  function toast(message, ms = 3400) {
    const el = $("toast");
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), ms);
  }

  function markBooted() {
    const bar = $("loadbar");
    if (!bar || bar.classList.contains("done")) return;
    bar.classList.add("done");
    setTimeout(() => { bar.hidden = true; }, 600);
  }

  function setNetOk(ok, message) {
    state.apiOk = ok;
    $("netAlert").hidden = ok;
    if (!ok) setText("netAlertText", message || "与面板的连接中断");
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
        return true;
      } catch (err) {
        return false;
      }
    }
  }

  /* ---------------- theme ---------------- */
  function applyTheme(value) {
    const theme = value === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("ef-theme", theme); } catch (e) { /* ignore */ }
    setText("railThemeLabel", theme === "light" ? "切换深色" : "切换浅色");
    const mm = $("mmTheme");
    if (mm) mm.textContent = theme === "light" ? "切换深色" : "切换浅色";
  }

  function toggleTheme() {
    applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
  }

  /* ---------------- navigation ---------------- */
  function setActiveNav(id) {
    $$(".rail-item").forEach((a) => {
      if (a.dataset.section === id) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    $$(".mm-item").forEach((a) => {
      if (a.dataset.section === id) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    setText("topTitle", NAV_TITLES[id] || "CONSOLE");
  }

  function updateActiveFromScroll() {
    if (state.navLock) return;
    let current = "live";
    $$("[data-nav]").forEach((section) => {
      if (section.getBoundingClientRect().top <= 150) current = section.id;
    });
    setActiveNav(current);
  }

  function initNav() {
    let queued = false;
    window.addEventListener("scroll", () => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => {
        queued = false;
        updateActiveFromScroll();
      });
    }, { passive: true });
    $$(".rail-item, .mm-item").forEach((a) => {
      a.addEventListener("click", () => {
        const id = a.dataset.section;
        if (id) setActiveNav(id);
        state.navLock = true;
        setTimeout(() => { state.navLock = false; }, 800);
        closeMenu(true);
      });
    });
    updateActiveFromScroll();
  }

  /* ---------------- mobile menu ---------------- */
  function openMenu() {
    const menu = $("mobileMenu");
    if (!menu || state.menuOpen) return;
    if (state.activeModal) closeModal(state.activeModal, true);
    state.menuOpen = true;
    state.menuFocus = document.activeElement;
    menu.hidden = false;
    requestAnimationFrame(() => menu.classList.add("open"));
    document.body.classList.add("modal-open");
    $("mmClose").focus();
  }

  function closeMenu(silent = false) {
    const menu = $("mobileMenu");
    if (!menu || !state.menuOpen) return;
    state.menuOpen = false;
    menu.classList.remove("open");
    clearTimeout(closeTimers.get(menu));
    closeTimers.set(menu, setTimeout(() => { menu.hidden = true; }, 200));
    document.body.classList.remove("modal-open");
    if (!silent && state.menuFocus && typeof state.menuFocus.focus === "function") {
      try { state.menuFocus.focus(); } catch (e) { /* ignore */ }
    }
    state.menuFocus = null;
  }

  /* ---------------- modals ---------------- */
  function focusables(container) {
    return $$('a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])', container)
      .filter((el) => el.offsetParent !== null);
  }

  function openModal(id, trigger) {
    const modal = $(id);
    if (!modal) return;
    if (state.menuOpen) closeMenu(true);
    if (state.activeModal && state.activeModal !== modal) closeModal(state.activeModal, true);
    clearTimeout(closeTimers.get(modal));
    if (!state.activeModal) state.lastFocus = trigger || document.activeElement;
    modal.hidden = false;
    requestAnimationFrame(() => modal.classList.add("open"));
    state.activeModal = modal;
    document.body.classList.add("modal-open");
    const panel = modal.querySelector(".modal-panel") || modal;
    const items = focusables(panel);
    const auto = panel.querySelector("[autofocus]");
    const firstField = panel.querySelector(".modal-body .input, .modal-body input:not([type='checkbox']):not([type='hidden']), .modal-body select, .modal-body textarea");
    (auto || firstField || items[0] || panel).focus?.();
  }

  function closeModal(modal = state.activeModal, silent = false) {
    if (!modal) return;
    if (modal.id === "confirmModal") resolveConfirm(false);
    modal.classList.remove("open");
    clearTimeout(closeTimers.get(modal));
    closeTimers.set(modal, setTimeout(() => { modal.hidden = true; }, 200));
    if (state.activeModal === modal) state.activeModal = null;
    document.body.classList.remove("modal-open");
    if (!silent && state.lastFocus && typeof state.lastFocus.focus === "function") {
      try { state.lastFocus.focus(); } catch (e) { /* ignore */ }
    }
    state.lastFocus = null;
  }

  function askConfirm({ band = "Confirm Action", title, text, note = "", ok = "确认", tone = "danger" }) {
    return new Promise((resolve) => {
      state.confirmResolve = resolve;
      setText("confirmBandTitle", band);
      setText("confirmTitle", title);
      setText("confirmText", text);
      const noteEl = $("confirmNote");
      noteEl.textContent = note;
      noteEl.hidden = !note;
      const okBtn = $("confirmOk");
      okBtn.textContent = ok;
      okBtn.className = "btn " + (tone === "danger" ? "btn-danger" : "btn-control") + " btn-sm";
      openModal("confirmModal");
    });
  }

  function resolveConfirm(value) {
    const resolve = state.confirmResolve;
    state.confirmResolve = null;
    if (resolve) resolve(value);
  }

  /* ---------------- status rendering ---------------- */
  function runTasksOf(status) {
    return (status && Array.isArray(status.run_tasks) && status.run_tasks.length)
      ? status.run_tasks : DAILY;
  }

  function ensureSegments(total) {
    const box = $("progressBar");
    if (box.children.length !== total) {
      box.replaceChildren();
      for (let i = 0; i < total; i++) {
        const seg = document.createElement("span");
        seg.className = "seg";
        seg.setAttribute("aria-hidden", "true");
        box.appendChild(seg);
      }
    }
    return Array.from(box.children);
  }

  function renderTasks(tasks, states, durations) {
    const sig = tasks.join("|") + "#" + JSON.stringify(states) + "#" + JSON.stringify(durations);
    if (sig === state.lastTasksSig) return;
    state.lastTasksSig = sig;
    const frag = document.createDocumentFragment();
    tasks.forEach((key, i) => {
      const st = states[key] || "pending";
      const li = document.createElement("li");
      li.className = "task";
      li.dataset.state = st;

      const ix = document.createElement("span");
      ix.className = "ix";
      ix.textContent = pad(i + 1);

      const nm = document.createElement("span");
      nm.className = "nm";
      const b = document.createElement("b");
      b.textContent = taskLabel(key);
      const em = document.createElement("em");
      em.textContent = taskCode(key);
      nm.append(b, em);

      const stEl = document.createElement("span");
      stEl.className = "st";
      const mark = document.createElement("i");
      mark.className = "mark";
      mark.setAttribute("aria-hidden", "true");
      stEl.append(mark, document.createTextNode((STATE_META[st] || STATE_META.pending).code));

      const dur = document.createElement("span");
      dur.className = "dur";
      dur.textContent = fmtDuration(durations ? durations[key] : null);

      li.append(ix, nm, stEl, dur);
      frag.appendChild(li);
    });
    $("taskList").replaceChildren(frag);
  }

  function classifyLog(line) {
    if (/=====/.test(line)) return "meta";
    if (/\[X\]|Traceback|ERROR|FAIL/i.test(line)) return "err";
    if (/succeeded=False|TIMEOUT|WARN/i.test(line)) return "warn";
    if (/succeeded=True/.test(line)) return "ok";
    return "";
  }

  function renderLog(lines) {
    const sig = (lines || []).join("\u0000");
    if (sig === state.lastLogSig) return;
    state.lastLogSig = sig;
    const body = $("logBody");
    const follow = $("logFollow").checked;
    const nearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 48;
    const frag = document.createDocumentFragment();
    if (!lines || !lines.length) {
      const empty = document.createElement("div");
      empty.className = "log-line meta";
      empty.textContent = "— 暂无日志";
      frag.appendChild(empty);
    } else {
      lines.forEach((line, i) => {
        const row = document.createElement("div");
        row.className = "log-line " + classifyLog(line);
        const no = document.createElement("span");
        no.className = "ln";
        no.textContent = pad(i + 1);
        row.append(no, document.createTextNode(line));
        frag.appendChild(row);
      });
    }
    body.replaceChildren(frag);
    if (follow || nearBottom) body.scrollTop = body.scrollHeight;
  }

  function applyMemory(mem) {
    const total = mem.total_mb;
    const avail = mem.available_mb;
    const used = mem.used_mb != null ? mem.used_mb
      : ((total != null && avail != null) ? Math.max(0, total - avail) : null);
    setText("memState", avail != null ? `${avail} MB FREE` : "--");
    setText("hudMem", avail != null ? `${avail} MB FREE` : "-- MB FREE");
    setText("memAvail", (used != null && total != null)
      ? `USED ${used} MB / ${total} MB · ${avail} MB FREE` : "—");
    setText("statMem", used != null ? `${used} MB` : "—");
    setText("statMemSub", (used != null && total != null)
      ? `${used} / ${total} MB USED · ${avail} MB FREE` : "USED / AVAILABLE");
  }

  function renderStatus() {
    const s = state.status;
    if (!s) return;

    const tasks = runTasksOf(s);
    const states = s.states || {};
    const durations = s.durations || {};
    const running = !!s.running;
    const starting = !!s.starting;
    const busy = running || starting;
    const wasBusy = !!state.wasBusy;
    state.wasBusy = busy;
    if (wasBusy && !busy) loadHistory();
    const success = tasks.filter((t) => states[t] === "success").length;
    const fail = tasks.filter((t) => states[t] === "fail").length;
    const done = success + fail;
    const total = tasks.length;
    const current = s.current;
    const takeover = !!s.takeover;
    applyMaaVersion(s.maa_version || "");

    const ops = $("opsPanel");
    ops.classList.toggle("running", running || starting);
    ops.classList.toggle("failed", !busy && fail > 0);

    if (starting && !running) {
      setText("stateCode", "BOOT");
      setText("stateText", "启动中");
      setText("stateSub", "启动浏览器 / 连接云会话…");
    } else if (running) {
      setText("stateCode", "RUN");
      setText("stateText", "作业中");
      setText("stateSub", current
        ? `${taskLabel(current)} · ${taskCode(current)} / 第 ${tasks.indexOf(current) + 1} 项 · 共 ${pad(total)} 项`
        : "正在调度任务…");
    } else if (takeover) {
      setText("stateCode", "VNC");
      setText("stateText", "手动接管");
      setText("stateSub", "自动任务已暂停，结束接管后回到待命");
    } else if (fail > 0) {
      setText("stateCode", "HOLD");
      setText("stateText", "异常待命");
      setText("stateSub", "上次运行存在失败项，检查日志后重试");
    } else {
      setText("stateCode", "STBY");
      setText("stateText", "待命");
      setText("stateSub", done ? `上次运行完成 ${done} / ${pad(total)} 项` : "等待指令 / 上次运行 —");
    }

    setText("progressText", `${pad(done)} / ${pad(total)}`);
    const segments = ensureSegments(total);
    segments.forEach((seg, i) => {
      const st = states[tasks[i]] || "pending";
      seg.dataset.state = st;
      seg.title = `${pad(i + 1)} ${taskLabel(tasks[i])} — ${(STATE_META[st] || STATE_META.pending).label}`;
    });
    const bar = $("progressBar");
    bar.setAttribute("aria-valuemax", String(total));
    bar.setAttribute("aria-valuenow", String(done));

    setText("lastResult", s.last_result || "—");
    setText("hudTask", running && current ? taskCode(current) : (takeover ? "VNC" : "STBY"));
    setText("chromeState", s.chrome ? "ONLINE" : "OFFLINE");
    setText("chromeState2", s.chrome ? "ONLINE" : "OFFLINE");
    $("linkChip").classList.toggle("on", !!s.chrome);
    $("liveChip").classList.toggle("live", !!s.chrome);
    const chromeTag = $("chromeTag");
    if (chromeTag) {
      chromeTag.textContent = s.chrome ? "ONLINE" : "OFFLINE";
      chromeTag.className = "status-tag " + (s.chrome ? "ok" : "");
    }

    applyMemory(s.mem || {});

    setText("serverTime", s.server_time || "—");
    setText("logFile", basename(s.log_file));
    setText("logSource", basename(s.log_file).toUpperCase().replace(/\.LOG$/, "") || "—");

    renderLog(s.log || []);
    renderTasks(tasks, states, durations);

    setText("statPass", `${success} / ${total}`);
    setText("statPassSub", `OK ${success} · ERR ${fail}`);
    const sched = s.schedule || state.schedule || {};
    setText("statNext", sched.enabled ? shortNext(sched.next) : "OFF");
    setText("statNextSub", sched.enabled ? "AUTO START" : "SCHEDULE DISABLED");
    setText("statUptime", s.uptime != null ? fmtDuration(s.uptime) : "—");
    setText("statUptimeSub", running ? "CURRENT RUN" : "IDLE");

    const startLabel = $("startBtn").querySelector("span");
    const idleLabel = presetActionLabel(currentPreset());
    if (startLabel) startLabel.textContent = starting ? "正在启动…" : (running ? "运行中…" : idleLabel);
    $("startBtn").disabled = busy;
    $("stopBtn").disabled = !(busy || s.chrome || takeover);

    if (state.settings) $("authChk").checked = !!state.settings.auth;

    if (s.schedule) {
      setText("schedNextModal", s.schedule.enabled ? (s.schedule.next || "—") : "已关闭");
      setText("schedSummary", s.schedule.enabled ? (s.schedule.times || []).join(" / ") : "已关闭");
    }
    if (s.game_account) setText("gameAccountName", s.game_account);
    setText("uptime", s.uptime != null ? fmtDuration(s.uptime) : (running ? "RUNNING" : "—"));

    const taking = takeover;
    const takingBoot = !!s.takeover_starting && !taking;
    const tb = $("takeoverBtn");
    tb.classList.toggle("active", taking);
    setText("takeoverLabel", taking ? "结束接管" : (takingBoot ? "启动中…" : "接管控制"));
    const ts = $("takeoverState");
    ts.textContent = taking ? "ONLINE" : (takingBoot ? "BOOT" : "OFFLINE");
    ts.className = "status-tag " + (taking ? "ok" : (takingBoot ? "run" : ""));

    renderQueue();
  }

  /* ---------------- data refresh ---------------- */
  async function refreshStatus(silent = false) {
    try {
      state.status = await api("/api/status");
      setNetOk(true);
      renderStatus();
      document.body.classList.add("ready");
      markBooted();
    } catch (e) {
      if (e.message === "AUTH") return;
      setNetOk(false, "连接失败：" + e.message);
      setText("stateCode", "NO LINK");
      setText("stateText", "连接失败");
      setText("stateSub", "检查服务是否在线");
    }
  }

  async function refreshMe() {
    try {
      state.me = await api("/api/me");
      const me = state.me;
      const admin = me.role === "admin";
      const anonymous = !!me.anonymous;
      setText("userChip", me.token ? "TOKEN" : (me.username || "—"));
      $("userChip").hidden = false;
      $("logoutBtn").hidden = anonymous || !!me.token;
      $("settingsLogout").hidden = anonymous || !!me.token;
      $("mmLogout").hidden = anonymous || !!me.token;
      $("tokenSetting").hidden = !admin;
      $("tokenRow").hidden = !admin;
      $("openAccounts").hidden = !admin;
      $("maaUpdateRow").hidden = !admin;
      $("openPassword").disabled = !!me.token;
      $("securityNote").hidden = !admin;
      setText("loginSummary", anonymous
        ? "开放模式（尚无可登录账号）"
        : `${me.username} · ${me.role}${me.token ? " · token 访问" : ""}`);
    } catch (e) {
      if (e.message !== "AUTH") setNetOk(false, "读取登录状态失败：" + e.message);
    }
  }

  async function refreshSettings() {
    try {
      state.settings = await api("/api/settings");
      $("authChk").checked = !!state.settings.auth;
      if (state.settings.token) setText("tokenText", state.settings.token);
      else setText("tokenText", "—");
    } catch (e) { /* keep last */ }
  }

  async function refreshSchedule(quiet = false) {
    try {
      const s = await api("/api/schedule");
      state.schedule = s;
      if (!quiet || $("scheduleModal").hidden) {
        setText("schedSummary", s.enabled ? (s.times || []).join(" / ") : "已关闭");
        setText("statNext", s.enabled ? shortNext(s.next) : "OFF");
        setText("statNextSub", s.enabled ? "AUTO START" : "SCHEDULE DISABLED");
      }
      if (!$("scheduleModal").hidden) renderSchedule(s);
    } catch (e) { /* keep last */ }
  }

  async function refreshGameAccounts(render = false) {
    try {
      const data = await api("/api/game-accounts");
      state.gameAccounts = data;
      const active = (data.accounts || []).find((a) => a.active);
      setText("gameAccountName", active ? active.name : "—");
      if (render || !$("gameAccountsModal").hidden) renderGameAccounts();
    } catch (e) { /* keep last */ }
  }

  /* ---------------- tasks ---------------- */
  function renderTasksList(tasks, states, durations) {
    renderTasks(tasks, states, durations);
  }

  function applyMaaVersion(value) {
    const raw = String(value || "").trim();
    if (/^v?\d/.test(raw)) state.maaVersion = raw;
    const version = (state.maaVersion || "2.35.0").replace(/^v/i, "");
    const count = state.catalog.length || 49;
    setText("maaStack", `MAAEND v${version}`);
    setText("maaMeta", `MAAEND v${version}`);
    setText("maaFoot", `v${version}`);
    setText("maaMobile", `MAAEND v${version}`);
    setText("maaSettingVersion", `v${version} / ${count} TASKS`);
    setText("libraryIntroCount", String(count));
  }

  async function loadCatalog() {
    try {
      const data = await api("/api/tasks");
      state.catalog = Array.isArray(data.tasks) ? data.tasks : [];
    } catch (e) {
      state.catalog = DAILY.map((name) => ({ name, label: name, group: "web", controllers: ["Linux-Wlroots"] }));
    }
    state.meta = {};
    state.catalog.forEach((t) => { if (t && t.name) state.meta[t.name] = t; });
    const queueSet = new Set(state.catalog.map((t) => t.name).concat(DAILY));
    state.queue = state.queue.filter((n) => queueSet.has(n));
    setText("catalogCount", `${state.catalog.length} TASKS`);
    applyMaaVersion();
    renderLibrary();
    renderQueue();
  }

  /* ---------------- Maa presets ---------------- */
  function currentPreset() {
    return state.presets.find((p) => p.id === state.preset) || null;
  }

  async function loadPresets() {
    try {
      const data = await api("/api/presets");
      state.presets = Array.isArray(data.presets) ? data.presets : [];
    } catch (e) {
      state.presets = [];
    }
    if (!state.presets.some((p) => p.id === state.preset)) {
      const fallback = state.presets.find((p) => p.kind === "panel") || state.presets[0];
      state.preset = fallback ? fallback.id : "";
    }
    renderPresets();
  }

  function selectPreset(id) {
    if (!state.presets.some((p) => p.id === id)) return;
    state.preset = id;
    savePresetId(id);
    renderPresets();
  }

  function presetActionLabel(p) {
    const text = String((p && (p.label || p.name)) || "").replace(/^[^\u4e00-\u9fa5A-Za-z0-9]+/, "");
    return text ? `开始${text}` : "开始全套日常";
  }

  function renderPresets() {
    const grid = $("presetGrid");
    if (!grid) return;
    const current = currentPreset();
    grid.textContent = "";
    state.presets.forEach((p) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "preset-chip" + (p.id === state.preset ? " active" : "");
      btn.dataset.preset = p.id;
      btn.dataset.kind = p.kind || "maa";
      btn.title = p.description || p.label || p.name || "";
      const name = document.createElement("b");
      name.textContent = p.label || p.name || p.id;
      const meta = document.createElement("small");
      const count = p.count || 0;
      meta.textContent = `${count} ${count === 1 ? "TASK" : "TASKS"}${p.long ? " · LONG" : ""}${p.scheduled ? " · SCHEDULED" : ""}`;
      btn.append(name, meta);
      btn.addEventListener("click", () => selectPreset(p.id));
      grid.appendChild(btn);
    });
    setText("presetCount", state.presets.length ? `${state.presets.length} SETS` : "—");
    setText("presetDesc", current ? current.description : "Maa 预设读取失败，将按默认全套日常执行。");
    setText("startNote", current ? (current.note || current.description)
      : "默认全套 11 项，跑完自动收尾；单项失败会继续下一项，不会中断整轮。");
    const startLabel = $("startBtn") && $("startBtn").querySelector("span");
    if (startLabel) startLabel.textContent = presetActionLabel(current);
  }

  /* ---------------- run history ---------------- */
  function fmtHistoryTime(ts) {
    if (!ts) return "—";
    const d = new Date(Number(ts) * 1000);
    if (isNaN(d.getTime())) return "—";
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function fmtLongDuration(sec) {
    if (sec == null || isNaN(Number(sec))) return "—";
    const n = Math.max(0, Number(sec));
    if (n >= 3600) return `${Math.floor(n / 3600)}h${pad(Math.floor((n % 3600) / 60))}m`;
    if (n >= 60) return `${Math.floor(n / 60)}m${pad(Math.round(n % 60))}s`;
    return `${Math.round(n)}s`;
  }

  function historyStatusMeta(run) {
    if (run.status === "running") return { code: "RUN", cls: "running", text: "进行中" };
    if (run.status === "interrupted") return { code: "STOP", cls: "interrupted", text: "已中断" };
    if (run.total && run.fail === 0 && run.success === run.total) {
      return { code: "OK", cls: "ok", text: "完成" };
    }
    if (run.success > 0) return { code: "PART", cls: "partial", text: "部分完成" };
    return { code: "FAIL", cls: "fail", text: "失败" };
  }

  function historyInstanceLabel(instance) {
    const found = state.presets.find((p) => p.id === instance);
    if (found) return found.label;
    return String(instance || "运行").replace(/^preset:/, "");
  }

  function renderHistory() {
    const list = $("historyList");
    if (!list) return;
    const runs = state.history || [];
    setText("historyCount", `${runs.length} RUNS`);

    const finished = runs.filter((r) => r.status !== "running");
    const last = runs[0];
    setText("histLast", last ? fmtHistoryTime(last.started) : "—");
    setText("histLastSub", last ? `${last.total || 0} TASKS · ${last.success || 0} OK` : "NO RUNS");

    const okCount = finished.reduce((sum, r) => sum + (Number(r.success) || 0), 0);
    const totalCount = finished.reduce((sum, r) => sum + (Number(r.total) || 0), 0);
    setText("histRate", totalCount ? `${Math.round(okCount / totalCount * 100)}%` : "—");
    setText("histRateSub", `${finished.length} FINISHED RUNS`);

    const timed = runs.filter((r) => Number(r.duration_seconds) > 0);
    const avg = timed.length
      ? timed.reduce((sum, r) => sum + Number(r.duration_seconds), 0) / timed.length : 0;
    setText("histAvg", avg ? fmtLongDuration(avg) : "—");
    setText("histAvgSub", `${timed.length} TIMED RUNS`);

    const queues = runs.filter((r) => Number(r.queue_seconds) > 0);
    const avgQueue = queues.length
      ? queues.reduce((sum, r) => sum + Number(r.queue_seconds), 0) / queues.length : 0;
    setText("histQueue", avgQueue ? fmtLongDuration(avgQueue) : "—");
    setText("histQueueSub", `${queues.length} WITH QUEUE`);

    list.textContent = "";
    if (!runs.length) {
      const empty = document.createElement("div");
      empty.className = "history-empty";
      empty.textContent = "暂无历史运行记录。完成一次任务后会自动写入。";
      list.appendChild(empty);
      return;
    }

    runs.forEach((run) => {
      const item = document.createElement("details");
      item.className = "run-item";
      const summary = document.createElement("summary");

      const time = document.createElement("span");
      time.className = "run-time";
      time.textContent = fmtHistoryTime(run.started);

      const name = document.createElement("span");
      name.className = "run-name";
      name.textContent = `${historyInstanceLabel(run.instance)} · ${run.total || 0} 项`;

      const queue = document.createElement("span");
      queue.className = "run-queue run-meta";
      queue.title = "排队 / 启动时长";
      queue.textContent = `Q ${fmtLongDuration(run.queue_seconds)}`;

      const dur = document.createElement("span");
      dur.className = "run-dur";
      dur.textContent = `D ${fmtLongDuration(run.duration_seconds)}`;

      const ok = document.createElement("span");
      ok.className = "run-ok";
      ok.textContent = `${run.success || 0}/${run.total || 0}`;

      const meta = historyStatusMeta(run);
      const status = document.createElement("span");
      status.className = `status-tag run-status ${meta.cls}`;
      status.textContent = meta.code;
      status.title = `${meta.text}${run.finished ? " · " + fmtHistoryTime(run.finished) : ""}`;

      summary.append(time, name, queue, dur, ok, status);
      item.appendChild(summary);

      const detail = document.createElement("div");
      detail.className = "run-detail";
      const tasks = Array.isArray(run.tasks) ? run.tasks : [];
      if (!tasks.length) {
        const empty = document.createElement("div");
        empty.className = "run-task-empty";
        empty.textContent = "这次运行没有逐项任务记录。";
        detail.appendChild(empty);
      } else {
        const head = document.createElement("div");
        head.className = "run-task-head";
        ["TASK", "STATE", "TIME", "LAST NODE"].forEach((text) => {
          const cell = document.createElement("span");
          cell.textContent = text;
          head.appendChild(cell);
        });
        detail.appendChild(head);
        tasks.forEach((task) => {
          const row = document.createElement("div");
          row.className = "run-task";
          const taskName = document.createElement("b");
          taskName.textContent = taskLabel(task.name);
          const state = document.createElement("span");
          const stateKey = task.state || "pending";
          const stateText = { success: "OK", fail: "ERR", running: "RUN", pending: "STBY" }[stateKey] || stateKey;
          state.className = `st-${stateKey}`;
          state.textContent = stateText;
          const timeCell = document.createElement("span");
          timeCell.textContent = task.seconds != null ? fmtLongDuration(task.seconds) : "—";
          const node = document.createElement("code");
          node.textContent = task.last_node || (task.timeout ? "TIMEOUT" : "—");
          row.append(taskName, state, timeCell, node);
          detail.appendChild(row);
        });
      }
      item.appendChild(detail);
      list.appendChild(item);
    });
  }

  async function loadHistory() {
    try {
      const data = await api("/api/history?limit=50");
      state.history = Array.isArray(data.runs) ? data.runs : [];
      renderHistory();
    } catch (e) {
      /* keep last */
    }
  }

  function renderLibrary(filter = "") {
    const box = $("taskLibrary");
    const frag = document.createDocumentFragment();
    const f = String(filter || "").trim().toLowerCase();
    const groups = new Map();
    state.catalog.forEach((t) => {
      const hay = [t.label, t.name, t.description].join(" ").toLowerCase();
      if (f && !hay.includes(f)) return;
      const g = t.group || "other";
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(t);
    });
    if (!groups.size) {
      const empty = document.createElement("div");
      empty.className = "queue-empty";
      empty.style.padding = "18px 14px";
      empty.textContent = f ? "没有匹配的任务。" : "任务库加载中…";
      frag.appendChild(empty);
    }
    groups.forEach((items, group) => {
      const section = document.createElement("div");
      section.className = "lib-group";
      const title = document.createElement("div");
      title.className = "lib-group-title";
      title.textContent = GROUP_LABELS[group] || group.toUpperCase();
      section.appendChild(title);
      items.forEach((t) => {
        const row = document.createElement("div");
        row.className = "lib-task";
        const main = document.createElement("label");
        main.className = "lib-main";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.className = "check";
        cb.checked = state.queue.includes(t.name);
        cb.addEventListener("change", () => {
          if (cb.checked) {
            if (!state.queue.includes(t.name)) state.queue.push(t.name);
          } else {
            state.queue = state.queue.filter((x) => x !== t.name);
          }
          saveQueue();
          renderQueue();
        });
        const label = document.createElement("span");
        label.className = "label";
        const b = document.createElement("b");
        b.textContent = taskLabel(t.name);
        const em = document.createElement("em");
        em.textContent = t.name;
        label.append(b, em);
        const grp = document.createElement("span");
        grp.className = "grp";
        grp.textContent = (t.controllers || []).includes("Linux-Wlroots") ? "WLROOTS" : "ALL";
        main.append(cb, label);
        row.append(main, grp);
        if (hasOptions(t)) {
          const gear = document.createElement("button");
          gear.type = "button";
          gear.className = "task-settings";
          gear.setAttribute("aria-label", "设置 " + taskLabel(t.name));
          gear.innerHTML = icon("settings", "icon-sm");
          gear.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            openTaskOptions(t.name, gear);
          });
          row.appendChild(gear);
        }
        section.appendChild(row);
      });
      frag.appendChild(section);
    });
    box.replaceChildren(frag);
  }

  function selectedCaseNames(opt) {
    const value = state.optionValues[opt.key] || {};
    if (opt.type === "switch") {
      if (value.value !== undefined && value.value !== null) return [value.value ? "Yes" : "No"];
      return opt.default ? [opt.default] : [];
    }
    if (opt.type === "select") {
      const one = value.caseName || opt.default;
      return one ? [one] : [];
    }
    if (opt.type === "checkbox") {
      let picked = value.caseNames;
      if (picked == null) picked = opt.default;
      if (typeof picked === "string") picked = [picked];
      return Array.isArray(picked) ? picked : [];
    }
    return [];
  }

  function buildOptionGroup(opt, seen, depth) {
    const group = document.createElement("div");
    group.className = "option-group" + (depth ? " depth-" + Math.min(depth, 3) : "");

    const head = document.createElement("div");
    head.className = "option-head";
    const copy = document.createElement("div");
    const label = document.createElement("div");
    label.className = "option-label";
    label.textContent = opt.label || opt.key;
    const key = document.createElement("span");
    key.className = "option-key";
    key.textContent = opt.key;
    label.appendChild(key);
    copy.appendChild(label);
    if (opt.description) {
      const desc = document.createElement("p");
      desc.className = "option-desc";
      desc.textContent = opt.description;
      copy.appendChild(desc);
    }
    head.appendChild(copy);

    const control = document.createElement("div");
    control.className = "option-control";
    const children = document.createElement("div");
    children.className = "option-children";

    const refreshChildren = () => {
      children.replaceChildren();
      const picked = selectedCaseNames(opt);
      const rendered = new Set();
      picked.forEach((caseName) => {
        const item = (opt.cases || []).find((c) => c.name === caseName);
        if (!item) return;
        (item.options || []).forEach((child) => {
          if (!child || !child.key || seen.has(child.key) || rendered.has(child.key)) return;
          rendered.add(child.key);
          children.appendChild(buildOptionGroup(child, new Set(seen).add(child.key), depth + 1));
        });
      });
    };

    if (opt.type === "switch") {
      const wrap = document.createElement("label");
      wrap.className = "switch";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = selectedCaseNames(opt)[0] === "Yes";
      const stateText = document.createElement("span");
      stateText.className = "micro";
      stateText.textContent = input.checked ? "ON" : "OFF";
      input.addEventListener("change", () => {
        state.optionValues[opt.key] = { type: "switch", value: !!input.checked };
        stateText.textContent = input.checked ? "ON" : "OFF";
        refreshChildren();
      });
      const track = document.createElement("span");
      track.className = "track";
      const knob = document.createElement("span");
      knob.className = "knob";
      track.appendChild(knob);
      wrap.append(input, track);
      control.append(wrap, stateText);
    } else if (opt.type === "select") {
      const select = document.createElement("select");
      select.className = "option-select";
      (opt.cases || []).forEach((item) => {
        const option = document.createElement("option");
        option.value = item.name;
        option.textContent = item.label || item.name;
        if (selectedCaseNames(opt).includes(item.name)) option.selected = true;
        select.appendChild(option);
      });
      if (!opt.cases || !opt.cases.length) {
        const option = document.createElement("option");
        option.textContent = "无可选项";
        select.appendChild(option);
      }
      select.addEventListener("change", () => {
        state.optionValues[opt.key] = { type: "select", caseName: select.value };
        refreshChildren();
      });
      control.appendChild(select);
    } else if (opt.type === "checkbox") {
      const wrap = document.createElement("div");
      wrap.className = "option-check";
      const picked = selectedCaseNames(opt);
      (opt.cases || []).forEach((item) => {
        const row = document.createElement("label");
        const input = document.createElement("input");
        input.type = "checkbox";
        input.className = "check";
        input.checked = picked.includes(item.name);
        input.addEventListener("change", () => {
          const names = Array.from(wrap.querySelectorAll("input:checked"))
            .map((el) => el.dataset.caseName)
            .filter(Boolean);
          state.optionValues[opt.key] = { type: "checkbox", caseNames: names };
          refreshChildren();
        });
        input.dataset.caseName = item.name;
        const text = document.createElement("span");
        text.textContent = item.label || item.name;
        row.append(input, text);
        wrap.appendChild(row);
      });
      control.appendChild(wrap);
    } else if (opt.type === "input" || opt.type === "hotkey") {
      const current = (state.optionValues[opt.key] || {}).values || {};
      (opt.inputs || []).forEach((item) => {
        const row = document.createElement("label");
        row.className = "field";
        row.style.margin = "0";
        const text = document.createElement("span");
        text.className = "field-label";
        text.textContent = item.label || item.name;
        const input = document.createElement("input");
        input.className = "option-input";
        input.value = current[item.name] !== undefined ? current[item.name] : (item.default != null ? item.default : "");
        input.placeholder = item.default != null ? String(item.default) : "";
        if (/^(int|float)$/.test(item.pipeline_type || "")) input.inputMode = "decimal";
        if (item.verify) input.title = item.verify;
        input.addEventListener("input", () => {
          const values = Object.assign({}, (state.optionValues[opt.key] || {}).values || {});
          values[item.name] = input.value;
          state.optionValues[opt.key] = { type: "input", values };
        });
        row.append(text, input);
        control.appendChild(row);
      });
    } else {
      const note = document.createElement("span");
      note.className = "option-empty";
      note.textContent = opt.type === "cycle" ? "循环引用，已跳过" : "该选项类型暂不支持编辑（" + (opt.type || "unknown") + "）";
      control.appendChild(note);
    }

    group.append(head, control, children);
    refreshChildren();
    return group;
  }

  function renderTaskOptions() {
    const task = state.optionTask;
    const form = $("taskOptionsForm");
    if (!task || !form) return;
    form.replaceChildren();
    if (!hasOptions(task)) {
      const empty = document.createElement("div");
      empty.className = "option-empty";
      empty.textContent = "这个任务没有可配置选项。";
      form.appendChild(empty);
      return;
    }
    task.options.forEach((opt) => {
      if (opt && opt.key) form.appendChild(buildOptionGroup(opt, new Set([opt.key]), 0));
    });
  }

  function openTaskOptions(name, trigger) {
    const task = state.catalog.find((t) => t && t.name === name);
    if (!task || !hasOptions(task)) return;
    state.optionTask = task;
    state.optionValues = clone(task.optionValues || {});
    setText("taskOptionsTitle", "Task Options / " + taskLabel(name));
    setText("taskOptionsDesc", task.description || "与 MXU 使用同一份 optionValues；保存后下一次任务生效。");
    renderTaskOptions();
    openModal("taskOptionsModal", trigger);
  }

  async function saveTaskOptions() {
    if (!state.optionTask) return;
    const btn = $("saveTaskOptions");
    btn.disabled = true;
    try {
      const data = await post("/api/task-options", {
        task: state.optionTask.name,
        optionValues: state.optionValues
      });
      if (data.ok) {
        state.optionTask.optionValues = clone(state.optionValues);
        closeModal($("taskOptionsModal"));
        toast("任务设置已保存");
      } else {
        toast("保存失败：" + (data.msg || "未知原因"), 5000);
      }
    } catch (e) {
      toast("保存失败：" + e.message, 5000);
    } finally {
      btn.disabled = false;
    }
  }

  function renderQueue() {
    const busy = !!(state.status && (state.status.running || state.status.starting));
    const sig = state.queue.join("|") + "#" + busy + "#" + state.catalog.length;
    if (sig === state.lastQueueSig) return;
    state.lastQueueSig = sig;
    const box = $("queueChips");
    const frag = document.createDocumentFragment();
    setText("queueCount", pad(state.queue.length));
    if (!state.queue.length) {
      const empty = document.createElement("div");
      empty.className = "queue-empty";
      empty.textContent = "未选择任务。从左侧任务库勾选后点「执行待选」。";
      frag.appendChild(empty);
    } else {
      state.queue.forEach((name) => {
        const chip = document.createElement("span");
        chip.className = "qchip";
        const label = document.createElement("span");
        label.textContent = taskLabel(name);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.setAttribute("aria-label", "移除 " + taskLabel(name));
        btn.textContent = "×";
        btn.addEventListener("click", () => {
          state.queue = state.queue.filter((x) => x !== name);
          saveQueue();
          renderQueue();
          renderLibrary($("taskSearch").value);
        });
        chip.append(label, btn);
        frag.appendChild(chip);
      });
    }
    box.replaceChildren(frag);
    const btn = $("runQueue");
    btn.disabled = busy || state.queue.length === 0;
    const span = btn.querySelector("span");
    if (span) span.textContent = busy ? "任务运行中" : "执行待选任务";
  }

  /* ---------------- log ---------------- */
  function bindLog() {
    $("logFollow").addEventListener("change", () => {
      if ($("logFollow").checked) $("logBody").scrollTop = $("logBody").scrollHeight;
    });
    $("logCopy").addEventListener("click", async () => {
      const lines = (state.status && state.status.log) || [];
      if (!lines.length) { toast("暂无日志可复制"); return; }
      const ok = await copyText(lines.join("\n"));
      toast(ok ? "日志已复制" : "复制失败，请手动选择文本");
    });
  }

  /* ---------------- schedule ---------------- */
  function addTimeRow(value) {
    const row = document.createElement("div");
    row.className = "time-row";
    const input = document.createElement("input");
    input.className = "input";
    input.type = "text";
    input.inputMode = "numeric";
    input.maxLength = 5;
    input.placeholder = "04:00";
    input.value = value || "12:00";
    input.setAttribute("aria-label", "自动启动时间（HH:MM）");
    const del = document.createElement("button");
    del.type = "button";
    del.className = "btn-icon";
    del.setAttribute("aria-label", "移除这个时间");
    del.innerHTML = icon("close", "icon-sm");
    del.addEventListener("click", () => {
      row.remove();
      if (!$("schedTimes").children.length) addTimeRow("04:00");
    });
    row.append(input, del);
    $("schedTimes").appendChild(row);
  }

  function renderSchedule(s) {
    state.schedule = s;
    $("schedChk").checked = !!s.enabled;
    const box = $("schedTimes");
    box.replaceChildren();
    (s.times || []).forEach(addTimeRow);
    if (!box.children.length) addTimeRow("04:00");
    setText("schedNextModal", s.enabled ? (s.next || "—") : "已关闭");
    setText("schedSummary", s.enabled ? (s.times || []).join(" / ") : "已关闭");
  }

  async function openSchedule() {
    try {
      const s = await api("/api/schedule");
      state.schedule = s;
      renderSchedule(s);
    } catch (e) {
      toast("读取定时失败：" + e.message, 5000);
      return;
    }
    openModal("scheduleModal");
  }

  function scheduleTimes() {
    const raw = $$("#schedTimes input").map((el) => el.value.trim()).filter(Boolean);
    const bad = raw.filter((v) => !/^([01]?\d|2[0-3]):[0-5]\d$/.test(v));
    if (bad.length) {
      toast("时间格式应为 HH:MM：" + bad.join(" / "), 5000);
      return null;
    }
    return Array.from(new Set(raw.map((v) => {
      const parts = v.split(":");
      return pad(Number(parts[0])) + ":" + parts[1];
    }))).sort();
  }

  async function saveSchedule() {
    const enabled = $("schedChk").checked;
    const times = scheduleTimes();
    if (times === null) return;
    if (enabled && !times.length) { toast("至少保留一个启动时间"); return; }
    const btn = $("saveSched");
    btn.disabled = true;
    try {
      const data = await post("/api/schedule", { enabled, times });
      if (data.ok) {
        renderSchedule(data);
        toast(enabled ? "定时已保存" : "定时已关闭");
        await refreshStatus(true);
      } else {
        toast("保存失败：" + (data.msg || "未知原因"), 5000);
      }
    } catch (e) {
      toast("保存失败：" + e.message, 5000);
    } finally {
      btn.disabled = false;
    }
  }

  /* ---------------- game accounts ---------------- */
  function renderGameAccounts() {
    const box = $("gameAccountsList");
    box.replaceChildren();
    const accounts = state.gameAccounts.accounts || [];
    if (!accounts.length) {
      const empty = document.createElement("div");
      empty.className = "account-empty";
      empty.textContent = "尚未配置云账号。";
      box.appendChild(empty);
      return;
    }
    accounts.forEach((acct) => {
      const row = document.createElement("div");
      row.className = "account-item" + (acct.active ? " active" : "");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = acct.name;
      const role = document.createElement("span");
      role.className = "role";
      role.textContent = acct.active ? "当前" : (acct.exists ? "已保存" : "待登录");
      const acts = document.createElement("span");
      acts.className = "acts";

      if (acct.active) {
        const open = document.createElement("button");
        open.type = "button";
        open.className = "btn btn-control";
        open.textContent = "打开接管";
        open.addEventListener("click", () => {
          closeGameAccounts();
          startTakeoverFlow({ path: "/api/takeover", body: {}, label: "正在打开接管画面…" });
        });
        acts.appendChild(open);

        const out = document.createElement("button");
        out.type = "button";
        out.className = "btn btn-text";
        out.textContent = "退出登录";
        out.addEventListener("click", async () => {
          const ok = await askConfirm({
            title: "退出云游戏登录？",
            text: "会停止当前任务、清除该账号的云登录状态，并打开登录页。",
            ok: "退出登录"
          });
          if (!ok) { openGameAccounts(); return; }
          closeGameAccounts();
          startTakeoverFlow({ path: "/api/game-accounts/logout", body: {}, label: "正在退出登录并打开登录页…" });
        });
        acts.appendChild(out);
      } else {
        const sw = document.createElement("button");
        sw.type = "button";
        sw.className = "btn btn-control";
        sw.textContent = "切换 / 登录";
        sw.addEventListener("click", async () => {
          const ok = await askConfirm({
            title: "切换云账号？",
            text: "会停止当前任务，并打开 " + acct.name + " 的云页面。",
            ok: "切换账号"
          });
          if (!ok) { openGameAccounts(); return; }
          closeGameAccounts();
          startTakeoverFlow({
            path: "/api/game-accounts/switch",
            body: { id: acct.id },
            label: "正在切换账号并打开云页面…"
          });
        });
        acts.appendChild(sw);

        if (acct.id !== "default") {
          const del = document.createElement("button");
          del.type = "button";
          del.className = "btn btn-text";
          del.textContent = "删除";
          del.addEventListener("click", async () => {
            const ok = await askConfirm({
              title: "删除云账号？",
              text: "会删除 " + acct.name + " 的本地 Chrome 配置，不影响云游戏账号本身。",
              ok: "删除"
            });
            if (!ok) { openGameAccounts(); return; }
            closeGameAccounts();
            startTakeoverFlow({
              path: "/api/game-accounts/delete",
              body: { id: acct.id },
              label: "正在删除账号…"
            });
          });
          acts.appendChild(del);
        }
      }
      row.append(name, role, acts);
      box.appendChild(row);
    });
  }

  function closeGameAccounts() {
    closeModal($("gameAccountsModal"), true);
  }

  async function openGameAccounts() {
    await refreshGameAccounts(true);
    openModal("gameAccountsModal");
  }

  async function addGameAccount() {
    const name = $("gameAccountInput").value.trim();
    if (!name) { toast("请填写账号备注名"); return; }
    const ok = await askConfirm({
      title: "添加云账号？",
      text: "会停止当前任务并打开新的登录页面；请在接管画面扫码 / 登录。",
      ok: "添加并登录"
    });
    if (!ok) { openGameAccounts(); return; }
    closeGameAccounts();
    startTakeoverFlow({
      path: "/api/game-accounts/add",
      body: { name },
      label: "正在创建账号并打开登录页…"
    });
  }

  /* ---------------- takeover flow ---------------- */
  function writePopupLoading(win, text) {
    if (!win) return;
    try {
      const doc = win.document;
      doc.open();
      doc.write(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>ENDFIELD // CONNECTING</title>
<style>
html,body{height:100%;margin:0;background:#141414;color:#fafafa;font-family:system-ui,sans-serif}
body{display:grid;place-items:center}
.box{width:min(420px,86vw)}
.mark{width:32px;height:36px;background:#fafafa;position:relative;margin-bottom:24px}
.mark::after{content:"";position:absolute;left:7px;top:9px;width:4px;height:18px;background:#fffa00}
.t{font:500 10px/1.4 "Space Grotesk",monospace;letter-spacing:.12em;color:#8a8a8a;text-transform:uppercase}
.m{font:800 30px/1 system-ui;letter-spacing:.02em;margin:8px 0 20px}
.bar{height:6px;background:#282828;overflow:hidden}
.bar i{display:block;width:38%;height:100%;background:#fffa00;animation:x 1.2s ease-in-out infinite alternate}
@keyframes x{from{transform:translateX(-60%)}to{transform:translateX(260%)}}
</style></head><body><div class="box"><div class="mark"></div><div class="t">// MANUAL TAKEOVER</div>
<div class="m">正在准备画面</div><div class="t">${escapeHtml(text)}</div><div class="bar"><i></i></div></div></body></html>`);
      doc.close();
    } catch (e) { /* ignore */ }
  }

  function resetTakeoverModal(label) {
    state.takeoverUrl = "";
    $("takeoverTag").className = "status-tag run";
    $("takeoverTag").textContent = "BOOT";
    setText("takeoverCode", "00:00");
    setText("takeoverText", label || "正在准备接管画面…");
    $("cancelTakeover").hidden = false;
    $("cancelTakeover").disabled = false;
    $("retryTakeover").hidden = true;
    $("closeTakeoverModal").hidden = true;
  }

  function failTakeover(message) {
    $("takeoverTag").className = "status-tag bad";
    $("takeoverTag").textContent = "ERR";
    setText("takeoverCode", "—");
    setText("takeoverText", "启动失败：" + (message || "未知原因"));
    $("cancelTakeover").hidden = true;
    $("retryTakeover").hidden = false;
    $("retryTakeover").textContent = "重试";
    $("closeTakeoverModal").hidden = false;
  }

  async function startTakeoverFlow(opts) {
    if (state.takeoverBusy) { toast("接管正在启动或停止，请稍候"); return; }
    state.takeoverBusy = true;
    state.takeoverCancelled = false;
    state.lastTakeoverOpts = opts;
    resetTakeoverModal(opts.label);
    openModal("takeoverModal");

    const win = window.open("", "_blank");
    state.takeoverPopup = win;
    if (win) writePopupLoading(win, "正在启动 Chrome / Wayland / VNC…");

    state.takeoverStart = Date.now();
    clearInterval(state.takeoverTimer);
    state.takeoverTimer = setInterval(() => {
      const sec = Math.floor((Date.now() - state.takeoverStart) / 1000);
      setText("takeoverCode", pad(Math.floor(sec / 60)) + ":" + pad(sec % 60));
    }, 250);

    try {
      const data = await post(opts.path, opts.body || {});
      if (state.takeoverCancelled) {
        if (win) { try { win.close(); } catch (e) { /* ignore */ } }
        state.takeoverPopup = null;
        closeModal($("takeoverModal"), true);
        toast("已取消接管启动");
        return;
      }
      if (data.ok && data.url) {
        if (win) {
          try { win.opener = null; win.location.href = data.url; } catch (e) { win = null; }
        }
        if (win) {
          state.takeoverPopup = null;
          closeModal($("takeoverModal"), true);
          toast("接管已开启（画面若未刷新，移动一下鼠标）", 6000);
        } else {
          state.takeoverUrl = data.url;
          $("takeoverTag").className = "status-tag ok";
          $("takeoverTag").textContent = "OK";
          setText("takeoverCode", "READY");
          setText("takeoverText", "接管已就绪，但新窗口被浏览器拦截。点击「打开画面」继续。");
          $("cancelTakeover").hidden = true;
          $("retryTakeover").hidden = false;
          $("retryTakeover").textContent = "打开画面";
          $("closeTakeoverModal").hidden = false;
        }
        await refreshGameAccounts();
        await refreshStatus(true);
      } else {
        if (win) { try { win.close(); } catch (e) { /* ignore */ } }
        state.takeoverPopup = null;
        failTakeover(data.msg || "未知原因");
        toast("接管失败：" + (data.msg || "未知原因"), 5000);
      }
    } catch (e) {
      if (win) { try { win.close(); } catch (err) { /* ignore */ } }
      state.takeoverPopup = null;
      if (!state.takeoverCancelled) failTakeover(e.message);
    } finally {
      clearInterval(state.takeoverTimer);
      state.takeoverTimer = 0;
      state.takeoverBusy = false;
    }
  }

  async function cancelTakeover() {
    if (!state.takeoverBusy) return;
    state.takeoverCancelled = true;
    $("cancelTakeover").disabled = true;
    setText("takeoverText", "正在取消启动，等待进程退出…");
    try { await post("/api/takeover/stop"); } catch (e) { /* start request will surface it */ }
  }

  function retryTakeover() {
    if (state.takeoverUrl) {
      window.open(state.takeoverUrl, "_blank");
      return;
    }
    const opts = state.lastTakeoverOpts;
    closeModal($("takeoverModal"), true);
    if (opts) setTimeout(() => startTakeoverFlow(opts), 60);
  }

  function closeTakeoverModal() {
    if (state.takeoverPopup) {
      try { state.takeoverPopup.close(); } catch (e) { /* ignore */ }
      state.takeoverPopup = null;
    }
    closeModal($("takeoverModal"), true);
  }

  function toggleTakeover() {
    const s = state.status || {};
    const active = !!s.takeover;
    if (active) {
      askConfirm({
        title: "结束接管？",
        text: "会关闭 noVNC 画面。自动任务保持暂停，需要时再手动开始。",
        ok: "结束接管"
      }).then((ok) => {
        if (!ok) return;
        post("/api/takeover/stop").then(() => {
          toast("已结束接管");
          setTimeout(() => refreshStatus(true), 600);
        }).catch((e) => toast("结束失败：" + e.message));
      });
      return;
    }
    const busy = !!(s.busy || s.running || s.starting);
    if (busy) {
      askConfirm({
        title: "接管会先停止自动任务",
        text: "手动接管需要暂停自动作业，继续？",
        ok: "暂停并接管"
      }).then((ok) => {
        if (!ok) return;
        startTakeoverFlow({ path: "/api/takeover", body: {}, label: "正在停止任务并准备接管画面…" });
      });
    } else {
      startTakeoverFlow({ path: "/api/takeover", body: {}, label: "正在启动 Chrome / Wayland / VNC…" });
    }
  }

  /* ---------------- start / stop ---------------- */
  async function startDaily() {
    if ($("startBtn").disabled) return;
    $("startBtn").disabled = true;
    const preset = currentPreset();
    const startLabel = $("startBtn").querySelector("span");
    if (startLabel) startLabel.textContent = "正在启动…";
    try {
      const data = await post("/api/start", preset ? { preset: preset.id } : {});
      const label = preset ? preset.label : "全套日常";
      toast(data.ok ? `${label}已启动` : "未启动：" + (data.msg || "未知原因"));
      setTimeout(() => refreshStatus(true), 900);
    } catch (e) {
      if (startLabel) startLabel.textContent = presetActionLabel(preset);
      toast("启动失败：" + e.message, 5000);
      $("startBtn").disabled = false;
    }
  }

  async function stopDaily() {
    const ok = await askConfirm({
      title: "确认停止？",
      text: "停止会结束云会话、关闭浏览器与合成器，当前任务不会完成。",
      ok: "停止作业"
    });
    if (!ok) return;
    try {
      await post("/api/stop");
      toast("已发送停止指令");
      setTimeout(() => refreshStatus(true), 900);
    } catch (e) {
      toast("停止失败：" + e.message, 5000);
    }
  }

  /* ---------------- queue actions ---------------- */
  async function runQueue() {
    if ($("runQueue").disabled || !state.queue.length) return;
    if (state.status && (state.status.running || state.status.starting)) {
      toast("任务正在运行，先停止或等待完成");
      return;
    }
    try {
      const data = await post("/api/run", { tasks: state.queue });
      if (data.ok) {
        toast(`待选任务已启动（${state.queue.length} 项）`);
        setTimeout(() => refreshStatus(true), 900);
      } else {
        toast("未启动：" + (data.msg || "未知原因"), 5000);
      }
    } catch (e) {
      toast("启动失败：" + e.message, 5000);
    }
  }

  /* ---------------- panel users ---------------- */
  function renderUsers() {
    const box = $("accountsList");
    box.replaceChildren();
    if (!state.users.length) {
      const empty = document.createElement("div");
      empty.className = "account-empty";
      empty.textContent = "暂无账号。";
      box.appendChild(empty);
      return;
    }
    state.users.forEach((user) => {
      const row = document.createElement("div");
      row.className = "account-item";
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = user.username;
      const role = document.createElement("span");
      role.className = "role";
      role.textContent = String(user.role || "user").toUpperCase();
      row.append(name, role);
      if (user.username !== (state.me && state.me.username)) {
        const acts = document.createElement("span");
        acts.className = "acts";
        const del = document.createElement("button");
        del.type = "button";
        del.className = "btn btn-text";
        del.textContent = "删除";
        del.addEventListener("click", async () => {
          const ok = await askConfirm({
            title: "删除账号？",
            text: "删除后该账号将无法登录，确定删除 " + user.username + "？",
            ok: "删除"
          });
          if (!ok) return;
          try {
            const data = await post("/api/users/delete", { username: user.username });
            if (data.ok) { toast("账号已删除"); loadUsers(); }
            else toast("删除失败：" + (data.msg || "未知原因"), 5000);
          } catch (e) {
            toast("删除失败：" + e.message, 5000);
          }
        });
        acts.appendChild(del);
        row.appendChild(acts);
      }
      box.appendChild(row);
    });
  }

  async function loadUsers() {
    if (!state.me || state.me.role !== "admin") return;
    try {
      const data = await api("/api/users");
      state.users = data.users || [];
      renderUsers();
    } catch (e) {
      toast("读取账号失败：" + e.message, 5000);
    }
  }

  async function openAccounts() {
    if (!state.me || state.me.role !== "admin") return;
    await loadUsers();
    openModal("accountsModal");
  }

  async function addAccount() {
    const username = $("newUsername").value.trim();
    const password = $("newPassword").value;
    if (!username || password.length < 8) {
      toast("用户名必填，密码至少 8 位");
      return;
    }
    const btn = $("addAccount");
    btn.disabled = true;
    try {
      const data = await post("/api/users", { username, password });
      if (data.ok) {
        $("newUsername").value = "";
        $("newPassword").value = "";
        toast("账号已添加");
        loadUsers();
      } else {
        toast("添加失败：" + (data.msg || "未知原因"), 5000);
      }
    } catch (e) {
      toast("添加失败：" + e.message, 5000);
    } finally {
      btn.disabled = false;
    }
  }

  /* ---------------- password / token ---------------- */
  function openPassword() {
    if (state.me && state.me.token) { toast("token 访问不能修改密码"); return; }
    $("oldPassword").value = "";
    $("newPassword1").value = "";
    $("newPassword2").value = "";
    setText("passwordErr", "");
    openModal("passwordModal");
  }

  async function changePassword() {
    const oldPw = $("oldPassword").value;
    const newPw = $("newPassword1").value;
    const again = $("newPassword2").value;
    setText("passwordErr", "");
    if (!oldPw) { setText("passwordErr", "请输入当前密码"); return; }
    if (newPw.length < 8) { setText("passwordErr", "新密码至少 8 位"); return; }
    if (newPw !== again) { setText("passwordErr", "两次输入的新密码不一致"); return; }
    const btn = $("changePassword");
    btn.disabled = true;
    try {
      const data = await post("/api/password", { old: oldPw, new: newPw });
      if (data.ok) {
        closeModal($("passwordModal"));
        toast("密码已修改");
      } else {
        setText("passwordErr", data.msg || "修改失败");
      }
    } catch (e) {
      setText("passwordErr", "修改失败：" + e.message);
    } finally {
      btn.disabled = false;
    }
  }

  async function toggleAuth() {
    if (!state.settings) return;
    const enabled = $("authChk").checked;
    $("authChk").disabled = true;
    try {
      const data = await post("/api/auth", { enabled });
      state.settings.auth = !!data.auth;
      if (data.token) setText("tokenText", data.token);
      toast(enabled ? "已开启 token 后备访问" : "已关闭 token 后备访问");
    } catch (e) {
      $("authChk").checked = !enabled;
      toast("设置失败：" + e.message, 5000);
    } finally {
      $("authChk").disabled = false;
    }
  }

  async function rotateToken() {
    const ok = await askConfirm({
      title: "轮换访问 token？",
      text: "旧 token 会立即失效。已经登录的会话不受影响。",
      ok: "轮换 token"
    });
    if (!ok) return;
    try {
      const data = await post("/api/token/rotate", {});
      if (data.ok) {
        setText("tokenText", data.token);
        toast("token 已轮换");
      }
    } catch (e) {
      toast("轮换失败：" + e.message, 5000);
    }
  }

  async function refreshMaaInfo() {
    if (!state.me || state.me.role !== "admin") {
      $("maaUpdateRow").hidden = true;
      return;
    }
    $("maaUpdateRow").hidden = false;
    try {
      const data = await api("/api/maa/info");
      state.maa = data;
      setText("maaVersion", data.current || "—");
      setText("maaLatest", data.latest || "未检查");
      applyMaaVersion(data.current || "");
      const job = data.job || {};
      let message = job.message || "";
      if (!message && data.busy) message = "Maa 正在运行；更新需要先停止任务";
      setText("maaUpdateMsg", message || "—");
      $("maaUpdate").disabled = job.state === "running" || !!data.busy || !!data.takeover;
      $("maaCheck").disabled = job.state === "running";
    } catch (e) {
      /* keep last value */
    }
  }

  async function checkMaaUpdate() {
    const btn = $("maaCheck");
    btn.disabled = true;
    try {
      const data = await post("/api/maa/check", {});
      if (data.ok) {
        setText("maaLatest", data.latest || "—");
        setText("maaUpdateMsg", data.latest && data.latest !== data.current ? "有可用更新" : "已是最新");
        toast("最新 Maa 版本：" + (data.latest || "未知"));
        await refreshMaaInfo();
      } else {
        setText("maaUpdateMsg", data.error || "检查失败");
        toast("检查更新失败：" + (data.error || "网络不可用"), 5000);
      }
    } catch (e) {
      toast("检查更新失败：" + e.message, 5000);
    } finally {
      btn.disabled = false;
    }
  }

  function openMaaUpdateModal() {
    setText("maaUpdateStatus", "准备更新…");
    $("maaUpdateLog").textContent = "—";
    $("maaUpdateReload").hidden = true;
    openModal("maaUpdateModal");
  }

  async function startMaaUpdate() {
    const ok = await askConfirm({
      title: "更新 Maa？",
      text: "会下载最新版并替换 resource / interface / agent / maafw。更新期间不能运行任务；脚本会先备份，失败自动回滚。",
      ok: "开始更新"
    });
    if (!ok) return;
    try {
      const data = await post("/api/maa/update", {});
      if (!data.ok) {
        toast("未启动：" + (data.msg || "未知原因"), 5000);
        return;
      }
      openMaaUpdateModal();
      pollMaaUpdate();
    } catch (e) {
      toast("更新启动失败：" + e.message, 5000);
    }
  }

  async function pollMaaUpdate() {
    clearInterval(state.maaPoll);
    const tick = async () => {
      try {
        const job = await api("/api/maa/update/status");
        const message = job.message || job.state || "更新中…";
        setText("maaUpdateStatus", message);
        const lines = (job.log || []).slice(-40);
        if (job.output) lines.push(job.output);
        $("maaUpdateLog").textContent = lines.join("\n") || "—";
        if (job.state !== "running") {
          clearInterval(state.maaPoll);
          state.maaPoll = 0;
          $("maaUpdateReload").hidden = false;
          await refreshMaaInfo();
          if (job.state === "done" && job.after && job.after !== job.before) {
            setText("maaUpdateStatus", "更新完成：" + message + "。正在刷新面板…");
            setTimeout(() => location.reload(), 1800);
          } else if (job.state === "error") {
            toast(message || "更新失败", 6000);
          } else {
            toast(message || "Maa 已是最新");
          }
        }
      } catch (e) {
        /* keep polling */
      }
    };
    await tick();
    state.maaPoll = setInterval(tick, 2000);
  }

  async function logout() {
    try { await post("/api/logout"); } catch (e) { /* ignore */ }
    location.replace("/");
  }

  /* ---------------- screenshot ---------------- */
  function setFrame(visible) {
    state.hasFrame = visible;
    $("viewport").classList.toggle("has-frame", visible);
  }

  function refreshShot() {
    if (document.hidden || state.shotBusy) return;
    const s = state.status;
    if (s && !s.chrome) {
      setFrame(false);
      setText("shotState", "");
      return;
    }
    state.shotBusy = true;
    const url = apiUrl("/api/shot");
    url.searchParams.set("t", String(Date.now()));
    const next = new Image();
    next.onload = () => {
      state.shotBusy = false;
      $("shot").src = next.src;
      setFrame(true);
      setText("shotState", "");
      if (!$("shotModal").hidden) $("modalShot").src = next.src;
    };
    next.onerror = () => {
      state.shotBusy = false;
      if (state.hasFrame) setText("shotState", "SIGNAL LOST");
      else { setFrame(false); setText("shotState", ""); }
    };
    next.src = url.toString();
  }

  function openShot() {
    if (!state.hasFrame || !$("shot").src) {
      toast("还没有画面，先启动任务或接管");
      return;
    }
    $("modalShot").src = $("shot").src;
    openModal("shotModal");
  }

  /* ---------------- clock / polling ---------------- */
  function tick() {
    const now = fmtClock();
    setText("clock", now);
    setText("hudClock", now);
    setText("footClock", now);
  }

  function scheduleShots() {
    clearInterval(state.shotTimer);
    state.shotTimer = setInterval(() => {
      if (!document.hidden) refreshShot();
    }, state.shotRate);
  }

  function applyShotRate(rate) {
    const next = SHOT_RATES.includes(Number(rate)) ? Number(rate) : 1000;
    state.shotRate = next;
    saveShotRate(next);
    const select = $("shotRate");
    if (select) select.value = String(next);
    scheduleShots();
    refreshShot();
    const label = next === 2000 ? "2 秒 1 张" : (next === 1000 ? "1 秒 1 张" : (next === 333 ? "1 秒 3 张" : "1 秒 5 张"));
    toast("截图频率：" + label);
  }

  async function refreshMem() {
    try {
      const data = await api("/api/mem");
      if (data && data.mem) applyMemory(data.mem);
    } catch (e) { /* keep last value */ }
  }

  function fmtCloudMinutes(value) {
    if (value == null || value === "" || !Number.isFinite(Number(value))) return "--";
    const total = Math.max(0, Math.round(Number(value)));
    if (total < 60) return total + "m";
    const hours = Math.floor(total / 60);
    const minutes = total % 60;
    return minutes ? `${hours}h${pad(minutes)}m` : `${hours}h`;
  }

  async function refreshCloudTime() {
    const el = $("cloudTime");
    if (!el) return;
    if (!state.status || !state.status.chrome) {
      setText("cloudTime", "免 -- · 付 --");
      el.title = "截图 OCR 识别剩余云游戏时长";
      return;
    }
    try {
      const data = await api("/api/cloud-time");
      if (!data || !data.ok) {
        setText("cloudTime", "免 -- · 付 --");
        el.title = "暂未识别到时长（任务中或页面未显示）";
        return;
      }
      const free = fmtCloudMinutes(data.free_minutes);
      const paid = fmtCloudMinutes(data.paid_minutes);
      setText("cloudTime", `免 ${free} · 付 ${paid}`);
      el.title = `截图识别：免费 ${free} / 付费 ${paid}`;
    } catch (e) {
      setText("cloudTime", "免 -- · 付 --");
      el.title = "时长识别失败";
    }
  }

  function startPolling() {
    clearInterval(state.pollTimer);
    clearInterval(state.memTimer);
    clearInterval(state.historyTimer);
    clearInterval(state.cloudTimer);
    state.pollTimer = setInterval(() => {
      if (!document.hidden) refreshStatus(true);
    }, 2500);
    state.memTimer = setInterval(() => {
      if (!document.hidden) refreshMem();
    }, 1000);
    state.historyTimer = setInterval(() => {
      if (!document.hidden) loadHistory();
    }, 30000);
    state.cloudTimer = setInterval(() => {
      if (!document.hidden) refreshCloudTime();
    }, 30000);
    scheduleShots();
  }

  /* ---------------- binding ---------------- */
  function bind() {
    $("themeBtn").addEventListener("click", toggleTheme);
    $("railTheme").addEventListener("click", toggleTheme);
    $("mmTheme").addEventListener("click", toggleTheme);

    $("menuBtn").addEventListener("click", openMenu);
    $("mmClose").addEventListener("click", () => closeMenu());
    $("mobileMenu").addEventListener("click", (e) => {
      if (e.target === $("mobileMenu")) closeMenu();
    });

    $("takeoverBtn").addEventListener("click", toggleTakeover);

    $("startBtn").addEventListener("click", startDaily);
    $("stopBtn").addEventListener("click", stopDaily);
    $("refreshBtn").addEventListener("click", refreshAll);
    $("netRetry").addEventListener("click", refreshAll);
    $("historyRefresh").addEventListener("click", loadHistory);

    $("expandBtn").addEventListener("click", openShot);
    $("viewport").addEventListener("click", openShot);
    $("viewport").addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openShot(); }
    });

    $("openSchedule").addEventListener("click", openSchedule);
    $("addSchedTime").addEventListener("click", () => {
      if ($("schedTimes").children.length >= 12) { toast("最多 12 个启动时间"); return; }
      addTimeRow("12:00");
    });
    $("schedChk").addEventListener("change", () => {
      if ($("schedChk").checked && !$("schedTimes").children.length) addTimeRow("04:00");
    });
    $("saveSched").addEventListener("click", saveSchedule);

    $("openGameAccounts").addEventListener("click", openGameAccounts);
    $("addGameAccount").addEventListener("click", addGameAccount);

    $("openAccounts").addEventListener("click", openAccounts);
    $("addAccount").addEventListener("click", addAccount);

    $("openPassword").addEventListener("click", openPassword);
    $("changePassword").addEventListener("click", changePassword);

    $("maaCheck").addEventListener("click", checkMaaUpdate);
    $("maaUpdate").addEventListener("click", startMaaUpdate);
    $("maaUpdateReload").addEventListener("click", () => location.reload());
    $("saveTaskOptions").addEventListener("click", saveTaskOptions);

    const shotRate = $("shotRate");
    if (shotRate) shotRate.addEventListener("change", (e) => applyShotRate(e.target.value));

    $("authChk").addEventListener("change", toggleAuth);
    $("tokenCopy").addEventListener("click", async () => {
      const token = $("tokenText").textContent || "";
      if (!token || token === "—") { toast("暂无 token"); return; }
      const ok = await copyText(token);
      toast(ok ? "token 已复制" : "复制失败");
    });
    $("tokenRotate").addEventListener("click", rotateToken);

    $("logoutBtn").addEventListener("click", logout);
    $("settingsLogout").addEventListener("click", logout);
    $("mmLogout").addEventListener("click", logout);
    $("logoutBtn").hidden = true;
    $("settingsLogout").hidden = true;
    $("mmLogout").hidden = true;

    $("cancelTakeover").addEventListener("click", cancelTakeover);
    $("retryTakeover").addEventListener("click", retryTakeover);
    $("closeTakeoverModal").addEventListener("click", closeTakeoverModal);

    $("confirmCancel").addEventListener("click", () => closeModal($("confirmModal")));
    $("confirmOk").addEventListener("click", () => {
      resolveConfirm(true);
      closeModal($("confirmModal"), true);
    });

    document.addEventListener("click", (e) => {
      const closer = e.target.closest("[data-close]");
      if (!closer) return;
      const modal = closer.closest(".modal");
      if (modal) closeModal(modal);
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (state.activeModal) { closeModal(); return; }
        if (state.menuOpen) { closeMenu(); return; }
      }
      if (e.key === "Tab") {
        if (state.activeModal) {
          const panel = state.activeModal.querySelector(".modal-panel") || state.activeModal;
          trapFocus(e, panel);
        } else if (state.menuOpen) {
          trapFocus(e, $("mobileMenu"));
        }
      }
    });

    $("taskSearch").addEventListener("input", (e) => {
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => renderLibrary(e.target.value), 120);
    });
    $("clearQueue").addEventListener("click", () => {
      state.queue = [];
      saveQueue();
      renderQueue();
      renderLibrary($("taskSearch").value);
    });
    $("runQueue").addEventListener("click", runQueue);

    $("schedTimes").addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const inputs = $$("#schedTimes input");
      const i = inputs.indexOf(e.target);
      if (i === inputs.length - 1) { e.preventDefault(); $("saveSched").click(); }
    });

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        refreshStatus(true);
        refreshMem();
        refreshShot();
      }
    });

    bindLog();
  }

  function trapFocus(event, container) {
    const items = focusables(container);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (!container.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
      return;
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function refreshAll() {
    const btn = $("refreshBtn");
    btn.disabled = true;
    try {
      await refreshMe();
      await Promise.allSettled([
        refreshStatus(true),
        refreshSettings(),
        refreshSchedule(),
        refreshGameAccounts(false),
        refreshMaaInfo(),
        loadPresets(),
        loadHistory()
      ]);
      refreshShot();
      refreshCloudTime();
      toast("已刷新");
    } finally {
      setTimeout(() => { btn.disabled = false; }, 400);
    }
  }

  /* ---------------- init ---------------- */
  async function init() {
    applyTheme(document.documentElement.dataset.theme || "light");
    const shotSelect = $("shotRate");
    if (shotSelect) shotSelect.value = String(state.shotRate);
    bind();
    tick();
    setInterval(tick, 1000);
    initNav();

    const host = location.host || "127.0.0.1:8787";
    ["nodeAddr", "nodeAddr2", "footNode", "railNode", "mmNode"].forEach((id) => setText(id, host));

    setTimeout(markBooted, 1800);
    await refreshMe();
    await refreshMaaInfo();
    await Promise.allSettled([loadCatalog(), loadPresets(), loadHistory(), refreshSettings(), refreshSchedule(true), refreshGameAccounts(false)]);
    await refreshStatus();
    startPolling();
    refreshShot();
    refreshCloudTime();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
