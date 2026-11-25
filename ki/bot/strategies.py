"""Strategy Library. Long-only (Spot, kein Hebel).

Jede Strategie liefert pro Kerze (berechnet beim Schlusskurs, ausgeführt erst
an der NÄCHSTEN Kerze): entry, exit, stop_atr, tp_atr, max_hold, confidence.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from . import indicators as ind


def grid(**axes):
    keys = list(axes)
    return [dict(zip(keys, v)) for v in itertools.product(*axes.values())]


class Strategy:
    sid = "S000"
    name = "base"
    family = ""
    evidence = ""  # Einordnung laut RESEARCH.md
    param_grid: list[dict] = [{}]

    def raw(self, df: pd.DataFrame, **p) -> dict:
        raise NotImplementedError

    def signals(self, df: pd.DataFrame, **p) -> pd.DataFrame:
        r = self.raw(df, **p)
        n = len(df)
        out = pd.DataFrame(index=df.index)
        out["entry"] = r["entry"].fillna(False).astype(bool)
        out["exit"] = r["exit"].fillna(False).astype(bool)
        out["stop_atr"] = float(p.get("stop", 2.5))
        out["tp_atr"] = float(p["tp"]) if p.get("tp") else np.nan
        out["max_hold"] = float(p["hold"]) if p.get("hold") else np.nan
        out["confidence"] = r.get("confidence", pd.Series(np.full(n, 0.5), df.index))
        out["atr"] = ind.atr(df, 14)
        out.loc[out["atr"].isna(), "entry"] = False
        return out


class EMATrend(Strategy):
    sid, name, family = "S001", "EMA Trend Following", "Trend"
    evidence = "empirisch belegt (Trend/Time-Series-Momentum), Parameter oft überoptimiert"
    param_grid = grid(fast=[20, 50], slow=[100, 200], stop=[3.0])

    def raw(self, df, fast, slow, **_):
        f, s = ind.ema(df["close"], fast), ind.ema(df["close"], slow)
        cond = (f > s) & (df["close"] > s)
        return {"entry": cond, "exit": ~cond}


class RSIMeanReversion(Strategy):
    sid, name, family = "S002", "RSI Mean Reversion", "Mean Reversion"
    evidence = "plausibel, kurzfristige Umkehr teils belegt; stark regimeabhängig"
    param_grid = grid(entry=[25, 30], exit_=[50, 60], stop=[2.0], hold=[20])

    def raw(self, df, entry, exit_, **_):
        r = ind.rsi(df["close"], 14)
        trend_ok = df["close"] > ind.sma(df["close"], 200)  # nur Dips im übergeordneten Aufwärtstrend
        return {"entry": (r < entry) & trend_ok, "exit": r > exit_}


class DonchianBreakout(Strategy):
    sid, name, family = "S003", "Donchian Volatility Breakout", "Breakout"
    evidence = "empirisch belegt als Trendfolge-Variante (Turtle-Typ), hohe Fehlsignalrate"
    param_grid = grid(n=[20, 55], exit_n=[10, 20], stop=[2.5])

    def raw(self, df, n, exit_n, **_):
        _, hi = ind.donchian(df, n)
        lo, _ = ind.donchian(df, exit_n)
        return {"entry": df["close"] > hi.shift(1), "exit": df["close"] < lo.shift(1)}


class MomentumVolume(Strategy):
    sid, name, family = "S004", "Momentum + Volume Confirmation", "Momentum"
    evidence = "Momentum belegt; Volumenbestätigung plausibel, schwach belegt"
    param_grid = grid(lb=[20, 60], vmult=[1.2, 1.5], stop=[2.5])

    def raw(self, df, lb, vmult, **_):
        m = ind.roc(df["close"], lb)
        vol_ok = df["volume"] > vmult * ind.sma(df["volume"], 20)
        return {"entry": (m > 0) & vol_ok & (df["close"] > df["open"]), "exit": m < 0}


class LiquiditySweep(Strategy):
    sid, name, family = "S005", "Liquidity Sweep / Stop Hunt Reversal (SMC)", "Market Structure"
    evidence = "Trading-Community-Behauptung, kaum wissenschaftlich belegt – wird hier getestet"
    param_grid = grid(n=[20, 50], tp=[2.0, 3.0], stop=[1.5], hold=[30])

    def raw(self, df, n, **_):
        prev_low = df["low"].rolling(n).min().shift(1)  # Liquiditätspool unter Equal Lows
        sweep = (df["low"] < prev_low) & (df["close"] > prev_low)  # unterschritten, dann zurückgewiesen
        rejection = (df["close"] - df["low"]) > 0.6 * (df["high"] - df["low"])  # Rejection Candle
        return {"entry": sweep & rejection, "exit": pd.Series(False, df.index)}


class BollingerMR(Strategy):
    sid, name, family = "S006", "Bollinger Band Mean Reversion", "Mean Reversion"
    evidence = "plausibel in Seitwärtsphasen, verliert in starken Trends"
    param_grid = grid(n=[20], k=[2.0, 2.5], stop=[2.0, 3.0], hold=[20])

    def raw(self, df, n, k, **_):
        lo, mid, _ = ind.bollinger(df["close"], n, k)
        return {"entry": df["close"] < lo, "exit": df["close"] > mid}


class TSMomentum(Strategy):
    sid, name, family = "S007", "Time-Series Momentum (vol-gefiltert)", "Momentum"
    evidence = "empirisch gut belegt (Moskowitz/Ooi/Pedersen 2012; Krypto: Liu/Tsyvinski 2021)"
    param_grid = grid(lb=[30, 90, 180], stop=[4.0])

    def raw(self, df, lb, **_):
        m = ind.roc(df["close"], lb)
        return {"entry": m > 0, "exit": m < 0}


# ---------------------------------------------------------------- Machine Learning

_ML_CACHE: dict = {}


def ml_features(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"]
    a = ind.atr(df, 14)
    lo, mid, hi = ind.bollinger(c, 20, 2)
    X = pd.DataFrame(index=df.index)
    for k in (1, 3, 6, 12, 24, 72):
        X[f"ret{k}"] = np.log(c / c.shift(k))
    X["rsi"] = ind.rsi(c, 14) / 100
    X["adx"] = ind.adx(df, 14) / 100
    X["vol"] = a / c
    X["d_ema20"] = (c - ind.ema(c, 20)) / a
    X["d_ema100"] = (c - ind.ema(c, 100)) / a
    X["bb_pos"] = (c - lo) / (hi - lo)
    X["vol_z"] = ind.zscore(np.log(df["volume"] + 1), 50)
    return X


def prepare_ml(dfs: dict, models=("logit", "gbm"), horizon=5, cost=0.01, retrain_days=60,
               train_days=1095, min_rows=1500):
    """Gepooltes Walk-Forward-Training über ALLE Märkte (mehr Daten, weniger Overfitting).

    Für Vorhersagen ab Datum d werden nur Zeilen genutzt, deren Label (Rendite
    über `horizon` Kerzen) VOR d bekannt war: label_time < d. Kein Data Leakage.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    parts = []
    for mk, df in dfs.items():
        X = ml_features(df)
        fwd = df["close"].shift(-horizon) / df["close"] - 1
        X["_y"] = (fwd > cost).astype(float).where(fwd.notna())
        X["_label_time"] = pd.Series(df.index.tz_convert(None), index=df.index).shift(-horizon)
        X["_mk"] = mk
        X["_t"] = df.index.tz_convert(None)
        parts.append(X)
    P = pd.concat(parts, ignore_index=True)
    feat = [c for c in P.columns if not c.startswith("_")]
    ok = P[feat].notna().all(axis=1).values
    t = P["_t"].values
    lt = P["_label_time"].values
    y = P["_y"].values
    probs = {m: np.full(len(P), np.nan) for m in models}
    t0, t_end = P["_t"].min().tz_localize("UTC"), P["_t"].max().tz_localize("UTC")
    d = t0 + pd.Timedelta(days=200)
    while d <= t_end:
        d_next = d + pd.Timedelta(days=retrain_days)
        dn = d.tz_convert(None).to_datetime64()
        dl = (d - pd.Timedelta(days=train_days)).tz_convert(None).to_datetime64()
        tr = ok & (~pd.isna(lt)) & (lt < dn) & (t >= dl) & ~np.isnan(y)
        pr = ok & (t >= dn) & (t < d_next.tz_convert(None).to_datetime64())
        if tr.sum() >= min_rows and pr.any() and len(np.unique(y[tr])) == 2:
            Xtr, ytr, Xpr = P.loc[tr, feat].values, y[tr].astype(int), P.loc[pr, feat].values
            for m in models:
                clf = (make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500)) if m == "logit" else
                       HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05,
                                                      l2_regularization=1.0, random_state=0))
                clf.fit(Xtr, ytr)
                probs[m][pr] = clf.predict_proba(Xpr)[:, 1]
        d = d_next
    _ML_CACHE.clear()
    for m in models:
        for mk, idx in P.groupby("_mk").groups.items():
            _ML_CACHE[(m, mk)] = pd.Series(probs[m][idx], index=pd.DatetimeIndex(P.loc[idx, "_t"]).tz_localize("UTC"))


class MLLogit(Strategy):
    sid, name, family = "S008", "ML Logistic Regression", "Machine Learning"
    evidence = "einfaches, robustes Modell, gepoolt über 24 Märkte; Vorteil in Kursdaten meist klein"
    model = "logit"
    param_grid = grid(thr=[0.55, 0.6], stop=[2.5], hold=[10])

    def raw(self, df, thr, **_):
        cached = _ML_CACHE.get((self.model, df.attrs.get("market")))
        if cached is None:
            raise RuntimeError("prepare_ml() muss vor ML-Signalen laufen")
        p = cached.reindex(df.index)
        base = p.rolling(250, min_periods=60).mean()  # relativ zur Grundrate (kausal)
        return {"entry": p > np.maximum(thr, base + 0.05), "exit": p < 0.5, "confidence": p.fillna(0.5)}


class MLGBM(MLLogit):
    sid, name, family = "S009", "ML Gradient Boosting", "Machine Learning"
    evidence = "stark, aber anfällig für Overfitting bei verrauschten Kursdaten"
    model = "gbm"


ALL = [EMATrend(), RSIMeanReversion(), DonchianBreakout(), MomentumVolume(), LiquiditySweep(),
       BollingerMR(), TSMomentum(), MLLogit(), MLGBM()]
BY_ID = {s.sid: s for s in ALL}
