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
   (`.kdbx`, `.key`, `.odt`, `.docx`, …) en bestanden die jonger zijn dan 2 uur.
   Maximaal 15 bestanden per ronde.
2. **Heuristiek** – geeft hints zoals *onvolledige download (`.part`)*, *leeg bestand*,
   *dubbele download `(1)`*, *oude installer*, *lockbestand*, *oude schermafdruk*.
3. **Lokaal AI-model** (Ollama, standaard `qwen2.5:1.5b`) krijgt per bestand naam, type,
   grootte, leeftijd, de hints en (voor tekstbestanden) de eerste 200 tekens, en beslist
   met gestructureerde JSON-uitvoer. Het is geïnstrueerd om bij twijfel *niets* weg te gooien.
   Er gaat **niets** het internet op.

Draait Ollama niet, dan gebruikt de roomba alleen de heuristiek (en zegt hij dat).

Ander model? Pas `model` aan in de config, bijv. `qwen2.5:0.5b` (lichter) of
`llama3.2:3b` (slimmer), en doe `ollama pull <model>`.

## Instellingen

`~/.config/kde-roomba/config.json` (rechtsklik → Instellingen). Belangrijkste opties:

| Optie | Standaard | Betekenis |
|---|---|---|
| `use_ai` | `true` | Ollama gebruiken |
| `model` | `qwen2.5:1.5b` | Ollama-model |
| `min_age_hours` | `2` | Nieuwere bestanden nooit weggooien |
| `max_files_per_run` | `15` | Maximum per ronde |
| `protected_extensions` | … | Nooit weggooien |
| `allow_folders` | `false` | Ook (lege) mappen mogen weg |
| `dry_run` | `false` | Proefrun |
| `roomba_size`, `speed_px_s` | `96`, `260` | Grootte en snelheid |
| `icon_cell_width/height`, `icon_flow` | auto | Zie hieronder |

Herstart de roomba na het wijzigen (rechtsklik → Afsluiten, dan `kde-roomba`).

## Technische notities

- **Wayland (standaard op Fedora KDE):** een programma mag zijn venster daar niet zelf
  positioneren of 'onder alle vensters' zetten. De roomba maakt daarom automatisch een
  **KWin-vensterregel** aan (`~/.config/kwinrulesrc`, groep `kde-roomba-overlay`) die het
  transparante venster over het bureaublad legt, onder je andere vensters houdt en uit de
  taakbalk/alt-tab weert. Alleen de roomba zelf vangt muisklikken; de rest van het venster
  laat klikken door naar je bureaublad (input-region). Uitzetten: `"manage_kwin_rule": false`.
- **Iconposities:** de roomba leest de posities uit
  `~/.config/plasma-org.kde.plasma.desktop-appletsrc`; voor automatisch geplaatste iconen
  bootst hij Plasma's raster na (mappen eerst, dan alfabetisch, kolom voor kolom). Dat is een
  benadering. Komt hij net naast je iconen uit, stel dan `icon_cell_width` / `icon_cell_height`
  (in pixels) of `icon_flow` (`"columns"` of `"rows"`) bij.
- Alleen het **primaire scherm** wordt gebruikt.
- Bestanden gaan via `QFile.moveToTrash` (freedesktop-prullenbak), met `gio trash` als terugval.

## Verwijderen

```bash
./uninstall.sh
```

Gebruik `./uninstall.sh --purge` om ook config en geschiedenis te wissen.

## Ontwikkelen

```bash
python3 -m pytest -q tests
```
