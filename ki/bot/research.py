"""Strategy Research Engine / Strategy Lab – über alle 24 Märkte gemeinsam.

Ablauf je Strategie:
1. Signale für jede Parameter-Kombination und jeden Markt (kausal).
2. Anchored Walk-Forward über die Zeit: In jedem Fold werden die Parameter
   gemeinsam für ALLE Märkte gewählt (weniger Freiheitsgrade = weniger
   Overfitting) und zwar nur anhand von Trades, die vor dem Fold-Start
   bereits ABGESCHLOSSEN waren. Danach wird der folgende Zeitraum
   Out-of-Sample gehandelt.
3. OOS-Kennzahlen des Gesamtdepots (24 Teildepots à 100 €), 2x-Kosten-Stresstest,
   Monte Carlo, Bootstrap-p-Wert, Bonferroni, Auswertung nach Regime,
   Anlageklasse und Markt.
4. Hybrid: Regime-Tabelle je Fold nur aus früher abgeschlossenen OOS-Trades.
5. Versionierte Registry; Paper-Trading nutzt nur aktive Versionen.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest, metrics, regime, selector, strategies, validation
from .logbook import research_log
from .sim import Costs
from .strategies import ALL, BY_ID

REGISTRY = Path("state/registry.json")


def _score(trades):
    n = len(trades)
    if n < 20:
        return -5 + n / 10
    return validation.t_stat([t["eq_ret"] for t in trades])


def code_hash():
    d = Path(__file__).parent
    return hashlib.sha1((d / "strategies.py").read_bytes() + (d / "sim.py").read_bytes()).hexdigest()[:10]


def _tag(trades, mk, meta):
    for t in trades:
        t["market"], t["klasse"] = mk, meta["klasse"]
        t["regime_key"] = f"{meta['klasse']}:{t.get('regime')}"
    return trades


class Universe:
    def __init__(self, dfs, metas, cfg):
        self.dfs, self.metas, self.cfg = dfs, metas, cfg
        self.costs = Costs(**cfg["costs"])
        self.risk = {**cfg["risk_sleeve"], "limits_enabled": False}
        self.cap = cfg["capital_per_market"]
        rc = cfg["research"]
        self.warmup, self.folds = rc.get("warmup", 250), rc.get("folds", 4)
        self.regs = {m: regime.detect(df) for m, df in dfs.items()}
        self.keys = {m: metas[m]["klasse"] + ":" + self.regs[m]["trend"].astype(str) for m in dfs}
        t0 = min(df.index[min(self.warmup, len(df) - 1)] for df in dfs.values())
        t1 = max(df.index[-1] for df in dfs.values())
        self.bounds = [t0 + (t1 - t0) * i / (self.folds + 1) for i in range(self.folds + 2)]

    def pos(self, m, t, last=False):
        idx = self.dfs[m].index
        if last:
            return len(idx)
        return max(self.warmup, int(idx.searchsorted(t)))

    def fold_range(self, m, k):
        return self.pos(m, self.bounds[k]), self.pos(m, self.bounds[k + 1], last=(k == self.folds))

    def run_all(self, sigs: dict, start_at=None, costs=None):
        """Backtest je Markt; gibt (Trades gesamt, Portfolio-Kurve, Accounts) zurück."""
        trades, curves, accs = [], [], {}
        for m, df in self.dfs.items():
            st = self.warmup if start_at is None else self.pos(m, start_at)
            if st >= len(df) - 1:
                curves.append([])
                continue
            acc = backtest.run(df, sigs[m], costs or self.costs, self.risk, self.cap, st)
            trades += _tag(acc.trades, m, self.metas[m])
            curves.append(acc.equity_curve)
            accs[m] = acc
        caps = [self.cap] * len(curves)
        return trades, metrics.portfolio_curve(curves, caps), accs


def walk_forward(U: Universe, strat):
    combos = strat.param_grid
    sigs = [{m: backtest.attach_regime(strat.signals(df, **p), U.regs[m], strat.sid) for m, df in U.dfs.items()}
            for p in combos]
    full = [U.run_all(s)[0] for s in sigs]
    chosen = []
    combined = {m: sigs[0][m].copy() for m in U.dfs}
    for k in range(1, U.folds + 1):
        cutoff = str(U.bounds[k])
        scores = [_score([t for t in tr if t["exit_time"] < cutoff]) for tr in full]
        best = int(np.argmax(scores))
        chosen.append({"fold": k, "params": combos[best], "train_score": scores[best],
                       "test_from": cutoff[:10], "test_to": str(U.bounds[k + 1])[:10]})
        for m in U.dfs:
            a, b = U.fold_range(m, k)
            if b > a:
                combined[m].iloc[a:b] = sigs[best][m].iloc[a:b].values
    fs = [_score(tr) for tr in full]
    stability = float(np.mean([np.mean([t["eq_ret"] for t in tr]) > 0 if tr else False for tr in full]))
    return combined, chosen, combos[int(np.argmax(fs))], stability


def breakdown(trades, key):
    out = {}
    for t in trades:
        out.setdefault(t.get(key) or "UNKNOWN", []).append(t["eq_ret"])
    return {r: {"n": len(x), "mean_ret": float(np.mean(x)), "win_rate": float(np.mean(np.array(x) > 0)),
                "t": validation.t_stat(x)} for r, x in sorted(out.items())}


def evaluate(U: Universe, sigs, n_tests):
    rc = U.cfg["research"]
    start = U.bounds[1]
    trades, curve, _ = U.run_all(sigs, start)
    m = metrics.compute(curve, trades, "1d", U.cap * len(U.dfs))
    st_trades, st_curve, _ = U.run_all(sigs, start, U.costs.scaled(2.0))
    sm = metrics.compute(st_curve, st_trades, "1d", U.cap * len(U.dfs))
    eqr = [t["eq_ret"] for t in trades]
    mc = validation.monte_carlo([x / len(U.dfs) for x in eqr], rc.get("mc_runs", 2000))  # Beitrag zum Gesamtdepot
    p = validation.bootstrap_pvalue(eqr)
    p_adj = min(1.0, p * n_tests)
    v, why = validation.verdict(m, sm, mc, p_adj, rc.get("min_trades", 50), U.cfg["risk_portfolio"]["max_drawdown"] + 0.05)
    R = [t["R"] for t in trades]
    return trades, {"oos": m, "stress_2x_costs": sm, "monte_carlo": mc, "p_value": p, "p_adj": p_adj,
                    "verdict": v, "verdict_text": why, "regimes": breakdown(trades, "regime_key"),
                    "klassen": breakdown(trades, "klasse"), "maerkte": breakdown(trades, "market"),
                    "R_mean": float(np.mean(R)) if R else 0.0, "R_std": float(np.std(R)) if len(R) > 1 else 1.0,
                    "curve": curve[-800:]}


def load_registry():
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text())
    return {"strategies": {}, "hybrid": None, "runs": []}


def save_registry(reg):
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(metrics.clean(reg), indent=1, default=str))


def register(reg, sid, name, entry):
    s = reg["strategies"].setdefault(sid, {"name": name, "active_version": None, "versions": []})
    entry["version"] = (s["versions"][-1]["version"] + 1) if s["versions"] else 1
    s["versions"].append(entry)
    act = next((v for v in s["versions"] if v["version"] == s["active_version"]), None)
    if act is None:
        s["active_version"], note = entry["version"], "erste Version aktiviert"
    elif validation.VERDICT_RANK[entry["verdict"]] >= validation.VERDICT_RANK[act["verdict"]]:
        s["active_version"], note = entry["version"], f"v{entry['version']} ersetzt v{act['version']} (Urteil nicht schlechter, mehr Daten)"
    else:
        note = f"v{entry['version']} NICHT aktiviert: Urteil schlechter als aktive v{act['version']}"
    s["versions"] = s["versions"][-20:]
    return note


def run_research(dfs, metas, cfg, label="real"):
    t0 = time.time()
    for m, df in dfs.items():
        df.attrs["market"] = m
    U = Universe(dfs, metas, cfg)
    n_tests = len(ALL) + 1
    research_log(f"Research gestartet: {len(dfs)} Märkte ({sum(1 for m in metas.values() if m['klasse'] == 'krypto')} Krypto, "
                 f"{sum(1 for m in metas.values() if m['klasse'] == 'aktie')} Aktien), Tageskerzen, Daten: {label}")
    strategies.prepare_ml(dfs, horizon=cfg["research"].get("ml_horizon", 5))
    registry = load_registry()
    results, oos_sigs, all_oos = {}, {}, []
    for strat in ALL:
        combined, chosen, live_params, stability = walk_forward(U, strat)
        trades, ev = evaluate(U, combined, n_tests)
        ev.update({"folds": chosen, "live_params": live_params, "param_stability": stability,
                   "family": strat.family, "evidence_class": strat.evidence})
        results[strat.sid] = ev
        oos_sigs[strat.sid] = combined
        all_oos += trades
        o = ev["oos"]
        research_log(f"{strat.sid} {strat.name}: OOS {o.get('n_trades', 0)} Trades über alle Märkte, Depot "
                     f"{o.get('total_return', 0):+.1%}, PF {o.get('profit_factor', 0) or 0:.2f}, "
                     f"MaxDD {o.get('max_drawdown', 0):.1%} -> {ev['verdict']}")
        kl = ev["klassen"]
        if len(kl) == 2:
            research_log(f"{strat.sid}: Krypto {kl['krypto']['mean_ret']:+.2%}/Trade (n={kl['krypto']['n']}), "
                         f"Aktien {kl['aktie']['mean_ret']:+.2%}/Trade (n={kl['aktie']['n']})")
        good = [(r, x) for r, x in ev["regimes"].items() if x["n"] >= 15]
        if len(good) >= 2:
            b, w = max(good, key=lambda kv: kv[1]["mean_ret"]), min(good, key=lambda kv: kv[1]["mean_ret"])
            research_log(f"{strat.sid}: am besten in {b[0]} ({b[1]['mean_ret']:+.2%}/Trade), "
                         f"am schlechtesten in {w[0]} ({w[1]['mean_ret']:+.2%}/Trade)")

    # ---------------- Hybrid ohne Leakage
    rc = cfg["research"]
    hyb = {m: None for m in dfs}
    for k in range(1, U.folds + 1):
        cutoff = str(U.bounds[k])
        tab = selector.regime_table([t for t in all_oos if t["exit_time"] < cutoff],
                                    rc.get("min_regime_trades", 15), rc.get("min_regime_t", 2.0))
        for m in dfs:
            a, b = U.fold_range(m, k)
            hyb[m] = selector.hybrid_signals(dfs[m].index, U.keys[m], {s: oos_sigs[s][m] for s in oos_sigs}, tab, a, b, hyb[m])
    hyb = {m: backtest.attach_regime(h, U.regs[m], "HYBRID") for m, h in hyb.items()}
    _, hev = evaluate(U, hyb, n_tests)
    hev["family"], hev["evidence_class"] = "Adaptive Multi-Strategy", "Regime-Auswahl anhand OOS-Evidenz"
    results["HYBRID"] = hev
    final_table = selector.regime_table(all_oos, rc.get("min_regime_trades", 15), rc.get("min_regime_t", 2.0))
    research_log(f"HYBRID: OOS {hev['oos'].get('n_trades', 0)} Trades, Depot {hev['oos'].get('total_return', 0):+.1%}, "
                 f"MaxDD {hev['oos'].get('max_drawdown', 0):.1%} -> {hev['verdict']}")
    if not final_table:
        research_log("Keine Strategie zeigt in irgendeinem Regime genug OOS-Evidenz -> Hybrid bleibt in Cash.", "WARN")
    for r, rows in final_table.items():
        research_log(f"Regime {r}: bevorzugt {rows[0]['sid']} (n={rows[0]['n']}, t={rows[0]['t']:.2f})")

    # Benchmark: Buy & Hold in allen 24 Teildepots
    bh_curves = [backtest.buy_and_hold(df, U.pos(m, U.bounds[1]), len(df), U.costs, U.cap)
                 for m, df in dfs.items() if U.pos(m, U.bounds[1]) < len(df) - 1]
    bhm = metrics.compute(metrics.portfolio_curve(bh_curves, [U.cap] * len(bh_curves)), [], "1d", U.cap * len(bh_curves))
    research_log(f"Benchmark Buy & Hold (alle Märkte, gleicher Zeitraum): {bhm.get('total_return', 0):+.1%}, "
                 f"MaxDD {bhm.get('max_drawdown', 0):.1%}")

    ch, now = code_hash(), pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")
    data_range = [str(min(d.index[0] for d in dfs.values()))[:10], str(max(d.index[-1] for d in dfs.values()))[:10]]
    for sid, ev in results.items():
        if sid == "HYBRID":
            continue
        note = register(registry, sid, BY_ID[sid].name, {
            "created": now, "params": ev["live_params"], "verdict": ev["verdict"], "data": label,
            "data_range": data_range, "code_hash": ch, "oos": ev["oos"], "R_mean": ev["R_mean"],
            "R_std": ev["R_std"], "p_adj": ev["p_adj"]})
        research_log(f"Registry {sid}: {note}")
    hv = (registry["hybrid"] or {}).get("version", 0) + 1
    registry["hybrid"] = {"version": hv, "created": now, "table": final_table, "verdict": hev["verdict"],
                          "oos": hev["oos"], "R_mean": hev["R_mean"], "R_std": hev["R_std"]}
    registry["runs"] = (registry["runs"] + [{"time": now, "data": label, "markets": len(dfs), "code_hash": ch,
                                             "seconds": round(time.time() - t0, 1)}])[-50:]
    save_registry(registry)

    out = {"time": now, "data": label, "markets": len(dfs), "data_range": data_range,
           "oos_from": str(U.bounds[1])[:10], "benchmark_buy_hold": bhm, "results": results,
           "hybrid_table": final_table, "n_tests": n_tests}
    Path("state").mkdir(exist_ok=True)
    Path("state/research.json").write_text(json.dumps(metrics.clean(out), default=str))
    write_report(out)
    research_log(f"Research fertig in {time.time() - t0:.0f}s")
    return out


def write_report(out):
    L = [f"# KI-Research-Report – {out['markets']} Märkte (Tageskerzen)",
         f"Erstellt: {out['time']}  |  Daten: {out['data']}  |  Zeitraum: {out['data_range'][0]} – {out['data_range'][1]}",
         f"Out-of-Sample ab: {out['oos_from']}  |  Getestete Hypothesen: {out['n_tests']} (Bonferroni-korrigiert)",
         "Depot je Strategie: 24 Teildepots à 100 € (wie die MA-Bots)", "",
         "| ID | Strategie | Trades | Depot | PF | Sharpe | MaxDD | 2x Kosten PF | p (korr.) | Urteil |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for sid, ev in out["results"].items():
        o, s = ev["oos"], ev["stress_2x_costs"]
        name = BY_ID[sid].name if sid in BY_ID else "Hybrid (Regime-Auswahl)"
        L.append(f"| {sid} | {name} | {o.get('n_trades', 0)} | {o.get('total_return', 0):+.1%} | "
                 f"{(o.get('profit_factor') or 0):.2f} | {o.get('sharpe', 0):.2f} | {o.get('max_drawdown', 0):.1%} | "
                 f"{(s.get('profit_factor') or 0):.2f} | {ev['p_adj']:.3f} | {ev['verdict']} |")
    b = out["benchmark_buy_hold"]
    L += ["", f"Buy & Hold (alle Märkte, gleicher Zeitraum): {b.get('total_return', 0):+.1%}, MaxDD {b.get('max_drawdown', 0):.1%}",
          "", "## Begründungen"]
    for sid, ev in out["results"].items():
        L.append(f"- **{sid}**: {ev['verdict_text']}")
    L += ["", "**Hinweis:** Vergangene Ergebnisse garantieren nichts. EDGE_PLAUSIBLE heißt nur: weiter im Paper-Trading beobachten."]
    Path("reports").mkdir(exist_ok=True)
    Path("reports/research_report.md").write_text("\n".join(L))
