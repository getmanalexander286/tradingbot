"""Performance-Kennzahlen."""
import numpy as np
import pandas as pd

BARS_PER_YEAR = {"15m": 35040, "1h": 8760, "4h": 2190, "1d": 365}


def equity_series(curve):
    if not curve:
        return pd.Series(dtype=float)
    s = pd.Series([e for _, e in curve], index=pd.to_datetime([t for t, _ in curve], utc=True))
    return s[~s.index.duplicated(keep="last")]


def drawdowns(eq: pd.Series):
    return 1 - eq / eq.cummax()


def compute(curve, trades, interval="4h", start_capital=None):
    eq = equity_series(curve)
    out = {"n_trades": len(trades)}
    if len(eq) < 2:
        return out
    bpy = BARS_PER_YEAR.get(interval, 2190)
    r = eq.pct_change().dropna()
    cap = start_capital or eq.iloc[0]
    dd = drawdowns(eq)
    years = max(len(eq) / bpy, 1e-9)
    total = eq.iloc[-1] / cap - 1
    downside = r[r < 0].std()
    out.update({
        "start_equity": float(cap), "end_equity": float(eq.iloc[-1]), "total_return": float(total),
        "cagr": float((1 + total) ** (1 / years) - 1) if total > -1 else -1.0,
        "sharpe": float(r.mean() / r.std() * np.sqrt(bpy)) if r.std() > 0 else 0.0,
        "sortino": float(r.mean() / downside * np.sqrt(bpy)) if downside and downside > 0 else 0.0,
        "max_drawdown": float(dd.max()), "avg_drawdown": float(dd[dd > 0].mean()) if (dd > 0).any() else 0.0,
    })
    out["recovery_factor"] = float(total / out["max_drawdown"]) if out["max_drawdown"] > 0 else 0.0
    if trades:
        pnl = np.array([t["pnl"] for t in trades])
        wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
        out.update({
            "win_rate": float(len(wins) / len(pnl)), "loss_rate": float(len(losses) / len(pnl)),
            "avg_win": float(wins.mean()) if len(wins) else 0.0,
            "avg_loss": float(losses.mean()) if len(losses) else 0.0,
            "profit_factor": float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf"),
            "expectancy": float(pnl.mean()), "expectancy_R": float(np.mean([t["R"] for t in trades])),
            "avg_bars_held": float(np.mean([t["bars"] for t in trades])),
            "fees_paid": float(sum(t["fees"] for t in trades)),
        })
    return out


def clean(d):
    """inf/nan -> JSON-freundlich."""
    if isinstance(d, dict):
        return {k: clean(v) for k, v in d.items()}
    if isinstance(d, list):
        return [clean(v) for v in d]
    if isinstance(d, (float, np.floating)):
        if np.isnan(d):
            return None
        if np.isinf(d):
            return 999.0 if d > 0 else -999.0
        return float(d)
    if isinstance(d, np.integer):
        return int(d)
    if isinstance(d, np.bool_):
        return bool(d)
    return d


def portfolio_curve(curves: list, capitals: list) -> list:
    """Summiert Teildepot-Kurven (unterschiedliche Kalender) zu einer Depotkurve."""
    series = []
    for cv, cap in zip(curves, capitals):
        s = equity_series(cv)
        series.append(s if len(s) else pd.Series([cap], index=[pd.NaT]).dropna())
    idx = sorted(set().union(*[set(s.index) for s in series]))
    if not idx:
        return []
    total = sum(s.reindex(idx).ffill().fillna(cap) for s, cap in zip(series, capitals))
    return [(str(t), float(v)) for t, v in total.items()]
