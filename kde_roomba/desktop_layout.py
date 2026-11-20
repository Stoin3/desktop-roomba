"""Schat de schermpositie van bureaublad-iconen in KDE Plasma.

Plasma bewaart handmatig geplaatste iconen in
``~/.config/plasma-org.kde.plasma.desktop-appletsrc`` onder
``[Containments][N][General] positions=...``. Plasma 6 gebruikt JSON per
resolutie, Plasma 5 een kommagescheiden lijst. Formaat (na de kop met
aantal stroken / items per strook): ``url, strook, positie-in-strook``.

Staan iconen niet in die lijst (automatische indeling), dan zetten we ze in
dezelfde volgorde als Plasma: mappen eerst, daarna alfabetisch, kolom voor
kolom vanaf linksboven.

Dit is een benadering: de roomba hoeft alleen ongeveer bij het icoon uit te
komen. Stel ``icon_cell_width``/``icon_cell_height`` bij in de config als
het niet goed uitkomt.
"""

from __future__ import annotations

import configparser
import json
import re
import urllib.parse
from pathlib import Path

from .config import Config

APPLETSRC = Path("~/.config/plasma-org.kde.plasma.desktop-appletsrc").expanduser()

# Plasma folderview iconSize-index → pixelgrootte
ICON_SIZES = [16, 22, 32, 48, 64, 128]


class _CaseConfigParser(configparser.RawConfigParser):
    def optionxform(self, optionstr: str) -> str:  # behoud hoofdletters
        return optionstr


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
        m = re.fullmatch(r"Containments\]\[(\d+)", sec)
        if not m:
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


def _parse_positions(raw: str, area_w: int, area_h: int) -> tuple[list[str], int] | None:
    raw = raw.strip()
    if not raw:
        return None
    entries: list[str] | None = None
    if raw.startswith("{"):
        try:
            data = json.loads(raw.replace("\\\\", "\\"))
        except ValueError:
            try:
                data = json.loads(raw)
            except ValueError:
                return None
        if not isinstance(data, dict) or not data:
            return None
        key = f"{area_w}x{area_h}"
        if key in data:
            entries = data[key]
        else:
            # kies de resolutie die het dichtst bij ligt
            def dist(k: str) -> float:
                try:
                    w, h = (int(x) for x in k.split("x"))
                    return abs(w - area_w) + abs(h - area_h)
                except ValueError:
                    return 1e9

            entries = data[min(data, key=dist)]
    else:
        entries = [e.strip() for e in raw.split(",")]
    if not entries or len(entries) < 2:
        return None
    try:
        per_stripe = int(entries[1])
    except ValueError:
        per_stripe = 0
    return [str(e) for e in entries[2:]], per_stripe


def _url_to_name(url: str) -> str:
    if url.startswith("desktop:/"):
        url = url[len("desktop:/") :]
    elif url.startswith("file://"):
        url = url[len("file://") :]
    return urllib.parse.unquote(url).rstrip("/").split("/")[-1]


class DesktopLayout:
    def __init__(self, cfg: Config, area_x: int, area_y: int, area_w: int, area_h: int, scale: float = 1.0):
        self.cfg = cfg
        self.ax, self.ay, self.aw, self.ah = area_x, area_y, area_w, area_h
        general = _read_folder_containment()
        try:
            icon_idx = int(general.get("iconSize", "3"))
        except ValueError:
            icon_idx = 3
        icon_px = ICON_SIZES[max(0, min(icon_idx, len(ICON_SIZES) - 1))]
        self.icon_px = icon_px
        # Benadering van Plasma's celgrootte (icoon + label + marges)
        self.cell_w = cfg.icon_cell_width or int(max(icon_px * 1.9, icon_px + 64))
        self.cell_h = cfg.icon_cell_height or int(icon_px + 52)

        flow = cfg.icon_flow
        if flow == "auto":
            # arrangement: 0 = Rows (links→rechts), 1 = Columns (boven→onder).
            # Op het bureaublad is boven→onder de standaard.
            flow = "rows" if general.get("arrangement") == "0" else "columns"
        self.flow = flow
        self.rows = max(1, (area_h - 2 * cfg.icon_margin_y) // self.cell_h)
        self.cols = max(1, (area_w - 2 * cfg.icon_margin_x) // self.cell_w)

        self.fixed: dict[str, tuple[int, int]] = {}  # naam -> (kolom, rij)
        parsed = _parse_positions(general.get("positions", ""), area_w, area_h)
        if parsed:
            items, _per_stripe = parsed
            for i in range(0, len(items) - 2, 3):
                try:
                    stripe, pos = int(items[i + 1]), int(items[i + 2])
                except ValueError:
                    continue
                col, row = (stripe, pos) if flow == "columns" else (pos, stripe)
                self.fixed[_url_to_name(items[i])] = (col, row)

    def cell_center(self, col: int, row: int) -> tuple[float, float]:
        x = self.ax + self.cfg.icon_margin_x + col * self.cell_w + self.cell_w / 2
        y = self.ay + self.cfg.icon_margin_y + row * self.cell_h + self.icon_px / 2 + 8
        return x, y

    def positions(self, names_dirs: list[tuple[str, bool]]) -> dict[str, tuple[float, float]]:
        """Geeft het (geschatte) middelpunt van het icoon van elk item."""
        result: dict[str, tuple[float, float]] = {}
        taken: set[tuple[int, int]] = set()
        for name, _ in names_dirs:
            if name in self.fixed:
                c = self.fixed[name]
                taken.add(c)
                result[name] = self.cell_center(*c)

        # Plasma: mappen eerst, dan op naam (hoofdletterongevoelig)
        rest = sorted((nd for nd in names_dirs if nd[0] not in result), key=lambda nd: (not nd[1], nd[0].lower()))
        idx = 0
        for name, _ in rest:
            while True:
                if self.flow == "columns":
                    c = (idx // self.rows, idx % self.rows)
                else:
                    c = (idx % self.cols, idx // self.cols)
                idx += 1
                if c not in taken:
                    break
            taken.add(c)
            result[name] = self.cell_center(*c)
        return result
