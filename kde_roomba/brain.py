"""Het brein van de roomba: bepaalt welke bureaubladbestanden afval zijn.

Werkwijze
---------
1. Alle items op het bureaublad worden verzameld met metadata
   (naam, extensie, grootte, leeftijd, mimetype, stukje tekst).
2. Harde veiligheidsregels sluiten items uit (mappen, .desktop-snelkoppelingen,
   te jonge bestanden, beschermde extensies ...). Die gaan NOOIT naar de AI.
3. Een heuristiek geeft elk bestand een 'afvalscore' + hints.
4. Een klein lokaal taalmodel (via Ollama) beslist per bestand of het afval is.
   Is Ollama niet bereikbaar, dan valt hij terug op de heuristiek.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config

DAY = 86400.0


@dataclass
class FileInfo:
    path: Path
    name: str
    ext: str
    is_dir: bool
    size: int
    age_days: float
    mime: str
    snippet: str = ""
    meaningful_chars: int | None = None  # letters/cijfers aan echte tekst (alleen tekstbestanden)
    score: float = 0.0
    hints: list[str] = field(default_factory=list)
    protected_reason: str | None = None

    def for_ai(self) -> dict:
        d = {
            "name": self.name,
            "type": "folder" if self.is_dir else (self.mime or "unknown"),
            "size": human_size(self.size),
            "age_days": round(self.age_days, 1),
        }
        if self.hints:
            d["hints"] = self.hints
        if self.snippet:
            d["content_start"] = self.snippet
        return d


@dataclass
class Verdict:
    info: FileInfo
    trash: bool
    reason: str
    source: str  # "ai" of "heuristiek"


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def desktop_dir() -> Path:
    try:
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=3)
        p = out.stdout.strip()
        if p and Path(p).is_dir():
            return Path(p)
    except (OSError, subprocess.SubprocessError):
        pass
    for cand in ("~/Desktop", "~/Bureaublad"):
        p = Path(cand).expanduser()
        if p.is_dir():
            return p
    return Path("~/Desktop").expanduser()


# --------------------------------------------------------------------------
# Scannen
# --------------------------------------------------------------------------

TEXT_EXTS = {".txt", ".log", ".md", ".csv", ".json", ".xml", ".ini", ".cfg", ".conf", ".yaml", ".yml", ".sh", ".py"}


MARKUP_EXTS = {".html", ".htm", ".xml", ".svg", ".xhtml"}


def _meaningful_chars(path: Path, mime: str) -> int | None:
    """Hoeveel echte tekst (letters/cijfers) zit er in een tekstbestand? Tags,
    witruimte en leestekens tellen niet mee. None = geen tekstbestand."""
    ext = path.suffix.lower()
    if not (mime.startswith("text/") or ext in TEXT_EXTS or ext in MARKUP_EXTS):
        return None
    try:
        with path.open("rb") as fh:
            raw = fh.read(65536)
    except OSError:
        return None
    txt = raw.decode("utf-8", errors="replace")
    if ext in MARKUP_EXTS or "html" in mime or "xml" in mime:
        txt = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", txt)
        txt = re.sub(r"(?s)<!--.*?-->", " ", txt)
        txt = re.sub(r"(?s)<[^>]*>", " ", txt)
        txt = re.sub(r"&[a-zA-Z#0-9]+;", " ", txt)
    return len(re.findall(r"\w", txt))


def _snippet(path: Path, mime: str) -> str:
    if not (mime.startswith("text/") or path.suffix.lower() in TEXT_EXTS):
        return ""
    try:
        with path.open("rb") as fh:
            raw = fh.read(300)
        txt = raw.decode("utf-8", errors="replace")
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt[:200]
    except OSError:
        return ""


def scan_desktop(cfg: Config, folder: Path | None = None) -> list[FileInfo]:
    folder = folder or desktop_dir()
    now = time.time()
    items: list[FileInfo] = []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return items
    for e in entries:
        if e.name.startswith("."):
            continue
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        is_dir = e.is_dir(follow_symlinks=False)
        p = Path(e.path)
        ext = p.suffix.lower() if not is_dir else ""
        mime = "inode/directory" if is_dir else (mimetypes.guess_type(e.name)[0] or "")
        info = FileInfo(
            path=p,
            name=e.name,
            ext=ext,
            is_dir=is_dir,
            size=st.st_size if not is_dir else 0,
            age_days=max(0.0, (now - max(st.st_mtime, st.st_ctime if is_dir else st.st_mtime)) / DAY),
            mime=mime,
        )
        info.snippet = "" if is_dir else _snippet(p, mime)
        info.meaningful_chars = None if is_dir else _meaningful_chars(p, mime)
        info.protected_reason = protection(info, cfg)
        score_file(info)
        items.append(info)
    return items


# --------------------------------------------------------------------------
# Veiligheid
# --------------------------------------------------------------------------

def protection(info: FileInfo, cfg: Config) -> str | None:
    if info.is_dir and not cfg.allow_folders:
        return "map"
    if info.path.is_symlink():
        return "snelkoppeling"
    if info.ext in {e.lower() for e in cfg.protected_extensions}:
        return f"beschermde extensie {info.ext}"
    if info.age_days * 24 < cfg.min_age_hours:
        return "te nieuw"
    return None


# --------------------------------------------------------------------------
# Heuristiek
# --------------------------------------------------------------------------

JUNK_EXTS = {
    ".tmp": (0.9, "tijdelijk bestand"),
    ".temp": (0.9, "tijdelijk bestand"),
    ".part": (0.95, "onvolledige download"),
    ".crdownload": (0.95, "onvolledige download"),
    ".download": (0.9, "onvolledige download"),
    ".partial": (0.95, "onvolledige download"),
    ".bak": (0.6, "back-upbestand"),
    ".old": (0.6, "oud bestand"),
    ".swp": (0.85, "editor-swapbestand"),
    ".log": (0.55, "logbestand"),
    ".dmp": (0.8, "crashdump"),
    ".torrent": (0.6, "torrentbestand"),
    ".exe": (0.55, "Windows-installer"),
    ".msi": (0.6, "Windows-installer"),
    ".rpm": (0.5, "installatiepakket"),
    ".deb": (0.6, "installatiepakket"),
    ".pyc": (0.9, "gecompileerd python-bestand"),
}

INSTALLER_EXTS = {".rpm", ".deb", ".appimage", ".flatpakref", ".exe", ".msi", ".dmg", ".iso"}

JUNK_NAME_PATTERNS = [
    (re.compile(r"^(untitled|naamloos|nieuw(e)? (tekst)?(document|bestand)|new (text )?document)", re.I), 0.5, "naamloos bestand"),
    (re.compile(r"\((\d+)\)(\.[^.]+)?$"), 0.35, "lijkt een dubbele download"),
    (re.compile(r"(^|[ _-])(copy|kopie)( of| van)?([ _-]|$)", re.I), 0.35, "lijkt een kopie"),
    (re.compile(r"^(screenshot|schermafdruk|schermafbeelding|spectacle)", re.I), 0.2, "schermafdruk"),
    (re.compile(r"^(test|temp|tmp|asdf|foo|bla|xxx)\d*([._ -]|$)", re.I), 0.45, "testbestand"),
    (re.compile(r"~$"), 0.8, "editor-back-up"),
    (re.compile(r"^~\$"), 0.9, "Office-lockbestand"),
    (re.compile(r"^\.~lock\."), 0.9, "lockbestand"),
]


KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
KEYBOARD_CLASSICS = ("asdf", "fdsa", "qwer", "zxcv", "hjkl", "jkl")
VOWELS = set("aeiouy")


def looks_like_gibberish(stem: str) -> bool:
    """Herkent ingetypte onzin zoals 'liuhliuhliuh', 'asdfgh' of 'kjhkjhkjh'."""
    s = stem.lower()
    letters = re.sub(r"[^a-z]", "", s)
    if len(letters) < 4 or len(letters) < len(s) * 0.8:
        return False  # te kort, of veel cijfers/spaties/leestekens (echte namen)

    # toetsenbordgeklop: asdf, 5 opeenvolgende toetsen van één rij (qwert, lkjhg)
    if any(k in letters for k in KEYBOARD_CLASSICS if len(k) >= 4) or letters in KEYBOARD_CLASSICS:
        return True
    for row in KEYBOARD_ROWS:
        for i in range(len(row) - 4):
            chunk = row[i:i + 5]
            if chunk in letters or chunk[::-1] in letters:
                return True

    # het grootste deel van de naam is een herhaald stukje: 'liuhliuh', 'kjhkjhkjh'
    n_len = len(letters)
    for n in range(2, 7):
        for i in range(0, n_len - 2 * n + 1):
            unit, k = letters[i:i + n], 1
            while letters[i + k * n:i + (k + 1) * n] == unit:
                k += 1
            if k >= 2 and (n >= 3 or k >= 3) and k * n >= 0.6 * n_len:
                return True

    vowel_ratio = sum(c in VOWELS for c in letters) / n_len
    # heel weinig verschillende letters: 'liuhluihliuh'
    # (echte woorden met weinig letters hebben meestal dubbele letters: Mississippi)
    if n_len >= 8 and len(set(letters)) / n_len < 0.42 and not re.search(r"(.)\1", letters):
        return True
    # lange medeklinkerreeks zonder klinkers eromheen: 'sdfkjhg'
    if re.search(r"[^aeiouy]{6,}", letters) and vowel_ratio < 0.25:
        return True
    return False


def _or(a: float, b: float) -> float:
    """Combineer twee onafhankelijke 'afval-kansen'."""
    return 1.0 - (1.0 - a) * (1.0 - b)


def score_file(info: FileInfo) -> None:
    if info.is_dir:
        try:
            if not any(info.path.iterdir()):
                info.score, info.hints = 0.7, ["lege map"]
        except OSError:
            pass
        return
    score = 0.0
    hints: list[str] = []

    if info.ext in JUNK_EXTS:
        s, h = JUNK_EXTS[info.ext]
        score = max(score, s)
        hints.append(h)
    for rx, s, h in JUNK_NAME_PATTERNS:
        if rx.search(info.name):
            score = _or(score, s)
            hints.append(h)
    stem = info.name[: -len(info.ext)] if info.ext and info.name.endswith(info.ext) else info.name
    if looks_like_gibberish(stem):
        score = _or(score, 0.6)
        hints.append("naam lijkt willekeurig getypt")
        if info.size < 4096:
            score = _or(score, 0.4)
            hints.append("vrijwel geen inhoud")
    if info.size > 0 and info.meaningful_chars is not None:
        if info.meaningful_chars < 3:
            score = _or(score, 0.6)
            hints.append("geen tekst, alleen opmaak/witruimte")
        elif info.meaningful_chars < 40:
            words = re.findall(r"[^\W\d_]{4,}", re.sub(r"<[^>]*>", " ", info.snippet))
            if words and all(looks_like_gibberish(w) for w in words):
                score = _or(score, 0.6)
                hints.append("inhoud is willekeurig getypt")
    if info.size == 0:
        score = _or(score, 0.85)
        hints.append("leeg bestand (0 bytes)")
    if info.ext in INSTALLER_EXTS and info.age_days > 7:
        score = min(1.0, score + 0.2)
        hints.append(f"installer van {int(info.age_days)} dagen oud")
    if "schermafdruk" in hints and info.age_days > 30:
        score = min(1.0, score + 0.3)
        hints.append("oude schermafdruk")

    # Ouderdom verhoogt de kans dat iets vergeten afval is
    if score > 0:
        if info.age_days > 90:
            score = min(1.0, score + 0.15)
        elif info.age_days > 30:
            score = min(1.0, score + 0.08)

    info.score = round(score, 2)
    info.hints = list(dict.fromkeys(hints))


STRONG_JUNK = 0.75


def heuristic_verdict(info: FileInfo, threshold: float = 0.6) -> Verdict:
    trash = info.score >= threshold
    reason = ", ".join(info.hints) if info.hints else "ziet er nuttig uit"
    return Verdict(info, trash, reason, "heuristiek")


# --------------------------------------------------------------------------
# Lokale AI via Ollama
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """Je bent het brein van een robotstofzuiger die het bureaublad van een gebruiker opruimt.
Je krijgt een lijst bestanden met metadata. Bepaal per bestand of het AFVAL is: waarschijnlijk nutteloos,
tijdelijk, dubbel, onvolledig, leeg, of een vergeten download die niemand meer nodig heeft.

Regels:
- Wees VOORZICHTIG. Twijfel je, dan is het GEEN afval (trash=false).
- Persoonlijke documenten, foto's, projecten, notities met echte inhoud, scripts en archieven die werk lijken te bevatten zijn GEEN afval.
- Tijdelijke bestanden, onvolledige downloads (.part/.crdownload), lege bestanden, lockbestanden, editor-back-ups,
  dubbele downloads zoals "bestand (1).pdf", oude installers en oude schermafdrukken zijn meestal WEL afval.
- Bestanden met een willekeurig getypte naam (toetsenbordgeklop zoals "asdfgh", "liuhliuh", "kjhkjh")
  en zonder zinvolle inhoud zijn WEL afval.
- 'hints' komen van een eenvoudige heuristiek en zijn slechts een indicatie.
- Geef voor ELK bestand precies één resultaat, met exact dezelfde naam.
- 'reason' is een korte Nederlandse uitleg (max 10 woorden).
Antwoord uitsluitend met JSON."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "trash": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["name", "trash", "reason"],
            },
        }
    },
    "required": ["files"],
}


class AIUnavailable(Exception):
    pass


def _post_json(url: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def ollama_status(cfg: Config) -> tuple[bool, str]:
    """(bruikbaar, uitleg). Start Ollama zelf als het geïnstalleerd is maar niet draait."""
    url = cfg.ollama_url.rstrip("/") + "/api/tags"

    def tags():
        with urllib.request.urlopen(url, timeout=2) as resp:
            return json.loads(resp.read().decode())

    try:
        data = tags()
    except (OSError, ValueError, urllib.error.URLError):
        if not shutil.which("ollama"):
            return False, "Ollama is niet geïnstalleerd"
        logging.getLogger("kde-roomba").info("Ollama draait niet; ik start 'ollama serve'.")
        try:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, start_new_session=True)
        except OSError as exc:
            return False, f"Ollama starten mislukt: {exc}"
        data = None
        for _ in range(30):
            time.sleep(0.5)
            try:
                data = tags()
                break
            except (OSError, ValueError, urllib.error.URLError):
                continue
        if data is None:
            return False, "Ollama reageert niet"
    names = {m.get("name", "") for m in data.get("models", [])}
    want = cfg.model if ":" in cfg.model else cfg.model + ":latest"
    if want in names or cfg.model in names:
        return True, "ok"
    return False, f"model {cfg.model} ontbreekt (ollama pull {cfg.model})"


def ollama_available(cfg: Config) -> bool:
    return ollama_status(cfg)[0]


def ai_classify_batch(cfg: Config, batch: list[FileInfo]) -> dict[str, tuple[bool, str]]:
    user = "Bestanden op het bureaublad:\n" + json.dumps([f.for_ai() for f in batch], ensure_ascii=False, indent=1)
    payload = {
        "model": cfg.model,
        "stream": False,
        "format": RESPONSE_SCHEMA,
        "options": {"temperature": 0, "num_ctx": 4096},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
    }
    try:
        data = _post_json(cfg.ollama_url.rstrip("/") + "/api/chat", payload, cfg.ai_timeout_s)
        content = data["message"]["content"]
        parsed = json.loads(content)
    except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
        raise AIUnavailable(str(exc)) from exc

    results: dict[str, tuple[bool, str]] = {}
    for item in parsed.get("files", []):
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            results[item["name"]] = (bool(item.get("trash")), str(item.get("reason", ""))[:120])
    return results


def classify(cfg: Config, items: list[FileInfo], progress=None) -> tuple[list[Verdict], str]:
    """Geeft (verdicts, gebruikte_methode) terug. Alleen niet-beschermde items."""
    candidates = [i for i in items if i.protected_reason is None]
    verdicts: list[Verdict] = []
    method = "heuristiek"

    use_ai = False
    if cfg.use_ai and candidates:
        use_ai, why = ollama_status(cfg)
        if not use_ai:
            method = f"heuristiek – {why}"
            logging.getLogger("kde-roomba").warning("Geen AI: %s", why)
    if use_ai:
        method = f"AI ({cfg.model})"
        bs = max(1, int(cfg.ai_batch_size))
        for start in range(0, len(candidates), bs):
            batch = candidates[start : start + bs]
            if progress:
                progress(start, len(candidates))
            try:
                res = ai_classify_batch(cfg, batch)
            except AIUnavailable as exc:
                logging.getLogger("kde-roomba").warning("AI-fout, terugval op heuristiek: %s", exc)
                res = {}
                method = f"AI ({cfg.model}) + heuristiek"
            for info in batch:
                if info.name in res:
                    trash, reason = res[info.name]
                    # Vangnet: een bestand met hoge heuristische score dat de AI
                    # mist, of een AI-'ja' bij iets zonder enig signaal en met
                    # veel inhoud, wordt extra gecontroleerd.
                    if trash and info.score == 0 and info.size > 5 * 1024 * 1024:
                        trash, reason = False, "groot bestand zonder afvalsignalen"
                    # Een klein model twijfelt soms bij overduidelijk afval
                    # (leeg, onzinnaam, .part...). Sterke signalen winnen.
                    if not trash and info.score >= STRONG_JUNK:
                        trash, reason = True, ", ".join(info.hints) + " (sterke afvalsignalen)"
                    verdicts.append(Verdict(info, trash, reason or "afval volgens AI", "ai"))
                else:
                    verdicts.append(heuristic_verdict(info))
    else:
        verdicts = [heuristic_verdict(i) for i in candidates]

    if progress:
        progress(len(candidates), len(candidates))
    return verdicts, method


def choose_trash(cfg: Config, verdicts: list[Verdict]) -> list[Verdict]:
    picked = [v for v in verdicts if v.trash]
    picked.sort(key=lambda v: -v.info.score)
    return picked[: max(0, int(cfg.max_files_per_run))]


def log_action(line: str) -> None:
    from .config import state_dir

    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    with (d / "history.log").open("a", encoding="utf-8") as fh:
        fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line + "\n")
