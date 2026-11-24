"""Erzeugt docs/index.html: Vergleich aller Strategien."""

import json
import csv
import os
import yaml
from datetime import datetime, timezone

ORDNER = os.path.dirname(os.path.abspath(__file__))
STAND = os.path.join(ORDNER, 'state')
ZIEL = os.path.join(ORDNER, 'docs', 'index.html')

# Farben aus dem Design-System, Paar geprueft fuer Farbfehlsichtigkeit
T = {
    'surface': ('#fcfcfb', '#1a1a19'),
    'plane': ('#f9f9f7', '#0d0d0d'),
    'ink': ('#0b0b0b', '#f0efec'),
    'ink2': ('#52514e', '#c3c2b7'),
    'muted': ('#898781', '#898781'),
    'grid': ('#e1e0d9', '#2c2c2a'),
    'axis': ('#c3c2b7', '#383835'),
    'gut': ('#006300', '#0ca30c'),
    'schlecht': ('#d03b3b', '#e66767'),
    'rand': ('rgba(11,11,11,0.10)', 'rgba(255,255,255,0.10)'),
    'serie1': ('#2a78d6', '#3987e5'),
    'serie2': ('#eb6834', '#d95926'),
}
SERIEN = ['serie1', 'serie2']


def lade_json(name, standard):
    p = os.path.join(STAND, name)
    return json.load(open(p)) if os.path.exists(p) else standard


def lade_csv(*teile):
    p = os.path.join(STAND, *teile)
    return list(csv.DictReader(open(p))) if os.path.exists(p) else []


def kurz(iso):
    try:
        return datetime.fromisoformat(iso).strftime('%d.%m. %H:%M')
    except Exception:
        return iso or '-'


def zahl(x, n=2):
    return f"{x:,.{n}f}".replace(',', ' ')


def klasse(x):
    return 'gut' if x > 0 else ('schlecht' if x < 0 else '')


# ------------------------------------------------------------- Chart

def vergleichschart(reihen, start):
    """reihen: Liste (name, farbvariable, [(zeit, wert), ...])"""
    laengen = [len(p) for _, _, p in reihen]
    if not laengen or max(laengen) < 2:
        return ('<p class="hinweis">Noch zu wenig Daten. Der Chart erscheint '
                'nach dem zweiten Durchlauf.</p>')

    B, H = 1000, 340
    ol, orr, otop, ou = 64, 96, 16, 34
    pb, ph = B - ol - orr, H - otop - ou

    alle = [w for _, _, p in reihen for _, w in p] + [start]
    lo, hi = min(alle), max(alle)
    spanne = (hi - lo) or max(hi * 0.01, 1.0)
    lo -= spanne * 0.1
    hi += spanne * 0.1
    n = max(laengen)

    def x(i):
        return ol + pb * i / (n - 1) if n > 1 else ol

    def y(w):
        return otop + ph * (1 - (w - lo) / (hi - lo))

    teile = []
    for k in range(5):
        w = lo + (hi - lo) * k / 4
        yy = y(w)
        teile.append(f'<line x1="{ol}" y1="{yy:.1f}" x2="{B-orr}" y2="{yy:.1f}" class="gitter"/>')
        teile.append(f'<text x="{ol-10}" y="{yy+4:.1f}" class="achse" text-anchor="end">'
                     f'{zahl(w, 0)}</text>')

    y0 = y(start)
    teile.append(f'<line x1="{ol}" y1="{y0:.1f}" x2="{B-orr}" y2="{y0:.1f}" class="bezug"/>')

    js_reihen = []
    for idx, (name, farbe, punkte) in enumerate(reihen):
        if len(punkte) < 2:
            continue
        pfad = ' '.join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(w):.1f}"
                        for i, (_, w) in enumerate(punkte))
        teile.append(f'<path d="{pfad}" class="linie" style="stroke:var(--{farbe})"/>')
        # Direktbeschriftung am Linienende statt nur Legende
        ex, ey = x(len(punkte) - 1), y(punkte[-1][1])
        teile.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4" '
                     f'style="fill:var(--{farbe})" class="ende"/>')
        teile.append(f'<text x="{ex+10:.1f}" y="{ey+4:.1f}" class="endlabel" '
                     f'style="fill:var(--{farbe})">{name}</text>')
        js_reihen.append({'name': name, 'farbe': farbe,
                          'punkte': [[kurz(t), round(w, 2), round(x(i), 1), round(y(w), 1)]
                                     for i, (t, w) in enumerate(punkte)]})

    marken = []
    laengste = max(reihen, key=lambda r: len(r[2]))[2]
    for i in (0, len(laengste) // 2, len(laengste) - 1):
        anker = 'start' if i == 0 else ('end' if i == len(laengste) - 1 else 'middle')
        marken.append(f'<text x="{x(i):.1f}" y="{H-12}" class="achse" '
                      f'text-anchor="{anker}">{kurz(laengste[i][0])}</text>')

    legende = ' '.join(
        f'<span class="le"><i style="background:var(--{f})"></i>{n_}</span>'
        for n_, f, p in reihen if len(p) >= 2)

    return f"""
<div class="legende">{legende}<span class="le gestrichelt">Startkapital</span></div>
<div class="chartbox">
  <svg viewBox="0 0 {B} {H}" class="chart" id="chart" role="img"
       aria-label="Vergleich des Depotwerts der Strategien in Euro">
    {''.join(teile)}
    <line x1="{ol}" y1="{otop+ph}" x2="{B-orr}" y2="{otop+ph}" class="basis"/>
    {''.join(marken)}
    <g id="fokus" style="display:none">
      <line y1="{otop}" y2="{otop+ph}" class="kreuz"/>
    </g>
    <rect x="{ol}" y="{otop}" width="{pb}" height="{ph}" fill="transparent" id="feld"/>
  </svg>
  <div id="tipp" class="tipp" hidden></div>
</div>
<script>
const reihen = {json.dumps(js_reihen)};
const svg = document.getElementById('chart');
const feld = document.getElementById('feld');
const fokus = document.getElementById('fokus');
const kreuz = fokus.querySelector('line');
const tipp = document.getElementById('tipp');

function zeigen(evt) {{
  const kasten = svg.getBoundingClientRect();
  const sx = (evt.clientX - kasten.left) / kasten.width * {B};
  let zeilen = '', zeitpunkt = '', bestX = null;
  reihen.forEach(r => {{
    let best = 0, ab = Infinity;
    r.punkte.forEach((p, i) => {{ const d = Math.abs(p[2] - sx);
      if (d < ab) {{ ab = d; best = i; }} }});
    const p = r.punkte[best];
    zeitpunkt = p[0];
    if (bestX === null) bestX = p[2];
    zeilen += '<div class="tz"><i style="background:var(--' + r.farbe + ')"></i>' +
      r.name + '<b>' + p[1].toLocaleString('de-DE',
      {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) + ' &euro;</b></div>';
  }});
  if (bestX === null) return;
  kreuz.setAttribute('x1', bestX); kreuz.setAttribute('x2', bestX);
  fokus.style.display = '';
  tipp.hidden = false;
  tipp.innerHTML = '<div class="tt">' + zeitpunkt + '</div>' + zeilen;
  const px = kasten.left + bestX / {B} * kasten.width;
  tipp.style.left = Math.min(Math.max(px - 80, 4),
    window.innerWidth - tipp.offsetWidth - 8) + 'px';
  tipp.style.top = (kasten.top + window.scrollY + 20) + 'px';
}}
feld.addEventListener('mousemove', zeigen);
feld.addEventListener('touchmove', e => {{ zeigen(e.touches[0]); e.preventDefault(); }});
svg.addEventListener('mouseleave', () => {{ fokus.style.display = 'none'; tipp.hidden = true; }});
</script>
"""


# ------------------------------------------------------------- Tabellen

def positionstabelle(zustand, daten, kuerzel):
    zeilen = []
    for markt in sorted(zustand):
        p = zustand[markt]
        d = daten.get(markt, {})
        preis = d.get('preis', 0.0)
        s = d.get('strategien', {}).get(kuerzel, {})
        wert = p['bargeld'] + p['menge'] * preis
        offen = p['menge'] > 0
        gv = (preis / p['einstieg'] - 1) * 100 if offen and p['einstieg'] else None
        ml = s.get('ma_langsam', 0)
        abstand = (s.get('ma_schnell', 0) / ml - 1) * 100 if ml else None
        zeilen.append(f"""<tr>
<td><b>{markt.split('/')[0]}</b></td>
<td>{'<span class="marke offen">investiert</span>' if offen
     else '<span class="marke">Bargeld</span>'}</td>
<td class="z">{preis:.4f}</td>
<td class="z {klasse(gv or 0)}">{f'{gv:+.2f} %' if gv is not None else '-'}</td>
<td class="z">{zahl(wert)}</td>
<td class="z">{f'{abstand:+.2f} %' if abstand is not None else '-'}</td>
</tr>""")
    return ''.join(zeilen)


def tradetabelle(trades):
    if not trades:
        return ('<tr><td colspan="6" style="color:var(--muted)">Noch keine Trades.</td></tr>')
    zeilen = []
    for t in reversed(trades[-40:]):
        try:
            gv = float(t['gewinn_prozent'])
        except (TypeError, ValueError):
            gv = 0.0
        zeilen.append(f"""<tr>
<td>{kurz(t['zeit'])}</td>
<td><b>{t['markt'].split('/')[0]}</b></td>
<td>{t['typ'].capitalize()}</td>
<td class="z">{float(t['preis']):.4f}</td>
<td class="z {klasse(gv) if t['typ'] == 'VERKAUF' else ''}">
{f'{gv:+.2f} %' if t['typ'] == 'VERKAUF' else '-'}</td>
<td>{t['grund']}</td>
</tr>""")
    return ''.join(zeilen)


# ------------------------------------------------------------- Seite

def main():
    cfg = yaml.safe_load(open(os.path.join(ORDNER, 'config.yaml')))
    letzter = lade_json('last_run.json', {})
    start = float(cfg['startkapital'])
    daten = letzter.get('daten', {})
    anzahl = int(letzter.get('anzahl_maerkte', len(cfg['maerkte'])))
    aktiv = bool(letzter.get('aktiv', True))

    stand = ''
    if letzter.get('zeit'):
        try:
            minuten = (datetime.now(timezone.utc)
                       - datetime.fromisoformat(letzter['zeit'])).total_seconds() / 60
            stand = (f'<span class="marke offen">vor {minuten:.0f} min</span>' if minuten < 30
                     else f'<span class="marke warn">vor {minuten/60:.1f} h</span>')
        except Exception:
            pass

    reihen, karten, bloecke = [], [], []

    for idx, st in enumerate(cfg['strategien']):
        k = st['kuerzel']
        farbe = SERIEN[idx % len(SERIEN)]
        info = letzter.get('strategien', {}).get(k, {})
        gesamt = float(info.get('gesamtwert', start))
        inv = int(info.get('investiert', 0))

        verlauf = lade_csv(k, 'history.csv')
        punkte = []
        for z in verlauf:
            try:
                punkte.append((z['zeit'], float(z['gesamtwert'])))
            except (KeyError, TypeError, ValueError):
                continue
        reihen.append((st['name'], farbe, punkte[-600:]))

        trades = lade_csv(k, 'trades.csv')
        verkaeufe = [t for t in trades if t['typ'] == 'VERKAUF']
        werte = []
        for t in verkaeufe:
            try:
                werte.append(float(t['gewinn_prozent']))
            except (TypeError, ValueError):
                pass
        quote = f"{sum(1 for w in werte if w > 0) / len(werte) * 100:.0f} %" if werte else '-'
        schnitt = f"{sum(werte) / len(werte):+.2f} %" if werte else '-'

        erg = gesamt - start
        karten.append(f"""
<div class="karte" style="border-left:3px solid var(--{farbe})">
  <div class="titel">{st['name']}</div>
  <div class="wert">{zahl(gesamt)} &euro;</div>
  <div class="neben {klasse(erg)}">{erg:+,.2f} &euro; &middot; {(gesamt/start-1)*100:+.2f} %</div>
  <div class="neben">{inv}/{anzahl} investiert &middot; {len(trades)} Trades
    &middot; Treffer {quote}</div>
</div>""")

        zustand = lade_json(os.path.join(k, 'positions.json'), {})
        bloecke.append(f"""
<h2><span class="punktfarbe" style="background:var(--{farbe})"></span>{st['name']}</h2>
<div class="rolle"><table>
<thead><tr><th>Markt</th><th>Status</th><th class="z">Kurs</th><th class="z">G/V</th>
<th class="z">Wert &euro;</th><th class="z">Abstand MA</th></tr></thead>
<tbody>{positionstabelle(zustand, daten, k)}</tbody></table></div>
<details><summary>Trades anzeigen ({len(trades)})</summary>
<div class="rolle" style="margin-top:8px"><table>
<thead><tr><th>Zeit</th><th>Markt</th><th>Typ</th><th class="z">Kurs</th>
<th class="z">G/V</th><th>Grund</th></tr></thead>
<tbody>{tradetabelle(trades)}</tbody></table></div></details>
""")

    css_hell = ''.join(f"  --{k}: {v[0]};\n" for k, v in T.items())
    css_dunkel = ''.join(f"    --{k}: {v[1]};\n" for k, v in T.items())

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Trading-Bot</title>
<style>
:root {{
  color-scheme: light dark;
{css_hell}}}
@media (prefers-color-scheme: dark) {{ :root {{
{css_dunkel}}} }}
* {{ box-sizing: border-box; }}
body {{ margin:0; padding:20px 16px 64px; background:var(--plane); color:var(--ink);
  font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }}
.huelle {{ max-width:1040px; margin:0 auto; }}
h1 {{ font-size:20px; margin:0; letter-spacing:-0.01em; }}
h2 {{ font-size:15px; margin:34px 0 10px; color:var(--ink2); font-weight:600;
  display:flex; align-items:center; gap:8px; }}
.punktfarbe {{ width:10px; height:10px; border-radius:3px; display:inline-block; }}
.kopf {{ display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }}
.unter {{ color:var(--muted); font-size:13px; margin:4px 0 22px; }}
.karten {{ display:grid; gap:10px; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); }}
.karte {{ background:var(--surface); border:1px solid var(--rand); border-radius:10px;
  padding:14px 16px; }}
.karte .titel {{ font-size:12px; color:var(--muted); margin-bottom:6px;
  text-transform:uppercase; letter-spacing:0.04em; }}
.karte .wert {{ font-size:26px; font-weight:600; letter-spacing:-0.02em;
  font-variant-numeric:tabular-nums; }}
.karte .neben {{ font-size:13px; color:var(--ink2); margin-top:2px;
  font-variant-numeric:tabular-nums; }}
.gut {{ color:var(--gut); }} .schlecht {{ color:var(--schlecht); }}
.legende {{ display:flex; gap:16px; flex-wrap:wrap; margin:0 0 8px; font-size:13px;
  color:var(--ink2); }}
.le {{ display:inline-flex; align-items:center; gap:6px; }}
.le i {{ width:12px; height:3px; border-radius:2px; display:inline-block; }}
.le.gestrichelt::before {{ content:""; width:12px; height:0;
  border-top:1px dashed var(--muted); display:inline-block; }}
.chartbox {{ position:relative; background:var(--surface); border:1px solid var(--rand);
  border-radius:10px; padding:8px; }}
.chart {{ width:100%; height:auto; display:block; touch-action:pan-y; }}
.gitter {{ stroke:var(--grid); stroke-width:1; }}
.basis {{ stroke:var(--axis); stroke-width:1; }}
.bezug {{ stroke:var(--muted); stroke-width:1; stroke-dasharray:4 4; }}
.linie {{ fill:none; stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }}
.ende {{ stroke:var(--surface); stroke-width:2; }}
.endlabel {{ font-size:13px; font-weight:600; font-family:system-ui,sans-serif; }}
.kreuz {{ stroke:var(--muted); stroke-width:1; }}
.achse {{ fill:var(--muted); font-size:12px; font-family:system-ui,sans-serif;
  font-variant-numeric:tabular-nums; }}
.tipp {{ position:absolute; background:var(--surface); color:var(--ink);
  border:1px solid var(--rand); border-radius:8px; padding:8px 10px; font-size:13px;
  pointer-events:none; white-space:nowrap; box-shadow:0 4px 14px rgba(0,0,0,0.12);
  font-variant-numeric:tabular-nums; z-index:5; }}
.tipp .tt {{ color:var(--muted); font-size:12px; margin-bottom:4px; }}
.tipp .tz {{ display:flex; align-items:center; gap:6px; }}
.tipp .tz i {{ width:10px; height:3px; border-radius:2px; display:inline-block; }}
.tipp .tz b {{ margin-left:auto; padding-left:12px; }}
.rolle {{ overflow-x:auto; background:var(--surface); border:1px solid var(--rand);
  border-radius:10px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th {{ text-align:left; font-weight:600; font-size:12px; color:var(--muted);
  text-transform:uppercase; letter-spacing:0.04em; padding:10px 12px;
  border-bottom:1px solid var(--rand); white-space:nowrap; }}
td {{ padding:9px 12px; border-bottom:1px solid var(--rand); white-space:nowrap; }}
tr:last-child td {{ border-bottom:none; }}
.z {{ text-align:right; font-variant-numeric:tabular-nums; }}
.marke {{ font-size:12px; padding:2px 8px; border-radius:99px; background:var(--grid);
  color:var(--ink2); }}
.marke.offen {{ background:color-mix(in oklab,var(--serie1) 16%,transparent);
  color:var(--serie1); }}
.marke.warn {{ background:color-mix(in oklab,var(--schlecht) 16%,transparent);
  color:var(--schlecht); }}
.hinweis {{ color:var(--muted); background:var(--surface); border:1px solid var(--rand);
  border-radius:10px; padding:20px; margin:0; font-size:14px; }}
details {{ margin-top:10px; }}
summary {{ cursor:pointer; color:var(--ink2); font-size:13px; }}
footer {{ margin-top:36px; color:var(--muted); font-size:12px; }}
</style>
</head>
<body>
<div class="huelle">

<div class="kopf">
  <h1>Trading-Bot</h1>
  {stand}
  {'<span class="marke">pausiert</span>' if not aktiv else ''}
</div>
<p class="unter">Papier-Depot, kein echtes Geld &middot; zwei Strategien im Vergleich
  &middot; Stand {kurz(letzter.get('zeit',''))} UTC</p>

<div class="karten">{''.join(karten)}</div>

<h2>Vergleich der Depotwerte</h2>
{vergleichschart(reihen, start)}

{''.join(bloecke)}

<footer>
  Stop-Loss {cfg['stop_loss']*100:.0f} % &middot;
  Take-Profit {'aus' if not cfg.get('take_profit') else f"{cfg['take_profit']*100:.0f} %"}
  &middot; Gebuehr {cfg['gebuehr']*100:.2f} % &middot; {anzahl} Maerkte<br>
  Seite aktualisiert sich alle 5 Minuten selbst.
  Einstellungen in <code>config.yaml</code> im Repository.
</footer>

</div>
</body>
</html>"""

    os.makedirs(os.path.dirname(ZIEL), exist_ok=True)
    open(ZIEL, 'w').write(html)
    print(f"  Dashboard geschrieben: {len(html)} Zeichen")


if __name__ == '__main__':
    main()
