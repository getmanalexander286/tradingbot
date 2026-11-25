"""Statistische Validierung: Monte Carlo, Bootstrap, Signifikanz, Urteil."""
from __future__ import annotations

import numpy as np


def bootstrap_pvalue(x, n=5000, seed=0):
    """Einseitiger p-Wert für mittlere Trade-Rendite > 0 (zentrierter Bootstrap)."""
    x = np.asarray(x, float)
    if len(x) < 5:
        return 1.0
    rng = np.random.default_rng(seed)
    centered = x - x.mean()
    means = rng.choice(centered, (n, len(x)), replace=True).mean(axis=1)
    return float((means >= x.mean()).mean())


def monte_carlo(eq_rets, runs=2000, seed=1):
    """Zieht Trades mit Zurücklegen -> Verteilung von Endrendite und Max Drawdown."""
    x = np.asarray(eq_rets, float)
    if len(x) < 5:
        return {}
    rng = np.random.default_rng(seed)
    sims = rng.choice(x, (runs, len(x)), replace=True)
    eq = np.cumprod(1 + sims, axis=1)
    final = eq[:, -1] - 1
    dd = (1 - eq / np.maximum.accumulate(eq, axis=1)).max(axis=1)
    return {"ret_p5": float(np.percentile(final, 5)), "ret_median": float(np.median(final)),
            "ret_p95": float(np.percentile(final, 95)), "prob_loss": float((final < 0).mean()),
            "maxdd_median": float(np.median(dd)), "maxdd_p95": float(np.percentile(dd, 95))}


def t_stat(x):
    x = np.asarray(x, float)
    if len(x) < 3 or x.std(ddof=1) == 0:
        return 0.0
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x)))


def verdict(m: dict, stress: dict, mc: dict, p_adj: float, min_trades: int, max_dd_limit: float) -> tuple[str, str]:
    n = m.get("n_trades", 0)
    pf = m.get("profit_factor") or 0
    if n < min_trades:
        return "INSUFFICIENT", f"Nur {n} Out-of-Sample-Trades (< {min_trades}) – zu wenig Evidenz für ein Urteil."
    if (m.get("expectancy") or 0) <= 0 or pf < 1.0:
        return "NO_EDGE", f"Out-of-Sample nicht profitabel (PF {pf:.2f}) – kein Vorteil nachweisbar."
    spf = stress.get("profit_factor") or 0
    if p_adj < 0.05 and pf > 1.1 and spf > 1.0 and m.get("max_drawdown", 1) < max_dd_limit and mc.get("ret_p5", -1) > -0.5:
        return "EDGE_PLAUSIBLE", (f"OOS profitabel (PF {pf:.2f}), signifikant nach Mehrfachtest-Korrektur "
                                  f"(p={p_adj:.3f}), übersteht doppelte Kosten (PF {spf:.2f}). Weiter Paper-Trading.")
    why = []
    if p_adj >= 0.05:
        why.append(f"nicht signifikant (p={p_adj:.2f})")
    if spf <= 1.0:
        why.append("bricht bei doppelten Kosten ein")
    if pf <= 1.1:
        why.append("Profit Factor zu knapp")
    if m.get("max_drawdown", 1) >= max_dd_limit:
        why.append("Drawdown zu hoch")
    return "UNCLEAR", "Leicht positiv, aber " + ", ".join(why or ["nicht robust"]) + " – kann Zufall sein."


VERDICT_RANK = {"NO_EDGE": 0, "INSUFFICIENT": 1, "UNCLEAR": 2, "EDGE_PLAUSIBLE": 3}
