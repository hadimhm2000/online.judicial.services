# رفع خطای ImportError در ربات تلگرام خدمات قضایی

## 📋 خلاصه مشکل

هنگام انتخاب گزینه "🔍 انتخاب شعبه از لیست" در بخش ثبت لایحه، خطای زیر رخ می‌داد:

```
File "lavayeh_handlers.py", line 411, in lavayeh_get_branch_input_method
    from keyboards import lavayeh_branch_input_method_kb, back_only_kb, ReplyKeyboardRemove
ImportError: cannot import name 'ReplyKeyboardRemove' from 'keyboards'
```

## 🔍 تحلیل مشکل

### علت اصلی
در خط ۴۱۱ فایل `lavayeh_handlers.py`، سعی شده بود که کلاس `ReplyKeyboardRemove` از ماژول محلی `keyboards.py` import شود:

```python
from keyboards import lavayeh_branch_input_method_kb, back_only_kb, ReplyKeyboardRemove
```

اما `ReplyKeyboardRemove` یک کلاس از کتابخانه `aiogram` است که باید از `aiogram.types` import شود، نه از فایل محلی `keyboards.py`.

### چرا این خطا رخ داد؟
- کلاس `ReplyKeyboardRemove` قبلاً در خط ۱۴ به درستی از `aiogram.types` import شده بود
- اما در خط ۴۱۱، به اشتباه سعی شده بود دوباره از `keyboards` import شود
- ماژول `keyboards.py` این کلاس را export نمی‌کند، بنابراین خطا رخ می‌دهد

## ✅ راه حل

خطا با حذف `ReplyKeyboardRemove` از import خط ۴۱۱ رفع شد:

**قبل:**
```python
from keyboards import lavayeh_branch_input_method_kb, back_only_kb, ReplyKeyboardRemove
from branches import UNITS_DATA, create_branches_keyboard, ROOT_NODES
```

**بعد:**
```python
from keyboards import lavayeh_branch_input_method_kb, back_only_kb
from branches import UNITS_DATA, create_branches_keyboard, ROOT_NODES
```

## 🎯 نتیجه

پس از این تغییر:
1. ✅ خطای `ImportError` برطرف شد
2. ✅ کلاس `ReplyKeyboardRemove` از import اصلی در خط ۱۴ استفاده می‌شود
3. ✅ سیستم انتخاب شعبه به درستی کار می‌کند
4. ✅ لیست شعب قضایی نمایش داده می‌شود

## 🧪 تست رفع خطا

### روش ۱: اجرای ربات
```bash
# فعال‌سازی محیط مجازی
source venv/bin/activate  # Linux/Mac
# یا
venv\Scripts\activate  # Windows

# اجرای ربات
python bot.py
```

### روش ۲: تست سیستم شعب
```bash
python test_branches_system.py
```

### روش ۳: تست import ها
```bash
python test_import_fix.py
```

## 📝 مراحل تست در تلگرام

1. ربات را اجرا کنید
2. به ربات در تلگرام پیام `/start` بدهید
3. گزینه **"📝 ثبت لایحه"** را انتخاب کنید
4. مراحل را طی کنید:
   - انتخاب عنوان لایحه
   - وارد کردن شماره بایگانی
5. در مرحله انتخاب شعبه، گزینه **"🔍 انتخاب شعبه از لیست"** را انتخاب کنید
6. باید پیام زیر را ببینید:
   ```
   🏛 سامانه انتخاب شعبه قضایی
   
   لطفاً از لیست زیر شروع کنید و تا رسیدن به واحد نهایی (شعبه) ادامه دهید:
   
   ℹ️ فقط واحدهای نهایی که دارای کد هستند قابل انتخاب می‌باشند.
   ```
7. سپس لیست شعب به صورت inline keyboard نمایش داده می‌شود

## 🔧 فایل‌های تغییر یافته

- **`lavayeh_handlers.py`** (خط ۴۱۱)

## 📚 توضیحات فنی

### ساختار import در lavayeh_handlers.py

```python
# خط ۱۴ - import اصلی (صحیح)
from aiogram.types import Message, ReplyKeyboardRemove

# خط ۲۱-۳۰ - import کیبوردهای محلی
from keyboards import (
    main_menu_kb, restart_kb, back_only_kb,
    lavayeh_title_kb, LAVAYEH_TITLES,
    # ... سایر کیبوردها
)

# خط ۴۱۱ - import محلی در تابع (اصلاح شده)
from keyboards import lavayeh_branch_input_method_kb, back_only_kb
# ReplyKeyboardRemove حذف شد چون از خط ۱۴ در دسترس است
```

### نحوه استفاده از ReplyKeyboardRemove

```python
# استفاده در خط ۴۳۰
await message.answer(
    "🏛 **سامانه انتخاب شعبه قضایی**\n\n"
    "لطفاً از لیست زیر شروع کنید...",
    reply_markup=ReplyKeyboardRemove(),  # حذف کیبورد معمولی
    parse_mode="Markdown"
)
```

## ⚠️ نکات مهم

1. **وجود فایل units_compact.json**
   - اگر فایل `units_compact.json` موجود نباشد، لیست شعب نمایش داده نمی‌شود
   - مطمئن شوید این فایل در پوشه اصلی پروژه قرار دارد

2. **بررسی داده شعب**
   ```bash
   python test_branches_system.py
   ```

3. **لاگ‌های خطا**
   - در صورت بروز مشکل، لاگ‌های کنسول را بررسی کنید
   - خطاهای مربوط به import باید برطرف شده باشند

## 🐛 مشکلات احتمالی

### مشکل: لیست شعب نمایش داده نمی‌شود

**علت‌های احتمالی:**
1. فایل `units_compact.json` وجود ندارد
2. فرمت JSON فایل معتبر نیست
3. مشکل در بارگذاری داده‌ها

**راه حل:**
```bash
# بررسی وجود فایل
ls -l units_compact.json

# بررسی فرمت JSON
python -m json.tool units_compact.json > /dev/null && echo "JSON معتبر است"

# تست سیستم شعب
python test_branches_system.py
```

### مشکل: خطاهای دیگر import

اگر خطاهای مشابه دیگری مشاهده کردید:
```bash
# جستجوی همه import های ReplyKeyboardRemove
grep -rn "from keyboards import.*ReplyKeyboardRemove" .
```

## 📞 پشتیبانی

در صورت بروز مشکل:
1. لاگ‌های کامل را بررسی کنید
2. فایل `test_import_fix.py` را اجرا کنید
3. با تیم توسعه تماس بگیرید

## 📄 مستندات مرتبط

- [README.md](README.md) - راهنمای اصلی پروژه
- [README_BRANCHES.md](README_BRANCHES.md) - سیستم انتخاب شعب
- [CHANGES.md](CHANGES.md) - تغییرات اخیر

## ✨ خلاصه

این رفع خطا باعث می‌شود:
- ✅ سیستم انتخاب شعبه به درستی کار کند
- ✅ کاربران بتوانند از لیست کامل شعب قضایی استفاده کنند
- ✅ تجربه کاربری بهبود یابد
- ✅ خطاهای import برطرف شوند

---

**نسخه:** 2.0.1  
**تاریخ رفع خطا:** امروز  
**وضعیت:** ✅ تایید شده و آماده استفاده
