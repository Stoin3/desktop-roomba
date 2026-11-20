"""KDE Roomba – hoofdprogramma.

Een transparant venster ter grootte van het bureaublad. Alleen de roomba
(en het laadstation) vangen muisklikken; de rest van het venster laat
klikken door naar het bureaublad (Wayland input-region / X11 shape).
"""

from __future__ import annotations

import math
import os
import random
import shutil
import signal
import subprocess
import sys
import time
import logging
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QMimeDatabase, QPointF, QRect, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap, QRegion
from PyQt6.QtWidgets import QApplication, QFileIconProvider, QMenu, QWidget
from PyQt6.QtCore import QFileInfo, QFile, QLockFile

from . import APP_ID, __version__, art, brain, kwin, wayland_layer
from .config import Config, config_dir, state_dir
from .desktop_layout import DesktopLayout

log = logging.getLogger("kde-roomba")


def wrap_angle(a: float) -> float:
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def ease_in_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


# --------------------------------------------------------------------------
# Achtergrondthread voor scannen + AI
# --------------------------------------------------------------------------

class BrainWorker(QThread):
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(list, str, int, str)  # [Verdict], methode, aantal_bekeken, overgeslagen
    failed = pyqtSignal(str)

    def __init__(self, cfg: Config, desktop: Path):
        super().__init__()
        self.cfg = cfg
        self.desktop = desktop

    def run(self) -> None:
        try:
            items = brain.scan_desktop(self.cfg, self.desktop)

            def prog(done: int, total: int) -> None:
                if total:
                    self.progress.emit(f"Even nadenken…\n{done}/{total} bestanden bekeken")

            verdicts, method = brain.classify(self.cfg, items, prog)
            from collections import Counter

            skipped = Counter(i.protected_reason for i in items if i.protected_reason)
            labels = {"map": "map(pen)", "snelkoppeling": "snelkoppeling(en)", "te nieuw": "net gewijzigd"}
            skip_txt = ", ".join(f"{n} {labels.get(r, r)}" for r, n in skipped.most_common())
            log.info("Bekeken: %d, overgeslagen: %s, methode: %s", len(items), skip_txt or "geen", method)
            for v in verdicts:
                log.info("  %s %s — %s [%s]", "AFVAL " if v.trash else "houden", v.info.name, v.reason, v.source)
            self.finished_ok.emit(brain.choose_trash(self.cfg, verdicts), method, len(items), skip_txt)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


# --------------------------------------------------------------------------
# Effecten
# --------------------------------------------------------------------------

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: QColor
    target: Callable[[], QPointF] | None = None


@dataclass
class FlyingIcon:
    pixmap: QPixmap
    start: QPointF
    t: float = 0.0
    duration: float = 1.1


@dataclass
class Robot:
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0  # radialen, 0 = naar rechts
    speed: float = 0.0
    brush_angle: float = 0.0
    brush_speed: float = 0.0  # 0..1
    bin_fill: float = 0.0
    trail: list[tuple[float, float, float]] = field(default_factory=list)  # x, y, tijd


# --------------------------------------------------------------------------
# Acties (een simpele takenrij voor de animaties)
# --------------------------------------------------------------------------

class Action:
    def start(self, w: "RoombaWindow") -> None: ...

    def step(self, w: "RoombaWindow", dt: float) -> bool:
        """True = klaar."""
        return True


class Wait(Action):
    def __init__(self, seconds: float):
        self.left = seconds

    def step(self, w, dt):
        self.left -= dt
        return self.left <= 0


class Call(Action):
    def __init__(self, fn: Callable[[], None]):
        self.fn = fn

    def step(self, w, dt):
        self.fn()
        return True


class Reverse(Action):
    def __init__(self, dist: float, speed: float = 70.0):
        self.left = dist
        self.speed = speed

    def step(self, w, dt):
        r = w.robot
        d = min(self.left, self.speed * dt)
        r.x -= math.cos(r.heading) * d
        r.y -= math.sin(r.heading) * d
        r.speed = -self.speed
        self.left -= d
        if self.left <= 0:
            r.speed = 0
            return True
        return False


class TurnTo(Action):
    def __init__(self, angle_fn: Callable[[], float]):
        self.angle_fn = angle_fn

    def step(self, w, dt):
        r = w.robot
        diff = wrap_angle(self.angle_fn() - r.heading)
        maxd = math.radians(w.cfg.turn_deg_s) * dt
        if abs(diff) <= maxd:
            r.heading += diff
            return True
        r.heading += math.copysign(maxd, diff)
        return False


class DriveTo(Action):
    """Rijdt vloeiend naar een doel: stuurt tijdens het rijden bij,
    remt af bij het doel, met een klein beetje 'roomba-wiebel'."""

    def __init__(self, target_fn: Callable[[], QPointF], stop_short: float = 0.0, max_speed: float | None = None):
        self.target_fn = target_fn
        self.stop_short = stop_short
        self.max_speed = max_speed
        self.t = 0.0
        self.stuck = 0.0

    def step(self, w, dt):
        r = w.robot
        self.t += dt
        tgt = self.target_fn()
        dx, dy = tgt.x() - r.x, tgt.y() - r.y
        dist = math.hypot(dx, dy) - self.stop_short
        if dist <= 2.0:
            r.speed = 0.0
            return True
        desired = math.atan2(dy, dx) + 0.06 * math.sin(self.t * 5.0)
        diff = wrap_angle(desired - r.heading)
        maxd = math.radians(w.cfg.turn_deg_s) * dt
        r.heading += max(-maxd, min(maxd, diff))
        vmax = self.max_speed or w.cfg.speed_px_s
        align = max(0.0, math.cos(diff)) ** 3
        accel = 520.0
        v_target = min(vmax * align, math.sqrt(2 * accel * 0.8 * max(dist, 0)) + 15)
        if r.speed < v_target:
            r.speed = min(v_target, r.speed + accel * dt)
        else:
            r.speed = max(v_target, r.speed - accel * 1.5 * dt)
        step = min(r.speed * dt, dist)
        r.x += math.cos(r.heading) * step
        r.y += math.sin(r.heading) * step
        self.stuck = self.stuck + dt if self.t > 25 else 0
        return self.stuck > 0.5  # noodrem


class Suck(Action):
    """Rijdt langzaam over het icoon terwijl het naar binnen gezogen wordt."""

    def __init__(self, target: brain.Verdict, pos_fn: Callable[[], QPointF], duration: float = 1.3):
        self.v = target
        self.pos_fn = pos_fn
        self.duration = duration
        self.t = 0.0
        self.started = False
        self.base_heading = 0.0

    def start(self, w):
        self.started = True
        self.base_heading = w.robot.heading
        w.begin_suck(self.v, self.pos_fn())

    def step(self, w, dt):
        if not self.started:
            self.start(w)
        self.t += dt
        r = w.robot
        k = self.t / self.duration
        # wiebelen
        r.heading = self.base_heading + math.radians(14) * math.sin(k * math.pi * 4) * (1 - k)
        # langzaam vooruit, over de plek van het icoon
        tgt = self.pos_fn()
        dx, dy = tgt.x() - r.x, tgt.y() - r.y
        d = math.hypot(dx, dy)
        if d > 1:
            mv = min(d, 55 * dt)
            r.x += dx / d * mv
            r.y += dy / d * mv
        r.speed = 40
        if self.t >= self.duration:
            r.speed = 0
            r.heading = self.base_heading
            return True
        return False


class Spin(Action):
    def __init__(self, turns: float, seconds: float):
        self.total = turns * 2 * math.pi
        self.seconds = seconds
        self.t = 0.0
        self.start_h = None

    def step(self, w, dt):
        if self.start_h is None:
            self.start_h = w.robot.heading
        self.t += dt
        k = ease_in_out(self.t / self.seconds)
        w.robot.heading = self.start_h + self.total * k
        if self.t >= self.seconds:
            w.robot.heading = self.start_h
            return True
        return False


# --------------------------------------------------------------------------
# Het venster
# --------------------------------------------------------------------------

class RoombaWindow(QWidget):
    def __init__(self, cfg: Config, geom: QRect):
        super().__init__()
        self.cfg = cfg
        self.geom = geom
        self.R = cfg.roomba_size / 2
        self.wayland = QGuiApplication.platformName().startswith("wayland")
        self.desktop = brain.desktop_dir()

        self.setWindowTitle("KDE Roomba")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnBottomHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.resize(geom.size())

        # Wayland: via layer-shell-qt in de 'bottom'-laag (boven het
        # bureaublad, onder vensters). De compositor bepaalt dan de grootte
        # (het vrije bureaubladgebied) → zie resizeEvent.
        self.layer_shell, how = (wayland_layer.enable(self, screen=self.target_screen())
                                 if self.wayland else (False, "X11"))
        log.info("Vensterlaag: %s (%s)", "layer-shell" if self.layer_shell else "gewoon venster", how)
        if not self.layer_shell:
            self.setGeometry(geom)

        self.hub = self._initial_hub()
        self.robot = Robot(self.hub.x(), self.hub.y(), 0.0)
        self.state = "charging"
        self.t0 = time.monotonic()
        self.last = self.t0
        self.queue: list[Action] = []
        self.particles: list[Particle] = []
        self.flying: list[FlyingIcon] = []
        self.bubble_text = ""
        self.bubble_until = 0.0
        self.bubble_alpha = 0.0
        self.hover = False
        self.press_pos: QPointF | None = None
        self.dragging = False
        self.worker: BrainWorker | None = None
        self._threads: set[BrainWorker] = set()
        self.cleaned: list[brain.Verdict] = []
        self.failed: list[str] = []
        self.sparks_at = 0.0
        self.mime_db = QMimeDatabase()
        self.icon_provider = QFileIconProvider()

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

        self.say(f"Hoi! Dubbelklik op mij\nom je bureaublad op te ruimen.", 5)

    # ------------------------------------------------------------ helpers
    def target_screen(self):
        """Het scherm met je bureaublad-iconen: config 'screen', anders KDE's hoofdscherm."""
        screens = {sc.name(): sc for sc in QGuiApplication.screens()}
        want = self.cfg.screen or wayland_layer.kde_primary_output()
        log.info("Gewenst scherm: %s", want or "(onbekend – compositor kiest)")
        return screens.get(want) if want else None

    def now(self) -> float:
        return time.monotonic() - self.t0

    def _initial_hub(self) -> QPointF:
        R = self.R
        if self.cfg.hub_x is not None and self.cfg.hub_y is not None:
            x, y = self.cfg.hub_x, self.cfg.hub_y
        else:
            x = self.geom.width() - R * 2.6
            y = self.geom.height() - R * 1.8
        return self._clamp_hub(QPointF(x, y))

    def _clamp_hub(self, p: QPointF) -> QPointF:
        R = self.R
        return QPointF(
            max(R * 1.3, min(p.x(), self.geom.width() - R * 2.2)),
            max(R * 1.3, min(p.y(), self.geom.height() - R * 1.3)),
        )

    def say(self, text: str, seconds: float = 3.5) -> None:
        self.bubble_text = text
        self.bubble_until = self.now() + seconds

    def roomba_pos(self) -> QPointF:
        return QPointF(self.robot.x, self.robot.y)

    def busy(self) -> bool:
        return self.state not in ("charging", "idle", "error")

    def layout(self) -> DesktopLayout:
        # Kirigami.Units.gridUnit = hoogte van het standaardlettertype (even getal)
        gu = QFontMetrics(QApplication.font()).height()
        gu += gu % 2
        h = self.windowHandle()
        sc = h.screen() if h and h.screen() else QGuiApplication.primaryScreen()
        sg = sc.geometry() if sc else self.geom
        return DesktopLayout(self.cfg, 0, 0, self.geom.width(), self.geom.height(),
                             grid_unit=gu, screen_w=sg.width(), screen_h=sg.height())

    def icon_position(self, name: str) -> QPointF | None:
        # Kort cachen: tijdens het rijden wordt dit elk frame gevraagd.
        cache = getattr(self, "_pos_cache", None)
        if cache and time.monotonic() - cache[0] < 0.5 and name in cache[1]:
            return cache[1][name]
        result = self._compute_icon_positions(name)
        self._pos_cache = (time.monotonic(), result)
        return result.get(name)

    def _compute_icon_positions(self, name: str) -> dict[str, QPointF]:
        try:
            entries = [(e.name, e.is_dir()) for e in os.scandir(self.desktop) if not e.name.startswith(".")]
        except OSError:
            entries = []
        if not any(n == name for n, _ in entries):
            entries.append((name, False))
        return {n: QPointF(*xy) for n, xy in self.layout().positions(entries).items()}

    def file_pixmap(self, info: brain.FileInfo, size: int) -> QPixmap:
        if info.mime.startswith("image/") and 0 < info.size < 25 * 1024 * 1024:
            pm = QPixmap(str(info.path))
            if not pm.isNull():
                return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        mt = self.mime_db.mimeTypeForFile(str(info.path))
        icon = QIcon.fromTheme(mt.iconName(), QIcon.fromTheme(mt.genericIconName()))
        if icon.isNull():
            icon = self.icon_provider.icon(QFileInfo(str(info.path)))
        if icon.isNull():
            icon = QIcon.fromTheme("text-x-generic")
        return icon.pixmap(size, size)

    # ------------------------------------------------------------ flow
    def start_cleaning(self) -> None:
        if self.busy():
            return
        self.state = "thinking"
        self.say("Even nadenken…\nwelke bestanden zijn afval?", 600)
        self.cleaned, self.failed = [], []
        self.robot.bin_fill = 0.0
        self.worker = BrainWorker(self.cfg, self.desktop)
        self._threads.add(self.worker)  # referentie houden tot de thread echt klaar is
        self.worker.progress.connect(lambda s: self.say(s, 600))
        self.worker.finished_ok.connect(self.on_brain_done)
        self.worker.failed.connect(self.on_brain_failed)
        # Pas loslaten als de thread écht klaar is (anders: "QThread: Destroyed
        # while thread is still running" → crash).
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()

    def _worker_finished(self) -> None:
        w = self.sender()
        if w is self.worker:
            self.worker = None
        if w in self._threads:
            self._threads.discard(w)
            w.deleteLater()

    def stop_worker(self) -> None:
        """Bij afsluiten: lopende AI-vragen netjes laten aflopen."""
        for w in list(self._threads):
            if w.isRunning() and not w.wait(3000):
                w.terminate()
                w.wait(2000)

    def on_brain_failed(self, msg: str) -> None:
        self.state = "error"
        self.say(f"Er ging iets mis 😵\n{msg[:80]}", 6)
        self.queue = [Wait(4), Call(self._back_to_charging)]

    def on_brain_done(self, targets: list, method: str, seen: int, skipped: str = "") -> None:
        if not targets:
            self.state = "happy"
            extra = f"\nOvergeslagen: {skipped}" if skipped else ""
            self.say(f"Alles is al schoon! ✨\n({seen} items bekeken, {method}){extra}", 7)
            self.queue = [Wait(0.3), Spin(1, 1.4), Wait(0.4), Call(self._back_to_charging)]
            return

        names = ", ".join(v.info.name for v in targets[:3]) + ("…" if len(targets) > 3 else "")
        extra = " (proefrun)" if self.cfg.dry_run else ""
        self.say(f"{len(targets)} stuk(s) afval gevonden{extra}!\n{names}", 3.5)
        self.state = "leaving"

        # volgorde: steeds de dichtstbijzijnde
        remaining = list(targets)
        order: list[brain.Verdict] = []
        cur = self.hub
        start_positions = {v.info.name: self.icon_position(v.info.name) for v in remaining}
        while remaining:
            def d(v):
                p = start_positions.get(v.info.name) or self.hub
                return (p.x() - cur.x()) ** 2 + (p.y() - cur.y()) ** 2
            nxt = min(remaining, key=d)
            remaining.remove(nxt)
            order.append(nxt)
            cur = start_positions.get(nxt.info.name) or cur

        lay = self.layout()
        log.info("Bureaubladraster: %s", lay.describe())
        for v in order:
            p = start_positions.get(v.info.name)
            log.info("  doel %s op (%d, %d)", v.info.name, p.x() if p else -1, p.y() if p else -1)

        q: list[Action] = [Wait(0.6), Reverse(self.R * 1.5), Call(lambda: self._set_state("working"))]
        for v in order:
            q += self._visit(v)
        q += self._return_home()
        self.queue = q

    def _set_state(self, s: str) -> None:
        self.state = s

    def _visit(self, v: brain.Verdict) -> list[Action]:
        cache: dict[str, QPointF] = {}

        def pos() -> QPointF:
            # posities lui bepalen: Plasma kan iconen verschuiven nadat er
            # een is weggehaald. Eenmaal bij het doel: vastzetten.
            if "p" not in cache:
                p = self.icon_position(v.info.name) or self.hub
                return self._clamp_target(p)
            return cache["p"]

        def lock() -> None:
            cache["p"] = pos()

        return [
            DriveTo(pos, stop_short=self.R * 1.05),
            Call(lock),
            Suck(v, pos),
            Wait(0.15),
        ]

    def _clamp_target(self, p: QPointF) -> QPointF:
        R = self.R
        return QPointF(max(R, min(p.x(), self.geom.width() - R)), max(R, min(p.y(), self.geom.height() - R)))

    def _return_home(self) -> list[Action]:
        approach = lambda: QPointF(self.hub.x() - self.R * 2.2, self.hub.y())
        return [
            Call(lambda: self._set_state("returning")),
            DriveTo(approach),
            TurnTo(lambda: 0.0),
            DriveTo(lambda: self.hub, max_speed=90),
            Call(self._docked),
        ]

    def _docked(self) -> None:
        self.robot.x, self.robot.y, self.robot.heading = self.hub.x(), self.hub.y(), 0.0
        self.sparks_at = self.now()
        self._back_to_charging()
        n = len(self.cleaned)
        if self.cfg.dry_run:
            msg = f"Proefrun klaar: {n} bestand(en)\nzou ik weggooien. Niets verwijderd."
        else:
            msg = f"Klaar! {n} bestand(en) in de prullenbak. 🗑️"
        if self.failed:
            msg += f"\n{len(self.failed)} lukte niet."
        self.say(msg, 6)

    def _back_to_charging(self) -> None:
        self.state = "charging"

    def begin_suck(self, v: brain.Verdict, pos: QPointF) -> None:
        """Het moment van opzuigen: bestand naar de prullenbak + animatie."""
        size = self.layout().icon_px
        pm = self.file_pixmap(v.info, size)
        ok = True
        if not self.cfg.dry_run:
            ok = trash_file(v.info.path)
        brain.log_action(
            f"{'PROEF ' if self.cfg.dry_run else ''}{'PRULLENBAK' if ok else 'MISLUKT'}: "
            f"{v.info.path} — {v.reason} [{v.source}]"
        )
        if not ok:
            self.failed.append(v.info.name)
            self.say(f"Oei, {v.info.name}\nkrijg ik niet weg.", 2.5)
            return
        self.cleaned.append(v)
        self.robot.bin_fill = min(1.0, self.robot.bin_fill + 0.2)
        self.flying.append(FlyingIcon(pm, QPointF(pos)))
        self.say(f"Slurp! {v.info.name}\n{v.reason}", 2.2)
        for _ in range(26):
            a = random.uniform(0, 2 * math.pi)
            rad = random.uniform(4, size * 0.7)
            self.particles.append(Particle(
                pos.x() + math.cos(a) * rad, pos.y() + math.sin(a) * rad,
                random.uniform(-30, 30), random.uniform(-30, 30),
                0.0, random.uniform(0.6, 1.2), random.uniform(1.2, 3.2),
                QColor(random.choice(["#b9a88f", "#8f8170", "#d8cdbb", "#6f6658"])),
                target=self.roomba_pos,
            ))

    # ------------------------------------------------------------ tick
    def tick(self) -> None:
        nowm = time.monotonic()
        dt = min(0.05, nowm - self.last)
        self.last = nowm
        t = self.now()
        r = self.robot

        # takenrij
        while self.queue:
            if self.queue[0].step(self, dt):
                self.queue.pop(0)
                dt = 0.0  # volgende actie begint volgende frame
                continue
            break

        moving = abs(r.speed) > 1 or self.state in ("working", "leaving", "returning")
        target_brush = 1.0 if moving and self.state != "charging" else 0.0
        r.brush_speed += (target_brush - r.brush_speed) * min(1.0, dt * 3)
        r.brush_angle = (r.brush_angle + r.brush_speed * 1100 * max(dt, 0.016)) % 360

        if self.state == "thinking":
            # klein 'wakker worden'-wiebeltje
            r.heading = math.radians(4) * math.sin(t * 6)

        # 'schoongemaakt' spoor
        if self.state in ("working", "returning", "leaving") and abs(r.speed) > 5:
            if not r.trail or math.hypot(r.trail[-1][0] - r.x, r.trail[-1][1] - r.y) > 6:
                r.trail.append((r.x, r.y, t))
        r.trail = [p for p in r.trail if t - p[2] < 3.5]

        # deeltjes
        alive = []
        for p in self.particles:
            p.life += dt
            if p.life >= p.max_life:
                continue
            if p.target:
                tp = p.target()
                dx, dy = tp.x() - p.x, tp.y() - p.y
                d = math.hypot(dx, dy) or 1
                if d < self.R * 0.35:
                    continue
                pull = 900 * (p.life / p.max_life + 0.2)
                p.vx += dx / d * pull * dt - dy / d * 220 * dt  # draaikolk
                p.vy += dy / d * pull * dt + dx / d * 220 * dt
                p.vx *= 0.9
                p.vy *= 0.9
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self.particles = alive

        for f in self.flying:
            f.t += dt
        self.flying = [f for f in self.flying if f.t < f.duration]

        target_alpha = 1.0 if t < self.bubble_until else 0.0
        if self.hover and not self.busy() and t >= self.bubble_until:
            self.bubble_text = "Dubbelklik: opruimen\nRechtsklik: menu • slepen: verplaatsen"
            target_alpha = 1.0
        self.bubble_alpha += (target_alpha - self.bubble_alpha) * min(1.0, dt * 8)

        self.update_input_region()
        self.update()

    # ------------------------------------------------------------ input region
    def interactive_rect(self) -> QRectF:
        R = self.R
        return QRectF(self.robot.x - R, self.robot.y - R, 2 * R, 2 * R)

    def hub_rect(self) -> QRectF:
        R = self.R
        return QRectF(self.hub.x() - R * 1.1, self.hub.y() - R * 1.1, R * 3.6, R * 2.2)

    def update_input_region(self) -> None:
        handle = self.windowHandle()
        if handle is None:
            return
        reg = QRegion(self.interactive_rect().toAlignedRect(), QRegion.RegionType.Ellipse)
        if self.wayland:
            # Alleen de input-region; tekenen blijft overal mogelijk.
            new = reg
        else:
            # X11: shape knipt ook het tekenen. Tijdens het rijden het hele
            # venster, in rust alleen het laadstation + ballon.
            if self.busy() or self.particles or self.flying or self.bubble_alpha > 0.02:
                new = QRegion(self.rect())
            else:
                new = QRegion(self.hub_rect().adjusted(-4, -4, 4, 4).toAlignedRect())
        # Opnieuw toepassen bij wijziging, en af en toe voor de zekerheid
        # (bijv. als de Wayland-surface pas na de eerste tick bestond).
        self._mask_frames = getattr(self, "_mask_frames", 0) + 1
        if getattr(self, "_last_region", None) != new or self._mask_frames > 60:
            self._last_region = new
            self._mask_frames = 0
            handle.setMask(new)

    # ------------------------------------------------------------ painting
    def paintEvent(self, _ev) -> None:
        if not getattr(self, "_painted_once", False):
            self._painted_once = True
            h = self.windowHandle()
            log.info("Eerste frame getekend: venster %dx%d, roomba op (%d, %d), scherm %s, schaal %.2f",
                     self.width(), self.height(), self.robot.x, self.robot.y,
                     h.screen().name() if h and h.screen() else "?", self.devicePixelRatioF())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        t = self.now()
        R = self.R
        r = self.robot
        docked = (abs(r.x - self.hub.x()) < 2 and abs(r.y - self.hub.y()) < 2)

        # laadstation (plaat)
        p.save()
        p.translate(self.hub)
        art.draw_hub_base(p, R, t, self.state == "charging", docked)
        p.restore()

        # spoor: subtiele 'gestofzuigde' baan (per vervaagniveau één pad,
        # zodat overlappende stukjes niet optellen)
        if len(r.trail) > 1:
            buckets = 14
            for b in range(buckets):
                path = QPainterPath()
                seg = False
                for (x1, y1, _t1), (x2, y2, t2) in zip(r.trail, r.trail[1:]):
                    age = (t - t2) / 3.5
                    if int(min(0.999, max(0.0, age)) * buckets) != b:
                        seg = False
                        continue
                    if not seg:
                        path.moveTo(x1, y1)
                        seg = True
                    path.lineTo(x2, y2)
                if path.isEmpty():
                    continue
                a = 1 - (b + 0.5) / buckets
                pen = QPen(QColor(255, 255, 255, int(22 * a)), R * 1.5)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)

        # vliegende iconen (onder de roomba: ze verdwijnen eronder)
        for f in self.flying:
            k = ease_in_out(f.t / f.duration)
            tgt = self.roomba_pos()
            ang = k * 2.2 * math.pi
            rad = (1 - k) * 12
            x = f.start.x() + (tgt.x() - f.start.x()) * k + math.cos(ang) * rad
            y = f.start.y() + (tgt.y() - f.start.y()) * k + math.sin(ang) * rad
            scale = max(0.05, 1 - k * 0.92)
            p.save()
            p.translate(x, y)
            p.rotate(k * 540)
            p.scale(scale, scale)
            p.setOpacity(1 - k * 0.5)
            w, h = f.pixmap.width() / f.pixmap.devicePixelRatio(), f.pixmap.height() / f.pixmap.devicePixelRatio()
            p.drawPixmap(QRectF(-w / 2, -h / 2, w, h), f.pixmap, QRectF(f.pixmap.rect()))
            p.restore()

        # stof
        p.setPen(Qt.PenStyle.NoPen)
        for prt in self.particles:
            a = 1 - prt.life / prt.max_life
            c = QColor(prt.color)
            c.setAlphaF(max(0.0, min(1.0, a)))
            p.setBrush(c)
            p.drawEllipse(QPointF(prt.x, prt.y), prt.size, prt.size)

        # roomba
        p.save()
        p.translate(r.x, r.y)
        art.draw_shadow(p, R)
        p.rotate(math.degrees(r.heading))
        state = self.state if not (self.state == "charging" and not docked) else "idle"
        art.draw_roomba(p, R, state, t, r.brush_angle, r.brush_speed, r.bin_fill)
        p.restore()

        # toren over de roomba heen
        p.save()
        p.translate(self.hub)
        art.draw_hub_tower(p, R, t, self.state == "charging" and docked)
        p.restore()

        # vonkjes bij het aankoppelen
        st = t - self.sparks_at
        if 0 <= st < 0.6 and self.sparks_at > 0:
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(10):
                a = i / 10 * 2 * math.pi
                d = R * (0.3 + st * 1.4)
                p.setBrush(QColor(140, 255, 180, int(255 * (1 - st / 0.6))))
                p.drawEllipse(QPointF(self.hub.x() + R * 0.4 + math.cos(a) * d * 0.4,
                                      self.hub.y() + math.sin(a) * d * 0.5), 2.2, 2.2)

        # hover-gloed
        if self.hover and not self.busy():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(120, 190, 255, 120), 2))
            p.drawEllipse(self.roomba_pos(), R + 4, R + 4)

        # tekstballon
        art.draw_bubble(p, QPointF(r.x, r.y - R), self.bubble_text, self.bubble_alpha,
                        QRectF(self.rect()), below_y=r.y + R)
        p.end()

    def resizeEvent(self, ev) -> None:
        sz = ev.size()
        if sz.width() <= 0 or sz.height() <= 0:
            return
        if (sz.width(), sz.height()) != (self.geom.width(), self.geom.height()):
            log.info("Bureaubladgebied: %dx%d", sz.width(), sz.height())
            self.geom = QRect(self.geom.topLeft(), sz)
            self._pos_cache = None
            if not self.busy():
                self.hub = self._initial_hub()
                self.robot.x, self.robot.y = self.hub.x(), self.hub.y()

    # ------------------------------------------------------------ muis
    def on_roomba(self, pos: QPointF) -> bool:
        return math.hypot(pos.x() - self.robot.x, pos.y() - self.robot.y) <= self.R + 2

    def mouseMoveEvent(self, ev) -> None:
        pos = ev.position()
        self.hover = self.on_roomba(pos)
        if self.press_pos is not None and not self.busy():
            if not self.dragging and (pos - self.press_pos).manhattanLength() > 6:
                self.dragging = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self.dragging:
                self.hub = self._clamp_hub(pos)
                self.robot.x, self.robot.y = self.hub.x(), self.hub.y()

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton and self.on_roomba(ev.position()):
            self.press_pos = ev.position()
        elif ev.button() == Qt.MouseButton.RightButton:
            self.show_menu(ev.globalPosition().toPoint())

    def mouseReleaseEvent(self, ev) -> None:
        if self.dragging:
            self.cfg.hub_x, self.cfg.hub_y = int(self.hub.x()), int(self.hub.y())
            self.cfg.save()
            self.unsetCursor()
        self.press_pos = None
        self.dragging = False

    def mouseDoubleClickEvent(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton and self.on_roomba(ev.position()):
            if self.busy():
                self.say("Ik ben al bezig! 🧹", 1.5)
            else:
                self.start_cleaning()

    def leaveEvent(self, _ev) -> None:
        self.hover = False

    def show_menu(self, global_pos) -> None:
        m = QMenu(self)
        a_clean = m.addAction("🧹  Opruimen")
        a_clean.setEnabled(not self.busy())
        a_dry = m.addAction("Proefrun (niets echt weggooien)")
        a_dry.setCheckable(True)
        a_dry.setChecked(self.cfg.dry_run)
        a_ai = m.addAction(f"AI gebruiken ({self.cfg.model})")
        a_ai.setCheckable(True)
        a_ai.setChecked(self.cfg.use_ai)
        m.addSeparator()
        a_hist = m.addAction("Geschiedenis bekijken")
        a_trash = m.addAction("Prullenbak openen")
        a_cfg = m.addAction("Instellingen (config.json)")
        a_home = m.addAction("Laadstation terugzetten naar rechtsonder")
        m.addSeparator()
        a_quit = m.addAction("Afsluiten")
        chosen = m.exec(global_pos)
        if chosen is a_clean:
            self.start_cleaning()
        elif chosen is a_dry:
            self.cfg.dry_run = a_dry.isChecked()
            self.cfg.save()
            self.say("Proefrun aan: ik gooi niets echt weg." if self.cfg.dry_run else "Proefrun uit.", 2.5)
        elif chosen is a_ai:
            self.cfg.use_ai = a_ai.isChecked()
            self.cfg.save()
            if self.cfg.use_ai:
                ok, why = brain.ollama_status(self.cfg)
                self.say("AI staat aan. 🧠" if ok else f"AI niet beschikbaar: {why}.\nIk gebruik mijn eigen regels.", 4)
        elif chosen is a_hist:
            f = state_dir() / "history.log"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.touch()
            open_url(str(f))
        elif chosen is a_trash:
            open_url("trash:/")
        elif chosen is a_cfg:
            open_url(str(config_dir() / "config.json"))
        elif chosen is a_home and not self.busy():
            self.cfg.hub_x = self.cfg.hub_y = None
            self.cfg.save()
            self.hub = self._initial_hub()
            self.robot.x, self.robot.y = self.hub.x(), self.hub.y()
        elif chosen is a_quit:
            QApplication.quit()


# --------------------------------------------------------------------------
# Hulpfuncties
# --------------------------------------------------------------------------

def trash_file(path: Path) -> bool:
    """Naar de (freedesktop) prullenbak – herstelbaar via Dolphin."""
    try:
        res = QFile.moveToTrash(str(path))
        ok = res[0] if isinstance(res, tuple) else bool(res)
        if ok:
            return True
    except Exception as exc:  # noqa: BLE001
        log.warning("moveToTrash faalde: %s", exc)
    for cmd in (["gio", "trash", "--", str(path)], ["kioclient6", "move", str(path), "trash:/"]):
        if shutil.which(cmd[0]):
            if subprocess.run(cmd, capture_output=True).returncode == 0:
                return True
    return False


def open_url(url: str) -> None:
    if shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def notify(title: str, body: str) -> None:
    """Bureaubladmelding, zodat fouten nooit 'stil' zijn."""
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-a", "KDE Roomba", "-i", "edit-clear-all", title, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def setup_logging() -> Path:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    logfile = d / "roomba.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(logfile, mode="w", encoding="utf-8"), logging.StreamHandler()],
    )
    return logfile


def main() -> int:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("KDE Roomba hoort bij jouw bureaublad: start hem ZONDER sudo, gewoon:  kde-roomba", file=sys.stderr)
        return 1
    logfile = setup_logging()
    try:
        return _main(logfile)
    except Exception:  # noqa: BLE001
        log.error("Opstarten mislukt:\n%s", traceback.format_exc())
        notify("KDE Roomba kon niet starten", f"Zie {logfile}")
        return 1


def _main(logfile: Path) -> int:
    QGuiApplication.setDesktopFileName(APP_ID)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName("KDE Roomba")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(True)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    log.info("KDE Roomba %s, Qt %s, platform %s, sessie %s/%s", __version__,
             __import__("PyQt6.QtCore", fromlist=["QT_VERSION_STR"]).QT_VERSION_STR,
             app.platformName(), os.environ.get("XDG_SESSION_TYPE", "?"),
             os.environ.get("XDG_CURRENT_DESKTOP", "?"))

    # Fouten tijdens het draaien: loggen + één melding, niet crashen.
    shown = {"n": 0}

    def excepthook(etype, value, tb):
        log.error("Onverwachte fout:\n%s", "".join(traceback.format_exception(etype, value, tb)))
        if shown["n"] == 0:
            notify("KDE Roomba: er ging iets mis", f"{value}\nZie {logfile}")
        shown["n"] += 1

    sys.excepthook = excepthook

    # Maar één roomba tegelijk.
    lock = QLockFile(str(state_dir() / "roomba.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(200):
        log.info("Er draait al een KDE Roomba.")
        notify("KDE Roomba draait al", "Hij staat al op je bureaublad (rechtsklik → Afsluiten om te stoppen).")
        return 0

    # Een eerdere versie zette een KWin-vensterregel; die ruimen we op.
    try:
        if kwin.remove_rule_if_present():
            log.info("Oude KWin-vensterregel van KDE Roomba verwijderd.")
    except Exception as exc:  # noqa: BLE001
        log.warning("Opruimen oude KWin-regel mislukt: %s", exc)

    cfg = Config.load()
    screen = app.primaryScreen()
    geom = screen.availableGeometry()
    for i, sc in enumerate(app.screens()):
        g = sc.geometry()
        log.info("Scherm %d: %s %s %s %dx%d op (%d,%d), schaal %.2f%s", i, sc.name(), sc.manufacturer(), sc.model(),
                 g.width(), g.height(), g.x(), g.y(), sc.devicePixelRatio(),
                 " (primair volgens Qt)" if sc == screen else "")

    w = RoombaWindow(cfg, geom)
    w.show()
    log.info("Venster getoond.")

    def report():
        h = w.windowHandle()
        log.info("Status na 3 s: zichtbaar=%s, blootgesteld=%s, scherm=%s, venster %dx%d, getekend=%s",
                 w.isVisible(), h.isExposed() if h else "?", h.screen().name() if h and h.screen() else "?",
                 w.width(), w.height(), getattr(w, "_painted_once", False))

    QTimer.singleShot(3000, report)
    if w.wayland and not w.layer_shell:
        w.say("Let op: layer-shell-qt niet beschikbaar,\nik draai als gewoon venster.", 6)

    def on_geom(_g=None):
        if w.layer_shell:
            return  # de compositor regelt de grootte
        g = screen.availableGeometry()
        if g != w.geom:
            w.setGeometry(g)

    screen.availableGeometryChanged.connect(on_geom)
    app.aboutToQuit.connect(w.stop_worker)
    rc = app.exec()
    lock.unlock()
    return rc
