"""Mum formasyonları, destek dönüşü ve klasik grafik formasyonları.
Hepsi 'geleceğe bakmadan' çalışır: bir tepe/dip ancak k mum sonra onaylanmış sayılır.
last_only=True ise sadece son mum hesaplanır (canlı tarama için hızlı)."""
import numpy as np
import pandas as pd
import config as cfg
from indicators import sma

NAMES = ["hammer", "bullish_engulfing", "morning_star", "support_bounce",
         "double_bottom", "ascending_triangle", "bull_flag"]


def _candles(df):
    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    lower = np.minimum(o, c) - l
    upper = h - np.maximum(o, c)
    sma20 = sma(c, 20)
    down1 = c.shift(1) < sma20.shift(1)
    down2 = c.shift(2) < sma20.shift(2)

    hammer = down1 & (body > 0) & (lower >= 0.6 * rng) & (upper <= 0.1 * rng)
    engulf = (down1 & (c.shift(1) < o.shift(1)) & (c > o) & (o <= c.shift(1))
              & (c >= o.shift(1)) & (body > body.shift(1)))
    morning = (down2 & (c.shift(2) < o.shift(2)) & (body.shift(2) / rng.shift(2) >= 0.6)
               & (body.shift(1) <= 0.3 * body.shift(2))
               & (np.maximum(o, c).shift(1) <= c.shift(2))
               & (c > o) & (c > (o.shift(2) + c.shift(2)) / 2))
    return hammer.fillna(False), engulf.fillna(False), morning.fillna(False)


def _bull_flag(df):
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    vol_avg = v.rolling(20).mean().shift(1)
    out = pd.Series(False, index=df.index)
    for f in (6, 10):
        pole_start = c.shift(f + 10)
        pole_gain = c.shift(f) / pole_start - 1
        flag_high = h.shift(1).rolling(f).max()
        flag_low = l.shift(1).rolling(f).min()
        retrace = (flag_high - flag_low) / (flag_high - pole_start)
        cond = ((pole_gain >= 0.15) & ((flag_high - flag_low) / flag_high <= 0.10)
                & (retrace <= 0.4) & (c > flag_high) & (v >= 1.2 * vol_avg))
        out |= cond.fillna(False)
    return out


def pattern_signals(df, last_only=False):
    n = len(df)
    k = cfg.PIVOT_K
    o, h, l, c = (df[x].values for x in ("Open", "High", "Low", "Close"))

    hammer, engulf, morning = _candles(df)
    out = {nm: np.zeros(n, dtype=bool) for nm in NAMES}
    if last_only:
        for nm, s in (("hammer", hammer), ("bullish_engulfing", engulf), ("morning_star", morning)):
            out[nm][-1] = bool(s.iloc[-1])
        flag = _bull_flag(df.iloc[-60:]).values
        out["bull_flag"][-1] = bool(flag[-1])
    else:
        out["hammer"], out["bullish_engulfing"], out["morning_star"] = hammer.values, engulf.values, morning.values
        out["bull_flag"] = _bull_flag(df).values

    # onaylanabilir tepe/dipler (merkezli pencere, onay k mum sonra)
    hs = df["High"].rolling(2 * k + 1, center=True).max().values
    ls = df["Low"].rolling(2 * k + 1, center=True).min().values
    ph_idx = np.flatnonzero(h == hs)
    pl_idx = np.flatnonzero(l == ls)

    start = n - 1 if last_only else 60
    for t in range(max(start, 2 * k + 2), n):
        lim = t - k
        hi_i = ph_idx[:np.searchsorted(ph_idx, lim, side="right")]
        lo_i = pl_idx[:np.searchsorted(pl_idx, lim, side="right")]

        # ÇİFT DİP: iki benzer dip + boyun çizgisi kırılımı
        if len(lo_i) >= 2:
            i1, i2 = lo_i[-2], lo_i[-1]
            p1, p2 = l[i1], l[i2]
            if 10 <= i2 - i1 <= 70 and abs(p2 - p1) / p1 <= 0.03 and t - i2 <= 40:
                neck = h[i1:i2 + 1].max()
                if neck >= max(p1, p2) * 1.06 and c[t] > neck and c[t - 1] <= neck:
                    out["double_bottom"][t] = True

        # YÜKSELEN ÜÇGEN: yatay direnç + yükselen dipler + kırılım
        hs_w = hi_i[hi_i >= t - 60][-3:]
        ls_w = lo_i[lo_i >= t - 60][-3:]
        if len(hs_w) >= 2 and len(ls_w) >= 2:
            hp = h[hs_w]
            res = hp.max()
            lp = l[ls_w]
            flat = (res - hp.min()) / res <= 0.015
            rising = bool(np.all(np.diff(lp) > 0)) and lp[-1] >= lp[0] * 1.02
            if flat and rising and c[t] > res and c[t - 1] <= res:
                out["ascending_triangle"][t] = True

        # DESTEK DÖNÜŞÜ: en az 2 kez test edilmiş desteğe dokunup yeşil mumla dönüş
        ls2 = lo_i[lo_i >= t - cfg.SR_LOOKBACK]
        if len(ls2) >= 2 and c[t] > o[t]:
            pr = l[ls2]
            touches = (np.abs(pr[:, None] - pr[None, :]) <= cfg.SR_TOLERANCE * pr[:, None]).sum(1)
            for p in pr[touches >= cfg.SR_MIN_TOUCHES]:
                if p * 0.98 <= l[t] <= p * 1.01 and c[t] > p:
                    out["support_bounce"][t] = True
                    break

    return pd.DataFrame(out, index=df.index)
