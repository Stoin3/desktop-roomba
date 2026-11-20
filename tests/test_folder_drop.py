import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kde_roomba import folder_drop

ROOT = Path(__file__).resolve().parents[1]


def test_resolve_folder_rules(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "Documenten" / "rommel").mkdir(parents=True)
    (home / ".config").mkdir()
    monkeypatch.setenv("HOME", str(home))
    ok, _ = folder_drop.resolve_folder(str(home / "Documenten" / "rommel"))
    assert ok == (home / "Documenten" / "rommel").resolve()
    ok, _ = folder_drop.resolve_folder("file://" + str(home / "Documenten"))
    assert ok is not None
    assert folder_drop.resolve_folder(str(home))[0] is None            # hele thuismap
    assert folder_drop.resolve_folder(str(home / ".config"))[0] is None  # verborgen
    assert folder_drop.resolve_folder("/usr/share")[0] is None          # buiten thuismap
    assert folder_drop.resolve_folder("smb://nas/share")[0] is None     # niet lokaal
    assert folder_drop.resolve_folder(str(home / "bestaat-niet"))[0] is None


@pytest.mark.skipif(not shutil.which("dbus-run-session"), reason="geen dbus-run-session")
def test_dolphin_style_dbus_call_reaches_roomba(tmp_path):
    """Doet wat Dolphin bij een drop doet: org.kde.ark.DndExtract.extractSelectedFilesTo."""
    code = f"""
import sys
from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtDBus import QDBusConnection, QDBusMessage
from kde_roomba import folder_drop
app = QCoreApplication(sys.argv)
r = folder_drop.DropReceiver()
assert r.ok
md = r.mime_data()
got = []
r.folderDropped.connect(lambda p: (got.append(p), app.quit()))
def drop():
    msg = QDBusMessage.createMethodCall(bytes(md.data(folder_drop.SERVICE_MIME)).decode(),
                                        bytes(md.data(folder_drop.PATH_MIME)).decode(),
                                        "org.kde.ark.DndExtract", "extractSelectedFilesTo")
    msg.setArguments([{str(tmp_path)!r}])
    QDBusConnection.sessionBus().asyncCall(msg)
QTimer.singleShot(100, drop)
QTimer.singleShot(5000, app.quit)
app.exec()
print("GOT", got)
"""
    res = subprocess.run(["dbus-run-session", "--", sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True, timeout=30, env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    assert f"GOT ['{tmp_path}']" in res.stdout, res.stdout + res.stderr
