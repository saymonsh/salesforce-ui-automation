"""Draft persistence for the manual-entry grid (issue #18, epic #14 step 4).

The grid's backing model is plain Python data (lists of dicts of strings + bools,
see :class:`src.ui.data_grid.DataGridView`), so a draft is just that model
snapshotted to JSON next to ``config.ini``. Saving on grid-dialog close and on
window close means a half-typed table survives the app being closed and reopened
— the user never loses work to an accidental quit.

This module is deliberately *silent*: a missing/corrupt/locked draft file must
never crash startup, so every failure degrades to "no draft" rather than raising.
The grid itself owns the model⇄dict translation (``export_state`` /
``restore_state``); here we only touch the disk.
"""
import json
import os

from src.core.config import config_instance as parm

# Lives beside config.ini in the project root and is git-ignored — it is a local,
# per-machine scratch file, not shared state.
_DRAFT_FILENAME = "draft.json"


def _draft_path() -> str:
    return os.path.join(parm.project_root, _DRAFT_FILENAME)


def load_draft() -> dict | None:
    """Return the saved grid state, or ``None`` if there is no usable draft.

    Any error (file absent, not JSON, unreadable) collapses to ``None`` so the
    app always starts — a bad draft is dropped, never fatal.
    """
    path = _draft_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def save_draft(state: dict) -> bool:
    """Persist ``state`` (from ``DataGridView.export_state``) to disk.

    Best-effort: returns ``False`` instead of raising if the write fails (e.g.
    the file is locked), since a failed autosave must never break closing a
    dialog or the app.
    """
    try:
        with open(_draft_path(), "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
