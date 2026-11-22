"""Configuratie: ~/.config/kde-roomba/config.json"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


IS_WINDOWS = os.name == "nt"


def config_dir() -> Path:
    if IS_WINDOWS and not os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ.get("APPDATA") or os.path.expanduser("~/AppData/Roaming")) / "kde-roomba"
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "kde-roomba"


def state_dir() -> Path:
    if IS_WINDOWS and not os.environ.get("XDG_STATE_HOME"):
        return Path(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")) / "kde-roomba"
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(base) / "kde-roomba"


@dataclass
class Config:
    config_version: int = 2

    # --- AI -------------------------------------------------------------
    # Ollama-server en (klein) model. Zet use_ai op false om alleen de
    # ingebouwde heuristiek te gebruiken.
    use_ai: bool = True
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:1.5b"
    ai_timeout_s: float = 90.0
    ai_batch_size: int = 8

    # --- Veiligheid -----------------------------------------------------
    # Bestanden die in de laatste paar minuten nog gewijzigd zijn (bijv. een
    # lopende download) worden overgeslagen. 0.05 uur = 3 minuten.
    min_age_hours: float = 0.05
    # Mappen worden standaard nooit weggegooid.
    allow_folders: bool = False
    # Extensies die nooit weggegooid worden.
    protected_extensions: list[str] = field(
        default_factory=lambda: [".desktop", ".lnk", ".url", ".kdbx", ".key", ".pem", ".gpg", ".odt", ".docx",
                                 ".xlsx", ".ods", ".pptx", ".ini"]
    )
    # Maximaal aantal bestanden per schoonmaakronde.
    max_files_per_run: int = 15
    # Alleen tonen wat hij zou doen, niets echt weggooien.
    dry_run: bool = False

    # --- Uiterlijk / positie --------------------------------------------
    # Op welk scherm (bijv. "HDMI-A-1"). Leeg = KDE's hoofdscherm.
    screen: str = ""
    # Uiterlijk: zie rechtsklik → Outfit (klassiek, wit, kat, panda, ...)
    outfit: str = "klassiek"
    roomba_size: int = 96
    speed_px_s: float = 260.0
    turn_deg_s: float = 260.0
    # Positie van het laadstation (midden), relatief t.o.v. het
    # bureaublad. null = automatisch rechtsonder.
    hub_x: int | None = None
    hub_y: int | None = None

    # --- Bureaublad-iconen (benadering van het Plasma-raster) ----------
    icon_cell_width: int = 0   # 0 = automatisch op basis van iconSize
    icon_cell_height: int = 0
    # Extra verschuiving (pixels) als de roomba er structureel naast zit.
    icon_offset_x: int = 0
    icon_offset_y: int = 0
    # Dolphin-venster (rondrijden in een map): breedte Plaatsen-paneel en
    # hoogte werkbalk in pixels; -1 = automatisch schatten.
    dolphin_panel_width: int = -1
    dolphin_toolbar_height: int = -1
    # Bij slepen naar een map echt door het Dolphin-venster rijden.
    drive_in_dolphin: bool = True

    # "auto" (= Plasma-instelling), "columns" (boven→onder) of "rows" (links→rechts)
    icon_flow: str = "auto"

    @classmethod
    def load(cls) -> "Config":
        path = config_dir() / "config.json"
        cfg = cls()
        if path.exists():
            try:
                data = json.loads(path.read_text())
                known = {f.name for f in fields(cls)}
                for k, v in data.items():
                    if k in known:
                        setattr(cfg, k, v)
                if int(data.get("config_version", 1)) < 2:
                    # v1 had een te strenge leeftijdsgrens van 2 uur
                    if data.get("min_age_hours") == 2.0:
                        cfg.min_age_hours = 0.05
                    cfg.config_version = 2
                    cfg.save()
            except (OSError, ValueError) as exc:
                print(f"[kde-roomba] Kon config niet lezen ({exc}), gebruik standaardwaarden.")
        else:
            cfg.save()
        return cfg

    def save(self) -> None:
        path = config_dir() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n")
