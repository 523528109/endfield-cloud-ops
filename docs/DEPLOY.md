# 部署文档

本文以 Ubuntu 24.04、用户 `maa`、安装目录 `/home/maa` 为例。面板和 MaaEnd 在同一台机器上运行。

> 本项目 **基于 MaaEnd**。请先按 [MaaEnd 官方文档](https://github.com/MaaEnd/MaaEnd) 安装 MaaEnd；本仓库不包含 MaaEnd 本体、MaaFramework 二进制或游戏资源。

## 1. 目录约定

| 路径 | 内容 |
| --- | --- |
| `/home/maa/maaend` | MaaEnd 本体（`interface.json`、`tasks/`、`config/`、`resource/`） |
| `/home/maa/maaend-web/web` | 网页端 runner / pipeline 覆盖层（本仓库 `panel/web/`） |
| `/home/maa/maaend-webui` | 面板（本仓库 `panel/`） |
| `/home/maa/maaend-webui/static` | 前端静态文件 |
| `/home/maa/maaend-webui/tasks.json` | 由 `gen_catalog.py` 生成，不入库 |
| `/home/maa/venv` | 带 `maa` 模块的 Python venv |
| `/home/maa/.config/endfield-web` | 云游戏 Chrome profile |

服务器上通常是：

```text
/home/maa/maaend/web -> /home/maa/maaend-web/web
```

## 2. 系统依赖

```bash
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-pip \
  git curl unzip \
  sway swaybg \
  websockify wayvnc \
  fonts-noto-cjk \
  tesseract-ocr tesseract-ocr-chi-sim
```

安装 Google Chrome（MaaEnd 的网页端控制需要 Chromium 的 CDP；脚本默认 `/usr/bin/google-chrome`）：

```bash
# 以官方 .deb 或发行版仓库安装均可；确认：
/usr/bin/google-chrome --version
```

Wayland 使用 headless sway，不需要物理显示器。Chrome 使用 SwiftShader，服务器最好至少 2 GB 内存并配置 swap。

## 3. 安装 MaaEnd

按 MaaEnd 官方安装方式装到 `/home/maa/maaend`，并确认：

```bash
ls /home/maa/maaend/interface.json
ls /home/maa/maaend/tasks
/home/maa/venv/bin/python -c "import maa; print(maa.__file__)"
```

`maa` Python 模块必须装在 `/home/maa/venv` 里；`auto_update.sh` 和自检脚本都使用这个 venv，而不是系统 `python3`。

### 3.1 准备 `mxu-MaaEnd.json`

面板的日常/定时使用 `webcloud-full` 实例，任务库使用 `panel-queue` 实例。

- 如果已经有 MXU 配置：直接使用 `/home/maa/maaend/config/mxu-MaaEnd.json`。
- 新部署：可以先用示例生成：

```bash
sudo -u maa mkdir -p /home/maa/maaend/config
sudo -u maa cp deploy/mxu-MaaEnd.example.json /home/maa/maaend/config/mxu-MaaEnd.json
```

示例只包含 `webcloud-full` 11 项；第一次运行 `gen_catalog.py` 会自动创建并补全 `panel-queue`。

## 4. 安装面板

```bash
sudo -u maa git clone <YOUR_REPO_URL> /home/maa/endfield-cloud-ops
cd /home/maa/endfield-cloud-ops
sudo -u maa bash deploy/install.sh
```

`install.sh` 会：

- 复制 `panel/webui.py`、`gen_catalog.py` 和 `static/` 到 `/home/maa/maaend-webui/`
- 复制 `panel/web/` 到 `/home/maa/maaend-web/web/`
- 给 runner / 更新脚本加执行权限
- 检查 `/home/maa/maaend/web` 软链接

不会覆盖 `mxu-MaaEnd.json`、`users.json`、`game-accounts.json` 等运行时配置。

### 4.1 生成任务目录

```bash
sudo -u maa env \
  HOME=/home/maa \
  MAAEND_ROOT=/home/maa/maaend \
  MAAEND_WEBUI_DIR=/home/maa/maaend-webui \
  /home/maa/venv/bin/python /home/maa/maaend-webui/gen_catalog.py
```

输出类似：

```text
catalog: 49 tasks, 39 options, version v2.35.0
```

如果任务库为空 / 页面显示 0 项，检查 `interface.json` 的 `import` 和 `MAAEND_ROOT`。

### 4.2 noVNC（接管画面）

```bash
sudo apt install -y git websockify wayvnc
sudo -u maa bash /home/maa/endfield-cloud-ops/deploy/fetch-novnc.sh
```

noVNC 不随仓库分发（MPL-2.0），由脚本从上游拉取。面板通过 `/vnc/*` 反向代理，无需放行 6080。

## 5. systemd 服务

```bash
sudo cp /home/maa/endfield-cloud-ops/deploy/maaend-webui.service \
  /etc/systemd/system/maaend-webui.service
sudo systemctl daemon-reload
sudo systemctl enable --now maaend-webui
sudo systemctl status maaend-webui --no-pager
```

默认监听 `0.0.0.0:8787`。如果只允许本机 / 内网：

```bash
# /etc/systemd/system/maaend-webui.service
Environment=WEBUI_BIND=127.0.0.1
Environment=WEBUI_PORT=8787
```

修改后 `sudo systemctl daemon-reload && sudo systemctl restart maaend-webui`。

### 5.1 首次初始化

打开：

```text
http://<SERVER_IP>:8787/setup
```

创建管理员账号（密码至少 8 位）。之后 `/setup` 会重定向，账号保存在
`/home/maa/maaend-webui/users.json`。

如果面板没有生成初始化页，检查 `users.json` 是否已存在；忘记密码时，管理员可在服务器上备份/移走 `users.json` 后重新初始化。

### 5.2 Docker 部署（可选）

提供两个镜像：

| 标签 | 内容 |
| --- | --- |
| `xl233/endfield-cloud-ops:full` | 面板 + MaaEnd v2.35.0 + MaaFw venv + Chrome/sway/noVNC |
| `xl233/endfield-cloud-ops:latest` | 面板运行时，需要挂载现有 MaaEnd/venv |

**一体化部署（推荐）**：

```bash
docker pull xl233/endfield-cloud-ops:full

docker run -d --name endfield-cloud-ops \
  --restart unless-stopped \
  -p 8787:8787 \
  --shm-size=1g \
  -v endfield-config:/home/maa/.config \
  -v endfield-data:/home/maa/data \
  xl233/endfield-cloud-ops:full
```

如需让 MaaEnd 更新在容器重建后保留，额外挂载：

```bash
-v endfield-maaend:/home/maa/maaend \
-v endfield-venv:/home/maa/venv
```

首次会自动从镜像内容初始化这两个卷。

**只替换面板（已有 MaaEnd）**：

```bash
docker pull xl233/endfield-cloud-ops:latest

docker run -d --name endfield-cloud-ops \
  --restart unless-stopped \
  -p 8787:8787 \
  --shm-size=1g \
  -v /home/maa/maaend:/home/maa/maaend \
  -v /home/maa/venv:/home/maa/venv \
  -v endfield-config:/home/maa/.config \
  -v endfield-data:/home/maa/data \
  xl233/endfield-cloud-ops:latest
```

首次启动后访问：

```text
http://<SERVER_IP>:8787/setup
```

**项目不提供默认账号，也不提供默认密码**；请在 `/setup` 页面自行创建管理员账号（密码至少 8 位）。

说明：

- `:full` 已内置 MaaEnd 和 venv，不需要挂载 `/home/maa/maaend`、`/home/maa/venv`。
- `:latest` 必须挂载 `/home/maa/maaend` 和 `/home/maa/venv`，否则任务无法运行。
- 面板数据保存在 `endfield-data` 卷（`users.json`、`tasks.json`、`schedule.json` 等），Chrome/账号状态保存在 `endfield-config` 卷。
- 容器内自带 Chrome + sway，任务和实时画面都在容器内执行；接管通过 `/vnc/*` 反代，不需要放行 6080。
- 镜像默认是公开的；如果改为私有，先 `docker login`。
- 完整说明见 [docker/README.md](../docker/README.md)。
- 使用 Docker 时不需要再安装第 5 节的 systemd 服务；两者选一种即可。

## 6. 定时任务

面板 **OPERATION → AUTO START → 设置**：

- 开关自动运行
- 增删任意 `HH:MM`
- 保存后写入 `maa` 用户 crontab

检查：

```bash
crontab -u maa -l
```

默认是 `04:00` / `16:00`，执行 `webcloud-full`（面板“定时任务”11 项）。
普通任务默认 420 秒上限；`WebStartGame` 允许 2 小时处理云游戏排队。

## 7. Maa 更新

面板 **系统设置 → MAA 版本**：

- **检查更新**：读取 GitHub 最新 Release
- **更新 Maa**：调用 `/home/maa/maaend/web/linux/homesrv/auto_update.sh`

更新流程：

1. 备份 `resource/`、`interface.json`、`tasks/`、`agent/`、`maafw/`
2. 依次尝试 `ghfast.top` → `gh-proxy.com` → GitHub 直连 → `MAAEND_PROXY`
3. 替换后运行 `post_upgrade_check.py`（15 个关键节点）
4. 运行 `option_audit.py` 对比覆盖项基线
5. 失败自动回滚；更新后自动重建 `tasks.json` 和 `panel-queue`

需要给 `maa` 用户可写的 `/home/maa/venv` 和 GitHub 网络访问。

## 8. 反向代理 / HTTPS（强烈建议）

面板拥有启动任务和接管画面的权限。公网使用时至少加一层 Nginx/Caddy、HTTPS 和来源 IP 限制。

Nginx 示例：

```nginx
server {
    listen 443 ssl http2;
    server_name maa.example.com;

    ssl_certificate     /etc/letsencrypt/live/maa.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/maa.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8787;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

`/vnc/websockify` 也是 WebSocket，必须保留 `Upgrade` / `Connection` 头。
**不要**把 wayvnc/websockify 的 6080 端口直接暴露公网。

## 9. 运行与排查

### 服务状态

```bash
systemctl status maaend-webui --no-pager
journalctl -u maaend-webui -n 100 --no-pager
```

### 实时画面是 NO SIGNAL

```bash
pgrep -af 'google-chrome.*endfield-web'
curl -s http://127.0.0.1:9334/json/version
tail -50 /tmp/chrome-endfield.log
tail -30 /tmp/sway-endfield.log
```

- `wayland-1` 不存在：检查 `XDG_RUNTIME_DIR=/run/user/1000`、`sway` 进程。
- Chrome 起不来：检查 `chrome_homesrv.sh` 的 profile、Singleton 锁、磁盘和内存。
- `controller connected=False`：通常是 Wayland socket 不对或 Chrome 已退出。

### 启动阶段停止显示“启动浏览器失败”

旧版本在 Chrome 启动的 16 秒窗口内停止会误报；当前脚本已用 `.manual_stop` 标记把这种情况识别为正常停止。如果仍然出现 `[X]`，查看 `/tmp/chrome-endfield.log` 和 `daily.log`。

### 云游戏排队

`WebStartGame` 最长 2 小时；普通任务 420 秒。排队时任务保持 running 是正常的，不要反复点停止。

### 任务卡在「帝江号」主菜单

如果日志里 `InMenuList` / `CheckMenuListColor` 识别失败，但游戏已经进入主菜单，可重新应用本地兼容补丁：

```bash
cd /home/maa/maaend
sudo -u maa env MAAEND_ROOT=/home/maa/maaend \
  /home/maa/venv/bin/python web/linux/homesrv/apply_local_patches.py
```

补丁只移除 `InMenuList` 里的颜色断言，保留两个 OCR 检查；修改前会备份 `resource/pipeline/nodes.json`。`auto_update.sh` 在 MaaEnd 升级后会自动执行一次。

### 任务库 / 预设为空

```bash
ls -l /home/maa/maaend/config/mxu-MaaEnd.json
ls -l /home/maa/maaend-webui/tasks.json
sudo -u maa env MAAEND_ROOT=/home/maa/maaend \
  MAAEND_WEBUI_DIR=/home/maa/maaend-webui \
  /home/maa/venv/bin/python /home/maa/maaend-webui/gen_catalog.py
```

### VNC 502 / 画面打不开

```bash
pgrep -af 'wayvnc|websockify'
ss -ltnp | grep -E '6080|9334|8787'
```

确认 `websockify` 和 `wayvnc` 已安装，`/home/maa/maaend-webui/novnc/vnc.html` 存在，登录会话有效。

### 内存不足

```bash
free -m
swapon --show
dmesg -T | tail -50
```

Chrome + Maa 识别在 2 GB 内存上容易吃紧，建议 4 GB 或至少 8 GB swap。

## 10. 升级 / 卸载

升级：

```bash
cd /home/maa/endfield-cloud-ops
sudo -u maa git pull
sudo -u maa bash deploy/install.sh
sudo -u maa env MAAEND_ROOT=/home/maa/maaend \
  MAAEND_WEBUI_DIR=/home/maa/maaend-webui \
  /home/maa/venv/bin/python /home/maa/maaend-webui/gen_catalog.py
sudo systemctl restart maaend-webui
```

升级前先备份 `users.json`、`game-accounts.json`、`mxu-MaaEnd.json`。

卸载面板（保留 MaaEnd）：

```bash
sudo systemctl disable --now maaend-webui
sudo rm -f /etc/systemd/system/maaend-webui.service
sudo systemctl daemon-reload
# 可选：删除 /home/maa/maaend-webui 和 /home/maa/maaend-web/web 下的覆盖层
```

## 11. 安全清单

- [ ] 首次初始化时设置强密码（项目不提供默认账号/密码）
- [ ] 面板只开放给内网 / 固定 IP，或放在 HTTPS 反向代理后
- [ ] 不暴露 6080；VNC 仅通过 `/vnc/*` 反代
- [ ] 不提交 `users.json`、`game-accounts.json`、`active-profile`、token
- [ ] 定期备份 `mxu-MaaEnd.json` 和账号配置
- [ ] 更新 MaaEnd 前先停止任务（面板会拒绝运行中更新）
