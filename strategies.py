"""Sinyaller vektörel hesaplanır: aynı kod hem canlı tarama hem backtest için kullanılır."""
import pandas as pd
import config as cfg
from indicators import sma, rsi, macd, atr
from patterns import pattern_signals


def compute_signals(df: pd.DataFrame, last_only: bool = False):
    """df: Open High Low Close Volume. Dönüş: (bool sinyal DataFrame, gösterge DataFrame)."""
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]

    sma50, sma200 = sma(c, 50), sma(c, 200)
    r = rsi(c, cfg.RSI_PERIOD)
    macd_line, macd_sig, _ = macd(c)
    vol_avg20 = sma(v, 20)
    high_n = h.rolling(cfg.BREAKOUT_LOOKBACK).max()

    sig = pd.DataFrame(index=df.index)
    sig["oversold_dip"] = (r < cfg.RSI_OVERSOLD) & (c > sma200)
    sig["rsi_recovery"] = (r.shift(1) < cfg.RSI_OVERSOLD) & (r >= cfg.RSI_OVERSOLD)
    sig["golden_cross"] = (sma50 > sma200) & (sma50.shift(1) <= sma200.shift(1))
    sig["macd_cross_up"] = (
        (macd_line > macd_sig) & (macd_line.shift(1) <= macd_sig.shift(1)) & (macd_line < 0)
    )
    sig["breakout"] = (c > high_n.shift(1)) & (v >= cfg.BREAKOUT_VOLUME_MULT * vol_avg20.shift(1))
    sig["pullback_to_sma50"] = (
        (c > sma200) & (sma50 > sma200) & (l <= sma50 * 1.01) & (c >= sma50) & (r < cfg.PULLBACK_RSI_MAX)
    )
    sig = sig.fillna(False).astype(bool)
    sig = pd.concat([sig, pattern_signals(df, last_only=last_only)], axis=1)

    info = pd.DataFrame({
        "close": c,
        "rsi": r,
        "sma50": sma50,
        "sma200": sma200,
        "atr": atr(df),
        "dollar_vol": sma(c * v, 20),
        "chg_1d": c.pct_change() * 100,
        "from_52w_high": (c / h.rolling(252, min_periods=60).max() - 1) * 100,
    })
    return sig, info


def score_series(sig: pd.DataFrame) -> pd.Series:
    total = pd.Series(0.0, index=sig.index)
    for name, w in cfg.SIGNAL_WEIGHTS.items():
        if name in sig:
            total += sig[name].astype(float) * w
    return total


def passes_filters(df: pd.DataFrame, info_last) -> bool:
    if len(df) < cfg.MIN_HISTORY_DAYS:
        return False
    if info_last["close"] < cfg.MIN_PRICE:
        return False
    if not info_last["dollar_vol"] >= cfg.MIN_AVG_DOLLAR_VOLUME:
        return False
    return True
