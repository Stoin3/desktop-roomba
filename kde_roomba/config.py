"""Configuratie: ~/.config/kde-roomba/config.json"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "kde-roomba"


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(base) / "kde-roomba"


@dataclass
class Config:
    # --- AI -------------------------------------------------------------
    # Ollama-server en (klein) model. Zet use_ai op false om alleen de
    # ingebouwde heuristiek te gebruiken.
    use_ai: bool = True
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:1.5b"
    ai_timeout_s: float = 90.0
    ai_batch_size: int = 8

    # --- Veiligheid -----------------------------------------------------
    # Bestanden jonger dan dit worden nooit weggegooid.
    min_age_hours: float = 2.0
    # Mappen worden standaard nooit weggegooid.
    allow_folders: bool = False
    # Extensies die nooit weggegooid worden.
    protected_extensions: list[str] = field(
        default_factory=lambda: [".desktop", ".kdbx", ".key", ".pem", ".gpg", ".odt", ".docx", ".xlsx", ".ods"]
    )
    # Maximaal aantal bestanden per schoonmaakronde.
    max_files_per_run: int = 15
    # Alleen tonen wat hij zou doen, niets echt weggooien.
    dry_run: bool = False

    # --- Uiterlijk / positie --------------------------------------------
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
    icon_margin_x: int = 8
    icon_margin_y: int = 8
    # "auto", "columns" (boven→onder) of "rows" (links→rechts)
    icon_flow: str = "auto"

    # --- Overig ----------------------------------------------------------
    manage_kwin_rule: bool = True

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
            except (OSError, ValueError) as exc:
                print(f"[kde-roomba] Kon config niet lezen ({exc}), gebruik standaardwaarden.")
        else:
            cfg.save()
        return cfg

    def save(self) -> None:
        path = config_dir() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n")
