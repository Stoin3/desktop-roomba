import os
import time
from pathlib import Path

from kde_roomba import brain
from kde_roomba.config import Config


def make(tmp: Path, name: str, content: bytes | None = b"x", age_days: float = 40):
    p = tmp / name
    if content is None:
        p.mkdir()
    else:
        p.write_bytes(content)
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return p


def verdicts(tmp, cfg=None):
    cfg = cfg or Config()
    cfg.use_ai = False
    items = brain.scan_desktop(cfg, tmp)
    v, method = brain.classify(cfg, items)
    return {x.info.name: x for x in v}, {i.name: i for i in items}, method


def test_obvious_junk_is_trashed(tmp_path):
    for n in ("a.part", "b.crdownload", "leeg.txt", "x.tmp", "core.dmp"):
        make(tmp_path, n, b"" if n == "leeg.txt" else b"data")
    v, _, method = verdicts(tmp_path)
    assert method == "heuristiek"
    assert all(v[n].trash for n in v), {n: (x.trash, x.reason) for n, x in v.items()}


def test_useful_files_are_kept(tmp_path):
    make(tmp_path, "Scriptie hoofdstuk 3.pdf", b"%PDF" * 1000)
    make(tmp_path, "notities.txt", b"belangrijke dingen")
    make(tmp_path, "foto.jpg", b"\xff\xd8" * 500)
    v, _, _ = verdicts(tmp_path)
    assert not any(x.trash for x in v.values())


def test_protection_rules(tmp_path):
    make(tmp_path, "Map", None)
    make(tmp_path, "firefox.desktop", b"")
    make(tmp_path, "nieuw.tmp", b"x", age_days=0.01)  # te nieuw
    make(tmp_path, ".verborgen.tmp", b"x")
    v, items, _ = verdicts(tmp_path)
    assert v == {}
    assert items["Map"].protected_reason == "map"
    assert items["nieuw.tmp"].protected_reason == "te nieuw"
    assert ".verborgen.tmp" not in items


def test_max_files_per_run(tmp_path):
    for i in range(10):
        make(tmp_path, f"f{i}.tmp")
    cfg = Config()
    cfg.max_files_per_run = 3
    v, _, _ = verdicts(tmp_path, cfg)
    assert len(brain.choose_trash(cfg, list(v.values()))) == 3


def test_ai_result_used_when_available(tmp_path, monkeypatch):
    make(tmp_path, "rapport (1).pdf", b"%PDF")
    make(tmp_path, "x.tmp")
    cfg = Config()
    monkeypatch.setattr(brain, "ollama_available", lambda c: True)
    monkeypatch.setattr(brain, "ai_classify_batch",
                        lambda c, b: {"rapport (1).pdf": (True, "dubbele download")})
    items = brain.scan_desktop(cfg, tmp_path)
    v, method = brain.classify(cfg, items)
    by = {x.info.name: x for x in v}
    assert method.startswith("AI")
    assert by["rapport (1).pdf"].trash and by["rapport (1).pdf"].source == "ai"
    # niet door AI beantwoord -> heuristiek
    assert by["x.tmp"].source == "heuristiek" and by["x.tmp"].trash
