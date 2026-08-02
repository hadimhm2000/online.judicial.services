```python
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ متغیر محیطی BOT_TOKEN تنظیم نشده است.")

_admin_id_raw = os.environ.get("ADMIN_ID")
if not _admin_id_raw:
    raise RuntimeError("❌ متغیر محیطی ADMIN_ID تنظیم نشده است.")
ADMIN_ID = int(_admin_id_raw)

PROXY_URL = os.environ.get("PROXY_URL", "http://127.0.0.1:10808")

# تنظیمات مالی ربات
CARD_NUMBER = os.environ.get("CARD_NUMBER")
ACCOUNT_NAME = os.environ.get("ACCOUNT_NAME")

if not CARD_NUMBER or not ACCOUNT_NAME:
    raise RuntimeError("❌ متغیرهای محیطی CARD_NUMBER یا ACCOUNT_NAME تنظیم نشده‌اند.")

DEBUG_LOG_REQUESTS = False

FEES = {
    "شماره تماس": 65000,
    "کد ملی": 55000,
    "کد رهگیری ساده": 50000,
    "کد رهگیری با منضمات": 50000
}

def get_fee(query_type, need_attachments):
    if query_type == "شماره تماس":
        return FEES["شماره تماس"]
    elif query_type == "کد ملی":
        return FEES["کد ملی"]
    else:
        if need_attachments:
            return FEES["کد رهگیری با منضمات"]
        else:
            return FEES["کد رهگیری ساده"]

def calculate_lavayeh_fee(court_total: int) -> int:
    if court_total <= 200_000:
        deduction = 10_000
    elif court_total <= 300_000:
        deduction = 20_000
    else:
        deduction = 35_000
    final_fee = court_total + (court_total - deduction)
    return final_fee

def format_lavayeh_fee_explanation(court_total: int) -> str:
    if court_total <= 200_000:
        deduction = 10_000
        bracket = "تا ۲۰۰,۰۰۰ تومان"
    elif court_total <= 300_000:
        deduction = 20_000
        bracket = "۲۰۱,۰۰۰ تا ۳۰۰,۰۰۰ تومان"
    else:
        deduction = 35_000
        bracket = "بالای ۳۰۰,۰۰۰ تومان"

    net = court_total - deduction
    final_fee = court_total + net

    return (
        f"💰 **محاسبه هزینه خدمات:**\n\n"
        f"مجموع هزینه ثبت شده در سامانه: **{court_total:,} تومان**\n"
        f"بازه: {bracket} → کسر: **{deduction:,} تومان**\n\n"
        f"فرمول: {court_total:,} + ({court_total:,} − {deduction:,})\n"
        f"       = {court_total:,} + {net:,}\n"
        f"       = **{final_fee:,} تومان**\n\n"
        f"💳 **مبلغ نهایی قابل پرداخت: {final_fee:,} تومان**"
    )
