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
    assert lay.fixed == {"a.txt": (0, 0), "b c.tmp": (4, 1)}  # rijen: (kolom=pos, rij=strook)
    pos = lay.positions([("a.txt", False), ("b c.tmp", False), ("new.txt", False)])
    assert pos["b c.tmp"][0] > pos["a.txt"][0]
    assert pos["b c.tmp"][1] > pos["a.txt"][1]
    # nieuw bestand krijgt een vrije cel (niet die van a.txt)
    assert pos["new.txt"] != pos["a.txt"]


def test_auto_layout_folders_first(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "APPLETSRC", tmp_path / "missing")
    lay = dl.DesktopLayout(Config(), 0, 0, 1280, 720)
    pos = lay.positions([("zzz.txt", False), ("Map", True), ("aaa.txt", False)])
    # Plasma-standaard is rijen (links→rechts)
    assert pos["Map"][0] < pos["aaa.txt"][0] < pos["zzz.txt"][0]
    assert pos["Map"][1] == pos["aaa.txt"][1] == pos["zzz.txt"][1]


def test_matches_plasma_grid_from_screenshot(tmp_path, monkeypatch):
    """Situatie van de gebruiker: 1920 breed, standaardinstellingen (rijen, 64px).
    Sober/Steam rij 0 kolom 2/3, html rij 3 kolom 0 → x ≈ 50/162/274, y ≈ 45/380."""
    rc = tmp_path / "appletsrc"
    rc.write_text(
        "[Containments][1]\nlastScreen=0\nplugin=org.kde.plasma.folder\n\n"
        "[Containments][1][General]\n"
        'positions={"1920x1080":["4"\\,"17"\\,"desktop:/org.vinegarhq.Sober.desktop"\\,"0"\\,"2"\\,'
        '"desktop:/steam.desktop"\\,"0"\\,"3"\\,"desktop:/liuhliuhliuh.html"\\,"3"\\,"0"]}\n'
    )
    monkeypatch.setattr(dl, "APPLETSRC", rc)
    lay = dl.DesktopLayout(Config(), 0, 0, 1920, 1036, grid_unit=18, screen_w=1920, screen_h=1080)
    assert lay.flow == "rows" and lay.cell_w == 112
    pos = lay.positions([("org.vinegarhq.Sober.desktop", False), ("steam.desktop", False),
                         ("liuhliuhliuh.html", False), ("liuhluihliuh.txt", False)])
    sx, sy = pos["steam.desktop"]
    hx, hy = pos["liuhliuhliuh.html"]
    assert abs(sx - 392) < 15 and abs(sy - 45) < 15
    assert abs(hx - 56) < 15 and abs(hy - 380) < 20
    # nieuw bestand zonder opgeslagen positie: eerste vrije cel (rij 0, kolom 0)
    assert pos["liuhluihliuh.txt"][1] < 100
