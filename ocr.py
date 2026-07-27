"""
تایید خودکار فیش پرداخت با OCR چند لایه (Tesseract + OpenCV)
این ماژول از چندین تکنیک پیش‌پردازش تصویر برای افزایش دقت OCR استفاده می‌کند.
"""
import logging
import re
import os

# ================= کتابخانه‌های اختیاری OCR فیش پرداخت =================
HAS_OCR = False
HAS_OPENCV = False

try:
    from PIL import Image, ImageEnhance, ImageFilter
    import pytesseract
    HAS_OCR = True
    logging.info("✅ PIL و Pytesseract با موفقیت بارگذاری شد!")
except ImportError as e:
    logging.warning(f"⚠️ خطا در بارگذاری PIL/Pytesseract: {e}")

try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
    logging.info("✅ OpenCV با موفقیت بارگذاری شد!")
except ImportError:
    logging.warning("⚠️ OpenCV یافت نشد. از پیش‌پردازش ساده استفاده می‌شود.")

# تلاش برای یافتن مسیر Tesseract در ویندوز
if os.name == 'nt':
    possible_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'C:\Users\Administrator\AppData\Local\Programs\Tesseract-OCR\tesseract.exe',
    ]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = path
                logging.info(f"✅ Tesseract پیدا شد: {path}")
                break
            except:
                pass


def preprocess_image_opencv(image_path):
    """
    پیش‌پردازش پیشرفته تصویر با OpenCV برای بهبود دقت OCR
    شامل: تبدیل به خاکستری، اعمال فیلتر، threshold، و شارپنینگ
    """
    if not HAS_OPENCV:
        return None
    
    try:
        # خواندن تصویر
        img = cv2.imread(image_path)
        if img is None:
            logging.error(f"❌ نمی‌توان تصویر را خواند: {image_path}")
            return None
        
        # تبدیل به خاکستری
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # اعمال فیلتر برای کاهش نویز
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        
        # افزایش کنتراست با CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        
        # اعمال Threshold برای تبدیل به سیاه و سفید
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # شارپنینگ برای وضوح بیشتر
        kernel = np.array([[-1, -1, -1],
                          [-1,  9, -1],
                          [-1, -1, -1]])
        sharpened = cv2.filter2D(binary, -1, kernel)
        
        # ذخیره موقت
        temp_path = image_path.replace('.jpg', '_processed.jpg').replace('.png', '_processed.png')
        cv2.imwrite(temp_path, sharpened)
        
        logging.info(f"✅ پیش‌پردازش OpenCV انجام شد: {temp_path}")
        return temp_path
        
    except Exception as e:
        logging.error(f"❌ خطا در پیش‌پردازش OpenCV: {e}")
        return None


def preprocess_image_pil(image_path):
    """
    پیش‌پردازش ساده با PIL (زمانی که OpenCV موجود نیست)
    """
    try:
        img = Image.open(image_path)
        
        # تبدیل به خاکستری
        img = img.convert('L')
        
        # افزایش کنتراست
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        
        # افزایش وضوح
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(2.0)
        
        # اعمال فیلتر
        img = img.filter(ImageFilter.SHARPEN)
        
        # ذخیره موقت
        temp_path = image_path.replace('.jpg', '_processed.jpg').replace('.png', '_processed.png')
        img.save(temp_path)
        
        logging.info(f"✅ پیش‌پردازش PIL انجام شد: {temp_path}")
        return temp_path
        
    except Exception as e:
        logging.error(f"❌ خطا در پیش‌پردازش PIL: {e}")
        return image_path


def normalize_persian_text(text):
    """
    نرمال‌سازی متن فارسی: تبدیل اعداد فارسی/عربی به انگلیسی و حذف کاراکترهای اضافی
    """
    # اعداد فارسی و عربی
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    arabic_digits = '٠١٢٣٤٥٦٧٨٩'
    english_digits = '0123456789'
    
    # ایجاد جدول ترجمه
    translation_table = str.maketrans(
        persian_digits + arabic_digits,
        english_digits + english_digits
    )
    
    # اعمال ترجمه
    normalized = text.translate(translation_table)
    
    # حذف کاراکترهای اضافی
    normalized = normalized.replace(" ", "").replace(",", "").replace("/", "")
    normalized = normalized.replace("\n", " ").replace("\r", "").replace("\t", " ")
    normalized = normalized.replace("\u200c", "").replace("\u200f", "").replace("\u200e", "")
    normalized = normalized.replace("_", "").replace("-", "").replace(".", "")
    
    return normalized


def extract_numbers(text):
    """
    استخراج تمام اعداد از متن (حتی اعداد با جداکننده)
    """
    # حذف کاراکترهای غیر عددی به جز اعداد
    normalized = normalize_persian_text(text)
    
    # یافتن تمام اعداد
    numbers = re.findall(r'\d+', normalized)
    
    return [int(n) for n in numbers if len(n) >= 3]  # فقط اعداد 3 رقمی یا بیشتر


def verify_payment_receipt(photo_path, expected_amount, card_number):
    """
    بررسی هوشمند و چند لایه تصویر فیش واریزی
    
    Args:
        photo_path: مسیر فایل تصویر
        expected_amount: مبلغ مورد انتظار به تومان
        card_number: شماره کارت مقصد
    
    Returns:
        (bool, str): وضعیت تایید و پیام توضیحات
    """
    if not HAS_OCR:
        logging.warning("❌ OCR engine غیرفعال است - کتابخانه‌های لازم نصب نیستند")
        return False, "⚠️ سیستم تایید خودکار غیرفعال است. فیش شما برای تایید دستی ارسال می‌شود."
    
    try:
        # مرحله 1: پیش‌پردازش تصویر
        processed_path = None
        if HAS_OPENCV:
            processed_path = preprocess_image_opencv(photo_path)
        
        if not processed_path:
            processed_path = preprocess_image_pil(photo_path)
        
        # مرحله 2: OCR با زبان‌های مختلف
        texts = []
        
        # تلاش 1: فارسی + انگلیسی
        try:
            img = Image.open(processed_path or photo_path)
            text_fas_eng = pytesseract.image_to_string(img, lang='fas+eng')
            texts.append(text_fas_eng)
            logging.info(f"📝 OCR (fas+eng):\n{text_fas_eng[:200]}")
        except Exception as e:
            logging.warning(f"⚠️ OCR با fas+eng ناموفق: {e}")
        
        # تلاش 2: فقط فارسی
        try:
            img = Image.open(processed_path or photo_path)
            text_fas = pytesseract.image_to_string(img, lang='fas')
            texts.append(text_fas)
            logging.info(f"📝 OCR (fas):\n{text_fas[:200]}")
        except Exception as e:
            logging.warning(f"⚠️ OCR با fas ناموفق: {e}")
        
        # تلاش 3: فقط انگلیسی
        try:
            img = Image.open(processed_path or photo_path)
            text_eng = pytesseract.image_to_string(img, lang='eng')
            texts.append(text_eng)
            logging.info(f"📝 OCR (eng):\n{text_eng[:200]}")
        except Exception as e:
            logging.warning(f"⚠️ OCR با eng ناموفق: {e}")
        
        if not texts:
            return False, "❌ خطا در خواندن تصویر. لطفا تصویر واضح‌تری ارسال کنید."
        
        # ترکیب تمام متن‌ها
        combined_text = " ".join(texts)
        normalized_text = normalize_persian_text(combined_text).lower()
        
        logging.info(f"📊 متن نرمال شده ({len(normalized_text)} کاراکتر): {normalized_text[:300]}")
        
        # مرحله 3: استخراج اعداد
        all_numbers = extract_numbers(combined_text)
        logging.info(f"🔢 اعداد یافت شده: {all_numbers}")
        
        # مرحله 4: بررسی مبلغ
        # تومان
        expected_toman = expected_amount
        # ریال (تومان × 10)
        expected_rial = expected_amount * 10
        
        has_amount = False
        found_amount = None
        
        # بررسی مبلغ در لیست اعداد
        for num in all_numbers:
            # بررسی دقیق
            if num == expected_toman or num == expected_rial:
                has_amount = True
                found_amount = num
                logging.info(f"✅ مبلغ دقیق یافت شد: {num}")
                break
            
            # بررسی تقریبی (±5%)
            if expected_toman > 0:
                diff_percent_toman = abs(num - expected_toman) / expected_toman * 100
                diff_percent_rial = abs(num - expected_rial) / expected_rial * 100
                
                if diff_percent_toman <= 5 or diff_percent_rial <= 5:
                    has_amount = True
                    found_amount = num
                    logging.info(f"✅ مبلغ تقریبی یافت شد: {num} (انتظار: {expected_toman} تومان یا {expected_rial} ریال)")
                    break
        
        # بررسی مبلغ در متن (برای اعداد با جداکننده)
        if not has_amount:
            # حذف تمام کاراکترهای غیر عددی و جستجو
            clean_text = re.sub(r'[^\d]', '', normalized_text)
            
            if str(expected_toman) in clean_text or str(expected_rial) in clean_text:
                has_amount = True
                found_amount = expected_toman
                logging.info(f"✅ مبلغ در متن پیوسته یافت شد")
        
        # مرحله 5: بررسی شماره کارت
        has_card = False
        last_4_card = card_number[-4:] if card_number else ""
        last_6_card = card_number[-6:] if card_number and len(card_number) >= 6 else ""
        
        if last_4_card and (last_4_card in normalized_text or last_4_card in str(all_numbers)):
            has_card = True
            logging.info(f"✅ 4 رقم آخر کارت یافت شد: {last_4_card}")
        elif last_6_card and (last_6_card in normalized_text):
            has_card = True
            logging.info(f"✅ 6 رقم آخر کارت یافت شد: {last_6_card}")
        
        # مرحله 6: بررسی کلمات کلیدی
        keywords_payment = [
            "رسید", "انتقال", "موفق", "پیگیری", "ارجاع", "شناسه", 
            "عملیات", "بانک", "واریز", "کارت", "شماره", "سند",
            "پایا", "ساتنا", "مبلغ", "تراکنش", "پرداخت", "successful"
        ]
        
        keyword_matches = [kw for kw in keywords_payment if kw in normalized_text or kw in combined_text.lower()]
        keyword_count = len(keyword_matches)
        
        logging.info(f"🔑 کلمات کلیدی یافت شده ({keyword_count}): {keyword_matches}")
        
        # مرحله 7: تصمیم‌گیری نهایی
        score = 0
        reasons = []
        
        if has_amount:
            score += 60
            reasons.append(f"✓ مبلغ صحیح ({found_amount})")
        
        if has_card:
            score += 25
            reasons.append(f"✓ شماره کارت")
        
        if keyword_count >= 3:
            score += 15
            reasons.append(f"✓ {keyword_count} کلمه کلیدی")
        elif keyword_count >= 1:
            score += 10
            reasons.append(f"✓ {keyword_count} کلمه کلیدی")
        
        logging.info(f"📊 امتیاز نهایی: {score}/100")
        logging.info(f"📋 دلایل: {', '.join(reasons)}")
        
        # حداقل امتیاز برای تایید: 70
        if score >= 70:
            detail = f"✅ رسید پرداخت تایید شد!\n\n📊 امتیاز: {score}/100\n📝 {', '.join(reasons)}"
            return True, detail
        
        # اگر مبلغ درست است ولی امتیاز کم است
        if has_amount and score >= 60:
            detail = f"✅ رسید پرداخت تایید شد (بر اساس مبلغ)\n\n⚠️ امتیاز: {score}/100\n📝 {', '.join(reasons)}\n\nتوجه: برخی جزئیات تشخیص داده نشد ولی مبلغ صحیح است."
            return True, detail
        
        # رد شدن
        missing = []
        if not has_amount:
            missing.append("❌ مبلغ صحیح")
        if not has_card:
            missing.append("⚠️ شماره کارت")
        if keyword_count < 1:
            missing.append("⚠️ کلمات کلیدی رسید")
        
        detail = f"❌ رسید تایید نشد\n\n📊 امتیاز: {score}/100\n\nموارد یافت نشده:\n" + "\n".join(missing)
        detail += f"\n\n💡 انتظار: {expected_toman:,} تومان"
        detail += f"\n🔢 اعداد یافت شده: {', '.join([f'{n:,}' for n in all_numbers[:10]])}"
        
        return False, detail
        
    except Exception as ocr_err:
        logging.error(f"❌ خطای کلی در OCR: {ocr_err}", exc_info=True)
        return False, f"❌ خطا در پردازش تصویر: {str(ocr_err)}\n\nلطفا تصویر واضح‌تری ارسال کنید یا با ادمین تماس بگیرید."
