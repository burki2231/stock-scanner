"""Günlük tarayıcı: python scanner.py [--dry-run] [--test-notify] [--min-score 3] [--limit 50] [--no-charts]"""
import argparse
import json
import os
from datetime import datetime, timedelta

import config as cfg
from data import get_universe, download_prices
from strategies import compute_signals, score_series, passes_filters
from levels import sr_levels
from charts import make_chart
from notifier import notify

LABELS = {
    "oversold_dip": "Trendde aşırı satım (RSI<30, 200g üstü)",
    "rsi_recovery": "RSI 30'u yukarı kesti",
    "pullback_to_sma50": "50g ortalamaya geri çekilme",
    "macd_cross_up": "MACD yukarı kesişim",
    "golden_cross": "Golden cross (50g>200g)",
    "breakout": "Hacimli zirve kırılımı",
    "hammer": "Çekiç mumu",
    "bullish_engulfing": "Yükseliş yutan mum",
    "morning_star": "Sabah yıldızı",
    "support_bounce": "Destekten dönüş",
    "double_bottom": "Çift dip kırılımı",
    "ascending_triangle": "Yükselen üçgen kırılımı",
    "bull_flag": "Boğa bayrağı kırılımı",
}


def load_state():
    if os.path.exists(cfg.STATE_FILE):
        try:
            with open(cfg.STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state):
    cutoff = (datetime.utcnow() - timedelta(days=60)).strftime("%Y-%m-%d")
    state = {k: v for k, v in state.items() if v.get("date", "") >= cutoff}
    with open(cfg.STATE_FILE, "w") as f:
        json.dump(state, f, indent=1)


def calc_stop_target(price, atr, lv):
    """Stop: ATR bazlı, yakın destek varsa onun hemen altı (en az 1 ATR aşağıda).
    Hedef: riskin TARGET_RR katı; yakında direnç varsa direnç seviyesi."""
    stop = price - cfg.STOP_ATR_MULT * atr
    sup = lv.get("support")
    if sup and sup * 0.99 > stop:
        stop = min(sup * 0.99, price - cfg.STOP_MIN_ATR * atr)
    risk = price - stop
    target = price + cfg.TARGET_RR * risk
    res = lv.get("resistance")
    if cfg.USE_RESISTANCE_FOR_TARGET and res and price + risk <= res < target:
        target = res
    return stop, target


def scan(tickers, min_score, prices=None):
    prices = prices if prices is not None else download_prices(tickers)
    print(f"{len(prices)} hisse için veri alındı, analiz ediliyor...")
    hits = []
    for t, df in prices.items():
        try:
            sig, info = compute_signals(df, last_only=True)
            last = info.iloc[-1]
            if not passes_filters(df, last):
                continue
            active = [n for n in sig.columns if bool(sig[n].iloc[-1])]
            score = float(score_series(sig).iloc[-1])
            if not active or score < min_score:
                continue
            price, atr = float(last["close"]), float(last["atr"])
            lv = sr_levels(df)
            stop, target = calc_stop_target(price, atr, lv)
            hits.append({
                "ticker": t, "score": score, "signals": active, "price": price,
                "rsi": float(last["rsi"]), "chg": float(last["chg_1d"]),
                "from_high": float(last["from_52w_high"]),
                "stop": stop, "target": target,
                "support": lv["support"], "resistance": lv["resistance"], "levels": lv,
                "date": str(df.index[-1].date()), "df": df,
            })
        except Exception as e:
            print(f"[hata] {t}: {e}")
    return sorted(hits, key=lambda x: -x["score"])


def format_message(hits, total):
    lines = [f"📈 Borsa Tarayıcı - {len(hits)} aday ({total} hisse tarandı)", ""]
    for h in hits[:cfg.MAX_ALERTS_PER_RUN]:
        p, stop, tgt = h["price"], h["stop"], h["target"]
        rr = (tgt - p) / (p - stop) if p > stop else 0
        lines.append(f"{h['ticker']}  ${p:.2f}  ({h['chg']:+.1f}%)  puan {h['score']:.1f}")
        lines.append(f"  Stop ${stop:.2f} ({(stop/p-1)*100:+.1f}%) | Hedef ${tgt:.2f} ({(tgt/p-1)*100:+.1f}%) | R/Ö 1:{rr:.1f}")
        for s in h["signals"]:
            lines.append(f"  • {LABELS.get(s, s)}")
        lines.append("")
    lines.append("Bu bir yatırım tavsiyesi değildir; stop ve hedef örnek seviyelerdir, sadece 'bakmaya değer' listesidir.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="bildirim gönderme, ekrana yaz + grafikleri kaydet")
    ap.add_argument("--test-notify", action="store_true", help="sadece test bildirimi gönder")
    ap.add_argument("--min-score", type=float, default=cfg.MIN_SCORE)
    ap.add_argument("--limit", type=int, default=0, help="sadece ilk N hisseyi tara (test için)")
    ap.add_argument("--no-charts", action="store_true", help="grafik üretme")
    args = ap.parse_args()

    if args.test_notify:
        ok = notify("✅ Test bildirimi: Borsa Tarayıcı çalışıyor.")
        print("gönderildi" if ok else "Hiçbir kanal ayarlı değil (README'ye bak).")
        return

    tickers = get_universe()
    if args.limit:
        tickers = tickers[:args.limit]
    print(f"{len(tickers)} hisse taranacak")

    hits = scan(tickers, args.min_score)
    state = load_state()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    fresh = []
    for h in hits:
        prev = state.get(h["ticker"])
        sigset = ",".join(sorted(h["signals"]))
        if prev and prev["signals"] == sigset:
            age = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(prev["date"], "%Y-%m-%d")).days
            if age < cfg.COOLDOWN_DAYS:
                continue
        fresh.append(h)

    if not fresh:
        print("Yeni fırsat yok.")
        return

    fresh = fresh[:cfg.MAX_ALERTS_PER_RUN]
    msg = format_message(fresh, len(tickers))
    print(msg)

    images = []
    if not args.no_charts:
        for h in fresh[:cfg.MAX_CHARTS_PER_RUN]:
            try:
                path = make_chart(h["ticker"], h["df"], h["levels"], [LABELS.get(s, s) for s in h["signals"]])
                images.append((path, f"{h['ticker']} ${h['price']:.2f} | " + ", ".join(LABELS.get(s, s) for s in h["signals"])))
            except Exception as e:
                print(f"[grafik hatası] {h['ticker']}: {e}")
        print(f"{len(images)} grafik '{cfg.CHART_DIR}/' klasörüne kaydedildi")

    if args.dry_run:
        return
    if notify(msg, images=images):
        for h in fresh:
            state[h["ticker"]] = {"signals": ",".join(sorted(h["signals"])), "date": today}
        save_state(state)
    else:
        print("Bildirim kanalı ayarlı değil; sadece ekrana yazıldı.")


if __name__ == "__main__":
    main()
