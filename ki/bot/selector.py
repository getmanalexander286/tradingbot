"""Strategy Selection Engine (Hybrid).

Wählt je Anlageklasse + Marktregime (z. B. "krypto:WEAK_BULL") die Strategie mit der besten OUT-OF-SAMPLE-Evidenz in
genau diesem Regime. Ohne ausreichende Evidenz -> NO TRADE.
Widersprüche zwischen geeigneten Strategien -> halbe Position oder kein Trade.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from .validation import t_stat

NEVER_TRADE = {"STRESS", "UNKNOWN"}


def regime_table(trades: list[dict], min_n: int = 8, min_t: float = 1.0) -> dict:
    groups = defaultdict(lambda: defaultdict(list))
    for t in trades:
        groups[t.get("regime_key", t.get("regime"))][t["strategy"]].append(t["eq_ret"])
    table = {}
    for reg, by_s in groups.items():
        if reg is None or str(reg).split(":")[-1] in NEVER_TRADE:
            continue
        rows = []
        for sid, x in by_s.items():
            ts = t_stat(x)
            if len(x) >= min_n and np.mean(x) > 0 and ts >= min_t:
                rows.append({"sid": sid, "n": len(x), "mean": float(np.mean(x)), "t": ts})
        if rows:
            table[reg] = sorted(rows, key=lambda r: -r["t"])
    return table


def hybrid_signals(index, regimes: pd.Series, sigs: dict[str, pd.DataFrame], table: dict,
                   lo: int, hi: int, out: pd.DataFrame | None = None) -> pd.DataFrame:
    """Füllt Zeilen [lo, hi) des Hybrid-Signals anhand der Regime-Tabelle."""
    if out is None:
        any_sig = next(iter(sigs.values()))
        out = pd.DataFrame(index=index)
        out["entry"] = False
        out["exit"] = True
        out["stop_atr"] = 2.5
        out["tp_atr"] = np.nan
        out["max_hold"] = np.nan
        out["confidence"] = 0.0
        out["size_mult"] = 1.0
        out["atr"] = any_sig["atr"].values
        out["strategy"] = "NONE"
        out["reason"] = "Kein Regime mit nachgewiesenem Vorteil -> NO TRADE"
    reg = regimes.values
    rng = np.zeros(len(index), bool)
    rng[lo:hi] = True
    for r, rows in table.items():
        mask = rng & (reg == r)
        if not mask.any():
            continue
        best = rows[0]["sid"]
        s = sigs[best]
        m = np.where(mask)[0]
        out.iloc[m, out.columns.get_loc("entry")] = s["entry"].values[m]
        out.iloc[m, out.columns.get_loc("exit")] = s["exit"].values[m]
        for col in ("stop_atr", "tp_atr", "max_hold"):
            out.iloc[m, out.columns.get_loc(col)] = s[col].values[m]
        out.iloc[m, out.columns.get_loc("confidence")] = rows[0]["t"]
        out.iloc[m, out.columns.get_loc("strategy")] = best
        out.iloc[m, out.columns.get_loc("reason")] = (
            f"Regime {r}: {best} hat beste OOS-Evidenz (n={rows[0]['n']}, t={rows[0]['t']:.2f})")
        others = [x["sid"] for x in rows[1:]]
        if others:
            n_exit = np.sum([sigs[o]["exit"].values[m] for o in others], axis=0)
            frac = n_exit / len(others)
            mult = np.where(frac > 0.5, 0.0, np.where(frac > 0, 0.5, 1.0))  # Konflikt -> kleiner / skip
            out.iloc[m, out.columns.get_loc("size_mult")] = mult
    return out
