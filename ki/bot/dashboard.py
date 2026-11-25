"""KI-Dashboard: erzeugt ../docs/ki/index.html (eigene Seite, berührt die MA-Bots nicht)."""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

import pandas as pd

from . import metrics
from .logbook import read_research_log
from .paper import MODE_TEXT, load_state
from .research import load_registry
from .strategies import BY_ID

CSS = """
:root{color-scheme:dark;--bg:#000;--card:#111113;--line:#232326;--txt:#f5f5f7;--mut:#8e8e93;--g:#30d158;--r:#ff453a;--y:#ffd60a;--b:#0a84ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","Inter",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px 60px}a{color:var(--b);text-decoration:none}
.demo{background:linear-gradient(90deg,#ffd60a,#ff9f0a);color:#000;font-weight:700;text-align:center;padding:10px;border-radius:14px;letter-spacing:.04em}
h1{font-size:28px;font-weight:700;margin:22px 0 4px;letter-spacing:-.02em}h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);margin:30px 0 10px;font-weight:600}
.sub{color:var(--mut);font-size:13px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(165px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:14px 16px}
.k{color:var(--mut);font-size:12px}.v{font-size:21px;font-weight:600;margin-top:2px;letter-spacing:-.01em}
.pos{color:var(--g)}.neg{color:var(--r)}.warn{color:var(--y)}
.tbl{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:18px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--mut);font-weight:500}tr:last-child td{border:0}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;font-size:11px;font-weight:600;background:#1c1c1e}
.p-EDGE_PLAUSIBLE{color:var(--g)}.p-NO_EDGE{color:var(--r)}.p-UNCLEAR{color:var(--y)}.p-INSUFFICIENT{color:var(--mut)}
.log{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:6px 16px;max-height:420px;overflow:auto;font-size:13px}
.log div{padding:7px 0;border-bottom:1px solid var(--line)}.log div:last-child{border:0}.log time{color:var(--mut);margin-right:8px;font-variant-numeric:tabular-nums}
svg{width:100%;height:140px;display:block}.why{white-space:normal;min-width:240px;color:var(--mut)}
"""


def _e(x):
    return html.escape(str(x))


def _money(x, sign=False):
    return (f"{x:+,.2f} €" if sign else f"{x:,.2f} €").replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x, sign=True):
    return f"{x:+.2%}" if sign else f"{x:.2%}"


def _pf(x):
    x = x or 0
    return "∞" if x >= 999 else f"{x:.2f}"


def _cls(x):
    return "pos" if x > 0 else "neg" if x < 0 else ""


def _card(k, v, cls=""):
    return f'<div class="card"><div class="k">{_e(k)}</div><div class="v {cls}">{v}</div></div>'


def _spark(curve, start):
    if len(curve) < 2:
        return '<div class="sub">Die Equity-Kurve erscheint nach den ersten Durchläufen.</div>'
    ys = [e for _, e in curve][-800:]
    lo, hi = min(ys + [start]), max(ys + [start])
    rng = (hi - lo) or 1
    pts = " ".join(f"{i / (len(ys) - 1) * 1000:.1f},{130 - (y - lo) / rng * 120:.1f}" for i, y in enumerate(ys))
    base = 130 - (start - lo) / rng * 120
    col = "#30d158" if ys[-1] >= start else "#ff453a"
    return (f'<svg viewBox="0 0 1000 140" preserveAspectRatio="none"><line x1="0" x2="1000" y1="{base:.1f}" y2="{base:.1f}" '
            f'stroke="#3a3a3c" stroke-dasharray="4 6"/><polyline fill="none" stroke="{col}" stroke-width="2.2" points="{pts}"/></svg>')


def _period(curve, days):
    eq = metrics.equity_series(curve)
    if eq.empty:
        return 0.0
    past = eq[eq.index <= eq.index[-1] - pd.Timedelta(days=days)]
    return float(eq.iloc[-1] - (past.iloc[-1] if len(past) else eq.iloc[0]))


def _ma_bots(root):
    """Liest (nur lesend) den aktuellen Stand der drei MA-Bots zum Vergleich."""
    out = []
    try:
        import yaml
        cfg = yaml.safe_load((root / "config.yaml").read_text())
        start = float(cfg.get("startkapital", 0))
        for s in cfg.get("strategien", []):
            p = root / "state" / s["kuerzel"] / "history.csv"
            rows = list(csv.DictReader(p.open())) if p.exists() else []
            if rows:
                out.append((s["name"], float(rows[-1]["gesamtwert"]), start))
    except Exception:
        pass
    return out


def _sleeve_eq(a):
    return a["cash"] + a["qty"] * (a["last_close"] or 0)


def render(cfg, out="../docs/ki/index.html"):
    st, reg = load_state(), load_registry()
    rp = Path("state/research.json")
    research = json.loads(rp.read_text()) if rp.exists() else {}
    status, ports, ev = st.get("status", {}), st.get("portfolios", {}), st.get("evidence", {})
    h = ports.get("HYBRID")
    P = [f'<div class="demo">MODE: {MODE_TEXT}</div>',
         f'<h1>KI Quant Research Bot</h1><div class="sub">{status.get("markets_total", "–")} Märkte (dieselben wie die MA-Bots) · '
         f'Tageskerzen · letzter Lauf {_e(status.get("last_run", "–"))} UTC · '
         f'<a href="../">← zu den 3 MA-Bots</a></div>']

    P.append("<h2>Overview · KI-Hybrid-Depot (virtuell)</h2>")
    if h:
        cap = h["start_capital"]
        eq = h["history"][-1][1] if h["history"] else cap
        rk = h["risk"]
        dd = 1 - eq / max(rk["peak"], eq)
        n_pos = sum(1 for a in h["sleeves"].values() if a["pos"])
        invested = sum(a["qty"] * (a["last_close"] or 0) for a in h["sleeves"].values())
        P.append('<div class="grid">' + "".join([
            _card("Virtuelle Equity", _money(eq)), _card("Startkapital", _money(cap)),
            _card("Gesamt P/L", _money(eq - cap, True), _cls(eq - cap)), _card("Rendite", _pct(eq / cap - 1), _cls(eq - cap)),
            _card("Heute", _money(_period(h["history"], 1), True), _cls(_period(h["history"], 1))),
            _card("7 Tage", _money(_period(h["history"], 7), True), _cls(_period(h["history"], 7))),
            _card("30 Tage", _money(_period(h["history"], 30), True), _cls(_period(h["history"], 30))),
            _card("Drawdown", _pct(dd, False), "warn" if dd > 0.1 else ""),
            _card("Cash", _money(eq - invested)), _card("Offene Positionen", f"{n_pos} / {len(h['sleeves'])}"),
        ]) + "</div>")
        P.append(f'<div class="card" style="margin-top:10px">{_spark(h["history"], cap)}</div>')
    else:
        P.append('<div class="card">Noch keine Paper-Daten – der erste Research-Lauf läuft.</div>')

    # Vergleich mit den MA-Bots + allen KI-Depots
    P.append("<h2>Vergleich · alle Bots, je 2.400 € Spielgeld</h2><div class='tbl'><table><tr><th>Bot</th><th>Equity</th>"
             "<th>Rendite</th><th>Trades</th><th>Max DD</th><th>Urteil (Paper)</th><th>Urteil (Backtest OOS)</th><th>Version</th></tr>")
    rows = []
    for name, eqv, start in _ma_bots(Path("..")):
        rows.append((eqv / start - 1, f"<tr><td>{_e(name)} <span class='sub'>(MA-Bot)</span></td><td>{_money(eqv)}</td>"
                     f"<td class='{_cls(eqv - start)}'>{_pct(eqv / start - 1)}</td><td class='sub'>–</td><td class='sub'>–</td>"
                     f"<td class='sub'>–</td><td class='sub'>–</td><td></td></tr>"))
    for name, p in ports.items():
        e = ev.get(name, {})
        eqv = p["history"][-1][1] if p["history"] else p["start_capital"]
        rr = (research.get("results") or {}).get(name, {})
        ver = reg["strategies"].get(name, {}).get("active_version") if name != "HYBRID" else (reg.get("hybrid") or {}).get("version")
        title = f"{name} {BY_ID[name].name}" if name in BY_ID else "HYBRID KI-Auswahl"
        rows.append((eqv / p["start_capital"] - 1, (
            f"<tr><td>{_e(title)}</td><td>{_money(eqv)}</td><td class='{_cls(eqv - p['start_capital'])}'>{_pct(eqv / p['start_capital'] - 1)}</td>"
            f"<td>{e.get('n_trades', 0)}</td><td>{_pct(e.get('max_drawdown', 0), False)}</td>"
            f"<td><span class='pill p-{_e(e.get('verdict', 'INSUFFICIENT'))}'>{_e(e.get('verdict', 'INSUFFICIENT'))}</span></td>"
            f"<td><span class='pill p-{_e(rr.get('verdict', ''))}'>{_e(rr.get('verdict', '–'))}</span></td><td>v{ver}</td></tr>")))
    P.append("".join(r for _, r in sorted(rows, key=lambda x: -x[0])) + "</table></div>")

    # BOT STATUS + RISK
    if h:
        lim, rk = cfg["risk_portfolio"], h["risk"]
        open_risk = sum(a["pos"]["qty"] * max(0, (a["last_close"] or 0) - a["pos"]["stop"]) for a in h["sleeves"].values() if a["pos"])
        bot = status.get("bot", "OFFLINE")
        P.append("<h2>Bot Status & Risk Monitor</h2><div class='grid'>" + "".join([
            _card("Status", _e(bot), "pos" if bot == "ONLINE" else "neg"), _card("Trading Mode", "PAPER", "warn"),
            _card("Märkte mit Daten", f"{status.get('markets_ok', 0)} / {status.get('markets_total', 0)}"),
            _card("Nächste Analyse", "stündlich"),
            _card("Tagesverlust / Limit", f"{_pct(rk['equity'] / rk['day_start'] - 1)} / -{lim['max_daily_loss']:.0%}"),
            _card("Wochenverlust / Limit", f"{_pct(rk['equity'] / rk['week_start'] - 1)} / -{lim['max_weekly_loss']:.0%}"),
            _card("Drawdown / Limit", f"{_pct(1 - rk['equity'] / rk['peak'], False)} / {lim['max_drawdown']:.0%}"),
            _card("Risiko pro Trade", f"{cfg['risk_sleeve']['risk_per_trade']:.0%} je Teildepot"),
            _card("Offenes Risiko", _money(open_risk)),
            _card("Risk Status", "GESTOPPT" if rk["dd_halt"] else "OK", "neg" if rk["dd_halt"] else "pos"),
        ]) + "</div>")
        if status.get("message") not in (None, "OK"):
            P.append(f'<div class="card warn" style="margin-top:10px">{_e(status["message"])}</div>')

    # MÄRKTE
    mk = st.get("markets", {})
    if mk:
        P.append("<h2>Märkte · Regime & KI-Entscheidung</h2><div class='tbl'><table><tr><th>Wert</th><th>Art</th><th>Kurs</th>"
                 "<th>Kerze</th><th>Regime</th><th>Volatilität</th><th>Entscheidung</th><th>Teildepot</th><th>Begründung</th></tr>")
        for m, v in sorted(mk.items(), key=lambda kv: (kv[1].get("klasse", ""), kv[0])):
            if "regime" not in v:
                P.append(f"<tr><td>{_e(m)}</td><td colspan=8 class='warn'>{_e(v.get('problem'))}</td></tr>")
                continue
            P.append(f"<tr><td><b>{_e(v['name'])}</b></td><td>{_e(v['klasse'])}</td><td>{v['price']:,.4g}</td><td>{_e(v['last_bar'])}</td>"
                     f"<td>{_e(v['regime'])}</td><td>{_e(v['vol'])}</td><td>{_e(v['decision'])}</td>"
                     f"<td class='{_cls(v['equity'] - cfg['capital_per_market'])}'>{_money(v['equity'])}</td>"
                     f"<td class='why'>{_e(v['reason'])}{(' · ⚠ ' + _e(v['problem'])) if v.get('problem') else ''}</td></tr>")
        P.append("</table></div>")

    # RESEARCH
    if research:
        P.append(f"<h2>Strategy Rankings · Walk-Forward Out-of-Sample ab {_e(research.get('oos_from', ''))}</h2>"
                 "<div class='tbl'><table><tr><th>ID</th><th>Familie</th><th>Trades</th><th>Depot</th><th>PF</th><th>Sharpe</th>"
                 "<th>MaxDD</th><th>PF 2x Kosten</th><th>Krypto Ø/Trade</th><th>Aktien Ø/Trade</th><th>p korr.</th><th>Begründung</th></tr>")
        for sid, r in sorted(research["results"].items(), key=lambda kv: -(kv[1]["oos"].get("sharpe") or -99)):
            o, s, kl = r["oos"], r["stress_2x_costs"], r.get("klassen", {})
            P.append(f"<tr><td>{_e(sid)}</td><td>{_e(r.get('family', ''))}</td><td>{o.get('n_trades', 0)}</td>"
                     f"<td class='{_cls(o.get('total_return', 0))}'>{_pct(o.get('total_return', 0))}</td><td>{_pf(o.get('profit_factor'))}</td>"
                     f"<td>{o.get('sharpe', 0):.2f}</td><td>{_pct(o.get('max_drawdown', 0), False)}</td><td>{_pf(s.get('profit_factor'))}</td>"
                     f"<td>{_pct(kl.get('krypto', {}).get('mean_ret', 0))}</td><td>{_pct(kl.get('aktie', {}).get('mean_ret', 0))}</td>"
                     f"<td>{r.get('p_adj', 1):.3f}</td><td class='why'>{_e(r.get('verdict_text', ''))}</td></tr>")
        b = research.get("benchmark_buy_hold", {})
        P.append(f"</table></div><div class='sub' style='margin-top:8px'>Benchmark Buy & Hold (alle Märkte, gleicher Zeitraum): "
                 f"{_pct(b.get('total_return', 0))}, MaxDD {_pct(b.get('max_drawdown', 0), False)} · Daten: {_e(research.get('data'))} · "
                 f"Evidenzklassen siehe RESEARCH.md</div>")

    # TRADES
    trades = sorted([t for p in ports.values() for a in p["sleeves"].values() for t in a["trades"]],
                    key=lambda t: t["exit_time"], reverse=True)[:30]
    P.append("<h2>Trading History · alle KI-Depots</h2><div class='tbl'><table><tr><th>Exit</th><th>Wert</th><th>Strategie</th>"
             "<th>Entry</th><th>Exit</th><th>P/L</th><th>R</th><th>Regime</th><th>Grund Entry</th><th>Exit-Grund</th></tr>")
    for t in trades:
        P.append(f"<tr><td>{_e(t['exit_time'][:10])}</td><td>{_e(t.get('market'))}</td><td>{_e(t['strategy'])}</td>"
                 f"<td>{t['entry']:,.4g}</td><td>{t['exit']:,.4g}</td><td class='{_cls(t['pnl'])}'>{_money(t['pnl'], True)}</td>"
                 f"<td>{t['R']:+.2f}</td><td>{_e(t.get('regime'))}</td><td class='why'>{_e((t.get('decision') or {}).get('reason', ''))}</td>"
                 f"<td>{_e(t['exit_reason'])}</td></tr>")
    if not trades:
        P.append("<tr><td colspan=10 class='sub'>Noch keine abgeschlossenen Demo-Trades. Kein Trade ist eine gültige Entscheidung.</td></tr>")
    P.append("</table></div>")

    P.append("<h2>AI Research Log</h2><div class='log'>")
    for e in read_research_log(60):
        P.append(f"<div class='{'warn' if e['level'] != 'INFO' else ''}'><time>{_e(e['time'][5:16].replace('T', ' '))}</time>{_e(e['msg'])}</div>")
    P.append("</div><p class='sub'>Keine Anlageberatung. Ausschließlich virtuelles Geld. Es werden keine Orders an Börsen gesendet.</p>")

    page = (f"<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<meta http-equiv='refresh' content='600'><title>DEMO · KI Quant Bot</title><style>{CSS}</style></head>"
            f"<body><div class='wrap'>{''.join(P)}</div></body></html>")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(page)
    return out
