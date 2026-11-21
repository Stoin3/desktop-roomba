"""Outfits / thema's voor de roomba (van bovenaf getekend).

Elk outfit heeft een kleurenpalet en optioneel accessoires: oogjes, oortjes,
een hoorn, vleugeltjes, stippen of strepen. De voorkant van de roomba is +x.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient


def _c(hex_: str, a: int = 255) -> QColor:
    col = QColor(hex_)
    col.setAlpha(a)
    return col


@dataclass(frozen=True)
class Outfit:
    key: str
    name: str
    group: str  # "normaal" of "cute"
    body: tuple[str, str, str]          # radiaal verloop licht → donker
    edge: str                           # rand
    bumper: tuple[str, str]
    plate: tuple[str, str, str]
    button: tuple[str, str]
    text: str
    bin_lines: str = "#5c6068"
    pattern: str = ""                   # "", "stripes", "dots", "spots", "rainbow"
    pattern_color: str = "#000000"
    extras: tuple[str, ...] = field(default_factory=tuple)  # eyes, ears_cat, ears_round, horn, wings, whiskers, frog_eyes, antennae, blush
    ear_color: str = "#000000"
    ear_inner: str = "#ff9fb2"


OUTFITS: dict[str, Outfit] = {o.key: o for o in [
    # --- normaal ---------------------------------------------------------
    Outfit("klassiek", "Klassiek grafiet", "normaal",
           ("#4a4e55", "#2a2c31", "#141518"), "#0b0b0d", ("#1d1e22", "#33363c"),
           ("#5b6068", "#2f3238", "#202226"), ("#6a6f78", "#2a2d33"), "#d7dae0"),
    Outfit("wit", "Wit & zilver", "normaal",
           ("#ffffff", "#e6e8eb", "#b9bec5"), "#8e949b", ("#c9cdd2", "#eef0f2"),
           ("#ffffff", "#dfe3e8", "#c4c9cf"), ("#ffffff", "#c9ced4"), "#5b626b", bin_lines="#9aa1a8"),
    Outfit("zwart", "Mat zwart", "normaal",
           ("#2b2b2e", "#171719", "#0a0a0b"), "#000000", ("#0e0e10", "#1f1f22"),
           ("#262629", "#161618", "#0e0e10"), ("#3a3a3e", "#141416"), "#9a9aa2", bin_lines="#3a3a3e"),
    Outfit("rood", "Sportief rood", "normaal",
           ("#ff6b5e", "#d62f22", "#7a130c"), "#4a0905", ("#8f1a12", "#c4291e"),
           ("#3a3d42", "#25272b", "#18191c"), ("#62666e", "#23252a"), "#ffd9d4", bin_lines="#ff9a8f"),
    Outfit("blauw", "Oceaanblauw", "normaal",
           ("#6cc4ff", "#1f7fd1", "#0b3a66"), "#062541", ("#0f4f87", "#1d6fb8"),
           ("#e9f4ff", "#bcd9f2", "#8fb8de"), ("#ffffff", "#9cc3e6"), "#0b3a66", bin_lines="#8fc8ff"),
    # --- cute ------------------------------------------------------------
    Outfit("kat", "Poes 🐱", "cute",
           ("#ffbf7a", "#f08c2e", "#a85412"), "#6b3205", ("#d9741f", "#f6a14f"),
           ("#fff1e0", "#ffd9b0", "#f3b77a"), ("#fff7ee", "#f3c89a"), "#a85412", bin_lines="#ffd2a1",
           pattern="stripes", pattern_color="#b85a10", extras=("ears_cat", "eyes", "whiskers", "blush"),
           ear_color="#f08c2e", ear_inner="#ffb3c1"),
    Outfit("panda", "Panda 🐼", "cute",
           ("#ffffff", "#eef0f2", "#c9ced4"), "#2a2a2a", ("#1c1c1e", "#3a3a3e"),
           ("#ffffff", "#f1f2f4", "#d9dce0"), ("#2b2b2e", "#111113"), "#ffffff", bin_lines="#9aa1a8",
           extras=("ears_round", "panda_eyes", "blush"), ear_color="#1c1c1e", ear_inner="#3a3a3e"),
    Outfit("kikker", "Kikker 🐸", "cute",
           ("#a6f07a", "#5cc23a", "#2c7a17"), "#1a4d0c", ("#3f9a24", "#6fd14a"),
           ("#d9ffc4", "#b5f08f", "#85d65f"), ("#e8ffd9", "#9be070"), "#2c7a17", bin_lines="#c4ffa6",
           pattern="spots", pattern_color="#3f9a24", extras=("frog_eyes", "blush")),
    Outfit("eenhoorn", "Eenhoorn 🦄", "cute",
           ("#fff0fb", "#f6c8ef", "#d79ad8"), "#a06aa8", ("#e7b3ea", "#f9dcf6"),
           ("#ffffff", "#f7e6ff", "#e3c8f5"), ("#ffffff", "#e9cdf7"), "#a06aa8", bin_lines="#ffffff",
           pattern="rainbow", extras=("horn", "eyes", "blush"), ear_color="#f6c8ef", ear_inner="#ffd6f1"),
    Outfit("bij", "Bijtje 🐝", "cute",
           ("#ffe36b", "#ffc81f", "#c28a00"), "#5a3d00", ("#2a2418", "#4a3f26"),
           ("#fff6c4", "#ffe680", "#f5c938"), ("#fffbe0", "#f2d35a"), "#6b4a00", bin_lines="#2a2418",
           pattern="stripes", pattern_color="#2a2418", extras=("wings", "antennae", "eyes")),
    Outfit("lieveheersbeestje", "Lieveheersbeestje 🐞", "cute",
           ("#ff5a4e", "#e0281b", "#8f120a"), "#3d0603", ("#141414", "#2a2a2a"),
           ("#ff6e63", "#e3372a", "#b81d12"), ("#1c1c1c", "#000000"), "#ffffff", bin_lines="#1c1c1c",
           pattern="dots", pattern_color="#111111", extras=("antennae", "eyes")),
    Outfit("spook", "Spookje 👻", "cute",
           ("#ffffff", "#eef1f8", "#c8cede"), "#9aa3ba", ("#e3e7f2", "#ffffff"),
           ("#ffffff", "#f5f7fc", "#e1e6f2"), ("#ffffff", "#dfe4f0"), "#7c86a0", bin_lines="#c8cede",
           extras=("eyes", "blush", "ghost_mouth")),
]}

DEFAULT = "klassiek"


def get(key: str) -> Outfit:
    return OUTFITS.get(key, OUTFITS[DEFAULT])


# --------------------------------------------------------------------------
# Accessoires
# --------------------------------------------------------------------------

def _circle_path(rad: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(0, 0), rad, rad)
    return path


def draw_under(p: QPainter, r: float, o: Outfit, t: float, moving: float) -> None:
    """Onder de behuizing (steekt uit): vleugeltjes."""
    if "wings" in o.extras:
        flap = 1.0 + 0.18 * math.sin(t * 40) * moving + 0.05 * math.sin(t * 3)
        for side in (-1, 1):
            p.save()
            p.translate(-r * 0.15, side * r * 0.75)
            p.rotate(side * 25)
            p.scale(flap, 1)
            g = QRadialGradient(QPointF(0, 0), r * 0.6)
            g.setColorAt(0, _c("#ffffff", 200))
            g.setColorAt(1, _c("#cfe9ff", 120))
            p.setBrush(QBrush(g))
            p.setPen(QPen(_c("#8fb8de", 180), 1))
            p.drawEllipse(QPointF(-r * 0.1, side * r * 0.25), r * 0.45, r * 0.3)
            p.restore()


def draw_pattern(p: QPainter, r: float, o: Outfit) -> None:
    """Op de behuizing, onder bumper/bovenplaat (geknipt op de cirkel)."""
    if not o.pattern:
        return
    p.save()
    p.setClipPath(_circle_path(r * 0.99))
    p.setPen(Qt.PenStyle.NoPen)
    if o.pattern == "stripes":
        p.setBrush(_c(o.pattern_color, 210))
        for x in (-0.8, -0.4, 0.0, 0.4):
            path = QPainterPath()
            path.addRoundedRect(QRectF(x * r, -r, r * 0.16, 2 * r), r * 0.05, r * 0.05)
            p.drawPath(path)
    elif o.pattern == "dots":
        p.setBrush(_c(o.pattern_color))
        for ang, rad, size in ((150, 0.82, 0.11), (210, 0.82, 0.11), (110, 0.85, 0.09), (250, 0.85, 0.09),
                               (180, 0.84, 0.1), (75, 0.86, 0.07), (285, 0.86, 0.07)):
            a = math.radians(ang)
            p.drawEllipse(QPointF(math.cos(a) * rad * r, math.sin(a) * rad * r), size * r, size * r)
        p.setPen(QPen(_c(o.pattern_color), r * 0.05))
        p.drawLine(QPointF(-r, 0), QPointF(-r * 0.68, 0))
    elif o.pattern == "spots":
        p.setBrush(_c(o.pattern_color, 200))
        for ang, size in ((140, 0.08), (200, 0.1), (240, 0.07), (100, 0.06), (170, 0.06)):
            a = math.radians(ang)
            p.drawEllipse(QPointF(math.cos(a) * 0.83 * r, math.sin(a) * 0.83 * r), size * r, size * r * 0.8)
    elif o.pattern == "rainbow":
        cols = ["#ff8fa3", "#ffc38f", "#fff08f", "#a8f0a0", "#8fd3ff", "#c3a8ff"]
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, col in enumerate(cols):
            pen = QPen(_c(col, 230), r * 0.055)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            rad = r * (0.95 - i * 0.045)
            p.drawArc(QRectF(-rad, -rad, 2 * rad, 2 * rad), 120 * 16, 120 * 16)
    p.restore()


def _blink(t: float) -> float:
    """1 = open, 0 = dicht; af en toe knipperen."""
    ph = (t % 4.3) / 4.3
    return 0.1 if 0.0 <= ph < 0.035 else 1.0


def _eye(p: QPainter, x: float, y: float, s: float, t: float, happy: bool, white: bool = True) -> None:
    if happy:  # ^ ^
        pen = QPen(_c("#2a1a12"), s * 0.35)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(x - s * 0.7, y - s * 0.7, s * 1.4, s * 1.4), 0, 180 * 16)  # (rotatie volgt rijrichting)
        return
    open_ = _blink(t)
    p.setPen(Qt.PenStyle.NoPen)
    if white:
        p.setBrush(_c("#ffffff"))
        p.drawEllipse(QPointF(x, y), s, s * open_)
    p.setBrush(_c("#1b1410"))
    p.drawEllipse(QPointF(x + s * 0.25, y), s * 0.62, s * 0.62 * open_)
    if open_ > 0.5:
        p.setBrush(_c("#ffffff", 230))
        p.drawEllipse(QPointF(x + s * 0.42, y - s * 0.22), s * 0.2, s * 0.2)


def draw_face(p: QPainter, r: float, o: Outfit, t: float, state: str) -> None:
    """Bovenop: oortjes, ogen, hoorn, snorharen, voelsprieten."""
    ex = o.extras
    happy = state in ("happy", "charging")
    if "ears_cat" in ex or "ears_round" in ex:
        for side in (-1, 1):
            a = math.radians(side * 48)
            cx, cy = math.cos(a) * r * 0.86, math.sin(a) * r * 0.86
            p.save()
            p.translate(cx, cy)
            p.rotate(math.degrees(a))
            if "ears_cat" in ex:
                tri = QPainterPath()
                tri.moveTo(-r * 0.05, -r * 0.2)
                tri.lineTo(r * 0.32, 0)
                tri.lineTo(-r * 0.05, r * 0.2)
                tri.closeSubpath()
                p.setPen(QPen(_c(o.edge), 1.2))
                p.setBrush(_c(o.ear_color))
                p.drawPath(tri)
                inner = QPainterPath()
                inner.moveTo(0, -r * 0.1)
                inner.lineTo(r * 0.2, 0)
                inner.lineTo(0, r * 0.1)
                inner.closeSubpath()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_c(o.ear_inner))
                p.drawPath(inner)
            else:
                p.setPen(QPen(_c(o.edge), 1))
                p.setBrush(_c(o.ear_color))
                p.drawEllipse(QPointF(r * 0.1, 0), r * 0.2, r * 0.2)
                p.setBrush(_c(o.ear_inner))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(r * 0.12, 0), r * 0.1, r * 0.1)
            p.restore()

    if "horn" in ex:
        horn = QPainterPath()
        horn.moveTo(r * 0.78, -r * 0.1)
        horn.lineTo(r * 1.32, 0)
        horn.lineTo(r * 0.78, r * 0.1)
        horn.closeSubpath()
        g = QLinearGradient(QPointF(r * 0.78, 0), QPointF(r * 1.32, 0))
        g.setColorAt(0, _c("#ffd36b"))
        g.setColorAt(1, _c("#fff6c9"))
        p.setPen(QPen(_c("#c9962a"), 1))
        p.setBrush(QBrush(g))
        p.drawPath(horn)
        p.setPen(QPen(_c("#c9962a", 200), 1))
        for k in range(4):
            x = r * (0.86 + k * 0.11)
            hw = 0.1 * (1.32 * r - x) / (0.54 * r) * r
            p.drawLine(QPointF(x, -hw), QPointF(x + r * 0.05, hw))

    if "antennae" in ex:
        pen = QPen(_c("#1c1c1c"), r * 0.035)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        wob = math.sin(t * 6) * r * 0.03
        for side in (-1, 1):
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath(QPointF(r * 0.7, side * r * 0.15))
            path.quadTo(QPointF(r * 1.0, side * r * 0.2), QPointF(r * 1.15 + wob, side * r * 0.38))
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_c("#1c1c1c"))
            p.drawEllipse(QPointF(r * 1.15 + wob, side * r * 0.38), r * 0.06, r * 0.06)

    s = r * 0.12
    if "eyes" in ex:
        for side in (-1, 1):
            _eye(p, r * 0.5, side * r * 0.24, s, t, happy)
    if "panda_eyes" in ex:
        for side in (-1, 1):
            p.save()
            p.translate(r * 0.5, side * r * 0.25)
            p.rotate(side * -25)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_c("#1c1c1e"))
            p.drawEllipse(QPointF(0, 0), s * 1.7, s * 1.25)
            p.restore()
            _eye(p, r * 0.5, side * r * 0.25, s * 0.8, t, happy)
    if "frog_eyes" in ex:
        for side in (-1, 1):
            a = math.radians(side * 32)
            cx, cy = math.cos(a) * r * 0.86, math.sin(a) * r * 0.86
            p.setPen(QPen(_c(o.edge), 1.2))
            p.setBrush(_c(o.body[1]))
            p.drawEllipse(QPointF(cx, cy), r * 0.22, r * 0.22)
            _eye(p, cx + r * 0.02, cy, r * 0.15, t, happy)
        pen = QPen(_c(o.edge), r * 0.04)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(r * 0.4, -r * 0.3, r * 0.4, r * 0.6), -60 * 16, 120 * 16)
    if "blush" in ex:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_c("#ff7f9e", 110))
        for side in (-1, 1):
            p.drawEllipse(QPointF(r * 0.36, side * r * 0.42), r * 0.07, r * 0.1)
    if "whiskers" in ex:
        pen = QPen(_c("#5a2d08", 200), 1.1)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(_c("#ff8fa3"))
        p.drawEllipse(QPointF(r * 0.62, 0), r * 0.04, r * 0.05)  # neusje
        for side in (-1, 1):
            for k in (-1, 0, 1):
                p.drawLine(QPointF(r * 0.6, side * r * 0.1), QPointF(r * 0.72 + k * r * 0.06, side * r * 0.5))
    if "ghost_mouth" in ex:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_c("#3b3f52"))
        p.drawEllipse(QPointF(r * 0.66, 0), r * 0.05, r * 0.07 * (1 + 0.3 * math.sin(t * 3)))
