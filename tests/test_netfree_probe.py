"""Self-check for the proxy/env probe (diag/netfree-machine) — no framework.

    python tests/test_netfree_probe.py

The probe reports WHEN HKCU\\Environment was last modified, to date the stray proxy.
That hinges on converting a Windows FILETIME (100-ns ticks since 1601) to a datetime
— an easy place to get the epoch or the scale wrong, which would point the install-
window cross-reference at the wrong date. This pins it.
"""
import datetime
import os
import sys

# Runnable as `python tests/test_netfree_probe.py` too: project root on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.netfree_probe import _filetime_to_dt  # noqa: E402


def check() -> None:
    assert _filetime_to_dt(0) == datetime.datetime(1601, 1, 1), "FILETIME 0 is the 1601 epoch"
    assert _filetime_to_dt(10_000_000) == datetime.datetime(1601, 1, 1, 0, 0, 1), \
        "10M ticks = 1 second (100-ns scale)"
    # A realistic value: round-trip a known date through the tick math.
    known = datetime.datetime(2021, 1, 1, 12, 30)
    ticks = int((known - datetime.datetime(1601, 1, 1)).total_seconds() * 10_000_000)
    assert _filetime_to_dt(ticks) == known, "round-trips a real date"


def main() -> None:
    check()
    print("OK: FILETIME-to-datetime conversion has the right epoch and scale")


if __name__ == "__main__":
    main()
