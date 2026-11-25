"""Kerntests: kein Look-Ahead, realistische Kosten, Stops, Risk-Limits, Paper-only, Isolation."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bot import backtest, data, paper, regime, strategies
from bot.risk import HARD_LIMITS, RiskManager
from bot.sim import Account, Costs
from bot.strategies import ALL

KI = Path(__file__).resolve().parents[1]
MARKETS = [{"symbol": f"C{i}/EUR", "klasse": "krypto", "name": f"C{i}"} for i in range(3)] + \
          [{"symbol": f"A{i}.DE", "klasse": "aktie", "name": f"A{i}"} for i in range(2)]


def _universe(cut=None):
    dfs = data.synthetic_universe(MARKETS, n_crypto=720, n_stock=900, seed=3)
    if cut is not None:
        dfs = {m: df[df.index < cut] for m, df in dfs.items()}
    for m, df in dfs.items():
        df.attrs["market"] = m
    return dfs


@pytest.mark.parametrize("strat", ALL, ids=lambda s: s.sid)
def test_no_lookahead(strat):
    """Signale bis zum Stichtag dürfen sich nicht ändern, wenn Zukunftsdaten fehlen (auch gepooltes ML)."""
    full = _universe()
    cut = pd.Timestamp("2026-06-01", tz="UTC")
    p = strat.param_grid[0]
    strategies.prepare_ml(full)
    a = {m: strat.signals(df, **p) for m, df in full.items()}
    part = _universe(cut)
    strategies.prepare_ml(part)
    for m, df in part.items():
        b = strat.signals(df, **p)
        pd.testing.assert_series_equal(a[m]["entry"].loc[b.index], b["entry"])
        pd.testing.assert_series_equal(a[m]["exit"].loc[b.index], b["exit"])


def test_regime_no_lookahead():
    df = data.synthetic(900, seed=2)
    a = regime.detect(df).iloc[:700]
    b = regime.detect(df.iloc[:700])
    assert (a["trend"].values == b["trend"].values).all()


def _flat_df(n=50, px=100.0):
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"open": px, "high": px * 1.001, "low": px * 0.999, "close": px, "volume": 1e6}, index=idx)


def _sig(df, entry_at=None, exit_at=None, stop=2.0):
    s = pd.DataFrame(index=df.index)
    s["entry"] = False
    s["exit"] = False
    if entry_at is not None:
        s.iloc[entry_at, 0] = True
    if exit_at is not None:
        s.iloc[exit_at, 1] = True
    s["stop_atr"], s["tp_atr"], s["max_hold"], s["confidence"] = stop, np.nan, np.nan, 0.5
    s["atr"], s["regime"], s["vol_regime"], s["strategy"] = 1.0, "SIDEWAYS", "LOW_VOL", "T"
    return s


RISK = {"risk_per_trade": 0.02, "max_position_frac": 1.0, "limits_enabled": False}


def test_round_trip_costs_lose_money():
    df = _flat_df()
    acc = backtest.run(df, _sig(df, 5, 10), Costs(), RISK, 100)
    assert len(acc.trades) == 1 and acc.trades[0]["pnl"] < 0 and acc.trades[0]["fees"] > 0


def test_execution_next_bar_open():
    df = _flat_df()
    df.iloc[6, df.columns.get_loc("open")] = 105.0
    df.iloc[6, df.columns.get_loc("high")] = 105.2
    acc = backtest.run(df, _sig(df, 5, 10), Costs(spread_bps=0, slippage_bps=0, slippage_atr_frac=0), RISK, 100)
    assert acc.trades[0]["entry"] == pytest.approx(105.0)


def test_stop_gap_fills_worse_than_stop():
    df = _flat_df()
    df.iloc[8, :4] = [90.0, 90.5, 89.0, 90.0]
    acc = backtest.run(df, _sig(df, 5), Costs(), RISK, 100)
    t = acc.trades[0]
    assert t["exit_reason"] == "STOP_GAP" and t["exit"] < 98.0 and t["R"] < -1.0


def test_risk_hard_limits_cannot_be_exceeded():
    rm = RiskManager({"risk_per_trade": 0.5, "max_drawdown": 0.9}, 1000)
    assert rm.cfg["risk_per_trade"] == HARD_LIMITS["risk_per_trade"]
    assert rm.cfg["max_drawdown"] == HARD_LIMITS["max_drawdown"]


def test_daily_loss_blocks_new_trades_and_drawdown_halts():
    rm = RiskManager({"max_daily_loss": 0.03, "max_drawdown": 0.2}, 1000)
    t = pd.Timestamp("2024-01-01 00:00", tz="UTC")
    rm.update(t, 1000)
    rm.update(t + pd.Timedelta(hours=4), 960)
    assert rm.can_open()[0] is False
    rm.update(t + pd.Timedelta(days=1), 960)
    assert rm.can_open()[0] is True
    rm.update(t + pd.Timedelta(days=2), 790)
    assert rm.dd_halt and rm.must_flatten() == "MAX_DRAWDOWN"


def test_portfolio_override_blocks_and_flattens():
    df = _flat_df()
    acc = Account("x", 100, Costs(), RISK)
    acc.override = {"block": "Depot: Tagesverlust-Limit"}
    sig = _sig(df, 5)
    rows = sig.to_dict("records")
    for i in range(10):
        r = df.iloc[i]
        acc.on_bar(df.index[i], r.open, r.high, r.low, r.close, 1e8, rows[i])
    assert acc.pos is None and acc.last_decision["blocked_by"].startswith("Depot")


def test_account_roundtrip_serialization():
    df = _flat_df()
    acc = backtest.run(df, _sig(df, 5, 10), Costs(), RISK, 100)
    acc2 = Account.from_dict(acc.to_dict())
    assert acc2.cash == acc.cash and len(acc2.trades) == 1


def test_live_mode_is_refused():
    with pytest.raises(paper.LiveTradingForbidden):
        paper.assert_paper({"mode": "LIVE"})


def test_no_order_code_to_exchanges():
    src = " ".join(p.read_text() for p in (KI / "bot").glob("*.py")).lower()
    for bad in ("create_order", "createorder", "withdraw", "apikey", "api_secret", "secret="):
        assert bad not in src


def test_workflow_only_touches_ki_files():
    """Der KI-Workflow darf nur ki/ und docs/ki/ committen und hat eine eigene Concurrency-Gruppe."""
    wf = (KI.parent / ".github/workflows/ki-bot.yml").read_text()
    assert "group: ki-bot" in wf
    for line in wf.splitlines():
        if "git add" in line:
            paths = line.split("git add", 1)[1].replace("-A", "").split("2>")[0].split("||")[0].split()
            assert paths and all(p.startswith("ki/") or p.startswith("docs/ki") for p in paths), line


def test_data_validation():
    bad = data.synthetic(400)
    bad.iloc[100, bad.columns.get_loc("close")] = np.nan
    with pytest.raises(data.DataError):
        data.validate(bad)
    with pytest.raises(data.DataError):
        data.validate(data.synthetic(400), "krypto", check_age=True)  # synthetische Daten sind alt


def test_drop_unfinished_daily_bar():
    df = _flat_df(10)
    now = df.index[-1] + pd.Timedelta(hours=5)
    assert len(data.drop_unfinished(df, now)) == 9


def test_kraken_parsing():
    class FakeEx:
        def fetch_ohlcv(self, s, timeframe, limit):
            b = 1_700_000_000_000
            return [[b + i * 86_400_000, 100, 101, 99, 100.5, 12] for i in range(3)]
    df = data.fetch_kraken("BTC/EUR", "1d", FakeEx())
    assert len(df) == 3 and df["close"].iloc[0] == 100.5 and str(df.index.tz) == "UTC"


def test_markets_read_from_shared_config():
    ms = data.markets_from_config(KI.parent / "config.yaml")
    assert len(ms) >= 1 and {m["klasse"] for m in ms} <= {"krypto", "aktie"}
