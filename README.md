# Trading-Bot

Papier-Depot für Krypto. **Kein echtes Geld** – der Bot ist mit keiner Börse
und keinem Konto verbunden und kann nichts kaufen. Er notiert nur, was er
getan *hätte*.

## Wie es läuft

GitHub führt `trader.py` alle 5 Minuten aus. Jeder Durchlauf:

1. holt die aktuellen Kurse von Kraken
2. berechnet die gleitenden Durchschnitte (MA20 / MA50)
3. entscheidet pro Markt: kaufen, verkaufen, halten
4. prüft Stop-Loss und Take-Profit
5. schreibt den neuen Stand nach `state/`
6. erzeugt das Dashboard in `docs/index.html`

Kein Server nötig, läuft auch wenn alle eigenen Geräte aus sind.

## Dashboard

→ **https://getmanalexander286.github.io/tradingbot/**

Aktualisiert sich alle 5 Minuten selbst. Funktioniert auf dem Handy.

## Einstellungen ändern

`config.yaml` im Browser öffnen, Stift-Symbol, ändern, speichern.
Wirkt beim nächsten Durchlauf.

| Einstellung | Bedeutung |
|---|---|
| `aktiv` | `false` = beobachtet nur, handelt nicht. Stop-Loss greift weiter. |
| `startkapital` | wird gleichmäßig auf die Märkte verteilt |
| `ma_schnell` / `ma_langsam` | Länge der Durchschnitte in Tagen |
| `stop_loss` | `0.08` = Notverkauf bei 8 % Verlust |
| `take_profit` | `0` = aus. `0.2` = Gewinnmitnahme bei +20 % |
| `maerkte` | welche Paare gehandelt werden |

## Bot anhalten

- **Kurz:** in `config.yaml` `aktiv: false` setzen
- **Ganz:** Reiter *Actions* → *Trading Bot* → *Disable workflow*

## Zurücksetzen

Dateien in `state/` löschen. Beim nächsten Durchlauf fängt das Depot
mit dem Startkapital neu an.

## Dateien

| Datei | Zweck |
|---|---|
| `trader.py` | ein Durchlauf: Kurse holen, entscheiden, Stand speichern |
| `build_dashboard.py` | erzeugt `docs/index.html` |
| `config.yaml` | alle Einstellungen |
| `state/positions.json` | aktuelle Positionen und Bargeld |
| `state/trades.csv` | alle Trades |
| `state/history.csv` | Depotwert über Zeit |
| `.github/workflows/bot.yml` | Zeitplan |

## Grenzen

- **Takt:** GitHub erlaubt höchstens alle 5 Minuten und hält das bei Auslastung
  nicht immer ein. Bei einem Kurseinbruch reagiert der Stop-Loss also mit
  Verzögerung. Für Papier-Handel unerheblich; bei echtem Geld würde der
  Stop-Loss als Order direkt bei der Börse liegen.
- **Öffentlich:** Das Repository muss öffentlich sein, damit GitHub Actions
  unbegrenzt läuft. Also keine Zugangsdaten hier ablegen – es gibt auch keine,
  weil nichts mit einer Börse verbunden ist.
- **Strategie:** MA-Crossover ist seit Jahrzehnten bekannt und schlägt den Markt
  meist nicht. Der Zweck ist zu lernen und zu messen, nicht Gewinn.
