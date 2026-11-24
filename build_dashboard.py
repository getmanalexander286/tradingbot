"""
Erzeugt docs/index.html aus den Dateien in state/.
Wird nach jedem Durchlauf aufgerufen; GitHub Pages liefert das Ergebnis aus.
"""

import json
import csv
import os
from datetime import datetime, timezone

ORDNER = os.path.dirname(os.path.abspath(__file__))
STAND = os.path.join(ORDNER, 'state')
ZIEL = os.path.join(ORDNER, 'docs', 'index.html')

# Farben aus dem Design-System (hell / dunkel)
T = {
    'surface': ('#fcfcfb', '#1a1a19'),
    'plane': ('#f9f9f7', '#0d0d0d'),
    'ink': ('#0b0b0b', '#f0efec'),
    'ink2': ('#52514e', '#c3c2b7'),
    'muted': ('#898781', '#898781'),
    'grid': ('#e1e0d9', '#2c2c2a'),
    'axis': ('#c3c2b7', '#383835'),
    'serie': ('#2a78d6', '#3987e5'),
    'gut': ('#006300', '#0ca30c'),
    'schlecht': ('#d03b3b', '#e66767'),
    'rand': ('rgba(11,11,11,0.10)', 'rgba(255,255,255,0.10)'),
}


def lade_json(name, standard):
    pfad = os.path.join(STAND, name)
    if not os.path.exists(pfad):
        return standard
    with open(pfad) as f:
        return json.load(f)


def lade_csv(name):
    pfad = os.path.join(STAND, name)
    if not os.path.exists(pfad):
        return []
    with open(pfad) as f:
        return list(csv.DictReader(f))


def kurz(iso):
    try:
        d = datetime.fromisoformat(iso)
        return d.strftime('%d.%m. %H:%M')
    except Exception:
        return iso or '-'


def zahl(x, n=2):
    return f"{x:,.{n}f}".replace(',', ' ')


# ------------------------------------------------------------- Chart (SVG)

def linienchart(punkte, start):
    """punkte: Liste (iso-zeit, wert). Einzelne Serie, daher keine Legende."""
    if len(punkte) < 2:
        return ('<p class="hinweis">Noch zu wenig Daten fuer einen Verlauf. '
                'Der Chart erscheint nach dem zweiten Durchlauf.</p>')

    B, H = 1000, 320
    ol, orr, otop, ou = 64, 16, 16, 34
    pb, ph = B - ol - orr, H - otop - ou

    werte = [w for _, w in punkte]
    lo, hi = min(werte + [start]), max(werte + [start])
    spanne = hi - lo or max(hi * 0.01, 1.0)
    lo -= spanne * 0.08
    hi += spanne * 0.08

    def x(i):
        return ol + pb * i / (len(punkte) - 1)

    def y(w):
        return otop + ph * (1 - (w - lo) / (hi - lo))

    # Gitterlinien und Achsenbeschriftung
    gitter = []
    for k in range(5):
        w = lo + (hi - lo) * k / 4
        yy = y(w)
        gitter.append(f'<line x1="{ol}" y1="{yy:.1f}" x2="{B-orr}" y2="{yy:.1f}" '
                      f'class="gitter"/>')
        gitter.append(f'<text x="{ol-10}" y="{yy+4:.1f}" class="achse" '
                      f'text-anchor="end">{zahl(w, 0)}</text>')

    # Startkapital als Bezugslinie
    y0 = y(start)
    bezug = (f'<line x1="{ol}" y1="{y0:.1f}" x2="{B-orr}" y2="{y0:.1f}" class="bezug"/>'
             f'<text x="{B-orr}" y="{y0-8:.1f}" class="achse" text-anchor="end">'
             f'Start {zahl(start, 0)} &#8364;</text>')

    pfad = ' '.join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(w):.1f}"
                    for i, (_, w) in enumerate(punkte))
    flaeche = (f"M{x(0):.1f},{otop+ph:.1f} " +
               ' '.join(f"L{x(i):.1f},{y(w):.1f}" for i, (_, w) in enumerate(punkte)) +
               f" L{x(len(punkte)-1):.1f},{otop+ph:.1f} Z")

    # Zeitmarken unten
    marken = []
    for i in (0, len(punkte) // 2, len(punkte) - 1):
        anker = 'start' if i == 0 else ('end' if i == len(punkte) - 1 else 'middle')
        marken.append(f'<text x="{x(i):.1f}" y="{H-12}" class="achse" '
                      f'text-anchor="{anker}">{kurz(punkte[i][0])}</text>')

    daten_js = json.dumps([[kurz(t), round(w, 2), round(x(i), 1), round(y(w), 1)]
                           for i, (t, w) in enumerate(punkte)])

    return f"""
<div class="chartbox">
  <svg viewBox="0 0 {B} {H}" class="chart" id="chart"
       role="img" aria-label="Verlauf des Depotwerts in Euro">
    {''.join(gitter)}
    {bezug}
    <path d="{flaeche}" class="flaeche"/>
    <path d="{pfad}" class="linie"/>
    <line x1="{ol}" y1="{otop+ph}" x2="{B-orr}" y2="{otop+ph}" class="basis"/>
    {''.join(marken)}
    <g id="fokus" style="display:none">
      <line y1="{otop}" y2="{otop+ph}" class="kreuz"/>
      <circle r="5" class="punkt"/>
    </g>
    <rect x="{ol}" y="{otop}" width="{pb}" height="{ph}" fill="transparent" id="feld"/>
  </svg>
  <div id="tipp" class="tipp" hidden></div>
</div>
<script>
  const punkte = {daten_js};
  const svg = document.getElementById('chart');
  const feld = document.getElementById('feld');
  const fokus = document.getElementById('fokus');
  const tipp = document.getElementById('tipp');
  const kreuz = fokus.querySelector('line');
  const kugel = fokus.querySelector('circle');

  function naechster(evt) {{
    const kasten = svg.getBoundingClientRect();
    const sx = (evt.clientX - kasten.left) / kasten.width * {B};
    let best = 0, abstand = Infinity;
    punkte.forEach((p, i) => {{
      const d = Math.abs(p[2] - sx);
      if (d < abstand) {{ abstand = d; best = i; }}
    }});
    return best;
  }}

  function zeigen(evt) {{
    const i = naechster(evt);
    const p = punkte[i];
    kreuz.setAttribute('x1', p[2]); kreuz.setAttribute('x2', p[2]);
    kugel.setAttribute('cx', p[2]); kugel.setAttribute('cy', p[3]);
    fokus.style.display = '';
    tipp.hidden = false;
    tipp.innerHTML = '<b>' + p[1].toLocaleString('de-DE',
      {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) + ' &euro;</b><br>' + p[0];
    const kasten = svg.getBoundingClientRect();
    const px = kasten.left + p[2] / {B} * kasten.width;
    tipp.style.left = Math.min(Math.max(px - 60, 4),
      window.innerWidth - tipp.offsetWidth - 8) + 'px';
    tipp.style.top = (kasten.top + window.scrollY + p[3] / {H} * kasten.height - 56) + 'px';
  }}

  feld.addEventListener('mousemove', zeigen);
  feld.addEventListener('touchmove', e => {{ zeigen(e.touches[0]); e.preventDefault(); }});
  svg.addEventListener('mouseleave', () => {{
    fokus.style.display = 'none'; tipp.hidden = true;
  }});
</script>
"""


# ------------------------------------------------------------- Tabellen

def positionstabelle(zustand, daten):
    zeilen = []
    for markt in sorted(zustand):
        p = zustand[markt]
        d = daten.get(markt, {})
        preis = d.get('preis', 0.0)
        wert = p['bargeld'] + p['menge'] * preis
        offen = p['menge'] > 0
        gv = (preis / p['einstieg'] - 1) * 100 if offen and p['einstieg'] else None

        ms, ml = d.get('ma_schnell', 0), d.get('ma_langsam', 0)
        abstand = (ms / ml - 1) * 100 if ml else None

        klasse = 'gut' if (gv or 0) > 0 else ('schlecht' if (gv or 0) < 0 else '')
        zeilen.append(f"""<tr>
<td><b>{markt.split('/')[0]}</b></td>
<td>{'<span class="marke offen">investiert</span>' if offen
     else '<span class="marke">Bargeld</span>'}</td>
<td class="z">{preis:.4f}</td>
<td class="z">{p['einstieg']:.4f}</td>
<td class="z {klasse}">{f'{gv:+.2f} %' if gv is not None else '-'}</td>
<td class="z">{zahl(wert)}</td>
<td class="z">{f'{abstand:+.2f} %' if abstand is not None else '-'}</td>
</tr>""")
    return ''.join(zeilen)


def tradetabelle(trades):
    zeilen = []
    for t in reversed(trades[-60:]):
        try:
            gv = float(t['gewinn_prozent'])
        except (TypeError, ValueError):
            gv = 0.0
        klasse = 'gut' if gv > 0 else ('schlecht' if gv < 0 else '')
        ist_verkauf = t['typ'] == 'VERKAUF'
        zeilen.append(f"""<tr>
<td>{kurz(t['zeit'])}</td>
<td><b>{t['markt'].split('/')[0]}</b></td>
<td>{t['typ'].capitalize()}</td>
<td class="z">{float(t['preis']):.4f}</td>
<td class="z">{zahl(float(t['wert']))}</td>
<td class="z {klasse}">{f'{gv:+.2f} %' if ist_verkauf else '-'}</td>
<td>{t['grund']}</td>
</tr>""")
    return ''.join(zeilen)


# ------------------------------------------------------------- Seite

def main():
    letzter = lade_json('last_run.json', {})
    zustand = lade_json('positions.json', {})
    trades = lade_csv('trades.csv')
    verlauf = lade_csv('history.csv')

    import yaml
    with open(os.path.join(ORDNER, 'config.yaml')) as f:
        cfg = yaml.safe_load(f)

    start = float(cfg['startkapital'])
    daten = letzter.get('daten', {})
    gesamt = float(letzter.get('gesamtwert', start))
    investiert = int(letzter.get('investiert', 0))
    anzahl = int(letzter.get('anzahl_maerkte', len(cfg['maerkte'])))
    aktiv = bool(letzter.get('aktiv', True))

    ergebnis = gesamt - start
    ergebnis_pc = (gesamt / start - 1) * 100 if start else 0.0
    kl = 'gut' if ergebnis > 0 else ('schlecht' if ergebnis < 0 else '')

    punkte = []
    for z in verlauf:
        try:
            punkte.append((z['zeit'], float(z['gesamtwert'])))
        except (KeyError, TypeError, ValueError):
            continue
    punkte = punkte[-600:]

    verkaeufe = [t for t in trades if t['typ'] == 'VERKAUF']
    if verkaeufe:
        werte = []
        for t in verkaeufe:
            try:
                werte.append(float(t['gewinn_prozent']))
            except (TypeError, ValueError):
                pass
        gewinner = sum(1 for w in werte if w > 0)
        quote = f"{gewinner / len(werte) * 100:.0f} %" if werte else '-'
        schnitt = f"{sum(werte) / len(werte):+.2f} %" if werte else '-'
    else:
        quote, schnitt = '-', '-'

    stand_alter = ''
    if letzter.get('zeit'):
        try:
            minuten = (datetime.now(timezone.utc)
                       - datetime.fromisoformat(letzter['zeit'])).total_seconds() / 60
            stand_alter = (f'<span class="marke offen">vor {minuten:.0f} min</span>'
                           if minuten < 30 else
                           f'<span class="marke warn">vor {minuten/60:.1f} h</span>')
        except Exception:
            pass

    def var(name):
        return f"  --{name}: {T[name][0]};\n"

    def var_d(name):
        return f"    --{name}: {T[name][1]};\n"

    css_hell = ''.join(var(k) for k in T)
    css_dunkel = ''.join(var_d(k) for k in T)

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
@media (prefers-color-scheme: dark) {{
  :root {{
{css_dunkel}  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 20px 16px 64px;
  background: var(--plane); color: var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
}}
.huelle {{ max-width: 1040px; margin: 0 auto; }}
h1 {{ font-size: 20px; margin: 0 0 2px; letter-spacing: -0.01em; }}
h2 {{ font-size: 15px; margin: 32px 0 10px; color: var(--ink2); font-weight: 600; }}
.kopf {{ display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
         margin-bottom: 22px; }}
.kopf p {{ margin: 0; color: var(--muted); font-size: 13px; }}
.karten {{ display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }}
.karte {{ background: var(--surface); border: 1px solid var(--rand);
          border-radius: 10px; padding: 14px 16px; }}
.karte .titel {{ font-size: 12px; color: var(--muted); margin-bottom: 6px;
                 text-transform: uppercase; letter-spacing: 0.04em; }}
.karte .wert {{ font-size: 26px; font-weight: 600; letter-spacing: -0.02em;
                font-variant-numeric: tabular-nums; }}
.karte .neben {{ font-size: 13px; color: var(--ink2); margin-top: 2px;
                 font-variant-numeric: tabular-nums; }}
.gut {{ color: var(--gut); }}
.schlecht {{ color: var(--schlecht); }}
.chartbox {{ position: relative; background: var(--surface);
             border: 1px solid var(--rand); border-radius: 10px; padding: 8px; }}
.chart {{ width: 100%; height: auto; display: block; touch-action: pan-y; }}
.gitter {{ stroke: var(--grid); stroke-width: 1; }}
.basis {{ stroke: var(--axis); stroke-width: 1; }}
.bezug {{ stroke: var(--muted); stroke-width: 1; stroke-dasharray: 4 4; }}
.linie {{ fill: none; stroke: var(--serie); stroke-width: 2;
          stroke-linejoin: round; stroke-linecap: round; }}
.flaeche {{ fill: var(--serie); opacity: 0.08; stroke: none; }}
.kreuz {{ stroke: var(--muted); stroke-width: 1; }}
.punkt {{ fill: var(--serie); stroke: var(--surface); stroke-width: 2; }}
.achse {{ fill: var(--muted); font-size: 12px;
          font-family: system-ui, sans-serif; font-variant-numeric: tabular-nums; }}
.tipp {{ position: absolute; background: var(--surface); color: var(--ink);
         border: 1px solid var(--rand); border-radius: 8px; padding: 6px 10px;
         font-size: 13px; pointer-events: none; white-space: nowrap;
         box-shadow: 0 4px 14px rgba(0,0,0,0.12);
         font-variant-numeric: tabular-nums; z-index: 5; }}
.rolle {{ overflow-x: auto; background: var(--surface);
          border: 1px solid var(--rand); border-radius: 10px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th {{ text-align: left; font-weight: 600; font-size: 12px; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.04em;
      padding: 10px 12px; border-bottom: 1px solid var(--rand); white-space: nowrap; }}
td {{ padding: 9px 12px; border-bottom: 1px solid var(--rand); white-space: nowrap; }}
tr:last-child td {{ border-bottom: none; }}
.z {{ text-align: right; font-variant-numeric: tabular-nums; }}
.marke {{ font-size: 12px; padding: 2px 8px; border-radius: 99px;
          background: var(--grid); color: var(--ink2); }}
.marke.offen {{ background: color-mix(in oklab, var(--serie) 16%, transparent);
                color: var(--serie); }}
.marke.warn {{ background: color-mix(in oklab, var(--schlecht) 16%, transparent);
               color: var(--schlecht); }}
.hinweis {{ color: var(--muted); background: var(--surface);
            border: 1px solid var(--rand); border-radius: 10px;
            padding: 20px; margin: 0; font-size: 14px; }}
footer {{ margin-top: 36px; color: var(--muted); font-size: 12px; }}
footer a {{ color: var(--ink2); }}
</style>
</head>
<body>
<div class="huelle">

<div class="kopf">
  <h1>Trading-Bot</h1>
  {stand_alter}
  {'<span class="marke">pausiert</span>' if not aktiv else ''}
</div>
<p style="margin:-16px 0 22px;color:var(--muted);font-size:13px">
  Papier-Depot, kein echtes Geld &middot; Stand {kurz(letzter.get('zeit', ''))} UTC
</p>

<div class="karten">
  <div class="karte">
    <div class="titel">Depotwert</div>
    <div class="wert">{zahl(gesamt)} &euro;</div>
    <div class="neben">Start {zahl(start)} &euro;</div>
  </div>
  <div class="karte">
    <div class="titel">Ergebnis</div>
    <div class="wert {kl}">{ergebnis:+,.2f} &euro;</div>
    <div class="neben {kl}">{ergebnis_pc:+.2f} %</div>
  </div>
  <div class="karte">
    <div class="titel">Investiert</div>
    <div class="wert">{investiert} <span style="font-size:16px;color:var(--muted)">/ {anzahl}</span></div>
    <div class="neben">Maerkte</div>
  </div>
  <div class="karte">
    <div class="titel">Trades</div>
    <div class="wert">{len(trades)}</div>
    <div class="neben">davon {len(verkaeufe)} geschlossen</div>
  </div>
  <div class="karte">
    <div class="titel">Trefferquote</div>
    <div class="wert">{quote}</div>
    <div class="neben">Schnitt {schnitt}</div>
  </div>
</div>

<h2>Verlauf des Depotwerts</h2>
{linienchart(punkte, start)}

<h2>Positionen</h2>
<div class="rolle">
<table>
<thead><tr>
<th>Markt</th><th>Status</th><th class="z">Kurs</th><th class="z">Einstieg</th>
<th class="z">G/V</th><th class="z">Wert &euro;</th><th class="z">Abstand MA</th>
</tr></thead>
<tbody>{positionstabelle(zustand, daten)}</tbody>
</table>
</div>
<p style="color:var(--muted);font-size:13px;margin-top:8px">
  <b>Abstand MA</b>: wie weit der schnelle Durchschnitt vom langsamen entfernt ist.
  Negativ heisst noch kein Kaufsignal; bei 0 kreuzen sich die Linien.
</p>

<h2>Letzte Trades</h2>
<div class="rolle">
<table>
<thead><tr>
<th>Zeit</th><th>Markt</th><th>Typ</th><th class="z">Kurs</th>
<th class="z">Wert &euro;</th><th class="z">G/V</th><th>Grund</th>
</tr></thead>
<tbody>{tradetabelle(trades) or
  '<tr><td colspan="7" style="color:var(--muted)">Noch keine Trades. '
  'Der Bot kauft erst, wenn der schnelle Durchschnitt den langsamen von '
  'unten nach oben kreuzt.</td></tr>'}</tbody>
</table>
</div>

<footer>
  MA{cfg['ma_schnell']}/{cfg['ma_langsam']} &middot;
  Stop-Loss {cfg['stop_loss']*100:.0f} % &middot;
  Take-Profit {'aus' if not cfg.get('take_profit') else f"{cfg['take_profit']*100:.0f} %"} &middot;
  Gebuehr {cfg['gebuehr']*100:.2f} %<br>
  Seite aktualisiert sich alle 5 Minuten selbst. Einstellungen aenderst du in
  <code>config.yaml</code> im Repository.
</footer>

</div>
</body>
</html>"""

    os.makedirs(os.path.dirname(ZIEL), exist_ok=True)
    with open(ZIEL, 'w') as f:
        f.write(html)
    print(f"  Dashboard geschrieben: {len(html)} Zeichen")


if __name__ == '__main__':
    main()
