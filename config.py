"""Tüm ayarlar burada. Kodu değiştirmeden stratejiyi buradan ayarlayabilirsin."""
import os

# --- Evren (taranacak hisseler) ---
# "sp500", "nasdaq100", "custom" (tickers.txt dosyasındaki hisseler)
UNIVERSES = ["sp500", "nasdaq100", "custom"]

# --- Veri ---
HISTORY_PERIOD = "2y"          # tarama için çekilen geçmiş
BACKTEST_PERIOD = "10y"        # backtest için çekilen geçmiş
BATCH_SIZE = 100               # yfinance'a tek seferde gönderilen hisse sayısı

# --- Likidite / kalite filtreleri ---
MIN_PRICE = 5.0                        # penny stock'ları ele
MIN_AVG_DOLLAR_VOLUME = 20_000_000     # 20 günlük ort. işlem hacmi (USD)
MIN_HISTORY_DAYS = 220                 # 200 günlük ortalama için yeterli veri

# --- Gösterge parametreleri ---
RSI_PERIOD = 14
RSI_OVERSOLD = 30
BREAKOUT_LOOKBACK = 55         # 55 günlük zirve kırılımı
BREAKOUT_VOLUME_MULT = 1.5     # kırılımda hacim, 20g ortalamanın en az 1.5 katı
PULLBACK_RSI_MAX = 45

# --- Sinyal ağırlıkları (puan sistemi) ---
# Bir hisse bildirim için toplam puanın MIN_SCORE'u geçmesi gerekir.
SIGNAL_WEIGHTS = {
    "oversold_dip":       2.0,  # RSI<30 ama fiyat 200g ortalamanın üstünde (yükseliş trendinde düşüş)
    "rsi_recovery":       2.0,  # RSI 30'u aşağıdan yukarı kesti (dönüş başlangıcı)
    "pullback_to_sma50":  1.5,  # yükseliş trendinde 50g ortalamaya geri çekilme + tepki
    "macd_cross_up":      1.0,  # MACD sinyali yukarı kesti (sıfırın altında, erken dönüş)
    "golden_cross":       1.5,  # 50g ort. 200g ort.'yı yukarı kesti
    "breakout":           2.0,  # hacimli 55 günlük zirve kırılımı
    # --- mum formasyonları (tek başına bildirim çıkarmaz, diğer sinyalleri güçlendirir) ---
    "hammer":             1.0,  # çekiç mumu (düşüş sonrası uzun alt fitil)
    "bullish_engulfing":  1.5,  # yükseliş yutan mum
    "morning_star":       1.5,  # sabah yıldızı (3 mumlu dönüş)
    # --- destek / direnç ---
    "support_bounce":     1.5,  # tekrar test edilmiş desteğe dokunup yeşil mumla dönüş
    # --- klasik grafik formasyonları ---
    "double_bottom":      2.0,  # çift dip + boyun çizgisi kırılımı
    "ascending_triangle": 1.5,  # yükselen üçgen, yatay direnç kırılımı
    "bull_flag":          1.5,  # boğa bayrağı kırılımı
}
MIN_SCORE = 2.0                # en az bu puan olursa bildirim gelir
MAX_ALERTS_PER_RUN = 15        # tek bildirimde en fazla kaç hisse

# --- Formasyon / destek-direnç parametreleri ---
PIVOT_K = 5                    # bir tepe/dip için solundaki ve sağındaki mum sayısı
SR_LOOKBACK = 250              # destek/direnç için bakılan gün sayısı
SR_TOLERANCE = 0.015           # seviyeleri kümelerken yakınlık toleransı (%1.5)
SR_MIN_TOUCHES = 2             # bir seviyenin geçerli sayılması için min. dokunuş

# --- Grafik ---
CHART_BARS = 130               # grafikte gösterilen işlem günü
MAX_CHARTS_PER_RUN = 5         # bildirimle en fazla kaç grafik gönderilsin
CHART_DIR = "charts"

# --- Stop / hedef hesabı ---
STOP_ATR_MULT = 2.0            # stop = fiyat - 2 x ATR (günlük ortalama hareketin 2 katı)
STOP_MIN_ATR = 1.0             # destek çok yakınsa bile stop en az 1 ATR aşağıda olsun
TARGET_RR = 2.0                # hedef = riskin 2 katı kazanç (Risk/Ödül 1:2)
USE_RESISTANCE_FOR_TARGET = True   # yakında direnç varsa hedefi direnç seviyesine çek

# --- Tekrar bildirim engeli ---
COOLDOWN_DAYS = 5              # aynı hisse için aynı sinyal setini bu kadar gün tekrar gönderme
STATE_FILE = "state.json"

# --- Bildirim kanalları (ortam değişkenleri ile) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")           # ntfy.sh/<topic>
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")

# =====================  DAY TRADE MODU  =====================
# --- 1. eleme (günlük veriye göre) ---
DT_MIN_PRICE = 5.0
DT_MIN_AVG_VOLUME = 2_000_000          # günlük ort. işlem adedi
DT_MIN_AVG_DOLLAR_VOLUME = 150_000_000 # günlük ort. işlem hacmi (USD)
DT_MIN_ATR_PCT = 1.8                   # günlük ATR / fiyat (%): hareket yoksa day trade olmaz
DT_SHORTLIST = 40                      # gün içi veriyle detaylı bakılacak hisse sayısı

# --- 2. puanlama ---
DT_MIN_SCORE = 55                      # bu puanın altında "bugün net aday yok" der
DT_ALTERNATES = 2                      # ana seçimin yanında yedek olarak kaç isim yazılsın (0 = hiç)
DT_SETUP_POINTS = {                    # kurulum (setup) puanları, toplam en fazla 30
    "orb": 15, "gap_and_go": 12, "vwap_reclaim": 10, "vwap_pullback": 10, "trend": 5,
}

# --- 3. işlem planı ---
DT_STOP_MIN_ATR_FRAC = 0.25            # stop mesafesi en az günlük ATR'nin %25'i
DT_STOP_MAX_ATR_FRAC = 0.60            # en fazla günlük ATR'nin %60'ı
DT_TARGET1_R = 1.5                     # hedef 1 = riskin 1.5 katı
DT_TARGET2_R = 2.5                     # hedef 2 = riskin 2.5 katı
DT_ACCOUNT_SIZE = float(os.getenv("DT_ACCOUNT_SIZE", "0"))  # USD; 0 ise adet hesabı yapılmaz
DT_RISK_PCT = 1.0                      # tek işlemde hesabın % kaçı riske edilsin

# --- 4. zamanlama ---
DT_WINDOW_ET = ("09:50", "15:30")      # tarama saat aralığı (New York saati)
DT_WATCH_INTERVAL_MIN = 5              # --watch modunda kaç dakikada bir tarasın
DT_WATCH_END_ET = "15:30"              # --watch modu bu saatte kapanır
DT_STATE_FILE = "daytrade_state.json"
