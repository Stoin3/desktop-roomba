"""Vensterposities opvragen bij KWin (Wayland).

Onder Wayland mag een gewoon programma niet zien waar andere vensters staan.
KWin kan het wel vertellen: we laden via D-Bus (org.kde.KWin /Scripting) een
klein, tijdelijk KWin-script dat de vensterlijst en het bruikbare
schermgebied terugstuurt via ``callDBus``, en verwijderen het script meteen
daarna weer. Er wordt niets in je KDE-instellingen opgeslagen.
"""

from __future__ import annotations

import itertools
import json
import logging
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtClassInfo, pyqtSlot
from PyQt6.QtDBus import (QDBusAbstractAdaptor, QDBusConnection, QDBusMessage, QDBusPendingCallWatcher,
                          QDBusPendingReply)

from .config import state_dir

log = logging.getLogger("kde-roomba")

OBJECT_PATH = "/KdeRoomba/KWinReport"
INTERFACE = "org.kde.kderoomba.KWinReport"

SCRIPT = r"""
// Tijdelijk script van KDE Roomba: vensters + schermgebieden terugmelden.
(function () {
    var res = { windows: [], areas: {} };
    try {
        var outs = workspace.screens || [];
        for (var i = 0; i < outs.length; i++) {
            var a = workspace.clientArea(KWin.MaximizeArea, outs[i], workspace.currentDesktop);
            var g = outs[i].geometry;
            res.areas[outs[i].name] = { x: a.x, y: a.y, w: a.width, h: a.height,
                                        ox: g ? g.x : 0, oy: g ? g.y : 0 };
        }
        var wins = workspace.windowList();
        for (var j = 0; j < wins.length; j++) {
            var w = wins[j];
            if (!w.normalWindow || w.minimized || w.deleted) continue;
            var c = w.clientGeometry;
            var onDesk = w.onAllDesktops || !w.desktops || w.desktops.length === 0 ||
                         w.desktops.indexOf(workspace.currentDesktop) >= 0;
            res.windows.push({ cls: String(w.resourceClass), file: String(w.desktopFileName || ""),
                               caption: String(w.caption), x: c.x, y: c.y, w: c.width, h: c.height,
                               active: !!w.active, stack: w.stackingOrder, desk: !!onDesk,
                               output: w.output ? String(w.output.name) : "" });
        }
    } catch (e) {
        res.error = String(e);
    }
    callDBus("@SERVICE@", "@PATH@", "@IFACE@", "report", JSON.stringify(res));
})();
"""


@pyqtClassInfo("D-Bus Interface", INTERFACE)
class _ReportAdaptor(QDBusAbstractAdaptor):
    def __init__(self, parent: "WindowQuery"):
        super().__init__(parent)
        self._q = parent

    @pyqtSlot(str)
    def report(self, data: str) -> None:
        self._q._received(data)


class WindowQuery(QObject):
    """Eén vraag tegelijk: query(callback) → callback(dict | None)."""

    _counter = itertools.count(1)

    def __init__(self) -> None:
        super().__init__()
        self._adaptor = _ReportAdaptor(self)
        self.bus = QDBusConnection.sessionBus()
        self.ok = self.bus.isConnected() and self.bus.registerObject(OBJECT_PATH, self)
        self._callback: Callable[[dict | None], None] | None = None
        self._plugin = ""
        self._watchers: list[QDBusPendingCallWatcher] = []

    def available(self) -> bool:
        if not self.ok:
            return False
        iface = self.bus.interface()
        return bool(iface and iface.isServiceRegistered("org.kde.KWin").value())

    def query(self, callback: Callable[[dict | None], None], timeout_ms: int = 2500) -> None:
        if not self.available():
            callback(None)
            return
        self._finish(None)  # eventuele vorige vraag afbreken
        self._callback = callback
        self._plugin = f"kde-roomba-query-{next(self._counter)}"
        path = state_dir() / "kwin-query.js"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SCRIPT.replace("@SERVICE@", self.bus.baseService())
                        .replace("@PATH@", OBJECT_PATH).replace("@IFACE@", INTERFACE))
        self._call("/Scripting", "org.kde.kwin.Scripting", "unloadScript", [self._plugin])
        self._call("/Scripting", "org.kde.kwin.Scripting", "loadScript", [str(path), self._plugin], self._loaded)
        QTimer.singleShot(timeout_ms, lambda p=self._plugin: self._timeout(p))

    # ------------------------------------------------------------------
    def _call(self, path: str, iface: str, method: str, args: list, on_reply=None) -> None:
        msg = QDBusMessage.createMethodCall("org.kde.KWin", path, iface, method)
        msg.setArguments(args)
        watcher = QDBusPendingCallWatcher(self.bus.asyncCall(msg), self)
        self._watchers.append(watcher)

        def done(w: QDBusPendingCallWatcher) -> None:
            reply = QDBusPendingReply(w).reply()  # QDBusMessage
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                log.warning("KWin %s: %s", method, reply.errorMessage())
            if on_reply:
                on_reply(reply)
            self._watchers.remove(w)
            w.deleteLater()

        watcher.finished.connect(done)

    def _loaded(self, reply: QDBusMessage) -> None:
        args = reply.arguments()
        if reply.type() == QDBusMessage.MessageType.ErrorMessage or not args or int(args[0]) < 0:
            log.warning("KWin-script laden mislukt")
            self._finish(None)
            return
        sid = int(args[0])
        # Script starten; oudere KWin-versies: alle geladen scripts starten.
        self._call(f"/Scripting/Script{sid}", "org.kde.kwin.Script", "run", [],
                   lambda r: r.type() == QDBusMessage.MessageType.ErrorMessage
                   and self._call("/Scripting", "org.kde.kwin.Scripting", "start", []))

    def _received(self, data: str) -> None:
        try:
            parsed = json.loads(data)
        except ValueError:
            parsed = None
        if parsed and parsed.get("error"):
            log.warning("KWin-script meldt: %s", parsed["error"])
        QTimer.singleShot(0, lambda: self._finish(parsed))

    def _timeout(self, plugin: str) -> None:
        if self._callback and plugin == self._plugin:
            log.warning("KWin gaf geen vensterlijst (time-out)")
            self._finish(None)

    def _finish(self, result: dict | None) -> None:
        cb, self._callback = self._callback, None
        if self._plugin:
            self._call("/Scripting", "org.kde.kwin.Scripting", "unloadScript", [self._plugin])
        if cb:
            cb(result)


def pick_dolphin_window(data: dict, folder: Path) -> dict | None:
    """Het Dolphin-venster waarin waarschijnlijk is neergezet."""
    wins = [w for w in data.get("windows", [])
            if ("dolphin" in w.get("cls", "").lower() or "dolphin" in w.get("file", "").lower()) and w.get("desk", True)]
    if not wins:
        return None

    def score(w: dict) -> tuple:
        cap = w.get("caption", "")
        return (folder.name.lower() in cap.lower() or str(folder) in cap, w.get("active", False), w.get("stack", 0))

    return max(wins, key=score)
