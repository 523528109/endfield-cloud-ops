#!/usr/bin/env bash
# Fetch noVNC into the panel directory. noVNC is MPL-2.0; it is not vendored.
set -euo pipefail

DEST="${1:-$HOME/maaend-webui/novnc}"
if [ -f "$DEST/vnc.html" ]; then
  echo "noVNC already exists: $DEST"
  exit 0
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone --depth 1 https://github.com/novnc/noVNC.git "$TMP/noVNC"
rm -rf "$DEST"
mv "$TMP/noVNC" "$DEST"
echo "noVNC installed: $DEST"
echo "Install websockify separately, e.g.: sudo apt install websockify"
