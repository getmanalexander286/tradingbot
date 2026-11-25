"""Backtesting Engine – nutzt denselben Simulator wie das Paper-Trading."""
from __future__ import annotations

import pandas as pd

from .sim import Account, Costs, sig_rows


def attach_regime(sig: pd.DataFrame, reg: pd.DataFrame, sid: str) -> pd.DataFrame:
    s = sig.copy()
    s["regime"] = reg["trend"].values
    s["vol_regime"] = reg["vol"].values
    if "strategy" not in s:
        s["strategy"] = sid
    return s


def run(df: pd.DataFrame, sig: pd.DataFrame, costs: Costs, risk_cfg: dict | None, capital: float,
        start: int = 0, end: int | None = None, name: str = "bt") -> Account:
    end = len(df) if end is None else end
    acc = Account(name, capital, costs, risk_cfg)
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    vq = (df["volume"] * df["close"]).to_numpy()  # Volumen in Quote-Währung
    rows = sig_rows(sig.iloc[start:end])
    idx = df.index
    for j, i in enumerate(range(start, end)):
        s = rows[j]
        if s["atr"] != s["atr"]:  # NaN -> Warmup
            s = None
        acc.on_bar(idx[i], o[i], h[i], l[i], c[i], vq[i], s if i < end - 1 else None)
    if end > start:
        acc.close_all(idx[end - 1], c[end - 1], float(sig["atr"].iloc[end - 1] or 0))
    return acc


def buy_and_hold(df, start, end, costs: Costs, capital):
    o = df["open"].iloc[start]
    fill = costs.buy(o, 0)
    qty = capital / (fill * (1 + costs.fee_rate))
    eq = qty * df["close"].iloc[start:end]
    return [(str(t), float(e)) for t, e in eq.items()]
