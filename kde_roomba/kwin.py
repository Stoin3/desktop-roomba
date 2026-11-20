"""Opruimen van de KWin-vensterregel die versie 1.0.0 aanmaakte.

KDE Roomba wijzigt je KDE-instellingen niet (meer). Versie 1.0.0 schreef een
vensterregel in ~/.config/kwinrulesrc (groep ``kde-roomba-overlay``) die o.a.
"geen titelbalk en rand" afdwong. Blijft daar een restant van over zonder
vensterklasse, dan geldt die regel voor ÁLLE vensters (titelbalken weg).

Deze module verwijdert:
* de groep ``kde-roomba-overlay``,
* elke regel met omschrijving "KDE Roomba ...",
* restanten van onze regel: regels zonder venster-/titelmatch waarvan alle
  sleutels uit onze set komen (een door jezelf gemaakte regel heeft altijd
  een omschrijving of andere sleutels en blijft dus staan).

Gebruik vanaf de terminal:  python3 -m kde_roomba.kwin   (toont en herstelt)
"""

from __future__ import annotations

import configparser
import os
import shutil
import subprocess
import sys
from pathlib import Path

GROUP = "kde-roomba-overlay"
_KEYS = set(
    "Description wmclass wmclassmatch wmclasscomplete position positionrule size sizerule below belowrule "
    "above aboverule skiptaskbar skiptaskbarrule skippager skippagerrule skipswitcher skipswitcherrule "
    "acceptfocus acceptfocusrule noborder noborderrule desktops desktopsrule".split()
)
_MATCH_KEYS = {"wmclass", "title", "windowrole", "clientmachine", "types"}


def _rules_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "kwinrulesrc"


def _tool(*names: str) -> str | None:
    return next((n for n in names if shutil.which(n)), None)


def _parse() -> configparser.RawConfigParser:
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str  # type: ignore[assignment]
    try:
        cp.read(_rules_file(), encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        pass
    return cp


def _is_ours(cp: configparser.RawConfigParser, group: str) -> bool:
    if group == GROUP:
        return True
    keys = set(cp.options(group)) if cp.has_section(group) else set()
    if not keys:
        return False
    desc = cp.get(group, "Description", fallback="")
    if desc.startswith("KDE Roomba"):
        return True
    has_match = any(cp.get(group, k, fallback="").strip() for k in _MATCH_KEYS)
    # restant: geen omschrijving, geen vensterklasse/titel, alleen onze sleutels
    return not desc and not has_match and keys <= _KEYS


def find_problems() -> list[str]:
    """Regels die er niet horen (van ons) – voor weergave."""
    cp = _parse()
    rules = [r for r in cp.get("General", "rules", fallback="").split(",") if r]
    groups = set(rules) | {s for s in cp.sections() if s != "General"}
    return sorted(g for g in groups if _is_ours(cp, g))


def noborder_rules() -> list[tuple[str, str, str]]:
    """Alle actieve regels die titelbalken weghalen: (groep, omschrijving, venster)."""
    cp = _parse()
    rules = [r for r in cp.get("General", "rules", fallback="").split(",") if r]
    out = []
    for g in rules:
        if cp.has_section(g) and cp.get(g, "noborder", fallback="").lower() == "true":
            out.append((g, cp.get(g, "Description", fallback="(geen omschrijving)"),
                        cp.get(g, "wmclass", fallback="") or "ALLE vensters"))
    return out


def remove_rule_if_present() -> bool:
    """Verwijdert onze (restant-)regels. Geeft True als er iets is weggehaald."""
    wr = _tool("kwriteconfig6", "kwriteconfig5")
    if not wr:
        return False
    cp = _parse()
    ours = find_problems()
    if not ours:
        return False
    rules = [r for r in cp.get("General", "rules", fallback="").split(",") if r]
    rest = [r for r in rules if r not in ours]

    def run(*a: str) -> None:
        subprocess.run([wr, "--file", "kwinrulesrc", *a], capture_output=True, timeout=5)

    # eerst uit de lijst halen (dan doet KWin er niets meer mee), dan leegmaken
    run("--group", "General", "--key", "rules", ",".join(rest))
    run("--group", "General", "--key", "count", str(len(rest)))
    for g in ours:
        keys = set(cp.options(g)) if cp.has_section(g) else set()
        for k in sorted(keys | _KEYS):
            run("--group", g, "--key", k, "--delete")
    if shutil.which("dbus-send"):
        subprocess.run(["dbus-send", "--session", "--type=method_call", "--dest=org.kde.KWin", "/KWin",
                        "org.kde.KWin.reconfigure"], capture_output=True, timeout=5)
    return True


def main() -> int:
    print(f"KWin-vensterregels: {_rules_file()}")
    nb = noborder_rules()
    if nb:
        print("Regels die de titelbalk weghalen:")
        for g, desc, win in nb:
            print(f"  - [{g}] {desc} → {win}")
    else:
        print("Geen enkele regel haalt titelbalken weg.")
    ours = find_problems()
    if not ours:
        print("Geen regels van KDE Roomba gevonden.")
        if nb:
            print("De regel(s) hierboven zijn niet van KDE Roomba. Verwijderen kan via\n"
                  "Systeeminstellingen → Vensterbeheer → Vensterregels.")
        return 0
    print("Van KDE Roomba (wordt verwijderd): " + ", ".join(ours))
    if remove_rule_if_present():
        print("Verwijderd en KWin opnieuw geladen. Nieuwe vensters hebben weer een titelbalk;")
        print("bestaande vensters krijgen hem terug na sluiten en opnieuw openen.")
    else:
        print("Kon niet verwijderen (kwriteconfig6 ontbreekt?). Gebruik Systeeminstellingen → Vensterregels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
