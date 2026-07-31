"""
هندلرهای بخش «ابزار فایل» — گزینه‌ی مستقل در منوی اصلی.
شامل دو ابزار:
  ۱) کاهش حجم عکس (فشرده‌سازی هوشمند تا رسیدن به حجم هدف)
  ۲) تبدیل فایل PDF چندصفحه‌ای به یک عکس بلند (اسکرول عمودی، همه صفحات پشت‌سرهم)
"""
import io
import logging
import os

from aiogram import Bot, F, Router
from aiogram.types import Message, FSInputFile, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from PIL import Image

from states import Form
from keyboards import flow_type_kb, file_tools_menu_kb, file_tools_back_kb

file_tools_router = Router()

# حداکثر تعداد صفحات مجاز برای تبدیل PDF (برای جلوگیری از فایل‌های خیلی حجیم/کند)
MAX_PDF_PAGES = 40
# حجم هدف برای فشرده‌سازی عکس (کیلوبایت)
TARGET_IMAGE_KB = 500


async def file_tools_entry(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🛠 **ابزار فایل**\n\n"
        "لطفاً یکی از ابزارهای زیر را انتخاب فرمایید:\n\n"
        "🖼 **کاهش حجم عکس** — عکس را ارسال کنید تا حجم آن کاهش یابد.\n"
        "📄➡️🖼 **تبدیل PDF به عکس** — فایل PDF چندصفحه‌ای را ارسال کنید تا تمام صفحات آن به صورت یک عکس بلند (پشت‌سرهم) تبدیل شود.",
        reply_markup=file_tools_menu_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.file_tools_menu)


@file_tools_router.message(Form.file_tools_menu)
async def file_tools_menu_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "🖼 کاهش حجم عکس":
        await message.answer(
            "🖼 لطفاً عکس مورد نظر را ارسال فرمایید (به صورت Photo یا فایل تصویری):",
            reply_markup=file_tools_back_kb
        )
        await state.set_state(Form.file_tools_waiting_image)
        return

    if text == "📄➡️🖼 تبدیل PDF به عکس":
        await message.answer(
            "📄 لطفاً فایل PDF مورد نظر را ارسال فرمایید:",
            reply_markup=file_tools_back_kb
        )
        await state.set_state(Form.file_tools_waiting_pdf)
        return

    if text == "🔙 بازگشت به منوی اصلی":
        await state.clear()
        await message.answer("بازگشت به منوی اصلی.", reply_markup=flow_type_kb)
        await state.set_state(Form.waiting_for_flow_type)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های منو را انتخاب فرمایید:", reply_markup=file_tools_menu_kb)


def _compress_image(src_path: str, dst_path: str, target_kb: int = TARGET_IMAGE_KB) -> int:
    """
    عکس را با کاهش تدریجی کیفیت/ابعاد فشرده می‌کند تا حجم آن به حدود target_kb برسد.
    خروجی: حجم نهایی فایل به بایت.
    """
    img = Image.open(src_path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    quality = 90
    scale = 1.0
    target_bytes = target_kb * 1024

    while True:
        w, h = img.size
        resized = img
        if scale < 1.0:
            resized = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=quality, optimize=True)
        size = buf.tell()

        if size <= target_bytes or (quality <= 30 and scale <= 0.3):
            with open(dst_path, "wb") as f:
                f.write(buf.getvalue())
            return size

        if quality > 30:
            quality -= 10
        else:
            scale -= 0.15


@file_tools_router.message(Form.file_tools_waiting_image, F.text == "🔙 بازگشت")
async def file_tools_image_back(message: Message, state: FSMContext):
    await message.answer("🛠 بازگشت به منوی ابزار فایل:", reply_markup=file_tools_menu_kb)
    await state.set_state(Form.file_tools_menu)


@file_tools_router.message(Form.file_tools_waiting_image, F.photo | F.document)
async def file_tools_receive_image(message: Message, state: FSMContext, bot: Bot):
    is_photo = bool(message.photo)
    if not is_photo and not (message.document and (message.document.mime_type or "").startswith("image/")):
        await message.answer("⚠️ لطفاً یک فایل تصویری (عکس) ارسال فرمایید.")
        return

    await message.answer("⏳ در حال دریافت و فشرده‌سازی عکس...")

    user_id = message.from_user.id
    file_id = message.photo[-1].file_id if is_photo else message.document.file_id
    src_path = f"filetools_src_{user_id}.jpg"
    dst_path = f"filetools_compressed_{user_id}.jpg"

    try:
        file_info = await bot.get_file(file_id)
        await bot.download_file(file_info.file_path, src_path)
        original_size = os.path.getsize(src_path)

        final_size = _compress_image(src_path, dst_path)

        if final_size >= original_size:
            # اگر فشرده‌سازی کمکی نکرد (عکس از قبل کوچک بود)، همان فایل اصلی برگردانده شود
            os.replace(src_path, dst_path)
            final_size = os.path.getsize(dst_path)

        doc = FSInputFile(dst_path)
        await message.answer_document(
            doc,
            caption=(
                f"✅ **کاهش حجم انجام شد.**\n\n"
                f"حجم اولیه: {original_size / 1024:.0f} کیلوبایت\n"
                f"حجم نهایی: {final_size / 1024:.0f} کیلوبایت"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"file_tools image compress error: {e}")
        await message.answer("❌ خطایی در پردازش عکس رخ داد. لطفاً دوباره تلاش کنید.")
    finally:
        for p in (src_path, dst_path):
            if os.path.exists(p):
                os.remove(p)

    await message.answer(
        "می‌توانید عکس دیگری ارسال کنید یا بازگردید:",
        reply_markup=file_tools_back_kb
    )


@file_tools_router.message(Form.file_tools_waiting_pdf, F.text == "🔙 بازگشت")
async def file_tools_pdf_back(message: Message, state: FSMContext):
    await message.answer("🛠 بازگشت به منوی ابزار فایل:", reply_markup=file_tools_menu_kb)
    await state.set_state(Form.file_tools_menu)


@file_tools_router.message(Form.file_tools_waiting_pdf, F.document)
async def file_tools_receive_pdf(message: Message, state: FSMContext, bot: Bot):
    mime = (message.document.mime_type or "")
    fname = (message.document.file_name or "")
    if mime != "application/pdf" and not fname.lower().endswith(".pdf"):
        await message.answer("⚠️ لطفاً فقط فایل با فرمت PDF ارسال فرمایید.")
        return

    await message.answer("⏳ در حال تبدیل فایل PDF به عکس... (بسته به تعداد صفحات ممکن است کمی طول بکشد)")

    import fitz  # PyMuPDF — تبدیل صفحات PDF به تصویر

    user_id = message.from_user.id
    pdf_path = f"filetools_src_{user_id}.pdf"
    img_path = f"filetools_pdf2img_{user_id}.jpg"

    try:
        file_info = await bot.get_file(message.document.file_id)
        await bot.download_file(file_info.file_path, pdf_path)

        pdf = fitz.open(pdf_path)
        page_count = pdf.page_count

        if page_count == 0:
            await message.answer("❌ فایل PDF ارسالی خالی یا نامعتبر است.")
            pdf.close()
            return

        if page_count > MAX_PDF_PAGES:
            await message.answer(
                f"⚠️ این فایل {page_count} صفحه دارد و بیشتر از حد مجاز ({MAX_PDF_PAGES} صفحه) است.\n"
                f"لطفاً فایل را به بخش‌های کوچک‌تر تقسیم و مجدداً ارسال کنید."
            )
            pdf.close()
            return

        # کیفیت رندر بر اساس تعداد صفحات تنظیم می‌شود تا فایل نهایی خیلی حجیم نشود
        zoom = 2.0 if page_count <= 10 else (1.5 if page_count <= 20 else 1.0)
        matrix = fitz.Matrix(zoom, zoom)

        page_images = []
        for i in range(page_count):
            pix = pdf.load_page(i).get_pixmap(matrix=matrix)
            mode = "RGB" if pix.n < 4 else "RGBA"
            page_img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            if mode == "RGBA":
                page_img = page_img.convert("RGB")
            page_images.append(page_img)
        pdf.close()

        max_width = max(im.width for im in page_images)
        total_height = sum(im.height for im in page_images)
        combined = Image.new("RGB", (max_width, total_height), color="white")

        y_offset = 0
        for im in page_images:
            x_offset = (max_width - im.width) // 2
            combined.paste(im, (x_offset, y_offset))
            y_offset += im.height

        combined.save(img_path, format="JPEG", quality=85, optimize=True)

        # اگر خیلی حجیم شد، فشرده‌سازی اضافه انجام شود
        if os.path.getsize(img_path) > 9 * 1024 * 1024:  # نزدیک به سقف تلگرام
            _compress_image(img_path, img_path, target_kb=8000)

        doc = FSInputFile(img_path)
        await message.answer_document(
            doc,
            caption=f"✅ تبدیل انجام شد. ({page_count} صفحه در یک عکس)"
        )
    except Exception as e:
        logging.error(f"file_tools pdf2image error: {e}")
        await message.answer("❌ خطایی در تبدیل فایل PDF رخ داد. لطفاً از سالم بودن فایل مطمئن شوید و دوباره تلاش کنید.")
    finally:
        for p in (pdf_path, img_path):
            if os.path.exists(p):
                os.remove(p)

    await message.answer(
        "می‌توانید فایل PDF دیگری ارسال کنید یا بازگردید:",
        reply_markup=file_tools_back_kb
    )


@file_tools_router.message(Form.file_tools_waiting_pdf)
async def file_tools_pdf_wrong_type(message: Message, state: FSMContext):
    await message.answer("⚠️ لطفاً فایل PDF را به صورت Document ارسال فرمایید.")
