import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_running_instance_answers_commands(tmp_path):
    env = dict(os.environ, XDG_STATE_HOME=str(tmp_path), QT_QPA_PLATFORM="offscreen")
    server = subprocess.Popen([sys.executable, "-c", """
import sys
from PyQt6.QtCore import QCoreApplication, QTimer
from kde_roomba import instance
app = QCoreApplication(sys.argv)
s = instance.Server()
s.command.connect(lambda c: (print("GOT", c, flush=True), c == "quit" and app.quit()))
QTimer.singleShot(8000, app.quit)
app.exec()
"""], cwd=ROOT, env=env, stdout=subprocess.PIPE, text=True)
    time.sleep(1.0)
    client = subprocess.run([sys.executable, "-c", """
import sys
from PyQt6.QtCore import QCoreApplication
from kde_roomba import instance
a = QCoreApplication(sys.argv)
print(instance.send("show"), instance.send("quit"))
"""], cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
    out, _ = server.communicate(timeout=10)
    assert client.stdout.strip() == "ok ok", client.stdout + client.stderr
    assert "GOT show" in out and "GOT quit" in out


def test_every_outfit_draws_and_can_be_selected(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "s"),
               XDG_CONFIG_HOME=str(tmp_path / "c"), QT_QPA_PLATFORM="offscreen")
    code = """
import os, sys; os.geteuid = lambda: 1000
from PyQt6.QtCore import QTimer
import kde_roomba.app as A
from kde_roomba import outfits
orig = A.RoombaWindow.show
def show(self):
    orig(self)
    def go():
        for o in outfits.OUTFITS.values():
            assert not self.outfit_icon(o).isNull()
            self.set_outfit(o)
            self.grab()           # tekent het venster met dit outfit
            self.roomba_pixmap()  # sleepafbeelding
        print("OUTFITS", len(outfits.OUTFITS), self.cfg.outfit, flush=True)
        A.QApplication.quit()
    QTimer.singleShot(300, go)
A.RoombaWindow.show = show
sys.exit(A.main())
"""
    res = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr[-1500:]
    assert "OUTFITS 12 spook" in res.stdout, res.stdout + res.stderr[-1500:]
    assert '"outfit": "spook"' in (tmp_path / "c" / "kde-roomba" / "config.json").read_text()
