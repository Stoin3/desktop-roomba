"""Rooktest: het programma moet echt kunnen opstarten (alle imports + venster)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_modules_import():
    import kde_roomba
    from kde_roomba import app, art, brain, config, desktop_layout, kwin, wayland_layer  # noqa: F401

    assert kde_roomba.APP_ID and kde_roomba.__version__
    assert callable(app.main)


def test_program_starts_and_shows_window(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "state"),
               XDG_CONFIG_HOME=str(tmp_path / "cfg"), QT_QPA_PLATFORM="offscreen")
    code = (
        "import os, sys; os.geteuid = lambda: 1000\n"
        "from PyQt6.QtCore import QTimer\n"
        "import kde_roomba.app as A\n"
        "orig = A.RoombaWindow.show\n"
        "def show(self):\n"
        "    orig(self); QTimer.singleShot(3500, A.QApplication.quit)\n"
        "A.RoombaWindow.show = show\n"
        "sys.exit(A.main())\n"
    )
    res = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    log = (tmp_path / "state" / "kde-roomba" / "roomba.log").read_text()
    assert res.returncode == 0, res.stderr + log
    assert "Venster getoond" in log and "Eerste frame getekend" in log and "Status na 3 s" in log, log
