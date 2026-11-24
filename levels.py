"""Destek / direnç seviyeleri: onaylanmış tepe ve dipleri kümeleyerek bulur."""
import numpy as np
import config as cfg


def _pivot_prices(d, k):
    hs = d["High"].rolling(2 * k + 1, center=True).max()
    ls = d["Low"].rolling(2 * k + 1, center=True).min()
    highs = d["High"][d["High"] == hs].values
    lows = d["Low"][d["Low"] == ls].values
    return np.concatenate([highs, lows])


def sr_levels(df, k=None, lookback=None, tol=None, min_touches=None):
    k = k or cfg.PIVOT_K
    lookback = lookback or cfg.SR_LOOKBACK
    tol = tol or cfg.SR_TOLERANCE
    min_touches = min_touches or cfg.SR_MIN_TOUCHES
    d = df.iloc[-lookback:]
    pts = np.sort(_pivot_prices(d, k))
    clusters = []
    for p in pts:
        if clusters and p <= np.mean(clusters[-1]) * (1 + tol):
            clusters[-1].append(p)
        else:
            clusters.append([p])
    levels = [(float(np.mean(c)), len(c)) for c in clusters if len(c) >= min_touches]
    price = float(df["Close"].iloc[-1])
    below = [lv for lv in levels if lv[0] < price * 0.999]
    above = [lv for lv in levels if lv[0] > price * 1.001]
    sup = max(below, key=lambda x: x[0]) if below else None
    res = min(above, key=lambda x: x[0]) if above else None
    return {
        "levels": levels,
        "support": sup[0] if sup else None,
        "support_touches": sup[1] if sup else 0,
        "resistance": res[0] if res else None,
        "resistance_touches": res[1] if res else 0,
        "price": price,
    }
