# راهنمای نصب و راه‌اندازی OCR

## مشکل: OCR کار نمی‌کند

اگر سیستم OCR کار نمی‌کند، به ترتیب مراحل زیر را انجام دهید:

---

## مرحله 1: نصب Tesseract OCR

### ویندوز

1. **دانلود نصب‌کننده:**
   - از [این لینک](https://github.com/UB-Mannheim/tesseract/wiki) آخرین نسخه را دانلود کنید
   - فایل معمولا: `tesseract-ocr-w64-setup-v5.x.x.exe`

2. **نصب:**
   - نصب‌کننده را اجرا کنید
   - **مهم:** در مرحله انتخاب زبان‌ها، حتما **Persian (Farsi)** را انتخاب کنید
   - مسیر پیشنهادی: `C:\Program Files\Tesseract-OCR`

3. **افزودن به PATH:**
   - کلید Windows را فشار دهید و "Environment Variables" تایپ کنید
   - روی "Edit the system environment variables" کلیک کنید
   - دکمه "Environment Variables" را بزنید
   - در قسمت "System variables" متغیر `Path` را پیدا کنید و Edit کنید
   - New بزنید و مسیر زیر را اضافه کنید:
     ```
     C:\Program Files\Tesseract-OCR
     ```
   - OK بزنید و تمام پنجره‌ها را ببندید

4. **تست:**
   - یک Command Prompt جدید باز کنید
   ```cmd
   tesseract --version
   ```
   - باید نسخه Tesseract را نمایش دهد

### لینوکس (Ubuntu/Debian)

```bash
# نصب Tesseract و زبان فارسی
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-fas tesseract-ocr-eng

# تست
tesseract --version
tesseract --list-langs
```

باید `fas` و `eng` در لیست زبان‌ها باشد.

### macOS

```bash
# نصب با Homebrew
brew install tesseract
brew install tesseract-lang

# تست
tesseract --version
tesseract --list-langs
```

---

## مرحله 2: نصب کتابخانه‌های Python

### نصب وابستگی‌های OCR

```bash
# فعال کردن virtual environment (اگر دارید)
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# نصب کتابخانه‌های OCR
pip install Pillow==10.4.0
pip install pytesseract==0.3.13
pip install opencv-python==4.10.0.84

# یا نصب از requirements.txt
pip install -r requirements.txt
```

### تست کتابخانه‌ها

```python
python -c "from PIL import Image; print('✅ PIL OK')"
python -c "import pytesseract; print('✅ pytesseract OK')"
python -c "import cv2; print('✅ OpenCV OK')"
```

---

## مرحله 3: تست OCR با تصویر نمونه

### ایجاد اسکریپت تست

فایل `test_ocr.py` بسازید:

```python
from ocr import verify_payment_receipt
import logging

logging.basicConfig(level=logging.INFO)

# تست با یک تصویر فیش
result, message = verify_payment_receipt(
    photo_path='lavayeh_img_509108833_0.jpg',  # مسیر تصویر شما
    expected_amount=50000,  # مبلغ به تومان
    card_number='6037991234567890'  # شماره کارت
)

print("\n" + "="*60)
print("نتیجه:", "✅ تایید شد" if result else "❌ رد شد")
print("="*60)
print(message)
print("="*60)
```

### اجرای تست

```bash
python test_ocr.py
```

---

## مرحله 4: عیب‌یابی مشکلات رایج

### خطا: `TesseractNotFoundError`

**مشکل:** Python نمی‌تواند Tesseract را پیدا کند.

**راه‌حل:**

1. **ویندوز:** مسیر Tesseract را به صورت دستی تنظیم کنید:

```python
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

2. یا در فایل `ocr.py` مسیر را به‌روز کنید (قبلا اضافه شده است)

### خطا: `TesseractError: (1, 'Error opening data file...')`

**مشکل:** فایل‌های زبان فارسی نصب نیست.

**راه‌حل:**

1. **ویندوز:** Tesseract را دوباره نصب کنید و Persian را انتخاب کنید

2. **لینوکس:**
```bash
sudo apt-get install tesseract-ocr-fas
```

3. **دانلود دستی:**
   - از [اینجا](https://github.com/tesseract-ocr/tessdata) فایل `fas.traineddata` را دانلود کنید
   - در پوشه `tessdata` قرار دهید:
     - Windows: `C:\Program Files\Tesseract-OCR\tessdata\`
     - Linux: `/usr/share/tesseract-ocr/4.00/tessdata/`
     - Mac: `/usr/local/share/tessdata/`

### خطا: `ModuleNotFoundError: No module named 'cv2'`

**مشکل:** OpenCV نصب نیست.

**راه‌حل:**
```bash
pip install opencv-python
```

### OCR متن را نمی‌خواند یا اشتباه می‌خواند

**راه‌حل‌ها:**

1. **کیفیت تصویر:**
   - تصویر باید حداقل 300 DPI باشد
   - تصویر باید واضح و بدون blur باشد
   - نور کافی داشته باشد (نه خیلی تاریک، نه خیلی روشن)

2. **فرمت تصویر:**
   - فرمت‌های پیشنهادی: PNG یا JPG
   - از فشرده‌سازی زیاد خودداری کنید

3. **تنظیمات OCR:**
   - در فایل `ocr.py` می‌توانید PSM mode را تغییر دهید:
   ```python
   text = pytesseract.image_to_string(img, lang='fas+eng', config='--psm 6')
   ```
   - PSM modes:
     - `3`: Fully automatic page segmentation (پیش‌فرض)
     - `6`: Uniform block of text
     - `11`: Sparse text
     - `12`: Sparse text with OSD

4. **پیش‌پردازش:**
   - کد فعلی از OpenCV برای پیش‌پردازش استفاده می‌کند
   - اگر OpenCV نصب است، تصویر به صورت خودکار بهینه می‌شود

---

## مرحله 5: بررسی Log ها

زمان اجرای ربات، لاگ‌های دقیق OCR نمایش داده می‌شود:

```
✅ PIL و Pytesseract با موفقیت بارگذاری شد!
✅ OpenCV با موفقیت بارگذاری شد!
✅ Tesseract پیدا شد: C:\Program Files\Tesseract-OCR\tesseract.exe
✅ پیش‌پردازش OpenCV انجام شد: photo_processed.jpg
📝 OCR (fas+eng):
رسید انتقال وجه
مبلغ: 50000 تومان
...
🔢 اعداد یافت شده: [50000, 6037, 1234]
✅ مبلغ دقیق یافت شد: 50000
✅ 4 رقم آخر کارت یافت شد: 7890
📊 امتیاز نهایی: 95/100
```

اگر این لاگ‌ها را نمی‌بینید:
- سطح logging را به INFO یا DEBUG تنظیم کنید
- مطمئن شوید که فایل `ocr.py` جدید استفاده می‌شود

---

## مرحله 6: تنظیمات پیشرفته

### کاهش حساسیت (برای فیش‌های ضعیف)

در فایل `ocr.py` خط 269، threshold امتیاز را کاهش دهید:

```python
# از 70 به 60
if score >= 60:
    return True, detail
```

### افزایش دقت (برای فیش‌های حرفه‌ای)

در فایل `ocr.py` خط 269، threshold امتیاز را افزایش دهید:

```python
# از 70 به 80
if score >= 80:
    return True, detail
```

### غیرفعال کردن OpenCV (در صورت مشکل)

در فایل `ocr.py` خط 16:

```python
HAS_OPENCV = False  # به صورت دستی غیرفعال شود
```

---

## تست نهایی

پس از انجام تمام مراحل بالا:

```bash
# تست OCR
python test_ocr.py

# اجرای ربات
python bot.py
```

در ربات:
1. یک فرآیند پرداخت را شروع کنید
2. تصویر فیش را ارسال کنید
3. باید پیام تایید خودکار دریافت کنید

---

## پشتیبانی

اگر همچنان مشکل دارید:

1. خروجی این دستور را بفرستید:
```bash
tesseract --version
tesseract --list-langs
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

2. لاگ کامل ربات را ذخیره کنید:
```bash
python bot.py > bot_log.txt 2>&1
```

3. یک تصویر نمونه از فیش را تست کنید و نتیجه را بررسی کنید

---

## نکات مهم

- ✅ **Tesseract** باید حتما نصب باشد (بدون این OCR کار نمی‌کند)
- ✅ **زبان فارسی** باید در Tesseract نصب باشد
- ✅ **OpenCV** اختیاری است ولی دقت را 30-40% بهبود می‌دهد
- ✅ **کیفیت تصویر** مهم‌ترین فاکتور است
- ✅ سیستم به صورت هوشمند چندین روش OCR را امتحان می‌کند
- ✅ حتی اگر OCR غیرفعال باشد، ربات کار می‌کند (با تایید دستی ادمین)

---

**موفق باشید! 🚀**
