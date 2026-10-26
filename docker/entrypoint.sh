#!/usr/bin/env bash
set -euo pipefail

export HOME=/home/maa
export XDG_RUNTIME_DIR=/run/user/1000
export XDG_SESSION_TYPE=wayland
export MAAEND_CHROME="${MAAEND_CHROME:-/usr/bin/google-chrome}"
export MAAEND_DATA_DIR="${MAAEND_DATA_DIR:-/home/maa/data}"

mkdir -p "$XDG_RUNTIME_DIR" "$MAAEND_DATA_DIR" /home/maa/.config /home/maa/maaend
chmod 700 "$XDG_RUNTIME_DIR"
chown -R maa:maa "$XDG_RUNTIME_DIR" "$MAAEND_DATA_DIR" /home/maa/maaend-web 2>/dev/null || true
chown -R maa:maa /home/maa/.config 2>/dev/null || true

# MaaEnd normally exposes <root>/web as a symlink to the overlay.
if [ ! -e /home/maa/maaend/web ]; then
  ln -sfn /home/maa/maaend-web/web /home/maa/maaend/web 2>/dev/null || true
fi

# Generate the task catalog on first start when MaaEnd and its venv are mounted.
if [ ! -f "$MAAEND_DATA_DIR/tasks.json" ] \
   && [ -f /home/maa/maaend/interface.json ] \
   && [ -x /home/maa/venv/bin/python ]; then
  gosu maa env \
    HOME=/home/maa \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
    MAAEND_ROOT=/home/maa/maaend \
    MAAEND_WEBUI_DIR=/home/maa/maaend-webui \
    MAAEND_DATA_DIR="$MAAEND_DATA_DIR" \
    PYTHONPATH=/home/maa/maaend-web/web/linux \
    /home/maa/venv/bin/python /home/maa/maaend-webui/gen_catalog.py || true
fi

# The schedule feature writes to the maa user's crontab.
cron 2>/dev/null || true

exec gosu maa "${MAAEND_PANEL_PYTHON:-/usr/bin/python3}" /home/maa/maaend-webui/webui.py
