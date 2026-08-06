"""
هندلرهای تلگرام برای مرحله اخذ امضای الکترونیک لایحه.

جریان:
  ۱. پس از پرداخت موفق، send_lavayeh_result در lavayeh_handlers.py
     پیام «آمادگی برای ارسال کد» را می‌فرستد → state: lavayeh_sign_ready
  ۲. کاربر «آماده‌ام» می‌زند → سامانه کد را می‌فرستد → state: lavayeh_sign_code_input
  ۳. کاربر کد(ها) را ارسال می‌کند → امضا انجام می‌شود
  ۴. اگر ۱۵ دقیقه کد نیامد → سوال ارسال مجدد → lavayeh_sign_resend_prompt
  ۵. اگر «خیر» → سوال «بعداً اقدام می‌کنید؟» → lavayeh_sign_later_prompt
"""

import asyncio
import datetime
import logging

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

import runtime_state
from config import ADMIN_ID
from keyboards import (
    lavayeh_sign_ready_kb,
    lavayeh_sign_resend_kb,
    lavayeh_sign_later_kb,
    restart_kb,
    new_lavayeh_request_kb,
    ezhhar_sign_ready_kb,
    ezhhar_sign_resend_kb,
    ezhhar_sign_later_kb,
    ezhhar_sign_try_again_kb,
)
from states import Form

lavayeh_sign_router = Router()

# تایم‌اوت انتظار برای دریافت کد از کاربر (ثانیه)
SIGN_CODE_WAIT_TIMEOUT = 15 * 60   # ۱۵ دقیقه


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱ — آمادگی کاربر برای ارسال کد
# ══════════════════════════════════════════════════════════════════════════════

@lavayeh_sign_router.message(Form.lavayeh_sign_ready, F.text == "✅ آماده‌ام، کد امضا ارسال شود")
async def sign_ready_handler(message: Message, state: FSMContext, bot: Bot):
    """کاربر آمادگی خود را اعلام کرد — ارسال کد موقت از سامانه"""
    user_id = message.from_user.id
    data = await state.get_data()

    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        await message.answer(
            "⚠️ اطلاعات لایحه برای ارسال کد امضا یافت نشد. لطفاً مجدداً شروع کنید.",
            reply_markup=restart_kb
        )
        await state.clear()
        return

    await message.answer(
        "⏳ **در حال ارسال کد موقت امضا...**\n\n"
        "کد تا دقایق دیگر ارسال می‌گردد.\n"
        "⚠️ توجه داشته باشید مهلت کد کلاً **۷ دقیقه** می‌باشد.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

    # ارسال تسک به صف
    await runtime_state.job_queue.put({
        "user_id": user_id,
        "task_type": "LAVAYEH_SEND_SIGN_CODE",
        "query_type": "لایحه_امضا",
        "tracking_code": sign_info["tracking_code"],
        "province": sign_info.get("province", ""),
        "row_number": sign_info.get("row_number", 1),
        "lavayeh_title": sign_info.get("lavayeh_title", "لایحه دفاعیه"),
        "persons": sign_info.get("persons", []),
    })

    # انتظار — حلقه نظارتی برای تایم‌اوت ۱۵ دقیقه
    sign_info["sign_sent_time"] = datetime.datetime.now()
    sign_info["sign_codes_received"] = {}
    sign_info["resend_notified"] = False
    runtime_state.pending_lavayeh_sign[user_id] = sign_info

    await state.set_state(Form.lavayeh_sign_code_input)

    # تسک پس‌زمینه برای نظارت بر تایم‌اوت
    asyncio.create_task(_sign_code_timeout_watcher(bot, user_id, state))


@lavayeh_sign_router.message(Form.lavayeh_sign_ready)
async def sign_ready_invalid(message: Message):
    await message.answer(
        "لطفاً از دکمه زیر استفاده کنید:",
        reply_markup=lavayeh_sign_ready_kb
    )


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲ — دریافت کد(های) امضا از کاربر
# ══════════════════════════════════════════════════════════════════════════════

@lavayeh_sign_router.message(Form.lavayeh_sign_code_input)
async def sign_code_input_handler(message: Message, state: FSMContext, bot: Bot):
    """دریافت کد امضا از کاربر"""
    user_id = message.from_user.id
    text = (message.text or "").strip()

    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        await message.answer("⚠️ اطلاعات لایحه یافت نشد.", reply_markup=restart_kb)
        await state.clear()
        return

    # تبدیل اعداد فارسی/عربی
    _FA_AR = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    code = text.translate(_FA_AR).replace(" ", "").strip()

    if not code.isdigit() or not (3 <= len(code) <= 6):
        await message.answer(
            "⚠️ لطفاً **کد امضای دریافتی** را ارسال فرمایید:\n"
            "_(کد معمولاً ۵ رقمی است)_",
            parse_mode="Markdown"
        )
        return

    await message.answer(
        f"✅ کد `{code}` دریافت شد.\n⏳ در حال ثبت امضا در سامانه...",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    # ذخیره کد — برای اولین شخص (row 0) ارسال می‌کنیم
    # اگر چند شخص باشد، ترتیباً می‌پرسیم
    persons_awaiting = sign_info.get("persons_awaiting_sign", [0])
    codes_received = sign_info.get("sign_codes_received", {})

    # ثبت کد برای اولین شخص در صف انتظار
    if persons_awaiting:
        current_row = persons_awaiting[0]
        codes_received[str(current_row)] = code
        sign_info["sign_codes_received"] = codes_received
        runtime_state.pending_lavayeh_sign[user_id] = sign_info

    # ارسال تسک امضا به صف
    await runtime_state.job_queue.put({
        "user_id": user_id,
        "task_type": "LAVAYEH_SUBMIT_SIGN",
        "query_type": "لایحه_امضا",
        "tracking_code": sign_info["tracking_code"],
        "province": sign_info.get("province", ""),
        "row_number": sign_info.get("row_number", 1),
        "lavayeh_title": sign_info.get("lavayeh_title", "لایحه دفاعیه"),
        "sign_codes": codes_received,
    })


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳ — یادآوری تایم‌اوت و سوال ارسال مجدد
# ══════════════════════════════════════════════════════════════════════════════

async def _sign_code_timeout_watcher(bot: Bot, user_id: int, state: FSMContext):
    """
    ۱۵ دقیقه صبر می‌کند. اگر کد دریافت نشد، می‌پرسد «کد جدید ارسال کنیم؟»
    """
    await asyncio.sleep(SIGN_CODE_WAIT_TIMEOUT)

    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        return

    # اگر کد قبلاً دریافت شده بود، کاری نکن
    if sign_info.get("sign_codes_received"):
        return

    if sign_info.get("resend_notified"):
        return

    sign_info["resend_notified"] = True
    runtime_state.pending_lavayeh_sign[user_id] = sign_info

    try:
        current_state = await state.get_state()
        if current_state != Form.lavayeh_sign_code_input:
            return

        await bot.send_message(
            user_id,
            "⏰ **یادآوری:**\n\n"
            "۱۵ دقیقه گذشت و کد امضا دریافت نشد.\n\n"
            "آیا کد جدید ارسال کنیم؟",
            reply_markup=lavayeh_sign_resend_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_sign_resend_prompt)
    except Exception as e:
        logging.error(f"[SIGN] خطا در watcher تایم‌اوت کاربر {user_id}: {e}")


@lavayeh_sign_router.message(Form.lavayeh_sign_resend_prompt, F.text == "بله")
async def sign_resend_yes(message: Message, state: FSMContext, bot: Bot):
    """کاربر خواست کد جدید ارسال شود"""
    user_id = message.from_user.id
    sign_info = runtime_state.pending_lavayeh_sign.get(user_id)
    if not sign_info:
        await message.answer("⚠️ اطلاعات یافت نشد.", reply_markup=restart_kb)
        await state.clear()
        return

    await message.answer(
        "⏳ **در حال ارسال کد موقت جدید...**\n\n"
        "کد تا دقایق دیگر ارسال می‌گردد.\n"
        "⚠️ مهلت کد کلاً **۷ دقیقه** می‌باشد.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

    # reset وضعیت
    sign_info["sign_sent_time"] = datetime.datetime.now()
    sign_info["sign_codes_received"] = {}
    sign_info["resend_notified"] = False
    runtime_state.pending_lavayeh_sign[user_id] = sign_info

    await runtime_state.job_queue.put({
        "user_id": user_id,
        "task_type": "LAVAYEH_SEND_SIGN_CODE",
        "query_type": "لایحه_امضا",
        "tracking_code": sign_info["tracking_code"],
        "province": sign_info.get("province", ""),
        "row_number": sign_info.get("row_number", 1),
        "lavayeh_title": sign_info.get("lavayeh_title", "لایحه دفاعیه"),
        "persons": sign_info.get("persons", []),
    })

    await state.set_state(Form.lavayeh_sign_code_input)
    asyncio.create_task(_sign_code_timeout_watcher(bot, user_id, state))


@lavayeh_sign_router.message(Form.lavayeh_sign_resend_prompt, F.text == "خیر")
async def sign_resend_no(message: Message, state: FSMContext):
    """کاربر نمی‌خواهد کد جدید ارسال شود — می‌پرسیم بعداً اقدام می‌کند؟"""
    await message.answer(
        "آیا بعداً اقدام می‌کنید؟",
        reply_markup=lavayeh_sign_later_kb
    )
    await state.set_state(Form.lavayeh_sign_later_prompt)


@lavayeh_sign_router.message(Form.lavayeh_sign_resend_prompt)
async def sign_resend_invalid(message: Message):
    await message.answer(
        "لطفاً «بله» یا «خیر» را انتخاب کنید:",
        reply_markup=lavayeh_sign_resend_kb
    )


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴ — «آیا بعداً اقدام می‌کنید؟»
# ══════════════════════════════════════════════════════════════════════════════

@lavayeh_sign_router.message(Form.lavayeh_sign_later_prompt, F.text == "بله")
async def sign_later_yes(message: Message, state: FSMContext):
    """کاربر بعداً اقدام می‌کند"""
    await message.answer(
        "✅ **لایحه ثبتی تا ۲۴ ساعت آینده قابلیت تکمیل شدن را دارد.**\n\n"
        "منتظر اعلام خبر شما هستیم.\n\n"
        "📲 چاپ لایحه خود را جهت ادامه تکمیل نمودن به واتساپ به شماره "
        "**09306186888** ارسال فرمائید.",
        reply_markup=new_lavayeh_request_kb,
        parse_mode="Markdown"
    )
    await state.clear()


@lavayeh_sign_router.message(Form.lavayeh_sign_later_prompt, F.text == "خیر")
async def sign_later_no(message: Message, state: FSMContext):
    """کاربر نمی‌خواهد بعداً اقدام کند"""
    await message.answer(
        "📲 چاپ لایحه خود را جهت ادامه تکمیل نمودن به واتساپ به شماره "
        "**09306186888** ارسال فرمائید.",
        reply_markup=new_lavayeh_request_kb,
        parse_mode="Markdown"
    )
    await state.clear()


@lavayeh_sign_router.message(Form.lavayeh_sign_later_prompt)
async def sign_later_invalid(message: Message):
    await message.answer(
        "لطفاً «بله» یا «خیر» را انتخاب کنید:",
        reply_markup=lavayeh_sign_later_kb
    )


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی برای فراخوانی از scenarios.py
# ══════════════════════════════════════════════════════════════════════════════

async def on_sign_code_sent_success(bot: Bot, user_id: int, persons_count: int, state: FSMContext):
    """
    پس از ارسال موفق کد(ها) از سامانه، این تابع فراخوانی می‌شود.
    به کاربر اعلام می‌کند و state را روی دریافت کد می‌گذارد.
    """
    sign_info = runtime_state.pending_lavayeh_sign.get(user_id, {})
    sign_info["persons_awaiting_sign"] = list(range(persons_count))
    sign_info["sign_codes_received"] = {}
    runtime_state.pending_lavayeh_sign[user_id] = sign_info

    persons_text = "شخص ارائه‌دهنده لایحه" if persons_count == 1 else f"{persons_count} شخص ارائه‌دهنده لایحه"

    await bot.send_message(
        user_id,
        f"✅ **کد موقت امضا** برای {persons_text} ارسال شد.\n\n"
        "لطفاً هرچه سریع‌تر کد را ارسال کنید.\n"
        "_(در صورتی که کد برای شما ارسال نشد منتظر پیام بعدی ما باشید)_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Form.lavayeh_sign_code_input)


async def on_sign_code_sent_failure(bot: Bot, user_id: int, state: FSMContext):
    """ارسال کد ناموفق بود"""
    await bot.send_message(
        user_id,
        "⚠️ **سامانه در ارسال کد موقت با مشکل مواجه شد.**\n\n"
        "📲 چاپ لایحه خود را جهت ادامه تکمیل نمودن به واتساپ به شماره "
        "**09306186888** ارسال فرمائید.",
        parse_mode="Markdown",
        reply_markup=new_lavayeh_request_kb
    )
    runtime_state.pending_lavayeh_sign.pop(user_id, None)
    await state.clear()


async def on_sign_submit_success(bot: Bot, user_id: int, state: FSMContext):
    """امضا با موفقیت انجام شد"""
    runtime_state.pending_lavayeh_sign.pop(user_id, None)
    await bot.send_message(
        user_id,
        "✅ **امضای الکترونیک لایحه با موفقیت انجام شد.**\n\n"
        "فرآیند ثبت لایحه کاملاً تکمیل گردید. 🎉",
        reply_markup=new_lavayeh_request_kb,
        parse_mode="Markdown"
    )
    await bot.send_message(ADMIN_ID, f"✅ [SIGN] امضای لایحه کاربر {user_id} موفق.")
    await state.clear()


async def on_sign_submit_failure(bot: Bot, user_id: int, state: FSMContext):
    """امضا ناموفق بود"""
    runtime_state.pending_lavayeh_sign.pop(user_id, None)
    await bot.send_message(
        user_id,
        "⚠️ **سامانه اختلال دارد.**\n\n"
        "📲 چاپ لایحه خود را جهت ادامه تکمیل نمودن به واتساپ به شماره "
        "**09306186888** ارسال فرمائید.",
        parse_mode="Markdown",
        reply_markup=new_lavayeh_request_kb
    )
    await bot.send_message(ADMIN_ID, f"❌ [SIGN] امضای لایحه کاربر {user_id} ناموفق.")
    await state.clear()


# ══════════════════════════════════════════════════════════════════════════════
# بخش اخذ امضای الکترونیک اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════

# تایم‌اوت‌ها
EZHHAR_SIGN_CODE_TIMEOUT = 6 * 60     # ۶ دقیقه مهلت ارسال کد
EZHHAR_SIGN_WRONG_CODE_WAIT = 20 * 60  # ۲۰ دقیقه صبر بعد از کد اشتباه
EZHHAR_SIGN_NO_ACTION_TIMEOUT = 60 * 60  # ۶۰ دقیقه بدون اقدام

# ۶ دقیقه تایم‌اوت از زمان ارسال کد موقت امضا (نه از اعلام آمادگی)
EZHHAR_CODE_ENTRY_TIMEOUT = 6 * 60


@lavayeh_sign_router.message(Form.ezhhar_sign_ready, F.text == "✅ آماده‌ام، کد امضا ارسال شود")
async def ezhhar_sign_ready_handler(message: Message, state: FSMContext, bot: Bot):
    """کاربر آمادگی خود را اعلام کرد — نمایش اشخاص برای انتخاب"""
    user_id = message.from_user.id
    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        await message.answer(
            "⚠️ اطلاعات اظهارنامه برای ارسال کد امضا یافت نشد. لطفاً مجدداً شروع کنید.",
            reply_markup=restart_kb
        )
        await state.clear()
        return

    persons_awaiting = sign_info.get("persons_awaiting_sign", [])
    all_persons = sign_info.get("sign_persons", [])

    if not persons_awaiting:
        await message.answer(
            "✅ **امضای الکترونیک اظهارنامه با موفقیت انجام شد.**\n\n"
            "فرآیند ثبت اظهارنامه کاملاً تکمیل گردید. 🎉",
            reply_markup=new_lavayeh_request_kb,
            parse_mode="Markdown"
        )
        runtime_state.pending_ezhhar_sign.pop(user_id, None)
        await state.clear()
        return

    # ساخت کیبورد انتخاب شخص
    person_buttons = []
    for idx in persons_awaiting:
        person = next((p for p in all_persons if p["idx"] == idx), None)
        if person:
            name = person.get("name", f"شخص {idx + 1}")
            person_type = person.get("person_type", "")
            label = f"👤 {name}"
            if person_type:
                label += f" ({person_type})"
            person_buttons.append([KeyboardButton(text=label)])

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    person_select_kb = ReplyKeyboardMarkup(keyboard=person_buttons, resize_keyboard=True)

    await message.answer(
        "📝 **انتخاب شخص جهت ارسال کد امضا:**\n\n"
        "لطفاً شخصی که در دسترس است و آماده دریافت کد می‌باشد را انتخاب کنید:\n"
        "_(فقط یک نفر انتخاب کنید)_",
        reply_markup=person_select_kb,
        parse_mode="Markdown"
    )

    await state.set_state(Form.ezhhar_sign_person_select)


@lavayeh_sign_router.message(Form.ezhhar_sign_ready)
async def ezhhar_sign_ready_invalid(message: Message):
    await message.answer(
        "لطفاً از دکمه زیر استفاده کنید:",
        reply_markup=ezhhar_sign_ready_kb
    )


@lavayeh_sign_router.message(Form.ezhhar_sign_person_select)
async def ezhhar_sign_person_select_handler(message: Message, state: FSMContext, bot: Bot):
    """کاربر شخصی را برای ارسال کد انتخاب کرد"""
    user_id = message.from_user.id
    text = (message.text or "").strip()

    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        await message.answer("⚠️ اطلاعات یافت نشد.", reply_markup=restart_kb)
        await state.clear()
        return

    all_persons = sign_info.get("sign_persons", [])
    persons_awaiting = sign_info.get("persons_awaiting_sign", [])

    # یافتن شخص انتخاب‌شده
    selected_idx = None
    for idx in persons_awaiting:
        person = next((p for p in all_persons if p["idx"] == idx), None)
        if person:
            name = person.get("name", "")
            person_type = person.get("person_type", "")
            expected = f"👤 {name}"
            if person_type:
                expected += f" ({person_type})"
            if text == expected or name in text:
                selected_idx = idx
                break

    if selected_idx is None:
        await message.answer(
            "⚠️ لطفاً یکی از اشخاص لیست‌شده را انتخاب کنید."
        )
        return

    person = next((p for p in all_persons if p["idx"] == selected_idx), {})
    person_name = person.get("name", f"شخص {selected_idx + 1}")

    await message.answer(
        f"⏳ **در حال ارسال کد موقت امضا برای {person_name}...**\n\n"
        "کد تا دقایق دیگر ارسال می‌گردد.\n"
        "⚠️ توجه داشته باشید مهلت کد کلاً **۷ دقیقه** می‌باشد.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

    sign_info["current_person_idx"] = selected_idx
    sign_info["sign_sent_time"] = datetime.datetime.now()
    sign_info["sign_codes_received"] = {}
    runtime_state.pending_ezhhar_sign[user_id] = sign_info

    # ارسال تسک به صف
    await runtime_state.job_queue.put({
        "user_id": user_id,
        "task_type": "EZHHARNAMEH_SEND_SIGN_CODE",
        "tracking_code": sign_info["tracking_code"],
        "target_row_indices": [selected_idx],
    })

    await state.set_state(Form.ezhhar_sign_code_input)


@lavayeh_sign_router.message(Form.ezhhar_sign_code_input)
async def ezhhar_sign_code_input_handler(message: Message, state: FSMContext, bot: Bot):
    """دریافت کد امضا از کاربر برای اظهارنامه"""
    user_id = message.from_user.id
    text = (message.text or "").strip()

    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        await message.answer("⚠️ اطلاعات اظهارنامه یافت نشد.", reply_markup=restart_kb)
        await state.clear()
        return

    # تبدیل اعداد فارسی/عربی
    _FA_AR = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    code = text.translate(_FA_AR).replace(" ", "").strip()

    if not code.isdigit() or not (3 <= len(code) <= 6):
        await message.answer(
            "⚠️ لطفاً **کد امضای دریافتی** را ارسال فرمایید:\n"
            "_(کد معمولاً ۵ رقمی است)_",
            parse_mode="Markdown"
        )
        return

    current_idx = sign_info.get("current_person_idx", 0)
    await message.answer(
        f"✅ کد `{code}` دریافت شد.\n⏳ در حال ثبت امضا در سامانه...",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    # ارسال تسک امضا به صف
    await runtime_state.job_queue.put({
        "user_id": user_id,
        "task_type": "EZHHARNAMEH_SUBMIT_SIGN",
        "tracking_code": sign_info["tracking_code"],
        "row_idx": current_idx,
        "code": code,
    })


# ══════════════════════════════════════════════════════════════════════════════
# کال‌بک‌های موفقیت/خطا از سمت scenarios.py برای اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════

async def on_ezhhar_sign_code_sent_success(bot: Bot, user_id: int, persons: list, state: FSMContext):
    """پس از ارسال موفق کد از سامانه — اطلاع به کاربر و انتظار کد"""
    sign_info = runtime_state.pending_ezhhar_sign.get(user_id, {})
    sent_persons = [p for p in persons if p.get("sent")]

    for person in sent_persons:
        name = person.get("name", "نامشخص")
        await bot.send_message(
            user_id,
            f"✅ **کد موقت امضا** برای **{name}** ارسال شد.\n\n"
            "⏰ مهلت استفاده از این کد **۷ دقیقه** می‌باشد.\n"
            "لطفاً کد دریافتی را هرچه سریع‌تر ارسال کنید.",
            parse_mode="Markdown"
        )

    sign_info["sign_sent_time"] = datetime.datetime.now()
    # ثبت زمان برای تایم‌اوت ۶ دقیقه — از لحظه ارسال کد (نه اعلام آمادگی)
    sign_info["code_sent_announce_time"] = datetime.datetime.now()
    runtime_state.pending_ezhhar_sign[user_id] = sign_info

    # شروع تایمر ۶ دقیقه از زمان ارسال کد
    asyncio.create_task(_ezhhar_code_entry_timeout_watcher(bot, user_id, state))


async def on_ezhhar_sign_code_sent_failure(bot: Bot, user_id: int, state: FSMContext):
    """ارسال کد ناموفق بود"""
    await bot.send_message(
        user_id,
        "⚠️ **سامانه در ارسال کد موقت با مشکل مواجه شد.**\n\n"
        "📲 لطفاً جهت ثبت امضا به شماره **09306186888** در واتساپ پیام دهید.",
        parse_mode="Markdown",
        reply_markup=new_lavayeh_request_kb
    )
    runtime_state.pending_ezhhar_sign.pop(user_id, None)
    await state.clear()


async def on_ezhhar_sign_submit_success(bot: Bot, user_id: int, row_idx: int, state: FSMContext):
    """امضای شخص با موفقیت انجام شد — حذف از لیست و ادامه"""
    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        return

    persons_awaiting = sign_info.get("persons_awaiting_sign", [])
    if row_idx in persons_awaiting:
        persons_awaiting.remove(row_idx)
    sign_info["persons_awaiting_sign"] = persons_awaiting
    runtime_state.pending_ezhhar_sign[user_id] = sign_info

    if not persons_awaiting:
        # همه امضا کردند
        runtime_state.pending_ezhhar_sign.pop(user_id, None)
        await bot.send_message(
            user_id,
            "✅ **امضای الکترونیک با موفقیت درج شد و مورد شما ارسال گردید.**\n\n"
            "باتشکر از همراهی شما 🙏",
            reply_markup=new_lavayeh_request_kb,
            parse_mode="Markdown"
        )
        await bot.send_message(ADMIN_ID, f"✅ [EZHHAR_SIGN] امضای اظهارنامه کاربر {user_id} کامل شد.")
        await state.clear()
    else:
        # اشخاص دیگری هم باید امضا کنند
        all_persons = sign_info.get("sign_persons", [])
        remaining_names = []
        for idx in persons_awaiting:
            person = next((p for p in all_persons if p["idx"] == idx), None)
            if person:
                remaining_names.append(person.get("name", f"شخص {idx + 1}"))

        remaining_text = "\n".join([f"• {n}" for n in remaining_names])

        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        person_buttons = []
        for idx in persons_awaiting:
            person = next((p for p in all_persons if p["idx"] == idx), None)
            if person:
                name = person.get("name", f"شخص {idx + 1}")
                person_type = person.get("person_type", "")
                label = f"👤 {name}"
                if person_type:
                    label += f" ({person_type})"
                person_buttons.append([KeyboardButton(text=label)])

        person_select_kb = ReplyKeyboardMarkup(keyboard=person_buttons, resize_keyboard=True)

        await bot.send_message(
            user_id,
            f"✅ **امضای الکترونیک با موفقیت درج شد و مورد شما ارسال گردید.**\n\n"
            f"افراد باقی‌مانده جهت امضا:\n{remaining_text}\n\n"
            "لطفاً شخص بعدی که در دسترس است را انتخاب کنید:",
            reply_markup=person_select_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ezhhar_sign_person_select)


async def on_ezhhar_sign_wrong_code(bot: Bot, user_id: int, row_idx: int, state: FSMContext):
    """رمز موقت اشتباه بود — ۲۰ دقیقه صبر و سپس امکان ارسال مجدد"""
    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        return

    sign_info["wrong_code_time"] = datetime.datetime.now()
    runtime_state.pending_ezhhar_sign[user_id] = sign_info

    await bot.send_message(
        user_id,
        "⚠️ **رمز موقت اشتباه است.**\n\n"
        "لطفاً **۲۰ دقیقه** دیگر امتحان کنید.\n"
        "بعد از ۲۰ دقیقه می‌توانید درخواست کد جدید بدهید.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

    await state.set_state(Form.ezhhar_sign_wrong_code_wait)
    asyncio.create_task(_ezhhar_wrong_code_waiter(bot, user_id, state))


async def on_ezhhar_sign_submit_failure(bot: Bot, user_id: int, state: FSMContext):
    """امضا ناموفق بود — سوال ارسال مجدد"""
    await bot.send_message(
        user_id,
        "⚠️ **خطا در ثبت امضا.**\n\n"
        "آیا می‌خواهید کد جدید ارسال شود؟",
        reply_markup=ezhhar_sign_try_again_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.ezhhar_sign_resend_prompt)


# ══════════════════════════════════════════════════════════════════════════════
# هندلرهای تایم‌اوت و ارسال مجدد اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════

async def _ezhhar_code_entry_timeout_watcher(bot: Bot, user_id: int, state: FSMContext):
    """۶ دقیقه از زمان ارسال کد موقت — اگر کاربر کد نفرست، مهلت تمام شده"""
    await asyncio.sleep(EZHHAR_CODE_ENTRY_TIMEOUT)

    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        return

    current_state = await state.get_state()
    if current_state not in (Form.ezhhar_sign_person_select, Form.ezhhar_sign_code_input):
        return

    try:
        await bot.send_message(
            user_id,
            "⏰ **مهلت ارسال کد به پایان رسید.**\n\n"
            "اگر کد دریافت کرده‌اید، لطفاً ارسال کنید.\n"
            "در غیر این صورت مجدداً آمادگی خود را اعلام فرمایید.",
            reply_markup=ezhhar_sign_ready_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ezhhar_sign_ready)
    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] خطا در code_entry_timeout_watcher: {e}")


async def _ezhhar_wrong_code_waiter(bot: Bot, user_id: int, state: FSMContext):
    """۲۰ دقیقه صبر بعد از کد اشتباه — سپس اجازه ارسال مجدد"""
    await asyncio.sleep(EZHHAR_SIGN_WRONG_CODE_WAIT)

    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        return

    current_state = await state.get_state()
    if current_state != Form.ezhhar_sign_wrong_code_wait:
        return

    try:
        # دکمه ارسال مجدد کد
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        all_persons = sign_info.get("sign_persons", [])
        persons_awaiting = sign_info.get("persons_awaiting_sign", [])
        current_idx = sign_info.get("current_person_idx")

        # اگر هنوز این شخص در لیست انتظار هست
        if current_idx in persons_awaiting:
            person = next((p for p in all_persons if p["idx"] == current_idx), {})
            person_name = person.get("name", "شخص")

            person_buttons = []
            for idx in persons_awaiting:
                person = next((p for p in all_persons if p["idx"] == idx), None)
                if person:
                    name = person.get("name", f"شخص {idx + 1}")
                    person_type = person.get("person_type", "")
                    label = f"👤 {name}"
                    if person_type:
                        label += f" ({person_type})"
                    person_buttons.append([KeyboardButton(text=label)])

            person_select_kb = ReplyKeyboardMarkup(keyboard=person_buttons, resize_keyboard=True)

            await bot.send_message(
                user_id,
                f"⏰ **۲۰ دقیقه گذشت.**\n\n"
                f"اگر {person_name} در دسترس است، لطفاً مجدداً انتخاب کنید تا کد جدید ارسال شود:",
                reply_markup=person_select_kb,
                parse_mode="Markdown"
            )
            await state.set_state(Form.ezhhar_sign_person_select)
        else:
            await bot.send_message(
                user_id,
                "⏰ **۲۰ دقیقه گذشت.**\n\n"
                "لطفاً مجدداً آمادگی خود را اعلام فرمایید.",
                reply_markup=ezhhar_sign_ready_kb,
                parse_mode="Markdown"
            )
            await state.set_state(Form.ezhhar_sign_ready)

    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] خطا در wrong_code_waiter: {e}")


async def _ezhhar_no_action_60min_watcher(bot: Bot, user_id: int, state: FSMContext):
    """۶۰ دقیقه بدون هیچ اقدامی — ارسال پیام واتساپ"""
    await asyncio.sleep(EZHHAR_SIGN_NO_ACTION_TIMEOUT)

    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        return

    try:
        await bot.send_message(
            user_id,
            "⏰ **مهلت امضا به پایان رسید.**\n\n"
            "لطفاً جهت ثبت امضا به شماره **09306186888** در واتساپ "
            "پیام دهید تا امور شما تکمیل گردد.",
            reply_markup=new_lavayeh_request_kb,
            parse_mode="Markdown"
        )
        await bot.send_message(
            ADMIN_ID,
            f"⏰ [EZHHAR_SIGN] کاربر {user_id} پس از ۶۰ دقیقه اقدامی نکرد."
        )
    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] خطا در 60min watcher: {e}")

    runtime_state.pending_ezhhar_sign.pop(user_id, None)
    try:
        await state.clear()
    except Exception:
        pass


@lavayeh_sign_router.message(Form.ezhhar_sign_resend_prompt, F.text == "بله، کد جدید ارسال شود")
async def ezhhar_sign_resend_yes(message: Message, state: FSMContext, bot: Bot):
    """کاربر خواست کد جدید ارسال شود — بازگشت به انتخاب شخص"""
    user_id = message.from_user.id
    sign_info = runtime_state.pending_ezhhar_sign.get(user_id)
    if not sign_info:
        await message.answer("⚠️ اطلاعات یافت نشد.", reply_markup=restart_kb)
        await state.clear()
        return

    all_persons = sign_info.get("sign_persons", [])
    persons_awaiting = sign_info.get("persons_awaiting_sign", [])

    person_buttons = []
    for idx in persons_awaiting:
        person = next((p for p in all_persons if p["idx"] == idx), None)
        if person:
            name = person.get("name", f"شخص {idx + 1}")
            person_type = person.get("person_type", "")
            label = f"👤 {name}"
            if person_type:
                label += f" ({person_type})"
            person_buttons.append([KeyboardButton(text=label)])

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    person_select_kb = ReplyKeyboardMarkup(keyboard=person_buttons, resize_keyboard=True)

    await message.answer(
        "📝 **انتخاب شخص جهت ارسال کد جدید:**\n\n"
        "لطفاً شخصی که در دسترس است را انتخاب کنید:",
        reply_markup=person_select_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.ezhhar_sign_person_select)


@lavayeh_sign_router.message(Form.ezhhar_sign_resend_prompt, F.text == "خیر")
async def ezhhar_sign_resend_no(message: Message, state: FSMContext):
    """کاربر نمی‌خواهد کد جدید — سوال اقدام بعدی"""
    await message.answer(
        "آیا بعداً اقدام می‌کنید؟",
        reply_markup=ezhhar_sign_later_kb
    )
    await state.set_state(Form.ezhhar_sign_later_prompt)


@lavayeh_sign_router.message(Form.ezhhar_sign_later_prompt, F.text == "بله")
async def ezhhar_sign_later_yes(message: Message, state: FSMContext):
    await message.answer(
        "✅ **اظهارنامه تا ۲۴ ساعت آینده قابلیت تکمیل شدن را دارد.**\n\n"
        "📲 لطفاً جهت ثبت امضا به شماره **09306186888** در واتساپ پیام دهید.",
        reply_markup=new_lavayeh_request_kb,
        parse_mode="Markdown"
    )
    runtime_state.pending_ezhhar_sign.pop(message.from_user.id, None)
    await state.clear()


@lavayeh_sign_router.message(Form.ezhhar_sign_later_prompt, F.text == "خیر")
async def ezhhar_sign_later_no(message: Message, state: FSMContext):
    await message.answer(
        "📲 لطفاً جهت ثبت امضا به شماره **09306186888** در واتساپ پیام دهید.",
        reply_markup=new_lavayeh_request_kb,
        parse_mode="Markdown"
    )
    runtime_state.pending_ezhhar_sign.pop(message.from_user.id, None)
    await state.clear()
