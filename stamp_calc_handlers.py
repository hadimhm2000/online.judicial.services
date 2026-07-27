"""
هندلرهای بخش محاسبه تمبر مالیاتی وکیل (مستقل از فلوی اعلام وکالت).

جریان:
  ۱. کاربر «محاسبه تمبر مالیاتی وکیل» را انتخاب می‌کند
  ۲. نوع دعوی را انتخاب می‌کند (مالی / غیر مالی)
  ۳. اگر مالی: مبلغ خواسته را وارد می‌کند
     → محاسبه تمبر
     → اعلام هزینه 200,000 ریال برای دریافت نتیجه
     → کاربر رسید می‌فرستد
     → نتیجه محاسبه ارسال می‌شود
     → اگر ۲ ساعت رسید نیامد، پاکسازی state
  ۴. اگر غیر مالی: اعلام مبلغ 200,000 ریال به ازای هر خواسته
     → بدون نیاز به پرداخت
"""
import asyncio
import datetime
import logging

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

import runtime_state
from config import ADMIN_ID, CARD_NUMBER, ACCOUNT_NAME
from states import Form
from keyboards import restart_kb, stamp_calc_claim_type_kb, continue_kb, back_only_kb
from stamp_duty import calculate_stamp_duty, format_result_fa

stamp_calc_router = Router()

_FA_AR = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789"
)

def _to_en(text: str) -> str:
    return text.translate(_FA_AR).replace(" ", "").strip()

def _fmt(n: int) -> str:
    return f"{n:,}"

STAMP_CALC_FEE = 200_000  # ریال — هزینه دریافت نتیجه محاسبه


# ══════════════════════════════════════════════════════════════════════════════
# ورود به بخش محاسبه تمبر
# ══════════════════════════════════════════════════════════════════════════════
@stamp_calc_router.message(StateFilter("*"), F.text == "🧮 محاسبه تمبر مالیاتی وکیل")
async def stamp_calc_entry(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🧮 **محاسبه تمبر مالیاتی وکیل**\n\n"
        "لطفاً گزینه‌های زیر را انتخاب کنید:",
        reply_markup=stamp_calc_claim_type_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.stamp_calc_claim_type)


# ══════════════════════════════════════════════════════════════════════════════
# انتخاب نوع دعوی
# ══════════════════════════════════════════════════════════════════════════════
@stamp_calc_router.message(Form.stamp_calc_claim_type)
async def stamp_calc_claim_type_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if "2️⃣" in text or "غیر مالی" in text:
        # دعوی غیر مالی — بدون پرداخت
        await message.answer(
            "📋 **تمبر دعوی غیر مالی:**\n\n"
            "مبلغ **200,000 ریال** به ازای هر خواسته می‌باشد.\n\n"
            "⚠️ نیازی به پرداخت هزینه نمی‌باشد.",
            reply_markup=restart_kb,
            parse_mode="Markdown"
        )
        await state.clear()
        return

    if "1️⃣" in text or "مالی" in text:
        await message.answer(
            "💵 لطفاً **مبلغ خواسته** را به **ریال** وارد فرمایید:\n_(فقط عدد)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.stamp_calc_claim_amount)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=stamp_calc_claim_type_kb)


# ══════════════════════════════════════════════════════════════════════════════
# دریافت مبلغ خواسته
# ══════════════════════════════════════════════════════════════════════════════
@stamp_calc_router.message(Form.stamp_calc_claim_amount)
async def stamp_calc_amount_handler(message: Message, state: FSMContext, bot: Bot):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer(
            "🧮 **محاسبه تمبر مالیاتی وکیل**\n\nلطفاً گزینه‌های زیر را انتخاب کنید:",
            reply_markup=stamp_calc_claim_type_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.stamp_calc_claim_type)
        return

    amount_str = _to_en(message.text)
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await message.answer("⚠️ لطفاً مبلغ را به **ریال** وارد کنید (فقط عدد):", parse_mode="Markdown")
        return

    claim_amount = int(amount_str)
    try:
        result = calculate_stamp_duty(claim_amount)
    except ValueError as e:
        await message.answer(f"⚠️ خطا در محاسبه: {e}")
        return

    # ذخیره نتیجه برای بعد از پرداخت
    await state.update_data(
        stamp_claim_amount=claim_amount,
        stamp_result=result,
        stamp_invoice_time=datetime.datetime.now().isoformat()
    )

    await message.answer(
        f"💰 **برای دریافت نتیجه محاسبه، هزینه زیر را پرداخت فرمایید:**\n\n"
        f"مبلغ: **{_fmt(STAMP_CALC_FEE)} ریال**\n\n"
        f"💳 شماره کارت: `{CARD_NUMBER}`\n"
        f"👤 بنام: **{ACCOUNT_NAME}**\n\n"
        f"👇 پس از واریز، **عکس فیش** را ارسال فرمایید.\n\n"
        f"⚠️ در صورت عدم پرداخت ظرف ۲ ساعت، درخواست لغو می‌شود.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.stamp_calc_waiting_payment)

    # تسک نظارت بر ۲ ساعت
    asyncio.create_task(_stamp_calc_timeout_watcher(bot, message.from_user.id, state))


# ══════════════════════════════════════════════════════════════════════════════
# دریافت رسید پرداخت
# ══════════════════════════════════════════════════════════════════════════════
@stamp_calc_router.message(Form.stamp_calc_waiting_payment, F.photo)
async def stamp_calc_payment_receipt(message: Message, state: FSMContext, bot: Bot):
    import os
    from ocr import verify_payment_receipt

    data = await state.get_data()
    claim_amount = data.get("stamp_claim_amount", 0)
    result = data.get("stamp_result", {})

    photo = message.photo[-1]
    photo_file = await bot.get_file(photo.file_id)
    photo_path = f"stamp_receipt_{message.from_user.id}_{int(datetime.datetime.now().timestamp())}.jpg"
    await bot.download_file(photo_file.file_path, photo_path)

    # STAMP_CALC_FEE به ریال است، اما verify_payment_receipt مبلغ را به تومان می‌گیرد
    # و خودش داخلش ضربدر ۱۰ می‌کند تا معادل ریالی را هم چک کند. بدون تبدیل زیر،
    # مقایسه همیشه با اعداد اشتباه انجام می‌شد و OCR هیچ‌وقت رسید را تایید نمی‌کرد.
    expected_amount_toman = STAMP_CALC_FEE // 10
    is_valid, ocr_msg = verify_payment_receipt(photo_path, expected_amount_toman, CARD_NUMBER)

    if is_valid:
        if os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass
        result_text = format_result_fa(claim_amount, result)
        await message.answer(
            f"✅ **پرداخت تایید شد.**\n\n{result_text}",
            reply_markup=restart_kb,
            parse_mode="Markdown"
        )
        await state.clear()
    else:
        # ارسال به ادمین برای تایید دستی — عکس رسید هم همراه پیام فرستاده می‌شود
        # تا ادمین واقعاً چیزی برای بررسی داشته باشد
        from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تایید",
                    callback_data=f"ok_stamp:{message.from_user.id}:{claim_amount}"
                ),
                InlineKeyboardButton(
                    text="❌ رد",
                    callback_data=f"no_stamp:{message.from_user.id}"
                )
            ]
        ])
        await state.update_data(stamp_photo_path=photo_path)
        admin_doc = FSInputFile(photo_path)
        await bot.send_photo(
            ADMIN_ID,
            photo=admin_doc,
            caption=(
                f"📥 **تایید دستی محاسبه تمبر:**\n\n"
                f"👤 کاربر: {message.from_user.full_name} (`{message.from_user.id}`)\n"
                f"مبلغ خواسته: {_fmt(claim_amount)} ریال\n"
                f"هزینه: {_fmt(STAMP_CALC_FEE)} ریال\n\n"
                f"موتور OCR تایید نکرد."
            ),
            reply_markup=inline_kb,
            parse_mode="Markdown"
        )
        await message.answer(
            "⏳ رسید برای بررسی دستی به مدیریت ارسال شد. نتیجه به زودی اعلام می‌شود."
        )


@stamp_calc_router.message(Form.stamp_calc_waiting_payment)
async def stamp_calc_waiting_text(message: Message):
    await message.answer("⚠️ لطفاً **عکس فیش واریزی** را ارسال فرمایید.", parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════════════════════
# نظارت ۲ ساعته
# ══════════════════════════════════════════════════════════════════════════════
async def _stamp_calc_timeout_watcher(bot: Bot, user_id: int, state: FSMContext):
    """اگر ۲ ساعت گذشت و رسید نیامد، state را پاک می‌کند."""
    await asyncio.sleep(2 * 3600)

    try:
        current_state = await state.get_state()
        if current_state == Form.stamp_calc_waiting_payment:
            await state.clear()
            await bot.send_message(
                user_id,
                "⏰ **مهلت پرداخت پایان یافت.**\n\n"
                "درخواست محاسبه تمبر لغو شد. برای درخواست مجدد، «محاسبه تمبر مالیاتی وکیل» را انتخاب کنید.",
                reply_markup=restart_kb,
                parse_mode="Markdown"
            )
    except Exception as e:
        logging.error(f"[STAMP_CALC] خطا در watcher کاربر {user_id}: {e}")
