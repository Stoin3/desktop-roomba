import configparser
import os
import stat
import sys
from pathlib import Path

from kde_roomba import kwin

FAKE_KWRITE = r'''#!PYTHON
import sys, configparser, os
a = sys.argv[1:]; f = os.path.join(os.environ["XDG_CONFIG_HOME"], a[a.index("--file") + 1])
g, k = a[a.index("--group") + 1], a[a.index("--key") + 1]
cp = configparser.RawConfigParser(strict=False, interpolation=None); cp.optionxform = str; cp.read(f)
if "--delete" in a:
    if cp.has_section(g): cp.remove_option(g, k)
    if cp.has_section(g) and not cp.options(g): cp.remove_section(g)
else:
    if not cp.has_section(g): cp.add_section(g)
    cp.set(g, k, a[-1])
with open(f, "w") as fh: cp.write(fh, space_around_delimiters=False)
'''


def setup(tmp_path, monkeypatch, content):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "kwinrulesrc").write_text(content)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    tool = bin_ / "kwriteconfig6"
    tool.write_text(FAKE_KWRITE.replace("PYTHON", sys.executable))
    tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    monkeypatch.setenv("PATH", f"{bin_}:{os.environ['PATH']}")
    return cfg / "kwinrulesrc"


def read(path):
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read(path)
    return cp


def test_removes_leftover_that_hides_all_titlebars_but_keeps_user_rule(tmp_path, monkeypatch):
    f = setup(tmp_path, monkeypatch, """[General]
count=2
rules=abc-firefox,kde-roomba-overlay

[abc-firefox]
Description=Firefox zonder rand
wmclass=firefox
wmclassmatch=1
noborder=true
noborderrule=2

[kde-roomba-overlay]
noborder=true
noborderrule=2
below=true
belowrule=2
""")
    assert ("kde-roomba-overlay", "(geen omschrijving)", "ALLE vensters") in kwin.noborder_rules()
    assert kwin.find_problems() == ["kde-roomba-overlay"]
    assert kwin.remove_rule_if_present()
    cp = read(f)
    assert cp.get("General", "rules") == "abc-firefox" and cp.get("General", "count") == "1"
    assert not cp.has_section("kde-roomba-overlay")
    assert cp.get("abc-firefox", "noborder") == "true"  # eigen regel blijft
    assert kwin.find_problems() == [] and not kwin.remove_rule_if_present()


def test_detects_renamed_or_description_leftovers(tmp_path, monkeypatch):
    f = setup(tmp_path, monkeypatch, """[General]
count=3
rules=1,2,3

[1]
Description=KDE Roomba (automatisch)
wmclass=kde-roomba
noborder=true

[2]
noborder=true
noborderrule=2
acceptfocus=false

[3]
Description=Mijn regel
noborder=true
""")
    assert kwin.find_problems() == ["1", "2"]
    kwin.remove_rule_if_present()
    assert read(f).get("General", "rules") == "3"
