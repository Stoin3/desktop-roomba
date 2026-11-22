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


from .folders import resolve_folder  # noqa: E402,F401 (voor bestaande aanroepen)
