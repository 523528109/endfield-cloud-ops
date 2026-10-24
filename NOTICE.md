# Third-party notices

This project is a web console / deployment layer for **MaaEnd**. It does not
contain the MaaEnd application itself. The user installs MaaEnd separately.

## MaaEnd

- Project: MaaEnd — MAA 终末地小助手
- Upstream: https://github.com/MaaEnd/MaaEnd
- License: **GNU Affero General Public License v3.0 (AGPL-3.0)**
- Copyright: MaaEnd contributors

Files under `panel/web/linux/` that run tasks, resolve MXU presets, or update
MaaEnd are adapted from the MaaEnd web overlay and are distributed under
AGPL-3.0. The full license text is in `LICENSE`.

## MaaFramework and MXU

- MaaFramework: https://github.com/MaaXYZ/MaaFramework
- MXU / MaaEnd GUI: part of the MaaEnd project
- Refer to each upstream repository for its license and copyright notices.

## noVNC

- Project: noVNC — VNC client using HTML5
- Upstream: https://github.com/novnc/noVNC
- License: **MPL-2.0**
- noVNC is **not vendored** in this repository. `deploy/fetch-novnc.sh` fetches
  it into the panel directory at deployment time.

## Fonts

The panel loads local WOFF2 files:

- Archivo — Omnibus-Type, SIL Open Font License 1.1
- Outfit — Smartsheet / On Brand Investments, SIL Open Font License 1.1
- Space Grotesk — Florian Karsten, SIL Open Font License 1.1

See the upstream font repositories for the full OFL text and copyright.

## Arknights: Endfield name and logo

《明日方舟：终末地》/ *Arknights: Endfield* and its logo are trademarks and
copyrighted material of Hypergryph. The logo in `panel/static/assets/logo.svg`
is used only to identify the game this self-hosted tool automates. This project
is unofficial, non-commercial, and not affiliated with or endorsed by
Hypergryph or the MaaEnd authors.

## This project

The original web console code in this repository is licensed under
**AGPL-3.0** to remain compatible with the MaaEnd-derived scripts it includes.
