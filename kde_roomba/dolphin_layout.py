"""Schat waar Dolphin de bestanden van een map tekent.

Nagebouwd uit Dolphin's broncode:

* ``DolphinItemListView::updateGridSize`` – celmaat per weergave:
  pictogrammen: breedte ``48 + textWidthIndex*64*fontFactor*e^(zoom/13)``,
  hoogte ``3*padding + icoon + regelafstand``; compact en details eigen formules.
* ``KItemListViewLayouter::doLayout`` – kolommen = (breedte - marge) /
  (cel + marge); ongebruikte breedte wordt over de kolommen verdeeld;
  rijen beginnen op ``kop + marge``.
* Standaardinstellingen (``dolphin_*modesettings.kcfg``): pictogrammen met
  voorbeelden 64 px, details/compact 16 px (voorbeelden 48 px),
  sorteren op naam met mappen eerst, verborgen bestanden niet zichtbaar.

Instellingen worden gelezen uit ``~/.config/dolphinrc`` en Dolphin's
weergave-eigenschappen. Breedte van het Plaatsen-paneel en hoogte van de
werkbalk zijn niet uit te lezen en worden geschat (instelbaar).
"""

from __future__ import annotations

import configparser
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config

PADDING = 2


def _ini(path: Path) -> configparser.RawConfigParser:
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str  # type: ignore[assignment]
    try:
        cp.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        pass
    return cp


def _get(cp: configparser.RawConfigParser, sec: str, key: str, default):
    try:
        raw = cp.get(sec, key)
    except (configparser.Error, KeyError):
        return default
    if isinstance(default, bool):
        return raw.strip().lower() in ("true", "1", "yes")
    try:
        return type(default)(raw)
    except (TypeError, ValueError):
        return default


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


@dataclass
class Metrics:
    """Lettertype- en stijlmaten (door de app met Qt bepaald)."""
    avg_char: float = 9.0
    line_spacing: int = 20
    font_height: int = 19
    grid_margin: int = 3  # QStyle::PM_SizeGripSize van de stijl (Breeze)


class DolphinLayout:
    def __init__(self, cfg: Config, folder: Path, client: tuple[float, float, float, float], metrics: Metrics):
        self.cfg = cfg
        self.folder = folder
        cx, cy, cw, ch = client
        home = Path.home()
        xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        xdg_data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
        rc = _ini(xdg_config / "dolphinrc")

        # weergave-eigenschappen (globaal of per map)
        global_props = _get(rc, "General", "GlobalViewProps", True)
        if global_props:
            props_file = xdg_data / "dolphin/view_properties/global/.directory"
        else:
            props_file = folder / ".directory"
            if not props_file.exists():
                props_file = xdg_data / "dolphin/view_properties/local" / str(folder).lstrip("/") / ".directory"
        props = _ini(props_file)
        self.mode = _get(props, "Dolphin", "ViewMode", 0)  # 0 pictogrammen, 1 details, 2 compact
        previews = _get(props, "Dolphin", "PreviewsShown", True)
        self.hidden_shown = _get(props, "Settings", "HiddenFilesShown", _get(props, "Dolphin", "HiddenFilesShown", False))
        self.folders_first = _get(props, "Dolphin", "SortFoldersFirst", True)
        self.descending = _get(props, "Dolphin", "SortOrder", 0) == 1

        group = {0: "IconsMode", 1: "DetailsMode", 2: "CompactMode"}.get(self.mode, "IconsMode")
        if previews:
            icon = _get(rc, group, "PreviewSize", 64 if self.mode == 0 else 48)
        else:
            icon = _get(rc, group, "IconSize", 32 if self.mode == 0 else 16)
        self.icon = icon
        zoom = {16: 0, 22: 1, 32: 2, 48: 3, 64: 4}.get(icon, 4 + ((icon - 64) >> 4))
        m = metrics
        self.metrics = m

        # --- venster-indeling (geschat) -------------------------------------
        panel = cfg.dolphin_panel_width
        if panel < 0:  # automatisch: Plaatsen-paneel ~ kwart van het venster
            panel = int(min(300, max(150, cw * 0.25))) if cw > 700 else 0
        toolbar = cfg.dolphin_toolbar_height if cfg.dolphin_toolbar_height >= 0 else int(m.font_height * 2 + 8)
        status = int(m.font_height + 12)
        self.view = (cx + panel + 1, cy + toolbar, max(100, cw - panel - 1 - 14), max(100, ch - toolbar - status))
        vx, vy, vw, vh = self.view

        # --- celmaat (DolphinItemListView::updateGridSize) ------------------
        self.header = 0
        self.vertical_flow = False
        if self.mode == 1:  # details
            self.item_w = vw
            self.item_h = PADDING * 2 + max(icon, m.line_spacing)
            self.margin_x = self.margin_y = 0
            self.header = m.font_height + 10
        elif self.mode == 2:  # compact
            self.item_w = PADDING * 4 + icon + m.font_height * 5
            self.item_h = PADDING * 2 + max(icon, m.line_spacing)
            self.margin_x, self.margin_y = 8, 0
            self.vertical_flow = True
        else:  # pictogrammen
            zf = math.exp(zoom / 13.0)
            ff = m.avg_char / 9.0
            tw = _get(rc, "IconsMode", "TextWidthIndex", 1)
            self.item_w = int(48 + tw * 64 * ff * zf)
            self.item_w = max(self.item_w, int(icon + PADDING * 2 * zf))
            self.item_h = PADDING * 3 + icon + m.line_spacing
            compact = _get(rc, "IconsMode", "CompactSpacing", False)
            self.margin_x = self.margin_y = PADDING * 2 if compact else m.grid_margin
            self.max_lines = _get(rc, "IconsMode", "MaximumTextLines", 3)

    def describe(self) -> str:
        mode = {0: "pictogrammen", 1: "details", 2: "compact"}.get(self.mode, "?")
        vx, vy, vw, vh = self.view
        return (f"{mode}, icoon {self.icon}px, cel {self.item_w}x{self.item_h}, "
                f"weergave op ({vx:.0f},{vy:.0f}) {vw:.0f}x{vh:.0f}")

    def visible_items(self) -> list[tuple[str, bool]]:
        try:
            entries = [(e.name, e.is_dir()) for e in os.scandir(self.folder)
                       if self.hidden_shown or not e.name.startswith(".")]
        except OSError:
            return []
        entries.sort(key=lambda nd: _natural_key(nd[0]), reverse=self.descending)
        if self.folders_first:
            entries.sort(key=lambda nd: not nd[1])
        return entries

    def _text_lines(self, name: str) -> int:
        if self.mode != 0:
            return 1
        per_line = max(4, int((self.item_w - 2 * PADDING) / max(5.0, self.metrics.avg_char)))
        return max(1, min(self.max_lines, math.ceil(len(name) / per_line)))

    def positions(self) -> dict[str, tuple[float, float]]:
        """Middelpunt van het icoon van elk zichtbaar item (globale coördinaten)."""
        items = self.visible_items()
        vx, vy, vw, vh = self.view
        out: dict[str, tuple[float, float]] = {}
        n = len(items)
        if not n:
            return out

        if self.vertical_flow:  # compact: kolommen van boven naar beneden
            rows = max(1, int((vh - self.margin_y) // (self.item_h + self.margin_y)))
            for i, (name, _) in enumerate(items):
                col, row = divmod(i, rows)
                x = vx + self.margin_x + col * (self.item_w + self.margin_x) + PADDING * 2 + self.icon / 2
                y = vy + row * self.item_h + self.item_h / 2
                out[name] = (x, y)
            return out

        if self.mode == 1:  # details: één kolom, icoon links
            for i, (name, _) in enumerate(items):
                out[name] = (vx + 20 + self.icon / 2, vy + self.header + i * self.item_h + self.item_h / 2)
            return out

        # pictogrammen (KItemListViewLayouter::doLayout)
        col_w = self.item_w + self.margin_x
        width_for_cols = max(vw - self.margin_x, col_w)
        cols = max(1, int(width_for_cols // col_w))
        x_inc = self.margin_x
        if n > cols and col_w >= 32:
            unused = width_for_cols - cols * col_w
            inc = unused / (cols + 1)
            col_w += inc
            x_inc += inc
        y = self.header + self.margin_y
        for start in range(0, n, cols):
            row_items = items[start:start + cols]
            row_h = max(self.item_h + (self._text_lines(nm) - 1) * self.metrics.line_spacing for nm, _ in row_items)
            for c, (name, _) in enumerate(row_items):
                x = vx + x_inc + c * col_w + self.item_w / 2
                out[name] = (x, vy + y + PADDING * 2 + self.icon / 2)
            y += row_h + self.margin_y
        return out
