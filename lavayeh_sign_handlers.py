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
        reply_markup=restart_kb,
        parse_mode="Markdown"
    )
    await state.clear()


@lavayeh_sign_router.message(Form.lavayeh_sign_later_prompt, F.text == "خیر")
async def sign_later_no(message: Message, state: FSMContext):
    """کاربر نمی‌خواهد بعداً اقدام کند"""
    await message.answer(
        "📲 چاپ لایحه خود را جهت ادامه تکمیل نمودن به واتساپ به شماره "
        "**09306186888** ارسال فرمائید.",
        reply_markup=restart_kb,
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
        reply_markup=restart_kb
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
        reply_markup=restart_kb,
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
        reply_markup=restart_kb
    )
    await bot.send_message(ADMIN_ID, f"❌ [SIGN] امضای لایحه کاربر {user_id} ناموفق.")
    await state.clear()
