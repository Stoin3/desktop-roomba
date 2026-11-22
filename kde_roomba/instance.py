"""Eén roomba tegelijk – maar nooit een doodlopende "draait al".

* Een lock-bestand bewaakt dat er één exemplaar draait.
* Het draaiende exemplaar luistert op een lokale socket naar opdrachten:
  ``show`` (weer zichtbaar maken), ``quit`` en ``ping``.
* Start je ``kde-roomba`` terwijl er al een draait, dan krijgt die ``show``.
  Antwoordt hij niet (vastgelopen), dan wordt hij gestopt en neemt het nieuwe
  exemplaar het over.
"""

from __future__ import annotations

import logging
import os
import signal
import time

from PyQt6.QtCore import QLockFile, QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from .config import state_dir

log = logging.getLogger("kde-roomba")


def socket_name() -> str:
    if hasattr(os, "getuid"):
        return f"kde-roomba-{os.getuid()}"
    import getpass

    return f"kde-roomba-{getpass.getuser()}"


def send(cmd: str, timeout_ms: int = 1500) -> str | None:
    """Stuurt een opdracht naar het draaiende exemplaar. None = geen antwoord."""
    sock = QLocalSocket()
    sock.connectToServer(socket_name())
    if not sock.waitForConnected(timeout_ms):
        return None
    sock.write((cmd + "\n").encode())
    sock.flush()
    if sock.bytesToWrite() > 0:
        sock.waitForBytesWritten(timeout_ms)  # (False als alles al weg is – geen fout)
    deadline = time.monotonic() + timeout_ms / 1000
    data = b""
    while b"\n" not in data and time.monotonic() < deadline:
        if sock.waitForReadyRead(100):
            data += bytes(sock.readAll())
    sock.disconnectFromServer()
    return data.decode(errors="replace").strip() or None


def _process_cmdline(pid: int) -> str | None:
    """Opdrachtregel/programma van een proces; None = onbekend."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
            if not h:
                return ""
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
            ctypes.windll.kernel32.CloseHandle(h)
            # python.exe of roomba.exe: argumenten zijn hier niet zichtbaar
            return None if ok and ("python" in buf.value.lower() or "roomba" in buf.value.lower()) else ""
        except (OSError, AttributeError):
            return None
    try:
        return open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return ""


def _alive(pid: int) -> bool:
    if os.name == "nt":  # let op: os.kill(pid, 0) BEËINDIGT een proces op Windows
        import ctypes

        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _terminate(pid: int) -> None:
    if os.name == "nt":
        import ctypes

        h = ctypes.windll.kernel32.OpenProcess(0x0001 | 0x1000, False, pid)  # TERMINATE | QUERY
        if h:
            ctypes.windll.kernel32.TerminateProcess(h, 1)
            ctypes.windll.kernel32.WaitForSingleObject(h, 3000)
            ctypes.windll.kernel32.CloseHandle(h)
        return
    for sig, wait in ((signal.SIGTERM, 2.0), (signal.SIGKILL, 1.0)):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return
        end = time.monotonic() + wait
        while time.monotonic() < end:
            if not _alive(pid):
                return
            time.sleep(0.1)


class Lock:
    def __init__(self) -> None:
        state_dir().mkdir(parents=True, exist_ok=True)
        self.lock = QLockFile(str(state_dir() / "roomba.lock"))
        self.lock.setStaleLockTime(0)

    def try_lock(self, timeout_ms: int = 200) -> bool:
        return self.lock.tryLock(timeout_ms)

    def holder_pid(self) -> int | None:
        info = self.lock.getLockInfo()
        ok, pid = (info[0], info[1]) if isinstance(info, tuple) else (False, 0)
        return int(pid) if ok and pid and pid != os.getpid() else None

    def kill_holder(self) -> bool:
        """Stopt een vastgelopen exemplaar (alleen als het echt kde_roomba is)."""
        pid = self.holder_pid()
        if not pid:
            self.lock.removeStaleLockFile()
            return True
        cmdline = _process_cmdline(pid)
        if cmdline is not None and "kde_roomba" not in cmdline and "roomba" not in cmdline.lower():
            log.info("Lock hoort bij proces %s dat geen roomba is; lock opruimen.", pid)
            self.lock.removeStaleLockFile()
            return True
        log.warning("Vastgelopen roomba (pid %s) wordt gestopt.", pid)
        _terminate(pid)
        self.lock.removeStaleLockFile()
        return True

    def unlock(self) -> None:
        self.lock.unlock()


class Server(QObject):
    command = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.server = QLocalServer(self)
        QLocalServer.removeServer(socket_name())  # oud socketbestand na crash
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.ok = self.server.listen(socket_name())
        if not self.ok:
            log.warning("Opdrachtensocket niet beschikbaar: %s", self.server.errorString())
        self.server.newConnection.connect(self._on_conn)

    def _on_conn(self) -> None:
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._on_read(s))
            sock.disconnected.connect(sock.deleteLater)
            # de opdracht kan al binnen zijn vóór readyRead verbonden was
            self._on_read(sock)

    def _on_read(self, sock: QLocalSocket) -> None:
        while sock.canReadLine():
            line = bytes(sock.readLine()).decode(errors="replace").strip()
            if not line:
                continue
            log.info("Opdracht ontvangen: %s", line)
            sock.write(b"ok\n")
            sock.flush()
            self.command.emit(line)
