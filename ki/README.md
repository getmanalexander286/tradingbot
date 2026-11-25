# KI Quant Research Bot (läuft neben den 3 MA-Bots)

> **MODE: DEMO TRADING — VIRTUAL MONEY ONLY.** Kein Code sendet Orders an eine Börse, es gibt keine API-Keys.

## Was er macht

- **Dieselben 24 Märkte** wie die MA-Bots (16 Krypto über Kraken, 8 Aktien über Yahoo). Die Liste wird nur **gelesen** aus der gemeinsamen `config.yaml`. Neue Werte dort gelten automatisch auch hier.
- **9 Strategien** (Trend, Momentum, Breakout, Mean Reversion, SMC-Liquidity-Sweep, 2× Machine Learning) plus eine **Hybrid-KI**, die pro Anlageklasse und Marktphase die Strategie mit der besten Out-of-Sample-Evidenz nimmt. Ohne Evidenz kauft sie nichts.
- **Gleiche Bedingungen wie die MA-Bots:** je Strategie 2.400 € Spielgeld = 24 Teildepots à 100 €, 0,26 % Gebühr. Zusätzlich Spread, Slippage und Kurslücken bei Stops.
- **Research (sonntags):** Walk-Forward über alle Märkte gemeinsam, Parameterwahl nur mit vorher abgeschlossenen Trades, 2×-Kosten-Test, Monte Carlo, Signifikanz mit Bonferroni-Korrektur.
- **Paper-Trading (stündlich):** verarbeitet neue Tageskerzen, setzt Stops, protokolliert jede Entscheidung mit Begründung.
- **Risiko:** 2 % Risiko pro Trade je Teildepot. Pro Depot gilt: −3 % am Tag / −6 % in der Woche → keine neuen Trades, −20 % → alles schließen und stoppen. Feste Obergrenzen im Code.

## Stört die MA-Bots nicht

| | MA-Bots | KI-Bot |
|---|---|---|
| Workflow | `bot.yml` („Trading Bot“), alle 5 min | `ki-bot.yml` („KI Bot“), stündlich |
| Concurrency-Gruppe | `trading-bot` | `ki-bot` (eigene, blockiert nichts) |
| Dateien | `state/`, `docs/index.html`, Root-Dateien | nur `ki/` und `docs/ki/` |
| Pakete | `requirements.txt` | `ki/requirements.txt` |

Die MA-Dateien werden nur gelesen (Marktliste, Kontostand für den Vergleich), nie geändert. Ein Test prüft, dass der Workflow nur `ki/` und `docs/ki/` committet.

## Dashboard

**https://getmanalexander286.github.io/tradingbot/ki/** zeigt alle KI-Depots und die 3 MA-Bots im direkten Vergleich, dazu Regime und Entscheidung pro Markt sowie das Research-Log.

## Steuern

| Aktion | Weg |
|---|---|
| Erster Start | Actions → **KI Bot** → Run workflow → `research` |
| Not-Aus (nur KI) | Run workflow → `kill` (wieder an: `unkill`) |
| Ganz anhalten | Actions → KI Bot → Disable workflow |
| Depots neu starten | Run workflow → `reset` |
| Lokal | `cd ki && pip install -r requirements.txt && python run.py research --synthetic` |

## Grenzen (ehrlich)

- Tageskerzen: Kraken liefert nur ~2 Jahre Krypto-Historie (wächst mit der Zeit im Cache), Aktien 5 Jahre.
- Depot-Limits (Tag/Woche/Drawdown) greifen im Paper-Trading, im Backtest werden sie nicht simuliert.
- Kein Live-Trading, kein Reinforcement Learning, keine Deep-Learning-Modelle (siehe `RESEARCH.md`).
