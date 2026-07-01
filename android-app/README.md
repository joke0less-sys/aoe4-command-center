# AoE4 Team Coach für Android

Eine reduzierte Android-Version des bisherigen Co-Caster-Programms – ohne Thor, Spracheingabe oder Screen-Scan.

## Funktionen

- AoE4World-Spielername, Profil-ID oder Profil-Link eingeben
- Eingabe wird lokal gespeichert und beim nächsten Start automatisch geladen
- aktuelles beziehungsweise letztes öffentliches Teamspiel anzeigen
- Tab **Matchup & Plan** mit Rollen und Strategievorschlägen
- maximal abgerundet 50 % des Teams erhalten Fast-Castle-/2-TC-/Tech-Boom-Rollen
- die übrigen Spieler erhalten Aggro-/Map-Control-Rollen
- im 1v1 gilt die 50-%-Begrenzung nicht; Fast Castle, 2 TC oder Aggro werden passend zur Civ empfohlen
- Tab **Gegner-Team** mit Rating/Rang, häufig gespielten Zivilisationen und Gefahreneinschätzung
- Tab **Meine Stats** mit Gesamt-Winrate, Form der letzten 10 Spiele sowie bester, schwächster und meistgespielter Civ
- Tab **Civs** als durchsuchbares Lexikon mit besonderen Einheiten, Gebäuden, Landmarks und Civ-Mechaniken aus den AoE4World-Explorer-Daten

## Oberfläche

- einheitliches dunkles AoE4-inspiriertes Design mit goldenen Rahmen
- kompakte Team-gegen-Gegner-Karten im Matchup-Tab
- farblich getrennte Rollen, primäres Angriffsziel und Timing-Leiste
- Gegnerkarten mit Rang, häufigen Civs, wahrscheinlicher Strategie und Gefahrenanzeige
- Stats-Dashboard mit Winrate, aktueller Form, Civ-Highlights und Fortschrittsbalken
- feste Navigation am unteren Bildschirmrand für die Bedienung auf dem Smartphone

## Öffnen und bauen

1. Den Ordner in Android Studio öffnen.
2. Falls gefragt, Android SDK 35 und Gradle-Abhängigkeiten installieren lassen.
3. Ein Android-Gerät per USB verbinden oder einen Emulator starten.
4. **Run** für die App oder **Build > Build APK(s)** für eine APK wählen.

Die App benötigt Internetzugriff, da sie die öffentliche AoE4World-API nutzt. Private Spiele können nicht ausgewertet werden.
