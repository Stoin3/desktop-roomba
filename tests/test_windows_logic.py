"""Windows-logica getest met een nagebootste windows_shell (draait ook op Linux)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CODE = r'''
import os, sys, types
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from dataclasses import dataclass
# --- nep-windows_shell -------------------------------------------------------
fake = types.ModuleType("kde_roomba.windows_shell")
@dataclass
class ViewInfo:
    folder: str; top_hwnd: int; view_hwnd: int; view_rect: tuple; mode: int; icon: int; spacing: tuple; items: dict
fake.ViewInfo = ViewInfo
calls = []
# Verkenner-venster op fysieke pixels (300,150) 900x600, scherm-schaal 1.5 (zie hieronder)
VIEW = ViewInfo("C:/Users/x/Downloads", 11, 12, (300, 150, 900, 600), 1, 72, (120, 120),
                {"asdfgh.txt": (360.0, 210.0), "verslag.docx": (480.0, 210.0)})
fake.refresh_view = lambda v: v
fake.desktop_view = lambda folder: ViewInfo(folder, 1, 2, (0, 0, 1500, 1500), 1, 72, (110, 110),
                                            {"a.txt": (75.0, 60.0)})
fake.cursor_pos = lambda: (450, 300)
fake.folder_at = lambda x, y, skip, desk: (calls.append((x, y, sorted(skip))) or ("C:/Users/x/Downloads", VIEW))
fake.place_on_desktop = lambda h: calls.append(("desk", h))
fake.set_topmost = lambda h, on: calls.append(("top", on))
sys.modules["kde_roomba.windows_shell"] = fake
# -----------------------------------------------------------------------------
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import QPointF
app = QApplication(sys.argv)
from kde_roomba import windows_integration as wi

sc = app.primaryScreen()
dpr = sc.devicePixelRatio()
g = sc.geometry()
# 1. pixelomrekening (met de schaal van dit scherm)
p = wi.phys_to_logical(g.x() + 150 * dpr, g.y() + 90 * dpr)
assert abs(p.x() - (g.x() + 150)) < 0.01 and abs(p.y() - (g.y() + 90)) < 0.01, p
assert wi.logical_to_phys(QPointF(g.x() + 150, g.y() + 90)) == (int(g.x() + 150 * dpr), int(g.y() + 90 * dpr))
assert wi.overlay_geometry() == g

class FakeRoomba(QWidget):
    desktop = "C:/Users/x/Desktop"
    bubble_alpha = 0.0; press_pos = None; dragging = False
    def on_roomba(self, pos): return False
    def to_overlay(self, gp): return QPointF(self.mapFromGlobal(gp))
    def roomba_pixmap(self):
        from PyQt6.QtGui import QPixmap; pm = QPixmap(40, 40); pm.fill(); return pm
    def show_menu(self, pos): pass
w = FakeRoomba(); w.setGeometry(g); w.show()
integ = wi.WinIntegration(w)
integ.hwnd = 99
# 2. Verkenner-weergave → widget-coördinaten
view = wi.WinFolderView(integ, VIEW)
pos = view.positions()
from PyQt6.QtCore import QPoint
ax, ay = pos["asdfgh.txt"]
exp = w.mapFromGlobal(QPoint(int(g.x() + 360 / dpr), int(g.y() + 210 / dpr)))
assert abs(ax - exp.x()) < 1.5 and abs(ay - exp.y()) < 1.5, (ax, ay, exp, dpr)
vx, vy, vw, vh = view.view
assert abs(vw - 900 / dpr) < 1.5 and abs(vh - 600 / dpr) < 1.5
assert view.icon == int(72 / dpr) and "Verkenner" in view.describe()
# 3. bureaubladposities
d = integ.desktop_positions()
assert abs(d["a.txt"].x() - w.mapFromGlobal(QPoint(int(g.x() + 75 / dpr), 0)).x()) < 1.5
# 4. slepen en loslaten op een Verkenner-venster
integ.start_carry(); integ.tick()
folder, v2 = integ.end_carry()
assert folder == "C:/Users/x/Downloads" and v2 is not None and integ.carry is None
assert 99 in calls[-1][2] and len(calls[-1][2]) == 2   # eigen venster + sleepvenster overgeslagen
# 5. z-volgorde
integ.set_topmost(True); integ.set_topmost(False)
assert ("top", True) in calls and ("top", False) in calls and ("desk", 99) in calls
print("WINDOWS-LOGICA OK")
'''


def test_windows_integration_logic():
    res = subprocess.run([sys.executable, "-c", CODE], cwd=ROOT, capture_output=True, text=True, timeout=60,
                         env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    assert "WINDOWS-LOGICA OK" in res.stdout, res.stdout + res.stderr[-2500:]


def test_windows_folder_rules(monkeypatch, tmp_path):
    from kde_roomba import folders
    monkeypatch.setattr(folders, "_IS_WIN", True)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    for k in ("SystemRoot", "ProgramFiles(x86)", "ProgramData", "APPDATA", "LOCALAPPDATA"):
        monkeypatch.setenv(k, str(tmp_path / "elders" / k))  # tmp_path ligt op Windows in AppData\Local\Temp
    (tmp_path / "pf" / "App").mkdir(parents=True)
    (tmp_path / "data" / "rommel").mkdir(parents=True)
    assert folders.resolve_folder(str(tmp_path / "pf" / "App"))[0] is None          # programmamap
    assert folders.resolve_folder(str(tmp_path / "data" / "rommel"))[0] is not None  # andere schijf/map mag
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    assert folders.resolve_folder(str(tmp_path / "data" / "rommel"))[0] is None      # AppData blijft dicht
    assert folders.resolve_folder("::{20D04FE0-3AEA-1069-A2D8-08002B30309D}")[0] is None  # 'Deze pc'


COMPACT = r'''
import os, sys, types
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.geteuid = lambda: 1000
from dataclasses import dataclass
fake = types.ModuleType("kde_roomba.windows_shell")
@dataclass
class ViewInfo:
    folder: str; top_hwnd: int; view_hwnd: int; view_rect: tuple; mode: int; icon: int; spacing: tuple; items: dict
fake.ViewInfo = ViewInfo
for name in ("place_on_desktop", "set_topmost"):
    setattr(fake, name, lambda *a: None)
fake.desktop_view = lambda folder: None
fake.cursor_pos = lambda: (0, 0)
sys.modules["kde_roomba.windows_shell"] = fake
from PyQt6.QtCore import QTimer, QPointF, QPoint
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtCore import Qt, QEvent
import kde_roomba.app as A
from kde_roomba import windows_integration
A.IS_WINDOWS = True
A.windows_integration = windows_integration
A._is_admin = lambda: False
res = {}
orig = A.RoombaWindow.show
def show(self):
    orig(self)
    def idle_check():
        res["compact"] = self.compact
        res["size"] = (self.width(), self.height())
        res["full"] = (self.geom.width(), self.geom.height())
        # dubbelklik op de roomba via een echt muisevent in het compacte venster
        local = QPointF(self.robot.x, self.robot.y) - self.view_off
        ev = QMouseEvent(QEvent.Type.MouseButtonDblClick, local, local, Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        self.mouseDoubleClickEvent(ev)
        res["state_after_click"] = self.state
        QTimer.singleShot(400, active_check)
    def active_check():
        res["compact_active"] = self.compact
        res["size_active"] = (self.width(), self.height())
        self.grab()
        print("RES", res, flush=True)
        A.QApplication.quit()
    QTimer.singleShot(2500, idle_check)
A.RoombaWindow.show = show
sys.exit(A.main())
'''


def test_windows_compact_window_at_rest(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "s"),
               XDG_CONFIG_HOME=str(tmp_path / "c"), QT_QPA_PLATFORM="offscreen")
    (tmp_path / "Desktop").mkdir()
    res = subprocess.run([sys.executable, "-c", COMPACT], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    line = next((l for l in res.stdout.splitlines() if l.startswith("RES")), None)
    assert line, res.stdout + res.stderr[-2000:]
    r = eval(line[4:])
    assert r["compact"] is True
    assert r["size"][0] * r["size"][1] < 0.25 * r["full"][0] * r["full"][1], r   # veel kleiner in rust
    assert r["state_after_click"] == "thinking", r                             # klik kwam goed aan
    assert r["compact_active"] is False and r["size_active"] == r["full"], r   # tijdens werk: volledig
