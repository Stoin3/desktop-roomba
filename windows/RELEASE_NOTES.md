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

### Nieuw in deze versie

- Windows-versie: exacte iconposities via de Shell-API, rondrijden door Verkenner-vensters
  (ook in detailweergave, via UI Automation), overlay boven alle vensters tijdens een ronde,
  systeemvak-icoon. Getest op een echte Windows-machine (eind-tot-eindtest in GitHub Actions).
- 12 outfits (rechtsklik → Outfit): 5 normale en 7 cute.
- Veel zuiniger in rust: ~1% van één CPU-kern (was 37%), ~0,3% met `"idle_animation": false`.
- Afsluiten/herstarten via menu, systeemvak en `--quit` / `--restart`; nooit meer vast op "draait al".
