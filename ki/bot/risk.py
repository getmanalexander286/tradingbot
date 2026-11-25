"""Risk Management Engine – unabhängig von den Strategien.

Strategien und Research-Engine haben KEINEN Zugriff, um Limits zu ändern.
Konfigurierte Werte werden zusätzlich auf harte Obergrenzen (HARD_LIMITS)
begrenzt, die nur durch Ändern dieses Codes verschoben werden können.
"""
from __future__ import annotations

import os

import pandas as pd

HARD_LIMITS = {
    "risk_per_trade": 0.02,      # max 2 % des Kapitals pro Trade riskieren
    "max_position_frac": 1.0,    # nie mehr als 100 % (kein Hebel)
    "max_daily_loss": 0.05,
    "max_weekly_loss": 0.10,
    "max_drawdown": 0.30,
}
DEFAULTS = {"risk_per_trade": 0.01, "max_position_frac": 0.5, "max_daily_loss": 0.03,
            "max_weekly_loss": 0.06, "max_drawdown": 0.20, "use_kill_switch": False, "limits_enabled": True,
            "kill_switch_file": "KILL_SWITCH"}


class RiskManager:
    def __init__(self, cfg: dict | None, capital: float):
        c = {**DEFAULTS, **(cfg or {})}
        for k, hard in HARD_LIMITS.items():
            c[k] = min(float(c[k]), hard)
        self.cfg = c
        self.peak = capital
        self.day_key = self.week_key = None
        self.day_start = self.week_start = capital
        self.equity = capital
        self.dd_halt = False
        self.events: list[dict] = []

    # ---- Zustand
    def to_dict(self):
        return {k: getattr(self, k) for k in ("peak", "day_key", "week_key", "day_start", "week_start",
                                               "equity", "dd_halt", "events")}

    def load(self, d):
        for k, v in d.items():
            setattr(self, k, v)

    def _event(self, ts, kind, msg):
        if not self.events or self.events[-1]["kind"] != kind or self.events[-1].get("key") != self.day_key:
            self.events.append({"time": str(ts), "kind": kind, "msg": msg, "key": self.day_key})
            self.events = self.events[-100:]

    # ---- Updates
    def update(self, ts: pd.Timestamp, equity: float):
        dk, wk = str(ts.date()), "%d-W%02d" % ts.isocalendar()[:2]
        if dk != self.day_key:
            self.day_key, self.day_start = dk, self.equity
        if wk != self.week_key:
            self.week_key, self.week_start = wk, self.equity
        self.equity = equity
        self.peak = max(self.peak, equity)
        if self.cfg["limits_enabled"] and self.drawdown >= self.cfg["max_drawdown"] and not self.dd_halt:
            self.dd_halt = True
            self._event(ts, "MAX_DRAWDOWN", f"Max Drawdown {self.drawdown:.1%} erreicht – Trading gestoppt")

    @property
    def drawdown(self):
        return 1 - self.equity / self.peak if self.peak > 0 else 0.0

    @property
    def daily_pnl(self):
        return self.equity / self.day_start - 1

    @property
    def weekly_pnl(self):
        return self.equity / self.week_start - 1

    def kill_switch(self):
        return self.cfg["use_kill_switch"] and os.path.exists(self.cfg["kill_switch_file"])

    def can_open(self, ts=None) -> tuple[bool, str]:
        if self.kill_switch():
            return False, "KILL_SWITCH aktiv"
        if not self.cfg["limits_enabled"]:
            return True, "OK"
        if self.dd_halt:
            return False, "Max Drawdown erreicht (manueller Reset nötig)"
        if self.daily_pnl <= -self.cfg["max_daily_loss"]:
            self._event(ts, "DAILY_LIMIT", f"Tagesverlust {self.daily_pnl:.1%} – keine neuen Trades heute")
            return False, "Tagesverlust-Limit"
        if self.weekly_pnl <= -self.cfg["max_weekly_loss"]:
            self._event(ts, "WEEKLY_LIMIT", f"Wochenverlust {self.weekly_pnl:.1%} – keine neuen Trades diese Woche")
            return False, "Wochenverlust-Limit"
        return True, "OK"

    def must_flatten(self) -> str | None:
        if self.kill_switch():
            return "KILL_SWITCH"
        if self.dd_halt:
            return "MAX_DRAWDOWN"
        return None

    def size(self, equity: float, price: float, stop: float, mult: float = 1.0) -> float:
        """Positionsgröße (im Teildepot) so, dass Stop-Loss ≈ risk_per_trade * equity kostet."""
        per_unit = price - stop
        if per_unit <= 0 or price <= 0:
            return 0.0
        qty_risk = equity * self.cfg["risk_per_trade"] * max(0.0, min(mult, 1.0)) / per_unit
        qty_cap = equity * self.cfg["max_position_frac"] / price
        return max(0.0, min(qty_risk, qty_cap))

    def status(self):
        ok, reason = self.can_open()
        return {"drawdown": self.drawdown, "daily_pnl": self.daily_pnl, "weekly_pnl": self.weekly_pnl,
                "can_trade": ok, "reason": reason, "limits": {k: self.cfg[k] for k in HARD_LIMITS}}
