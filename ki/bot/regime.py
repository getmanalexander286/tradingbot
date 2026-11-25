"""Market Regime Detector (regelbasiert, kausal, erklärbar).

Trend-Label: STRONG_BULL, WEAK_BULL, SIDEWAYS, WEAK_BEAR, STRONG_BEAR, STRESS
Vol-Label:   HIGH_VOL, NORMAL_VOL, LOW_VOL
"""
import numpy as np
import pandas as pd

from . import indicators as ind

TREND_LABELS = ["STRONG_BULL", "WEAK_BULL", "SIDEWAYS", "WEAK_BEAR", "STRONG_BEAR", "STRESS"]


def detect(df: pd.DataFrame) -> pd.DataFrame:
    a = ind.atr(df, 14)
    adx = ind.adx(df, 14)
    e50 = ind.ema(df["close"], 50)
    slope = (e50 - e50.shift(10)) / a  # Trendsteigung in ATR-Einheiten
    vol = a / df["close"]
    vol_rank = ind.rolling_pct_rank(vol, 500, 100)
    ret20 = ind.roc(df["close"], 20)
    dd30 = df["close"] / df["close"].rolling(30).max() - 1

    trend = np.full(len(df), "SIDEWAYS", dtype=object)
    up, dn = slope > 0.5, slope < -0.5
    trend[(adx > 20) & up] = "WEAK_BULL"
    trend[(adx > 30) & up & (slope > 1.5)] = "STRONG_BULL"
    trend[(adx > 20) & dn] = "WEAK_BEAR"
    trend[(adx > 30) & dn & (slope < -1.5)] = "STRONG_BEAR"
    stress = (vol_rank > 0.95) & ((ret20 < -0.10) | (dd30 < -6 * vol))
    trend[stress.fillna(False).values] = "STRESS"

    vlab = np.where(vol_rank > 0.7, "HIGH_VOL", np.where(vol_rank < 0.3, "LOW_VOL", "NORMAL_VOL"))
    out = pd.DataFrame({"trend": trend, "vol": vlab, "adx": adx, "slope": slope, "vol_rank": vol_rank}, index=df.index)
    out.loc[adx.isna() | vol_rank.isna(), ["trend", "vol"]] = "UNKNOWN"
    return out
