"""Self-check for the diag log mirror (diag/netfree-machine) — no framework.

    python tests/test_log_mirror.py

The whole point of the mirror is to run UNATTENDED on a filtered machine. If the
scp command ever loses its non-interactive flags, the first push hangs forever on
a host-key / password prompt with no one to answer — a silent freeze on exactly
the machine we can't debug. This pins the load-bearing flags and target.
"""
from src.core.log_mirror import _build_cmd, _REMOTE


def check_cmd_cannot_hang() -> None:
    cmd = _build_cmd("local.log", _REMOTE, "key")
    joined = " ".join(cmd)
    assert "BatchMode=yes" in joined, "scp must never prompt for a password"
    assert "StrictHostKeyChecking=accept-new" in joined, "scp must auto-accept the host key, not prompt"
    assert "ConnectTimeout=10" in joined, "scp must give up fast on an unreachable box"
    assert cmd[-1] == _REMOTE, "remote target must be the last arg"
    assert cmd[-2] == "local.log", "local file must be the source (second-to-last)"


def main() -> None:
    check_cmd_cannot_hang()
    print("OK: log mirror command is non-interactive and bounded")


if __name__ == "__main__":
    main()
