"""Maakt een roomba-icoon (.ico/.png) voor snelkoppelingen en de .exe.

    python -m kde_roomba.make_icon roomba.ico
"""

import os
import sys


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication, QImage, QPainter

    app = QGuiApplication(sys.argv[:1])  # noqa: F841
    from kde_roomba import art

    out = sys.argv[1] if len(sys.argv) > 1 else "roomba.ico"
    img = QImage(256, 256, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(128, 128)
    p.rotate(-90)
    art.draw_roomba(p, 100, "charging", 1.0, 30, 0.0, 0.0)
    p.end()
    ok = img.save(out)
    print(("Icoon opgeslagen: " if ok else "Opslaan mislukt: ") + out)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
