# Docker

镜像：`xl233/endfield-cloud-ops:latest`

这是一个**面板运行时镜像**，包含：

- 面板 `webui.py` / 静态前端 / web runner overlays
- Google Chrome、headless sway、wayvnc、websockify、noVNC
- Python 的 `websocket-client` / `Pillow`
- cron（面板定时任务）

它**不包含** MaaEnd 本体和 MaaEnd 的 Python venv；运行时挂载现有 MaaEnd：

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

首次启动会在 `/home/maa/data` 生成管理员初始化状态，打开：

```text
http://<SERVER_IP>:8787/setup
```

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
