# ربات تلگرام خدمات آنلاین قضایی

ربات تلگرام برای ارائه خدمات آنلاین قضایی شامل ثبت لایحه، اظهارنامه، و سایر خدمات.

## ویژگی‌ها

- 📝 **ثبت لایحه**: ثبت لایحه با انتخاب شعبه از ساختار درختی کامل
- 📋 **اعلام وکالت**: ثبت اعلامیه وکالت
- 📄 **اظهارنامه**: ثبت اظهارنامه
- 🧮 **محاسبه تمبر**: محاسبه خودکار هزینه تمبر
- 🔍 **انتخاب شعبه هوشمند**: جستجو و انتخاب از بین هزاران شعبه قضایی

## پیش‌نیازها

- Python 3.8 یا بالاتر
- اکانت ربات تلگرام (از BotFather)
- PostgreSQL (اختیاری - برای ذخیره‌سازی)

## نصب

### 1. کلون کردن پروژه

```bash
git clone https://github.com/hadimhm2000/online.judicial.services.git
cd online.judicial.services
```

### 2. ایجاد محیط مجازی

```bash
python -m venv venv
source venv/bin/activate  # در لینوکس/مک
# یا
venv\Scripts\activate  # در ویندوز
```

### 3. نصب وابستگی‌ها

```bash
pip install -r requirements.txt
```

### 4. تنظیم متغیرهای محیطی

فایل `.env` ایجاد کنید:

```env
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_ID=your_telegram_user_id
CARD_NUMBER=your_payment_card_number
ACCOUNT_NAME=account_holder_name

# اختیاری - برای Google Sheets
GOOGLE_CREDENTIALS_FILE=google-credentials.json
SPREADSHEET_ID=your_spreadsheet_id
```

### 5. نصب Playwright (برای automation مرورگر)

```bash
playwright install chromium
```

## استفاده

### اجرای ربات

```bash
python bot.py
```

### تست سیستم انتخاب شعب

```bash
python test_branches_system.py
```

## ساختار پروژه

```
.
├── bot.py                      # نقطه ورود اصلی ربات
├── handlers.py                 # هندلرهای اصلی
├── lavayeh_handlers.py         # هندلرهای بخش لایحه
├── lavayeh_scenario.py         # سناریوهای اتوماسیون لایحه
├── branches.py                 # سیستم انتخاب شعب
├── keyboards.py                # کیبوردهای تلگرام
├── states.py                   # وضعیت‌های FSM
├── config.py                   # تنظیمات
├── units_compact.json          # داده شعب قضایی
└── requirements.txt            # وابستگی‌ها
```

## فایل داده شعب

فایل `units_compact.json` شامل ساختار کامل شعب قضایی است. برای اطلاعات بیشتر:

```bash
cat README_UNITS.md
```

## تغییرات اخیر

برای مشاهده تغییرات اخیر و بهبودهای سیستم انتخاب شعبه:

```bash
cat CHANGES.md
```

## توسعه

### اضافه کردن handler جدید

1. هندلر را در فایل مربوطه (مثلاً `handlers.py`) تعریف کنید
2. State مربوطه را در `states.py` اضافه کنید
3. کیبورد لازم را در `keyboards.py` ایجاد کنید
4. Router را در `bot.py` ثبت کنید

### اضافه کردن سناریوی جدید

1. سناریو را در فایل `*_scenario.py` تعریف کنید
2. توابع automation مرورگر را در `browser_helpers.py` اضافه کنید
3. Handler مربوطه را ایجاد کنید

## مشکلات رایج

### ربات پاسخ نمی‌دهد
- بررسی کنید که `BOT_TOKEN` صحیح است
- مطمئن شوید که ربات در حال اجراست
- لاگ‌ها را بررسی کنید

### شعب نمایش داده نمی‌شوند
- بررسی کنید که فایل `units_compact.json` موجود است
- با `python test_branches_system.py` صحت داده را بررسی کنید

### خطای Playwright
```bash
playwright install
playwright install-deps
```

## مجوزها

این پروژه برای استفاده داخلی است. تمامی حقوق محفوظ است.

## پشتیبانی

برای گزارش مشکلات یا درخواست ویژگی‌های جدید، با تیم توسعه تماس بگیرید.

## نویسندگان

- توسعه‌دهنده اصلی: [@hadimhm2000](https://github.com/hadimhm2000)

## تاریخچه نسخه‌ها

### نسخه 2.0 (فعلی)
- ✅ بازطراحی کامل سیستم انتخاب شعب
- ✅ حذف ورود دستی نام شعبه
- ✅ افزودن ساختار درختی کامل قوه قضائیه
- ✅ پشتیبانی از 40+ شاخه اصلی
- ✅ validation کد شعبه

### نسخه 1.0
- ✅ ثبت لایحه
- ✅ اعلام وکالت
- ✅ محاسبه تمبر
- ✅ اظهارنامه
