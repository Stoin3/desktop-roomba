"""Opruimen van de KWin-vensterregel die een eerdere versie aanmaakte.

KDE Roomba wijzigt je KDE-instellingen niet (meer). Versie 1.0.0 schreef een
vensterregel in ~/.config/kwinrulesrc (groep ``kde-roomba-overlay``). Deze
module haalt die – en alleen die – weer weg als hij er nog staat.
"""

from __future__ import annotations

import shutil
import subprocess

GROUP = "kde-roomba-overlay"
_KEYS = (
    "Description wmclass wmclassmatch wmclasscomplete position positionrule size sizerule below belowrule "
    "above aboverule skiptaskbar skiptaskbarrule skippager skippagerrule skipswitcher skipswitcherrule "
    "acceptfocus acceptfocusrule noborder noborderrule desktops desktopsrule"
).split()


def _tool(*names: str) -> str | None:
    return next((n for n in names if shutil.which(n)), None)


def _read(tool: str, group: str, key: str) -> str:
    out = subprocess.run([tool, "--file", "kwinrulesrc", "--group", group, "--key", key],
                         capture_output=True, text=True, timeout=5)
    return out.stdout.strip()


def remove_rule_if_present() -> bool:
    """Geeft True als er een oude regel is verwijderd."""
    rd, wr = _tool("kreadconfig6", "kreadconfig5"), _tool("kwriteconfig6", "kwriteconfig5")
    if not rd or not wr:
        return False
    rules = [r for r in _read(rd, "General", "rules").split(",") if r]
    has_group = bool(_read(rd, GROUP, "wmclass"))
    if GROUP not in rules and not has_group:
        return False

    rest = [r for r in rules if r != GROUP]
    run = lambda *a: subprocess.run([wr, "--file", "kwinrulesrc", *a], capture_output=True, timeout=5)  # noqa: E731
    run("--group", "General", "--key", "rules", ",".join(rest))
    run("--group", "General", "--key", "count", str(len(rest)))
    for k in _KEYS:
        run("--group", GROUP, "--key", k, "--delete")
    if shutil.which("dbus-send"):
        subprocess.run(["dbus-send", "--session", "--type=method_call", "--dest=org.kde.KWin", "/KWin",
                        "org.kde.KWin.reconfigure"], capture_output=True, timeout=5)
    return True
