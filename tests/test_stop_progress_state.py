"""Self-check for the STOP-in-progress hero state — no framework.

    python tests/test_stop_progress_state.py

When STOP is clicked the stop is cooperative and can take a few seconds to
unwind. ``disable_stop`` flips the ring/bar to indeterminate (an animated
sweep that reads as *active*, not frozen) and labels the hero "עוצר…", while
stashing the determinate progress. ``set_running(False)`` restores that frozen
% so the final stopped state still shows where the run halted. A late per-row
``set_progress`` emit during the unwind must NOT clobber the sweep.

Guards that round-trip: indeterminate ⇒ guarded ⇒ restored. Built on real
``MainView`` methods over lightweight fakes (no Flet page needed).
"""
from types import SimpleNamespace

from src.ui.main_window import MainView


def _fake_view() -> MainView:
    """A MainView with only the controls the stop-state paths touch, and the
    heavy collaborators (layout/edit-lock/render) stubbed to no-ops."""
    v = object.__new__(MainView)
    v._running = True
    v._stopping = False
    v._action_required = False
    v._type_segments = {}
    v.progress_ring = SimpleNamespace(value=0.0)
    v.linear = SimpleNamespace(value=0.0)
    v.counter_text = SimpleNamespace(value="")
    v.hero_value = SimpleNamespace(value="", color=None)
    v.hero_icon = SimpleNamespace(visible=False)
    v.status_dot = SimpleNamespace(bgcolor=None)
    v.feed_button = SimpleNamespace(icon_color=None)
    v.play_icon = object()
    v.action_circle = SimpleNamespace(
        disabled=False, bgcolor=None, content=None, tooltip=None,
        shadow=SimpleNamespace(color=None),
    )
    v._apply_run_layout = lambda running: None
    v._set_edit_locked = lambda locked: None
    v._safe_update = lambda: None
    return v


def check_stop_progress_roundtrip() -> None:
    v = _fake_view()

    # Mid-run progress lands as a determinate 30%.
    v.set_progress(0.3)
    assert v.progress_ring.value == 0.3, v.progress_ring.value
    assert v.hero_value.value == "30%", v.hero_value.value

    # STOP clicked → indeterminate sweep, frozen value stashed, "עוצר…" label.
    v.disable_stop()
    assert v._stopping is True
    assert v.progress_ring.value is None and v.linear.value is None
    assert v._frozen_progress == 0.3
    assert v.hero_value.value == "עוצר…", v.hero_value.value
    assert v.action_circle.disabled is True

    # A late per-row emit during the unwind must be ignored, not clobber the sweep.
    v.set_progress(0.9)
    assert v.progress_ring.value is None, "stopping sweep was clobbered by set_progress"

    # Stop completes → ring restored to the frozen %, hero shows where it halted.
    v.set_running(False)
    assert v._stopping is False
    assert v.progress_ring.value == 0.3 and v.linear.value == 0.3, v.progress_ring.value
    assert v.hero_value.value == "30%", v.hero_value.value
    assert v.action_circle.disabled is False  # re-enabled for the next run


def main() -> None:
    check_stop_progress_roundtrip()
    print("test_stop_progress_state: OK")


if __name__ == "__main__":
    main()
