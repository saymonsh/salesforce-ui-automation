# Packaging — building the per-user Windows installer (ADR-001)

Turns the source app into a double-click installer that needs **no Python** and
**raises no UAC prompt**. Full rationale: [ADR-001](adr/ADR-001-packaging.md).

## Prerequisites (build machine)

- The project venv with deps installed, **plus** PyInstaller:
  ```powershell
  pip install -r requirements-build.txt
  ```
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`iscc` on PATH).
- The Flet desktop client must be present in the local cache
  (`~/.flet/client/flet-desktop-full-<ver>/flet/flet.exe`). It lands there the
  first time you run the app from source (`python -m src.main`). `build.spec`
  zips it into the bundle so the **installed** app runs offline — without it the
  built app downloads the client from GitHub on first launch (needs egress).

## Build

```powershell
pyinstaller build.spec --noconfirm     # -> dist\Kivun\ + build\version.iss
iscc installer.iss                     # -> Output\WelfareSFAutomation-Setup-<ver>.exe
```

`build.spec` reads the version from `src/core/version.py` and writes
`build\version.iss` so Inno picks it up automatically — bump the version in one
place, both outputs reflect it.

## What the installer does (per-user, no UAC)

- Installs to `%LOCALAPPDATA%\WelfareSFAutomation\` — a user-writable location,
  so Windows never elevates (`PrivilegesRequired=lowest`).
- Start-menu + optional desktop shortcuts under the **user's** profile.
- A one-time **SmartScreen** warning remains (the EXE is unsigned in phase one —
  "More info → Run anyway"). UAC and SmartScreen are different prompts; only
  code-signing removes SmartScreen.

## Where files live after install

| File | Location |
|------|----------|
| EXE + CPython runtime + Flet client | `%LOCALAPPDATA%\WelfareSFAutomation\` |
| `config.ini`, `draft.json`, `logs\debug.log` | `%APPDATA%\WelfareSFAutomation\` |

The writable files are routed through `src/core/paths.py`: in a **source** run
they stay in the project root (dev workflow unchanged); in a **frozen** build
they relocate to `%APPDATA%`, and `config.ini` is seeded there on first launch
from the bundled `config.ini.example` (so a fresh install starts instead of
crashing at import). Uninstall leaves `%APPDATA%` data in place.

## Versioning

The single source of truth is `src/core/version.py` (`__version__`). It flows to:

- **Window title** — shown at runtime via `APP_WINDOW_TITLE`.
- **build.spec** — reads it at build time, writes `build/version.iss`.
- **installer.iss** — includes `build/version.iss` for the installer filename.

To release: bump `__version__`, commit, tag (`git tag v1.2.3`), push the tag.

## Distribution (CI)

Pushing a `v*` tag triggers `.github/workflows/build-release.yml`, which:

1. Builds `dist\Kivun\` with PyInstaller on a Windows runner.
2. Compiles the Inno Setup installer.
3. Publishes `WelfareSFAutomation-Setup-<ver>.exe` as a **GitHub Release**.

The binary is not committed to git history — Releases only. For offline/gov
builds where the Flet client must be pre-cached, build locally (see above).

## In-app updates

On launch (frozen builds only), `src/core/update_checker.py` asks GitHub for the
latest release. If its tag is newer than `src/core/version.py`, the operator gets
a dialog offering a one-click **download + install** of the new installer; the
app then closes so the per-user installer can replace its files. The check is
stdlib-only (`urllib`) and offline-safe — a blocked network just skips it.

This supersedes the ADR-001 "updates: manual" line: bumping the version, tagging,
and pushing now both publishes the release (CI) *and* makes existing installs
self-update.

## Clean-machine checklist (ADR-001 action items 5–6)

On a Windows VM with **no Python**:
1. Run the installer — confirm **no UAC** prompt appears.
2. Launch the app — it embeds Chrome and runs a row without permission errors
   writing `config.ini` / `draft.json`. `--dry_run` exercises the flow without
   Salesforce.
