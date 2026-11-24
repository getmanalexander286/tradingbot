"""
Ein einzelner Durchlauf des Paper-Trading-Bots.

Laeuft bei GitHub Actions nach Zeitplan. Kein Dauerbetrieb: jeder Aufruf
liest den Zustand aus state/, entscheidet, schreibt den neuen Zustand zurueck.
Dadurch braucht es keinen Server, der staendig laeuft.
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
POSITIONEN = os.path.join(STAND, 'positions.json')
TRADES = os.path.join(STAND, 'trades.csv')
VERLAUF = os.path.join(STAND, 'history.csv')

VERLAUF_MAX = 5000   # aeltere Zeilen werden abgeschnitten, damit das Repo klein bleibt


def jetzt():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ------------------------------------------------------------------ Zustand

def zustand_laden(maerkte, startkapital):
    if os.path.exists(POSITIONEN):
        with open(POSITIONEN) as f:
            zustand = json.load(f)
    else:
        zustand = {}

    kapital = startkapital / len(maerkte)
    for markt in maerkte:
        if markt not in zustand:
            zustand[markt] = {'bargeld': kapital, 'menge': 0.0,
                              'einstieg': 0.0, 'einstiegszeit': None}
    # Maerkte, die aus der Liste genommen wurden, bleiben erhalten solange
    # noch eine Position offen ist - sonst waere das Geld verloren.
    for markt in list(zustand):
        if markt not in maerkte and zustand[markt]['menge'] == 0:
            del zustand[markt]
    return zustand


def zustand_speichern(zustand):
    os.makedirs(STAND, exist_ok=True)
    with open(POSITIONEN, 'w') as f:
        json.dump(zustand, f, indent=2, sort_keys=True)


def trade_anhaengen(zeile):
    os.makedirs(STAND, exist_ok=True)
    neu = not os.path.exists(TRADES)
    with open(TRADES, 'a', newline='') as f:
        s = csv.writer(f)
        if neu:
            s.writerow(['zeit', 'markt', 'typ', 'preis', 'menge', 'wert',
                        'gewinn_prozent', 'grund'])
        s.writerow(zeile)


def verlauf_anhaengen(zeit, gesamtwert, investiert, anzahl):
    os.makedirs(STAND, exist_ok=True)
    neu = not os.path.exists(VERLAUF)
    with open(VERLAUF, 'a', newline='') as f:
        s = csv.writer(f)
        if neu:
            s.writerow(['zeit', 'gesamtwert', 'investiert', 'anzahl_maerkte'])
        s.writerow([zeit, round(gesamtwert, 4), investiert, anzahl])

    # auf die letzten VERLAUF_MAX Zeilen kuerzen
    with open(VERLAUF) as f:
        zeilen = f.readlines()
    if len(zeilen) > VERLAUF_MAX + 1:
        with open(VERLAUF, 'w') as f:
            f.writelines([zeilen[0]] + zeilen[-VERLAUF_MAX:])


# ------------------------------------------------------------------ Boerse

def marktdaten_holen(boerse, maerkte, cfg):
    """Gibt {markt: {'preis', 'ma_schnell', 'ma_langsam', 'signal'}} zurueck."""
    tickers = boerse.fetch_tickers(maerkte)
    daten = {}

    for markt in maerkte:
        t = tickers.get(markt)
        if not t or t.get('last') is None:
            print(f"  {markt}: kein Kurs erhalten - uebersprungen")
            continue
        preis = float(t['last'])

        try:
            kerzen = boerse.fetch_ohlcv(markt, timeframe='1d', limit=200)
            schluss = pd.Series([k[4] for k in kerzen])
            schnell = schluss.rolling(cfg['ma_schnell']).mean().iloc[-1]
            langsam = schluss.rolling(cfg['ma_langsam']).mean().iloc[-1]
            if pd.isna(langsam) or pd.isna(schnell):
                signal, schnell, langsam = None, 0.0, 0.0
            else:
                signal = 1 if schnell > langsam else 0
        except Exception as fehler:
            print(f"  {markt}: Signal nicht berechenbar ({fehler})")
            signal, schnell, langsam = None, 0.0, 0.0

        daten[markt] = {'preis': preis, 'signal': signal,
                        'ma_schnell': float(schnell), 'ma_langsam': float(langsam)}
    return daten


# ------------------------------------------------------------------ Logik

def entscheiden(zustand, daten, cfg, zeit):
    """Geht jeden Markt durch und handelt wo noetig. Gibt Meldungen zurueck."""
    meldungen = []

    for markt, d in daten.items():
        if markt not in zustand:
            continue
        p = zustand[markt]
        preis = d['preis']
        signal = d['signal']
        investiert = p['menge'] > 0
        name = markt.split('/')[0]

        # --- Risiko zuerst: gilt auch wenn der Bot pausiert ---
        grund = None
        if investiert and p['einstieg'] > 0:
            if preis <= p['einstieg'] * (1 - cfg['stop_loss']):
                grund = 'Stop-Loss'
            elif cfg.get('take_profit', 0) > 0 and preis >= p['einstieg'] * (1 + cfg['take_profit']):
                grund = 'Take-Profit'

        if grund:
            erloes = p['menge'] * preis * (1 - cfg['gebuehr'])
            gewinn = (preis / p['einstieg'] - 1) * 100
            trade_anhaengen([zeit, markt, 'VERKAUF', round(preis, 8),
                             round(p['menge'], 10), round(erloes, 4),
                             round(gewinn, 3), grund])
            p.update({'bargeld': erloes, 'menge': 0.0, 'einstieg': 0.0,
                      'einstiegszeit': None})
            meldungen.append(f"{grund} {name} zu {preis:.4f} ({gewinn:+.1f} %)")
            continue

        if not cfg['aktiv'] or signal is None:
            continue

        # --- Kaufen ---
        if signal == 1 and not investiert and p['bargeld'] > 0:
            menge = (p['bargeld'] * (1 - cfg['gebuehr'])) / preis
            trade_anhaengen([zeit, markt, 'KAUF', round(preis, 8),
                             round(menge, 10), round(p['bargeld'], 4), 0.0, 'MA-Signal'])
            meldungen.append(f"KAUF {name} {menge:.6f} zu {preis:.4f}")
            p.update({'bargeld': 0.0, 'menge': menge, 'einstieg': preis,
                      'einstiegszeit': zeit})

        # --- Verkaufen ---
        elif signal == 0 and investiert:
            erloes = p['menge'] * preis * (1 - cfg['gebuehr'])
            gewinn = (preis / p['einstieg'] - 1) * 100 if p['einstieg'] > 0 else 0.0
            trade_anhaengen([zeit, markt, 'VERKAUF', round(preis, 8),
                             round(p['menge'], 10), round(erloes, 4),
                             round(gewinn, 3), 'MA-Signal'])
            meldungen.append(f"VERKAUF {name} zu {preis:.4f} ({gewinn:+.1f} %)")
            p.update({'bargeld': erloes, 'menge': 0.0, 'einstieg': 0.0,
                      'einstiegszeit': None})

    return meldungen


def bewerten(zustand, daten):
    gesamt = 0.0
    investiert = 0
    for markt, p in zustand.items():
        preis = daten.get(markt, {}).get('preis', p['einstieg'])
        gesamt += p['bargeld'] + p['menge'] * preis
        if p['menge'] > 0:
            investiert += 1
    return gesamt, investiert


# ------------------------------------------------------------------ Start

def main():
    with open(CONFIG) as f:
        cfg = yaml.safe_load(f)

    zeit = jetzt()
    print(f"Durchlauf {zeit}")

    boerse = ccxt.kraken({'enableRateLimit': True})
    boerse.load_markets()

    maerkte = [m for m in cfg['maerkte'] if m in boerse.markets]
    for m in cfg['maerkte']:
        if m not in boerse.markets:
            print(f"  {m} kennt Kraken nicht - uebersprungen")
    if not maerkte:
        raise SystemExit("Kein Markt verfuegbar.")

    zustand = zustand_laden(maerkte, cfg['startkapital'])
    daten = marktdaten_holen(boerse, maerkte, cfg)
    if not daten:
        raise SystemExit("Keine Kurse erhalten - Durchlauf abgebrochen.")

    meldungen = entscheiden(zustand, daten, cfg, zeit)
    gesamt, investiert = bewerten(zustand, daten)

    zustand_speichern(zustand)
    verlauf_anhaengen(zeit, gesamt, investiert, len(maerkte))

    # Momentaufnahme fuers Dashboard
    with open(os.path.join(STAND, 'last_run.json'), 'w') as f:
        json.dump({'zeit': zeit, 'gesamtwert': gesamt, 'investiert': investiert,
                   'anzahl_maerkte': len(maerkte), 'aktiv': cfg['aktiv'],
                   'meldungen': meldungen,
                   'daten': {m: {k: round(v, 8) if isinstance(v, float) else v
                                 for k, v in d.items()} for m, d in daten.items()}},
                  f, indent=2, sort_keys=True)

    for m in meldungen:
        print(f"  >> {m}")
    print(f"  Depotwert {gesamt:.2f} EUR | {investiert}/{len(maerkte)} investiert"
          f" | {'aktiv' if cfg['aktiv'] else 'pausiert'}")


if __name__ == '__main__':
    main()
