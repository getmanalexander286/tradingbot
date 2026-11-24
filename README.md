# Trading-Bot

Papier-Depot für Krypto und Aktien. **Kein echtes Geld** – der Bot ist mit keiner
Börse und keinem Konto verbunden und kann nichts kaufen. Er notiert nur, was er
getan *hätte*.

## Dashboard

→ **https://getmanalexander286.github.io/tradingbot/**

Aktualisiert sich alle 5 Minuten selbst. Funktioniert auf dem Handy.

## Drei Strategien im Vergleich

Alle drei laufen gleichzeitig auf denselben Kursen, jede mit eigenem Depot von
2.400 € (100 € je Wert). So lässt sich direkt ablesen, welche besser abschneidet.

| Strategie | Kerzen | Durchschnitte | Verhalten |
|---|---|---|---|
| **Langsam** | Tag | MA20 / MA50 | wenige Signale, träge, geringe Gebühren |
| **Schnell** | Tag | MA5 / MA20 | mehr Signale, reagiert früher |
| **Daytrader** | 15 Minuten | MA8 / MA21 | viele Signale, abends alles glattgestellt |

Der Daytrader hat zusätzlich einen engeren Stop-Loss (3 %) und eine
Mindesthaltedauer von 30 Minuten, damit er nicht ständig hin- und herspringt.

### Was dabei getestet wird

Die Studienlage zu Daytrading ist eindeutig negativ: Eine brasilianische
Untersuchung fand, dass von den Privatanlegern, die länger als 300 Handelstage
dabeiblieben, 97 % Geld verloren. Eine Langzeitstudie aus Taiwan kommt auf unter
1 % dauerhaft erfolgreiche Daytrader.

Dieses Projekt prüft das mit Spielgeld nach, statt es zu glauben oder zu
ignorieren. Erwartung: Der Daytrader macht am meisten Trades und verliert am
meisten an Gebühren — 0,52 % je Rundlauf summieren sich schnell.

## Gehandelte Werte

**16 Kryptowährungen** (Kraken, rund um die Uhr):
BTC, ETH, SOL, XRP, ADA, DOT, LINK, LTC, AVAX, DOGE, ATOM, XLM, UNI, AAVE, BCH, FIL

**8 Aktien** (Yahoo Finance, alle in Euro notiert):
SAP, Siemens, Allianz, ASML, LVMH, Airbus, Apple (Xetra), Microsoft (Xetra)

Aktienbörsen sind nur Mo–Fr etwa 08:00–16:30 UTC geöffnet. Außerhalb steht der
Kurs still; der Bot erkennt das und handelt diese Werte dann nicht.

## Wie es läuft

GitHub führt `trader.py` alle 5 Minuten aus. Jeder Durchlauf:

1. holt Kurse: Krypto von Kraken, Aktien von Yahoo Finance
2. berechnet die gleitenden Durchschnitte für jede Strategie
3. entscheidet pro Strategie und Wert: kaufen, verkaufen, halten
4. prüft Stop-Loss, Take-Profit und Tagesschluss
5. schreibt den neuen Stand nach `state/`
6. erzeugt das Dashboard in `docs/index.html`

Kein Server nötig, läuft auch wenn alle eigenen Geräte aus sind.

## Einstellungen ändern

`config.yaml` im Browser öffnen, Stift-Symbol, ändern, speichern.
Wirkt beim nächsten Durchlauf.

| Einstellung | Bedeutung |
|---|---|
| `aktiv` | `false` = beobachtet nur, handelt nicht. Stop-Loss greift weiter. |
| `startkapital` | je Strategie, gleichmäßig auf alle Werte verteilt |
| `strategien` | Name, Kürzel, Zeitfenster und MA-Längen je Strategie |
| `stop_loss` | `0.08` = Notverkauf bei 8 % Verlust (je Strategie überschreibbar) |
| `take_profit` | `0` = aus. `0.2` = Gewinnmitnahme bei +20 % |
| `krypto` / `aktien` | welche Werte gehandelt werden |
| `tagesschluss_utc` | wann der Daytrader spätestens verkauft |

## Bot anhalten

- **Kurz:** in `config.yaml` `aktiv: false` setzen
- **Ganz:** Reiter *Actions* → *Trading Bot* → *Disable workflow*

## Zurücksetzen

Den Ordner `state/` löschen (oder nur den einer Strategie). Beim nächsten
Durchlauf fängt das betroffene Depot mit dem Startkapital neu an.

## Dateien

| Datei | Zweck |
|---|---|
| `trader.py` | ein Durchlauf für alle Strategien |
| `marktdaten.py` | holt Kurse von Kraken und Yahoo Finance |
| `build_dashboard.py` | erzeugt `docs/index.html` |
| `config.yaml` | alle Einstellungen |
| `state/<kürzel>/` | Positionen, Trades und Verlauf je Strategie |

## Grenzen

- **Takt:** GitHub erlaubt höchstens alle 5 Minuten und hält das bei Auslastung
  nicht immer ein. Für echtes Daytrading wäre das zu langsam — der Daytrader hier
  ist ein Experiment, keine ernsthafte Handelsumsetzung.
- **Öffentlich:** Das Repository muss öffentlich sein, damit GitHub Actions
  unbegrenzt läuft. Es liegen keine Zugangsdaten darin, weil nichts mit einer
  Börse verbunden ist.
- **Strategie:** MA-Crossover ist seit Jahrzehnten bekannt und schlägt den Markt
  meist nicht. Der Zweck ist zu lernen und zu messen, nicht Gewinn.
