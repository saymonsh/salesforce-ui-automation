# PyInstaller spec — onedir build of the Welfare-Ministry Salesforce automation
# app (ADR-001). Build from the project root inside the venv:
#
#     pip install -r requirements-build.txt
#     pyinstaller build.spec --noconfirm
#
# Output: dist\Kivun\  (a folder with Kivun.exe + the full CPython runtime).
# The Inno Setup script (installer.iss) wraps that folder into a per-user
# installer. onedir (not onefile) is deliberate — see ADR-001 Option A:
# fast start-up, AV-friendly, and a read-only _MEIPASS that pairs with the
# writable-file relocation to %APPDATA% (src/core/paths.py).

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Read the canonical version from src/core/version.py so the EXE metadata and
# Inno Setup installer stay in sync without manual edits.
import re as _re
with open("src/core/version.py") as _vf:
    _APP_VERSION = _re.search(r'__version__\s*=\s*"([^"]+)"', _vf.read()).group(1)

# Emit build/version.iss so `iscc installer.iss` picks up the same version.
os.makedirs("build", exist_ok=True)
with open(os.path.join("build", "version.iss"), "w") as _vi:
    _vi.write(f'#define AppVersion "{_APP_VERSION}"\n')

datas = []
binaries = []
hiddenimports = collect_submodules("src")

# Flet ships a bundled Flutter desktop client (flet_desktop) that MUST travel
# with the app — collect both packages' data/binaries/hidden imports.
for pkg in ("flet", "flet_desktop"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Bundle the Flet desktop client so the INSTALLED app runs offline. Flet does
# not ship the Flutter client in the wheel — on first launch
# flet_desktop.ensure_client_cached() looks for a bundled archive at
# flet_desktop/app/flet-windows.zip and, failing that, downloads it from GitHub.
# A government/clean machine may have no GitHub egress, so we pre-stage the
# archive into the bundle (built once from this dev machine's client cache, then
# reused). Without it the app still works *if* it can reach GitHub on first run.
import zipfile
import flet_desktop.version as _fdv
from pathlib import Path as _Path

_flet_zip = os.path.join("build", "flet-windows.zip")
if not os.path.exists(_flet_zip):
    _cache = _Path.home() / ".flet" / "client" / f"flet-desktop-full-{_fdv.version}"
    if (_cache / "flet" / "flet.exe").exists():
        os.makedirs("build", exist_ok=True)
        # Zip so the archive root holds `flet/...` — what ensure_client_cached()
        # expects to extract (it later opens <cache>/flet/flet.exe).
        with zipfile.ZipFile(_flet_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in _cache.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(_cache))
    else:
        print(f"WARNING: Flet client cache not found at {_cache}; the built app "
              "will download it from GitHub on first run (needs egress).")
if os.path.exists(_flet_zip):
    datas += [(_flet_zip, "flet_desktop/app")]

# Bundled read-only assets. config.ini.example is the seed template
# src/core/paths.config_path() copies into %APPDATA% on first launch; fonts/
# icons back the UI.
datas += [
    ("config.ini.example", "."),
    ("assets", "assets"),
]

# Optional app icon: drop assets/icons/app.ico to brand the exe (Inno reuses it).
import os
_icon = "assets/icons/app.ico"
icon = _icon if os.path.exists(_icon) else None

block_cipher = None

a = Analysis(
    ["src/main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Kivun",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # windowed app — no console window
    disable_windowed_traceback=False,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Kivun",
)
