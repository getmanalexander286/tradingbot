"""
Ein Durchlauf des Paper-Trading-Bots fuer mehrere Strategien.

Jede Strategie hat ein eigenes Depot unter state/<kuerzel>/.
Kursdaten werden einmal geholt und von allen Strategien genutzt.
"""

import ccxt
import pandas as pd
import yaml
import json
import csv
import os
from datetime import datetime, timezone

import marktdaten

ORDNER = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ORDNER, 'config.yaml')
STAND = os.path.join(ORDNER, 'state')
VERLAUF_MAX = 5000


def jetzt():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ------------------------------------------------------------------ Zustand

def pfad(kuerzel, datei):
    return os.path.join(STAND, kuerzel, datei)


def zustand_laden(kuerzel, symbole, startkapital):
    p = pfad(kuerzel, 'positions.json')
    zustand = json.load(open(p)) if os.path.exists(p) else {}
    kapital = startkapital / len(symbole)
    for s in symbole:
        if s not in zustand:
            zustand[s] = {'bargeld': kapital, 'menge': 0.0,
                          'einstieg': 0.0, 'einstiegszeit': None}
    for s in list(zustand):
        if s not in symbole and zustand[s]['menge'] == 0:
            del zustand[s]
    return zustand


def zustand_speichern(kuerzel, zustand):
    os.makedirs(os.path.join(STAND, kuerzel), exist_ok=True)
    json.dump(zustand, open(pfad(kuerzel, 'positions.json'), 'w'),
              indent=2, sort_keys=True)


def trade_anhaengen(kuerzel, zeile):
    os.makedirs(os.path.join(STAND, kuerzel), exist_ok=True)
    p = pfad(kuerzel, 'trades.csv')
    neu = not os.path.exists(p)
    with open(p, 'a', newline='') as f:
        s = csv.writer(f)
        if neu:
            s.writerow(['zeit', 'wert', 'typ', 'preis', 'menge', 'betrag',
                        'gewinn_prozent', 'grund'])
        s.writerow(zeile)


def verlauf_anhaengen(kuerzel, zeit, gesamtwert, investiert, anzahl):
    os.makedirs(os.path.join(STAND, kuerzel), exist_ok=True)
    p = pfad(kuerzel, 'history.csv')
    neu = not os.path.exists(p)
    with open(p, 'a', newline='') as f:
        s = csv.writer(f)
        if neu:
            s.writerow(['zeit', 'gesamtwert', 'investiert', 'anzahl_werte'])
        s.writerow([zeit, round(gesamtwert, 4), investiert, anzahl])
    zeilen = open(p).readlines()
    if len(zeilen) > VERLAUF_MAX + 1:
        open(p, 'w').writelines([zeilen[0]] + zeilen[-VERLAUF_MAX:])


# ------------------------------------------------------------------ Signale

def signal_berechnen(schlusskurse, ma_schnell, ma_langsam):
    if len(schlusskurse) < ma_langsam + 1:
        return None, 0.0, 0.0
    reihe = pd.Series(schlusskurse)
    schnell = reihe.rolling(ma_schnell).mean().iloc[-1]
    langsam = reihe.rolling(ma_langsam).mean().iloc[-1]
    if pd.isna(schnell) or pd.isna(langsam):
        return None, 0.0, 0.0
    return (1 if schnell > langsam else 0), float(schnell), float(langsam)


def nach_tagesschluss(typ, cfg, zeitpunkt):
    """True, wenn fuer diesen Werttyp der Handelstag vorbei ist."""
    schluss = cfg.get('tagesschluss_utc', {}).get(typ)
    if not schluss:
        return False
    stunde, minute = (int(x) for x in schluss.split(':'))
    return (zeitpunkt.hour, zeitpunkt.minute) >= (stunde, minute)


def minuten_seit(iso, zeitpunkt):
    if not iso:
        return 1e9
    try:
        return (zeitpunkt - datetime.fromisoformat(iso)).total_seconds() / 60
    except Exception:
        return 1e9


# ------------------------------------------------------------------ Logik

def strategie_durchlaufen(st, zustand, daten, cfg, zeit, zeitpunkt):
    meldungen = []
    k = st['kuerzel']
    zf = st.get('zeitfenster', '1d')
    stop_loss = st.get('stop_loss', cfg['stop_loss'])
    take_profit = st.get('take_profit', cfg.get('take_profit', 0))
    tagesschluss = st.get('tagesschluss', False)
    mindesthaltedauer = st.get('mindesthaltedauer_minuten', 0)
    gebuehr = cfg['gebuehr']

    signale = {}

    for symbol, d in daten.items():
        if symbol not in zustand:
            continue
        p = zustand[symbol]
        preis = d['preis']
        investiert = p['menge'] > 0
        name = d['name']

        sig, ma_s, ma_l = signal_berechnen(d['reihen'].get(zf, []),
                                           st['ma_schnell'], st['ma_langsam'])
        signale[symbol] = {'signal': sig, 'ma_schnell': ma_s, 'ma_langsam': ma_l}

        def verkaufen(grund):
            erloes = p['menge'] * preis * (1 - gebuehr)
            gewinn = (preis / p['einstieg'] - 1) * 100 if p['einstieg'] else 0.0
            trade_anhaengen(k, [zeit, symbol, 'VERKAUF', round(preis, 8),
                                round(p['menge'], 10), round(erloes, 4),
                                round(gewinn, 3), grund])
            p.update({'bargeld': erloes, 'menge': 0.0, 'einstieg': 0.0,
                      'einstiegszeit': None})
            meldungen.append(f"{grund} {name} zu {preis:.4f} ({gewinn:+.1f} %)")

        # --- Risiko zuerst, gilt auch im Pausenmodus ---
        if investiert and p['einstieg'] > 0:
            if preis <= p['einstieg'] * (1 - stop_loss):
                verkaufen('Stop-Loss')
                continue
            if take_profit > 0 and preis >= p['einstieg'] * (1 + take_profit):
                verkaufen('Take-Profit')
                continue

        feierabend = tagesschluss and nach_tagesschluss(d['typ'], cfg, zeitpunkt)

        # --- Daytrader: abends glattstellen ---
        if investiert and feierabend:
            verkaufen('Tagesschluss')
            continue

        if not cfg['aktiv'] or sig is None:
            continue

        # Veraltete Kurse (geschlossene Boerse) nicht handeln
        if not marktdaten.ist_frisch(d, zf):
            continue

        if investiert and minuten_seit(p['einstiegszeit'], zeitpunkt) < mindesthaltedauer:
            continue

        if sig == 1 and not investiert and p['bargeld'] > 0 and not feierabend:
            menge = (p['bargeld'] * (1 - gebuehr)) / preis
            trade_anhaengen(k, [zeit, symbol, 'KAUF', round(preis, 8),
                                round(menge, 10), round(p['bargeld'], 4),
                                0.0, 'MA-Signal'])
            meldungen.append(f"KAUF {name} {menge:.6f} zu {preis:.4f}")
            p.update({'bargeld': 0.0, 'menge': menge, 'einstieg': preis,
                      'einstiegszeit': zeit})

        elif sig == 0 and investiert:
            verkaufen('MA-Signal')

    gesamt = 0.0
    investiert_anzahl = 0
    for symbol, p in zustand.items():
        preis = daten.get(symbol, {}).get('preis', p['einstieg'])
        gesamt += p['bargeld'] + p['menge'] * preis
        if p['menge'] > 0:
            investiert_anzahl += 1

    return meldungen, gesamt, investiert_anzahl, signale


# ------------------------------------------------------------------ Start

def main():
    cfg = yaml.safe_load(open(CONFIG))
    zeitpunkt = datetime.now(timezone.utc)
    zeit = zeitpunkt.replace(microsecond=0).isoformat()
    print(f"Durchlauf {zeit}")

    os.makedirs(STAND, exist_ok=True)

    zeitfenster = sorted({st.get('zeitfenster', '1d') for st in cfg['strategien']})
    print(f"  Zeitfenster: {', '.join(zeitfenster)}")

    boerse = ccxt.kraken({'enableRateLimit': True})
    boerse.load_markets()
    cfg['krypto'] = [m for m in cfg.get('krypto', []) if m in boerse.markets]

    daten = marktdaten.alles_holen(boerse, cfg, zeitfenster)
    if not daten:
        raise SystemExit("Keine Kurse erhalten.")
    symbole = sorted(daten)
    print(f"  {len(symbole)} Werte mit Kursen "
          f"({sum(1 for s in symbole if daten[s]['typ']=='krypto')} Krypto, "
          f"{sum(1 for s in symbole if daten[s]['typ']=='aktie')} Aktien)")

    uebersicht = {}
    alle_signale = {}

    for st in cfg['strategien']:
        zustand = zustand_laden(st['kuerzel'], symbole, cfg['startkapital'])
        meldungen, gesamt, inv, signale = strategie_durchlaufen(
            st, zustand, daten, cfg, zeit, zeitpunkt)
        zustand_speichern(st['kuerzel'], zustand)
        verlauf_anhaengen(st['kuerzel'], zeit, gesamt, inv, len(symbole))

        uebersicht[st['kuerzel']] = {
            'name': st['name'], 'zeitfenster': st.get('zeitfenster', '1d'),
            'gesamtwert': gesamt, 'investiert': inv, 'meldungen': meldungen}
        alle_signale[st['kuerzel']] = signale

        print(f"  [{st['name']}] {gesamt:.2f} EUR | {inv}/{len(symbole)} investiert")
        for m in meldungen:
            print(f"      >> {m}")

    json.dump({
        'zeit': zeit, 'aktiv': cfg['aktiv'], 'anzahl_werte': len(symbole),
        'strategien': uebersicht,
        'werte': {s: {'preis': round(daten[s]['preis'], 8),
                      'typ': daten[s]['typ'], 'name': daten[s]['name'],
                      'alter_min': round(daten[s]['alter_min'], 1)}
                  for s in symbole},
        'signale': alle_signale,
    }, open(os.path.join(STAND, 'last_run.json'), 'w'), indent=2, sort_keys=True)


if __name__ == '__main__':
    main()
