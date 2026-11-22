"""Mag de roomba in deze map stofzuigen? (Linux en Windows)"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

_IS_WIN = os.name == "nt"


def _under(path: Path, base: str) -> bool:
    pl = str(path).lower().replace("\\", "/").rstrip("/")
    bl = base.lower().replace("\\", "/").rstrip("/")
    return bool(bl) and (pl == bl or pl.startswith(bl + "/"))


def resolve_folder(destination: str) -> tuple[Path | None, str]:
    """(map, uitleg) – map is None als het niet mag."""
    d = destination.strip()
    if d.startswith("file://"):
        d = urllib.parse.unquote(urllib.parse.urlparse(d).path)
        if _IS_WIN and len(d) > 2 and d[0] == "/" and d[2] == ":":
            d = d[1:]  # /C:/Users/... → C:/Users/...
    if "://" in d or d.startswith(("::", "shell:")):
        return None, "ik kan alleen in mappen op deze computer stofzuigen"
    p = Path(d)
    if not (p.is_absolute() or (_IS_WIN and len(d) > 2 and d[1] == ":")):
        return None, "ik kan alleen in mappen op deze computer stofzuigen"
    try:
        p = p.resolve()
    except OSError:
        pass
    if not p.is_dir():
        return None, "dat is geen map"
    home = Path.home().resolve()
    if p == home or p.parent == p:
        return None, "je hele thuismap of een hele schijf is me te groot – kies een map erin"
    if any(part.startswith(".") for part in p.parts):
        return None, "verborgen (systeem)mappen laat ik met rust"
    if _IS_WIN:
        if str(p).startswith("\\\\"):
            return None, "netwerkmappen laat ik met rust"
        blocked = [os.environ.get(k, "") for k in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)",
                                                   "ProgramData", "APPDATA", "LOCALAPPDATA")]
        if any(_under(p, b) for b in blocked):
            return None, "systeem- en programmamappen laat ik met rust"
    else:
        try:
            p.relative_to(home)
        except ValueError:
            if not (p.parts[:2] in (("/", "run"), ("/", "media"), ("/", "mnt")) or str(p).startswith("/tmp")):
                return None, "buiten je thuismap stofzuig ik niet"
    if not os.access(p, os.W_OK):
        return None, "daar mag ik niets weggooien (geen schrijfrechten)"
    return p, "ok"
