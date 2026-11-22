"""Windows-koppeling: Shell (COM) en Win32 voor de roomba.

Windows geeft meer toegang dan Wayland:

* **Exacte iconposities** op het bureaublad én in Verkenner-vensters via de
  officiële Shell-API: ``IShellWindows`` → ``IServiceProvider`` →
  ``IShellBrowser`` → ``IShellView`` → ``IFolderView(2)::GetItemPosition``.
* **Welke map** een Verkenner-venster toont (``Document.Folder.Self.Path``)
  en waar dat venster staat (``GetWindowRect``).
* **Overlay**: het roomba-venster kan bovenop alles (HWND_TOPMOST) of net
  boven de bureaubladiconen liggen; klikken vallen erdoorheen behalve op de
  roomba zelf.

Alle coördinaten van Windows zijn fysieke pixels (de app is per-monitor
DPI-bewust); ``to_logical`` rekent om naar Qt-coördinaten.

Deze module wordt alleen op Windows geïmporteerd.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import byref, c_int, c_uint, wintypes
from dataclasses import dataclass

log = logging.getLogger("kde-roomba")

user32 = ctypes.windll.user32
ole32 = ctypes.windll.ole32
dwmapi = ctypes.windll.dwmapi

# COM (comtypes, UI Automation) wordt pas geladen als het nodig is: zie
# windows_com.py. In rust scheelt dat geheugen en opstarttijd.

def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256)
    return buf.value


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(hwnd), byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def client_origin(hwnd: int) -> tuple[int, int]:
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(wintypes.HWND(hwnd), byref(pt))
    return pt.x, pt.y


def client_rect_screen(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetClientRect(wintypes.HWND(hwnd), byref(r))
    x, y = client_origin(hwnd)
    return x, y, r.right - r.left, r.bottom - r.top


def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(byref(pt))
    return pt.x, pt.y


def is_cloaked(hwnd: int) -> bool:
    cloaked = c_int(0)
    try:
        dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 14, byref(cloaked), ctypes.sizeof(cloaked))  # DWMWA_CLOAKED
    except OSError:
        return False
    return cloaked.value != 0


def toplevel_at(x: int, y: int, skip: set[int]) -> int | None:
    """Bovenste zichtbare venster op (x, y), ons eigen venster overgeslagen."""
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        h = int(hwnd or 0)
        if h in skip or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd) or is_cloaked(h):
            return True
        left, top, w, hgt = window_rect(h)
        if w > 0 and hgt > 0 and left <= x < left + w and top <= y < top + hgt:
            found.append(h)
            return False
        return True

    user32.EnumWindows(cb, 0)  # z-volgorde: van boven naar beneden
    return found[0] if found else None


_host_cache: int | None = None


def desktop_icon_host() -> int | None:
    """Het venster met de bureaubladiconen (gecachet; alleen opnieuw zoeken als
    het verdwenen is, bijv. na een herstart van Verkenner)."""
    global _host_cache
    h = _host_cache
    if h and user32.IsWindow(wintypes.HWND(h)) and user32.FindWindowExW(h, None, "SHELLDLL_DefView", None):
        return h
    _host_cache = _find_desktop_icon_host()
    return _host_cache


def _find_desktop_icon_host() -> int | None:
    """Het venster dat de bureaubladiconen bevat (Progman of een WorkerW)."""
    progman = user32.FindWindowW("Progman", None)
    if progman and user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None):
        return int(progman)
    host: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            host.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(cb, 0)
    return host[0] if host else (int(progman) if progman else None)


def is_desktop_window(hwnd: int) -> bool:
    return _class_name(hwnd) in ("Progman", "WorkerW") or hwnd == desktop_icon_host()


HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_NOOWNERZORDER = 0x1, 0x2, 0x10, 0x200
GW_HWNDPREV = 3
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, c_int, c_int, c_int, c_int, c_uint]
user32.GetWindow.restype = wintypes.HWND
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, c_uint]
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]


def set_topmost(hwnd: int, on: bool) -> None:
    flags = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
    user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_TOPMOST if on else HWND_NOTOPMOST), 0, 0, 0, 0, flags)


def place_on_desktop(hwnd: int) -> None:
    """Net boven de bureaubladiconen, onder alle gewone vensters.
    (HWND_BOTTOM zou ons ónder het bureaublad leggen: onzichtbaar.)"""
    flags = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
    host = desktop_icon_host()
    topmost = bool(user32.GetWindowLongW(wintypes.HWND(hwnd), -20) & 0x8)  # GWL_EXSTYLE, WS_EX_TOPMOST
    above = user32.GetWindow(wintypes.HWND(host), GW_HWNDPREV) if host else None
    if not topmost and above and int(above) == hwnd:
        return  # ligt al goed: niets doen (elke SetWindowPos laat Windows opnieuw samenstellen)
    if topmost:
        user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_NOTOPMOST), 0, 0, 0, 0, flags)
    if not host:
        return
    above = user32.GetWindow(wintypes.HWND(host), GW_HWNDPREV)
    if above and int(above) == hwnd:
        return
    # 'insert after' X = direct ónder X; X = het venster boven de iconenhost
    insert_after = above if above else wintypes.HWND(0)
    user32.SetWindowPos(wintypes.HWND(hwnd), insert_after, 0, 0, 0, 0, flags)


# --------------------------------------------------------------------------
# Mapweergaven (bureaublad en Verkenner)
# --------------------------------------------------------------------------

@dataclass
class ViewInfo:
    folder: str               # pad van de map
    top_hwnd: int             # hoofdvenster (Verkenner) of iconenhost (bureaublad)
    view_hwnd: int            # SHELLDLL_DefView
    view_rect: tuple[int, int, int, int]  # fysieke schermpixels
    mode: int
    icon: int                 # icoongrootte (fysieke px)
    spacing: tuple[int, int]
    items: dict[str, tuple[int, int]]     # naam → middelpunt icoon (fysieke schermpixels)


def desktop_view(desktop_folder: str) -> "ViewInfo | None":
    """Exacte posities van de bureaubladiconen (laadt COM bij eerste gebruik)."""
    from . import windows_com

    return windows_com.desktop_view(desktop_folder)


def explorer_views() -> "list[ViewInfo]":
    """Alle open Verkenner-vensters (laadt COM bij eerste gebruik)."""
    from . import windows_com

    return windows_com.explorer_views()


def folder_at(x: int, y: int, skip: set[int], desktop_folder: str) -> tuple[str, ViewInfo | None] | None:
    """Welke map ligt er op schermpunt (x, y)? (pad, weergave) of None."""
    top = toplevel_at(x, y, skip)
    if top is None or is_desktop_window(top):
        return desktop_folder, None
    root = int(user32.GetAncestor(wintypes.HWND(top), 2) or top)  # GA_ROOT
    for v in explorer_views():
        if v.top_hwnd in (top, root):
            return v.folder, v
    return None


def refresh_view(view: ViewInfo) -> ViewInfo | None:
    """Verse posities voor dezelfde weergave (bestanden schuiven op na verwijderen)."""
    for v in explorer_views():
        if v.view_hwnd == view.view_hwnd or (v.top_hwnd == view.top_hwnd and v.folder == view.folder):
            return v
    return None


def main() -> int:
    """Diagnose: wat ziet de roomba?  python -m kde_roomba.windows_shell"""
    import sys

    logging.basicConfig(level=logging.DEBUG if "-v" in sys.argv else logging.INFO, format="%(levelname)s %(message)s")

    sys.path.insert(0, ".")
    from kde_roomba.brain import desktop_dir

    desk = str(desktop_dir())
    print(f"Bureaubladmap: {desk}")
    print(f"Iconenhost: {desktop_icon_host()!r}")
    v = desktop_view(desk)
    if v is None:
        print("Bureaublad: NIET uit te lezen")
    else:
        print(f"Bureaublad: weergave {v.mode}, icoon {v.icon}px, afstand {v.spacing}, {len(v.items)} iconen")
        for n, (x, y) in sorted(v.items.items()):
            print(f"   {n:40s} ({x:.0f}, {y:.0f})")
    views = explorer_views()
    print(f"Verkenner-vensters: {len(views)}")
    for v in views:
        print(f" - {v.folder}  venster {v.top_hwnd:#x}  weergave {v.view_rect}  modus {v.mode}  icoon {v.icon}px")
        for n, (x, y) in sorted(v.items.items())[:20]:
            print(f"     {n:38s} ({x:.0f}, {y:.0f})")
    return 0 if v is not None or views else 1


if __name__ == "__main__":
    raise SystemExit(main())
