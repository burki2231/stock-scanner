"""Aday hisse için mum grafiği: fiyat + 50/200g ort. + destek/direnç + hacim + RSI."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import config as cfg
from indicators import sma, rsi

BG, FG, GRID = "#0f1419", "#d7dde4", "#222b36"
UP, DOWN = "#26a69a", "#ef5350"


def make_chart(ticker, df, levels=None, signals=None, out_dir=None):
    out_dir = out_dir or cfg.CHART_DIR
    os.makedirs(out_dir, exist_ok=True)
    full = df.copy()
    full["sma50"], full["sma200"], full["rsi"] = sma(full["Close"], 50), sma(full["Close"], 200), rsi(full["Close"])
    d = full.iloc[-cfg.CHART_BARS:]
    x = np.arange(len(d))
    o, h, l, c, v = (d[k].values for k in ("Open", "High", "Low", "Close", "Volume"))
    col = np.where(c >= o, UP, DOWN)

    fig, (ax, axv, axr) = plt.subplots(3, 1, figsize=(10, 8), sharex=True, facecolor=BG,
                                       gridspec_kw={"height_ratios": [5, 1.2, 1.5], "hspace": 0.05})
    for a in (ax, axv, axr):
        a.set_facecolor(BG)
        a.tick_params(colors=FG, labelsize=8)
        a.grid(color=GRID, linewidth=0.5)
        for sp in a.spines.values():
            sp.set_color(GRID)

    ax.vlines(x, l, h, color=col, linewidth=0.8)
    ax.bar(x, np.maximum(np.abs(c - o), (h - l) * 0.01), bottom=np.minimum(o, c), color=col, width=0.7)
    ax.plot(x, d["sma50"].values, color="#ffb74d", linewidth=1.2, label="SMA50")
    ax.plot(x, d["sma200"].values, color="#64b5f6", linewidth=1.2, label="SMA200")

    price = float(c[-1])
    if levels:
        lo, hi = float(l.min()) * 0.97, float(h.max()) * 1.03
        for lvl, touches in levels["levels"]:
            if lo <= lvl <= hi:
                is_res = lvl > price
                ax.axhline(lvl, color="#ef9a9a" if is_res else "#a5d6a7", linestyle="--", linewidth=0.9, alpha=0.8)
                ax.text(len(d) - 0.5, lvl, f" ${lvl:.2f} ({touches}x)", color=FG, fontsize=7, va="center")
    ax.annotate("", xy=(x[-1], l[-1]), xytext=(x[-1], l[-1] - (h.max() - l.min()) * 0.08),
                arrowprops=dict(arrowstyle="->", color="#fff176", linewidth=1.6))
    title = f"{ticker}  ${price:.2f}"
    if signals:
        title += "   |   " + ", ".join(signals)
    ax.set_title(title, color=FG, fontsize=11, loc="left")
    ax.legend(loc="upper left", fontsize=8, facecolor=BG, edgecolor=GRID, labelcolor=FG)
    ax.set_xlim(-1, len(d) + 8)

    axv.bar(x, v, color=col, width=0.7)
    axv.set_ylabel("Hacim", color=FG, fontsize=8)
    axr.plot(x, d["rsi"].values, color="#ce93d8", linewidth=1.2)
    axr.axhline(70, color=DOWN, linestyle=":", linewidth=0.8)
    axr.axhline(30, color=UP, linestyle=":", linewidth=0.8)
    axr.set_ylim(0, 100)
    axr.set_ylabel("RSI", color=FG, fontsize=8)

    step = max(len(d) // 6, 1)
    axr.set_xticks(x[::step])
    axr.set_xticklabels([d.index[i].strftime("%d %b") for i in range(0, len(d), step)], color=FG, fontsize=8)

    path = os.path.join(out_dir, f"{ticker}.png")
    fig.savefig(path, dpi=110, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return path


def make_daytrade_chart(ticker, today, vwap, orh, orl, plan, title, out_dir=None):
    """Bugünün 5 dk mumları + VWAP + açılış aralığı + giriş/stop/hedef çizgileri."""
    out_dir = out_dir or cfg.CHART_DIR
    os.makedirs(out_dir, exist_ok=True)
    x = np.arange(len(today))
    o, h, l, c, v = (today[k].values for k in ("Open", "High", "Low", "Close", "Volume"))
    col = np.where(c >= o, UP, DOWN)

    fig, (ax, axv) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, facecolor=BG,
                                  gridspec_kw={"height_ratios": [4, 1], "hspace": 0.05})
    for a in (ax, axv):
        a.set_facecolor(BG)
        a.tick_params(colors=FG, labelsize=8)
        a.grid(color=GRID, linewidth=0.5)
        for sp in a.spines.values():
            sp.set_color(GRID)

    ax.vlines(x, l, h, color=col, linewidth=0.8)
    ax.bar(x, np.maximum(np.abs(c - o), (h - l) * 0.02), bottom=np.minimum(o, c), color=col, width=0.7)
    ax.plot(x, np.asarray(vwap), color="#ffb74d", linewidth=1.4, label="VWAP")
    ax.axhline(orh, color="#90a4ae", linestyle=":", linewidth=0.9)
    ax.axhline(orl, color="#90a4ae", linestyle=":", linewidth=0.9)
    ax.text(0, orh, " açılış aralığı üstü", color="#90a4ae", fontsize=7, va="bottom")

    lines = [("Giriş", plan["entry"], "#ffffff"), ("Stop", plan["stop"], DOWN),
             ("Hedef 1", plan["t1"], UP), ("Hedef 2", plan["t2"], "#66bb6a")]
    for name, val, colr in lines:
        ax.axhline(val, color=colr, linestyle="--", linewidth=1.0, alpha=0.9)
        ax.text(len(today) - 0.5, val, f" {name} ${val:.2f}", color=colr, fontsize=8, va="center",
                bbox=dict(facecolor=BG, edgecolor="none", pad=1.5))
    ax.set_xlim(-1, len(today) * 1.45 + 4)
    ax.set_title(title, color=FG, fontsize=11, loc="left")
    ax.legend(loc="upper left", fontsize=8, facecolor=BG, edgecolor=GRID, labelcolor=FG)

    axv.bar(x, v, color=col, width=0.7)
    axv.set_ylabel("Hacim", color=FG, fontsize=8)
    step = max(len(today) // 6, 1)
    axv.set_xticks(x[::step])
    axv.set_xticklabels([today.index[i].strftime("%H:%M") for i in range(0, len(today), step)],
                        color=FG, fontsize=8)
    path = os.path.join(out_dir, f"{ticker}_daytrade.png")
    fig.savefig(path, dpi=110, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return path
