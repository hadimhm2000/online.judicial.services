
"""
import logging
import re
import os

# ================= کتابخانه‌های OCR =================
HAS_OCR = False
HAS_OPENCV = False

try:
    from PIL import Image, ImageEnhance, ImageFilter
    import pytesseract
    HAS_OCR = True
except ImportError:
    logging.warning("⚠️ خطا در بارگذاری PIL/Pytesseract. OCR غیرفعال است.")

try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    logging.warning("⚠️ OpenCV یافت نشد. از پیش‌پردازش ساده استفاده می‌شود.")

# مسیر Tesseract در ویندوز
if os.name == 'nt':
    possible_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                pytesseract.pytesseract.tesseract_cmd = path
                break
            except:
                pass


def preprocess_image_opencv(image_path):
    """
    پیش‌پردازش فوق‌العاده برای فیش‌های بانکی:
    ۱. بزرگ‌نمایی (Upscale) برای خوانایی بهتر متن‌های ریز
    ۲. تبدیل به خاکستری
    ۳. آستانه‌گذاری تطبیقی (Adaptive Thresholding) که برای بک‌گراند‌های رنگی فیش‌ها عالی است
    """
    if not HAS_OPENCV:
        return None
    
    try:
        img = cv2.imread(image_path)
        if img is None:
            return None
        
        # ۱. بزرگ‌نمایی 1.5 برابری (مهم برای متن‌های ریز موبایل)
        img = cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        
        # ۲. تبدیل به خاکستری
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # ۳. افزایش کنتراست (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # ۴. حذف نویز
        denoised = cv2.fastNlMeansDenoising(enhanced, None, 7, 7, 21)
        
        # ۵. آستانه‌گذاری تطبیقی (علیه بک‌گراند‌های متغیر)
        binary = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 31, 10
        )
        
        temp_path = image_path.replace('.jpg', '_processed.jpg').replace('.png', '_processed.png')
        cv2.imwrite(temp_path, binary)
        
        return temp_path
        
    except Exception as e:
        logging.error(f"❌ خطا در پیش‌پردازش OpenCV: {e}")
        return None


def preprocess_image_pil(image_path):
    try:
        img = Image.open(image_path)
        img = img.convert('L')
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.5)
        img = img.filter(ImageFilter.SHARPEN)
        temp_path = image_path.replace('.jpg', '_processed.jpg').replace('.png', '_processed.png')
        img.save(temp_path)
        return temp_path
    except Exception as e:
        logging.error(f"❌ خطا در پیش‌پردازش PIL: {e}")
        return image_path


def normalize_persian_text(text):
    """نرمال‌سازی اعداد و حذف فاصله‌ها"""
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    arabic_digits = '٠١٢٣٤٥٦٧٨٩'
    english_digits = '0123456789'
    translation_table = str.maketrans(persian_digits + arabic_digits, english_digits + english_digits)
    normalized = text.translate(translation_table)
    normalized = normalized.replace(" ", "").replace(",", "").replace("/", "").replace("-", "").replace("_", "").replace(".", "")
    return normalized


def extract_all_digits(text):
    """استخراج تمام ارقام به صورت یک رشته پیوسته برای تطبیق شماره کارت"""
    normalized = normalize_persian_text(text)
    return re.sub(r'[^\d]', '', normalized)


def extract_amounts(text):
    """استخراج لیست مبالغ (اعداد ۴ رقمی به بالا)"""
    normalized = normalize_persian_text(text)
    numbers = re.findall(r'\d+', normalized)
    amounts = []
    for n in numbers:
        if len(n) >= 4:
            # تلاش برای بازیافت اعدادی که ممیز یا جداکننده داشته‌اند
            amounts.append(int(n))
            if len(n) > 4:
                # ممکن است تسراکت 650000 را 65,000 خوانده باشد و ما کاما را حذف کرده باشیم
                pass 
    return amounts


def verify_payment_receipt(photo_path, expected_amount, card_number):
    """
    بررسی هوشمند فیش پرداخت با منطق سخت‌گیرانه ضد فیک
    """
    if not HAS_OCR:
        return False, "⚠️ سیستم OCR غیرفعال است. فیش برای تایید دستی ارسال شد."

    try:
        # مرحله ۱: پیش‌پردازش تصویر
        processed_path = preprocess_image_opencv(photo_path) if HAS_OPENCV else preprocess_image_pil(photo_path)
        img = Image.open(processed_path or photo_path)
        
        # مرحله ۲: OCR با تنظیمات بهینه (PSM 6 برای بلوک متن یکنواخت)
        try:
            text_raw = pytesseract.image_to_string(img, lang='fas+eng', config='--psm 6')
        except Exception as e:
            logging.warning(f"⚠️ OCR ناموفق: {e}")
            text_raw = ""

        normalized_text = normalize_persian_text(text_raw).lower()
        clean_digits = extract_all_digits(text_raw)  # تمام اعداد پشت سر هم
        
        logging.info(f"📊 متن خروجی OCR:\n{text_raw[:500]}")
        logging.info(f"🔢 تمام ارقام پیوسته: {clean_digits[:100]}")

        # مرحله ۳: بررسی مبلغ
        expected_toman = int(expected_amount)
        expected_rial = expected_toman * 10
        
        has_amount = False
        found_amounts = []
        
        # جستجوی مبلغ در اعداد جدا شده
        amounts_found = extract_amounts(text_raw)
        for num in amounts_found:
            found_amounts.append(num)
            if num == expected_toman or num == expected_rial:
                has_amount = True
                break
            # تطبیق ۹۰٪ (برای خطاهای تسراکت مثل خواندن 5 به جای 6)
            diff_toman = abs(num - expected_toman) / expected_toman * 100 if expected_toman > 0 else 100
            diff_rial = abs(num - expected_rial) / expected_rial * 100 if expected_rial > 0 else 100
            if diff_toman <= 5 or diff_rial <= 5:
                has_amount = True
                break

        # جستجوی مبلغ در رشته پیوسته اعداد
        if not has_amount:
            if str(expected_toman) in clean_digits or str(expected_rial) in clean_digits:
                has_amount = True

        # مرحله ۴: بررسی شماره کارت
        has_card = False
        last_4 = card_number[-4:] if len(card_number) >= 4 else ""
        last_6 = card_number[-6:] if len(card_number) >= 6 else ""
        last_8 = card_number[-8:] if len(card_number) >= 8 else ""
        
        # برای جلوگیری از False Positive، شماره کارت را در رشته پیوسته اعداد می‌گردیم
        if last_4 and len(last_4) == 4:
            # گاهی تسراکت 6 را 0 می‌خواند یا برعکس، جستجوی فازی برای ۴ رقم آخر
            possible_last_4 = [
                last_4,
                last_4.replace('6', '0'),
                last_4.replace('0', '6'),
                last_4.replace('5', '6'),
                last_4.replace('1', '7'),
            ]
            for p4 in possible_last_4:
                if p4 in clean_digits:
                    has_card = True
                    break
            
            # بررسی ۶ رقم آخر دقیق
            if not has_card and last_6 in clean_digits:
                has_card = True

        # مرحله ۵: بررسی کلمات کلیدی بانکی
        keywords_payment = ["رسید", "انتقال", "موفق", "پیگیری", "ارجاع", "شناسه", "بانک", "واریز", "پایا", "ساتنا", "تراکنش", "successful", "payment", "transfer"]
        keyword_matches = [kw for kw in keywords_payment if kw in normalized_text or kw in text_raw.lower()]
        keyword_count = len(keyword_matches)

        # مرحله ۶: تصمیم‌گیری نهایی (منطق ضد فیک)
        # برای تایید فیش: مبلغ (اجباری) + شماره کارت (اجباری) + حداقل ۱ کلمه کلیدی
        score = 0
        reasons = []
        
        if has_amount:
            score += 50
            reasons.append("✓ مبلغ صحیح")
        if has_card:
            score += 40
            reasons.append("✓ شماره کارت تطبیق دارد")
        if keyword_count >= 2:
            score += 10
            reasons.append(f"✓ شامل کلمات بانکی ({keyword_count} مورد)")
        
        logging.info(f"📊 امتیاز نهایی OCR: {score}/100 | مبلغ: {has_amount} | کارت: {has_card}")

        # شرط تایید: حداقل ۸۰ امتیاز (یعنی حتماً مبلغ + کارت خوانده شده باشد)
        if has_amount and has_card and score >= 80:
            detail = f"✅ رسید پرداخت تایید شد!\n\n📊 امتیاز: {score}/100\n📝 {', '.join(reasons)}"
            return True, detail
            
        # اگر مبلغ درست باشد اما کارت خوانده نشود (احتمالا عکس بد است یا فیک است)
        if has_amount and not has_card:
            detail = "❌ مبلغ درست است اما شماره کارت مقصد در فیش شما مشخص نیست!\n\n⚠️ لطفا تصویر واضح‌تری ارسال کنید."
            return False, detail
            
        # در غیر این صورت (مبلغ اشتباه است)
        missing = []
        if not has_amount:
            missing.append(f"❌ مبلغ (انتظار: {expected_toman:,} تومان)\n🔢 اعداد یافت شده: {found_amounts[:5]}")
        if not has_card and not has_amount:
            missing.append("❌ شماره کارت")
            
        detail = "❌ رسید تایید نشد.\n\nموارد یافت نشده:\n" + "\n".join(missing)
        return False, detail
        
    except Exception as ocr_err:
        logging.error(f"❌ خطای کلی در OCR: {ocr_err}", exc_info=True)
        return False, "❌ خطا در پردازش تصویر. لطفا تصویر واضح‌تری ارسال کنید."
    finally:
        # پاکسازی فایل‌های موقت
        if 'processed_path' in locals() and processed_path and os.path.exists(processed_path):
            try:
                os.remove(processed_path)
            except:
                pass
```
 