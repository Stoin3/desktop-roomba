from pathlib import Path

from kde_roomba import kwin_windows
from kde_roomba.config import Config
from kde_roomba.dolphin_layout import DolphinLayout, Metrics


def test_matches_users_dolphin_screenshot(tmp_path, monkeypatch):
    """Dolphin-venster van de gebruiker: client (569,129) 1097x630, standaardinstellingen.
    Bestanden stonden op x ≈ 917 / 1054 / 1192 / 1330 / 1468, icoon-y ≈ 222."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    folder = tmp_path / "Desktop"
    folder.mkdir()
    for n in ("uihuijuhluhlu", "steam.desktop", "liuhluihliuh.txt", "org.vinegarhq.Sober.desktop", "liuhliuhliuh.html"):
        (folder / n).write_text("x")
    lay = DolphinLayout(Config(), folder, (569, 129, 1097, 630), Metrics(avg_char=9, line_spacing=20, font_height=19, grid_margin=3))
    pos = lay.positions()
    order = sorted(pos, key=lambda n: pos[n][0])
    assert order == ["liuhliuhliuh.html", "liuhluihliuh.txt", "org.vinegarhq.Sober.desktop", "steam.desktop", "uihuijuhluhlu"]
    for name, want_x in zip(order, (917, 1054, 1192, 1330, 1468)):
        assert abs(pos[name][0] - want_x) < 10, (name, pos[name])
        assert abs(pos[name][1] - 222) < 15, (name, pos[name])


def test_details_and_hidden_and_folders_first(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    props = data / "dolphin/view_properties/global"
    props.mkdir(parents=True)
    (props / ".directory").write_text("[Dolphin]\nViewMode=1\nPreviewsShown=false\n")
    folder = tmp_path / "map"
    (folder / "zmap").mkdir(parents=True)
    for n in ("b.txt", "a10.txt", "a2.txt", ".verborgen"):
        (folder / n).write_text("x")
    lay = DolphinLayout(Config(), folder, (0, 0, 1000, 600), Metrics())
    pos = lay.positions()
    assert ".verborgen" not in pos
    ys = sorted(pos, key=lambda n: pos[n][1])
    assert ys == ["zmap", "a2.txt", "a10.txt", "b.txt"]  # mappen eerst, natuurlijke sortering
    assert len({round(p[0]) for p in pos.values()}) == 1  # details: één kolom


def test_pick_dolphin_window_prefers_matching_caption():
    data = {"windows": [
        {"cls": "org.kde.dolphin", "caption": "Documenten — Dolphin", "active": True, "stack": 9},
        {"cls": "org.kde.dolphin", "caption": "Downloads — Dolphin", "active": False, "stack": 3},
        {"cls": "org.kde.konsole", "caption": "Downloads", "active": False, "stack": 10},
    ]}
    w = kwin_windows.pick_dolphin_window(data, Path("/home/x/Downloads"))
    assert w["caption"] == "Downloads — Dolphin"
    assert kwin_windows.pick_dolphin_window({"windows": []}, Path("/x")) is None


def test_kwin_script_runs_against_kwin_api(tmp_path):
    """Voert het KWin-script uit in node met nagebootste KWin-objecten (zelfde eigenschapsnamen)."""
    import json
    import shutil
    import subprocess

    import pytest

    if not shutil.which("node"):
        pytest.skip("node niet beschikbaar")
    script = tmp_path / "s.js"
    script.write_text(kwin_windows.SCRIPT.replace("@SERVICE@", ":1.5").replace("@PATH@", "/p").replace("@IFACE@", "i"))
    mock = tmp_path / "m.js"
    mock.write_text("""
const fs=require('fs'); const d={}; const o={name:'HDMI-A-1',geometry:{x:1920,y:0,width:1920,height:1080}};
global.KWin={MaximizeArea:2};
global.workspace={screens:[o],currentDesktop:d,clientArea:()=>({x:1920,y:0,width:1920,height:1034}),
 windowList:()=>[{normalWindow:true,minimized:false,deleted:false,resourceClass:'org.kde.dolphin',desktopFileName:'org.kde.dolphin',
  caption:'Desktop — Dolphin',clientGeometry:{x:2489,y:129,width:1097,height:630},active:true,stackingOrder:4,onAllDesktops:false,desktops:[d],output:o},
  {normalWindow:true,minimized:true,deleted:false,resourceClass:'konsole',clientGeometry:{x:0,y:0,width:1,height:1}}]};
global.callDBus=(s,p,i,m,a)=>console.log(JSON.stringify({s,p,i,m,a}));
eval(fs.readFileSync(process.argv[2],'utf8'));
""")
    out = json.loads(subprocess.check_output(["node", str(mock), str(script)], text=True))
    assert (out["s"], out["p"], out["i"], out["m"]) == (":1.5", "/p", "i", "report")
    data = json.loads(out["a"])
    assert "error" not in data
    assert [w["cls"] for w in data["windows"]] == ["org.kde.dolphin"]
    assert data["windows"][0]["output"] == "HDMI-A-1" and data["areas"]["HDMI-A-1"]["x"] == 1920
