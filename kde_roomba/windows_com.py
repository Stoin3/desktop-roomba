"""COM-deel van de Windows-koppeling (Shell-API en UI Automation).

Apart gezet zodat comtypes en de gegenereerde typelib-modules pas geladen worden
als de roomba echt iets met Verkenner/het bureaublad doet.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import POINTER, byref, c_int, c_uint, c_void_p, wintypes

from .windows_shell import ViewInfo, client_origin, client_rect_screen, desktop_icon_host, ole32, user32

log = logging.getLogger("kde-roomba")

import comtypes
import comtypes.automation
import comtypes.client
import comtypes.client.dynamic
from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

# --------------------------------------------------------------------------
# COM-interfaces (methodevolgorde volgens shobjidl_core.h)
# --------------------------------------------------------------------------

SID_STopLevelBrowser = GUID("{4C96BE40-915C-11CF-99D3-00AA004AE837}")


class IServiceProvider(IUnknown):
    _iid_ = GUID("{6D5140C1-7436-11CE-8034-00AA006009FA}")
    _methods_ = [
        COMMETHOD([], HRESULT, "QueryService",
                  (["in"], POINTER(GUID), "guidService"),
                  (["in"], POINTER(GUID), "riid"),
                  (["out"], POINTER(POINTER(IUnknown)), "ppv")),
    ]


class IShellItem(IUnknown):
    _iid_ = GUID("{43826D1E-E718-42EE-BC55-A1E261C37BFE}")
    _methods_ = [
        COMMETHOD([], HRESULT, "BindToHandler", (["in"], c_void_p), (["in"], POINTER(GUID)),
                  (["in"], POINTER(GUID)), (["out"], POINTER(c_void_p))),
        COMMETHOD([], HRESULT, "GetParent", (["out"], POINTER(c_void_p))),
        COMMETHOD([], HRESULT, "GetDisplayName", (["in"], c_uint, "sigdn"), (["out"], POINTER(c_void_p), "name")),
        COMMETHOD([], HRESULT, "GetAttributes", (["in"], c_uint), (["out"], POINTER(c_uint))),
        COMMETHOD([], HRESULT, "Compare", (["in"], c_void_p), (["in"], c_uint), (["out"], POINTER(c_int))),
    ]


def _placeholder(name: str):
    return COMMETHOD([], HRESULT, name)


class IShellView(IUnknown):
    _iid_ = GUID("{000214E3-0000-0000-C000-000000000046}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetWindow", (["out"], POINTER(wintypes.HWND), "hwnd")),
        _placeholder("ContextSensitiveHelp"),
        _placeholder("TranslateAccelerator"),
        _placeholder("EnableModeless"),
        _placeholder("UIActivate"),
        _placeholder("Refresh"),
        _placeholder("CreateViewWindow"),
        _placeholder("DestroyViewWindow"),
        _placeholder("GetCurrentInfo"),
        _placeholder("AddPropertySheetPages"),
        _placeholder("SaveViewState"),
        _placeholder("SelectItem"),
        _placeholder("GetItemObject"),
    ]


class IShellBrowser(IUnknown):
    _iid_ = GUID("{000214E2-0000-0000-C000-000000000046}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetWindow", (["out"], POINTER(wintypes.HWND), "hwnd")),
        _placeholder("ContextSensitiveHelp"),
        _placeholder("InsertMenusSB"),
        _placeholder("SetMenuSB"),
        _placeholder("RemoveMenusSB"),
        _placeholder("SetStatusTextSB"),
        _placeholder("EnableModelessSB"),
        _placeholder("TranslateAcceleratorSB"),
        _placeholder("BrowseObject"),
        _placeholder("GetViewStateStream"),
        _placeholder("GetControlWindow"),
        _placeholder("SendControlMsg"),
        COMMETHOD([], HRESULT, "QueryActiveShellView", (["out"], POINTER(POINTER(IShellView)), "view")),
        _placeholder("OnViewWindowActive"),
        _placeholder("SetToolbarItems"),
    ]


class IFolderView(IUnknown):
    _iid_ = GUID("{CDE725B0-CCC9-4519-917E-325D72FAB4CE}")
    _methods_ = [
        COMMETHOD([], HRESULT, "GetCurrentViewMode", (["out"], POINTER(c_uint), "mode")),
        _placeholder("SetCurrentViewMode"),
        _placeholder("GetFolder"),
        COMMETHOD([], HRESULT, "Item", (["in"], c_int, "index"), (["out"], POINTER(c_void_p), "pidl")),
        COMMETHOD([], HRESULT, "ItemCount", (["in"], c_uint, "flags"), (["out"], POINTER(c_int), "count")),
        _placeholder("Items"),
        _placeholder("GetSelectionMarkedItem"),
        _placeholder("GetFocusedItem"),
        COMMETHOD([], HRESULT, "GetItemPosition", (["in"], c_void_p, "pidl"), (["out"], POINTER(wintypes.POINT), "pt")),
        COMMETHOD([], HRESULT, "GetSpacing", (["out"], POINTER(wintypes.POINT), "pt")),
        _placeholder("GetDefaultSpacing"),
        _placeholder("GetAutoArrange"),
        _placeholder("SelectItem"),
        _placeholder("SelectAndPositionItems"),
    ]


class IFolderView2(IFolderView):
    _iid_ = GUID("{1AF3A467-214F-4298-908E-06B03E0B39F9}")
    _methods_ = [
        _placeholder("SetGroupBy"),
        _placeholder("GetGroupBy"),
        _placeholder("SetViewProperty"),
        _placeholder("GetViewProperty"),
        _placeholder("SetTileViewProperties"),
        _placeholder("SetExtendedTileViewProperties"),
        _placeholder("SetText"),
        _placeholder("SetCurrentFolderFlags"),
        _placeholder("GetCurrentFolderFlags"),
        _placeholder("GetSortColumnCount"),
        _placeholder("SetSortColumns"),
        _placeholder("GetSortColumns"),
        COMMETHOD([], HRESULT, "GetItem", (["in"], c_int, "index"), (["in"], POINTER(GUID), "riid"),
                  (["out"], POINTER(POINTER(IShellItem)), "item")),
        _placeholder("GetVisibleItem"),
        _placeholder("GetSelectedItem"),
        _placeholder("GetSelection"),
        _placeholder("GetSelectionState"),
        _placeholder("InvokeVerbOnSelection"),
        _placeholder("SetViewModeAndIconSize"),
        COMMETHOD([], HRESULT, "GetViewModeAndIconSize", (["out"], POINTER(c_int), "mode"),
                  (["out"], POINTER(c_int), "size")),
    ]


SVGIO_ALLVIEW = 2
SIGDN_PARENTRELATIVEPARSING = 0x80018001
SWC_DESKTOP = 8
SWFO_NEEDDISPATCH = 1
FVM_ICON, FVM_SMALLICON, FVM_LIST, FVM_DETAILS, FVM_THUMBNAIL, FVM_TILE, FVM_THUMBSTRIP, FVM_CONTENT = range(1, 9)

_coinit_done = False


def _coinit() -> None:
    global _coinit_done
    if not _coinit_done:
        try:
            comtypes.CoInitialize()
        except OSError:
            pass  # al geïnitialiseerd (bijv. door Qt)
        _coinit_done = True


# --------------------------------------------------------------------------
# Win32-helpers
# --------------------------------------------------------------------------


def _folder_view_from_dispatch(disp) -> tuple[IShellBrowser, IFolderView2] | None:
    sp = disp.QueryInterface(IServiceProvider)
    unk = sp.QueryService(byref(SID_STopLevelBrowser), byref(IShellBrowser._iid_))
    browser = unk.QueryInterface(IShellBrowser)
    view = browser.QueryActiveShellView()
    return browser, view.QueryInterface(IFolderView2)


SIGDN_NORMALDISPLAY = 0
_ICON_MODES = (FVM_ICON, FVM_THUMBNAIL, FVM_THUMBSTRIP)


def _item_names(fv: IFolderView2) -> list[tuple[str, str]]:
    """[(bestandsnaam, weergavenaam)] in de volgorde van de weergave."""
    out = []
    for i in range(fv.ItemCount(SVGIO_ALLVIEW)):
        try:
            item = fv.GetItem(i, byref(IShellItem._iid_))
            names = []
            for sigdn in (SIGDN_PARENTRELATIVEPARSING, SIGDN_NORMALDISPLAY):
                ptr = item.GetDisplayName(sigdn)
                names.append(ctypes.wstring_at(ptr))
                ole32.CoTaskMemFree(c_void_p(ptr))
            out.append((names[0].rsplit("\\", 1)[-1], names[1]))
        except (comtypes.COMError, OSError, ValueError) as exc:
            log.debug("Item %d: %s", i, exc)
            out.append(("", ""))
    return out




def _uia_rects(view_hwnd: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    """UI Automation: (weergavenaam, rechthoek op het scherm) van elk zichtbaar item.
    Werkt in álle weergaven (details, lijst, tegels, pictogrammen)."""
    # UI Automation alleen tijdens de vraag gebruiken en daarna loslaten: een
    # levend UIA-object laat Windows op de achtergrond doorwerken (CPU in rust).
    UIA = comtypes.client.GetModule("UIAutomationCore.dll")
    uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
    try:
        root = uia.ElementFromHandle(wintypes.HWND(view_hwnd))
        cond = uia.CreatePropertyCondition(30003, 50007)  # ControlType == ListItem
        found = root.FindAll(4, cond)  # TreeScope_Descendants
        out = []
        for k in range(found.Length):
            el = found.GetElement(k)
            r = el.CurrentBoundingRectangle
            if r.right - r.left > 0 and r.bottom - r.top > 0 and not el.CurrentIsOffscreen:
                out.append((str(el.CurrentName), (r.left, r.top, r.right, r.bottom)))
            del el
        del found, cond, root
        return out
    finally:
        del uia


def _read_view(folder: str, browser: IShellBrowser, fv: IFolderView2, top_hwnd: int | None = None) -> ViewInfo:
    shell_view = fv.QueryInterface(IShellView)
    view_hwnd = int(shell_view.GetWindow() or 0)
    top = top_hwnd or int(browser.GetWindow() or 0)
    if not top_hwnd and top:
        # IShellBrowser::GetWindow kan een binnenvenster geven: neem het hoofdvenster
        top = int(user32.GetAncestor(wintypes.HWND(top), 2) or top)  # GA_ROOT
    ox, oy = client_origin(view_hwnd)
    try:
        mode, icon = fv.GetViewModeAndIconSize()
    except comtypes.COMError:
        mode, icon = fv.GetCurrentViewMode(), 48
    try:
        sp = fv.GetSpacing()
        spacing = (sp.x, sp.y)
    except comtypes.COMError:
        spacing = (icon + 40, icon + 40)
    names = _item_names(fv)
    items: dict[str, tuple[float, float]] = {}

    # 1. pictogramweergaven: IFolderView::GetItemPosition (exact, ook buiten beeld)
    if mode in _ICON_MODES:
        for i, (fname, _disp) in enumerate(names):
            if not fname:
                continue
            try:
                pidl = fv.Item(i)
                try:
                    pt = fv.GetItemPosition(pidl)
                finally:
                    ole32.CoTaskMemFree(c_void_p(pidl))
            except (comtypes.COMError, OSError, ValueError) as exc:
                log.debug("GetItemPosition %s: %s", fname, exc)
                continue
            items[fname] = (ox + pt.x + spacing[0] / 2, oy + pt.y + icon / 2 + 4)

    # 2. andere weergaven (details/lijst/tegels) of als 1 niets gaf: UI Automation
    if len(items) < len([n for n in names if n[0]]):
        try:
            rects = _uia_rects(view_hwnd)
        except Exception as exc:  # noqa: BLE001
            log.warning("UI Automation niet beschikbaar: %s", exc)
            rects = []
        by_display: dict[str, list[str]] = {}
        for fname, disp in names:
            if fname and fname not in items:
                by_display.setdefault(disp, []).append(fname)
                by_display.setdefault(fname, []).append(fname)
        for disp, (left, top_, right, bottom) in rects:
            cands = [c for c in by_display.get(disp, []) if c not in items]
            if not cands:
                continue
            fname = cands[0]
            if mode in _ICON_MODES:
                cx, cy = (left + right) / 2, top_ + icon / 2 + 4
            else:  # rij: icoon links
                cx, cy = left + 6 + icon / 2, (top_ + bottom) / 2
            items[fname] = (cx, cy)
    return ViewInfo(folder, top, view_hwnd, client_rect_screen(view_hwnd), int(mode), int(icon), spacing, items)


def _shell_windows():
    _coinit()
    shdocvw = comtypes.client.GetModule("shdocvw.dll")
    return comtypes.client.CreateObject(shdocvw.ShellWindows, interface=shdocvw.IShellWindows)


def desktop_view(desktop_folder: str) -> ViewInfo | None:
    """Exacte posities van de bureaubladiconen."""
    try:
        sw = _shell_windows()
        loc = comtypes.automation.VARIANT(0)  # CSIDL_DESKTOP
        empty = comtypes.automation.VARIANT()
        res = sw.FindWindowSW(loc, empty, SWC_DESKTOP, SWFO_NEEDDISPATCH)
        disp = res[-1] if isinstance(res, tuple) else res
        browser, fv = _folder_view_from_dispatch(disp)
        return _read_view(desktop_folder, browser, fv, desktop_icon_host())
    except Exception as exc:  # noqa: BLE001
        log.warning("Bureaubladiconen niet uit te lezen: %s", exc)
        return None


def explorer_views() -> list[ViewInfo]:
    """Alle open Verkenner-vensters (alleen het zichtbare tabblad per venster)."""
    out: list[ViewInfo] = []
    try:
        sw = _shell_windows()
        for i in range(sw.Count):
            try:
                disp = sw.Item(comtypes.automation.VARIANT(i))
                if disp is None:
                    continue
                dyn = comtypes.client.dynamic.Dispatch(disp)
                folder = str(dyn.Document.Folder.Self.Path)
                browser, fv = _folder_view_from_dispatch(disp)
                info = _read_view(folder, browser, fv)
                if user32.IsWindowVisible(wintypes.HWND(info.view_hwnd)):
                    out.append(info)
            except Exception as exc:  # noqa: BLE001 – bv. een Internet-Explorer- of speciaal venster
                log.info("Shell-venster %d overgeslagen: %s", i, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("Verkenner-vensters niet uit te lezen: %s", exc)
    return out
