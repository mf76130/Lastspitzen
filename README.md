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
einen festen Schritt, sondern um so viele Ampere, dass der Gesamtbezug rechnerisch knapp unter die
Warnschwelle fällt:

`Überschuss (W) = Bezug − (Warnschwelle − Abstand)` → `Ampere = Überschuss ÷ (Spannung × Phasen)`

Der **Abstand unter der Warnschwelle** (Standard 100 W) ist der einzige Puffer. Wegen der ganzen Ampere wird
immer abgerundet, der Bezug landet also höchstens etwa 700 W unter dem Ziel. Bei mehreren Wallboxen wird die nötige
Reduktion gleichmäßig verteilt, nie unter den minimalen Ladestrom. Ist die Option aus, gilt der feste Reduktionsschritt.

## Schrittweise Wiederherstellung

Liegt der Bezug lange genug unter der Rückkehr-Schwelle, springt der Ladestrom **nicht** auf das Maximum, sondern
wird nur so weit erhöht, wie bis knapp unter die Warnschwelle noch Platz ist:

`Spielraum (W) = (Warnschwelle − Abstand) − aktueller Bezug` → `Ampere = Spielraum ÷ (Spannung × Phasen)` (abgerundet)

Die zusätzlichen Ampere gehen reihum an die ladenden Wallboxen. Reicht der Spielraum nicht für ein weiteres Ampere,
bleibt alles, wie es ist. Erst wenn der Bezug weiter sinkt, geht es Schritt für Schritt weiter, bis das Maximum erreicht
ist. So pendelt der Ladestrom nicht mehr zwischen Maximum und Drosselung. Nicht ladende Wallboxen werden direkt auf das
Maximum zurückgesetzt, da sie das Netz nicht belasten. Jeder Schritt braucht die eingestellte Dauer unter der
Rückkehr-Schwelle.

### Leistungssensor pro Wallbox (optional, empfohlen)

Gibst du bei einer Wallbox zusätzlich einen Leistungssensor (W) an, geht die Integration genauer vor:

- Nur Wallboxen, die gerade laden (> 300 W), werden gedrosselt. Eine Wallbox ohne Fahrzeug bekommt keinen Anteil mehr.
- Die Reduktion bezieht sich auf den **tatsächlich gezogenen** Strom, nicht auf den eingestellten. Zieht ein Auto nur 8 A bei 16 A Einstellung, bringt eine Senkung von 16 auf 13 A nichts – die Integration rechnet deshalb ab 8 A.
- Reichen die Wallboxen rechnerisch nicht aus (z. B. beide schon fast am Minimum), steht das in der Benachrichtigung.

Ohne Leistungssensor gilt wie bisher der eingestellte Strom und alle Wallboxen werden gleich behandelt.

In der Meldung „größter Verbraucher" werden Summen- und Nennwerte ausgelassen. Welche Begriffe im Sensornamen dazu führen,
steht im Feld **„Begriffe, die beim größten Verbraucher ignoriert werden"** (Standard u. a. `gesamt, total, rated, house load, hausverbrauch`).

### Status pro Wallbox (optional)

Meldet der Leistungssensor einer Wallbox verzögert, kannst du zusätzlich ein **Status-Entity** angeben
(z. B. den Fahrzeugstatus der Wallbox). Ist es gesetzt, entscheidet der Status, ob die Wallbox lädt:

- Status „lädt" → die Wallbox wird gedrosselt. Zeigt der Leistungssensor noch nichts, rechnet die
  Integration mit dem eingestellten Strom.
- Status „schläft/idle/…" → die Wallbox wird nicht angefasst, auch wenn der Leistungssensor noch einen alten Wert zeigt.
- Status `unknown`/`unavailable` → Rückfall auf den Leistungssensor.

Welche Status-Werte „lädt" bzw. „lädt nicht" bedeuten, steht in zwei Feldern (kommagetrennt, ohne
Groß-/Kleinschreibung): **„Status-Werte für lädt"** (Standard `charging, laden, lädt, ladend, on, true, in use`) und
**„Status-Werte für lädt nicht"** (Standard u. a. `idle, sleep, off, standby, complete, waitcar`).
**Ein Status, der in keiner der beiden Listen steht, wird als „lädt" behandelt** – im Zweifel wird also gedrosselt
statt nichts zu tun, und die Benachrichtigung weist darauf hin, den Wert zu ergänzen.
Die aktuellen Werte siehst du unter Entwicklerwerkzeuge → Zustände. Wähle möglichst den **Fahrzeug-/Ladestatus**
der Wallbox (z. B. beim go-e „Auto-Status"), nicht eine Freigabe-Einstellung wie `forced_on`.

Die Drosselung läuft auch dann, wenn die Wallboxen allein den Zielwert rechnerisch nicht erreichen können:
sie gehen dann bis auf den minimalen Ladestrom herunter.

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
