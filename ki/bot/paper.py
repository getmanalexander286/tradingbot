"""Paper Trading Engine – NUR virtuelles Geld, 24 Märkte.

Jede Strategie (S001–S009 + HYBRID) hat ein eigenes Depot aus 24 Teildepots
à 100 € – dieselbe Aufteilung wie die drei MA-Bots, damit man vergleichen kann.
Daily/Weekly-Loss und Max Drawdown werden auf Depot-Ebene überwacht.

Es gibt absichtlich KEINEN Code, der Orders an eine Börse sendet.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest, data, indicators as ind, metrics, regime, selector, strategies, validation
from .logbook import log, notify, research_log
from .research import load_registry
from .risk import RiskManager
from .sim import Account, Costs, sig_rows
from .strategies import BY_ID

STATE = Path("state/paper_state.json")
STATUS = Path("state/status.json")  # klein, ändert sich stündlich; großer Zustand nur bei neuen Kerzen
MODE_TEXT = "DEMO TRADING — VIRTUAL MONEY ONLY"


class LiveTradingForbidden(Exception):
    pass


def assert_paper(cfg):
    if cfg.get("mode") != "PAPER":
        raise LiveTradingForbidden("Nur mode='PAPER' ist erlaubt. Live-Trading ist nicht implementiert.")


def load_state():
    if STATE.exists():
        st = json.loads(STATE.read_text())
        if STATUS.exists():
            st["status"] = json.loads(STATUS.read_text())
        return st
    return {"portfolios": {}, "status": {}, "markets": {}, "steps": 0,
            "created": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")}


def save_state(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    for p in st["portfolios"].values():
        p["history"] = p["history"][-3000:]
        for a in p["sleeves"].values():
            a["equity_curve"] = a["equity_curve"][-120:]
            a["trades"] = a["trades"][-200:]
    STATUS.write_text(json.dumps(metrics.clean(st.get("status", {})), indent=1, default=str))
    big = {k: v for k, v in st.items() if k != "status"}
    new = json.dumps(metrics.clean(big), default=str)
    if not STATE.exists() or STATE.read_text() != new:  # nur schreiben, wenn sich etwas geändert hat
        STATE.write_text(new)


def _snapshot(df):
    c = df["close"]
    return pd.DataFrame({"rsi14": ind.rsi(c, 14), "adx14": ind.adx(df, 14), "atr14": ind.atr(df, 14),
                         "ema50": ind.ema(c, 50), "ema200": ind.ema(c, 200), "roc30": ind.roc(c, 30)},
                        index=df.index).round(6).to_dict("records")


def build_signals(dfs, metas, registry):
    strategies.prepare_ml(dfs)
    table = (registry.get("hybrid") or {}).get("table", {})
    out, regs, used = {}, {}, {}
    for sid, s in registry["strategies"].items():
        used[sid] = next(x for x in s["versions"] if x["version"] == s["active_version"])
    for m, df in dfs.items():
        reg = regime.detect(df)
        regs[m] = reg
        sigs = {sid: backtest.attach_regime(BY_ID[sid].signals(df, **v["params"]), reg, sid) for sid, v in used.items()}
        key = metas[m]["klasse"] + ":" + reg["trend"].astype(str)
        h = selector.hybrid_signals(df.index, key, sigs, table, 0, len(df))
        sigs["HYBRID"] = backtest.attach_regime(h, reg, "HYBRID")
        snap = _snapshot(df)
        for s in sigs.values():
            s["indicators"] = snap
        out[m] = sigs
    return out, regs, used


def analyze_trade(t, reg_now, ref):
    """Lernen nach jedem Trade: bewerten, NICHT sofort Regeln ändern."""
    mu, sd = (ref or {}).get("R_mean", 0.0), max((ref or {}).get("R_std", 1.0) or 1.0, 1e-6)
    z = (t["R"] - mu) / sd
    txt = (f"{t['market']} {t['strategy']}: {t['pnl']:+.2f} € ({t['R']:+.2f}R), Ausstieg {t['exit_reason']}. "
           f"Regime Entry {t.get('regime')} → jetzt {reg_now}. Regeln automatisch befolgt. "
           f"{'Im erwarteten Bereich' if abs(z) < 2 else 'AUSSERHALB der erwarteten Verteilung'} (z={z:+.1f}). "
           "Einzelner Trade = keine Evidenz, Strategie bleibt unverändert.")
    if t["exit_reason"] == "STOP_GAP":
        txt += " Stop durch Kurslücke schlechter gefüllt – Risiko war höher als geplant."
    return txt


def portfolio_evidence(p, min_trades):
    trades = [t for a in p["sleeves"].values() for t in a["trades"]]
    m = metrics.compute(p["history"], trades, "1d", p["start_capital"])
    m["n_trades"] = len(trades)
    if len(trades) < min_trades:
        m["verdict"], m["verdict_text"] = "INSUFFICIENT", f"{len(trades)}/{min_trades} Paper-Trades – noch keine Aussage möglich."
    else:
        pv = validation.bootstrap_pvalue([t["eq_ret"] for t in trades])
        good = pv < 0.05 and (m.get("profit_factor") or 0) > 1.1
        m["verdict"] = "EDGE_PLAUSIBLE" if good else ("NO_EDGE" if (m.get("expectancy") or 0) <= 0 else "UNCLEAR")
        m["verdict_text"] = f"{len(trades)} Paper-Trades, p={pv:.3f}."
    return m


def fetch_all(metas, cfg):
    """Holt alle Märkte. Fehler betreffen nur den jeweiligen Markt."""
    dfs, problems = {}, {}
    ex = None
    try:
        import ccxt
        ex = ccxt.kraken({"enableRateLimit": True})
    except Exception as e:
        log.warning("ccxt nicht verfügbar: %s", e)
    for m, meta in metas.items():
        try:
            df = data.load_or_update(meta, "1d", "data", ex)
            df, w = data.validate(df, meta["klasse"], check_age=True)
            df.attrs["market"] = m
            dfs[m] = df
            if w:
                problems[m] = "; ".join(w)
        except Exception as e:
            problems[m] = f"FEHLER: {e}"
    return dfs, problems


def step(cfg, metas, dfs=None, problems=None, quiet=False, now=None):
    assert_paper(cfg)
    st = load_state()
    now = now or pd.Timestamp.now(tz="UTC")
    status = st["status"]
    status.update({"last_run": now.isoformat(timespec="seconds"), "mode": MODE_TEXT})
    registry = load_registry()
    if not registry["strategies"]:
        status.update({"bot": "WAITING", "message": "Noch kein Research – zuerst `python run.py research`."})
        save_state(st)
        return st
    if dfs is None:
        dfs, problems = fetch_all(metas, cfg)
    problems = problems or {}
    errors = {m: p for m, p in problems.items() if p.startswith("FEHLER")}
    if len(dfs) < len(metas) / 2:
        status.update({"bot": "HALTED_DATA", "message": f"Zu viele Datenfehler ({len(errors)}/{len(metas)}) – Trading pausiert."})
        research_log(status["message"], "WARN")
        notify(status["message"]) if not quiet else None
        save_state(st)
        return st
    for m, p in errors.items():
        research_log(f"{m}: {p} – dieser Markt wird diesmal ausgelassen.", "WARN")

    hb = cfg["paper"].get("history_bars", 800)
    dfs = {m: df.iloc[-hb:] for m, df in dfs.items()}
    for m, df in dfs.items():
        df.attrs["market"] = m
    sigs, regs, used = build_signals(dfs, metas, registry)
    costs = Costs(**cfg["costs"])
    sleeve_risk = {**cfg["risk_sleeve"], "limits_enabled": False, "use_kill_switch": True}
    port_risk_cfg = {**cfg["risk_portfolio"], "use_kill_switch": True}
    cap = cfg["capital_per_market"]
    names = list(used) + ["HYBRID"]
    processed = 0
    for name in names:
        p = st["portfolios"].setdefault(name, {"start_capital": cap * len(metas), "sleeves": {}, "history": [], "risk": None})
        prm = RiskManager(port_risk_cfg, p["start_capital"])
        if p["risk"]:
            prm.load(p["risk"])
        block, flatten = None, prm.must_flatten()
        ok, why = prm.can_open()
        if not ok:
            block = "Depot: " + why
        ref = registry["hybrid"] if name == "HYBRID" else used.get(name)
        for m, df in dfs.items():
            ad = p["sleeves"].get(m)
            acc = Account.from_dict(ad) if ad else Account(f"{name}|{m}", cap, costs, sleeve_risk)
            acc.costs = costs
            acc.override = {"block": block, "flatten": flatten and ("PORTFOLIO_" + flatten)}
            if acc.last_ts is None:
                todo = [len(df) - 1]  # Start ab jetzt – kein Nachhandeln der Vergangenheit
            else:
                todo = list(np.where(df.index > pd.Timestamp(acc.last_ts))[0][-60:])
            if todo:
                rows = sig_rows(sigs[m][name].iloc[todo])
                o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
                vq = (df["volume"] * df["close"]).to_numpy()
                n_before = len(acc.trades)
                for j, i in enumerate(todo):
                    s = rows[j]
                    acc.on_bar(df.index[i], o[i], h[i], l[i], c[i], vq[i], s if s["atr"] == s["atr"] else None)
                processed = max(processed, len(todo))
                for t in acc.trades[n_before:]:
                    t["market"], t["klasse"] = m, metas[m]["klasse"]
                    t["analysis"] = analyze_trade(t, regs[m]["trend"].iloc[-1], ref)
                    if name == "HYBRID":
                        research_log(f"[HYBRID] {t['analysis']}")
                        if not quiet:
                            notify(f"KI-Hybrid {m}: Trade geschlossen {t['pnl']:+.2f} € ({t['exit_reason']})")
            p["sleeves"][m] = acc.to_dict()
        # Depot-Bewertung (letzter Schlusskurs je Teildepot)
        eq = sum(a["cash"] + a["qty"] * (a["last_close"] or 0) for a in p["sleeves"].values())
        eq += cap * (len(metas) - len(p["sleeves"]))  # noch nicht gestartete Teildepots = Bargeld
        prm.update(now, eq)
        for ev in prm.events:
            if not ev.get("notified"):
                ev["notified"] = True
                research_log(f"[{name}] DEPOT-RISIKO: {ev['msg']}", "WARN")
                if name == "HYBRID" and not quiet:
                    notify(f"KI-Bot Risk Limit: {ev['msg']}")
        p["risk"] = prm.to_dict()
        last_h = pd.Timestamp(p["history"][-1][0]) if p["history"] else None
        if processed or last_h is None or now - last_h >= pd.Timedelta(hours=6):
            p["history"].append((now.isoformat(timespec="seconds"), eq))

    # Marktübersicht für das Dashboard
    for m in metas:
        if m not in dfs:
            st["markets"][m] = {**st["markets"].get(m, {}), "problem": problems.get(m, "keine Daten")}
            continue
        hy = sigs[m]["HYBRID"].iloc[-1]
        sl = st["portfolios"]["HYBRID"]["sleeves"][m]
        if sl["pos"]:
            dec = f"Position ({sl['pos']['strategy']})"
        elif sl["pending"] and sl["pending"]["side"] == "buy":
            dec = f"Kauf zur nächsten Kerze ({sl['pending']['strategy']})"
        else:
            dec = "NO TRADE"
        st["markets"][m] = {"klasse": metas[m]["klasse"], "name": metas[m]["name"], "regime": regs[m]["trend"].iloc[-1],
                            "vol": regs[m]["vol"].iloc[-1], "price": float(dfs[m]["close"].iloc[-1]),
                            "last_bar": str(dfs[m].index[-1])[:10], "strategy": hy["strategy"], "decision": dec,
                            "reason": hy["reason"], "equity": sl["cash"] + sl["qty"] * (sl["last_close"] or 0),
                            "problem": problems.get(m)}
    if processed:
        regs_now = pd.Series([v["regime"] for v in st["markets"].values() if "regime" in v]).value_counts()
        n_pos = sum(1 for v in st["markets"].values() if str(v.get("decision", "")).startswith("Position"))
        research_log(f"Neue Tageskerzen verarbeitet. Regime-Verteilung: {', '.join(f'{k} {v}' for k, v in regs_now.items())}. "
                     f"Hybrid hält {n_pos} von {len(metas)} Positionen.")
    kill = Path(cfg["risk_portfolio"].get("kill_switch_file", "KILL_SWITCH")).exists()
    hp = st["portfolios"]["HYBRID"]
    status.update({"bot": "KILL_SWITCH" if kill else "ONLINE",
                   "message": f"{len(errors)} Märkte mit Datenfehler" if errors else "OK",
                   "markets_ok": len(dfs), "markets_total": len(metas), "bars_processed": processed,
                   "hybrid_halt": hp["risk"]["dd_halt"]})
    st["evidence"] = {n: portfolio_evidence(p, cfg["research"].get("min_trades", 50)) for n, p in st["portfolios"].items()}
    save_state(st)
    log.info("KI-Step: %d neue Kerzen, %d/%d Märkte ok", processed, len(dfs), len(metas))
    return st
