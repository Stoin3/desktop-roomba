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


def test_repeated_cleaning_rounds_do_not_crash(tmp_path):
    """Regressie: 'QThread: Destroyed while thread is still running' → Aborted."""
    desk = tmp_path / "Desktop"
    desk.mkdir()
    env = dict(os.environ, HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "state"),
               XDG_CONFIG_HOME=str(tmp_path / "cfg"), QT_QPA_PLATFORM="offscreen")
    code = f"""
import os, sys, gc, time; os.geteuid = lambda: 1000
from pathlib import Path
from PyQt6.QtCore import QTimer
import kde_roomba.app as A, kde_roomba.brain as B
B.desktop_dir = lambda: Path({str(desk)!r})
orig_classify = B.classify
def slow_classify(*a, **k):
    r = orig_classify(*a, **k); return r
B.classify = slow_classify
orig_run = A.BrainWorker.run
def lingering_run(self):
    orig_run(self); time.sleep(0.3)   # thread is na het resultaat nog even bezig
A.BrainWorker.run = lingering_run
rounds = {{"n": 0}}
orig_done = A.RoombaWindow.on_brain_done
def done(self, *a):
    orig_done(self, *a)
    gc.collect()            # ruim weggegooide objecten METEEN op (worst case)
    rounds["n"] += 1
    self.queue = []; self.state = "charging"
    if rounds["n"] < 6:
        QTimer.singleShot(0, self.start_cleaning)
    else:
        QTimer.singleShot(300, A.QApplication.quit)
A.RoombaWindow.on_brain_done = done
orig_show = A.RoombaWindow.show
def show(self):
    orig_show(self); self.cfg.use_ai = False; QTimer.singleShot(100, self.start_cleaning)
    QTimer.singleShot(20000, A.QApplication.quit)
A.RoombaWindow.show = show
rc = A.main()
print("ROUNDS", rounds["n"])
sys.exit(rc)
"""
    res = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr[-2000:]
    assert "ROUNDS 6" in res.stdout, res.stdout + res.stderr[-2000:]
