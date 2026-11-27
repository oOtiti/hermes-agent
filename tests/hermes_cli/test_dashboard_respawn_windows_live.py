"""Dashboard respawn keeps a windowless console of its own on Windows (#160538)."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from hermes_cli._subprocess_compat import windows_hide_flags


_DASHBOARD_CHILD = """
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys

from tests.waiting import wait_until

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.GetConsoleWindow.restype = wintypes.HWND
pids = (wintypes.DWORD * 32)()
count = kernel.GetConsoleProcessList(pids, len(pids))
assert 0 < count <= len(pids), (count, ctypes.get_last_error())
Path(sys.argv[1]).write_text(json.dumps({
    "pid": os.getpid(), "console": list(pids[:count]), "hwnd": kernel.GetConsoleWindow() or 0,
}), encoding="utf-8")
wait_until(Path(sys.argv[2]).exists, timeout=25, what="launcher acknowledgement")
"""

_LAUNCHER = """
import json
import os
from pathlib import Path
import sys

from hermes_cli.main_dashboard import _respawn_dashboard_processes
from tests.waiting import wait_until

command = [sys.executable, "-c", sys.argv[1], sys.argv[2], sys.argv[3], "dashboard"]
assert not _respawn_dashboard_processes([command])
report = Path(sys.argv[2])
wait_until(report.is_file, what="dashboard console report")
print(json.dumps({"launcher": os.getpid(), **json.loads(report.read_text(encoding="utf-8"))}))
"""


@pytest.mark.platforms("windows")
def test_respawned_dashboard_owns_a_windowless_console(tmp_path):
    # The launcher starts hidden, so inheriting its console on the old path
    # still cannot open a window during the test.
    report, stop = tmp_path / "console.json", tmp_path / "stop"
    root = Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(
            [sys.executable, "-c", _LAUNCHER, _DASHBOARD_CHILD, str(report), str(stop)],
            cwd=root, env={**os.environ, "HERMES_HOME": str(tmp_path), "PYTHONPATH": str(root)},
            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
            creationflags=windows_hide_flags(), timeout=25, check=False,
        )
    finally:
        stop.touch()

    assert result.returncode == 0, result.stdout + result.stderr
    state = json.loads(result.stdout.splitlines()[-1])
    assert state["hwnd"] == 0 and state["pid"] in state["console"], state
    assert state["launcher"] not in state["console"], state
