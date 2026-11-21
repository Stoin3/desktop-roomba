"""Tekenwerk: de roomba en zijn laadstation, van bovenaf gezien.

Alle functies tekenen rond de oorsprong; de aanroeper zet translate/rotate.
De roomba 'kijkt' in de +x-richting (heading 0).
"""

from __future__ import annotations

import math

from . import outfits

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)


def _c(hex_: str, a: int = 255) -> QColor:
    col = QColor(hex_)
    col.setAlpha(a)
    return col


# --------------------------------------------------------------------------
# Roomba
# --------------------------------------------------------------------------

def draw_shadow(p: QPainter, r: float) -> None:
    g = QRadialGradient(QPointF(r * 0.10, r * 0.16), r * 1.18)
    g.setColorAt(0.0, _c("#000000", 110))
    g.setColorAt(0.75, _c("#000000", 60))
    g.setColorAt(1.0, _c("#000000", 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(r * 0.10, r * 0.16), r * 1.18, r * 1.18)


def draw_side_brush(p: QPainter, r: float, angle_deg: float, motion_blur: float) -> None:
    """Zijborstel rechtsvoor, steekt een beetje buiten de behuizing uit."""
    cx, cy = r * 0.62, r * 0.55  # rechtsvoor (y omlaag = rechts t.o.v. rijrichting)
    p.save()
    p.translate(cx, cy)
    p.rotate(angle_deg)
    arm = r * 0.55
    # vage 'draaicirkel' bij hoge snelheid
    if motion_blur > 0.05:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_c("#d9d2c3", int(55 * motion_blur)))
        p.drawEllipse(QPointF(0, 0), arm, arm)
    for i in range(3):
        p.save()
        p.rotate(i * 120)
        for k in range(5):  # elke arm = bundeltje haren
            off = (k - 2) * 2.2
            pen = QPen(_c("#e8e1d0", 230 if k == 2 else 170), 1.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            path = QPainterPath(QPointF(0, 0))
            path.quadTo(QPointF(arm * 0.55, off * 1.2), QPointF(arm, off * 2.5 + arm * 0.12))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.restore()
    # naaf
    p.setPen(QPen(_c("#111111"), 1))
    p.setBrush(_c("#3a3d42"))
    p.drawEllipse(QPointF(0, 0), r * 0.09, r * 0.09)
    p.restore()


def led_color(state: str, t: float) -> tuple[QColor, float]:
    """Kleur en intensiteit (0..1) van de statusring."""
    if state == "charging":
        return _c("#38e07b"), 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 2.2))
    if state == "thinking":
        return _c("#4aa8ff"), 1.0
    if state in ("working", "returning", "leaving"):
        return _c("#f4f7ff"), 1.0
    if state == "happy":
        return _c("#ffd34a"), 1.0
    if state == "error":
        return _c("#ff5a4a"), 0.5 + 0.5 * (math.sin(t * 8) > 0)
    return _c("#38e07b"), 0.6


def draw_roomba(p: QPainter, r: float, state: str, t: float, brush_angle: float, brush_speed: float,
                bin_fill: float = 0.0, outfit: "outfits.Outfit | None" = None) -> None:
    o = outfit or outfits.get(outfits.DEFAULT)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    outfits.draw_under(p, r, o, t, brush_speed)

    draw_side_brush(p, r, brush_angle, brush_speed)

    # --- behuizing -----------------------------------------------------
    body = QRadialGradient(QPointF(-r * 0.25, -r * 0.3), r * 1.35)
    body.setColorAt(0.0, _c(o.body[0]))
    body.setColorAt(0.55, _c(o.body[1]))
    body.setColorAt(1.0, _c(o.body[2]))
    p.setPen(QPen(_c(o.edge), 1.5))
    p.setBrush(QBrush(body))
    p.drawEllipse(QPointF(0, 0), r, r)
    outfits.draw_pattern(p, r, o)

    # --- bumper (voorste helft) -------------------------------------------
    bumper = QPainterPath()
    outer = QRectF(-r, -r, 2 * r, 2 * r)
    inner_r = r * 0.9
    inner = QRectF(-inner_r, -inner_r, 2 * inner_r, 2 * inner_r)
    bumper.arcMoveTo(outer, 95)
    bumper.arcTo(outer, 95, -190)
    bumper.arcTo(inner, -95, 190)
    bumper.closeSubpath()
    bg = QLinearGradient(QPointF(r, 0), QPointF(0, 0))
    bg.setColorAt(0.0, _c(o.bumper[0]))
    bg.setColorAt(1.0, _c(o.bumper[1]))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(bg))
    p.drawPath(bumper)
    # naad van de bumper
    p.setPen(QPen(_c(o.edge, 220), 1.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(inner, -95 * 16, 190 * 16)

    # --- stofbak (achterkant) ---------------------------------------------
    bin_rect = QRectF(-r * 0.93, -r * 0.93, r * 1.86, r * 1.86)
    p.setPen(QPen(_c(o.bin_lines, 150), 1.0))
    p.drawArc(bin_rect, 140 * 16, 80 * 16)
    p.drawArc(QRectF(-r * 0.78, -r * 0.78, r * 1.56, r * 1.56), 140 * 16, 80 * 16)
    # ribbeltjes / handgreep
    p.setPen(QPen(_c(o.edge, 200), 1.6))
    for i in range(5):
        a = math.radians(160 + i * 10)
        p.drawLine(QPointF(math.cos(a) * r * 0.8, math.sin(a) * r * 0.8),
                   QPointF(math.cos(a) * r * 0.9, math.sin(a) * r * 0.9))
    # stofbak-vulindicator (kleine strook die oranje wordt)
    if bin_fill > 0:
        pen = QPen(_c("#ff9b3d", int(80 + 140 * min(1, bin_fill))), 2.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        span = 70 * min(1.0, bin_fill)
        p.drawArc(QRectF(-r * 0.85, -r * 0.85, r * 1.7, r * 1.7), int((180 - span / 2) * 16), int(span * 16))

    # --- glanzende bovenplaat -------------------------------------------
    plate_r = r * 0.68
    pg = QRadialGradient(QPointF(-r * 0.2, -r * 0.25), plate_r * 1.4)
    pg.setColorAt(0.0, _c(o.plate[0]))
    pg.setColorAt(0.6, _c(o.plate[1]))
    pg.setColorAt(1.0, _c(o.plate[2]))
    p.setPen(QPen(_c(o.edge), 1.2))
    p.setBrush(QBrush(pg))
    p.drawEllipse(QPointF(0, 0), plate_r, plate_r)

    # reflectie
    hl = QPainterPath()
    hl.addEllipse(QPointF(-r * 0.18, -r * 0.28), plate_r * 0.75, plate_r * 0.38)
    hg = QLinearGradient(QPointF(0, -plate_r), QPointF(0, 0))
    hg.setColorAt(0.0, _c("#ffffff", 70))
    hg.setColorAt(1.0, _c("#ffffff", 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(hg))
    p.drawPath(hl.intersected(_circle(plate_r)))

    # --- camera / sensorvenster voor (niet bij outfits met een gezichtje)
    if not any(e in o.extras for e in ("eyes", "panda_eyes", "frog_eyes", "whiskers")):
        p.setBrush(_c("#07080a"))
        p.setPen(QPen(_c("#4b4f57"), 0.8))
        p.drawRoundedRect(QRectF(r * 0.72, -r * 0.13, r * 0.11, r * 0.26), 3, 3)
        p.setBrush(_c("#3a6ea8", 160))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(r * 0.775, -r * 0.05), r * 0.02, r * 0.02)

    # --- statusring + knop ------------------------------------------------
    col, inten = led_color(state, t)
    ring_r = r * 0.3
    if state == "thinking":
        cg = QConicalGradient(QPointF(0, 0), -t * 360 * 1.3)
        cg.setColorAt(0.0, _c(col.name(), 255))
        cg.setColorAt(0.35, _c(col.name(), 30))
        cg.setColorAt(1.0, _c(col.name(), 255))
        pen = QPen(QBrush(cg), r * 0.07)
    else:
        pen = QPen(_c(col.name(), int(255 * inten)), r * 0.06)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # gloed
    glow = QRadialGradient(QPointF(0, 0), ring_r * 1.6)
    glow.setColorAt(0.55, _c(col.name(), int(90 * inten)))
    glow.setColorAt(1.0, _c(col.name(), 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(glow))
    p.drawEllipse(QPointF(0, 0), ring_r * 1.6, ring_r * 1.6)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(pen)
    p.drawEllipse(QPointF(0, 0), ring_r, ring_r)

    btn = QRadialGradient(QPointF(-ring_r * 0.3, -ring_r * 0.3), ring_r)
    btn.setColorAt(0.0, _c(o.button[0]))
    btn.setColorAt(1.0, _c(o.button[1]))
    p.setPen(QPen(_c("#111214"), 1))
    p.setBrush(QBrush(btn))
    p.drawEllipse(QPointF(0, 0), ring_r * 0.78, ring_r * 0.78)

    # 'CLEAN'-tekst, leesbaar ongeacht de rijrichting: tegen-roteren
    p.save()
    tr = p.worldTransform()
    heading = math.degrees(math.atan2(tr.m12(), tr.m11()))
    p.rotate(-heading)
    f = QFont("Sans")
    f.setPixelSize(max(6, int(r * 0.11)))
    f.setBold(True)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
    p.setFont(f)
    p.setPen(_c(o.text, 220))
    p.drawText(QRectF(-ring_r, -ring_r, 2 * ring_r, 2 * ring_r), Qt.AlignmentFlag.AlignCenter, "CLEAN")
    p.restore()

    outfits.draw_face(p, r, o, t, state)


def _circle(rad: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(0, 0), rad, rad)
    return path


# --------------------------------------------------------------------------
# Laadstation (hub)
# --------------------------------------------------------------------------

def draw_hub_base(p: QPainter, r: float, t: float, charging: bool, occupied: bool) -> None:
    """Basisplaat + toren. Oorsprong = parkeerpositie van de roomba.
    De roomba rijdt er vanaf links (−x) in; de toren staat rechts."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    tower_x = r * 1.04

    # schaduw
    sg = QRadialGradient(QPointF(tower_x * 0.6, r * 0.15), r * 1.5)
    sg.setColorAt(0.0, _c("#000000", 70))
    sg.setColorAt(1.0, _c("#000000", 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(sg))
    p.drawEllipse(QPointF(tower_x * 0.6, r * 0.15), r * 1.5, r * 1.3)

    # oprijplaat
    plate = QPainterPath()
    plate.addRoundedRect(QRectF(-r * 0.25, -r * 0.62, tower_x + r * 0.25, r * 1.24), r * 0.25, r * 0.25)
    pg = QLinearGradient(QPointF(-r * 0.25, 0), QPointF(tower_x, 0))
    pg.setColorAt(0.0, _c("#2a2c30", 120))
    pg.setColorAt(0.4, _c("#2f3236", 235))
    pg.setColorAt(1.0, _c("#3a3d42", 255))
    p.setBrush(QBrush(pg))
    p.setPen(QPen(_c("#16171a", 200), 1))
    p.drawPath(plate)

    # laadcontacten
    for dy in (-0.32, 0.32):
        cg = QLinearGradient(QPointF(0, r * (dy - 0.06)), QPointF(0, r * (dy + 0.06)))
        cg.setColorAt(0.0, _c("#f1f3f5"))
        cg.setColorAt(0.5, _c("#9aa0a8"))
        cg.setColorAt(1.0, _c("#d5d9de"))
        p.setBrush(QBrush(cg))
        p.setPen(QPen(_c("#55595f"), 0.8))
        p.drawRoundedRect(QRectF(r * 0.18, r * (dy - 0.06), r * 0.42, r * 0.12), 3, 3)

    if not occupied:
        # 'parkeervak'-cirkeltje als hint
        p.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(_c("#ffffff", 40), 1.2, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawEllipse(QPointF(0, 0), r * 0.98, r * 0.98)


def draw_hub_tower(p: QPainter, r: float, t: float, charging: bool) -> None:
    """De toren wordt BOVEN de roomba getekend (hij staat erachter/eroverheen)."""
    tower_x = r * 1.04
    tower = QPainterPath()
    tower.moveTo(tower_x - r * 0.05, -r * 0.78)
    tower.cubicTo(QPointF(tower_x + r * 0.55, -r * 0.82), QPointF(tower_x + r * 0.62, r * 0.82),
                  QPointF(tower_x - r * 0.05, r * 0.78))
    tower.cubicTo(QPointF(tower_x + r * 0.12, r * 0.3), QPointF(tower_x + r * 0.12, -r * 0.3),
                  QPointF(tower_x - r * 0.05, -r * 0.78))
    tg = QLinearGradient(QPointF(tower_x, 0), QPointF(tower_x + r * 0.55, 0))
    tg.setColorAt(0.0, _c("#45484e"))
    tg.setColorAt(0.5, _c("#2b2d31"))
    tg.setColorAt(1.0, _c("#18191c"))
    p.setPen(QPen(_c("#0c0d0f"), 1.2))
    p.setBrush(QBrush(tg))
    p.drawPath(tower)

    # glanslijn
    p.setPen(QPen(_c("#ffffff", 45), 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    arc = QPainterPath()
    arc.moveTo(tower_x + r * 0.08, -r * 0.6)
    arc.cubicTo(QPointF(tower_x + r * 0.3, -r * 0.55), QPointF(tower_x + r * 0.33, r * 0.5),
                QPointF(tower_x + r * 0.1, r * 0.6))
    p.drawPath(arc)

    # IR-venster
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_c("#0a0a0c"))
    p.drawRoundedRect(QRectF(tower_x + r * 0.13, -r * 0.18, r * 0.08, r * 0.36), 3, 3)

    # status-LED
    if charging:
        inten = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 2.2))
        col = "#38e07b"
    else:
        inten = 0.9
        col = "#ffffff"
    led = QPointF(tower_x + r * 0.36, 0)
    g = QRadialGradient(led, r * 0.2)
    g.setColorAt(0.0, _c(col, int(230 * inten)))
    g.setColorAt(1.0, _c(col, 0))
    p.setBrush(QBrush(g))
    p.drawEllipse(led, r * 0.2, r * 0.2)
    p.setBrush(_c(col, int(120 + 135 * inten)))
    p.drawEllipse(led, r * 0.035, r * 0.035)


# --------------------------------------------------------------------------
# Tekstballon
# --------------------------------------------------------------------------

def draw_bubble(p: QPainter, anchor: QPointF, text: str, alpha: float, bounds: QRectF,
                below_y: float | None = None) -> QRectF:
    if alpha <= 0 or not text:
        return QRectF()
    f = QFont("Sans")
    f.setPixelSize(13)
    p.setFont(f)
    fm = p.fontMetrics()
    lines = text.split("\n")
    w = max(fm.horizontalAdvance(line) for line in lines) + 22
    h = fm.height() * len(lines) + 14
    x = anchor.x() - w / 2
    y = anchor.y() - h - 12
    # binnen het scherm houden
    x = max(bounds.left() + 4, min(x, bounds.right() - w - 4))
    flip = y < bounds.top() + 4
    if flip:
        anchor = QPointF(anchor.x(), below_y if below_y is not None else anchor.y())
        y = anchor.y() + 12  # onder de roomba
    rect = QRectF(x, y, w, h)
    a = int(255 * alpha)
    path = QPainterPath()
    path.addRoundedRect(rect, 9, 9)
    tail = QPainterPath()
    ax = max(rect.left() + 12, min(anchor.x(), rect.right() - 12))
    if flip:
        tail.moveTo(ax - 7, rect.top() + 1)
        tail.lineTo(ax, rect.top() - 8)
        tail.lineTo(ax + 7, rect.top() + 1)
    else:
        tail.moveTo(ax - 7, rect.bottom() - 1)
        tail.lineTo(ax, rect.bottom() + 8)
        tail.lineTo(ax + 7, rect.bottom() - 1)
    tail.closeSubpath()
    path = path.united(tail)
    p.setPen(QPen(_c("#000000", int(a * 0.35)), 1))
    p.setBrush(_c("#fbfbfd", int(a * 0.95)))
    p.drawPath(path)
    p.setPen(_c("#1d1f23", a))
    p.drawText(rect.adjusted(11, 7, -11, -7), Qt.AlignmentFlag.AlignCenter, text)
    return rect.adjusted(-2, -10, 2, 10)
