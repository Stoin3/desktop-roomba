"""Echte eind-tot-eindtest op Windows (GitHub Actions, windows-latest).

1. Maakt een map met afval + nuttige bestanden en opent die in Verkenner.
2. Controleert dat de Shell-code (IFolderView) de bestanden en posities ziet.
3. Start de roomba, sleept hem met de echte muis naar het Verkenner-venster.
4. Controleert dat het afval in de prullenbak is en de rest er nog is.
Schermafbeeldingen en het log komen in e2e-out/.
"""

import ctypes
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "e2e-out"
OUT.mkdir(exist_ok=True)
user32 = ctypes.windll.user32
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2, net als Qt


def shot(name: str) -> None:
    ImageGrab.grab(all_screens=True).save(OUT / f"{name}.png")
    print("schermafbeelding:", name, flush=True)


def mouse_to(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))


def drag(x0, y0, x1, y1, steps=40) -> None:
    mouse_to(x0, y0); time.sleep(0.3)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # links omlaag
    for k in range(1, steps + 1):
        mouse_to(x0 + (x1 - x0) * k / steps, y0 + (y1 - y0) * k / steps)
        time.sleep(0.03)
        if k == 8:
            shot("2-slepen")
    time.sleep(0.3)
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # links omhoog


def main() -> int:
    folder = Path("C:/roomba-test/Rommel")
    folder.mkdir(parents=True, exist_ok=True)
    junk = {"leeg.txt": b"", "asdfgh.html": b"<html></html>", "download.part": b"x" * 100, "kjhkjhkjh.txt": b"x"}
    keep = {"verslag.txt": "Belangrijk verslag over het project met echte inhoud en conclusies.",
            "boodschappen.txt": "Boodschappen: melk, brood, kaas en eieren voor zaterdag."}
    for n, c in junk.items():
        (folder / n).write_bytes(c)
    for n, c in keep.items():
        (folder / n).write_text(c)
    old = time.time() - 3600
    for f in folder.iterdir():
        os.utime(f, (old, old))

    # Zoals een echt bureaublad: andere vensters (o.a. de runner-console) weg,
    # zodat de roomba rechtsonder zichtbaar is.
    import comtypes.client
    comtypes.client.CreateObject("Shell.Application").MinimizeAll()
    time.sleep(1.5)
    subprocess.Popen(["explorer.exe", str(folder)])
    time.sleep(5)

    # --- 2. ziet de Shell-code het Verkenner-venster en de posities? ------------
    diag = subprocess.run([sys.executable, "-m", "kde_roomba.windows_shell"], cwd=ROOT, capture_output=True,
                          text=True, timeout=60)
    print(diag.stdout, diag.stderr[-2000:], flush=True)
    (OUT / "diagnose.txt").write_text(diag.stdout + "\n" + diag.stderr)
    sys.path.insert(0, str(ROOT))
    from kde_roomba import windows_shell as ws

    views = [v for v in ws.explorer_views() if Path(v.folder) == folder]
    assert views, "Verkenner-venster met de testmap niet gevonden via IShellWindows"
    view = views[0]
    # Verkenner linksboven zetten (niet over het laadstation rechtsonder)
    user32.SetWindowPos(view.top_hwnd, 0, 20, 20, 640, 460, 0x0040)  # SWP_SHOWWINDOW
    time.sleep(1.5)
    view = [v for v in ws.explorer_views() if Path(v.folder) == folder][0]
    missing = set(junk) | set(keep)
    missing -= set(view.items)
    assert not missing, f"Bestanden niet gezien in IFolderView: {missing}"
    print("Verkenner gezien:", view.view_rect, {k: tuple(map(int, v)) for k, v in view.items.items()}, flush=True)
    shot("1-verkenner")

    # --- 3. roomba starten ------------------------------------------------------
    state = Path(os.environ["LOCALAPPDATA"]) / "kde-roomba"
    cfgdir = Path(os.environ["APPDATA"]) / "kde-roomba"
    cfgdir.mkdir(parents=True, exist_ok=True)
    (cfgdir / "config.json").write_text('{"use_ai": false, "outfit": "kat"}')
    log = state / "roomba.log"
    if log.exists():
        log.unlink()
    proc = subprocess.Popen([sys.executable, "-m", "kde_roomba"], cwd=ROOT)
    for _ in range(40):
        time.sleep(0.5)
        if log.exists() and "Status na 3 s" in log.read_text(errors="replace"):
            break
    text = log.read_text(errors="replace")
    print(text, flush=True)
    m = re.search(r"overlay \S+ op \((-?\d+),(-?\d+)\) (\d+)x(\d+), schaal ([\d.]+)", text)
    r = re.search(r"roomba op \((\d+), (\d+)\)", text)
    assert m and r, "overlay/roomba-positie niet in het log"
    ox, oy, scale = int(m.group(1)), int(m.group(2)), float(m.group(5))
    rx, ry = (ox + int(r.group(1))) * scale, (oy + int(r.group(2))) * scale
    time.sleep(1)
    shot("0-roomba")

    # --- 4. slepen naar het Verkenner-venster ------------------------------------
    vx, vy, vw, vh = view.view_rect
    drag(rx, ry, vx + vw // 2, vy + vh // 2)
    for k in range(30):
        time.sleep(1)
        if k in (4, 8):
            shot(f"3-rijden-{k}")
        left = {f.name for f in folder.iterdir()}
        if not (set(junk) & left) and "opgeruimd" in log.read_text(errors="replace"):
            break
    time.sleep(2)
    shot("4-klaar")
    left = {f.name for f in folder.iterdir()}
    text = log.read_text(errors="replace")
    (OUT / "roomba.log").write_text(text)
    subprocess.run([sys.executable, "-m", "kde_roomba", "--quit"], cwd=ROOT, timeout=30)
    proc.wait(timeout=20)
    print("Over in de map:", sorted(left), flush=True)
    assert not (set(junk) & left), f"Afval niet opgeruimd: {set(junk) & left}"
    assert set(keep) <= left, f"Nuttige bestanden weg: {set(keep) - left}"
    assert "Verkenner-venster:" in text, "roomba reed niet door het Verkenner-venster"
    print("WINDOWS E2E OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
