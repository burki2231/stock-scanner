import io
import os
import pandas as pd
import requests
import yfinance as yf
import config as cfg

HEADERS = {"User-Agent": "Mozilla/5.0 (stock-scanner)"}
HERE = os.path.dirname(os.path.abspath(__file__))


def _wiki_tables(url: str):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return pd.read_html(io.StringIO(r.text))


def _clean(tickers):
    return sorted({str(t).strip().upper().replace(".", "-") for t in tickers if str(t).strip() and str(t) != "nan"})


def _load_file(name):
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [ln.split("#")[0].strip() for ln in f if ln.split("#")[0].strip()]


def get_universe(names=None):
    names = names or cfg.UNIVERSES
    out = []
    for name in names:
        try:
            if name == "sp500":
                t = _wiki_tables("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
                out += list(t["Symbol"])
            elif name == "nasdaq100":
                for t in _wiki_tables("https://en.wikipedia.org/wiki/Nasdaq-100"):
                    col = next((c for c in t.columns if str(c) in ("Ticker", "Symbol")), None)
                    if col is not None and len(t) > 50:
                        out += list(t[col])
                        break
            elif name == "custom":
                out += _load_file("tickers.txt")
        except Exception as e:  # internet/Wikipedia sorunu olursa yedek listeye düş
            print(f"[uyarı] {name} listesi alınamadı ({e}); fallback_tickers.txt kullanılıyor")
            out += _load_file("fallback_tickers.txt")
    tickers = _clean(out)
    if not tickers:
        tickers = _clean(_load_file("fallback_tickers.txt"))
    return tickers


def download_prices(tickers, period=None, batch=None):
    period = period or cfg.HISTORY_PERIOD
    batch = batch or cfg.BATCH_SIZE
    result = {}
    for i in range(0, len(tickers), batch):
        chunk = tickers[i:i + batch]
        print(f"  veri indiriliyor {i + 1}-{i + len(chunk)} / {len(tickers)}")
        try:
            raw = yf.download(chunk, period=period, group_by="ticker", auto_adjust=True,
                              threads=True, progress=False)
        except Exception as e:
            print(f"  [hata] batch alınamadı: {e}")
            continue
        if raw is None or raw.empty:
            continue
        for t in chunk:
            try:
                df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
                df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                if not df.empty:
                    result[t] = df
            except KeyError:
                continue
    return result


def download_intraday(tickers, period="5d", interval="5m", batch=40):
    """Gün içi (5 dk) veri. İndeks New York saatine çevrilir."""
    result = {}
    for i in range(0, len(tickers), batch):
        chunk = tickers[i:i + batch]
        print(f"  gün içi veri {i + 1}-{i + len(chunk)} / {len(tickers)}")
        try:
            raw = yf.download(chunk, period=period, interval=interval, group_by="ticker",
                              auto_adjust=True, threads=True, progress=False, prepost=False)
        except Exception as e:
            print(f"  [hata] gün içi batch alınamadı: {e}")
            continue
        if raw is None or raw.empty:
            continue
        for t in chunk:
            try:
                df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
                df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                if df.empty:
                    continue
                idx = df.index
                if idx.tz is None:
                    idx = idx.tz_localize("UTC")
                df.index = idx.tz_convert("America/New_York")
                result[t] = df
            except KeyError:
                continue
    return result
