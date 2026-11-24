"""
Holt Kurse fuer Krypto (Kraken) und Aktien (Yahoo Finance).

Liefert je Wert den aktuellen Preis und die Schlusskurs-Reihen in allen
benoetigten Zeitfenstern, plus die Information, wie frisch der letzte
Kurs ist - wichtig bei Aktien, deren Boerse nachts geschlossen ist.
"""

import time
from datetime import datetime, timezone

# Wie viele Kerzen je Zeitfenster geholt werden
TIEFE = {'1d': 250, '1h': 500, '15m': 500, '5m': 500}

# Umrechnung der Zeitfenster fuer Yahoo Finance
YAHOO = {'1d': ('1y', '1d'), '1h': ('1mo', '1h'),
         '15m': ('5d', '15m'), '5m': ('5d', '5m')}

# Ab wann ein Kurs als veraltet gilt (Minuten)
FRISCHE = {'1d': 60 * 36, '1h': 150, '15m': 45, '5m': 20}


def jetzt_utc():
    return datetime.now(timezone.utc)


def krypto_holen(boerse, maerkte, zeitfenster):
    """{symbol: {'preis', 'typ', 'name', 'reihen': {zf: [schlusskurse]}, 'alter_min'}}"""
    ergebnis = {}
    try:
        tickers = boerse.fetch_tickers(maerkte)
    except Exception as fehler:
        print(f"  Krypto-Kurse nicht abrufbar: {fehler}")
        return ergebnis

    for markt in maerkte:
        t = tickers.get(markt)
        if not t or t.get('last') is None:
            print(f"  {markt}: kein Kurs")
            continue

        reihen = {}
        for zf in zeitfenster:
            try:
                kerzen = boerse.fetch_ohlcv(markt, timeframe=zf, limit=TIEFE.get(zf, 300))
                reihen[zf] = [k[4] for k in kerzen]
            except Exception as fehler:
                print(f"  {markt} [{zf}]: {fehler}")
                reihen[zf] = []
            time.sleep(0.35)

        ergebnis[markt] = {'preis': float(t['last']), 'typ': 'krypto',
                           'name': markt.split('/')[0], 'reihen': reihen,
                           'alter_min': 0.0}
    return ergebnis


def aktien_holen(aktien, zeitfenster):
    """Holt alle Aktien gebuendelt ueber yfinance."""
    ergebnis = {}
    if not aktien:
        return ergebnis

    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance fehlt - Aktien werden uebersprungen")
        return ergebnis

    symbole = [a['symbol'] for a in aktien]
    namen = {a['symbol']: a.get('name', a['symbol']) for a in aktien}

    for zf in zeitfenster:
        if zf not in YAHOO:
            continue
        zeitraum, intervall = YAHOO[zf]
        try:
            roh = yf.download(symbole, period=zeitraum, interval=intervall,
                              auto_adjust=True, progress=False,
                              group_by='ticker', threads=True)
        except Exception as fehler:
            print(f"  Aktien [{zf}] nicht abrufbar: {fehler}")
            continue

        for sym in symbole:
            try:
                if len(symbole) == 1:
                    spalte = roh['Close']
                else:
                    spalte = roh[sym]['Close']
                spalte = spalte.dropna()
                if spalte.empty:
                    print(f"  {sym} [{zf}]: keine Daten")
                    continue
                werte = [float(x) for x in spalte.tolist()]
                letzte_zeit = spalte.index[-1].to_pydatetime()
                if letzte_zeit.tzinfo is None:
                    letzte_zeit = letzte_zeit.replace(tzinfo=timezone.utc)
                alter = (jetzt_utc() - letzte_zeit).total_seconds() / 60

                eintrag = ergebnis.setdefault(sym, {
                    'preis': werte[-1], 'typ': 'aktie',
                    'name': namen[sym], 'reihen': {}, 'alter_min': alter})
                eintrag['reihen'][zf] = werte
                # Der Preis kommt aus dem feinsten verfuegbaren Zeitfenster
                if alter <= eintrag['alter_min']:
                    eintrag['preis'] = werte[-1]
                    eintrag['alter_min'] = alter
            except Exception as fehler:
                print(f"  {sym} [{zf}]: {fehler}")

    fehlend = [s for s in symbole if s not in ergebnis]
    if fehlend:
        print(f"  Keine Daten fuer: {', '.join(fehlend)}")
    return ergebnis


def alles_holen(boerse, cfg, zeitfenster):
    daten = krypto_holen(boerse, cfg.get('krypto', []), zeitfenster)
    daten.update(aktien_holen(cfg.get('aktien', []), zeitfenster))
    return daten


def ist_frisch(eintrag, zeitfenster):
    """True, wenn der Kurs aktuell genug ist, um darauf zu handeln."""
    return eintrag.get('alter_min', 0) <= FRISCHE.get(zeitfenster, 60)
