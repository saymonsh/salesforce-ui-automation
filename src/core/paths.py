"""Writable-file locations (ADR-001 packaging).

The single seam through which *every* read/write of a user-writable file —
``config.ini``, ``draft.json``, the debug log — resolves its path. Centralising
it here is the real architectural change behind the installer (ADR-001): a
per-user install lives under ``%LOCALAPPDATA%`` whose runtime folder is
effectively read-only to the app, so writable state must live elsewhere.

Two modes, decided once by :func:`is_frozen`:

* **Source / dev run** — everything stays in the project root, exactly as
  before. Running ``python -m src.main`` is unchanged; no migration, no surprise
  files in ``%APPDATA%``.
* **Frozen build** (PyInstaller, installed per-user) — writable files move to
  ``%APPDATA%\\WelfareSFAutomation\\`` (Roaming). ``config.ini`` is *seeded*
  there on first launch from the ``config.ini.example`` bundled into the build,
  so :class:`~src.core.config.Config` finds a valid file at import time instead
  of crashing the freshly-installed app.

ponytail: the frozen/source split means the relocation is only exercised by an
actual build — `test_paths.py` covers both modes by toggling `sys.frozen`.
"""
import os
import shutil
import sys

_APP_DIR_NAME = "WelfareSFAutomation"


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle (vs. a source checkout)."""
    return bool(getattr(sys, "frozen", False))


def _project_root() -> str:
    # src/core/paths.py -> ../../ -> project root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def bundle_dir() -> str:
    """Directory holding read-only bundled assets (``config.ini.example``, icons).

    Under PyInstaller this is the unpacked runtime dir (``sys._MEIPASS`` — the
    ``_internal`` folder for an onedir build); in source it is the project root.
    """
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return _project_root()


def app_data_dir() -> str:
    """Base directory for writable files. Created on demand.

    Frozen: ``%APPDATA%\\WelfareSFAutomation``. Source: the project root.
    """
    if not is_frozen():
        return _project_root()
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, _APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def logs_dir() -> str:
    """Directory for the on-disk debug log. Created on demand."""
    path = os.path.join(app_data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    """Absolute path to ``config.ini``, seeding it on first run when frozen.

    Seeding only happens in a frozen build: a source checkout keeps the
    raise-if-missing behaviour devs rely on (a forgotten ``config.ini`` should
    be a loud error, not a silent blank file). In a frozen build the app must
    not crash post-install, so a missing config is copied from the bundled
    example (which has empty credentials — the operator fills them in Settings).
    """
    path = os.path.join(app_data_dir(), "config.ini")
    if is_frozen() and not os.path.exists(path):
        example = os.path.join(bundle_dir(), "config.ini.example")
        if os.path.exists(example):
            try:
                shutil.copyfile(example, path)
            except OSError:
                pass  # best-effort; config.py surfaces a missing file normally
    return path
