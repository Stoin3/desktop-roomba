"""Plaatst het roomba-venster op Wayland in de 'bottom'-laag via layer-shell-qt.

Dat is dezelfde KDE-bibliotheek waarmee Plasma zijn panelen en bureaublad
tekent; op Fedora KDE is hij al geïnstalleerd (pakket ``layer-shell-qt``).
Er wordt NIETS aan je KDE-instellingen veranderd: het venster vraagt de
compositor alleen om:

* laag ``bottom``: boven het bureaublad, onder je gewone vensters;
* aan alle schermranden verankerd → precies het vrije bureaubladgebied
  (panelen blijven vrij);
* pakt nooit zelf focus (alleen als je erop klikt), geen taakbalkknop, niet in alt-tab.

Er zijn geen Python-bindings voor layer-shell-qt, dus de paar functies die
we nodig hebben worden via ctypes aangeroepen. Lukt dat niet, dan valt het
programma terug op een gewoon venster.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os

log = logging.getLogger("kde-roomba")

# enums uit LayerShellQt/window.h
LAYER_BOTTOM = 1
LAYER_TOP = 2
ANCHOR_ALL = 1 | 2 | 4 | 8
KEYBOARD_ON_DEMAND = 2  # nodig voor popupmenu's; focus alleen na klik

_SYMS = {
    "get": "_ZN12LayerShellQt6Window3getEP7QWindow",
    "setLayer": "_ZN12LayerShellQt6Window8setLayerENS0_5LayerE",
    "setAnchors": "_ZN12LayerShellQt6Window10setAnchorsE6QFlagsINS0_6AnchorEE",
    "setExclusiveZone": "_ZN12LayerShellQt6Window16setExclusiveZoneEi",
    "setKeyboardInteractivity": "_ZN12LayerShellQt6Window24setKeyboardInteractivityENS0_21KeyboardInteractivityE",
    "setActivateOnShow": "_ZN12LayerShellQt6Window17setActivateOnShowEb",
}
# Optioneel (versie-afhankelijk): op het actieve scherm plaatsen.
_SET_SCREEN = "_ZN12LayerShellQt6Window9setScreenEP7QScreen"                       # >= 6.6
_ACTIVE_SCREEN = "_ZN12LayerShellQt6Window26setWantsToBeOnActiveScreenEb"           # >= 6.6
_SCREEN_CONFIG = "_ZN12LayerShellQt6Window22setScreenConfigurationENS0_19ScreenConfigurationE"  # oudere


def _uses_bundled_qt() -> bool:
    """PyQt6 uit pip heeft een eigen Qt; dan mag de systeem-layer-shell-qt
    (gebouwd tegen systeem-Qt) niet geladen worden."""
    if os.environ.get("KDE_ROOMBA_FORCE_LAYER_SHELL") == "1":
        return False
    import PyQt6

    return os.path.isdir(os.path.join(os.path.dirname(PyQt6.__file__), "Qt6", "lib"))


def _load_lib():
    candidates = []
    found = ctypes.util.find_library("LayerShellQtInterface")
    if found:
        candidates.append(found)
    candidates += ["libLayerShellQtInterface.so.6", "/usr/lib64/libLayerShellQtInterface.so.6"]
    for c in candidates:
        try:
            return ctypes.CDLL(c)
        except OSError:
            continue
    return None


def kde_primary_output() -> str | None:
    """Naam van KDE's hoofdscherm (prioriteit 1 in Systeeminstellingen →
    Beeldscherm). Daar staat Plasma's 'scherm 0' met de bureaublad-iconen."""
    import json
    import shutil
    import subprocess

    if not shutil.which("kscreen-doctor"):
        return None
    try:
        out = subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, timeout=4).stdout
        outputs = json.loads(out).get("outputs", [])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    enabled = [o for o in outputs if o.get("enabled", True) and o.get("connected", True)]
    with_prio = [o for o in enabled if isinstance(o.get("priority"), int) and o["priority"] > 0]
    if with_prio:
        return min(with_prio, key=lambda o: o["priority"]).get("name")
    prim = [o for o in enabled if o.get("primary")]
    return prim[0].get("name") if prim else None


def enable(widget, layer: int = LAYER_BOTTOM, screen=None) -> tuple[bool, str]:
    """Moet aangeroepen worden vóórdat het venster getoond wordt.
    Geeft (gelukt, uitleg) terug."""
    from PyQt6 import sip
    from PyQt6.QtGui import QGuiApplication

    if not QGuiApplication.platformName().startswith("wayland"):
        return False, "geen Wayland"
    if _uses_bundled_qt():
        return False, "PyQt6 komt uit pip (eigen Qt); installeer python3-pyqt6 via dnf voor layer-shell"
    lib = _load_lib()
    if lib is None:
        return False, "libLayerShellQtInterface.so.6 niet gevonden (pakket layer-shell-qt)"
    try:
        fns = {k: getattr(lib, v) for k, v in _SYMS.items()}
    except AttributeError as exc:
        return False, f"onverwachte layer-shell-qt-versie: {exc}"

    fns["get"].argtypes = [ctypes.c_void_p]
    fns["get"].restype = ctypes.c_void_p
    for k in ("setLayer", "setAnchors", "setExclusiveZone", "setKeyboardInteractivity"):
        fns[k].argtypes = [ctypes.c_void_p, ctypes.c_int]
        fns[k].restype = None
    fns["setActivateOnShow"].argtypes = [ctypes.c_void_p, ctypes.c_bool]
    fns["setActivateOnShow"].restype = None

    if screen is not None:
        widget.setScreen(screen)
    widget.winId()  # maakt het QWindow aan (nog niet zichtbaar)
    handle = widget.windowHandle()
    if handle is None:
        return False, "geen QWindow"
    win = fns["get"](sip.unwrapinstance(handle))
    if not win:
        return False, "LayerShellQt::Window::get gaf niets terug"
    fns["setLayer"](win, layer)
    fns["setAnchors"](win, ANCHOR_ALL)
    fns["setExclusiveZone"](win, 0)
    fns["setKeyboardInteractivity"](win, KEYBOARD_ON_DEMAND)
    fns["setActivateOnShow"](win, False)

    # Scherm: bij voorkeur het opgegeven scherm (KDE's hoofdscherm). Anders
    # laat de compositor kiezen (het actieve scherm) i.p.v. Qt's 'eerste'.
    where = "scherm van Qt"
    if screen is not None and hasattr(lib, _SET_SCREEN):
        f = getattr(lib, _SET_SCREEN)
        f.argtypes, f.restype = [ctypes.c_void_p, ctypes.c_void_p], None
        f(win, sip.unwrapinstance(screen))
        where = f"scherm {screen.name()}"
    elif screen is not None and not hasattr(lib, _ACTIVE_SCREEN):
        where = f"scherm {screen.name()} (via Qt)"  # oude versie: volgt QWindow::screen()
    elif hasattr(lib, _ACTIVE_SCREEN):
        f = getattr(lib, _ACTIVE_SCREEN)
        f.argtypes, f.restype = [ctypes.c_void_p, ctypes.c_bool], None
        f(win, True)
        where = "actieve scherm"
    elif hasattr(lib, _SCREEN_CONFIG):
        f = getattr(lib, _SCREEN_CONFIG)
        f.argtypes, f.restype = [ctypes.c_void_p, ctypes.c_int], None
        f(win, 1)  # ScreenFromCompositor
        where = "scherm van de compositor"
    return True, f"layer-shell (bottom-laag, {where})"
