"""De roomba naar een Dolphin-map slepen.

Wayland laat een programma niet zien welk venster onder de muis zit of welke
map Dolphin open heeft. KDE heeft daar wel een nette oplossing voor, bedoeld
voor Ark (uitpakken door te slepen): bevat een sleepactie de MIME-types

    application/x-kde-ark-dndextract-service   (D-Bus-naam van de afzender)
    application/x-kde-ark-dndextract-path      (D-Bus-objectpad)

dan roepen Dolphin (DragAndDropHelper::dropUrls) en KIO (DropJob, o.a. het
Plasma-bureaublad) na het neerzetten via D-Bus

    org.kde.ark.DndExtract.extractSelectedFilesTo("/pad/naar/de/map")

aan. Zo weten we precies in welke map de roomba is neergezet – zonder
nepbestanden, menuutjes of instellingen te wijzigen.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from pathlib import Path

from PyQt6.QtCore import QMimeData, QObject, QTimer, pyqtClassInfo, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusAbstractAdaptor, QDBusConnection

log = logging.getLogger("kde-roomba")

SERVICE_MIME = "application/x-kde-ark-dndextract-service"
PATH_MIME = "application/x-kde-ark-dndextract-path"
OBJECT_PATH = "/KdeRoomba/DndExtract"


@pyqtClassInfo("D-Bus Interface", "org.kde.ark.DndExtract")
class _DndExtractAdaptor(QDBusAbstractAdaptor):
    def __init__(self, parent: "DropReceiver"):
        super().__init__(parent)
        self._receiver = parent

    @pyqtSlot(str)
    def extractSelectedFilesTo(self, destination: str) -> None:  # noqa: N802 (D-Bus-naam)
        # Dolphin wacht synchroon op dit antwoord: meteen terugkeren en het
        # echte werk pas daarna in de gebeurtenislus doen.
        self._receiver.received(destination)


class DropReceiver(QObject):
    folderDropped = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._adaptor = _DndExtractAdaptor(self)
        bus = QDBusConnection.sessionBus()
        self.ok = bus.isConnected() and bus.registerObject(OBJECT_PATH, self)
        self.service = bus.baseService() if bus.isConnected() else ""
        log.info("Slepen naar mappen: %s", f"klaar ({self.service})" if self.ok else "niet beschikbaar (geen D-Bus)")

    def received(self, destination: str) -> None:
        log.info("Neergezet in: %s", destination)
        QTimer.singleShot(0, lambda: self.folderDropped.emit(destination))

    def mime_data(self) -> QMimeData:
        md = QMimeData()
        md.setData(SERVICE_MIME, self.service.encode())
        md.setData(PATH_MIME, OBJECT_PATH.encode())
        return md


def resolve_folder(destination: str) -> tuple[Path | None, str]:
    """Controleert of we in deze map mogen stofzuigen. (map, uitleg)"""
    d = destination.strip()
    if d.startswith("file://"):
        d = urllib.parse.unquote(urllib.parse.urlparse(d).path)
    if "://" in d or not d.startswith("/"):
        return None, "ik kan alleen in mappen op deze computer stofzuigen"
    p = Path(d)
    try:
        p = p.resolve()
    except OSError:
        pass
    if not p.is_dir():
        return None, "dat is geen map"
    home = Path.home().resolve()
    if p == home or p == Path("/"):
        return None, "je hele thuismap is me te groot – kies een map erin"
    if any(part.startswith(".") for part in p.parts):
        return None, "verborgen (systeem)mappen laat ik met rust"
    try:
        p.relative_to(home)
    except ValueError:
        if not (p.parts[:2] in (("/", "run"), ("/", "media"), ("/", "mnt")) or str(p).startswith("/tmp")):
            return None, "buiten je thuismap stofzuig ik niet"
    if not os.access(p, os.W_OK):
        return None, "daar mag ik niets weggooien (geen schrijfrechten)"
    return p, "ok"
