"""
هندلرهای بخش ثبت لایحه — فقط فلوی مکالمه تلگرام.
شامل پشتیبانی از عنوان «اعلام وکالت» با جریان خاص خود.
"""
import asyncio
import datetime
import logging
import os
import re

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

import runtime_state
from config import ADMIN_ID, CARD_NUMBER, ACCOUNT_NAME, calculate_lavayeh_fee, format_lavayeh_fee_explanation
from sheets import log_event
from ocr import verify_payment_receipt
from states import Form
from keyboards import (
    main_menu_kb, restart_kb, back_only_kb,
    lavayeh_title_kb, LAVAYEH_TITLES,
    lavayeh_tracking_method_kb,
    lavayeh_branch_input_method_kb,
    create_province_kb, PROVINCES,
    create_person_type_kb, representative_type_kb,
    add_or_finish_kb, lavayeh_confirm_kb, lavayeh_edit_kb,
    lavayeh_attachment_title_kb_first, lavayeh_attachment_title_kb,
    lavayeh_attachment_more_kb, lavayeh_cancel_reminder_kb,
    lavayeh_sign_ready_kb,
    # کیبوردهای اعلام وکالت
    ealam_more_lawyers_kb,
    ealam_more_contracts_kb,
    ealam_stamp_amount_kb,
    ealam_claim_type_kb,
    ealam_stamp_type_kb,
    continue_kb,
)
from stamp_duty import calculate_stamp_duty, format_result_fa

lavayeh_router = Router()

# ── include کردن روتر امضا ──────────────────────────────────────────────────
from lavayeh_sign_handlers import lavayeh_sign_router
lavayeh_router.include_router(lavayeh_sign_router)

# ── include کردن روتر شعب ──────────────────────────────────────────────────
from branches import branches_router
lavayeh_router.include_router(branches_router)

_FA_AR = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789"
)

def _to_en(text: str) -> str:
    return text.translate(_FA_AR).replace(" ", "").strip()

def _fmt(n: int) -> str:
    return f"{n:,}"


async def _maybe_return_to_preview(data: dict, message: Message, state: FSMContext) -> bool:
    if data.get("_is_editing"):
        await state.update_data(_is_editing=False)
        await _go_to_preview(message, state)
        return True
    return False


def validate_tracking_code(code: str):
    if not code.isdigit():
        return False, "⚠️ شماره پرونده باید فقط شامل عدد باشد."
    year_prefix = int(code[:4])
    if 1400 <= year_prefix <= 1407:
        if len(code) == 18:
            return True, code
        return False, (
            f"⚠️ شماره پرونده با سال **{year_prefix}** باید **۱۸ رقمی** باشد.\n"
            f"کد شما **{len(code)} رقمی** است. مجدداً وارد کنید:"
        )
    elif year_prefix <= 1399:
        if len(code) == 16:
            return True, code
        return False, (
            f"⚠️ شماره پرونده با سال **{year_prefix}** باید **۱۶ رقمی** باشد.\n"
            f"کد شما **{len(code)} رقمی** است. مجدداً وارد کنید:"
        )
    else:
        return False, "⚠️ شماره پرونده نامعتبر است. مجدداً وارد کنید:"


def validate_archive_number(archive_num: str):
    """
    اعتبارسنجی شماره بایگانی:
    - اگر دو رقم اول ۰۰ تا ۰۷ باشد → باید ۷ رقمی باشد
    - اگر دو رقم اول ۹۳ تا ۹۹ باشد → باید ۶ رقمی باشد
    """
    if not archive_num.isdigit():
        return False, "⚠️ شماره بایگانی باید فقط شامل عدد باشد."
    
    if len(archive_num) < 2:
        return False, "⚠️ شماره بایگانی نامعتبر است. حداقل ۲ رقم وارد کنید."
    
    first_two = int(archive_num[:2])
    
    # بررسی دو رقم اول ۰۰ تا ۰۷
    if 0 <= first_two <= 7:
        if len(archive_num) == 7:
            return True, archive_num
        return False, (
            f"⚠️ شماره بایگانی با دو رقم اول **{archive_num[:2]}** باید **۷ رقمی** باشد.\n"
            f"شماره شما **{len(archive_num)} رقمی** است. مجدداً وارد کنید:"
        )
    
    # بررسی دو رقم اول ۹۳ تا ۹۹
    elif 93 <= first_two <= 99:
        if len(archive_num) == 6:
            return True, archive_num
        return False, (
            f"⚠️ شماره بایگانی با دو رقم اول **{archive_num[:2]}** باید **۶ رقمی** باشد.\n"
            f"شماره شما **{len(archive_num)} رقمی** است. مجدداً وارد کنید:"
        )
    
    else:
        return False, (
            f"⚠️ دو رقم اول شماره بایگانی (**{archive_num[:2]}**) نامعتبر است.\n"
            "باید بین **۰۰ تا ۰۷** (۷ رقمی) یا **۹۳ تا ۹۹** (۶ رقمی) باشد."
        )


def build_preview(data: dict) -> str:
    # بررسی عنوان اعلام وکالت
    if data.get("lavayeh_title") == "اعلام وکالت":
        return _build_ealam_preview(data)

    persons = data.get("lavayeh_persons", [])
    persons_text = ""
    for i, p in enumerate(persons, 1):
        ptype = p.get("person_type", "")
        if ptype == "شخص حقوقی":
            rep = p.get("representative_type", "")
            company_id = p.get("company_id", "")
            nat_id = p.get("national_id", "")
            persons_text += (
                f"  {i}. شخص حقوقی | شناسه شرکت: `{company_id}` | "
                f"نوع نماینده: {rep} | کدملی: `{nat_id}`\n"
            )
        else:
            nat_id = p.get("national_id", "")
            persons_text += f"  {i}. {ptype} | کدملی: `{nat_id}`\n"

    attachments = data.get("lavayeh_attachments", [])
    attachments_text = ""
    total_images = 0
    for i, att in enumerate(attachments, 1):
        n = len(att.get("images", []))
        total_images += n
        attachments_text += f"  {i}. {att.get('title', 'مستندات')} — {n} تصویر\n"
    if not attachments_text:
        attachments_text = "  (بدون مدرک)\n"

    text_preview = data.get("lavayeh_text", "")
    if len(text_preview) > 200:
        text_preview = text_preview[:200] + "..."

    # بررسی اینکه کدام روش برای ثبت استفاده شده
    tracking_method = data.get("tracking_method", "case_number")
    
    if tracking_method == "archive_number":
        # نمایش اطلاعات برای شماره بایگانی
        archive_info = (
            f"🔢 شماره بایگانی: `{data.get('lavayeh_archive_number', '---')}`\n"
            f"🏛 نام شعبه: **{data.get('lavayeh_branch_name', '---')}**\n"
            f"🏙 استان: **{data.get('lavayeh_province', '---')}**\n\n"
        )
    else:
        # نمایش اطلاعات برای شماره پرونده
        archive_info = (
            f"🔢 شماره پرونده: `{data.get('lavayeh_tracking_code', '---')}`\n"
            f"🏙 استان: **{data.get('lavayeh_province', '---')}**\n"
            f"🔢 ردیف فرعی: **{data.get('lavayeh_row_number', '---')}**\n\n"
        )

    return (
        f"📋 **پیش‌نمایش لایحه شما:**\n\n"
        f"📌 عنوان: **{data.get('lavayeh_title', '---')}**\n"
        f"{archive_info}"
        f"👥 اشخاص ارائه‌دهنده ({len(persons)} نفر):\n{persons_text}\n"
        f"📄 شرح متن:\n{text_preview}\n\n"
        f"🖼 مدارک ({total_images} تصویر در {len(attachments)} عنوان):\n{attachments_text}\n"
        f"آیا اطلاعات فوق صحیح است؟"
    )


def _build_ealam_preview(data: dict) -> str:
    lawyers = data.get("ealam_lawyers", [])
    contracts = data.get("ealam_contracts", [])
    stamp_amount = data.get("ealam_stamp_amount", 0)
    stamp_type = data.get("ealam_stamp_type", "")
    lavayeh_text = data.get("lavayeh_text", "")
    attachments = data.get("lavayeh_attachments", [])

    lawyers_text = "\n".join([f"  {i+1}. `{l}`" for i, l in enumerate(lawyers)]) or "  (ندارد)"
    contracts_text = "\n".join([f"  {i+1}. `{c}`" for i, c in enumerate(contracts)]) or "  (ندارد)"

    if stamp_type == "بدون تمبر":
        stamp_text = "بدون نیاز به تمبر"
    elif stamp_amount > 0:
        stamp_text = f"{_fmt(stamp_amount)} ریال ({stamp_type})"
    else:
        stamp_text = "بدون تمبر"

    text_preview = lavayeh_text[:200] + "..." if len(lavayeh_text) > 200 else lavayeh_text

    att_text = ""
    total_imgs = 0
    for i, att in enumerate(attachments, 1):
        n = len(att.get("images", []))
        total_imgs += n
        att_text += f"  {i}. {att.get('title', 'مستندات')} — {n} تصویر\n"
    if not att_text:
        att_text = "  (بدون مدرک)\n"

    # بررسی اینکه کدام روش برای ثبت استفاده شده
    tracking_method = data.get("tracking_method", "case_number")
    
    if tracking_method == "archive_number":
        # نمایش اطلاعات برای شماره بایگانی
        case_info = (
            f"🔢 شماره بایگانی: `{data.get('lavayeh_archive_number', '---')}`\n"
            f"🏛 نام شعبه: **{data.get('lavayeh_branch_name', '---')}**\n"
            f"🏙 استان: **{data.get('lavayeh_province', '---')}**\n\n"
        )
    else:
        # نمایش اطلاعات برای شماره پرونده
        case_info = (
            f"🔢 شماره پرونده: `{data.get('lavayeh_tracking_code', '---')}`\n"
            f"🏙 استان: **{data.get('lavayeh_province', '---')}**\n"
            f"🔢 ردیف فرعی: **{data.get('lavayeh_row_number', '---')}**\n\n"
        )

    return (
        f"📋 **پیش‌نمایش اعلام وکالت:**\n\n"
        f"{case_info}"
        f"👤 وکیل(ها):\n{lawyers_text}\n\n"
        f"📑 شماره(های) قرارداد:\n{contracts_text}\n\n"
        f"💰 تمبر: **{stamp_text}**\n\n"
        f"📄 شرح متن:\n{text_preview}\n\n"
        f"🖼 مدارک ({total_imgs} تصویر):\n{att_text}\n"
        f"آیا اطلاعات فوق صحیح است؟"
    )


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱ — ورود به بخش لایحه
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(StateFilter("*"), F.text == "📝 ثبت لایحه")
async def lavayeh_entry(message: Message, state: FSMContext):
    user_id = message.from_user.id
    active = runtime_state.active_lavayeh_users if hasattr(runtime_state, "active_lavayeh_users") else set()
    if user_id in active:
        await message.answer(
            "⚠️ شما یک درخواست لایحه فعال دارید.\nلطفاً ابتدا درخواست جاری را تکمیل یا لغو کنید.",
            reply_markup=restart_kb
        )
        return

    await state.clear()
    await state.update_data(lavayeh_persons=[], lavayeh_attachments=[])
    await message.answer(
        "📝 **ثبت لایحه**\n\nلطفاً عنوان لایحه خود را انتخاب فرمایید:",
        reply_markup=lavayeh_title_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.lavayeh_title)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱ — انتخاب عنوان لایحه
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_title)
async def lavayeh_get_title(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "🔙 بازگشت به منوی اصلی":
        await state.clear()
        await message.answer("بازگشت به منوی اصلی.", reply_markup=main_menu_kb)
        return

    if text not in LAVAYEH_TITLES:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=lavayeh_title_kb)
        return

    system_title = "لایحه دفاعیه" if text == "سایر عناوین" else text
    await state.update_data(
        lavayeh_title=text,
        lavayeh_system_title=system_title,
        ealam_lawyers=[],
        ealam_contracts=[],
        ealam_stamp_amount=0,
        ealam_stamp_type="",
    )

    data = await state.get_data()
    if await _maybe_return_to_preview(data, message, state):
        return

    await message.answer(
        f"✅ عنوان «**{text}**» انتخاب شد.\n\n"
        "🔢 لطفاً روش ثبت شماره پرونده را انتخاب فرمایید:",
        reply_markup=lavayeh_tracking_method_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.lavayeh_tracking_method)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱.۵ — انتخاب روش: شماره پرونده یا شماره بایگانی
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_tracking_method)
async def lavayeh_get_tracking_method(message: Message, state: FSMContext):
    text = message.text or ""
    
    if text == "🔙 بازگشت":
        await message.answer("📝 لطفاً عنوان لایحه را دوباره انتخاب کنید:", reply_markup=lavayeh_title_kb)
        await state.set_state(Form.lavayeh_title)
        return
    
    if text == "1️⃣ شماره پرونده و ردیف فرعی":
        # مسیر فعلی - شماره پرونده
        await state.update_data(tracking_method="case_number")
        await message.answer(
            "🔢 لطفاً **شماره پرونده** را ارسال فرمایید:\n\n"
            "_(پرونده‌های ۱۴۰۰ تا ۱۴۰۷: ۱۸ رقمی | پرونده‌های ۱۳۹۹ و قبل‌تر: ۱۶ رقمی)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_tracking_code)
        return
    
    if text == "2️⃣ شعبه رسیدگی کننده و شماره بایگانی":
        # مسیر جدید - شماره بایگانی
        await state.update_data(tracking_method="archive_number")
        await message.answer(
            "🔢 لطفاً **شماره بایگانی** را ارسال فرمایید:\n\n"
            "📌 **توجه:**\n"
            "• اگر دو رقم اول شماره بایگانی **۰۰ تا ۰۷** است، باید **۷ رقمی** باشد\n"
            "• اگر دو رقم اول شماره بایگانی **۹۳ تا ۹۹** است، باید **۶ رقمی** باشد",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_archive_number)
        return
    
    await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=lavayeh_tracking_method_kb)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲.۱ — دریافت شماره بایگانی (مسیر جدید)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_archive_number)
async def lavayeh_get_archive_number(message: Message, state: FSMContext):
    if not message.text:
        return
    
    if message.text == "🔙 بازگشت":
        await message.answer("🔢 لطفاً روش ثبت شماره پرونده را دوباره انتخاب کنید:", reply_markup=lavayeh_tracking_method_kb)
        await state.set_state(Form.lavayeh_tracking_method)
        return
    
    archive_num = _to_en(message.text)
    valid, result = validate_archive_number(archive_num)
    
    if not valid:
        await message.answer(result, parse_mode="Markdown")
        return
    
    await state.update_data(lavayeh_archive_number=archive_num)
    
    # import کیبورد جدید
    from keyboards import lavayeh_branch_input_method_kb
    
    await message.answer(
        "✅ شماره بایگانی ثبت شد.\n\n"
        "🏛 لطفاً نحوه ورود **نام شعبه** را انتخاب کنید:",
        reply_markup=lavayeh_branch_input_method_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.lavayeh_branch_input_method)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲.۱.۵ — انتخاب نحوه ورود نام شعبه (مسیر جدید)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_branch_input_method)
async def lavayeh_get_branch_input_method(message: Message, state: FSMContext):
    text = message.text or ""
    
    if text == "🔙 بازگشت":
        await message.answer(
            "🔢 لطفاً شماره بایگانی را مجدداً ارسال فرمایید:",
            reply_markup=back_only_kb
        )
        await state.set_state(Form.lavayeh_archive_number)
        return
    
    from keyboards import lavayeh_branch_input_method_kb, back_only_kb
    from branches import UNITS_DATA, create_branches_keyboard, ROOT_NODES
    
    if text == "📝 وارد کردن نام شعبه":
        # ورود دستی نام شعبه
        await message.answer(
            "🏛 لطفاً **نام شعبه** خود را وارد کنید:\n\n"
            "مثال: شعبه ۱۰۱ دادگاه عمومی حقوقی تهران",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_branch_name)
        return
    
    elif text == "🔍 انتخاب از لیست شعب":
        # انتخاب از لیست
        if not UNITS_DATA:
            await message.answer(
                "⚠️ متأسفانه لیست شعب در دسترس نیست.\n"
                "لطفاً نام شعبه را به صورت دستی وارد کنید:",
                reply_markup=back_only_kb
            )
            await state.set_state(Form.lavayeh_branch_name)
            return
        
        await message.answer(
            "🏛 **انتخاب شعبه از لیست**\n\n"
            "لطفاً از لیست زیر مسیر خود را انتخاب کنید:",
            reply_markup=create_branches_keyboard(ROOT_NODES, page=0, parent_id=None),
            parse_mode="Markdown"
        )
        # state همچنان lavayeh_branch_name می‌ماند تا callback handler آن را بگیرد
        await state.set_state(Form.lavayeh_branch_name)
        return
    
    await message.answer(
        "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
        reply_markup=lavayeh_branch_input_method_kb
    )


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲.۲ — دریافت نام شعبه (مسیر جدید)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_branch_name)
async def lavayeh_get_branch_name(message: Message, state: FSMContext):
    text = message.text or ""
    
    if text == "🔙 بازگشت":
        from keyboards import lavayeh_branch_input_method_kb
        await message.answer(
            "🏛 لطفاً نحوه ورود نام شعبه را دوباره انتخاب کنید:",
            reply_markup=lavayeh_branch_input_method_kb
        )
        await state.set_state(Form.lavayeh_branch_input_method)
        return
    
    if not text.strip():
        await message.answer("⚠️ لطفاً نام شعبه را وارد کنید:")
        return
    
    await state.update_data(lavayeh_branch_name=text)
    data = await state.get_data()
    
    if await _maybe_return_to_preview(data, message, state):
        return
    
    # ادامه به انتخاب استان
    await message.answer(
        "🏙 لطفاً **استان** مربوط به پرونده را انتخاب فرمایید:",
        reply_markup=create_province_kb(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.lavayeh_province)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲ — شماره پرونده (مسیر اصلی)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_tracking_code)
async def lavayeh_get_tracking_code(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer("🔢 لطفاً روش ثبت شماره پرونده را دوباره انتخاب کنید:", reply_markup=lavayeh_tracking_method_kb)
        await state.set_state(Form.lavayeh_tracking_method)
        return
    code = _to_en(message.text)
    valid, result = validate_tracking_code(code)
    if not valid:
        await message.answer(result, parse_mode="Markdown")
        return
    await state.update_data(lavayeh_tracking_code=code)
    data = await state.get_data()
    if await _maybe_return_to_preview(data, message, state):
        return
    await message.answer(
        "🏙 لطفاً **استان** مربوط به پرونده را انتخاب فرمایید:",
        reply_markup=create_province_kb(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.lavayeh_province)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲.۵ — انتخاب استان
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_province)
async def lavayeh_get_province(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    tracking_method = data.get("tracking_method", "case_number")
    
    if text == "🔙 بازگشت":
        # بازگشت به مرحله قبل بستگی به روش انتخاب شده دارد
        if tracking_method == "archive_number":
            await message.answer(
                "🏛 لطفاً نام شعبه خود را مجدداً تعیین کنید:",
                reply_markup=back_only_kb
            )
            await state.set_state(Form.lavayeh_branch_name)
        else:
            await message.answer("🔢 لطفاً شماره پرونده را مجدداً ارسال فرمایید:", reply_markup=ReplyKeyboardRemove())
            await state.set_state(Form.lavayeh_tracking_code)
        return
    
    if text not in PROVINCES:
        await message.answer("⚠️ لطفاً استان را از لیست انتخاب کنید:", reply_markup=create_province_kb())
        return
    
    await state.update_data(lavayeh_province=text)
    data = await state.get_data()
    
    if await _maybe_return_to_preview(data, message, state):
        return
    
    # اگر از شماره بایگانی استفاده شده، نیازی به ردیف فرعی نیست
    if tracking_method == "archive_number":
        # رفتن مستقیم به بخش اشخاص یا مرحله بعد
        title = data.get("lavayeh_title", "")
        if title == "اعلام وکالت":
            await message.answer(
                f"✅ استان «**{text}**» ثبت شد.\n\n"
                "👤 لطفاً **کدملی وکیل** را ارسال فرمایید:",
                reply_markup=back_only_kb,
                parse_mode="Markdown"
            )
            await state.set_state(Form.ealam_vakalaht_national_id)
        else:
            await message.answer(
                f"✅ استان «**{text}**» ثبت شد.\n\n"
                "👥 لطفاً نوع شخصیت ارائه‌دهنده لایحه را انتخاب کنید:",
                reply_markup=create_person_type_kb(),
                parse_mode="Markdown"
            )
            await state.set_state(Form.lavayeh_person_type)
    else:
        # درخواست ردیف فرعی
        await message.answer(
            f"✅ استان «**{text}**» ثبت شد.\n\n"
            "🔢 لطفاً **ردیف فرعی پرونده** را وارد فرمایید:\n_(عدد بین ۱ تا ۳۰)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_row_number)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳ — ردیف فرعی
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_row_number)
async def lavayeh_get_row_number(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer("🏙 لطفاً استان را دوباره انتخاب کنید:", reply_markup=create_province_kb())
        await state.set_state(Form.lavayeh_province)
        return
    num_str = _to_en(message.text)
    if not num_str.isdigit():
        await message.answer("⚠️ لطفاً یک عدد وارد کنید (۱ تا ۳۰):")
        return
    num = int(num_str)
    if not (1 <= num <= 30):
        await message.answer("⚠️ ردیف فرعی باید بین **۱ تا ۳۰** باشد:", parse_mode="Markdown")
        return
    await state.update_data(lavayeh_row_number=num)
    data = await state.get_data()
    if await _maybe_return_to_preview(data, message, state):
        return

    # ── اگر عنوان «اعلام وکالت» بود، جریان خاص ─────────────────────────
    if data.get("lavayeh_title") == "اعلام وکالت":
        await message.answer(
            "🔢 لطفاً **کد ملی وکیل** را وارد فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ealam_vakalaht_national_id)
        return

    # جریان عادی
    await state.update_data(lavayeh_persons=[], _current_person_index=0)
    await message.answer(
        "👤 لطفاً مشخص فرمایید ارائه‌دهنده لایحه **جزو کدام دسته** می‌باشد:",
        reply_markup=create_person_type_kb(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.lavayeh_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴ — نوع شخص (جریان عادی)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_person_type)
async def lavayeh_get_person_type(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    persons = data.get("lavayeh_persons", [])

    if text == "✅ خیر، ادامه مراحل":
        if not persons:
            await message.answer("⚠️ حداقل یک شخص باید ارائه‌دهنده لایحه باشد.")
            return
        if await _maybe_return_to_preview(data, message, state):
            return
        await message.answer(
            "📄 **شرح متن لایحه:**\n\nلطفاً متن کامل لایحه خود را ارسال فرمایید.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_text)
        return

    if text not in ["شخص حقیقی", "شخص حقوقی", "وکیل"]:
        first_types = [p.get("person_type") for p in persons]
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=create_person_type_kb(exclude=first_types if persons else [])
        )
        return

    await state.update_data(_current_person={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            "🏢 لطفاً **شناسه ملی شرکت** را ارسال فرمایید:\n_(۱۱ رقمی)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_company_id)
    else:
        await message.answer(
            f"🔢 لطفاً **کد ملی** {'وکیل' if text == 'وکیل' else 'شخص'} ارائه‌دهنده را وارد کنید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_national_id)


@lavayeh_router.message(Form.lavayeh_company_id)
async def lavayeh_get_company_id(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        persons = data.get("lavayeh_persons", [])
        first_types = [p.get("person_type") for p in persons]
        await message.answer(
            "👤 لطفاً نوع شخص را دوباره انتخاب کنید:",
            reply_markup=create_person_type_kb(exclude=first_types if persons else [])
        )
        await state.set_state(Form.lavayeh_person_type)
        return
    company_id = _to_en(message.text)
    if not company_id.isdigit() or len(company_id) != 11:
        await message.answer("⚠️ شناسه ملی شرکت باید **۱۱ رقمی** باشد:", parse_mode="Markdown")
        return
    data = await state.get_data()
    current_person = data.get("_current_person", {})
    current_person["company_id"] = company_id
    await state.update_data(_current_person=current_person)
    await message.answer("👔 لایحه توسط چه کسی ارائه می‌گردد؟", reply_markup=representative_type_kb)
    await state.set_state(Form.lavayeh_representative_type)


@lavayeh_router.message(Form.lavayeh_representative_type)
async def lavayeh_get_representative_type(message: Message, state: FSMContext):
    text = message.text or ""
    if text not in ["مدیرعامل", "نماینده"]:
        await message.answer("⚠️ لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=representative_type_kb)
        return
    data = await state.get_data()
    current_person = data.get("_current_person", {})
    current_person["representative_type"] = text
    await state.update_data(_current_person=current_person)
    await message.answer(
        f"🔢 لطفاً **کد ملی {text}** را وارد کنید:\n_(۱۰ رقمی)_",
        reply_markup=back_only_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.lavayeh_national_id)


@lavayeh_router.message(Form.lavayeh_national_id)
async def lavayeh_get_national_id(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        persons = data.get("lavayeh_persons", [])
        first_types = [p.get("person_type") for p in persons]
        await message.answer(
            "👤 لطفاً نوع شخص را دوباره انتخاب کنید:",
            reply_markup=create_person_type_kb(exclude=first_types if persons else [])
        )
        await state.set_state(Form.lavayeh_person_type)
        return
    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ کد ملی باید **۱۰ رقمی** باشد:", parse_mode="Markdown")
        return
    data = await state.get_data()
    current_person = data.get("_current_person", {})
    current_person["national_id"] = nat_id
    persons = data.get("lavayeh_persons", [])
    persons.append(current_person)
    await state.update_data(lavayeh_persons=persons, _current_person={})
    person_type = current_person.get("person_type", "")
    await message.answer(
        f"✅ کد ملی `{nat_id}` ({person_type}) ثبت شد.\n\n➕ آیا شخص دیگری نیز ارائه‌دهنده لایحه می‌باشد؟",
        reply_markup=add_or_finish_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.lavayeh_more_persons)


@lavayeh_router.message(Form.lavayeh_more_persons)
async def lavayeh_more_persons(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    persons = data.get("lavayeh_persons", [])

    if text == "➕ افزودن کدملی دیگر":
        used_types = [p.get("person_type") for p in persons]
        await message.answer(
            "👤 لطفاً نوع شخص جدید را انتخاب کنید:",
            reply_markup=create_person_type_kb(exclude=used_types)
        )
        await state.set_state(Form.lavayeh_person_type)
        return

    if text == "✅ اتمام و ادامه":
        if await _maybe_return_to_preview(data, message, state):
            return
        await message.answer(
            "📄 **شرح متن لایحه:**\n\nلطفاً متن کامل لایحه خود را ارسال فرمایید.\n\n"
            "⚠️ **توجه مهم:** متن پس از ارسال **قابل ویرایش نمی‌باشد**.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_text)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=add_or_finish_kb)


# ══════════════════════════════════════════════════════════════════════════════
# مراحل اعلام وکالت — کدملی وکیل (در فلوی ثبت لایحه)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.ealam_vakalaht_national_id)
async def ealam_in_lavayeh_get_national_id(message: Message, state: FSMContext):
    if not message.text:
        return
    data = await state.get_data()
    lawyers = data.get("ealam_lawyers", [])
    if message.text == "🔙 بازگشت":
        if lawyers:
            await message.answer("آیا وکیل دیگری نیز در این پرونده وکالت دارد؟", reply_markup=ealam_more_lawyers_kb)
            await state.set_state(Form.ealam_vakalaht_more_lawyers)
        else:
            await message.answer("🔢 لطفاً ردیف فرعی را دوباره وارد کنید:", reply_markup=back_only_kb)
            await state.set_state(Form.lavayeh_row_number)
        return
    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ کد ملی باید **۱۰ رقمی** باشد:", parse_mode="Markdown")
        return
    lawyers.append(nat_id)
    await state.update_data(ealam_lawyers=lawyers)
    await message.answer(
        f"✅ کد ملی وکیل `{nat_id}` ثبت شد.\n\nآیا **وکیل دیگری** نیز در این پرونده وکالت دارد؟",
        reply_markup=ealam_more_lawyers_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.ealam_vakalaht_more_lawyers)


@lavayeh_router.message(Form.ealam_vakalaht_more_lawyers)
async def ealam_in_lavayeh_more_lawyers(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ بله، وکیل دیگری هم هست":
        await message.answer(
            "🔢 لطفاً **کد ملی وکیل بعدی** را وارد فرمایید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ealam_vakalaht_national_id)
        return
    if text == "✅ خیر، ادامه مراحل":
        await message.answer(
            "🔢 لطفاً **شماره قرارداد وکالت** را وارد فرمایید:\n_(دقیقاً ۱۶ رقمی)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ealam_vakalaht_contract_number)
        return
    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=ealam_more_lawyers_kb)


@lavayeh_router.message(Form.ealam_vakalaht_contract_number)
async def ealam_in_lavayeh_get_contract(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        await message.answer("آیا وکیل دیگری نیز در این پرونده وکالت دارد؟", reply_markup=ealam_more_lawyers_kb)
        await state.set_state(Form.ealam_vakalaht_more_lawyers)
        return
    contract = _to_en(message.text)
    if not contract.isdigit() or len(contract) != 16:
        await message.answer(
            f"⚠️ شماره قرارداد باید **دقیقاً ۱۶ رقمی** باشد.\n"
            f"شماره وارد شده **{len(contract)} رقمی** است. مجدداً وارد کنید:",
            parse_mode="Markdown"
        )
        return
    data = await state.get_data()
    contracts = data.get("ealam_contracts", [])
    contracts.append(contract)
    await state.update_data(ealam_contracts=contracts)
    await message.answer(
        f"✅ شماره قرارداد `{contract}` ثبت شد.\n\nآیا **شماره قرارداد دیگری** نیز وجود دارد؟",
        reply_markup=ealam_more_contracts_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.ealam_vakalaht_more_contracts)


@lavayeh_router.message(Form.ealam_vakalaht_more_contracts)
async def ealam_in_lavayeh_more_contracts(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ افزودن شماره قرارداد دیگر":
        await message.answer(
            "🔢 لطفاً **شماره قرارداد بعدی** را وارد فرمایید:\n_(۱۶ رقمی)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ealam_vakalaht_contract_number)
        return
    if text == "✅ ادامه مراحل":
        await message.answer(
            "💰 **مقدار تمبر ابطالی:**\n\n"
            "اگر مقدار تمبر را به ریال می‌دانید، عدد را وارد کنید.\n"
            "در غیر این صورت از گزینه‌های زیر استفاده کنید:",
            reply_markup=ealam_stamp_amount_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ealam_vakalaht_stamp_amount)
        return
    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=ealam_more_contracts_kb)


@lavayeh_router.message(Form.ealam_vakalaht_stamp_amount)
async def ealam_in_lavayeh_stamp_amount(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text == "🚫 نیاز به ابطال تمبر ندارد":
        await state.update_data(ealam_stamp_amount=0, ealam_stamp_type="بدون تمبر")
        await _ask_lavayeh_text_ealam(message, state)
        return

    if text == "❓ نمیدانم، نیاز به محاسبه دارم":
        await message.answer(
            "🔍 **محاسبه تمبر:**\n\n"
            "لطفاً گزینه‌های زیر را انتخاب کنید.\n"
            "اگر گزینه‌های زیر کمکی نکرد، «عدم نیاز به تمبر» را انتخاب کنید "
            "(بعداً در شعبه قابلیت پرداخت تمبر را خواهید داشت) :",
            reply_markup=ealam_claim_type_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ealam_vakalaht_claim_type)
        return

    amount_str = _to_en(text)
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await message.answer(
            "⚠️ لطفاً مقدار تمبر را به **ریال** وارد کنید یا از گزینه‌های زیر استفاده کنید:",
            reply_markup=ealam_stamp_amount_kb,
            parse_mode="Markdown"
        )
        return

    stamp_amount = int(amount_str)
    await state.update_data(ealam_stamp_amount=stamp_amount, ealam_stamp_type="مشخص")
    await message.answer(f"✅ مقدار تمبر **{_fmt(stamp_amount)} ریال** ثبت شد.", parse_mode="Markdown")
    await _ask_lavayeh_text_ealam(message, state)


@lavayeh_router.message(Form.ealam_vakalaht_claim_type)
async def ealam_in_lavayeh_claim_type(message: Message, state: FSMContext):
    text = message.text or ""

    if "3️⃣" in text or "عدم نیاز" in text:
        await state.update_data(ealam_stamp_amount=0, ealam_stamp_type="بدون تمبر")
        await _ask_lavayeh_text_ealam(message, state)
        return

    if "2️⃣" in text or "غیر مالی" in text:
        stamp_amount = 200_000
        await state.update_data(ealam_stamp_amount=stamp_amount, ealam_stamp_type="غیر مالی")
        await message.answer(
            f"💰 مبلغ **{_fmt(stamp_amount)} ریال** تمبر ابطال می‌گردد.",
            reply_markup=continue_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ealam_vakalaht_text)
        return

    if "1️⃣" in text or "مالی" in text:
        await message.answer(
            "💵 لطفاً **مبلغ خواسته** را به **ریال** وارد فرمایید:\n_(فقط عدد)_",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await state.set_state(Form.ealam_vakalaht_claim_amount)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=ealam_claim_type_kb)


@lavayeh_router.message(Form.ealam_vakalaht_claim_amount)
async def ealam_in_lavayeh_claim_amount(message: Message, state: FSMContext):
    if not message.text:
        return
    amount_str = _to_en(message.text)
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await message.answer("⚠️ لطفاً مبلغ خواسته را به **ریال** وارد کنید (فقط عدد):", parse_mode="Markdown")
        return

    claim_amount = int(amount_str)
    try:
        result = calculate_stamp_duty(claim_amount)
    except ValueError as e:
        await message.answer(f"⚠️ خطا در محاسبه: {e}")
        return

    result_text = format_result_fa(claim_amount, result)
    await state.update_data(ealam_claim_amount=claim_amount, ealam_stamp_result=result)

    await message.answer(
        f"📊 **نتیجه محاسبه تمبر:**\n\n{result_text}\n\n"
        "لطفاً انتخاب کنید **کدام نوع تمبر** در پرونده قرار داده شود:",
        reply_markup=ealam_stamp_type_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.ealam_vakalaht_stamp_type)


@lavayeh_router.message(Form.ealam_vakalaht_stamp_type)
async def ealam_in_lavayeh_stamp_type(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    result = data.get("ealam_stamp_result", {})

    if "بدوی" in text:
        stamp_amount = result.get("tamber_bedvi", 0)
        stamp_type = "بدوی"
    elif "تجدیدنظر" in text:
        stamp_amount = result.get("tamber_tajdidnazar", 0)
        stamp_type = "تجدیدنظر"
    elif "کلی" in text:
        stamp_amount = result.get("tamber_kolli", 0)
        stamp_type = "کلی"
    else:
        await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=ealam_stamp_type_kb)
        return

    await state.update_data(ealam_stamp_amount=stamp_amount, ealam_stamp_type=stamp_type)
    await message.answer(
        f"✅ **تمبر {stamp_type}** به مبلغ **{_fmt(stamp_amount)} ریال** انتخاب شد.",
        parse_mode="Markdown"
    )
    await _ask_lavayeh_text_ealam(message, state)


async def _ask_lavayeh_text_ealam(message: Message, state: FSMContext):
    await message.answer(
        "📄 **شرح متن لایحه اعلام وکالت:**\n\n"
        "لطفاً متن لایحه را ارسال فرمایید.\n"
        "⚠️ **توجه:** متن پس از ارسال قابل ویرایش نمی‌باشد.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.ealam_vakalaht_text)


@lavayeh_router.message(Form.ealam_vakalaht_text)
async def ealam_in_lavayeh_get_text(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "✅ ادامه مراحل":
        await state.update_data(lavayeh_attachments=[])
        await _ask_attachment_title(message, state, is_first=True)
        return
    if not text:
        await message.answer("⚠️ لطفاً متن را به صورت متن ارسال فرمایید.")
        return
    await state.update_data(lavayeh_text=text, lavayeh_attachments=[])
    await _ask_attachment_title(message, state, is_first=True)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۵ — شرح متن لایحه (جریان عادی)
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_text)
async def lavayeh_get_text(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ لطفاً شرح متن لایحه را به صورت متن ارسال فرمایید.")
        return
    data = await state.get_data()
    is_editing = data.get("_is_editing")
    if is_editing:
        await state.update_data(lavayeh_text=message.text)
        data = await state.get_data()
        if await _maybe_return_to_preview(data, message, state):
            return
    await state.update_data(lavayeh_text=message.text, lavayeh_attachments=[])
    await _ask_attachment_title(message, state, is_first=True)


async def _ask_attachment_title(message: Message, state: FSMContext, is_first: bool):
    await state.update_data(lavayeh_images=[])
    kb = lavayeh_attachment_title_kb_first if is_first else lavayeh_attachment_title_kb
    intro = "✅ متن لایحه ثبت شد.\n\n" if is_first else ""
    await message.answer(
        f"{intro}📄 **عنوان مدرک بعدی:**\n\n"
        "در صورتی که تصویری برای ضمیمه در لایحه دارید، ابتدا عنوان تصویر مدرک را تایپ کنید (مثلاً «کارت ملی»)،\n"
        "یا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.lavayeh_attachment_title)


@lavayeh_router.message(Form.lavayeh_attachment_title)
async def lavayeh_get_attachment_title(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ لطفاً عنوان را به صورت متن ارسال فرمایید.")
        return
    data = await state.get_data()
    attachments = data.get("lavayeh_attachments", [])

    if text == "⏭ رد کردن (بدون مدرک)" and not attachments:
        await state.update_data(lavayeh_attachments=[])
        data = await state.get_data()
        if await _maybe_return_to_preview(data, message, state):
            return
        await _go_to_preview(message, state)
        return

    title = "مستندات" if text == "🔹 عنوان مهم نیست (صرفا درج شود مستندات)" else text
    await state.update_data(_current_attachment_title=title)
    await message.answer(
        f"✅ عنوان «**{title}**» ثبت شد.\n\n"
        "🖼 لطفاً تصاویر مربوط به این مدرک را به صورت **عکس (Photo)** ارسال فرمایید.\n"
        "⚠️ فقط فرمت **JPG / JPEG** قابل قبول است.\n\n"
        "پس از ارسال همه تصاویر، دکمه **«اتمام ارسال تصاویر»** را بفشارید.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.lavayeh_images)


@lavayeh_router.message(Form.lavayeh_images, F.photo)
async def lavayeh_receive_image(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    images = data.get("lavayeh_images", [])
    file_id = message.photo[-1].file_id
    images.append(file_id)
    await state.update_data(lavayeh_images=images)

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    manage_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
            [KeyboardButton(text="🗑 حذف تصویر")]
        ],
        resize_keyboard=True
    )
    await message.reply(
        f"✅ تصویر شماره **{len(images)}** دریافت شد.\n"
        f"مجموع تصاویر این مدرک: **{len(images)} تصویر**\n\n"
        "می‌توانید تصاویر بیشتری ارسال کنید یا «اتمام» را بزنید.",
        reply_markup=manage_kb,
        parse_mode="Markdown"
    )


@lavayeh_router.message(Form.lavayeh_images, F.document)
async def lavayeh_reject_document(message: Message, state: FSMContext):
    await message.answer(
        "⚠️ لطفاً تصاویر را به صورت **عکس (Photo)** ارسال کنید، نه فایل.",
        parse_mode="Markdown"
    )


@lavayeh_router.message(Form.lavayeh_images, F.text == "🗑 حذف تصویر")
async def lavayeh_ask_delete_image(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    images = data.get("lavayeh_images", [])
    if not images:
        await message.answer("⚠️ لیست تصاویر خالی است.")
        return
    await message.answer("🗑 **حذف تصویر:**\n\nعکس‌های ارسالی:", parse_mode="Markdown")
    for i, file_id in enumerate(images):
        await bot.send_photo(message.chat.id, photo=file_id, caption=f"تصویر شماره {i + 1}")
    await message.answer(
        "لطفاً **شماره تصویر** برای حذف را ارسال فرمایید:",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.update_data(_deleting_image=True)


@lavayeh_router.message(Form.lavayeh_images)
async def lavayeh_images_text(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    images = data.get("lavayeh_images", [])
    deleting = data.get("_deleting_image", False)

    if deleting:
        num_str = _to_en(text)
        if num_str.isdigit():
            idx = int(num_str) - 1
            if 0 <= idx < len(images):
                images.pop(idx)
                await state.update_data(lavayeh_images=images, _deleting_image=False)
                from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
                if images:
                    manage_kb = ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
                            [KeyboardButton(text="🗑 حذف تصویر")]
                        ],
                        resize_keyboard=True
                    )
                else:
                    manage_kb = ReplyKeyboardRemove()
                await message.answer(
                    f"✅ تصویر شماره **{idx+1}** حذف شد.\n"
                    f"مجموع باقیمانده: **{len(images)} تصویر**",
                    reply_markup=manage_kb,
                    parse_mode="Markdown"
                )
                return
            else:
                await message.answer(f"⚠️ شماره نامعتبر. لطفاً عددی بین ۱ تا {len(images)} وارد کنید:")
                return
        else:
            await state.update_data(_deleting_image=False)

    if text == "✅ اتمام ارسال تصاویر":
        if not images:
            await message.answer("⚠️ حداقل یک تصویر برای این مدرک ارسال کنید.")
            return
        attachments = data.get("lavayeh_attachments", [])
        title = data.get("_current_attachment_title", "مستندات")
        attachments.append({"title": title, "images": images})
        await state.update_data(lavayeh_attachments=attachments, lavayeh_images=[])
        await message.answer(
            f"✅ مدرک «**{title}**» با **{len(images)} تصویر** ثبت شد.\n\nآیا مدرک دیگری دارید؟",
            reply_markup=lavayeh_attachment_more_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_attachment_more)
        return

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    if images:
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
                [KeyboardButton(text="🗑 حذف تصویر")]
            ],
            resize_keyboard=True
        )
    else:
        kb = None
    await message.answer("⚠️ لطفاً تصویر این مدرک را ارسال کنید:", reply_markup=kb)


@lavayeh_router.message(Form.lavayeh_attachment_more)
async def lavayeh_attachment_more(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ بله، عنوان و مدرک دیگر دارم":
        await _ask_attachment_title(message, state, is_first=False)
        return
    if text == "✅ خیر، ادامه بده":
        data = await state.get_data()
        if await _maybe_return_to_preview(data, message, state):
            return
        await _go_to_preview(message, state)
        return
    await message.answer("لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=lavayeh_attachment_more_kb)


async def _go_to_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    preview_text = build_preview(data)
    await message.answer(preview_text, reply_markup=lavayeh_confirm_kb, parse_mode="Markdown")
    await state.set_state(Form.lavayeh_confirm)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۷ — تایید یا ویرایش
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_confirm)
async def lavayeh_confirm_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "✅ تایید و شروع ثبت":
        data = await state.get_data()
        user_id = message.from_user.id
        title = data.get("lavayeh_title", "")

        if not hasattr(runtime_state, "active_lavayeh_users"):
            runtime_state.active_lavayeh_users = set()
        runtime_state.active_lavayeh_users.add(user_id)

        await message.answer(
            "⏳ **درخواست لایحه تایید شد.**\n\nدر حال ارسال به صف پردازش...",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )

        if title == "اعلام وکالت":
            # ارسال تسک اعلام وکالت
            await runtime_state.job_queue.put({
                "user_id": user_id,
                "query_type": "اعلام_وکالت",
                "task_type": "EALAM_VAKALAHT_SUBMIT",
                "ealam_lawyers": data.get("ealam_lawyers", []),
                "ealam_contracts": data.get("ealam_contracts", []),
                "ealam_stamp_amount": data.get("ealam_stamp_amount", 0),
                "ealam_stamp_type": data.get("ealam_stamp_type", ""),
                "ealam_lavayeh_text": data.get("lavayeh_text", ""),
                "ealam_attachments": data.get("lavayeh_attachments", []),
                "lavayeh_tracking_code": data.get("lavayeh_tracking_code", ""),
                "lavayeh_province": data.get("lavayeh_province", ""),
                "lavayeh_row_number": data.get("lavayeh_row_number", 1),
            })
        else:
            # ارسال تسک لایحه عادی
            await runtime_state.job_queue.put({
                "user_id": user_id,
                "query_type": "لایحه_ثبت",
                "task_type": "LAVAYEH_SUBMIT",
                "lavayeh_title": data.get("lavayeh_title"),
                "lavayeh_system_title": data.get("lavayeh_system_title"),
                "lavayeh_tracking_code": data.get("lavayeh_tracking_code"),
                "lavayeh_province": data.get("lavayeh_province"),
                "lavayeh_row_number": data.get("lavayeh_row_number"),
                "lavayeh_persons": data.get("lavayeh_persons", []),
                "lavayeh_text": data.get("lavayeh_text"),
                "lavayeh_attachments": data.get("lavayeh_attachments", []),
            })

        await state.clear()
        return

    if text == "✏️ ویرایش اطلاعات":
        await message.answer(
            "✏️ **ویرایش اطلاعات:**\n\nکدام بخش را می‌خواهید ویرایش کنید؟",
            reply_markup=lavayeh_edit_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_edit_choice)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=lavayeh_confirm_kb)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۷-ب — منوی ویرایش
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.lavayeh_edit_choice)
async def lavayeh_edit_choice_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "🔙 بازگشت به پیش‌نمایش":
        data = await state.get_data()
        await message.answer(build_preview(data), reply_markup=lavayeh_confirm_kb, parse_mode="Markdown")
        await state.set_state(Form.lavayeh_confirm)
        return

    if text == "📝 ویرایش عنوان لایحه":
        await state.update_data(_is_editing=True)
        await message.answer("📝 لطفاً عنوان جدید را انتخاب کنید:", reply_markup=lavayeh_title_kb)
        await state.set_state(Form.lavayeh_title)
        return

    if text == "🔢 ویرایش شماره پرونده":
        await state.update_data(_is_editing=True)
        await message.answer("🔢 لطفاً شماره پرونده جدید را ارسال فرمایید:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.lavayeh_tracking_code)
        return

    if text == "🏙 ویرایش استان":
        await state.update_data(_is_editing=True)
        await message.answer("🏙 لطفاً استان جدید را انتخاب کنید:", reply_markup=create_province_kb())
        await state.set_state(Form.lavayeh_province)
        return

    if text == "🔢 ویرایش ردیف فرعی":
        await state.update_data(_is_editing=True)
        await message.answer("🔢 لطفاً ردیف فرعی جدید را وارد کنید (۱ تا ۳۰):", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.lavayeh_row_number)
        return

    if text == "👤 ویرایش اشخاص ارائه‌دهنده":
        data = await state.get_data()
        if data.get("lavayeh_title") == "اعلام وکالت":
            await state.update_data(ealam_lawyers=[], _is_editing=True)
            await message.answer(
                "👤 لیست وکلا پاک شد.\nلطفاً **کد ملی وکیل اول** را وارد فرمایید:\n_(۱۰ رقمی)_",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown"
            )
            await state.set_state(Form.ealam_vakalaht_national_id)
            return
        await state.update_data(lavayeh_persons=[], _current_person={}, _is_editing=True)
        await message.answer(
            "👤 لیست اشخاص پاک شد.\nلطفاً مشخص فرمایید اولین ارائه‌دهنده جزو کدام دسته می‌باشد:",
            reply_markup=create_person_type_kb()
        )
        await state.set_state(Form.lavayeh_person_type)
        return

    if text == "📄 ویرایش شرح متن لایحه":
        await state.update_data(_is_editing=True)
        await message.answer("📄 لطفاً متن جدید لایحه را ارسال فرمایید:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.lavayeh_text)
        return

    if text == "🖼 ویرایش تصاویر مدارک":
        await state.update_data(lavayeh_attachments=[], _is_editing=True)
        await message.answer("🖼 مدارک قبلی پاک شدند.")
        await _ask_attachment_title(message, state, is_first=True)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=lavayeh_edit_kb)


# ══════════════════════════════════════════════════════════════════════════════
# ارسال نتیجه ثبت لایحه به کاربر + شروع فلوی امضا
# ══════════════════════════════════════════════════════════════════════════════
async def send_lavayeh_result(
    bot: Bot,
    user_id: int,
    pdf_path: str,
    court_total: int,
    tracking_code: str = "",
    national_ids: str = "",
    lavayeh_title: str = "لایحه دفاعیه",
    lavayeh_province: str = "",
    lavayeh_row_number: int = 1,
    lavayeh_persons: list = None,
):
    from aiogram.types import FSInputFile

    if lavayeh_persons is None:
        lavayeh_persons = []

    if not hasattr(runtime_state, "active_lavayeh_users"):
        runtime_state.active_lavayeh_users = set()

    if os.path.exists(pdf_path):
        doc = FSInputFile(pdf_path)
        await bot.send_document(
            user_id,
            document=doc,
            caption="📄 **نسخه ثبت‌شده لایحه شما در سامانه قضایی**",
            parse_mode="Markdown"
        )
        os.remove(pdf_path)

    fee_text = format_lavayeh_fee_explanation(court_total)
    final_fee = calculate_lavayeh_fee(court_total)

    await bot.send_message(user_id, fee_text, parse_mode="Markdown")

    payment_msg = (
        f"💳 **فاکتور پرداخت خدمات لایحه:**\n\n"
        f"💰 مبلغ: **{final_fee:,} تومان**\n\n"
        f"💳 شماره کارت: `{CARD_NUMBER}`\n"
        f"👤 بنام: **{ACCOUNT_NAME}**\n\n"
        f"👇 پس از واریز، **عکس فیش** را ارسال فرمایید."
    )
    await bot.send_message(user_id, payment_msg, parse_mode="Markdown")

    await log_event(
        "ثبت", "لایحه", str(user_id), user_id,
        tracking_code=tracking_code, national_id=national_ids,
        doc_name="لایحه", payment_status="در انتظار پرداخت",
        note=f"مبلغ فاکتور: {final_fee:,} تومان (هزینه سامانه: {court_total:,} تومان)"
    )

    runtime_state.pending_lavayeh_payments[user_id] = {
        "invoice_time": datetime.datetime.now(),
        "final_fee": final_fee,
        "court_total": court_total,
        "tracking_code": tracking_code,
        "national_ids": national_ids,
        "reminder_sent": False,
        "blocked": False,
        "lavayeh_title": lavayeh_title,
        "lavayeh_province": lavayeh_province,
        "lavayeh_row_number": lavayeh_row_number,
        "lavayeh_persons": lavayeh_persons,
    }

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)
    await user_state.set_state(Form.waiting_for_lavayeh_payment_receipt)

    runtime_state.active_lavayeh_users.discard(user_id)


# ══════════════════════════════════════════════════════════════════════════════
# پرداخت هزینه لایحه
# ══════════════════════════════════════════════════════════════════════════════
@lavayeh_router.message(Form.waiting_for_lavayeh_payment_receipt, F.photo)
async def lavayeh_receive_payment_receipt(message: Message, bot: Bot, state: FSMContext):
    pending = runtime_state.pending_lavayeh_payments.get(message.from_user.id)
    if not pending:
        await message.answer("⚠️ فاکتور فعالی برای شما ثبت نشده است.")
        return

    expected_fee = pending["final_fee"]
    photo = message.photo[-1]
    photo_file = await bot.get_file(photo.file_id)
    photo_path = f"lavayeh_receipt_{message.from_user.id}_{int(datetime.datetime.now().timestamp())}.jpg"
    await bot.download_file(photo_file.file_path, photo_path)

    is_valid, ocr_msg = verify_payment_receipt(photo_path, expected_fee, CARD_NUMBER)

    if is_valid:
        await message.answer(
            f"✅ **تایید پرداخت:**\n{ocr_msg}\n\nهزینه لایحه تایید شد. متشکریم 🙏",
            reply_markup=ReplyKeyboardRemove()
        )
        await log_event(
            "پرداخت", "لایحه", message.from_user.full_name, message.from_user.id,
            tracking_code=pending.get("tracking_code", ""), national_id=pending.get("national_ids", ""),
            doc_name="لایحه", payment_status="پرداخت شده",
            note=f"مبلغ: {expected_fee:,} تومان"
        )

        user_id = message.from_user.id
        runtime_state.pending_lavayeh_sign[user_id] = {
            "tracking_code": pending.get("tracking_code", ""),
            "lavayeh_title": pending.get("lavayeh_title", "لایحه دفاعیه"),
            "province": pending.get("lavayeh_province", ""),
            "row_number": pending.get("lavayeh_row_number", 1),
            "persons": pending.get("lavayeh_persons", []),
            "sign_sent_time": None,
            "sign_codes_received": {},
            "resend_notified": False,
        }
        runtime_state.pending_lavayeh_payments.pop(user_id, None)

        await bot.send_message(
            user_id,
            "🖊 **مرحله اخذ امضای الکترونیک:**\n\n"
            "هر موقع آمادگی دارید که کد امضا ارسال شود، گزینه زیر را انتخاب کنید:",
            reply_markup=lavayeh_sign_ready_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_sign_ready)

    else:
        await message.answer(f"❌ {ocr_msg}\n\nلطفاً تصویر رسید معتبر مجدداً ارسال فرمایید.")
        await bot.send_message(
            ADMIN_ID,
            f"⚠️ [LAVAYEH] رسید کاربر {message.from_user.id} (مبلغ: {expected_fee:,} تومان) تایید نشد."
        )

    if os.path.exists(photo_path):
        try:
            os.remove(photo_path)
        except Exception:
            pass


@lavayeh_router.message(Form.waiting_for_lavayeh_payment_receipt)
async def lavayeh_payment_receipt_text_only(message: Message):
    await message.answer("⚠️ لطفاً تصویر فیش واریزی را به صورت **عکس (Photo)** ارسال فرمایید:")


# ══════════════════════════════════════════════════════════════════════════════
# یادآوری ۲۴ ساعته + مسدودسازی
# ══════════════════════════════════════════════════════════════════════════════
async def lavayeh_payment_reminder_loop(bot: Bot):
    while True:
        try:
            now = datetime.datetime.now()
            for user_id, info in list(runtime_state.pending_lavayeh_payments.items()):
                if info.get("reminder_sent") or info.get("blocked"):
                    continue
                age = now - info["invoice_time"]
                if age >= datetime.timedelta(days=1):
                    try:
                        await bot.send_message(
                            user_id,
                            "با درود\nآیا مورد ثبتی شما کنسل می‌باشد؟",
                            reply_markup=lavayeh_cancel_reminder_kb
                        )
                        info["reminder_sent"] = True
                        user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)
                        await user_state.set_state(Form.lavayeh_payment_reminder_response)
                    except Exception as e:
                        logging.error(f"[LAVAYEH] خطا در ارسال یادآوری به کاربر {user_id}: {e}")
        except Exception as e:
            logging.error(f"[LAVAYEH] خطا در حلقه یادآوری: {e}")
        await asyncio.sleep(1800)


@lavayeh_router.message(Form.lavayeh_payment_reminder_response, F.text == "خیر")
async def lavayeh_reminder_no(message: Message, state: FSMContext):
    await message.answer(
        "مورد ثبتی شما تا پایان فردا ابطال خواهد شد؛ هرچه سریع‌تر پرداخت فرمایید.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Form.waiting_for_lavayeh_payment_receipt)


@lavayeh_router.message(Form.lavayeh_payment_reminder_response, F.text == "بله")
async def lavayeh_reminder_yes(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pending = runtime_state.pending_lavayeh_payments.get(user_id)
    if not pending:
        await message.answer("⚠️ فاکتور فعالی برای شما ثبت نشده است.", reply_markup=ReplyKeyboardRemove())
        return
    reduced_amount = pending["final_fee"] - pending["court_total"]
    pending["blocked"] = True
    pending["final_fee"] = reduced_amount
    await message.answer(
        f"لطفاً هزینه ثبت لایحه را پرداخت بفرمائید.\n"
        f"مبلغ: **{reduced_amount:,} تومان**\n\nباتشکر",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.waiting_for_lavayeh_payment_receipt)


@lavayeh_router.message(Form.lavayeh_payment_reminder_response)
async def lavayeh_reminder_invalid(message: Message):
    await message.answer(
        "لطفاً یکی از گزینه‌های «بله» یا «خیر» را انتخاب فرمایید:",
        reply_markup=lavayeh_cancel_reminder_kb
    )
