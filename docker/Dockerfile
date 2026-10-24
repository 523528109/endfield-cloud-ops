# syntax=docker/dockerfile:1
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/home/maa \
    XDG_RUNTIME_DIR=/run/user/1000 \
    MAAEND_HOME=/home/maa \
    MAAEND_ROOT=/home/maa/maaend \
    MAAEND_DATA_DIR=/home/maa/data \
    MAAEND_CHROME=/usr/bin/google-chrome \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git python3 python3-pip \
        sway swaybg wayvnc websockify gosu cron procps \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Chrome is required by the MaaEnd web runner.
RUN curl -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
        -o /tmp/google-chrome.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
    && rm -f /tmp/google-chrome.deb \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --break-system-packages --no-cache-dir \
        websocket-client Pillow

RUN userdel -r ubuntu 2>/dev/null || true \
    && groupdel ubuntu 2>/dev/null || true \
    && groupadd -g 1000 maa \
    && useradd -u 1000 -g maa -m -d /home/maa -s /bin/bash maa

COPY panel/webui.py panel/gen_catalog.py /home/maa/maaend-webui/
COPY panel/static/ /home/maa/maaend-webui/static/
COPY panel/web/ /home/maa/maaend-web/

RUN git clone --depth 1 https://github.com/novnc/noVNC.git /home/maa/maaend-webui/novnc \
    && rm -rf /home/maa/maaend-webui/novnc/.git \
    && mkdir -p /home/maa/maaend /home/maa/data /home/maa/.config /run/user/1000 \
    && ln -sfn /home/maa/maaend-web/web /home/maa/maaend/web \
    && chown -R maa:maa /home/maa /run/user/1000

COPY docker/entrypoint.sh /usr/local/bin/endfield-entrypoint
RUN chmod 755 /usr/local/bin/endfield-entrypoint

# Mount these from an existing MaaEnd host:
#   /home/maa/maaend  MaaEnd installation
#   /home/maa/venv    Python venv with the "maa" module
#   /home/maa/.config Chrome profile / account state
#   /home/maa/data    panel users, tasks.json, schedule, tokens
VOLUME ["/home/maa/maaend", "/home/maa/venv", "/home/maa/.config", "/home/maa/data"]

EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8787/ >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/endfield-entrypoint"]
