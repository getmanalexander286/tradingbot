"""
Ein Durchlauf des Paper-Trading-Bots - fuer mehrere Strategien gleichzeitig.

Jede Strategie hat ihr eigenes Depot und ihren eigenen Ordner unter state/.
Die Kursdaten werden nur einmal geholt und von allen Strategien genutzt.
"""

import ccxt
import pandas as pd
import yaml
import json
import csv
import os
from datetime import datetime, timezone

ORDNER = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ORDNER, 'config.yaml')
STAND = os.path.join(ORDNER, 'state')

VERLAUF_MAX = 5000


def jetzt():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def altlasten_aufraeumen():
    """Entfernt die Dateien der Einzel-Strategie-Version aus state/."""
    for name in ('positions.json', 'trades.csv', 'history.csv'):
        pfad = os.path.join(STAND, name)
        if os.path.exists(pfad):
            os.remove(pfad)
            print(f"  alte Datei entfernt: state/{name}")


# ------------------------------------------------------------------ Zustand

def pfad(kuerzel, datei):
    return os.path.join(STAND, kuerzel, datei)


def zustand_laden(kuerzel, maerkte, startkapital):
    p = pfad(kuerzel, 'positions.json')
    zustand = json.load(open(p)) if os.path.exists(p) else {}

    kapital = startkapital / len(maerkte)
    for markt in maerkte:
        if markt not in zustand:
            zustand[markt] = {'bargeld': kapital, 'menge': 0.0,
                              'einstieg': 0.0, 'einstiegszeit': None}
    for markt in list(zustand):
        if markt not in maerkte and zustand[markt]['menge'] == 0:
            del zustand[markt]
    return zustand


def zustand_speichern(kuerzel, zustand):
    os.makedirs(os.path.join(STAND, kuerzel), exist_ok=True)
    with open(pfad(kuerzel, 'positions.json'), 'w') as f:
        json.dump(zustand, f, indent=2, sort_keys=True)


def trade_anhaengen(kuerzel, zeile):
    os.makedirs(os.path.join(STAND, kuerzel), exist_ok=True)
    p = pfad(kuerzel, 'trades.csv')
    neu = not os.path.exists(p)
    with open(p, 'a', newline='') as f:
        s = csv.writer(f)
        if neu:
            s.writerow(['zeit', 'markt', 'typ', 'preis', 'menge', 'wert',
                        'gewinn_prozent', 'grund'])
        s.writerow(zeile)


def verlauf_anhaengen(kuerzel, zeit, gesamtwert, investiert, anzahl):
    os.makedirs(os.path.join(STAND, kuerzel), exist_ok=True)
    p = pfad(kuerzel, 'history.csv')
    neu = not os.path.exists(p)
    with open(p, 'a', newline='') as f:
        s = csv.writer(f)
        if neu:
            s.writerow(['zeit', 'gesamtwert', 'investiert', 'anzahl_maerkte'])
        s.writerow([zeit, round(gesamtwert, 4), investiert, anzahl])

    zeilen = open(p).readlines()
    if len(zeilen) > VERLAUF_MAX + 1:
        open(p, 'w').writelines([zeilen[0]] + zeilen[-VERLAUF_MAX:])


# ------------------------------------------------------------------ Boerse

def kursdaten_holen(boerse, maerkte, strategien):
    """Holt Preise und Tageskerzen einmal und berechnet alle MA-Paare daraus."""
    tickers = boerse.fetch_tickers(maerkte)
    daten = {}

    for markt in maerkte:
        t = tickers.get(markt)
        if not t or t.get('last') is None:
            print(f"  {markt}: kein Kurs - uebersprungen")
            continue

        eintrag = {'preis': float(t['last']), 'strategien': {}}

        try:
            kerzen = boerse.fetch_ohlcv(markt, timeframe='1d', limit=250)
            schluss = pd.Series([k[4] for k in kerzen])
            for st in strategien:
                schnell = schluss.rolling(st['ma_schnell']).mean().iloc[-1]
                langsam = schluss.rolling(st['ma_langsam']).mean().iloc[-1]
                if pd.isna(schnell) or pd.isna(langsam):
                    eintrag['strategien'][st['kuerzel']] = {
                        'signal': None, 'ma_schnell': 0.0, 'ma_langsam': 0.0}
                else:
                    eintrag['strategien'][st['kuerzel']] = {
                        'signal': 1 if schnell > langsam else 0,
                        'ma_schnell': float(schnell), 'ma_langsam': float(langsam)}
        except Exception as fehler:
            print(f"  {markt}: Kerzen nicht abrufbar ({fehler})")
            for st in strategien:
                eintrag['strategien'][st['kuerzel']] = {
                    'signal': None, 'ma_schnell': 0.0, 'ma_langsam': 0.0}

        daten[markt] = eintrag
    return daten


# ------------------------------------------------------------------ Logik

def strategie_durchlaufen(st, zustand, daten, cfg, zeit):
    meldungen = []
    kuerzel = st['kuerzel']

    for markt, d in daten.items():
        if markt not in zustand:
            continue
        p = zustand[markt]
        preis = d['preis']
        s = d['strategien'].get(kuerzel, {})
        signal = s.get('signal')
        investiert = p['menge'] > 0
        name = markt.split('/')[0]

        grund = None
        if investiert and p['einstieg'] > 0:
            if preis <= p['einstieg'] * (1 - cfg['stop_loss']):
                grund = 'Stop-Loss'
            elif cfg.get('take_profit', 0) > 0 and preis >= p['einstieg'] * (1 + cfg['take_profit']):
                grund = 'Take-Profit'

        if grund:
            erloes = p['menge'] * preis * (1 - cfg['gebuehr'])
            gewinn = (preis / p['einstieg'] - 1) * 100
            trade_anhaengen(kuerzel, [zeit, markt, 'VERKAUF', round(preis, 8),
                                      round(p['menge'], 10), round(erloes, 4),
                                      round(gewinn, 3), grund])
            p.update({'bargeld': erloes, 'menge': 0.0, 'einstieg': 0.0, 'einstiegszeit': None})
            meldungen.append(f"{grund} {name} zu {preis:.4f} ({gewinn:+.1f} %)")
            continue

        if not cfg['aktiv'] or signal is None:
            continue

        if signal == 1 and not investiert and p['bargeld'] > 0:
            menge = (p['bargeld'] * (1 - cfg['gebuehr'])) / preis
            trade_anhaengen(kuerzel, [zeit, markt, 'KAUF', round(preis, 8),
                                      round(menge, 10), round(p['bargeld'], 4),
                                      0.0, 'MA-Signal'])
            meldungen.append(f"KAUF {name} {menge:.6f} zu {preis:.4f}")
            p.update({'bargeld': 0.0, 'menge': menge, 'einstieg': preis, 'einstiegszeit': zeit})

        elif signal == 0 and investiert:
            erloes = p['menge'] * preis * (1 - cfg['gebuehr'])
            gewinn = (preis / p['einstieg'] - 1) * 100 if p['einstieg'] else 0.0
            trade_anhaengen(kuerzel, [zeit, markt, 'VERKAUF', round(preis, 8),
                                      round(p['menge'], 10), round(erloes, 4),
                                      round(gewinn, 3), 'MA-Signal'])
            meldungen.append(f"VERKAUF {name} zu {preis:.4f} ({gewinn:+.1f} %)")
            p.update({'bargeld': erloes, 'menge': 0.0, 'einstieg': 0.0, 'einstiegszeit': None})

    gesamt = 0.0
    investiert_anzahl = 0
    for markt, p in zustand.items():
        preis = daten.get(markt, {}).get('preis', p['einstieg'])
        gesamt += p['bargeld'] + p['menge'] * preis
        if p['menge'] > 0:
            investiert_anzahl += 1

    return meldungen, gesamt, investiert_anzahl


# ------------------------------------------------------------------ Start

def main():
    cfg = yaml.safe_load(open(CONFIG))
    zeit = jetzt()
    print(f"Durchlauf {zeit}")

    os.makedirs(STAND, exist_ok=True)
    altlasten_aufraeumen()

    boerse = ccxt.kraken({'enableRateLimit': True})
    boerse.load_markets()

    maerkte = [m for m in cfg['maerkte'] if m in boerse.markets]
    for m in cfg['maerkte']:
        if m not in boerse.markets:
            print(f"  {m} kennt Kraken nicht - uebersprungen")
    if not maerkte:
        raise SystemExit("Kein Markt verfuegbar.")

    strategien = cfg['strategien']
    daten = kursdaten_holen(boerse, maerkte, strategien)
    if not daten:
        raise SystemExit("Keine Kurse erhalten.")

    uebersicht = {}
    for st in strategien:
        zustand = zustand_laden(st['kuerzel'], maerkte, cfg['startkapital'])
        meldungen, gesamt, inv = strategie_durchlaufen(st, zustand, daten, cfg, zeit)
        zustand_speichern(st['kuerzel'], zustand)
        verlauf_anhaengen(st['kuerzel'], zeit, gesamt, inv, len(maerkte))

        uebersicht[st['kuerzel']] = {
            'name': st['name'], 'ma_schnell': st['ma_schnell'],
            'ma_langsam': st['ma_langsam'], 'gesamtwert': gesamt, 'investiert': inv,
            'meldungen': meldungen}

        print(f"  [{st['name']}] {gesamt:.2f} EUR | {inv}/{len(maerkte)} investiert")
        for m in meldungen:
            print(f"      >> {m}")

    with open(os.path.join(STAND, 'last_run.json'), 'w') as f:
        json.dump({'zeit': zeit, 'aktiv': cfg['aktiv'], 'anzahl_maerkte': len(maerkte),
                   'strategien': uebersicht,
                   'daten': {m: {'preis': round(d['preis'], 8),
                                 'strategien': d['strategien']}
                             for m, d in daten.items()}},
                  f, indent=2, sort_keys=True)


if __name__ == '__main__':
    main()
