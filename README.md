# Borsa Tarayıcı (ABD hisseleri)

Her gün piyasa kapanışından sonra S&P 500 + Nasdaq 100 (+ kendi listen) hisselerini tarar,
teknik sinyalleri puanlar, güçlü adayları telefonuna bildirim olarak gönderir.

## Sinyaller
| Sinyal | Anlamı | Ağırlık |
|---|---|---|
| oversold_dip | RSI<30 ama fiyat 200g ortalamanın üstünde | 2.0 |
| rsi_recovery | RSI 30'u aşağıdan yukarı kesti | 2.0 |
| pullback_to_sma50 | Yükseliş trendinde 50g ortalamaya geri çekilme | 1.5 |
| macd_cross_up | MACD sıfırın altında sinyali yukarı kesti | 1.0 |
| golden_cross | 50g ort. 200g ort.'yı yukarı kesti | 1.5 |
| breakout | Hacimli 55 günlük zirve kırılımı | 2.0 |
| hammer | Çekiç mumu (düşüş sonrası) | 1.0 |
| bullish_engulfing | Yükseliş yutan mum | 1.5 |
| morning_star | Sabah yıldızı (3 mumlu dönüş) | 1.5 |
| support_bounce | En az 2 kez test edilmiş desteğe dokunup yeşil mumla dönüş | 1.5 |
| double_bottom | Çift dip + boyun çizgisi kırılımı | 2.0 |
| ascending_triangle | Yatay direnç + yükselen dipler, direnç kırılımı | 1.5 |
| bull_flag | Sert yükseliş sonrası dar bayrak, yukarı kırılım | 1.5 |

Her sinyale ağırlık verilir, toplam puan `MIN_SCORE`'u (varsayılan 2.0) geçerse bildirim gelir.
Tek başına 2.0'ın altında kalan sinyaller (hammer, macd) başka sinyallerle birleşince anlam kazanır.
Ağırlıklar, eşikler, filtreler: `config.py`.

## Grafik ve destek/direnç
- Bildirimle birlikte en yüksek puanlı (varsayılan 5) adayın grafiği PNG olarak gelir: mum grafiği, SMA50/200,
  destek (yeşil) / direnç (kırmızı) çizgileri, hacim ve RSI.
- Bildirim metninde en yakın destek ve direnç, fiyata uzaklıklarıyla yazar.
- `python scanner.py --dry-run` grafikleri `charts/` klasörüne kaydeder, bildirim atmaz.
- Formasyonlar "geleceğe bakmadan" tespit edilir: bir tepe/dip ancak 5 mum sonra onaylanmış sayılır.
- Klasik formasyonlar (çift dip, üçgen, bayrak) koda dökülünce yanlış alarm verebilir. Backtest'te zayıf çıkarsa ağırlığını düşür.

## Kurulum
```bash
pip install -r requirements.txt
python scanner.py --dry-run --limit 50     # bildirim atmadan dene
python backtest.py --limit 100             # sinyaller geçmişte işe yaramış mı?
```

## Telefona bildirim (birini seç)
**Telegram (önerilen):** @BotFather'dan `/newbot` ile bot oluştur, token'ı al. Bota bir mesaj yaz, sonra
`https://api.telegram.org/bot<TOKEN>/getUpdates` adresinden `chat.id` değerini bul.
```bash
export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHAT_ID=123456
python scanner.py --test-notify
```
**ntfy (hesapsız, çok kolay):** ntfy uygulamasını kur, tahmin edilmesi zor bir konu adına abone ol, `export NTFY_TOPIC=bunu-kimse-tahmin-edemez-123`.
**E-posta:** `SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_TO` ortam değişkenleri.

## Bilgisayarını açık tutmadan çalıştırma (GitHub Actions, ücretsiz)
1. Bu klasörü **private** bir GitHub reposuna yükle.
2. Repo > Settings > Secrets and variables > Actions: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (veya `NTFY_TOPIC`) ekle.
3. Actions sekmesinden "Günlük Borsa Taraması"nı elle bir kez çalıştırıp test et. Sonra hafta içi her gün otomatik çalışır.
`state.json` aynı hisse için tekrar bildirimi engeller.

## Önemli notlar
- Veri `yfinance` ile (resmi olmayan, ücretsiz Yahoo verisi). Bazen hata verebilir; ciddi kullanımda Polygon/Finnhub gibi bir API'ye geçilebilir.
- Önce `backtest.py` çalıştır: bir sinyal "tüm günlerin ortalaması"nı belirgin geçmiyorsa ağırlığını düşür.
- "ref. stop" sadece 2xATR'ye dayalı örnek bir referans, kesin seviye değil.
- Bu araç yatırım tavsiyesi vermez, sadece "bakmaya değer" listesi çıkarır. Kararlar sana ait.

## Day trade modu (günün tek en iyi hissesi)
`daytrade.py` gün içi 5 dakikalık veriye bakar ve günün en iyi tek adayını stop/hedefleriyle söyler.

```
python daytrade.py --replay --asof 10:30   # piyasa kapalıyken son işlem gününü dener
python daytrade.py --dry-run               # canlı, bildirim atmaz
python daytrade.py                         # canlı + telefona bildirim
python daytrade.py --watch                 # her 5 dk tarar, yeni güçlü aday çıkınca bildirir
```
**Nasıl seçiyor?**
1. Eleme: yeterli hacim ve günlük hareket (ATR) olmayan hisseler çıkar.
2. Gün içi: fiyat VWAP üstünde olmalı. Kurulumlar: açılış aralığı kırılımı, gap ve devam, VWAP'a dönüş/tepki, güçlü trend.
3. Puan (0-100): göreceli hacim, kurulum gücü, trend uyumu, gap, volatilite, yukarıda direnç boşluğu. Fazla uzamış hisse puan kaybeder.
4. Plan: stop (son dip/VWAP altı, günlük ATR'ye göre sınırlı), Hedef 1 = 1.5R, Hedef 2 = 2.5R.
Puan `DT_MIN_SCORE` altındaysa "bugün net aday yok" der.

Ayarlar `config.py`'ın en altındaki DAY TRADE bölümünde. `DT_ACCOUNT_SIZE` ortam değişkeniyle hesap büyüklüğü verilirse adet de hesaplanır.

**Zamanlama:** ABD piyasası New York saatiyle 09:30-16:00 (Almanya'da genelde 15:30-22:00). En mantıklı tarama
açılıştan 20-60 dk sonra. `daytrade.yml` GitHub Actions'ta bunu otomatik yapar (zamanlama birkaç dk kayabilir);
hassas zamanlama için bilgisayarda `--watch` kullan.

**Sınırlar:** Yahoo verisi ücretsiz ve gecikmeli olabilir, profesyonel veri değildir. Tek hisse seçimi bir olasılık
sıralamasıdır, garanti değildir. Day trade yüksek risklidir; stop'u kullan, gün bitmeden kapat.
