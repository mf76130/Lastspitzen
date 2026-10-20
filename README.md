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

## Icon / Logo

Seit Home Assistant 2026.3 liefert die Integration ihr Icon direkt mit
(`custom_components/lastspitze/brand/icon.png` + `logo.png`, je in normal
und `@2x`). Kein Pull Request beim `home-assistant/brands`-Repo mehr nötig –
das Icon erscheint automatisch, sobald diese Version installiert ist.

## Berechnete Reduktion

Ist **„Reduktion berechnen"** aktiv (Standard), senkt die Integration den Ladestrom nicht um
einen festen Schritt, sondern um so viele Ampere, dass der Gesamtbezug rechnerisch unter die
Warnschwelle fällt:

`Überschuss (W) = Bezug − Warnschwelle` → `Ampere = Überschuss ÷ (Spannung × Phasen)`

Bei mehreren Wallboxen wird die nötige Reduktion gleichmäßig verteilt (aufgerundet, mind. 1 A),
nie unter den minimalen Ladestrom. Ist die Option aus, gilt der feste Reduktionsschritt.
Hinweis: Die Rechnung geht davon aus, dass die Wallbox tatsächlich den eingestellten Strom zieht.

### Leistungssensor pro Wallbox (optional, empfohlen)

Gibst du bei einer Wallbox zusätzlich einen Leistungssensor (W) an, geht die Integration genauer vor:

- Nur Wallboxen, die gerade laden (> 300 W), werden gedrosselt. Eine Wallbox ohne Fahrzeug bekommt keinen Anteil mehr.
- Die Reduktion bezieht sich auf den **tatsächlich gezogenen** Strom, nicht auf den eingestellten. Zieht ein Auto nur 8 A bei 16 A Einstellung, bringt eine Senkung von 16 auf 13 A nichts – die Integration rechnet deshalb ab 8 A.
- Ein **Sicherheitsaufschlag** (Standard 10 %) auf die nötige Entlastung verhindert, dass es knapp nicht reicht.
- Reichen die Wallboxen rechnerisch nicht aus (z. B. beide schon fast am Minimum), steht das in der Benachrichtigung.

Ohne Leistungssensor gilt wie bisher der eingestellte Strom und alle Wallboxen werden gleich behandelt.

In der Meldung „größter Verbraucher" werden Summen- und Nennwerte (Namen mit „Gesamt", „Total", „Rated", „Alle Phasen") ausgelassen.

### Status pro Wallbox (optional)

Meldet der Leistungssensor einer Wallbox verzögert, kannst du zusätzlich ein **Status-Entity** angeben
(z. B. den Fahrzeugstatus der Wallbox). Ist es gesetzt, entscheidet der Status, ob die Wallbox lädt:

- Status „lädt" → die Wallbox wird gedrosselt. Zeigt der Leistungssensor noch nichts, rechnet die
  Integration mit dem eingestellten Strom.
- Status „schläft/idle/…" → die Wallbox wird nicht angefasst, auch wenn der Leistungssensor noch einen alten Wert zeigt.
- Status `unknown`/`unavailable` → Rückfall auf den Leistungssensor.

Welche Status-Werte „lädt" bedeuten, steht im Feld **„Status-Werte für lädt"** (kommagetrennt, ohne
Groß-/Kleinschreibung, Standard: `charging, laden, lädt, ladend, on, true, in use`). Passt der Status deiner Wallbox
nicht dazu, trag dort den passenden Wert ein. Die aktuellen Werte siehst du unter Entwicklerwerkzeuge → Zustände.

## Manuelle Wallbox-Eingriffe

Die Integration merkt sich intern, welche Wallboxen sie selbst gedrosselt hat.
Ändert der Nutzer den Ladestrom während einer aktiven Drosselung manuell
(z.B. in der go-eCharger-App), erkennt die Integration das an der
Zustandsänderung und **fasst diese Wallbox danach nicht mehr automatisch
an** – auch nicht, wenn der Verbrauch später unter die Rückkehr-Schwelle
fällt. Erst die nächste eigene Drosselung (neue Lastspitze) übernimmt die
Wallbox wieder in die automatische Steuerung.

Diese Information übersteht auch einen Neustart: sie wird als Attribut
`throttled_wallboxes` am Sensor `sensor.lastspitze_aktuell` gespeichert und
über Home Assistants eingebaute `RestoreEntity`-Funktion automatisch
wiederhergestellt – genau wie die Monatswerte.

## Wallbox-Steuerung (optional, beliebig viele)

Im Setup gibt es einen Schalter **„Wallbox-Steuerung aktivieren"**:

- **Aus** → die Integration liefert nur die drei Lastspitze-Sensoren, es wird nichts gedrosselt oder benachrichtigt.
- **Ein** → danach fragt der Assistent, wie viele Wallboxen du hast, und für jede die beiden
  Entities (Ladestrom-Steuerung + Maximalstrom). **Alle Wallboxen werden bei Überschreitung
  gleichzeitig und gleich behandelt** (gleicher Reduktionsschritt, gleiches Minimum, gleiche
  Wiederherstellung).

Bestehende Installationen mit nur einer Wallbox werden beim ersten Start nach dem Update
automatisch ins neue Format migriert – keine manuelle Aktion nötig.

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

## Neustarts mitten in der Viertelstunde

Die laufende Viertelstunde (aufgelaufene Energie und erfasste Zeit) wird beim Beenden oder Neuladen der
Integration mitgespeichert und danach wieder aufgenommen. Zusätzlich gilt:

- Der Wert wird auf die **tatsächlich erfasste Zeit** bezogen, eine kurze Lücke macht ihn also nicht mehr zu klein.
- Wurde weniger als die Hälfte der Viertelstunde (7,5 Minuten) erfasst, wird der Wert **nicht übernommen**
  (der alte bleibt stehen, im Protokoll steht eine Warnung) und fließt nicht ins Monatsmaximum ein.
- Das Attribut `quarter_coverage` am Sensor `sensor.lastspitze_aktuell` zeigt, welcher Anteil (0 bis 1) der
  zuletzt ausgewerteten Viertelstunde erfasst war.

Die Regelung der Wallbox (Warnung/Drosselung) arbeitet mit dem Momentanwert und ist davon nicht betroffen.

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
