"""Self-check for src/core/paths.py (ADR-001 writable-file relocation).

Framework-free, assert-based — run directly:  python tests/test_paths.py

Covers the two modes that the frozen/source split hinges on, since only an
actual build exercises the frozen branch in real life:
  * source run  -> writable base is the project root, no seeding
  * frozen run  -> writable base is %APPDATA%\\WelfareSFAutomation, config.ini
                   seeded from the bundled config.ini.example on first launch
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import paths


def _reset():
    for attr in ("frozen", "_MEIPASS"):
        if hasattr(sys, attr):
            delattr(sys, attr)


def test_source_mode_uses_project_root():
    _reset()
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    assert not paths.is_frozen()
    assert paths.app_data_dir() == root
    # In source mode config_path points at the repo's config.ini and never seeds.
    assert paths.config_path() == os.path.join(root, "config.ini")


def test_frozen_mode_relocates_and_seeds():
    _reset()
    with tempfile.TemporaryDirectory() as appdata, tempfile.TemporaryDirectory() as bundle:
        # Fake a frozen build: _MEIPASS holds the bundled example, APPDATA is empty.
        sys.frozen = True
        sys._MEIPASS = bundle
        with open(os.path.join(bundle, "config.ini.example"), "w", encoding="utf-8") as fh:
            fh.write("[Auth]\nUSERNAME = \n")
        old_appdata = os.environ.get("APPDATA")
        os.environ["APPDATA"] = appdata
        try:
            base = paths.app_data_dir()
            assert base == os.path.join(appdata, "WelfareSFAutomation")
            assert os.path.isdir(base)  # created on demand

            cfg = paths.config_path()
            assert cfg == os.path.join(base, "config.ini")
            assert os.path.exists(cfg), "config.ini must be seeded on first run"
            with open(cfg, encoding="utf-8") as fh:
                assert "[Auth]" in fh.read(), "seed copied from the bundled example"

            # logs dir lands under the relocated base too.
            assert paths.logs_dir() == os.path.join(base, "logs")
            assert os.path.isdir(paths.logs_dir())
        finally:
            if old_appdata is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = old_appdata
            _reset()


def test_frozen_seed_is_idempotent():
    """A second launch must not overwrite an operator-edited config.ini."""
    _reset()
    with tempfile.TemporaryDirectory() as appdata, tempfile.TemporaryDirectory() as bundle:
        sys.frozen = True
        sys._MEIPASS = bundle
        with open(os.path.join(bundle, "config.ini.example"), "w", encoding="utf-8") as fh:
            fh.write("EXAMPLE\n")
        old_appdata = os.environ.get("APPDATA")
        os.environ["APPDATA"] = appdata
        try:
            cfg = paths.config_path()  # seeds
            with open(cfg, "w", encoding="utf-8") as fh:
                fh.write("OPERATOR EDITED\n")
            paths.config_path()  # second launch — must NOT re-seed
            with open(cfg, encoding="utf-8") as fh:
                assert fh.read() == "OPERATOR EDITED\n"
        finally:
            if old_appdata is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = old_appdata
            _reset()


if __name__ == "__main__":
    test_source_mode_uses_project_root()
    test_frozen_mode_relocates_and_seeds()
    test_frozen_seed_is_idempotent()
    print("OK — all path self-checks passed")
