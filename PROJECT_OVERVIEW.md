# 🏛️ سیستم خدمات قضایی آنلاین - ربات تلگرام

## 🎯 معرفی کلی

این پروژه یک **ربات تلگرام پیشرفته** برای ارائه سرویس‌های قضایی آنلاین است که شامل موارد زیر می‌باشد:

- ✅ ثبت لایحه (با دو روش مختلف)
- ✅ ثبت اظهارنامه
- ✅ محاسبه تمبر مالیاتی
- ✅ استعلام پرونده‌ها
- ✅ جستجوی درختی شعب قضایی

---

## 🆕 آخرین به‌روزرسانی (نسخه ۲.۰)

### ✨ قابلیت‌های جدید

1. **دو روش ثبت لایحه:**
   - روش اول: شماره پرونده + ردیف فرعی (حفظ شده)
   - روش دوم: شماره بایگانی + شعبه (جدید)

2. **سیستم انتخاب شعب درختی:**
   - نمایش سلسله‌مراتبی شعب
   - صفحه‌بندی خودکار
   - دستور مستقل `/branches`

3. **Validation پیشرفته:**
   - شماره بایگانی: ۶ یا ۷ رقمی بسته به دو رقم اول

---

## 📁 ساختار پروژه

```
online.judicial.services/
├── 🤖 فایل‌های اصلی ربات
│   ├── bot.py                      # نقطه ورود اصلی
│   ├── config.py                   # تنظیمات
│   ├── states.py                   # State های FSM
│   ├── keyboards.py                # کیبوردها
│   └── handlers.py                 # هندلرهای عمومی
│
├── 📝 ماژول‌های تخصصی
│   ├── lavayeh_handlers.py         # بخش لایحه ⭐
│   ├── lavayeh_sign_handlers.py    # امضای الکترونیک
│   ├── ezhharnameh_handlers.py     # اظهارنامه
│   ├── stamp_calc_handlers.py      # محاسبه تمبر
│   └── branches.py                 # سیستم شعب ⭐
│
├── 🛠️ ماژول‌های کمکی
│   ├── scenarios.py                # سناریوهای اجرا
│   ├── browser_helpers.py          # اتوماسیون مرورگر
│   ├── ocr.py                      # تشخیص فیش
│   └── sheets.py                   # Google Sheets
│
├── 📄 داده‌ها
│   ├── sample_units.json           # نمونه داده شعب
│   └── make_compact_units.py       # تولید داده فشرده
│
├── 🧪 تست
│   └── test_lavayeh_validation.py
│
└── 📚 مستندات
    ├── README_TELEGRAM_BOT.md      # معرفی ربات
    ├── INSTALLATION.md             # راهنمای نصب
    ├── README_LAVAYEH_UPDATE.md    # تغییرات لایحه
    ├── README_BRANCHES.md          # سیستم شعب
    ├── FLOWCHART_LAVAYEH.md        # نمودار جریان
    ├── CHANGELOG_LAVAYEH.md        # تاریخچه نسخه ۲.۰
    ├── SUMMARY.md                  # خلاصه پروژه
    └── FINAL_SUMMARY.md            # خلاصه نهایی
```

---

## 🚀 شروع سریع

### ۱. نصب

```bash
git clone https://github.com/hadimhm2000/online.judicial.services.git
cd online.judicial.services
pip install -r requirements.txt
playwright install
```

### ۲. تنظیمات

```bash
cp .env.telegram.example .env
# ویرایش .env و تنظیم:
# BOT_TOKEN=...
# ADMIN_ID=...
```

### ۳. اجرا

```bash
python bot.py
```

برای جزئیات کامل، فایل [`INSTALLATION.md`](INSTALLATION.md) را ببینید.

---

## 📖 مستندات

| مستند | محتوا |
|-------|-------|
| [INSTALLATION.md](INSTALLATION.md) | راهنمای نصب و راه‌اندازی |
| [README_TELEGRAM_BOT.md](README_TELEGRAM_BOT.md) | معرفی کامل ربات |
| [README_LAVAYEH_UPDATE.md](README_LAVAYEH_UPDATE.md) | توضیحات بخش لایحه |
| [README_BRANCHES.md](README_BRANCHES.md) | سیستم شعب درختی |
| [FLOWCHART_LAVAYEH.md](FLOWCHART_LAVAYEH.md) | نمودار جریان |
| [FINAL_SUMMARY.md](FINAL_SUMMARY.md) | خلاصه کامل |

---

## 💡 ویژگی‌های کلیدی

### 🎯 دو روش ثبت لایحه

```
روش ۱: شماره پرونده          روش ۲: شماره بایگانی
├─ ۱۶ یا ۱۸ رقمی              ├─ ۶ یا ۷ رقمی
├─ استان                       ├─ نام شعبه (دستی/لیست)
└─ ردیف فرعی (۱-۳۰)           └─ استان
```

### 🏛️ سیستم شعب درختی

```
قوه قضائیه
└─ دادگستری استان
   └─ دادگاه
      └─ شعبه ۱۰۱
```

- صفحه‌بندی خودکار
- دکمه‌های ناوبری
- نمایش اطلاعات کامل

---

## 🧪 تست

```bash
# تست validation ها
python test_lavayeh_validation.py

# بررسی syntax
python -m py_compile *.py
```

---

## 📊 آمار پروژه

| مورد | تعداد |
|------|:-----:|
| فایل‌های Python | ۲۰+ |
| State های FSM | ۵۰+ |
| هندلرها | ۱۰۰+ |
| کیبوردها | ۳۰+ |
| مستندات (صفحه) | ۱۰۰+ |
| تست‌های واحد | ۱۵+ |

---

## 🤝 مشارکت

برای مشارکت:

1. Fork کنید
2. Branch جدید: `git checkout -b feature/amazing`
3. Commit: `git commit -m 'Add amazing feature'`
4. Push: `git push origin feature/amazing`
5. Pull Request ایجاد کنید

---

## 📄 مجوز

MIT License - فایل `LICENSE` را ببینید.

---

## 📞 ارتباط

- **GitHub:** [hadimhm2000/online.judicial.services](https://github.com/hadimhm2000/online.judicial.services)
- **نویسنده:** هادی منتظران

---

## 🙏 تشکر

از تمام مشارکت‌کنندگان و استفاده‌کنندگان این پروژه سپاسگزاریم!

---

**نسخه فعلی:** 2.0  
**آخرین به‌روزرسانی:** ۱۴۰۳/۰۵/۰۶  
**وضعیت:** ✅ فعال و قابل استفاده

**💻 ساخته شده با ❤️ در ایران**
