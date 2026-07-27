# 🤖 ربات تلگرام سرویس‌های قضایی آنلاین

<div dir="rtl">

## 📝 توضیحات

این ربات تلگرام برای ارائه سرویس‌های قضایی آنلاین طراحی شده است و امکانات زیر را فراهم می‌کند:

### ✨ امکانات اصلی

1. **📋 ثبت لایحه**
   - لایحه دفاعیه
   - صدور اجرائیه
   - اعتراض به نظر کارشناس
   - اعتراض به قرار رد دفتر
   - اعلام وکالت
   - سایر عناوین

2. **📄 ثبت اظهارنامه**
   - برای اشخاص حقیقی و حقوقی
   - با امکان افزودن مدارک

3. **🧮 محاسبه تمبر مالیاتی**
   - محاسبه خودکار بر اساس نوع و مبلغ خواسته

4. **🔍 استعلام**
   - براساس شماره تماس
   - براساس کدملی
   - براساس کد رهگیری

---

## 🆕 قابلیت جدید: دو روش ثبت لایحه

### روش ۱: شماره پرونده (روش سنتی)
```
شماره پرونده (۱۶ یا ۱۸ رقمی)
    ↓
انتخاب استان
    ↓
ردیف فرعی (۱-۳۰)
```

### روش ۲: شماره بایگانی (روش جدید) 🎉
```
شماره بایگانی (۶ یا ۷ رقمی)
    ↓
نام شعبه
    ↓
انتخاب استان
```

#### قوانین شماره بایگانی:
- 🔢 دو رقم اول **۰۰ تا ۰۷**: باید **۷ رقمی** باشد
- 🔢 دو رقم اول **۹۳ تا ۹۹**: باید **۶ رقمی** باشد

---

## 🚀 نصب و راه‌اندازی

### پیش‌نیازها
- Python 3.8+
- Playwright
- Tesseract OCR

### مراحل نصب

```bash
# ۱. کلون پروژه
git clone https://github.com/hadimhm2000/online.judicial.services.git
cd online.judicial.services

# ۲. ایجاد virtual environment (توصیه می‌شود)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# یا
venv\Scripts\activate     # Windows

# ۳. نصب پکیج‌ها
pip install -r requirements.txt

# ۴. نصب Playwright browsers
playwright install

# ۵. تنظیم متغیرهای محیطی
cp .env.telegram.example .env
# فایل .env را ویرایش کنید و BOT_TOKEN و ADMIN_ID را تنظیم کنید

# ۶. اجرای ربات
python bot.py
```

برای جزئیات بیشتر، فایل [`INSTALLATION.md`](INSTALLATION.md) را مطالعه کنید.

---

## 📚 مستندات

| فایل | توضیح |
|------|-------|
| [`README_TELEGRAM_BOT.md`](README_TELEGRAM_BOT.md) | این فایل - معرفی کلی |
| [`INSTALLATION.md`](INSTALLATION.md) | راهنمای کامل نصب |
| [`README_LAVAYEH_UPDATE.md`](README_LAVAYEH_UPDATE.md) | توضیحات قابلیت جدید لایحه |
| [`CHANGELOG_LAVAYEH.md`](CHANGELOG_LAVAYEH.md) | تاریخچه تغییرات نسخه ۲.۰ |
| [`FLOWCHART_LAVAYEH.md`](FLOWCHART_LAVAYEH.md) | نمودار جریان سیستم |
| [`SUMMARY.md`](SUMMARY.md) | خلاصه کامل پروژه |

---

## 🧪 تست

```bash
# اجرای تست‌های واحد
python test_lavayeh_validation.py

# بررسی syntax
python -m py_compile lavayeh_handlers.py
python -m py_compile states.py
python -m py_compile keyboards.py
```

---

## 🏗️ ساختار پروژه

```
.
├── bot.py                          # فایل اصلی ربات
├── config.py                       # تنظیمات (توکن، تعرفه‌ها)
├── states.py                       # تعریف State های FSM
├── keyboards.py                    # کیبوردهای تلگرام
├── handlers.py                     # هندلرهای عمومی
│
├── lavayeh_handlers.py             # هندلرهای بخش لایحه ⭐
├── lavayeh_sign_handlers.py        # امضای الکترونیک لایحه
├── lavayeh_scenario.py             # سناریوی اجرای لایحه
│
├── ezhharnameh_handlers.py         # هندلرهای اظهارنامه
├── ezhharnameh_scenario.py         # سناریوی اظهارنامه
│
├── ealam_vakalaht_handlers.py      # هندلرهای اعلام وکالت
├── ealam_vakalaht_scenario.py      # سناریوی اعلام وکالت
│
├── stamp_calc_handlers.py          # محاسبه تمبر
├── stamp_duty.py                   # منطق محاسبه تمبر
│
├── scenarios.py                    # سناریوهای عمومی
├── browser_helpers.py              # کمک‌کننده‌های مرورگر
├── ocr.py                          # تشخیص فیش واریزی
├── sheets.py                       # اتصال به Google Sheets
│
├── requirements.txt                # وابستگی‌های Python
├── .env.telegram.example           # نمونه فایل تنظیمات
│
└── docs/                           # مستندات
    ├── README_LAVAYEH_UPDATE.md
    ├── INSTALLATION.md
    ├── CHANGELOG_LAVAYEH.md
    ├── FLOWCHART_LAVAYEH.md
    └── SUMMARY.md
```

---

## 🔑 متغیرهای محیطی

فایل `.env` باید شامل موارد زیر باشد:

```env
# ضروری
BOT_TOKEN=توکن_ربات_از_BotFather
ADMIN_ID=آیدی_عددی_تلگرام_ادمین

# اختیاری (برای پروکسی)
PROXY_URL=http://127.0.0.1:10808
```

---

## 💡 مثال استفاده

### ثبت لایحه با شماره بایگانی

```
👤 کاربر: /start
🤖 ربات: خوش آمدید! لطفاً یک گزینه انتخاب کنید.

👤 کاربر: 📝 ثبت لایحه
🤖 ربات: لطفاً عنوان لایحه را انتخاب کنید.

👤 کاربر: لایحه دفاعیه
🤖 ربات: لطفاً روش ثبت را انتخاب کنید:
         1️⃣ شماره پرونده و ردیف فرعی
         2️⃣ شعبه رسیدگی کننده و شماره بایگانی

👤 کاربر: 2️⃣
🤖 ربات: لطفاً شماره بایگانی را ارسال فرمایید
         • دو رقم اول ۰۰-۰۷ → ۷ رقمی
         • دو رقم اول ۹۳-۹۹ → ۶ رقمی

👤 کاربر: 0012345
🤖 ربات: ✅ شماره بایگانی ثبت شد.
         لطفاً نام شعبه را تعیین کنید.

👤 کاربر: شعبه ۱۰۱ دادگاه عمومی تهران
🤖 ربات: لطفاً استان را انتخاب کنید.

👤 کاربر: تهران
🤖 ربات: ✅ ثبت شد. حالا نوع شخصیت را انتخاب کنید...
```

---

## 🛠️ تکنولوژی‌ها

- **Framework:** [Aiogram 3.7.0](https://aiogram.dev/)
- **اتوماسیون:** [Playwright](https://playwright.dev/)
- **OCR:** [Tesseract](https://github.com/tesseract-ocr/tesseract)
- **Database:** Google Sheets
- **زبان:** Python 3.8+

---

## 🐛 عیب‌یابی

### مشکلات رایج

1. **خطای ModuleNotFoundError**
   ```bash
   pip install -r requirements.txt
   ```

2. **ربات استارت نمی‌شود**
   - بررسی `.env`
   - بررسی توکن ربات
   - بررسی اتصال اینترنت/پروکسی

3. **خطای Playwright**
   ```bash
   playwright install
   ```

4. **خطای Tesseract**
   - نصب Tesseract OCR از [اینجا](https://github.com/UB-Mannheim/tesseract/wiki)

---

## 📊 آمار

- ⭐ ستاره‌ها: -
- 🍴 Fork ها: -
- 📝 Issues: -
- 👥 مشارکت‌کنندگان: 1+

---

## 🤝 مشارکت

برای مشارکت در پروژه:

1. Fork کنید
2. یک branch جدید بسازید (`git checkout -b feature/amazing-feature`)
3. تغییرات را commit کنید (`git commit -m 'Add amazing feature'`)
4. Push کنید (`git push origin feature/amazing-feature`)
5. یک Pull Request ایجاد کنید

---

## 📄 مجوز

این پروژه تحت مجوز MIT منتشر شده است - برای جزئیات فایل `LICENSE` را ببینید.

---

## 📞 تماس

- **مخزن GitHub:** [hadimhm2000/online.judicial.services](https://github.com/hadimhm2000/online.judicial.services)
- **نویسنده:** هادی منتظران

---

## 🙏 تشکر

از تمام کسانی که در توسعه این پروژه مشارکت داشته‌اند، سپاسگزاریم!

---

## 📌 یادداشت‌های نسخه

### نسخه ۲.۰ (فعلی)
- ✅ افزودن قابلیت ثبت با شماره بایگانی
- ✅ Validation پیشرفته برای شماره‌ها
- ✅ بهبود UX با پیام‌های راهنما
- ✅ مستندسازی کامل

### نسخه ۱.۰
- ثبت لایحه با شماره پرونده
- ثبت اظهارنامه
- محاسبه تمبر
- استعلام

---

**🔥 آخرین به‌روزرسانی:** ۱۴۰۳/۰۵/۰۶

**💻 ساخته شده با ❤️ در ایران**

</div>
