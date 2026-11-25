# Wissensbasis: Was ist belegt, was nicht?

Einordnung nach Evidenz, ohne Garantie und mit Stand der Literatur bis 2026. Das System **testet** jede Idee selbst. Diese Liste ist nur die Ausgangshypothese.

## 1. Empirisch gut belegt (aber: Vorteil schrumpft oft nach Veröffentlichung)

| Methode | Kernbelege | Im Bot |
|---|---|---|
| Time-Series Momentum / Trendfolge | Moskowitz, Ooi & Pedersen (2012); Hurst, Ooi & Pedersen „A Century of Evidence on Trend-Following“ | S001, S003, S007 |
| Cross-Sectional Momentum | Jegadeesh & Titman (1993) | – (braucht viele Assets) |
| Krypto-Momentum | Liu & Tsyvinski (2021), „Risks and Returns of Cryptocurrency“ | S007 |
| Volatility Targeting / vol-basiertes Sizing | Moreira & Muir (2017); verbessert vor allem das Risiko, nicht unbedingt die Rendite | ATR-basiertes Positionssizing |
| Kurzfristige Umkehr (Reversal) | Lehmann (1990), Jegadeesh (1990), stark kostenabhängig | S002, S006 |

## 2. Plausibel, aber schwach oder gemischt belegt

- **Klassische Indikatoren (RSI, MACD, MA-Kreuzungen):** Brock, Lakonishok & LeBaron (1992) fanden Vorteile. Sullivan, Timmermann & White (1999) zeigten, dass viel davon **Data Snooping** ist. In der Praxis sind es meist nur Varianten von Trend oder Mean Reversion.
- **Volumenbestätigung, Multi-Indikator-Konfluenz:** intuitiv, aber jede Zusatzregel erhöht die Overfitting-Gefahr.
- **Machine Learning auf Kursdaten:** Gu, Kelly & Xiu (2020) zeigen Nutzen bei *sehr vielen* Aktien und Features. Bei einem einzelnen Markt mit wenigen tausend Datenpunkten ist das Signal-Rausch-Verhältnis winzig. Einfache, regularisierte Modelle (S008) sind deshalb oft robuster als komplexe (S009).
- **Regime-Switching:** Hamilton (1989). Regime sind erst im Nachhinein klar erkennbar, live gibt es Verzögerung.

## 3. Trading-Community-Behauptungen (kaum wissenschaftlich geprüft)

- **Smart Money Concepts** (Order Blocks, Fair Value Gaps, CHoCH, Liquidity Sweeps, Inducement): keine belastbaren Peer-Review-Belege. Teilweise Umbenennungen bekannter Ideen (Support/Resistance, Stop-Cluster). → S005 testet Liquidity Sweeps neutral.
- **Fibonacci-Retracements/-Extensions, Candlestick-Muster:** Studien finden überwiegend keinen stabilen Vorteil nach Kosten (z. B. Marshall, Young & Rose 2006 zu Candlesticks).

## 4. Hohe Overfitting-Gefahr (bewusst nicht oder nur vorsichtig eingesetzt)

- **Deep Learning (LSTM, GRU, TCN, Transformer)** auf einzelnen Zeitreihen: viele Parameter, wenige unabhängige Beobachtungen.
- **Reinforcement Learning** für Entry/Exit: instabil, belohnt oft Simulator-Fehler. Höchstens später für Positionsgrößen und nur in Simulation.
- **Volle Kelly-Formel:** braucht exakt bekannte Gewinnwahrscheinlichkeiten, die man nicht hat. Wenn überhaupt, dann Fractional Kelly (¼ bis ½).

## 5. Wie das System Zufallsergebnisse vermeidet

| Gefahr | Gegenmaßnahme im Code |
|---|---|
| Look-Ahead Bias | Signal am Kerzenschluss, Ausführung erst an der nächsten Kerze; Tests prüfen, dass Signale ohne Zukunftsdaten identisch sind |
| Data Leakage (ML) | Training nur mit Zeilen, deren Label zum Zeitpunkt bereits bekannt war (Embargo = Label-Horizont) |
| Overfitting / Parameteroptimierung | Kleine Parameter-Gitter, Anchored Walk-Forward, Bewertung nur Out-of-Sample, Parameter-Stabilität wird gemessen |
| Multiple Testing | Bonferroni-Korrektur über alle getesteten Strategien (vgl. Harvey, Liu & Zhu 2016; Bailey & López de Prado 2014, „Deflated Sharpe Ratio“) |
| Zu optimistische Ausführung | Gebühren, Spread, Slippage (fix + ATR), Gap-Stops, Teilfüllung, 2×-Kosten-Stresstest |
| Glück | Bootstrap-p-Wert, Monte-Carlo-Verteilung von Rendite und Drawdown, Mindestanzahl Trades |
| Survivorship Bias | **Vorhanden:** Die 24 Werte sind heute noch handelbar. Pleite gegangene Coins/Aktien fehlen, Backtests wirken daher eher zu gut. Wird im Report so benannt. |

## 6. Wie institutionelle Systeme arbeiten (vereinfacht)

Getrennte Teams und Module für Research, Ausführung und Risiko. Das Risk Management hat Vetorecht und kann von Strategien nicht überstimmt werden. Neue Modelle laufen erst im „Shadow-Modus“ (Paper) mit. Jede Version ist reproduzierbar (Code-Hash, Datenbereich) und lässt sich zurückrollen. Diese Prinzipien sind hier im Kleinen umgesetzt.
