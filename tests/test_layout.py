from kde_roomba import desktop_layout as dl
from kde_roomba.config import Config


def test_parse_plasma6_positions(tmp_path, monkeypatch):
    rc = tmp_path / "appletsrc"
    rc.write_text(
        "[Containments][1]\nactivityId=abc\nlastScreen=0\nplugin=org.kde.plasma.folder\n\n"
        "[Containments][1][General]\niconSize=3\n"
        'positions={"1920x1080":["2","9","desktop:/a.txt","0","0","desktop:/b%20c.tmp","1","4"]}\n'
        "\n[Containments][2]\nplugin=org.kde.panel\n"
    )
    monkeypatch.setattr(dl, "APPLETSRC", rc)
    lay = dl.DesktopLayout(Config(), 0, 0, 1920, 1080)
    assert lay.fixed == {"a.txt": (0, 0), "b c.tmp": (1, 4)}
    pos = lay.positions([("a.txt", False), ("b c.tmp", False), ("new.txt", False)])
    assert pos["b c.tmp"][0] > pos["a.txt"][0]
    assert pos["b c.tmp"][1] > pos["a.txt"][1]
    # nieuw bestand krijgt een vrije cel (niet die van a.txt)
    assert pos["new.txt"] != pos["a.txt"]


def test_auto_layout_folders_first(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "APPLETSRC", tmp_path / "missing")
    lay = dl.DesktopLayout(Config(), 0, 0, 1280, 720)
    pos = lay.positions([("zzz.txt", False), ("Map", True), ("aaa.txt", False)])
    assert pos["Map"][1] < pos["aaa.txt"][1] < pos["zzz.txt"][1]
