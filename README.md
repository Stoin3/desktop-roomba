# 🧹 KDE Roomba

Een robotstofzuiger voor je **Fedora KDE**-bureaublad. Hij staat rustig in zijn
laadstation. **Dubbelklik** erop: een klein **lokaal AI-model** bepaalt welke
bestanden op je bureaublad afval zijn. Daarna rijdt de roomba ernaartoe, zuigt
ze op (ze gaan naar de **prullenbak**) en rijdt terug naar zijn laadstation.

Alles van bovenaf gezien, alsof er echt een roomba over je bureaublad rijdt:

- draaiende zijborstel, statusring (groen = opladen, blauw draaiend = nadenken, wit = aan het werk)
- vloeiend sturen, afremmen en bijdraaien, met een licht 'gestofzuigd' spoor
- iconen die in een draaikolk van stofdeeltjes onder de roomba verdwijnen
- stofbak-indicator die voller raakt, vonkjes bij het aankoppelen
- tekstballonnen met wat hij doet en waarom

## Installeren

```bash
git clone https://github.com/stoin3/kde-roomba.git
```

```bash
cd kde-roomba && ./install.sh
```

Het script:

1. installeert `python3-pyqt6` (via `dnf`) als dat nog niet aanwezig is;
2. zet het programma in `~/.local/share/kde-roomba` en maakt een `kde-roomba`-commando en menu-item;
3. vraagt of hij automatisch moet starten bij inloggen;
4. biedt aan **Ollama** te installeren en het model `qwen2.5:1.5b` (±1 GB) te downloaden.

Starten:

```bash
kde-roomba
```

Of zonder installatie, direct vanuit de map: `python3 -m kde_roomba`.

## Bediening

| Actie | Wat er gebeurt |
|---|---|
| **Dubbelklik** op de roomba | Opruimen starten |
| **Slepen** | Laadstation verplaatsen (wordt onthouden) |
| **Rechtsklik** | Menu: opruimen, proefrun, AI aan/uit, geschiedenis, prullenbak, instellingen, afsluiten |

Alle weggegooide bestanden staan in de **prullenbak** en zijn met Dolphin terug te zetten.
Een logboek staat in `~/.local/state/kde-roomba/history.log`.

> 💡 Probeer eerst een **Proefrun** (rechtsklik → Proefrun): dan rijdt hij wel rond,
> maar gooit hij niets echt weg.

## Hoe beslist hij wat afval is?

1. **Harde veiligheidsregels** – deze gaan nooit weg (en worden niet eens aan de AI getoond):
   mappen, snelkoppelingen/`.desktop`-bestanden, verborgen bestanden, beschermde extensies
   (`.kdbx`, `.key`, `.odt`, `.docx`, …) en bestanden die in de laatste 3 minuten nog gewijzigd zijn.
   Maximaal 15 bestanden per ronde.
2. **Heuristiek** – geeft hints zoals *onvolledige download (`.part`)*, *leeg bestand*,
   *dubbele download `(1)`*, *willekeurig getypte naam (`asdfgh`, `liuhliuh`)*, *oude installer*, *lockbestand*, *oude schermafdruk*.
3. **Lokaal AI-model** (Ollama, standaard `qwen2.5:1.5b`) krijgt per bestand naam, type,
   grootte, leeftijd, de hints en (voor tekstbestanden) de eerste 200 tekens, en beslist
   met gestructureerde JSON-uitvoer. Het is geïnstrueerd om bij twijfel *niets* weg te gooien.
   Er gaat **niets** het internet op.

Draait Ollama niet, dan start de roomba het zelf. Lukt dat niet, dan gebruikt hij alleen de heuristiek en zegt hij in de tekstballon waarom.

Ander model? Pas `model` aan in de config, bijv. `qwen2.5:0.5b` (lichter) of
`llama3.2:3b` (slimmer), en doe `ollama pull <model>`.

## Instellingen

`~/.config/kde-roomba/config.json` (rechtsklik → Instellingen). Belangrijkste opties:

| Optie | Standaard | Betekenis |
|---|---|---|
| `use_ai` | `true` | Ollama gebruiken |
| `model` | `qwen2.5:1.5b` | Ollama-model |
| `min_age_hours` | `0.05` | Bestanden die in de laatste 3 minuten gewijzigd zijn overslaan (lopende downloads) |
| `max_files_per_run` | `15` | Maximum per ronde |
| `protected_extensions` | … | Nooit weggooien |
| `allow_folders` | `false` | Ook (lege) mappen mogen weg |
| `dry_run` | `false` | Proefrun |
| `roomba_size`, `speed_px_s` | `96`, `260` | Grootte en snelheid |
| `icon_cell_width/height`, `icon_flow` | auto | Zie hieronder |

Herstart de roomba na het wijzigen (rechtsklik → Afsluiten, dan `kde-roomba`).

## Technische notities

- **Er wordt niets aan je KDE-instellingen veranderd.** Op Wayland gebruikt de roomba
  `layer-shell-qt`, dezelfde (al geïnstalleerde) bibliotheek waarmee Plasma zijn panelen en
  bureaublad tekent. Daarmee vraagt hij de compositor om een laag boven het bureaublad maar
  onder je vensters, zonder taakbalkknop en zonder focus te stelen. Alleen de roomba zelf vangt
  muisklikken; ernaast klik je gewoon op je bureaublad. Op X11 gebeurt hetzelfde met
  standaard-vensterhints.
- Versie 1.0.0 schreef een KWin-vensterregel; die wordt bij het starten automatisch weer verwijderd.
- **Iconposities:** de roomba leest de posities uit
  `~/.config/plasma-org.kde.plasma.desktop-appletsrc`; voor automatisch geplaatste iconen
  bootst hij Plasma's raster na (mappen eerst, dan alfabetisch, kolom voor kolom). Dat is een
  benadering. Komt hij net naast je iconen uit, stel dan `icon_cell_width` / `icon_cell_height`
  (in pixels) of `icon_flow` (`"columns"` of `"rows"`) bij.
- Alleen het **primaire scherm** wordt gebruikt.
- Bestanden gaan via `QFile.moveToTrash` (freedesktop-prullenbak), met `gio trash` als terugval.

## Problemen oplossen

Gebeurt er niets? Start hem in Konsole, dan zie je meteen wat er misgaat:

```bash
kde-roomba
```

Hetzelfde staat in `~/.local/state/kde-roomba/roomba.log`. Fouten verschijnen ook als
bureaubladmelding. Let op de regel `Vensterlaag:`; daar hoort `layer-shell` te staan.
Staat er `PyQt6 komt uit pip`, verwijder dan de pip-versie
(`pip uninstall PyQt6 PyQt6-Qt6 PyQt6-sip`) zodat de Fedora-versie (`python3-pyqt6`) wordt gebruikt.

## Verwijderen

```bash
./uninstall.sh
```

Gebruik `./uninstall.sh --purge` om ook config en geschiedenis te wissen.

## Ontwikkelen

```bash
python3 -m pytest -q tests
```
