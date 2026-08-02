
```python
"""
حالت‌های مشترک و متغیرهای زنده‌ی برنامه که چند ماژول دیگر باید همزمان بهشون
دسترسی داشته باشن (صف کارها، وضعیت لاگین، صفحه/کانتکست مرورگر).
"""
import asyncio
import json
import os
import datetime
import logging

job_queue: asyncio.Queue = asyncio.Queue()
login_event: asyncio.Event = asyncio.Event()

dp = None
browser_context = None
sana_page = None
active_lavayeh_users: set = set()

PAYMENTS_FILE = "pending_payments.json"

def load_pending_payments():
    """بارگذاری فاکتورهای در انتظار پرداخت از فایل JSON"""
    global pending_lavayeh_payments
    if os.path.exists(PAYMENTS_FILE):
        try:
            with open(PAYMENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # تبدیل کلیدها به int و زمان به datetime
                pending_lavayeh_payments = {}
                for uid, info in data.items():
                    if info.get("invoice_time"):
                        info["invoice_time"] = datetime.datetime.fromisoformat(info["invoice_time"])
                    pending_lavayeh_payments[int(uid)] = info
                logging.info(f"✅ {len(pending_lavayeh_payments)} فاکتور در انتظار پرداخت از فایل بارگذاری شد.")
        except Exception as e:
            logging.error(f"❌ خطا در خواندن فایل فاکتورها: {e}")
            pending_lavayeh_payments = {}
    else:
        pending_lavayeh_payments = {}

def save_pending_payments():
    """ذخیره فاکتورهای در انتظار پرداخت در فایل JSON"""
    try:
        data_to_save = {}
        for uid, info in pending_lavayeh_payments.items():
            info_copy = info.copy()
            if isinstance(info_copy.get("invoice_time"), datetime.datetime):
                info_copy["invoice_time"] = info_copy["invoice_time"].isoformat()
            data_to_save[str(uid)] = info_copy
            
        with open(PAYMENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"❌ خطا در ذخیره فایل فاکتورها: {e}")

# بارگذاری اولیه هنگام import ماژول
load_pending_payments()

pending_lavayeh_sign: dict = {}
```
