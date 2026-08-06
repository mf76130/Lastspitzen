# Lastspitze – Home Assistant Custom Integration

Überwacht die Viertelstunden-Lastspitze deines Hausanschlusses, merkt sich
Monatsmaximum/Vormonat und drosselt bei Überschreitung automatisch deine
Wallbox (und stellt sie danach wieder her).

Ersetzt das ursprüngliche YAML-Package (`utility_meter`, `template`,
`input_number`, `automation`) durch eine Integration mit UI-Setup –
kein manuelles YAML mehr nötig, Entity-Namen frei über den Options-Flow
anpassbar.

## Logo

`icon.svg` im Repo-Root enthält das Logo. Für die HACS-Store-Ansicht
in `icon.png` (256×256) umwandeln und ebenfalls im Repo-Root ablegen –
HACS erkennt `icon.png`/`logo.png` automatisch.

## Installation über HACS (Custom Repository)

1. HACS → drei Punkte oben rechts → *Benutzerdefinierte Repositories*
2. Repository-URL eintragen, Kategorie **Integration**
3. „Lastspitze" installieren, Home Assistant neu starten
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „Lastspitze"**

## Setup-Assistent fragt ab

| Feld | Bedeutung | Entspricht im alten YAML |
|---|---|---|
| Leistungssensor Hausanschluss (W) | Momentanleistung des gesamten Bezugs | `sensor.leistung_alle_phasen` |
| Ladestrom-Steuerung Wallbox | `number`-Entity zum Setzen des Ladestroms | `number.goe_221557_amp` |
| Maximaler Ladestrom Wallbox | `number`-Entity mit dem eingestellten Maximalstrom | `number.goe_221557_ama` |
| Warnschwelle / Dauer | ab wann + wie lange gedrosselt wird | `above: 9000`, `for: 00:02:00` |
| Rückkehr-Schwelle / Dauer | ab wann + wie lange wieder hochgefahren wird | `below: 8000`, `for: 00:10:00` |
| Minimaler Ladestrom / Reduktionsschritt | Grenzen der Drosselung | `6 A` Minimum, `-2 A` Schritt |
| Notify-Service / -Ziel | z. B. `notify.pushover` + `michael` | `notify.pushover`, `target: michael` |

Alle Werte lassen sich später über **Konfigurieren** an der Integration
(Options-Flow) ändern, ohne Neuanlage.

## Erzeugte Entities

- `sensor.lastspitze_aktuell` – aktuelle Viertelstunden-Durchschnittsleistung (kW)
- `sensor.lastspitze_monat_max` – Maximum im laufenden Monat (kW)
- `sensor.lastspitze_letzter_monat` – Maximum des Vormonats (kW)

Alle drei sind normale Sensor-Entities mit `state_class: measurement`,
überstehen Neustarts (Restore) und landen automatisch in den
Home-Assistant-Statistiken (Langzeitverlauf, `statistics-graph`).

> Bei mehreren Integrations-Instanzen (z. B. zwei Häusern) hängt HA an
> gleichnamige Entities automatisch `_2` usw. an – im Dashboard dann
> entsprechend anpassen.

## Wie die Viertelstunden-Leistung berechnet wird

Statt eines separaten `utility_meter`-Helfers integriert die Integration
den gewählten Momentanleistungssensor selbst per Trapezregel alle 10
Sekunden auf und wertet bei jeder viertelstündlichen Grenze (:00/:15/:30/:45)
die aufgelaufene Energie zu einer Durchschnittsleistung aus
(`kWh_im_Viertel × 4 = kW`). Das ist eine Näherung, keine eichfähige
Messung – für die Steuerung/Warnung völlig ausreichend, aber nicht für
eine offizielle Lastspitzen-Abrechnung gedacht.

## Warnung & Drosselung

Bleibt die Momentanleistung länger als die konfigurierte Dauer über der
Warnschwelle, wird per Notify-Service gewarnt (inkl. größtem aktuellen
Einzelverbraucher) und der Ladestrom der Wallbox um den konfigurierten
Schritt reduziert (nicht unter das Minimum). Fällt die Leistung
anschließend für die konfigurierte Dauer unter die Rückkehr-Schwelle,
wird der Ladestrom automatisch wieder auf das Maximum gesetzt.

## Dashboard

Fertiges Dashboard liegt unter [`dashboards/lastspitze-dashboard.yaml`](dashboards/lastspitze-dashboard.yaml) –
entweder als neue Ansicht per YAML einfügen, oder die drei Karten manuell
in ein bestehendes Dashboard übernehmen.

## Monatswechsel

Am 1. eines Monats um 00:00:05 wird `lastspitze_monat_max` nach
`lastspitze_letzter_monat` übernommen und danach zurückgesetzt – genau
wie die ursprüngliche Automation.
