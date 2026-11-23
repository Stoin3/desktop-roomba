"""Koppelt het Qt-roombavenster aan Windows (zie windows_shell.py).

* Overlay over het scherm; klikken vallen erdoor behalve op de roomba
  (WS_EX_TRANSPARENT wordt per frame aan/uit gezet op basis van de muis).
* In rust net boven de bureaubladiconen; tijdens een ronde bovenop alles.
* Slepen: de roomba hangt aan de muis (eigen klein venster, werkt over alle
  schermen); bij loslaten wordt het Verkenner-venster eronder bepaald.
* Systeemvak-icoon met het menu en meldingen.
"""

from __future__ import annotations

import logging
import time

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QCursor, QGuiApplication, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QSystemTrayIcon, QWidget

from . import windows_shell as ws

log = logging.getLogger("kde-roomba")


def overlay_geometry():
    """Overlay over alle schermen (als ze dezelfde schaal hebben), anders het hoofdscherm.
    Zo kan de roomba ook naar Verkenner-vensters op andere schermen rijden."""
    screens = QGuiApplication.screens()
    prim = QGuiApplication.primaryScreen()
    if not screens or prim is None:
        return None
    if len({round(sc.devicePixelRatio(), 2) for sc in screens}) == 1:
        rect = screens[0].geometry()
        for sc in screens[1:]:
            rect = rect.united(sc.geometry())
        return rect
    return prim.geometry()


def phys_to_logical(x: float, y: float) -> QPointF:
    """Fysieke schermpixels → Qt-coördinaten (per-monitor DPI)."""
    for sc in QGuiApplication.screens():
        g, dpr = sc.geometry(), sc.devicePixelRatio()
        if g.x() <= x < g.x() + g.width() * dpr and g.y() <= y < g.y() + g.height() * dpr:
            return QPointF(g.x() + (x - g.x()) / dpr, g.y() + (y - g.y()) / dpr)
    sc = QGuiApplication.primaryScreen()
    dpr = sc.devicePixelRatio() if sc else 1.0
    return QPointF(x / dpr, y / dpr)


def logical_to_phys(p: QPointF) -> tuple[int, int]:
    for sc in QGuiApplication.screens():
        g, dpr = sc.geometry(), sc.devicePixelRatio()
        if g.contains(p.toPoint()):
            return int(g.x() + (p.x() - g.x()) * dpr), int(g.y() + (p.y() - g.y()) * dpr)
    return int(p.x()), int(p.y())


class CarryWindow(QWidget):
    """Klein venster met de roomba dat de muis volgt tijdens het slepen."""

    def __init__(self, pixmap: QPixmap):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.pm = pixmap
        s = pixmap.size() / pixmap.devicePixelRatio()
        self.resize(s)

    def follow(self) -> None:
        c = QCursor.pos()
        self.move(c - QPoint(self.width() // 2, self.height() // 2))

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.drawPixmap(0, 0, self.pm)


class WinFolderView:
    """Zelfde vorm als DolphinLayout: positions(), view, icon, describe()."""

    def __init__(self, integ: "WinIntegration", view: ws.ViewInfo):
        self.integ = integ
        self.info = view
        self._update(view)

    def _update(self, view: ws.ViewInfo) -> None:
        self.info = view
        x, y, w, h = view.view_rect
        tl = self.integ.to_widget(x, y)
        br = self.integ.to_widget(x + w, y + h)
        self.view = (tl.x(), tl.y(), br.x() - tl.x(), br.y() - tl.y())
        sc = QGuiApplication.screenAt(phys_to_logical(x, y).toPoint())
        self.icon = int(view.icon / (sc.devicePixelRatio() if sc else 1.0))

    def describe(self) -> str:
        modes = {1: "pictogrammen", 2: "kleine pictogrammen", 3: "lijst", 4: "details", 5: "miniaturen",
                 6: "tegels", 8: "inhoud"}
        return f"Verkenner, {modes.get(self.info.mode, self.info.mode)}, icoon {self.info.icon}px, {len(self.info.items)} items"

    def positions(self) -> dict[str, tuple[float, float]]:
        fresh = ws.refresh_view(self.info)  # bestanden schuiven op na verwijderen
        if fresh is not None:
            self._update(fresh)
        out = {}
        for name, (px, py) in self.info.items.items():
            p = self.integ.to_widget(px, py)
            out[name] = (p.x(), p.y())
        return out


class WinIntegration:
    def __init__(self, window) -> None:
        self.w = window
        self.hwnd = 0
        self.topmost = False
        self.passthrough: bool | None = None
        self.carry: CarryWindow | None = None
        self._last_z = 0.0
        self._desk_cache: tuple[float, dict] | None = None
        self.tray: QSystemTrayIcon | None = None
        self._idle_since: float | None = None
        self._trimmed = False

    # ------------------------------------------------------------ opzetten
    def after_show(self) -> None:
        self.hwnd = int(self.w.winId())
        self.passthrough = None
        if not self.topmost:
            ws.place_on_desktop(self.hwnd)
        g = self.w.geometry()
        sc = self.w.screen()
        log.info("Windows: overlay %#x op (%d,%d) %dx%d, schaal %.2f, boven het bureaublad geplaatst",
                 self.hwnd, g.x(), g.y(), g.width(), g.height(), sc.devicePixelRatio() if sc else 1.0)
        if self.tray is None and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QIcon(self.w.roomba_pixmap()), self.w)
            self.tray.setToolTip("Roomba – klik voor het menu")
            self.tray.activated.connect(lambda _r: self.w.show_menu(QCursor.pos()))
            self.tray.show()

    def notify(self, title: str, body: str) -> None:
        if self.tray is not None:
            self.tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 4000)

    # ------------------------------------------------------------ coördinaten
    def to_widget(self, px: float, py: float) -> QPointF:
        g = phys_to_logical(px, py)
        return self.w.to_overlay(g.toPoint()) + QPointF(g.x() - int(g.x()), g.y() - int(g.y()))

    # ------------------------------------------------------------ per frame
    def tick(self) -> None:
        if not self.hwnd:
            return
        w = self.w
        if self.carry is not None:
            self.carry.follow()
            self._set_passthrough(False)
            return
        c = w.to_overlay(QCursor.pos())
        hit = w.on_roomba(c) or (w.bubble_alpha > 0.3 and getattr(w, "_bubble_rect", QRectF()).contains(c))
        self._set_passthrough(not hit and w.press_pos is None and not w.dragging)
        now = time.monotonic()
        # Na 20 s rust: ongebruikt geheugen teruggeven aan Windows (één keer per rustperiode)
        if w.compact and not w.busy():
            if self._idle_since is None:
                self._idle_since = now
            elif not self._trimmed and now - self._idle_since > 20:
                self._trimmed = True
                self.trim_memory()
        else:
            self._idle_since, self._trimmed = None, False
        if not self.topmost and now - self._last_z > 1.0:  # ook na Win+D weer boven de iconen
            self._last_z = now
            ws.place_on_desktop(self.hwnd)

    @staticmethod
    def trim_memory() -> None:
        """Python-afval opruimen en de 'working set' van het proces leegmaken: Windows
        haalt pagina's pas terug als ze weer nodig zijn (dat is wat Taakbeheer toont)."""
        import ctypes
        import gc

        gc.collect()
        k32 = ctypes.windll.kernel32
        k32.SetProcessWorkingSetSize(k32.GetCurrentProcess(), ctypes.c_size_t(-1), ctypes.c_size_t(-1))
        log.info("Geheugen teruggegeven aan Windows (rust)")

    def _set_passthrough(self, on: bool) -> None:
        """Klikken doorlaten (behalve op de roomba). Direct op het Windows-venster
        gezet en elke tick gecontroleerd: een Qt-vlag wordt op Windows pas echt
        toegepast bij een nieuw beeld, en in de zuinige modus komt dat er niet."""
        if not self.hwnd:
            return
        if on != self.passthrough or ws.click_through(self.hwnd) != on:
            self.passthrough = on
            ws.set_click_through(self.hwnd, on)

    def set_topmost(self, on: bool) -> None:
        self.topmost = on
        if self.hwnd:
            ws.set_topmost(self.hwnd, on)
            if not on:
                ws.place_on_desktop(self.hwnd)

    # ------------------------------------------------------------ bureaublad
    def desktop_positions(self) -> dict[str, QPointF] | None:
        now = time.monotonic()
        if self._desk_cache and now - self._desk_cache[0] < 0.5:
            return self._desk_cache[1]
        view = ws.desktop_view(str(self.w.desktop))
        if view is None:
            return None
        pos = {n: self.to_widget(x, y) for n, (x, y) in view.items.items()}
        self._desk_cache = (now, pos)
        return pos

    # ------------------------------------------------------------ slepen
    def start_carry(self) -> None:
        self.carry = CarryWindow(self.w.roomba_pixmap())
        self.carry.follow()
        self.carry.show()
        if self.carry.winId():
            ws.set_topmost(int(self.carry.winId()), True)

    def end_carry(self) -> tuple[str, "WinFolderView | None"] | None:
        carry, self.carry = self.carry, None
        skip = {self.hwnd}
        if carry is not None:
            skip.add(int(carry.winId()))
            carry.hide()
            carry.deleteLater()
        x, y = ws.cursor_pos()
        hit = ws.folder_at(x, y, skip, str(self.w.desktop))
        if hit is None:
            return None
        folder, view = hit
        return folder, (WinFolderView(self, view) if view is not None else None)
