"""Berekent de schermpositie van bureaublad-iconen in KDE Plasma 6.

Nagebouwd uit Plasma's eigen code (plasma-desktop, containments/desktop):

* ``positioner.cpp`` – posities staan in
  ``~/.config/plasma-org.kde.plasma.desktop-appletsrc``,
  ``[Containments][N][General] positions=`` als JSON per schermresolutie:
  ``{"1920x1080": [aantalStroken, perStrook, naam, strook, positie, ...]}``.
* ``FolderView.qml`` – ``itemX = (rows ? pos : strook) * cellWidth`` en
  ``itemY = (rows ? strook : pos) * cellHeight``; de celmaat wordt berekend
  uit icoongrootte, gridUnit (lettergrootte) en de beschikbare ruimte.
* ``main.xml`` – standaard: arrangement 0 (= rijen, links→rechts),
  iconSize 3 (= 64 px), labelWidth 1, textLines 2.

Iconen zonder opgeslagen positie worden gevuld zoals Plasma dat doet: in de
eerste vrije cellen, mappen eerst, dan op naam.
"""

from __future__ import annotations

import configparser
import json
import logging
import re
import urllib.parse
from pathlib import Path

from .config import Config

log = logging.getLogger("kde-roomba")

APPLETSRC = Path("~/.config/plasma-org.kde.plasma.desktop-appletsrc").expanduser()

# FolderTools.js: iconSizes[iconSize] (Kirigami.Units.iconSizes)
ICON_SIZES = [22, 32, 48, 64, 96, 128, 160, 192, 224, 256]
SMALL_ICON = 16  # Kirigami.Units.iconSizes.small
SMALL_SPACING = 4  # Kirigami.Units.smallSpacing


class _CaseConfigParser(configparser.RawConfigParser):
    def optionxform(self, optionstr: str) -> str:  # behoud hoofdletters
        return optionstr


def kconfig_unescape(value: str) -> str:
    """KConfig schrijft o.a. \\\\, \\s, \\t, \\n en \\, in waarden."""
    out, i = [], 0
    while i < len(value):
        c = value[i]
        if c == "\\" and i + 1 < len(value):
            n = value[i + 1]
            out.append({"\\": "\\", "s": " ", "t": "\t", "n": "\n", "r": "\r", ";": ";", ",": ","}.get(n, "\\" + n))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _read_folder_containment(screen_index: int = 0) -> dict[str, str]:
    """Geeft de [General]-sectie van de folder-containment van het scherm."""
    if not APPLETSRC.exists():
        return {}
    cp = _CaseConfigParser(strict=False, interpolation=None)
    try:
        cp.read(APPLETSRC, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return {}
    best: dict[str, str] = {}
    for sec in cp.sections():
        if not re.fullmatch(r"Containments\]\[(\d+)", sec):
            continue
        if cp.get(sec, "plugin", fallback="") != "org.kde.plasma.folder":
            continue
        gen_name = f"{sec}][General"
        general = dict(cp.items(gen_name)) if cp.has_section(gen_name) else {}
        try:
            screen = int(cp.get(sec, "lastScreen", fallback="0"))
        except ValueError:
            screen = 0
        if screen == screen_index:
            return general
        if not best:
            best = general
    return best


def _parse_positions(raw: str, screen_w: int, screen_h: int) -> list[str] | None:
    raw = kconfig_unescape(raw.strip())
    # Plasma zelf: readEntry("positions").replace("\\,", ",")
    raw = raw.replace("\\,", ",")
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except ValueError as exc:
            log.warning("Iconposities niet te lezen: %s", exc)
            return None
        if not isinstance(data, dict) or not data:
            return None
        key = f"{screen_w}x{screen_h}"
        if key not in data:

            def dist(k: str) -> float:
                try:
                    w, h = (int(x) for x in k.split("x"))
                    return abs(w - screen_w) + abs(h - screen_h)
                except ValueError:
                    return 1e9

            key = min(data, key=dist)
        entries = data[key]
    else:  # Plasma 5: kommagescheiden lijst
        entries = [e.strip() for e in raw.split(",")]
    if not isinstance(entries, list) or len(entries) < 2:
        return None
    return [str(e) for e in entries[2:]]


def _url_to_name(url: str) -> str:
    for prefix in ("desktop:/", "file://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
    return urllib.parse.unquote(url).rstrip("/").split("/")[-1]


def _extra(cell: int, container: int) -> int:
    """FolderView.qml: calcExtraSpacing – restruimte eerlijk over de cellen verdelen."""
    n = container // cell if cell > 0 else 0
    return (max(container - n * cell, 0) // n) if n > 0 else 0


def _int(general: dict[str, str], key: str, default: int) -> int:
    try:
        return int(general.get(key, default))
    except ValueError:
        return default


class DesktopLayout:
    def __init__(self, cfg: Config, area_x: int, area_y: int, area_w: int, area_h: int,
                 grid_unit: int = 18, screen_w: int = 0, screen_h: int = 0):
        self.cfg = cfg
        self.ax, self.ay, self.aw, self.ah = area_x, area_y, area_w, area_h
        general = _read_folder_containment()

        idx = _int(general, "iconSize", 3)
        self.icon_px = ICON_SIZES[max(0, min(idx, len(ICON_SIZES) - 1))]
        label_width = _int(general, "labelWidth", 1)
        text_lines = _int(general, "textLines", 2)

        min_w = max(self.icon_px + 2 * grid_unit + 2 * SMALL_SPACING, SMALL_ICON * (label_width * 2 + 4))
        min_h = self.icon_px + grid_unit * text_lines + SMALL_SPACING * 3
        self.cell_w = cfg.icon_cell_width or (min_w + _extra(min_w, area_w))
        self.cell_h = cfg.icon_cell_height or (min_h + _extra(min_h, area_h))

        flow = cfg.icon_flow
        if flow == "auto":
            flow = "columns" if general.get("arrangement") == "1" else "rows"  # standaard 0 = rijen
        self.flow = flow
        self.align_right = general.get("alignment") == "1"
        self.rows = max(1, area_h // self.cell_h)
        self.cols = max(1, area_w // self.cell_w)

        self.fixed: dict[str, tuple[int, int]] = {}  # naam -> (kolom, rij)
        items = _parse_positions(general.get("positions", ""), screen_w or area_w, screen_h or area_h)
        if items:
            for i in range(0, len(items) - 2, 3):
                try:
                    stripe, pos = int(items[i + 1]), int(items[i + 2])
                except ValueError:
                    continue
                col, row = (pos, stripe) if flow == "rows" else (stripe, pos)
                self.fixed[_url_to_name(items[i])] = (col, row)

    def describe(self) -> str:
        return (f"cel {self.cell_w}x{self.cell_h}, icoon {self.icon_px}px, {self.flow}"
                f"{', rechts uitgelijnd' if self.align_right else ''}, {len(self.fixed)} vaste posities")

    def cell_center(self, col: int, row: int) -> tuple[float, float]:
        x = col * self.cell_w + self.cell_w / 2
        if self.align_right:
            x = self.aw - x
        # het icoon staat bovenin de cel (met wat opvulling), het label eronder
        y = row * self.cell_h + SMALL_SPACING * 3 + self.icon_px / 2
        return self.ax + x + self.cfg.icon_offset_x, self.ay + y + self.cfg.icon_offset_y

    def positions(self, names_dirs: list[tuple[str, bool]]) -> dict[str, tuple[float, float]]:
        """Geeft het middelpunt van het icoon van elk item."""
        result: dict[str, tuple[float, float]] = {}
        taken: set[tuple[int, int]] = set()
        for name, _ in names_dirs:
            if name in self.fixed:
                c = self.fixed[name]
                taken.add(c)
                result[name] = self.cell_center(*c)

        rest = sorted((nd for nd in names_dirs if nd[0] not in result), key=lambda nd: (not nd[1], nd[0].lower()))
        idx = 0
        for name, _ in rest:
            while True:
                if self.flow == "rows":
                    c = (idx % self.cols, idx // self.cols)
                else:
                    c = (idx // self.rows, idx % self.rows)
                idx += 1
                if c not in taken:
                    break
            taken.add(c)
            result[name] = self.cell_center(*c)
        return result
