"""تایید خودکار فیش پرداخت با OCR (Tesseract). تمام منطق مربوط به خواندن و اعتبارسنجی رسید فقط اینجاست."""
import logging

# ================= کتابخانه‌های اختیاری OCR فیش پرداخت =================
HAS_OCR = False
try:
    from PIL import Image
    import pytesseract
    HAS_OCR = True
    logging.info("✅ OCR engine loaded successfully!")
except ImportError:
    logging.warning("⚠️ کتابخانه pytesseract یا Pillow یافت نشد. رسیدها برای تایید دستی ادمین فرستاده می‌شوند.")

def verify_payment_receipt(photo_path, expected_amount, card_number):
    """بررسی هوشمند تصویر فیش واریزی با موتور آفلاین Tesseract OCR"""
    if not HAS_OCR:
        logging.warning("OCR engine is disabled. Directing to admin manual approval.")
        return False, "تایید خودکار به دلیل عدم بارگذاری ماژول OCR غیرفعال است."
        
    try:
        img = Image.open(photo_path)
        text = pytesseract.image_to_string(img, lang="fas+eng")
        logging.info(f"Raw OCR Extracted Text:\n{text}")
        
        p_digits = '۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩'
        e_digits = '01234567890123456789'
        trans = str.maketrans(p_digits, e_digits)
        normalized_text = (
            text.translate(trans)
            .replace(" ", "").replace(",", "").replace("/", "")
            .replace("\n", "").replace("\r", "").replace("\t", "")
            .replace("\u200c", "").replace("\u200f", "").replace("\u200e", "")
            .lower()
        )
        
        expected_rials = expected_amount * 10
        amount_str = str(expected_amount)
        rials_str = str(expected_rials)
        has_amount = amount_str in normalized_text or rials_str in normalized_text
        
        keywords = ["رسید", "انتقال", "موفق", "پیگیری", "ارجاع", "عملیات", "بانک", "واریز", "کارت", "شماره", "سند", "پایا", "ساتنا", "مبلغ"]
        
        last_4_card = card_number[-4:]
        has_card = last_4_card in normalized_text
        
        keyword_count = sum(1 for kw in keywords if kw in normalized_text)
        logging.info(f"Verification Metrics: has_amount={has_amount}, keyword_count={keyword_count}, has_card={has_card}")
        
        if has_amount and (has_card or keyword_count >= 1):
            return True, "✅ رسید پرداخت شما با موفقیت توسط سیستم هوشمند تایید شد."
            
        return False, "❌ متاسفانه مبلغ یا مشخصات فیش ارسال‌شده به‌طور کامل تایید نشد."
        
    except Exception as ocr_err:
        logging.error(f"Error in OCR receipt verification: {ocr_err}")
        return False, "❌ خطا در پردازش تصویر فیش پرداخت. تصویر ناخوانا است."
