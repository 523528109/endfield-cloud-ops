#!/usr/bin/env bash
# Install the panel and web overlay into an existing MaaEnd home.
# Run as the MaaEnd user (normally "maa"), not as root.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="${MAAEND_HOME:-$HOME}"
PANEL_DIR="${MAAEND_WEBUI_DIR:-$HOME_DIR/maaend-webui}"
WEB_DIR="${MAAEND_WEB_DIR:-$HOME_DIR/maaend-web/web}"
MAAEND_ROOT="${MAAEND_ROOT:-$HOME_DIR/maaend}"

if [ "$(id -u)" -eq 0 ]; then
  echo "请用 maa 用户运行：sudo -u maa bash deploy/install.sh" >&2
  exit 1
fi

if [ ! -d "$MAAEND_ROOT" ]; then
  echo "找不到 MaaEnd：$MAAEND_ROOT" >&2
  echo "请先安装 MaaEnd，或设置 MAAEND_ROOT。" >&2
  exit 1
fi

echo "[1/4] 安装面板到 $PANEL_DIR"
mkdir -p "$PANEL_DIR/static/assets" "$PANEL_DIR/static/fonts"
install -m 644 "$SRC/panel/webui.py" "$SRC/panel/gen_catalog.py" "$PANEL_DIR/"
install -m 644 "$SRC/panel/static/index.html" "$SRC/panel/static/login.html" \
  "$SRC/panel/static/setup.html" "$SRC/panel/static/app.js" \
  "$SRC/panel/static/style.css" "$PANEL_DIR/static/"
install -m 644 "$SRC/panel/static/assets/logo.svg" "$PANEL_DIR/static/assets/"
install -m 644 "$SRC"/panel/static/fonts/*.woff2 "$PANEL_DIR/static/fonts/"

echo "[2/4] 安装网页端 runner / pipeline 覆盖层到 $WEB_DIR"
mkdir -p "$WEB_DIR/linux/homesrv" "$WEB_DIR/linux/resource_web_linux" \
  "$WEB_DIR/resource_web/pipeline" "$WEB_DIR/resource_web_homesrv"
cp -a "$SRC/panel/web/." "$WEB_DIR/"
chmod +x "$WEB_DIR"/linux/*.py "$WEB_DIR"/linux/homesrv/*.sh "$WEB_DIR"/linux/homesrv/*.py 2>/dev/null || true
chmod 775 "$WEB_DIR"/linux/homesrv/*.sh

echo "[3/4] 检查 MaaEnd web 目录"
if [ -e "$MAAEND_ROOT/web" ] && [ ! -L "$MAAEND_ROOT/web" ]; then
  echo "  ! $MAAEND_ROOT/web 已存在且不是软链接，跳过；请手动确认指向 $WEB_DIR" >&2
elif [ ! -e "$MAAEND_ROOT/web" ]; then
  ln -s "$WEB_DIR" "$MAAEND_ROOT/web"
  echo "  已创建 $MAAEND_ROOT/web -> $WEB_DIR"
else
  echo "  $MAAEND_ROOT/web 已存在软链接，保持不动"
fi

echo "[4/4] 完成"
echo "下一步："
echo "  1) 准备 mxu-MaaEnd.json（可参考 deploy/mxu-MaaEnd.example.json）"
echo "  2) 生成任务目录："
echo "     MAAEND_ROOT=$MAAEND_ROOT MAAEND_WEBUI_DIR=$PANEL_DIR \\"
echo "       $HOME_DIR/venv/bin/python $PANEL_DIR/gen_catalog.py"
echo "  3) 安装并启动 systemd 服务（见 docs/DEPLOY.md）"
echo "  4) 打开 http://<SERVER_IP>:8787/setup 初始化管理员"
