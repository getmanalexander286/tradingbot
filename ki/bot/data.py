"""Market Data Engine + Data Validation Engine (24 Märkte).

Die Marktliste wird NUR GELESEN aus der gemeinsamen ../config.yaml der
anderen drei Bots – so laufen alle Bots auf denselben Werten.
Krypto: Kraken (wie die anderen Bots), Aktien: Yahoo Finance. Nur Lesen.
Synthetische Daten: ausschließlich für Offline-Tests der Software.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

INTERVAL_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
COLS = ["open", "high", "low", "close", "volume"]
MAX_AGE_DAYS = {"krypto": 2.5, "aktie": 5.5}  # Aktien: Wochenende + Feiertag erlaubt


class DataError(Exception):
    """Datenproblem -> für diesen Markt wird nicht gehandelt."""


def markets_from_config(path="../config.yaml") -> list[dict]:
    import yaml
    cfg = yaml.safe_load(Path(path).read_text())
    out = [{"symbol": s, "klasse": "krypto", "name": s.split("/")[0]} for s in cfg.get("krypto", [])]
    out += [{"symbol": a["symbol"], "klasse": "aktie", "name": a.get("name", a["symbol"])} for a in cfg.get("aktien", [])]
    if not out:
        raise DataError(f"Keine Märkte in {path}")
    return out


def _frame(rows_index, o, h, l, c, v):
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=rows_index).astype(float)
    df.index = pd.DatetimeIndex(df.index).tz_convert("UTC") if df.index.tz is not None else pd.DatetimeIndex(df.index).tz_localize("UTC")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df.dropna(subset=["open", "high", "low", "close"])


def fetch_kraken(symbol: str, interval: str = "1d", exchange=None) -> pd.DataFrame:
    if exchange is None:
        import ccxt
        exchange = ccxt.kraken({"enableRateLimit": True})
    ex = exchange
    last = None
    for attempt in range(3):
        try:
            k = ex.fetch_ohlcv(symbol, timeframe=interval, limit=720)  # Kraken liefert max. 720 Kerzen
            if k:
                k = np.array(k, dtype=float)
                idx = pd.to_datetime(k[:, 0], unit="ms", utc=True)
                return _frame(idx, k[:, 1], k[:, 2], k[:, 3], k[:, 4], k[:, 5])
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise DataError(f"{symbol}: Kraken nicht erreichbar ({type(last).__name__ if last else 'leer'})")


def fetch_yahoo(symbol: str, period: str = "5y") -> pd.DataFrame:
    import yfinance as yf
    last = None
    for attempt in range(3):
        try:
            d = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
            if len(d):
                idx = pd.DatetimeIndex(d.index.date).tz_localize("UTC")  # Tageskerze = Kalendertag
                return _frame(idx, d["Open"].values, d["High"].values, d["Low"].values, d["Close"].values, d["Volume"].values)
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise DataError(f"{symbol}: Yahoo nicht erreichbar ({type(last).__name__ if last else 'leer'})")


def drop_unfinished(df: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Nur abgeschlossene Tageskerzen (heutige Kerze ist noch offen)."""
    now = now or pd.Timestamp.now(tz="UTC")
    return df[df.index < now.normalize()]


def load_or_update(market: dict, interval: str = "1d", data_dir: str = "data", exchange=None) -> pd.DataFrame:
    """Lädt neue Kerzen, ergänzt den Cache (Historie wächst über die Zeit)."""
    path = Path(data_dir) / (market["symbol"].replace("/", "_") + f"_{interval}.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    new = fetch_kraken(market["symbol"], interval, exchange) if market["klasse"] == "krypto" else fetch_yahoo(market["symbol"])
    if path.exists():
        old = pd.read_csv(path, index_col=0, parse_dates=True)
        old.index = pd.DatetimeIndex(old.index, tz="UTC") if old.index.tz is None else old.index
        df = pd.concat([old[old.index < new.index[0]], new])
    else:
        df = new
    df = drop_unfinished(df)
    df.to_csv(path)
    return df[COLS]


def validate(df: pd.DataFrame, klasse: str = "krypto", check_age: bool = False, min_bars: int = 250) -> tuple[pd.DataFrame, list[str]]:
    """Gibt (reparierte Daten, Warnungen) zurück oder wirft DataError."""
    warnings = []
    if len(df) < min_bars:
        raise DataError(f"zu wenige Kerzen ({len(df)})")
    if df[["open", "high", "low", "close"]].isna().any().any():
        raise DataError("NaN-Werte in Kursdaten")
    if not df.index.is_monotonic_increasing or df.index.duplicated().any():
        raise DataError("Zeitindex nicht sortiert oder doppelt")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise DataError("Preise <= 0")
    hi_ok = df[["open", "close"]].max(axis=1)
    lo_ok = df[["open", "close"]].min(axis=1)
    bad = (df["high"] < hi_ok * 0.995) | (df["low"] > lo_ok * 1.005)
    if bad.sum() > 3:
        raise DataError(f"{int(bad.sum())} Kerzen mit inkonsistentem High/Low")
    if ((df["high"] < hi_ok) | (df["low"] > lo_ok)).any():  # kleine Rundungsfehler reparieren
        df = df.copy()
        df["high"] = np.maximum(df["high"], hi_ok)
        df["low"] = np.minimum(df["low"], lo_ok)
        warnings.append("kleine High/Low-Rundungsfehler repariert")
    if (np.log(df["close"]).diff().abs() > 0.6).any():
        warnings.append("extreme Tagesbewegung >60 % – Daten prüfen")
    df = df.copy()
    df["volume"] = df["volume"].fillna(0).clip(lower=0)
    if check_age:
        age = pd.Timestamp.now(tz="UTC") - (df.index[-1] + pd.Timedelta(days=1))
        if age > pd.Timedelta(days=MAX_AGE_DAYS.get(klasse, 2.5)):
            raise DataError(f"Daten veraltet (letzte Kerze {df.index[-1].date()})")
    return df, warnings


def synthetic(n: int = 1500, seed: int = 7, start_price: float = 100.0, weekdays_only=False) -> pd.DataFrame:
    """Regime-wechselnde Tages-Testdaten. Nur für Software-Tests!"""
    rng = np.random.default_rng(seed)
    logp, out = np.log(start_price), []
    regime, left, anchor = 0, 0, logp
    for _ in range(n):
        if left <= 0:
            regime = rng.choice([0, 1, 2, 3], p=[0.3, 0.25, 0.35, 0.1])
            left, anchor = int(rng.integers(40, 200)), logp
        left -= 1
        r = {0: 0.0015 + 0.03 * rng.standard_t(4) / 1.4,
             1: -0.0012 + 0.032 * rng.standard_t(4) / 1.4,
             2: -0.04 * (logp - anchor) + 0.022 * rng.standard_t(4) / 1.4,
             3: -0.003 + 0.06 * rng.standard_t(3) / 1.7}[regime]
        logp += float(np.clip(r, -0.4, 0.4))
        out.append(logp)
    close = np.exp(np.array(out))
    open_ = np.r_[start_price, close[:-1]] * np.exp(rng.normal(0, 0.002, n))
    wick = np.abs(rng.normal(0, 0.012, n)) * close
    idx = pd.bdate_range("2019-01-01", periods=n, tz="UTC") if weekdays_only else pd.date_range("2019-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + wick, "low": np.minimum(open_, close) - wick,
                         "close": close, "volume": rng.lognormal(10, 0.5, n)}, index=idx)


def synthetic_universe(markets: list[dict], n_crypto=720, n_stock=1260, seed=0, end=None) -> dict[str, pd.DataFrame]:
    """Testuniversum mit derselben Struktur wie die echten 24 Märkte."""
    out = {}
    end = end or pd.Timestamp("2026-11-24", tz="UTC")
    for i, m in enumerate(markets):
        if m["klasse"] == "krypto":
            df = synthetic(n_crypto, seed + i)
        else:
            df = synthetic(n_stock, seed + i, weekdays_only=True)
        shift = end - df.index[-1]
        df.index = df.index + pd.Timedelta(days=shift.days)
        out[m["symbol"]] = df
    return out
