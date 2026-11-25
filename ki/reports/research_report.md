# KI-Research-Report – 24 Märkte (Tageskerzen)
Erstellt: 2026-11-25T09:40:34+00:00  |  Daten: kraken+yahoo  |  Zeitraum: 2021-11-25 – 2026-11-24
Out-of-Sample ab: 2023-09-04  |  Getestete Hypothesen: 10 (Bonferroni-korrigiert)
Depot je Strategie: 24 Teildepots à 100 € (wie die MA-Bots)

| ID | Strategie | Trades | Depot | PF | Sharpe | MaxDD | 2x Kosten PF | p (korr.) | Urteil |
|---|---|---|---|---|---|---|---|---|---|
| S001 | EMA Trend Following | 227 | +0.2% | 1.03 | 0.04 | 3.4% | 0.80 | 1.000 | UNCLEAR |
| S002 | RSI Mean Reversion | 22 | -0.0% | 1.00 | -0.00 | 0.5% | 0.72 | 1.000 | INSUFFICIENT |
| S003 | Donchian Volatility Breakout | 115 | +0.0% | 1.00 | 0.01 | 2.7% | 0.78 | 1.000 | UNCLEAR |
| S004 | Momentum + Volume Confirmation | 222 | +0.5% | 1.06 | 0.08 | 4.8% | 0.83 | 1.000 | UNCLEAR |
| S005 | Liquidity Sweep / Stop Hunt Reversal (SMC) | 243 | -5.7% | 0.60 | -1.28 | 6.3% | 0.45 | 1.000 | NO_EDGE |
| S006 | Bollinger Band Mean Reversion | 155 | -1.3% | 0.71 | -0.62 | 1.7% | 0.52 | 1.000 | NO_EDGE |
| S007 | Time-Series Momentum (vol-gefiltert) | 320 | -1.8% | 0.78 | -0.31 | 4.0% | 0.60 | 1.000 | NO_EDGE |
| S008 | ML Logistic Regression | 140 | -0.5% | 0.80 | -0.29 | 1.4% | 0.54 | 1.000 | NO_EDGE |
| S009 | ML Gradient Boosting | 360 | -1.9% | 0.71 | -0.75 | 2.2% | 0.42 | 1.000 | NO_EDGE |
| HYBRID | Hybrid (Regime-Auswahl) | 0 | +0.0% | 0.00 | 0.00 | 0.0% | 0.00 | 1.000 | INSUFFICIENT |

Buy & Hold (alle Märkte, gleicher Zeitraum): -23.3%, MaxDD 39.4%

## Begründungen
- **S001**: Leicht positiv, aber nicht signifikant (p=1.00), bricht bei doppelten Kosten ein, Profit Factor zu knapp – kann Zufall sein.
- **S002**: Nur 22 Out-of-Sample-Trades (< 50) – zu wenig Evidenz für ein Urteil.
- **S003**: Leicht positiv, aber nicht signifikant (p=1.00), bricht bei doppelten Kosten ein, Profit Factor zu knapp – kann Zufall sein.
- **S004**: Leicht positiv, aber nicht signifikant (p=1.00), bricht bei doppelten Kosten ein, Profit Factor zu knapp – kann Zufall sein.
- **S005**: Out-of-Sample nicht profitabel (PF 0.60) – kein Vorteil nachweisbar.
- **S006**: Out-of-Sample nicht profitabel (PF 0.71) – kein Vorteil nachweisbar.
- **S007**: Out-of-Sample nicht profitabel (PF 0.78) – kein Vorteil nachweisbar.
- **S008**: Out-of-Sample nicht profitabel (PF 0.80) – kein Vorteil nachweisbar.
- **S009**: Out-of-Sample nicht profitabel (PF 0.71) – kein Vorteil nachweisbar.
- **HYBRID**: Nur 0 Out-of-Sample-Trades (< 50) – zu wenig Evidenz für ein Urteil.

**Hinweis:** Vergangene Ergebnisse garantieren nichts. EDGE_PLAUSIBLE heißt nur: weiter im Paper-Trading beobachten.