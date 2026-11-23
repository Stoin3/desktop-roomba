## 🧹 KDE Roomba – ook voor Windows

Een robotstofzuiger voor je bureaublad. Dubbelklik erop: een klein **lokaal** AI-model bepaalt welke
bestanden afval zijn, de roomba rijdt ernaartoe, zuigt ze op (naar de **Prullenbak**, terug te zetten)
en rijdt terug naar zijn laadstation. Sleep hem op een **Verkenner-venster** en hij rijdt dáár
door de bestanden.

### Downloads

| Bestand | Wat |
|---|---|
| **Roomba.exe** | Eén bestand: dubbelklikken en klaar. Start iets langzamer (pakt zichzelf eerst uit). |
| **Roomba-windows.zip** | Map-versie: uitpakken en `Roomba.exe` in de map starten. Start sneller. |

Windows SmartScreen kan waarschuwen ("onbekende uitgever"), omdat het programma niet digitaal
ondertekend is: kies **Meer info → Toch uitvoeren**. Start de roomba **niet** als administrator.

Voor de AI: installeer [Ollama](https://ollama.com) en doe `ollama pull qwen2.5:1.5b`. Zonder Ollama
gebruikt de roomba zijn ingebouwde regels. Linux/KDE: zie de README (`./install.sh`).

### Nieuw in 2.2.0 – veel zuiniger in rust

Gemeten op een echte Windows-machine, roomba in rust (aangekoppeld):

| | CPU (van één kern) | Geheugen (echt privé) |
|---|---|---|
| v2.1.0 | 2,2% | – (Taakbeheer 134 MB) |
| **v2.2.0** | **0–1%** | **~72 MB** (Taakbeheer ~94 MB) |
| **v2.2.0, zuinige modus** | **0,1–0,2%** | ~71 MB |

- In rust een klein venster rond het laadstation i.p.v. een overlay over al je schermen
  (pas tijdens het rijden het volledige overlayvenster).
- In rust wordt alleen een kant-en-klaar plaatje getekend, en alleen als het laadlampje van
  helderheid verandert; een fout waardoor hij onzichtbaar toch steeds helemaal tekende is opgelost.
- UI Automation/COM pas laden bij gebruik en daarna loslaten; geen onnodige vensterbewerkingen.
- Nieuw: rechtsklik → **🔋 Zuinig** (laadlampje ademt niet, in rust bijna geen tekenwerk).

### Eerder (2.1.0)

- Windows-versie: exacte iconposities via de Shell-API, rondrijden door Verkenner-vensters
  (ook in detailweergave, via UI Automation), systeemvak-icoon.
- 12 outfits (rechtsklik → Outfit): 5 normale en 7 cute.
- Afsluiten/herstarten via menu, systeemvak en `--quit` / `--restart`.
