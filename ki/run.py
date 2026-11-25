#!/usr/bin/env python3
"""KI Quant Research Bot – Steuerung (nur Paper-Trading, 24 Märkte, läuft neben den MA-Bots).

  python run.py research              Research auf echten Daten (Kraken + Yahoo)
  python run.py research --synthetic  Research auf synthetischen Testdaten (nur Software-Test!)
  python run.py step                  Ein Paper-Trading-Schritt
  python run.py simulate --bars 60    Paper-Engine Tag für Tag auf Testdaten durchspielen
  python run.py dashboard             ../docs/ki/index.html neu erzeugen
  python run.py serve                 Dashboard lokal mit Passwort (DASHBOARD_PASSWORD)
  python run.py kill | unkill         Kill Switch (nur KI-Bot) an/aus
  python run.py rollback S001 2       Strategie-Version zurücksetzen
  python run.py reset                 KI-Demo-Depots zurücksetzen (Research bleibt)
"""
import argparse
import json
import os
import sys
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)

from bot import dashboard, data, paper, research  # noqa: E402
from bot.logbook import log, research_log  # noqa: E402


def cfg_load():
    cfg = json.loads(Path("config.json").read_text())
    paper.assert_paper(cfg)
    import yaml
    root = yaml.safe_load(Path(cfg["markets_config"]).read_text())
    metas = {m["symbol"]: m for m in data.markets_from_config(cfg["markets_config"])}
    cfg["capital_per_market"] = float(root.get("startkapital", 2400)) / len(metas)  # wie die MA-Bots
    return cfg, metas


def synthetic_dfs(metas, seed):
    return data.synthetic_universe(list(metas.values()), seed=seed)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd")
    p.add_argument("args", nargs="*")
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--bars", type=int)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    cfg, metas = cfg_load()
    kill_file = Path(cfg["risk_portfolio"].get("kill_switch_file", "KILL_SWITCH"))

    if a.cmd == "research":
        if a.synthetic:
            dfs, label, problems = synthetic_dfs(metas, a.seed), "synthetic", {}
        else:
            dfs, problems = paper.fetch_all(metas, cfg)
            label = "kraken+yahoo"
        for m, pr in problems.items():
            research_log(f"{m}: {pr}", "WARN")
        dfs = {m: data.validate(df, metas[m]["klasse"])[0] for m, df in dfs.items()}
        if len(dfs) < len(metas) / 2:
            sys.exit("Zu wenige Märkte mit Daten – Research abgebrochen.")
        research.run_research(dfs, {m: metas[m] for m in dfs}, cfg, label)
        dashboard.render(cfg)
        print(Path("reports/research_report.md").read_text())

    elif a.cmd == "step":
        paper.step(cfg, metas)
        dashboard.render(cfg)

    elif a.cmd == "simulate":
        full = synthetic_dfs(metas, a.seed + 100)
        days = pd.date_range(end=max(d.index[-1] for d in full.values()), periods=a.bars or 60, freq="D")
        research_log(f"Simulation: KI-Paper-Engine wird über {len(days)} Tage (synthetisch) abgespielt")
        for d in days:
            now = d + pd.Timedelta(hours=1)
            dfs = {m: df[df.index < d] for m, df in full.items()}
            paper.step(cfg, metas, dfs, {}, quiet=True, now=now)
        dashboard.render(cfg)
        st = paper.load_state()
        for name, e in st["evidence"].items():
            print(f"{name:7s} trades={e.get('n_trades', 0):4d} ret={e.get('total_return', 0):+.2%} "
                  f"maxDD={e.get('max_drawdown', 0):.1%} -> {e['verdict']}")

    elif a.cmd == "dashboard":
        print(dashboard.render(cfg))

    elif a.cmd == "serve":
        serve(a.port)

    elif a.cmd == "kill":
        kill_file.write_text("Kill Switch aktiv (nur KI-Bot)\n")
        research_log("KILL SWITCH aktiviert: keine neuen Trades, offene Positionen werden geschlossen.", "WARN")
    elif a.cmd == "unkill":
        kill_file.unlink(missing_ok=True)
        research_log("Kill Switch deaktiviert.")

    elif a.cmd == "rollback":
        sid, ver = a.args[0], int(a.args[1])
        reg = research.load_registry()
        s = reg["strategies"][sid]
        assert any(v["version"] == ver for v in s["versions"]), "Version existiert nicht"
        s["active_version"] = ver
        research.save_registry(reg)
        research_log(f"Rollback: {sid} -> v{ver} (manuell)")

    elif a.cmd == "reset":
        paper.STATE.unlink(missing_ok=True)
        research_log("KI-Demo-Depots zurückgesetzt (manuell).")
    else:
        p.print_help()


def serve(port):
    import base64
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    pw = os.environ.get("DASHBOARD_PASSWORD")
    if not pw:
        sys.exit("Bitte DASHBOARD_PASSWORD als Umgebungsvariable setzen.")
    token = base64.b64encode(f"admin:{pw}".encode()).decode()

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *x, **k):
            super().__init__(*x, directory="../docs", **k)

        def do_GET(self):
            if self.headers.get("Authorization") != f"Basic {token}":
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="bot"')
                self.end_headers()
                return
            super().do_GET()

    print(f"Dashboard: http://localhost:{port}  (Benutzer: admin)")
    HTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    main()
