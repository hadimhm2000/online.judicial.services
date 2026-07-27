# راهنمای نصب و اجرای ربات تلگرام

## پیش‌نیازها

1. Python 3.8 یا بالاتر
2. pip (مدیریت پکیج Python)
3. یک ربات تلگرام (دریافت توکن از [@BotFather](https://t.me/BotFather))
4. آیدی عددی تلگرام خود (می‌توانید از [@userinfobot](https://t.me/userinfobot) دریافت کنید)

## مراحل نصب

### ۱. کلون کردن پروژه

```bash
git clone https://github.com/hadimhm2000/online.judicial.services.git
cd online.judicial.services
```

### ۲. نصب پکیج‌های مورد نیاز

```bash
pip install -r requirements.txt
```

یا با استفاده از virtual environment (توصیه می‌شود):

```bash
# ایجاد virtual environment
python -m venv venv

# فعال‌سازی virtual environment
# در Windows:
venv\Scripts\activate
# در Linux/Mac:
source venv/bin/activate

# نصب پکیج‌ها
pip install -r requirements.txt
```

### ۳. نصب Playwright (برای اتوماسیون مرورگر)

```bash
playwright install
```

### ۴. نصب Tesseract OCR (برای خواندن فیش‌های واریزی)

**Windows:**
- دانلود از [این لینک](https://github.com/UB-Mannheim/tesseract/wiki)
- نصب و افزودن به PATH

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-fas
```

**macOS:**
```bash
brew install tesseract
```

### ۵. تنظیم متغیرهای محیطی

یک فایل `.env` در ریشه پروژه ایجاد کنید:

```bash
cp .env.telegram.example .env
```

سپس فایل `.env` را ویرایش کنید و مقادیر زیر را تنظیم کنید:

```env
BOT_TOKEN=توکن_ربات_شما_از_BotFather
ADMIN_ID=آیدی_عددی_تلگرام_شما
PROXY_URL=http://127.0.0.1:10808  # اختیاری - فقط در صورت نیاز به پروکسی
```

**نکته:** اگر نیاز به پروکسی ندارید، خط `PROXY_URL` را کامنت کنید یا خالی بگذارید.

## اجرای ربات

```bash
python bot.py
```

اگر همه چیز درست پیکربندی شده باشد، باید پیام زیر را ببینید:

```
🔌 اتصال مستقیم به سرورهای تلگرام...
```

یا در صورت استفاده از پروکسی:

```
🔌 اتصال از طریق پروکسی: http://127.0.0.1:10808
```

## تست قابلیت‌های جدید

### تست بخش لایحه با شماره بایگانی

1. در تلگرام، ربات را استارت کنید: `/start`
2. گزینه "📝 ثبت لایحه" را انتخاب کنید
3. یک عنوان لایحه را انتخاب کنید (مثلاً "لایحه دفاعیه")
4. در صفحه انتخاب روش، گزینه "2️⃣ شعبه رسیدگی کننده و شماره بایگانی" را انتخاب کنید
5. یک شماره بایگانی معتبر وارد کنید:
   - برای ۷ رقمی: `0012345` (با دو رقم اول ۰۰ تا ۰۷)
   - برای ۶ رقمی: `931234` (با دو رقم اول ۹۳ تا ۹۹)
6. نام شعبه را وارد کنید (مثلاً "شعبه ۱۰۱ دادگاه عمومی تهران")
7. استان را انتخاب کنید
8. بقیه مراحل را طبق معمول تکمیل کنید

### اجرای تست‌های واحد

برای اطمینان از صحت عملکرد توابع validation:

```bash
python test_lavayeh_validation.py
```

اگر همه چیز درست باشد، باید پیام زیر را ببینید:

```
🎉 تمام تست‌ها با موفقیت انجام شدند!
```

## عیب‌یابی

### خطای "ModuleNotFoundError"
اطمینان حاصل کنید که تمام پکیج‌ها نصب شده‌اند:
```bash
pip install -r requirements.txt
```

### خطای "BOT_TOKEN not set"
مطمئن شوید که فایل `.env` را ایجاد کرده‌اید و `BOT_TOKEN` را در آن تنظیم کرده‌اید.

### خطای اتصال به تلگرام
- بررسی کنید که اتصال اینترنت دارید
- اگر در ایران هستید، ممکن است نیاز به پروکسی داشته باشید
- `PROXY_URL` را در فایل `.env` تنظیم کنید

### خطای Playwright
اگر خطای مربوط به Playwright دریافت کردید:
```bash
playwright install
```

## فایل‌های مهم

- `bot.py`: فایل اصلی اجرای ربات
- `lavayeh_handlers.py`: هندلرهای بخش لایحه (شامل تغییرات جدید)
- `states.py`: تعریف حالت‌های مکالمه (FSM States)
- `keyboards.py`: تعریف کیبوردهای تلگرام
- `config.py`: تنظیمات اصلی (شماره کارت، تعرفه‌ها و...)

## اطلاعات بیشتر

برای جزئیات تغییرات اعمال شده در بخش لایحه، فایل `README_LAVAYEH_UPDATE.md` را مطالعه کنید.
