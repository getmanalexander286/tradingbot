"""Ausführungs-Simulator (gemeinsam für Backtest UND Paper-Trading).

Realismus-Regeln:
* Signal entsteht am Kerzen-Schluss, Ausführung frühestens am Open der nächsten Kerze.
* Kauf zum Ask (+Spread/2) plus Slippage (fix + ATR-abhängig), Verkauf entsprechend schlechter.
* Gebühren auf jede Ausführung.
* Stop-Loss: bei Gap unter den Stop wird zum (schlechteren) Open gefüllt, sonst Stop minus Slippage.
* Stop und Take-Profit in derselben Kerze -> konservativ: Stop zuerst.
* Teilfüllung: maximal `max_participation` des Kerzen-Volumens.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .risk import RiskManager


@dataclass
class Costs:
    fee_rate: float = 0.0026       # 0,26 % pro Seite (wie die anderen Bots / Kraken)
    spread_bps: float = 5.0
    slippage_bps: float = 5.0
    slippage_atr_frac: float = 0.05
    max_participation: float = 0.01

    def scaled(self, k: float) -> "Costs":
        return Costs(self.fee_rate * k, self.spread_bps * k, self.slippage_bps * k,
                     self.slippage_atr_frac * k, self.max_participation)

    def buy(self, px, atr):
        return px * (1 + (self.spread_bps / 2 + self.slippage_bps) / 1e4) + self.slippage_atr_frac * (atr or 0)

    def sell(self, px, atr):
        return px * (1 - (self.spread_bps / 2 + self.slippage_bps) / 1e4) - self.slippage_atr_frac * (atr or 0)


def _nan(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


class Account:
    """Virtuelles Konto für genau eine Strategie / ein Portfolio."""

    def __init__(self, name: str, capital: float, costs: Costs, risk_cfg: dict | None):
        self.name, self.start_capital, self.costs = name, capital, costs
        self.cash, self.qty = capital, 0.0
        self.pos: dict | None = None
        self.pending: dict | None = None
        self.trades: list[dict] = []
        self.fees = 0.0
        self.risk = RiskManager(risk_cfg, capital)
        self.equity_curve: list[tuple[str, float]] = []
        self.last_ts: str | None = None
        self.last_close = None
        self.last_decision: dict | None = None
        self.override: dict = {}  # vom Portfolio-Risk-Manager gesetzt: {"block": grund, "flatten": grund}

    # ------------------------------------------------------------ Persistenz
    def to_dict(self):
        return {"name": self.name, "start_capital": self.start_capital, "costs": asdict(self.costs),
                "cash": self.cash, "qty": self.qty, "pos": self.pos, "pending": self.pending,
                "trades": self.trades, "fees": self.fees, "risk": self.risk.to_dict(),
                "risk_cfg": self.risk.cfg, "equity_curve": self.equity_curve, "last_ts": self.last_ts,
                "last_close": self.last_close, "last_decision": self.last_decision}

    @classmethod
    def from_dict(cls, d):
        a = cls(d["name"], d["start_capital"], Costs(**d["costs"]), d["risk_cfg"])
        for k in ("cash", "qty", "pos", "pending", "trades", "fees", "equity_curve", "last_ts",
                  "last_close", "last_decision"):
            setattr(a, k, d[k])
        a.risk.load(d["risk"])
        return a

    # ------------------------------------------------------------ Kern
    def equity(self, price):
        return self.cash + self.qty * price

    def _buy(self, ts, px_fill, qty, info):
        notional = qty * px_fill
        fee = notional * self.costs.fee_rate
        self.cash -= notional + fee
        self.fees += fee
        self.qty = qty
        self.pos = {**info, "entry_time": str(ts), "entry": px_fill, "qty": qty, "entry_fee": fee, "bars": 0}

    def _sell(self, ts, px_fill, reason):
        p = self.pos
        proceeds = self.qty * px_fill
        fee = proceeds * self.costs.fee_rate
        self.cash += proceeds - fee
        self.fees += fee
        pnl = proceeds - fee - (p["qty"] * p["entry"] + p["entry_fee"])
        risk_amt = p["qty"] * (p["entry"] - p["stop"])
        self.trades.append({
            "strategy": p.get("strategy", self.name), "entry_time": p["entry_time"], "exit_time": str(ts),
            "entry": p["entry"], "exit": px_fill, "qty": p["qty"], "pnl": pnl,
            "ret": pnl / (p["qty"] * p["entry"]), "eq_ret": pnl / p["equity_at_entry"],
            "R": pnl / risk_amt if risk_amt > 0 else 0.0, "fees": p["entry_fee"] + fee, "bars": p["bars"],
            "regime": p.get("regime"), "exit_reason": reason, "decision": p.get("decision"),
        })
        self.qty, self.pos = 0.0, None

    def on_bar(self, ts, o, h, l, c, v, sig: dict | None):
        """Eine abgeschlossene Kerze verarbeiten. `sig` = Signal, berechnet am Schluss DIESER Kerze."""
        costs = self.costs
        # 1) Offene Order am Open ausführen
        if self.pending is not None:
            od, self.pending = self.pending, None
            atr = od["atr"]
            if od["side"] == "buy" and self.pos is None:
                fill = costs.buy(o, atr)
                stop = fill - od["stop_atr"] * atr
                eq = self.equity(o)
                qty = self.risk.size(eq, fill, stop, od.get("size_mult", 1.0))
                qty = min(qty, self.cash / (fill * (1 + costs.fee_rate)))
                liq_cap = costs.max_participation * v if v > 0 else qty
                partial = qty > liq_cap
                qty = min(qty, liq_cap)
                if qty * fill >= 1.0:  # Mindestorder 1 € (Teildepots sind klein)
                    tp = fill + od["tp_atr"] * atr if not _nan(od.get("tp_atr")) else None
                    dec = {**od["decision"], "fill": fill, "stop": stop, "take_profit": tp,
                           "risk_eur": qty * (fill - stop), "partial_fill": partial}
                    self._buy(ts, fill, qty, {"strategy": od["strategy"], "stop": stop, "tp": tp,
                                              "max_hold": od.get("max_hold"), "regime": od.get("regime"),
                                              "equity_at_entry": eq, "decision": dec})
            elif od["side"] == "sell" and self.pos is not None:
                self._sell(ts, costs.sell(o, atr), od["reason"])

        # 2) Stop-Loss / Take-Profit innerhalb der Kerze
        if self.pos is not None:
            p, atr = self.pos, (sig or {}).get("atr") or 0.0
            if o <= p["stop"]:
                self._sell(ts, costs.sell(o, atr), "STOP_GAP")
            elif l <= p["stop"]:
                self._sell(ts, costs.sell(p["stop"], atr), "STOP_LOSS")
            elif p.get("tp") and o >= p["tp"]:
                self._sell(ts, o * (1 - costs.spread_bps / 2e4), "TAKE_PROFIT_GAP")
            elif p.get("tp") and h >= p["tp"]:
                self._sell(ts, p["tp"], "TAKE_PROFIT")  # Limit-Order: keine Slippage
        if self.pos is not None:
            self.pos["bars"] += 1

        # 3) Bewertung + Risiko
        eq = self.equity(c)
        tsx = pd.Timestamp(ts)
        self.risk.update(tsx, eq)
        self.equity_curve.append((str(ts), eq))
        self.last_ts, self.last_close = str(ts), c

        # 4) Entscheidung am Schluss -> Order für nächste Kerze
        if sig is None:
            return
        flat_reason = self.override.get("flatten") or self.risk.must_flatten()
        if self.pos is not None:
            mh = self.pos.get("max_hold")
            if flat_reason:
                self.pending = {"side": "sell", "atr": sig["atr"], "reason": "RISK_" + flat_reason}
            elif sig.get("exit"):
                self.pending = {"side": "sell", "atr": sig["atr"], "reason": "SIGNAL_EXIT"}
            elif not _nan(mh) and self.pos["bars"] >= mh:
                self.pending = {"side": "sell", "atr": sig["atr"], "reason": "TIME_EXIT"}
        elif sig.get("entry"):
            ok, why = self.risk.can_open(tsx)
            if ok and self.override.get("block"):
                ok, why = False, self.override["block"]
            decision = {"time": str(ts), "strategy": sig.get("strategy", self.name), "regime": sig.get("regime"),
                        "vol_regime": sig.get("vol_regime"), "confidence": sig.get("confidence"),
                        "reason": sig.get("reason", "Entry-Regel erfüllt"), "indicators": sig.get("indicators", {}),
                        "close": c, "atr": sig["atr"], "stop_atr": sig["stop_atr"],
                        "size_mult": sig.get("size_mult", 1.0)}
            if ok and sig.get("size_mult", 1.0) > 0:
                self.pending = {"side": "buy", "atr": sig["atr"], "stop_atr": sig["stop_atr"],
                                "tp_atr": sig.get("tp_atr"), "max_hold": sig.get("max_hold"),
                                "size_mult": sig.get("size_mult", 1.0), "strategy": decision["strategy"],
                                "regime": sig.get("regime"), "decision": decision}
                self.last_decision = {**decision, "action": "BUY_NEXT_OPEN"}
            else:
                self.last_decision = {**decision, "action": "NO_TRADE", "blocked_by": why}

    def close_all(self, ts, price, atr=0.0, reason="END_OF_TEST"):
        if self.pos is not None:
            self._sell(ts, self.costs.sell(price, atr), reason)
            self.equity_curve[-1] = (str(ts), self.equity(price))


def sig_rows(sig: pd.DataFrame):
    """DataFrame -> Liste von dicts (schnell)."""
    cols = list(sig.columns)
    vals = sig.to_numpy(dtype=object)
    return [dict(zip(cols, r)) for r in vals]
