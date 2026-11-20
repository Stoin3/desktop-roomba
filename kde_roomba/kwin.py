"""KWin-vensterregel voor de roomba-overlay.

Onder Wayland mag een programma zijn eigen venster niet positioneren of
'onder alle vensters' zetten. Een KWin-regel kan dat wel. Deze module
schrijft (idempotent) een regel in ~/.config/kwinrulesrc die het
roomba-venster:

* op de juiste positie en grootte forceert (het hele bureaublad),
* altijd ONDER gewone vensters houdt (maar boven het bureaublad),
* uit de taakbalk / pager / alt-tab houdt,
* nooit focus laat pakken en geen rand geeft.
"""

from __future__ import annotations

import shutil
import subprocess

from . import APP_ID

GROUP = "kde-roomba-overlay"


def _tool(*names: str) -> str | None:
    for n in names:
        if shutil.which(n):
            return n
    return None


def _read(key: str, group: str) -> str:
    tool = _tool("kreadconfig6", "kreadconfig5")
    if not tool:
        return ""
    out = subprocess.run([tool, "--file", "kwinrulesrc", "--group", group, "--key", key], capture_output=True, text=True)
    return out.stdout.strip()


def _write(group: str, values: dict[str, str]) -> bool:
    tool = _tool("kwriteconfig6", "kwriteconfig5")
    if not tool:
        return False
    for k, v in values.items():
        args = [tool, "--file", "kwinrulesrc", "--group", group, "--key", k]
        if v in ("true", "false"):
            args += ["--type", "bool"]
        subprocess.run(args + [v], check=False)
    return True


def _reconfigure() -> None:
    if shutil.which("dbus-send"):
        subprocess.run(
            ["dbus-send", "--session", "--type=method_call", "--dest=org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"],
            check=False,
            capture_output=True,
        )


def _desired(x: int, y: int, w: int, h: int) -> dict[str, str]:
    return {
        "Description": "KDE Roomba (automatisch)",
        "wmclass": APP_ID,
        "wmclassmatch": "1",
        "wmclasscomplete": "false",
        "position": f"{x},{y}",
        "positionrule": "2",
        "size": f"{w},{h}",
        "sizerule": "2",
        "below": "true",
        "belowrule": "2",
        "above": "false",
        "aboverule": "2",
        "skiptaskbar": "true",
        "skiptaskbarrule": "2",
        "skippager": "true",
        "skippagerrule": "2",
        "skipswitcher": "true",
        "skipswitcherrule": "2",
        "acceptfocus": "false",
        "acceptfocusrule": "2",
        "noborder": "true",
        "noborderrule": "2",
        "desktops": "",
        "desktopsrule": "2",
    }


def ensure_rule(x: int, y: int, w: int, h: int) -> bool:
    """Maakt/actualiseert de regel. Geeft True als KWin herladen is."""
    desired = _desired(x, y, w, h)
    if not _tool("kwriteconfig6", "kwriteconfig5"):
        return False

    changed = any(_read(k, GROUP) != v for k, v in desired.items() if v not in ("true", "false"))
    changed = changed or _read("below", GROUP) != "true"

    rules = [r for r in _read("rules", "General").split(",") if r]
    if GROUP not in rules:
        rules.append(GROUP)
        _write("General", {"rules": ",".join(rules), "count": str(len(rules))})
        changed = True

    if changed:
        _write(GROUP, desired)
        _reconfigure()
    return changed


def remove_rule() -> None:
    rules = [r for r in _read("rules", "General").split(",") if r and r != GROUP]
    _write("General", {"rules": ",".join(rules), "count": str(len(rules))})
    tool = _tool("kwriteconfig6", "kwriteconfig5")
    if tool:
        for k in _desired(0, 0, 0, 0):
            subprocess.run([tool, "--file", "kwinrulesrc", "--group", GROUP, "--key", k, "--delete"], check=False)
    _reconfigure()
