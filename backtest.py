"""Sinyaller geçmişte işe yaramış mı? python backtest.py [--limit 100]
Her sinyal için sonraki 5/10/20 işlem günü getirisini, tüm günlerin ortalamasıyla kıyaslar."""
import argparse
import pandas as pd
import config as cfg
from data import get_universe, download_prices
from strategies import compute_signals, score_series

HORIZONS = (5, 10, 20)
GAP = 10  # aynı hissede sinyal kümelerini tek say (üst üste binmesin)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    tickers = get_universe()[:args.limit]
    prices = download_prices(tickers, period=cfg.BACKTEST_PERIOD)
    rows, base = [], {h: [] for h in HORIZONS}

    for t, df in prices.items():
        if len(df) < 300:
            continue
        sig, info = compute_signals(df)
        sig["combined"] = score_series(sig) >= cfg.MIN_SCORE
        fwd = {h: df["Close"].shift(-h) / df["Close"] - 1 for h in HORIZONS}
        for h in HORIZONS:
            base[h].append(fwd[h].dropna())
        ok = (df["Close"] >= cfg.MIN_PRICE) & (info["dollar_vol"] >= cfg.MIN_AVG_DOLLAR_VOLUME)
        for name in sig.columns:
            s = sig[name] & ok
            last_i = -10**9
            for i, flag in enumerate(s.values):
                if flag and i - last_i > GAP:
                    rows.append({"signal": name, "ticker": t, "date": df.index[i],
                                 **{f"r{h}": fwd[h].iloc[i] for h in HORIZONS}})
                if flag:
                    last_i = i

    if not rows:
        print("Hiç sinyal bulunamadı.")
        return
    res = pd.DataFrame(rows)
    res.to_csv("backtest_results.csv", index=False)

    print("\nTüm günlerin ortalama getirisi (kıyas):")
    for h in HORIZONS:
        allr = pd.concat(base[h])
        print(f"  {h} gün: ort {allr.mean()*100:.2f}%  kazanma oranı {(allr>0).mean()*100:.0f}%")

    print("\nSinyal bazında sonuçlar:")
    for name, g in res.groupby("signal"):
        print(f"\n{name}  (n={len(g)})")
        for h in HORIZONS:
            r = g[f"r{h}"].dropna()
            if len(r):
                print(f"  {h:>2} gün: ort {r.mean()*100:6.2f}%  medyan {r.median()*100:6.2f}%  "
                      f"kazanma {(r>0).mean()*100:3.0f}%  en kötü {r.min()*100:6.1f}%")
    print("\nNot: geçmiş performans gelecek için garanti değildir. Sonuçları kıyas satırıyla karşılaştır;")
    print("sinyal ortalamayı belirgin şekilde geçmiyorsa o kuralın ağırlığını düşür veya kapat.")


if __name__ == "__main__":
    main()
