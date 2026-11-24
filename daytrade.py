"""Day trade modu: günün en iyi tek hissesini seçer.

  python daytrade.py --dry-run             # canlı (piyasa açıkken), bildirim atmaz
  python daytrade.py                       # canlı + telefona bildirim
  python daytrade.py --watch               # her 5 dk tarar, yeni güçlü aday çıkınca bildirir
  python daytrade.py --replay --asof 10:30 # piyasa kapalıyken son işlem gününü o saatte taramış gibi dener
"""
import argparse
import json
import math
import os
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import config as cfg
from data import get_universe, download_prices, download_intraday
from indicators import atr as atr_fn, sma
from levels import sr_levels
from charts import make_daytrade_chart
from notifier import notify

ET = ZoneInfo("America/New_York")
OPEN_T, CLOSE_T = dtime(9, 30), dtime(16, 0)

SETUP_LABELS = {
    "orb": "Açılış aralığı (ilk 15 dk) yukarı kırılımı",
    "gap_and_go": "Gap ve devam",
    "vwap_reclaim": "VWAP üstüne geri dönüş",
    "vwap_pullback": "VWAP'tan tepki (geri çekilme)",
    "trend": "Güçlü trend (fiyat > EMA9 > VWAP)",
}


def _parse_hhmm(s):
    h, m = s.split(":")
    return dtime(int(h), int(m))


# ------------------------------------------------------------------ zaman / oturum
def resolve_session(daily, replay, asof_str):
    """(oturum_günü, asof) döner. Canlı: bugün + şimdi. Replay: son işlem günü + verilen saat."""
    now = datetime.now(ET)
    dates = [df.index[-1].date() for df in daily.values() if len(df)]
    if not dates:
        return None, None
    last = max(set(dates), key=dates.count)
    if last == now.date() and OPEN_T <= now.time() < CLOSE_T and not replay:
        return last, pd.Timestamp(now)
    if replay:
        return last, pd.Timestamp(datetime.combine(last, _parse_hhmm(asof_str), tzinfo=ET))
    return None, None


# ------------------------------------------------------------------ 1. aşama: günlük eleme
def stage1(daily, session_date):
    rows = []
    for t, df in daily.items():
        try:
            d = df.loc[:pd.Timestamp(session_date)]
            if len(d) < 60 or d.index[-1].date() != session_date:
                continue
            prev = d.iloc[:-1]
            prev_close = float(prev["Close"].iloc[-1])
            avg_vol = float(prev["Volume"].tail(20).mean())
            dollar = float((prev["Close"] * prev["Volume"]).tail(20).mean())
            a = float(atr_fn(prev).iloc[-1])
            atr_pct = a / prev_close * 100
            if (prev_close < cfg.DT_MIN_PRICE or avg_vol < cfg.DT_MIN_AVG_VOLUME
                    or dollar < cfg.DT_MIN_AVG_DOLLAR_VOLUME or atr_pct < cfg.DT_MIN_ATR_PCT):
                continue
            gap = (float(d["Open"].iloc[-1]) / prev_close - 1) * 100
            s50, s200 = sma(prev["Close"], 50).iloc[-1], sma(prev["Close"], 200).iloc[-1]
            rows.append({
                "ticker": t, "prev_close": prev_close, "gap": gap, "atr": a, "atr_pct": atr_pct,
                "dollar": dollar, "daily_up": bool(prev_close > s50),
                "daily_trend": bool(s50 > s200) if not np.isnan(s200) else False, "prev": prev,
            })
        except Exception as e:
            print(f"[hata] {t}: {e}")
    if not rows:
        return []
    ranks = pd.Series([r["dollar"] for r in rows]).rank(pct=True).values
    for r, rk in zip(rows, ranks):
        r["s1"] = max(r["gap"], 0) * 2 + r["atr_pct"] + 2 * rk   # hareket potansiyeli + likidite
    rows.sort(key=lambda r: -r["s1"])
    return rows[:cfg.DT_SHORTLIST]


# ------------------------------------------------------------------ 2. aşama: gün içi analiz
def analyze(info, idf, session_date, asof):
    dts = np.asarray(idf.index.date)
    today = idf[(dts == session_date) & (idf.index < asof)]
    n = len(today)
    if n < 4:                                   # en az 20 dk veri
        return None

    c, h, l, o, v = (today[k] for k in ("Close", "High", "Low", "Open", "Volume"))
    price = float(c.iloc[-1])
    open_today = float(o.iloc[0])
    tp = (h + l + c) / 3
    cumv = v.cumsum().replace(0, np.nan)
    vwap = (tp * v).cumsum() / cumv
    vw = float(vwap.iloc[-1])
    if np.isnan(vw) or price < vw:              # sadece alım (long) yönü: VWAP altı elenir
        return None

    orh, orl = float(h.iloc[:3].max()), float(l.iloc[:3].min())
    ema9 = c.ewm(span=9, adjust=False).mean()
    day_high = float(h.max())

    # --- gerçek RVOL: bugünkü hacim / önceki günlerde aynı saate kadarki hacim
    prior_days = sorted({d for d in dts if d < session_date})[-4:]
    cum = []
    for pdv in prior_days:
        pv = idf[dts == pdv]["Volume"].cumsum().values
        if len(pv) >= n:
            cum.append(pv[n - 1])
    rvol = float(v.sum() / np.mean(cum)) if cum and np.mean(cum) > 0 else float("nan")

    # --- kurulumlar
    setups = []
    if n > 3 and price >= orh * 0.999 and (c.iloc[-8:] > orh).any():
        setups.append("orb")
    if info["gap"] >= 2 and price > open_today and price >= day_high * 0.995:
        setups.append("gap_and_go")
    if n >= 8 and (c.iloc[-12:-2] < vwap.iloc[-12:-2]).any() and (c.iloc[-2:] > vwap.iloc[-2:]).all():
        setups.append("vwap_reclaim")
    ext_pct = (price / vw - 1) * 100
    if (0 <= ext_pct <= 0.4 and ema9.iloc[-1] > vw and c.iloc[-1] > o.iloc[-1]
            and (l.iloc[-3:] <= vwap.iloc[-3:] * 1.002).any()):
        setups.append("vwap_pullback")
    if n >= 5 and price > ema9.iloc[-1] > vw and ema9.iloc[-1] > ema9.iloc[-4]:
        setups.append("trend")
    if not setups:
        return None

    # --- işlem planı
    swing_low = float(l.iloc[-12:].min())
    stop_base = min(swing_low, vw) * 0.999
    a = info["atr"]
    risk = min(max(price - stop_base, cfg.DT_STOP_MIN_ATR_FRAC * a), cfg.DT_STOP_MAX_ATR_FRAC * a)
    plan = {"entry": price, "stop": price - risk, "risk": risk,
            "t1": price + cfg.DT_TARGET1_R * risk, "t2": price + cfg.DT_TARGET2_R * risk}

    lv = sr_levels(info["prev"])
    res = lv["resistance"]
    room_r = (res - price) / risk if res and res > price else None

    # --- puan (0-100)
    reasons, parts = [], {}
    parts["rvol"] = 0 if np.isnan(rvol) else min(rvol, 4) / 4 * 25
    if not np.isnan(rvol) and rvol >= 1.5:
        reasons.append(f"hacim normalin {rvol:.1f} katı")
    parts["setup"] = min(sum(cfg.DT_SETUP_POINTS[s] for s in setups), 30)
    parts["trend"] = (6 + (3 if price > ema9.iloc[-1] else 0)
                      + (3 if info["daily_up"] else 0) + (3 if info["daily_trend"] else 0))
    if info["daily_up"] and info["daily_trend"]:
        reasons.append("günlük trend yukarı (fiyat 50g üstünde, 50g > 200g)")
    parts["gap"] = min(max(info["gap"], 0), 5) / 5 * 10
    if info["gap"] >= 1:
        reasons.append(f"açılışta %{info['gap']:.1f} yukarı gap")
    parts["vol"] = min(info["atr_pct"], 5) / 5 * 10
    parts["room"] = 10 if room_r is None else min(room_r / 2.5, 1) * 10
    if room_r is not None and room_r < 1.5:
        reasons.append(f"dikkat: yakında direnç var (${res:.2f})")
    penalty = 0
    if ext_pct > 0.8 * info["atr_pct"]:
        penalty = 10
        reasons.append("dikkat: VWAP'tan fazla uzamış, kovalama riski")
    score = max(0.0, min(100.0, sum(parts.values()) - penalty))

    return {"ticker": info["ticker"], "score": score, "setups": setups, "price": price,
            "chg": (price / info["prev_close"] - 1) * 100, "gap": info["gap"], "rvol": rvol,
            "plan": plan, "reasons": reasons, "resistance": res, "today": today, "vwap": vwap,
            "orh": orh, "orl": orl, "atr_pct": info["atr_pct"]}


def evaluate(shortlist, session_date, asof):
    intra = download_intraday([r["ticker"] for r in shortlist])
    out = []
    for info in shortlist:
        idf = intra.get(info["ticker"])
        if idf is None:
            continue
        try:
            res = analyze(info, idf, session_date, asof)
            if res:
                out.append(res)
        except Exception as e:
            print(f"[hata] {info['ticker']}: {e}")
    return sorted(out, key=lambda r: -r["score"])


# ------------------------------------------------------------------ mesaj
def format_pick(best, alts, n_pass):
    p = best["plan"]
    pct = lambda x: (x / p["entry"] - 1) * 100
    lines = [f"⚡ DAY TRADE - Günün seçimi ({n_pass} hisse elemeyi geçti)", "",
             f"{best['ticker']}  ${p['entry']:.2f}  (bugün {best['chg']:+.1f}%)  puan {best['score']:.0f}/100",
             "Kurulum: " + ", ".join(SETUP_LABELS[s] for s in best["setups"]),
             "",
             f"Giriş  ~${p['entry']:.2f}",
             f"Stop   ${p['stop']:.2f} ({pct(p['stop']):+.1f}%)",
             f"Hedef1 ${p['t1']:.2f} ({pct(p['t1']):+.1f}%)",
             f"Hedef2 ${p['t2']:.2f} ({pct(p['t2']):+.1f}%)"]
    if cfg.DT_ACCOUNT_SIZE > 0:
        qty = math.floor(cfg.DT_ACCOUNT_SIZE * cfg.DT_RISK_PCT / 100 / p["risk"])
        lines.append(f"Adet   {qty} (hesabın %{cfg.DT_RISK_PCT:g}'i riskte)")
    if best["reasons"]:
        lines += ["", "Neden:"] + [f"• {r}" for r in best["reasons"]]
    if alts:
        lines += ["", "Yedekler: " + ", ".join(f"{a['ticker']} ({a['score']:.0f})" for a in alts)]
    lines += ["", "⚠ Day trade risklidir. Stop'u mutlaka kullan, gün bitmeden pozisyonu kapat.",
              "Yatırım tavsiyesi değildir; seviyeler otomatik hesaplanan örneklerdir."]
    return "\n".join(lines)


# ------------------------------------------------------------------ durum (aynı günde tekrar atma)
def load_state(session_date):
    try:
        with open(cfg.DT_STATE_FILE) as f:
            st = json.load(f)
        if st.get("date") == str(session_date):
            return st
    except Exception:
        pass
    return {"date": str(session_date), "sent": []}


def save_state(st):
    with open(cfg.DT_STATE_FILE, "w") as f:
        json.dump(st, f)


# ------------------------------------------------------------------ akış
def report(results, n_pass, args, state, session_date):
    """En iyi adayı yazdırır / gönderir. Gönderildiyse True döner."""
    if not results:
        print("Bu an için uygun kurulum bulunamadı.")
        return False
    ok = [r for r in results if r["score"] >= cfg.DT_MIN_SCORE]
    if not ok:
        top = results[0]
        print(f"Net aday yok: en iyi {top['ticker']} sadece {top['score']:.0f}/100 "
              f"(eşik {cfg.DT_MIN_SCORE}). Bugün işlem yapmamak da bir karardır.")
        return False
    fresh = [r for r in ok if r["ticker"] not in state["sent"] or args.force]
    if not fresh:
        print(f"Güçlü adaylar ({', '.join(r['ticker'] for r in ok[:3])}) bugün zaten gönderildi.")
        return False
    best = fresh[0]
    alts = [r for r in ok if r is not best][:cfg.DT_ALTERNATES]
    msg = format_pick(best, alts, n_pass)
    print(msg)
    images = []
    if not args.no_charts:
        title = f"{best['ticker']}  ${best['price']:.2f}  |  " + ", ".join(SETUP_LABELS[s] for s in best["setups"])
        path = make_daytrade_chart(best["ticker"], best["today"], best["vwap"], best["orh"], best["orl"],
                                   best["plan"], title)
        images.append((path, f"{best['ticker']} day trade planı"))
        print(f"grafik kaydedildi: {path}")
    if args.dry_run:
        return False
    if notify(msg, title="Day Trade", images=images):
        if not args.replay:
            state["sent"].append(best["ticker"])
            save_state(state)
        return True
    print("Bildirim kanalı ayarlı değil; sadece ekrana yazıldı.")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="bildirim gönderme")
    ap.add_argument("--watch", action="store_true", help="piyasa saatlerinde her N dakikada bir tara")
    ap.add_argument("--replay", action="store_true", help="piyasa kapalıyken son işlem gününü dene")
    ap.add_argument("--asof", default="10:30", help="replay için saat (New York), örn. 10:30")
    ap.add_argument("--force", action="store_true", help="saat penceresi ve 'zaten gönderildi' kontrolünü atla")
    ap.add_argument("--limit", type=int, default=0, help="sadece ilk N hisseyi tara (test)")
    ap.add_argument("--no-charts", action="store_true")
    args = ap.parse_args()

    now = datetime.now(ET)
    if not (args.replay or args.force or args.watch):
        lo, hi = _parse_hhmm(cfg.DT_WINDOW_ET[0]), _parse_hhmm(cfg.DT_WINDOW_ET[1])
        if now.weekday() >= 5 or not (lo <= now.time() <= hi):
            print(f"New York saati şu an {now:%a %H:%M}. Çalışma aralığı hafta içi "
                  f"{cfg.DT_WINDOW_ET[0]}-{cfg.DT_WINDOW_ET[1]}. (Zorla çalıştırmak için --force)")
            return

    if args.watch and not args.replay:
        start_t = _parse_hhmm(cfg.DT_WINDOW_ET[0])
        if now.weekday() >= 5:
            print("Hafta sonu, piyasa kapalı. Pazartesi tekrar çalıştır.")
            return
        while datetime.now(ET).time() < start_t:
            print(f"{datetime.now(ET):%H:%M} (NY): piyasa açılışı bekleniyor, {cfg.DT_WINDOW_ET[0]}'de başlayacak...")
            time.sleep(60)

    cached = None
    if not args.replay:
        cached = load_state(now.date()).get("shortlist")
    if cached:
        tickers = cached
        print(f"Bugünün kısa listesi kullanılıyor ({len(tickers)} hisse).")
    else:
        tickers = get_universe()
        if args.limit:
            tickers = tickers[:args.limit]
    print(f"{len(tickers)} hisse için günlük veri indiriliyor...")
    daily = download_prices(tickers, period="1y")
    session_date, asof = resolve_session(daily, args.replay, args.asof)
    if session_date is None:
        print("Piyasa şu an kapalı ya da bugün için veri yok. Denemek için: python daytrade.py --replay --asof 10:30")
        return
    print(f"Oturum günü: {session_date} | saat (NY): {asof:%H:%M}" + ("  [REPLAY]" if args.replay else ""))

    shortlist = stage1(daily, session_date)
    print(f"Günlük elemeyi geçen ve detaylı incelenen: {len(shortlist)} hisse")
    if not shortlist:
        print("Filtreleri geçen hisse yok.")
        return
    state = load_state(session_date)
    if not args.replay and not cached:
        state["shortlist"] = [r["ticker"] for r in shortlist]
        save_state(state)

    if not args.watch:
        report(evaluate(shortlist, session_date, asof), len(shortlist), args, state, session_date)
        return

    end_t = _parse_hhmm(cfg.DT_WATCH_END_ET)
    start_t = _parse_hhmm(cfg.DT_WINDOW_ET[0])
    print(f"İzleme modu: her {cfg.DT_WATCH_INTERVAL_MIN} dk. Durdurmak için Ctrl+C. Bitiş: {cfg.DT_WATCH_END_ET} (NY)")
    while True:
        now = datetime.now(ET)
        if now.time() >= end_t:
            print("İzleme bitti (gün sonuna yaklaşıldı).")
            return
        if now.time() >= start_t:
            print(f"\n--- {now:%H:%M} taranıyor ---")
            res = evaluate(shortlist, session_date, pd.Timestamp(now))
            report(res, len(shortlist), args, state, session_date)
        else:
            print(f"{now:%H:%M}: açılış aralığı oluşuyor, {cfg.DT_WINDOW_ET[0]}'de başlayacak...")
        time.sleep(cfg.DT_WATCH_INTERVAL_MIN * 60)


if __name__ == "__main__":
    main()
