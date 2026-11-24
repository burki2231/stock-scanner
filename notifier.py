import os
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
import config as cfg


def _chunks(text, size=3800):
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > size:
            parts.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        parts.append(cur)
    return parts


def send_telegram(text):
    if not (cfg.TELEGRAM_BOT_TOKEN and cfg.TELEGRAM_CHAT_ID):
        return False
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    for part in _chunks(text):
        r = requests.post(url, data={"chat_id": cfg.TELEGRAM_CHAT_ID, "text": part,
                                     "disable_web_page_preview": True}, timeout=20)
        r.raise_for_status()
    return True


def send_ntfy(text, title="Borsa Tarayıcı"):
    if not cfg.NTFY_TOPIC:
        return False
    r = requests.post(f"{cfg.NTFY_SERVER}/{cfg.NTFY_TOPIC}", data=text.encode("utf-8"),
                      headers={"Title": title.encode("utf-8"), "Priority": "default"}, timeout=20)
    r.raise_for_status()
    return True


def send_telegram_photo(path, caption=""):
    if not (cfg.TELEGRAM_BOT_TOKEN and cfg.TELEGRAM_CHAT_ID):
        return False
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open(path, "rb") as f:
        r = requests.post(url, data={"chat_id": cfg.TELEGRAM_CHAT_ID, "caption": caption[:1000]},
                          files={"photo": f}, timeout=60)
    r.raise_for_status()
    return True


def send_ntfy_image(path, caption="", title="Borsa Tarayıcı"):
    if not cfg.NTFY_TOPIC:
        return False
    with open(path, "rb") as f:
        r = requests.put(f"{cfg.NTFY_SERVER}/{cfg.NTFY_TOPIC}", data=f.read(), timeout=60,
                         headers={"Filename": os.path.basename(path),
                                  "Title": title.encode("utf-8"),
                                  "Message": caption.encode("utf-8")})
    r.raise_for_status()
    return True


def send_email(text, subject="Borsa Tarayıcı", images=None):
    if not (cfg.SMTP_HOST and cfg.EMAIL_TO):
        return False
    msg = MIMEMultipart()
    msg["Subject"], msg["From"], msg["To"] = subject, cfg.SMTP_USER, cfg.EMAIL_TO
    msg.attach(MIMEText(text, "plain", "utf-8"))
    for path, _cap in images or []:
        with open(path, "rb") as f:
            img = MIMEImage(f.read())
        img.add_header("Content-Disposition", "attachment", filename=os.path.basename(path))
        msg.attach(img)
    with smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT) as s:
        s.starttls()
        if cfg.SMTP_USER:
            s.login(cfg.SMTP_USER, cfg.SMTP_PASS)
        s.send_message(msg)
    return True


def notify(text, title="Borsa Tarayıcı", images=None):
    """Ayarlı tüm kanallara gönderir. images: [(png_yolu, açıklama), ...]. Hiçbiri ayarlı değilse False."""
    images = images or []
    sent = False
    jobs = [(send_telegram, (text,)), (send_ntfy, (text, title)), (send_email, (text, title, images))]
    for fn, args in jobs:
        try:
            sent = fn(*args) or sent
        except Exception as e:
            print(f"[bildirim hatası] {fn.__name__}: {e}")
    for path, cap in images:
        for fn in (send_telegram_photo, send_ntfy_image):
            try:
                fn(path, cap) if fn is send_telegram_photo else fn(path, cap, title)
            except Exception as e:
                print(f"[grafik gönderme hatası] {fn.__name__}: {e}")
    return sent
