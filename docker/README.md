# Docker

镜像：`xl233/endfield-cloud-ops:latest`

> 本项目**不提供默认账号或默认密码**。首次启动后访问 `/setup` 自行创建管理员账号（密码至少 8 位）。

这是一个**面板运行时镜像**，包含：

- 面板 `webui.py` / 静态前端 / web runner overlays
- Google Chrome、headless sway、wayvnc、websockify、noVNC
- Python 的 `websocket-client` / `Pillow`
- cron（面板定时任务）

它**不包含** MaaEnd 本体和 MaaEnd 的 Python venv；运行时挂载现有 MaaEnd。

### 前提

宿主机上已经安装并配置好：

```text
/home/maa/maaend     # 包含 interface.json / tasks/ / agent/ / maafw/
/home/maa/venv       # 包含 maa Python 模块
```

没有这两个目录时镜像仍能启动面板，但任务会失败。

运行时挂载现有 MaaEnd：

```bash
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

首次启动后打开：

```text
http://<SERVER_IP>:8787/setup
```

在页面里创建管理员账号。项目没有内置默认账号，也没有默认密码。

### 目录

| 容器路径 | 用途 |
| --- | --- |
| `/home/maa/maaend` | 挂载 MaaEnd 安装目录（必须有 `interface.json`、`tasks/`、`agent/`、`maafw/`） |
| `/home/maa/venv` | 挂载带 `maa` 模块的 Python venv |
| `/home/maa/.config` | Chrome profile / wayvnc / 游戏账号状态，建议持久化 |
| `/home/maa/data` | 面板的 `users.json`、`tasks.json`、`schedule.json`、token，建议持久化 |

### 说明

- 容器内自带 Chrome + headless sway，任务和实时画面都在容器内运行。
- 接管画面通过面板 `/vnc/*` 反代，不需要额外映射 6080。
- 定时任务由容器内 cron 执行；需要容器以 root 启动（默认 entrypoint 会降权到 `maa` 运行面板）。
- 如果 Chrome 启动失败，先看：

```bash
docker logs endfield-cloud-ops
docker exec endfield-cloud-ops tail -50 /tmp/chrome-endfield.log
```

- MaaEnd 升级仍然通过面板「更新 Maa」进行，更新的是挂载进来的 `/home/maa/maaend`。

## 自动构建

仓库已配置 `.github/workflows/docker.yml`：

- 推送到 `main`、创建 `v*` tag，或手动 `workflow_dispatch` 时触发
- 使用 `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` 两个 GitHub Actions secrets 登录 Docker Hub
- 自动推送 `latest`、commit SHA、版本 tag
- 构建完成后会启动容器做健康检查，再删除临时容器

