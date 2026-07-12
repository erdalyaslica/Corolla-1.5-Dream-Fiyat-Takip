import csv
import html
import json
import logging
import os
import smtplib
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError


TOYOTA_XML_URL = os.getenv("TOYOTA_XML_URL", "https://turkiye.toyota.com.tr/middle/fiyat-listesi/fiyat_v3.xml")
MODEL_NAME = os.getenv("MODEL_NAME", "1.5 Dream Multidrive S")
STATE_FILE = Path(os.getenv("STATE_FILE", "data/fiyat_gecmisi.csv"))
MIN_VALID_PRICE = int(os.getenv("MIN_VALID_PRICE", "1500000"))


@dataclass
class PriceResult:
    model_year: int
    price: int


def setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def format_try(value):
    return f"{int(value):,}".replace(",", ".")


def load_history():
    if not STATE_FILE.exists():
        return []
    with STATE_FILE.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def save_history(rows):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Tarih", "Model", "Fiyat", "Durum", "Detay"])
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(STATE_FILE)


def parse_price_number(raw):
    if raw is None:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if not digits:
        return None
    return int(digits)


def fetch_current_price():
    req = request.Request(
        TOYOTA_XML_URL,
        headers={
            "User-Agent": "Mozilla/5.0 Chrome/142 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
        },
    )
    with request.urlopen(req, timeout=60) as response:
        content = response.read()

    root = ET.fromstring(content)
    items = list(root.iter("ModelFiyat"))
    if not items:
        raise RuntimeError("XML içinde ModelFiyat kaydı bulunamadı")

    years = []
    for item in items:
        year_text = item.findtext("ModelYili")
        try:
            years.append(int(year_text))
        except (TypeError, ValueError):
            continue
    if not years:
        raise RuntimeError("Model yılı bulunamadı")
    latest_year = max(years)

    candidates = []
    for item in items:
        model = (item.findtext("Model") or "").strip()
        year_text = item.findtext("ModelYili")
        if model != MODEL_NAME or str(year_text).strip() != str(latest_year):
            continue
        raw_price = item.findtext("KampanyaliFiyati2") or item.findtext("ListeFiyati1")
        price = parse_price_number(raw_price)
        if price and price > MIN_VALID_PRICE:
            candidates.append(price)

    if not candidates:
        raise RuntimeError(f"{MODEL_NAME} ({latest_year}) için geçerli fiyat bulunamadı")

    return PriceResult(model_year=latest_year, price=max(candidates))


def last_price(rows):
    for row in reversed(rows):
        try:
            return int(float(row.get("Fiyat", "")))
        except (TypeError, ValueError):
            continue
    return None


def add_history_row(rows, result, status, detail):
    rows.append(
        {
            "Tarih": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Model": f"{MODEL_NAME} ({result.model_year})",
            "Fiyat": str(result.price),
            "Durum": status,
            "Detay": detail,
        }
    )


def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Eksik ortam değişkeni: {name}")
    return value


def email_app_password():
    value = os.getenv("EMAIL_APP_PASSWORD", "").strip() or os.getenv("EMAIL_PASSWORD", "").strip()
    if not value:
        raise RuntimeError("Eksik ortam değişkeni: EMAIL_APP_PASSWORD")
    return value


def email_shell(title, subtitle, content, accent="#0071e3"):
    return f"""<!doctype html><html><body style="margin:0;background:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#1d1d1f">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:40px 16px">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:720px;background:#fff;border-radius:24px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.08)">
    <tr><td style="height:6px;background:{accent}">&nbsp;</td></tr>
    <tr><td style="padding:42px 42px 20px"><div style="font-size:12px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;color:{accent}">Toyota Fiyat Takip</div>
    <h1 style="margin:10px 0 12px;font-size:34px;line-height:40px">{html.escape(title)}</h1>
    <p style="margin:0;font-size:17px;line-height:26px;color:#6e6e73">{html.escape(subtitle)}</p></td></tr>
    <tr><td style="padding:0 42px 42px">{content}</td></tr></table>
    <p style="font-size:12px;color:#86868b">Toyota Fiyat Takip · GitHub Actions</p>
    </td></tr></table></body></html>"""


def price_card(result, previous_price=None):
    diff_html = ""
    if previous_price is not None:
        diff = result.price - previous_price
        direction = "ARTTI" if diff > 0 else ("DÜŞTÜ" if diff < 0 else "AYNI")
        color = "#ff3b30" if diff > 0 else ("#30a14e" if diff < 0 else "#6e6e73")
        diff_html = f"""<div style="margin-top:14px;color:{color};font-weight:700">Değişim: {direction} · {format_try(abs(diff))} TL</div>"""
    return f"""<div style="margin-top:24px;padding:22px;border:1px solid #e8e8ed;border-radius:18px;background:#fbfbfd">
    <div style="font-size:14px;color:#6e6e73">Model</div>
    <div style="font-size:18px;font-weight:700;margin-top:4px">{html.escape(MODEL_NAME)} ({result.model_year})</div>
    <div style="font-size:14px;color:#6e6e73;margin-top:18px">Güncel fiyat</div>
    <div style="font-size:32px;font-weight:800;margin-top:4px">{format_try(result.price)} TL</div>
    {diff_html}
    </div>"""


def send_email(subject, body):
    if os.getenv("EMAIL_ENABLED", "true").lower() != "true":
        logging.info("E-posta gönderimi kapalı")
        return
    sender = required("EMAIL_USER")
    recipients = [x.strip() for x in required("NOTIFICATION_EMAIL").split(",") if x.strip()]
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, sender, ", ".join(recipients)
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, email_app_password())
        server.sendmail(sender, recipients, msg.as_string())


def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        logging.info("Telegram ayarları yok; bildirim atlandı")
        return
    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    ).encode("utf-8")
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("description") or detail
        except ValueError:
            pass
        raise RuntimeError(f"Telegram API {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Telegram bağlantı hatası: {exc}") from exc


def notify(result, previous_price, mode):
    old = "Bilinmiyor" if previous_price is None else f"{format_try(previous_price)} TL"
    diff = 0 if previous_price is None else result.price - previous_price
    direction = "➖ AYNI" if diff == 0 else ("📈 ARTTI" if diff > 0 else "📉 DÜŞTÜ")
    title = "Haftalık Toyota fiyat raporu" if mode == "weekly" else "Toyota fiyat değişti"
    subtitle = datetime.now().strftime("%d.%m.%Y %H:%M itibarıyla")
    body = email_shell(title, subtitle, price_card(result, previous_price), "#ff3b30" if mode == "change" else "#0071e3")

    telegram = (
        "🚗 <b>Toyota Fiyat Takip</b>\n\n"
        f"<b>Model:</b> {html.escape(MODEL_NAME)} ({result.model_year})\n"
        f"<b>Güncel:</b> {format_try(result.price)} TL\n"
        f"<b>Önceki:</b> {old}\n"
        f"<b>Durum:</b> {direction}"
        + (f" ({format_try(abs(diff))} TL)" if diff else "")
        + f"\n<b>Tarih:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

    try:
        send_email(f"Toyota Fiyat Takip - {format_try(result.price)} TL", body)
    except Exception as exc:
        logging.error("E-posta bildirimi gönderilemedi: %s", exc)
    try:
        send_telegram(telegram)
    except Exception as exc:
        logging.error("Telegram bildirimi gönderilemedi: %s", exc)


def weekly_summary(rows, result):
    cutoff = datetime.now() - timedelta(days=7)
    recent = []
    for row in rows:
        try:
            when = datetime.strptime(row.get("Tarih", ""), "%Y-%m-%d %H:%M:%S")
            price = int(float(row.get("Fiyat", "")))
        except (TypeError, ValueError):
            continue
        if when >= cutoff:
            recent.append(price)
    if not recent:
        recent = [result.price]
    return min(recent), max(recent), recent[-1], len(recent)


def run(mode):
    rows = load_history()
    result = fetch_current_price()
    previous = last_price(rows)
    logging.info("Güncel fiyat: %s TL; önceki fiyat: %s", result.price, previous)

    if mode == "price":
        notify(result, previous, "weekly")
        return 0

    if previous is None:
        add_history_row(rows, result, "Takip Başladı", "GitHub Actions")
        save_history(rows)
        notify(result, previous, "change")
        return 0

    if mode == "weekly":
        add_history_row(rows, result, "Haftalık Rapor", "Weekly")
        save_history(rows)
        notify(result, previous, "weekly")
        return 0

    if result.price != previous:
        status = "FİYAT ARTTI" if result.price > previous else "FİYAT DÜŞTÜ"
        add_history_row(rows, result, status, "Auto")
        save_history(rows)
        notify(result, previous, "change")
    else:
        logging.info("Fiyat aynı; kayıt ve bildirim yok")
    return 0


def main():
    setup_logging()
    mode = os.getenv("RUN_MODE", "change").strip().lower()
    if mode not in {"change", "weekly", "price"}:
        raise RuntimeError(f"Geçersiz RUN_MODE: {mode}")
    return run(mode)


if __name__ == "__main__":
    sys.exit(main())
