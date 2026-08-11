"""
لایه‌ی تلگرام: تمام هندلرهای مکالمه (FSM) و کال‌بک‌های ادمین.
"""
import datetime
import logging
import os
import re

from aiogram import Bot, F, Router, BaseMiddleware, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    ReplyKeyboardRemove, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

import runtime_state
from config import ADMIN_ID, CARD_NUMBER, ACCOUNT_NAME, get_fee, FEES
from states import Form
from sheets import append_to_sheet, log_event
from ocr import verify_payment_receipt
from api_direct import (
    fast_pre_check, FastCheckError, SessionExpiredError as FastSessionExpiredError,
    PetitionNotFoundError as FastPetitionNotFoundError,
    InvalidTrackingCodeError as FastInvalidTrackingCodeError,
)
from keyboards import (
    restart_kb, accept_rules_kb, flow_type_kb, main_menu_kb, doc_category_kb,
    attachments_kb, cart_kb, pay_kb, confirm_single_kb, confirm_cart_kb,
    admin_login_kb, SUB_MENUS, create_submenu_kb, back_only_kb, new_lavayeh_request_kb,
    payment_cancel_kb, disrupted_retry_kb,
)
from lavayeh_handlers import lavayeh_router
from stamp_calc_handlers import stamp_calc_router
from ezhharnameh_handlers import ezhharnameh_router
from file_tools_handlers import file_tools_router, file_tools_entry
from subscription_handlers import subscription_router, subscription_expiry_checker

logger = logging.getLogger(__name__)

# بازه‌ی سال‌های معتبر برای ۷ رقم ابتدایی کد رهگیری (۱۳۹۴ تا ۱۴۰۶)
TRACKING_CODE_PREFIX_MIN = 1394220
TRACKING_CODE_PREFIX_MAX = 1406220
TRACKING_CODE_LENGTH = 16

# ───────────────────────────────────────────────────────────────
# ثابت‌های محدودیت تلاش و قطعی
# ───────────────────────────────────────────────────────────────
MAX_INQUIRY_ATTEMPTS = 2  # حداکثر تلاش ناموفق قبل از توقف
DISRUPTED_RETRY_MINUTES = 45  # فرصت تکرار بدون پرداخت (دقیقه)

# پیام خطایی که سامانه قضایی نمایش می‌دهد وقتی نوع سند اشتباه انتخاب شود
SAMANEH_WRONG_TYPE_ERROR = "کد دفتر، مبلغ پرونده یا دسترسی تقویم مربوط به این شعبه و قاضی نیست."


def _is_valid_tracking_code(code: str) -> bool:
    """کد رهگیری باید ۱۶ رقمی باشد و ۷ رقم ابتدایی آن در بازه‌ی معتبر باشد."""
    if len(code) != TRACKING_CODE_LENGTH or not code.isdigit():
        return False
    prefix = int(code[:7])
    return TRACKING_CODE_PREFIX_MIN <= prefix <= TRACKING_CODE_PREFIX_MAX


def _record_failed_inquiry(user_id: int) -> int:
    """ثبت یک تلاش ناموفق استعلام. خروجی: تعداد تلاش فعلی."""
    now = datetime.datetime.now().isoformat()
    info = runtime_state.inquiry_attempts.get(user_id, {"count": 0, "last_attempt": now})
    info["count"] += 1
    info["last_attempt"] = now
    runtime_state.inquiry_attempts[user_id] = info
    return info["count"]


def _reset_inquiry_attempts(user_id: int):
    """پاکسازی شمارنده‌ی تلاش‌های ناموفق (مثلاً وقتی کاربر از اول شروع می‌کند)."""
    runtime_state.inquiry_attempts.pop(user_id, None)


def _check_inquiry_limit(user_id: int) -> bool:
    """بررسی آیا کاربر به محدودیت تلاش رسیده است. True = محدود شده."""
    info = runtime_state.inquiry_attempts.get(user_id)
    if not info:
        return False
    # پاکسازی خودکار اگر آخرین تلاش بیش از ۲ ساعت پیش بوده
    try:
        last = datetime.datetime.fromisoformat(info["last_attempt"])
        if (datetime.datetime.now() - last) > datetime.timedelta(hours=2):
            runtime_state.inquiry_attempts.pop(user_id, None)
            return False
    except (ValueError, TypeError):
        pass
    return info["count"] >= MAX_INQUIRY_ATTEMPTS

router = Router()

# ── include کردن روترها ───────────────────────────────────────────────────────
router.include_router(lavayeh_router)
router.include_router(stamp_calc_router)
router.include_router(ezhharnameh_router)
router.include_router(file_tools_router)
router.include_router(subscription_router)


# ── نگهبان: مسدودسازی کاربرانی که فاکتور لایحه کنسل‌شده را پرداخت نکرده‌اند ──
async def _is_blocked_lavayeh_user(message: types.Message) -> bool:
    pending = runtime_state.pending_lavayeh_payments.get(message.from_user.id)
    return bool(pending and pending.get("blocked"))

@router.message(StateFilter("*"), _is_blocked_lavayeh_user, ~F.photo)
async def block_unpaid_cancelled_lavayeh_user(message: types.Message):
    await message.answer(
        "لطفا هزینه ثبت لایحه‌ای که کنسل شده است را پرداخت بفرمائید، "
        "پس از پرداخت، ربات مجددا فعال خواهد شد.\nباتشکر",
        reply_markup=ReplyKeyboardRemove()
    )

# ================= نگهبان ساعات کاری =================
class WorkingHoursMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: types.Message, data: dict):
        if event.from_user and event.from_user.id == ADMIN_ID:
            return await handler(event, data)

        tehran_tz = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
        tehran_time = datetime.datetime.now(tehran_tz)

        if 12 <= tehran_time.hour < 22:
            return await handler(event, data)
        else:
            await event.answer("⛔️ **خارج از ساعت کاری**\n\nکاربر گرامی، ساعت کاری سامانه از ۱۲:۰۰ ظهر الی ۲۲:۰۰ می‌باشد.")
            return

router.message.middleware(WorkingHoursMiddleware())

# ================= بخش پردازش فیش‌های واریزی =================

@router.message(Form.waiting_for_payment_receipt, F.photo)
async def process_payment_receipt(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    expected_fee = data['total_payment_sum']
    cart = data.get("cart", [])
    
    await message.answer("⏳ در حال دریافت و بررسی هوشمند فیش واریزی شما...")
    
    photo = message.photo[-1]
    photo_file = await bot.get_file(photo.file_id)
    photo_path = f"receipt_{message.from_user.id}_{int(datetime.datetime.now().timestamp())}.jpg"
    await bot.download_file(photo_file.file_path, photo_path)
    
    is_valid, ocr_msg = verify_payment_receipt(photo_path, expected_fee, CARD_NUMBER)
    
    if is_valid:
        queue_position = runtime_state.job_queue.qsize()
        queue_note = f"\n📊 موقعیت شما در صف: **{queue_position + 1}**" if queue_position > 0 else "\n▶️ پردازش بلافاصله آغاز می‌شود."
        await message.answer(f"✅ **تایید پرداخت:**\n{ocr_msg}\nتعداد {len(cart)} استعلام در صف پردازش قرار گرفت.{queue_note}", reply_markup=restart_kb)
        
        for item in cart:
            q_type = item['query_type']
            tracking_code = item['tracking_code']
            doc_category = item.get('doc_category')
            doc_subcategory = item.get('doc_subcategory')
            need_attachments = item.get('need_attachments', False)
            
            doc_name = f"{doc_category} - {doc_subcategory}" if doc_subcategory else doc_category
            await log_event(
                "پرداخت", q_type, message.from_user.full_name, message.from_user.id,
                tracking_code=tracking_code, doc_name=doc_name, payment_status="پرداخت شده"
            )
            
            await runtime_state.job_queue.put({
                'user_id': message.from_user.id, 
                'query_type': q_type, 
                'tracking_code': tracking_code, 
                'doc_category': doc_category, 
                'doc_subcategory': doc_subcategory, 
                'doc_type': doc_name,
                'need_attachments': need_attachments
            })
            
        if os.path.exists(photo_path):
            os.remove(photo_path)
        await state.clear()
        
    else:
        await message.answer("⏳ سیستم هوشمند قادر به خواندن جزئیات فیش نبود. برای بررسی دستی به مدیریت ارسال شد...")
        
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تایید سبد خرید", callback_data=f"okcart:{message.from_user.id}"),
                InlineKeyboardButton(text="❌ رد سبد خرید (فیک)", callback_data=f"nocart:{message.from_user.id}")
            ]
        ])
        
        admin_caption = (
            f"📥 **سبد خرید نیاز به تایید دستی:**\n\n"
            f"👤 کاربر: {message.from_user.full_name} (`{message.from_user.id}`)\n"
            f"تعداد استعلام: **{len(cart)} مورد**\n"
            f"مجموع فاکتور: {expected_fee:,} تومان\n\n"
            f"موتور هوشمند این فیش را تایید نکرد."
        )
        
        admin_doc = FSInputFile(photo_path)
        await bot.send_photo(ADMIN_ID, photo=admin_doc, caption=admin_caption, reply_markup=inline_kb)
        await state.update_data(photo_path=photo_path)

@router.callback_query(F.data.startswith("okcart:"))
async def admin_approve_cart(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    
    user_state = runtime_state.dp.fsm.resolve_context(bot, target_user_id, target_user_id)
    user_data = await user_state.get_data()
    
    cart = user_data.get("cart", [])
    photo_path = user_data.get('photo_path')
    
    for item in cart:
        q_type = item['query_type']
        tracking_code = item['tracking_code']
        doc_category = item.get('doc_category')
        doc_subcategory = item.get('doc_subcategory')
        need_attachments = item.get('need_attachments', False)
        
        doc_name = f"{doc_category} - {doc_subcategory}" if doc_subcategory else doc_category
        await log_event(
            "پرداخت", q_type, "تایید دستی سبد", target_user_id,
            tracking_code=tracking_code, doc_name=doc_name, payment_status="پرداخت شده (تایید دستی)"
        )
        
        await runtime_state.job_queue.put({
            'user_id': target_user_id, 
            'query_type': q_type, 
            'tracking_code': tracking_code, 
            'doc_category': doc_category, 
            'doc_subcategory': doc_subcategory, 
            'doc_type': doc_name,
            'need_attachments': need_attachments
        })
        
    await bot.send_message(
        target_user_id, 
        f"✅ **سبد خرید شما توسط مدیریت تایید شد.**\nتعداد {len(cart)} استعلام در صف قرار گرفت.",
        reply_markup=restart_kb
    )
    
    if photo_path and os.path.exists(photo_path):
        try:
            os.remove(photo_path)
        except:
            pass
            
    await user_state.clear()
    await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n✅ **تایید شد.**")
    await callback.answer("سبد خرید تایید شد.")
    
@router.callback_query(F.data.startswith("nocart:"))
async def admin_reject_cart(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    
    user_state = runtime_state.dp.fsm.resolve_context(bot, target_user_id, target_user_id)
    user_data = await user_state.get_data()
    photo_path = user_data.get('photo_path')
    
    await bot.send_message(
        target_user_id, 
        "❌ **عدم تایید پرداخت سبد خرید:**\nفیش واریزی رد شد. لطفا رسید معتبر ارسال فرمایید.",
        reply_markup=restart_kb
    )
    
    if photo_path and os.path.exists(photo_path):
        try:
            os.remove(photo_path)
        except:
            pass
            
    await user_state.clear()
    await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n❌ **رد شد.**")
    await callback.answer("فیش رد شد.")


# callback تایید دستی محاسبه تمبر

@router.message(Form.waiting_for_payment_receipt)
async def process_payment_receipt_text_only(message: types.Message, state: FSMContext):
    if message.text and "انصراف" in message.text:
        data = await state.get_data()
        cart = data.get("cart", [])
        await log_event(
            "کنسل", "پرداخت", message.from_user.full_name, message.from_user.id,
            tracking_code=None, doc_name=f"{len(cart)} مورد" if cart else None,
            payment_status="کنسل شده توسط کاربر (مرحله فیش پرداخت)"
        )
        await state.clear()
        await message.answer("لغو گردید. لطفاً مجدداً شروع کنید:", reply_markup=main_menu_kb)
        await state.set_state(Form.main_menu)
        return
    await message.answer("⚠️ لطفاً تصویر فیش واریزی خود را به صورت **عکس (Photo)** ارسال فرمایید:")


# ================= هندلرهای تایید/رد ثبت دسته‌جمعی توسط مدیر =================
@router.message(F.from_user.id == ADMIN_ID, F.text.startswith("/approve_bulk"))
async def admin_approve_bulk(message: types.Message, bot: Bot):
    """تایید درخواست ثبت دسته‌جمعی توسط مدیر"""
    from bulk_submissions import BULK_TASKS, run_bulk_processing_task
    import asyncio
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("⚠️ فرمت صحیح: `/approve_bulk #CODE-123456`", parse_mode="Markdown")
            return
        
        tracking_code = parts[1]
        
        if tracking_code not in BULK_TASKS:
            await message.answer(f"⚠️ کد رهگیری `{tracking_code}` یافت نشد.", parse_mode="Markdown")
            return
        
        task_data = BULK_TASKS[tracking_code]
        if task_data.get("status") != "pending_admin":
            await message.answer(f"⚠️ این درخواست قبلاً پردازش شده است. وضعیت: {task_data.get('status')}")
            return
        
        # تغییر وضعیت به در حال پردازش
        task_data["status"] = "processing"
        user_id = task_data.get("user_id")
        service_type = task_data.get("service_type", "lavayeh")
        service_fa = "لایحه" if service_type == "lavayeh" else "اظهارنامه"
        items = task_data.get("items", [])
        
        # ارسال پیام به کاربر
        try:
            await bot.send_message(
                user_id,
                f"✅ **درخواست ثبت دسته‌جمعی شما تایید شد!**\n\n"
                f"🔖 کد رهگیری: `{tracking_code}`\n"
                f"📦 تعداد موارد: **{len(items)} {service_fa}**\n\n"
                f"⏳ پردازش خودکار در پس‌زمینه آغاز شد. گزارش پیشرفت به صورت خودکار ارسال می‌شود.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Error notifying user about bulk approval: {e}")
        
        await message.answer(
            f"✅ **درخواست `{tracking_code}` تایید شد.**\n"
            f"پردازش پس‌زمینه آغاز شد.",
            parse_mode="Markdown"
        )
        
        # شروع پردازش پس‌زمینه
        asyncio.create_task(run_bulk_processing_task(bot, user_id, tracking_code))
        
    except Exception as e:
        logging.error(f"[ADMIN_APPROVE_BULK] خطا: {e}")
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="admin_approve_bulk", error=e, notify_admin=False)
        except Exception:
            pass
        await message.answer(f"⚠️ خطا در تایید درخواست: {e}")


@router.message(F.from_user.id == ADMIN_ID, F.text.startswith("/reject_bulk"))
async def admin_reject_bulk(message: types.Message, bot: Bot):
    """رد درخواست ثبت دسته‌جمعی توسط مدیر"""
    from bulk_submissions import BULK_TASKS
    
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 2:
            await message.answer("⚠️ فرمت صحیح: `/reject_bulk #CODE-123456 [دلیل رد]`", parse_mode="Markdown")
            return
        
        tracking_code = parts[1]
        reason = parts[2] if len(parts) > 2 else "دلیل مشخص نشده"
        
        if tracking_code not in BULK_TASKS:
            await message.answer(f"⚠️ کد رهگیری `{tracking_code}` یافت نشد.", parse_mode="Markdown")
            return
        
        task_data = BULK_TASKS[tracking_code]
        if task_data.get("status") != "pending_admin":
            await message.answer(f"⚠️ این درخواست قبلاً پردازش شده است. وضعیت: {task_data.get('status')}")
            return
        
        # تغییر وضعیت به رد شده
        task_data["status"] = "rejected"
        task_data["reject_reason"] = reason
        user_id = task_data.get("user_id")
        service_type = task_data.get("service_type", "lavayeh")
        service_fa = "لایحه" if service_type == "lavayeh" else "اظهارنامه"
        
        # ارسال پیام به کاربر
        try:
            await bot.send_message(
                user_id,
                f"❌ **درخواست ثبت دسته‌جمعی شما رد شد.**\n\n"
                f"🔖 کد رهگیری: `{tracking_code}`\n"
                f"📝 دلیل: {reason}\n\n"
                f"لطفاً اطلاعات را اصلاح کرده و مجدداً ارسال نمایید.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Error notifying user about bulk rejection: {e}")
        
        await message.answer(
            f"❌ **درخواست `{tracking_code}` رد شد.**\n"
            f"دلیل: {reason}",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logging.error(f"[ADMIN_REJECT_BULK] خطا: {e}")
        try:
            from bug_reporter import report_bug
            await report_bug(bot, where="admin_reject_bulk", error=e, notify_admin=False)
        except Exception:
            pass
        await message.answer(f"⚠️ خطا در رد درخواست: {e}")


# ================= بخش مکالمات تلگرام =================

# ================= دستورات مدیر: مشاهده و ادامه تسک‌های ناقص =================
@router.message(F.from_user.id == ADMIN_ID, F.text == "/incomplete_tasks")
async def admin_show_incomplete_tasks(message: types.Message, bot: Bot):
    """نمایش لیست تسک‌های ناقص با امکان ادامه"""
    tasks = runtime_state.incomplete_tasks
    if not tasks:
        await message.answer("✅ هیچ تسک ناقصی وجود ندارد.")
        return

    lines = ["📋 **تسک‌های ناقص:**\n"]
    for key, info in tasks.items():
        task_type = "اظهارنامه" if info["type"] == "ezhhar" else "لایحه"
        lines.append(
            f"🔢 کد: `{info['bill_no']}` | {task_type}\n"
            f"👤 کاربر: {info['user_id']}\n"
            f"📍 آخرین مرحله: {info['last_completed_step']}\n"
            f"▶️ ادامه از: {info['next_step']}\n"
            f"💡 `/resume {key}` برای ادامه\n"
        )

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(F.from_user.id == ADMIN_ID, F.text.startswith("/logs"))
async def admin_upload_logs(message: types.Message, bot: Bot):
    """آپلود فایل لاگ به مدیر (آپلود مستمر خطاها).
    استفاده: `/logs` → فقط خطاها/هشدارها | `/logs all` → لاگ کامل"""
    from bug_reporter import upload_logs
    parts = message.text.strip().split(maxsplit=1)
    which = "all" if (len(parts) > 1 and parts[1].strip().lower() == "all") else "bugs"
    await message.answer(f"⏳ در حال آپلود لاگ «{'کامل' if which == 'all' else 'خطاها/هشدارها'}»...")
    ok = await upload_logs(bot, chat_id=message.chat.id, which=which)
    if not ok:
        await message.answer("ℹ️ لاگی برای ارسال نبود یا آپلود ناموفق شد.")


@router.message(F.from_user.id == ADMIN_ID, Command("resume"))
async def admin_resume_task(message: types.Message, bot: Bot):
    """مدیر می‌تواند ادامه تسک ناقص را از مرحله مشخص‌شده شروع کند"""
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ لطفاً کد تسک را بفرستید:\n`/resume ezhhar:1400...` یا `/resume lavayeh:1400...`", parse_mode="Markdown")
        return

    task_key = parts[1].strip()
    info = runtime_state.incomplete_tasks.get(task_key)

    if not info:
        await message.answer(f"❌ تسک `{task_key}` یافت نشد.\n`/incomplete_tasks` را ببینید.", parse_mode="Markdown")
        return

    task_type = "اظهارنامه" if info["type"] == "ezhhar" else "لایحه"
    await message.answer(
        f"🔄 **ادامه تسک {task_type}**\n"
        f"🔢 کد رهگیری: `{info['bill_no']}`\n"
        f"👤 کاربر: {info['user_id']}\n"
        f"📍 ادامه از مرحله: **{info['next_step']}**\n\n"
        f"⏳ در حال شروع ادامه فرآیند...",
        parse_mode="Markdown"
    )

    # ارسال تسک به job_queue برای ادامه
    resume_data = {
        "action": "resume",
        "task_type": info["type"],
        "bill_no": info["bill_no"],
        "from_step": info["next_step"],
        "task_data": info["task_data"],
    }
    await runtime_state.job_queue.put(("resume", resume_data))
    logging.info(f"[ADMIN] مدیر ادامه تسک {task_key} را از مرحله {info['next_step']} شروع کرد.")

@router.message(StateFilter("*"), F.from_user.id == ADMIN_ID, F.text == "✅ ورودم تکمیل شد")
async def confirm_login_from_admin_global(message: types.Message, state: FSMContext):
    if not runtime_state.login_event.is_set():
        runtime_state.login_event.set()
        await message.reply("✅ **لاگین تایید شد.**", reply_markup=ReplyKeyboardRemove())
    else:
        await message.reply("شما قبلاً تایید نموده‌اید.", reply_markup=ReplyKeyboardRemove())

@router.message(StateFilter("*"), Command("start"))
@router.message(StateFilter("*"), F.text == "🔄 ثبت درخواست جدید (شروع)")
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # ── بررسی آیا کاربر در وضعیت disrupted (پرداخت شده ولی سامانه قطع) هست ──
    disrupted_info = runtime_state.disrupted_users.get(user_id)
    if disrupted_info:
        elapsed = datetime.datetime.now() - disrupted_info["timestamp"]
        if elapsed < datetime.timedelta(minutes=DISRUPTED_RETRY_MINUTES):
            remaining = DISRUPTED_RETRY_MINUTES - int(elapsed.total_seconds() / 60)
            await message.answer(
                f"⚠️ **شما یک استعلام پرداخت‌شده دارید که به‌دلیل اختلال سامانه کامل نشد.**\n\n"
                f"🔧 شما {remaining} دقیقه دیگر فرصت دارید بدون پرداخت مجدد، تلاش کنید.\n\n"
                f"آیا مایلید تلاش مجدد انجام دهید؟",
                reply_markup=disrupted_retry_kb,
                parse_mode="Markdown"
            )
            await state.set_state(Form.waiting_for_disrupted_retry)
            return
        else:
            # بازه‌ی ۴۵ دقیقه تمام شده
            del runtime_state.disrupted_users[user_id]

    # ── بررسی آیا ربات اخیراً کرش کرده (بازیابی) — با تفکیک ثبت‌شده/ثبت‌نشده ──
    if hasattr(runtime_state, '_crash_recovered_users'):
        if user_id in runtime_state._crash_recovered_users:
            recovery_type = runtime_state._crash_recovered_users[user_id]
            if recovery_type == "submitted":
                # کاربر درخواستش ثبت شده — اطمینان‌بخش
                await message.answer(
                    "🤖 **بابت اختلال پیش‌آمده در سامانه صمیمانه پوزش می‌طلبیم.**\n\n"
                    "درخواست شما قبلاً در سامانه ثبت شده و در حال پردازش است.\n"
                    "مطمئن باشید که موارد شما در روند ثبت قرار گرفته است.\n"
                    "لطفاً مجدداً از منوی اصلی اقدام فرمایید.",
                    parse_mode="Markdown"
                )
            else:
                # کاربر هنوز ثبت نکرده — عذرخواهی و درخواست تلاش مجدد
                await message.answer(
                    "🤖 **بابت اختلال پیش‌آمده در سامانه صمیمانه پوزش می‌طلبیم.**\n\n"
                    "متاسفانه فرآیند شما پیش از ثبت نهایی قطع شد.\n"
                    "لطفاً مجدداً از ابتدا اقدام فرمایید.\n"
                    "اگر قبلاً پرداخت کرده‌اید، فرصت تکرار بدون پرداخت به شما داده می‌شود.",
                    parse_mode="Markdown"
                )
            # حذف از لیست بازیابی تا پیام تکرار نشود
            runtime_state._crash_recovered_users.pop(user_id, None)

    welcome_text = "با درود و احترام\n🟢 لطفاً پیش از هرگونه اقدام، آیین‌نامه را مطالعه فرمایید:\n🔗 https://forms.gle/UeevWfg5YiDkC5F37\n\n👇 آیا قوانین را تایید می‌نمایید؟"
    await message.answer(welcome_text, reply_markup=accept_rules_kb)
    await state.set_state(Form.waiting_for_rule_acceptance)


@router.message(StateFilter("*"), F.text == "ثبت درخواست جدید")
async def cmd_new_lavayeh_request(message: types.Message, state: FSMContext):
    """شروع مستقیم ثبت لایحه جدید بدون بازگشت به قوانین."""
    from lavayeh_handlers import lavayeh_entry
    await lavayeh_entry(message, state)


# ================= هندلر تلاش مجدد بدون پرداخت (disrupted retry) =================
@router.message(Form.waiting_for_disrupted_retry)
async def process_disrupted_retry(message: types.Message, state: FSMContext, bot: Bot):
    """کاربر disrupted می‌تواند یک‌بار بدون پرداخت تلاش مجدد کند."""
    user_id = message.from_user.id

    if message.text and "انصراف" in message.text:
        del runtime_state.disrupted_users[user_id]
        await message.answer(
            "❌ درخواست تلاش مجدد لغو شد.\nلطفاً مجدداً شروع کنید:",
            reply_markup=main_menu_kb
        )
        await state.set_state(Form.main_menu)
        return

    if message.text and "تلاش مجدد" in message.text:
        info = runtime_state.disrupted_users.get(user_id)
        if not info:
            await message.answer("⚠️ وضعیت تلاش مجدد یافت نشد. لطفاً از اول شروع کنید.", reply_markup=main_menu_kb)
            await state.set_state(Form.main_menu)
            return

        elapsed = datetime.datetime.now() - info["timestamp"]
        if elapsed >= datetime.timedelta(minutes=DISRUPTED_RETRY_MINUTES):
            del runtime_state.disrupted_users[user_id]
            await message.answer(
                f"⏰ بازه‌ی {DISRUPTED_RETRY_MINUTES} دقیقه‌ای تلاش مجدد تمام شده است.\n"
                f"لطفاً مجدداً شروع کنید:",
                reply_markup=main_menu_kb
            )
            await state.set_state(Form.main_menu)
            return

        # تلاش مجدد — ارسال مجدد job به صف بدون نیاز به پرداخت
        job_data = info["job_data"]
        queue_pos = runtime_state.job_queue.qsize()
        queue_note = f"\n📊 موقعیت شما در صف: **{queue_pos + 1}**" if queue_pos > 0 else "\n▶️ پردازش بلافاصله آغاز می‌شود."

        await message.answer(
            f"🔄 **تلاش مجدد بدون پرداخت ...**\n{queue_note}",
            reply_markup=restart_kb,
            parse_mode="Markdown"
        )
        await runtime_state.job_queue.put(job_data)

        # حذف از disrupted — فقط یک‌بار اجازه تلاش مجدد
        del runtime_state.disrupted_users[user_id]
        await state.clear()

        # اطلاع به مدیر
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔄 **تلاش مجدد disrupted:**\n"
                f"👤 کاربر: `{user_id}`\n"
                f"کد رهگیری: `{job_data.get('tracking_code', 'N/A')}`\n"
                f"نوع: {job_data.get('query_type', 'N/A')}",
                parse_mode="Markdown"
            )
        except Exception:
            pass

@router.message(Form.waiting_for_rule_acceptance, F.text == "✅ قوانین و مقررات را تایید می‌نمایم")
async def rules_accepted(message: types.Message, state: FSMContext):
    await message.answer("❓ **لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:**", reply_markup=flow_type_kb)
    await state.set_state(Form.waiting_for_flow_type)

@router.message(Form.waiting_for_flow_type)
async def process_flow_type(message: types.Message, state: FSMContext):
    if not message.text: return
    if "تک‌درخواست" in message.text or "تک درخواست" in message.text:
        await state.update_data(flow_type="single", cart=[])
        await message.answer("سپاسگزاریم.\nلطفاً نوع خدمت را انتخاب نمایید:", reply_markup=main_menu_kb)
        await state.set_state(Form.main_menu)
    elif "سبد خرید" in message.text:
        await state.update_data(flow_type="cart", cart=[])
        await message.answer("🛒 **حالت سبد خرید فعال شد.**\nلطفاً نوع استعلام اول خود را انتخاب نمایید:", reply_markup=main_menu_kb)
        await state.set_state(Form.main_menu)
    elif "ثبت لایحه" in message.text:
        from lavayeh_handlers import lavayeh_entry
        await lavayeh_entry(message, state)
    elif "ثبت اظهارنامه" in message.text:
        from ezhharnameh_handlers import ezhharnameh_entry
        await ezhharnameh_entry(message, state)
    elif "محاسبه تمبر" in message.text:
        from stamp_calc_handlers import stamp_calc_entry
        await stamp_calc_entry(message, state)
    elif "ابزار فایل" in message.text:
        await file_tools_entry(message, state)

async def _show_cart(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cart = data.get("cart", [])
    if not cart:
        await message.answer("🛒 سبد شما خالی است.", reply_markup=main_menu_kb)
        return

    cart_text = "🛒 **سبد استعلام‌های شما:**\n\n"
    total_sum = 0
    for idx, item in enumerate(cart):
        q_type = item['query_type']
        code = item['tracking_code']
        fee = item['fee']

        if q_type == "شماره تماس":
            desc = f"📞 استعلام شماره همراه `{code}`"
        elif q_type == "کد ملی":
            desc = f"👤 استعلام کد ملی `{code}`"
        else:
            att_desc = f" (همراه با {item['total_attachments']} پیوست)" if item['need_attachments'] else " (بدون پیوست)"
            desc = f"📄 کدرهگیری `{code}`" + att_desc

        cart_text += f"{idx+1}. {desc} — **{fee:,} تومان**\n"
        total_sum += fee

    cart_text += f"\n💰 **مجموع: {total_sum:,} تومان**"
    await message.answer(cart_text, reply_markup=pay_kb, parse_mode="Markdown")


@router.message(Form.main_menu)
async def process_main_menu(message: types.Message, state: FSMContext):
    if not message.text: return
    
    if "🔙 بازگشت به منوی اصلی" in message.text:
        await message.answer("❓ **لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:**", reply_markup=flow_type_kb, parse_mode="Markdown")
        await state.set_state(Form.waiting_for_flow_type)
        return

    if "➕ ثبت استعلام جدید" in message.text:
        await message.answer("لطفاً نوع خدمت جدید را انتخاب نمایید:", reply_markup=main_menu_kb)
        return
        
    elif "🧹 خالی کردن سبد" in message.text:
        await state.update_data(cart=[])
        await message.answer("🧹 سبد استعلام‌های شما خالی شد.", reply_markup=main_menu_kb)
        return
        
    elif "🛒 مشاهده سبد خرید" in message.text:
        await _show_cart(message, state)
        return
        
    elif "💳 پرداخت و تسویه حساب" in message.text:
        data = await state.get_data()
        cart = data.get("cart", [])
        if not cart:
            await message.answer("🛒 سبد خرید شما خالی است.", reply_markup=main_menu_kb)
            return
            
        total_sum = sum(item['fee'] for item in cart)
        await state.update_data(total_payment_sum=total_sum)
        
        payment_msg = (
            f"💳 **فاکتور پرداخت:**\n\n"
            f"💰 مجموع: **{total_sum:,} تومان**\n\n"
            f"💳 شماره کارت: `{CARD_NUMBER}`\n"
            f"👤 بنام: **{ACCOUNT_NAME}**\n\n"
            f"👇 پس از واریز، **عکس فیش** را ارسال فرمایید."
        )
        await message.answer(payment_msg, reply_markup=payment_cancel_kb, parse_mode="Markdown")
        await state.set_state(Form.waiting_for_payment_receipt)
        return
        
    elif "🔙 بازگشت به سبد خرید" in message.text:
        await _show_cart(message, state)
        return
        
    if "1️⃣" in message.text:
        await message.answer("لطفاً کد رهگیری خود را ارسال فرمایید:", reply_markup=back_only_kb)
        await state.set_state(Form.waiting_for_tracking_code)
    elif "2️⃣" in message.text:
        await message.answer("📞 لطفاً شماره تماس مورد نظر را ارسال فرمایید:\n(با فرمت 09 آغاز شود)", reply_markup=back_only_kb)
        await state.set_state(Form.waiting_for_phone_number)
    elif "3️⃣" in message.text:
        await message.answer("👤 لطفاً کد ملی مورد نظر را ارسال فرمایید:\n(یک عدد ۱۰ رقمی)", reply_markup=back_only_kb)
        await state.set_state(Form.waiting_for_national_id)

@router.message(Form.waiting_for_tracking_code)
async def process_tracking_code(message: types.Message, state: FSMContext):
    if not message.text: return
    if message.text == "🔙 بازگشت":
        await message.answer("لطفاً نوع خدمت را انتخاب نمایید:", reply_markup=main_menu_kb)
        await state.set_state(Form.main_menu)
        return
    clean_code = message.text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')).replace(" ", "").strip()
    if not re.match(r'^[0-9]+$', clean_code):
        await message.answer("⚠️ فرمت نامعتبر است. فقط عدد ارسال کنید:")
        return
    if not _is_valid_tracking_code(clean_code):
        await message.answer(
            "⚠️ کد رهگیری نامعتبر است.\n"
            "کد رهگیری باید ۱۶ رقم باشد و با یکی از سال‌های ۱۳۹۴ تا ۱۴۰۶ (یعنی اعداد ۱۳۹۴۲۲۰ الی ۱۴۰۶۲۲۰) شروع شود.\n"
            "لطفاً کد را دوباره بررسی و ارسال فرمایید:"
        )
        return
    # ── بررسی محدودیت تلاش قبل از ادامه ──
    if _check_inquiry_limit(message.from_user.id):
        await message.answer(
            f"❌ {SAMANEH_WRONG_TYPE_ERROR}\n\n"
            f"⚠️ **تعداد دفعات تلاش شما به حداکثر ({MAX_INQUIRY_ATTEMPTS} بار) رسیده است.**\n\n"
            f"لطفاً کدرهگیری و نوع سند (لایحه، اظهارنامه، شکواییه و ...) را به‌دقت بررسی فرمایید و مجدداً از منوی اصلی شروع کنید.",
            reply_markup=main_menu_kb,
            parse_mode="Markdown"
        )
        await state.clear()
        return
    # پاکسازی شمارنده‌ها وقتی کاربر کد معتبر وارد می‌کند
    _reset_inquiry_attempts(message.from_user.id)
    await state.update_data(query_type="کد رهگیری", tracking_code=clean_code)
    await message.answer("مربوط به کدام دسته است؟", reply_markup=doc_category_kb)
    await state.set_state(Form.waiting_for_doc_category)

@router.message(Form.waiting_for_doc_category)
async def process_doc_category(message: types.Message, state: FSMContext):
    category = message.text
    if category == "🔙 بازگشت به منوی قبل" or category == "🔙 بازگشت":
        await message.answer("کد رهگیری را ارسال کنید:", reply_markup=back_only_kb)
        await state.set_state(Form.waiting_for_tracking_code)
        return
    await state.update_data(doc_category=category)
    if category in SUB_MENUS:
        await message.answer(f"نوع دقیق «{category}» را مشخص کنید:", reply_markup=create_submenu_kb(category))
        await state.set_state(Form.waiting_for_doc_subcategory)
    else:
        await state.update_data(doc_subcategory=None)
        await message.answer("📋 آیا نیاز به دریافت فایل‌های پیوست (منضمات) دارید؟", reply_markup=attachments_kb)
        await state.set_state(Form.waiting_for_attachments_opt)

@router.message(Form.waiting_for_doc_subcategory)
async def process_doc_subcategory(message: types.Message, state: FSMContext):
    if message.text == "🔙 بازگشت به منوی قبل":
        await message.answer("دسته‌بندی اصلی را انتخاب کنید:", reply_markup=doc_category_kb)
        await state.set_state(Form.waiting_for_doc_category)
        return
    await state.update_data(doc_subcategory=message.text)
    await message.answer("📋 آیا نیاز به دریافت فایل‌های پیوست (منضمات) دارید؟", reply_markup=attachments_kb)
    await state.set_state(Form.waiting_for_attachments_opt)

@router.message(Form.waiting_for_attachments_opt)
async def process_attachments_opt(message: types.Message, state: FSMContext):
    if not message.text: return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        category = data.get('doc_category', '')
        if category in SUB_MENUS:
            await message.answer(f"نوع دقیق «{category}» را مشخص کنید:", reply_markup=create_submenu_kb(category))
            await state.set_state(Form.waiting_for_doc_subcategory)
        else:
            await message.answer("مربوط به کدام دسته است؟", reply_markup=doc_category_kb)
            await state.set_state(Form.waiting_for_doc_category)
        return
    need_attachments = "بله" in message.text
    await state.update_data(need_attachments=need_attachments)
    
    data = await state.get_data()
    flow_type = data.get('flow_type', 'single')
    
    if need_attachments:
        await message.answer("⏳ در حال استعلام تعداد پیوست‌های پرونده... لطفاً صبور باشید.", reply_markup=ReplyKeyboardRemove())
        
        doc_name = data.get('doc_subcategory') or data['doc_category']
        flow_type = data.get('flow_type', 'single')
        
        # ── تلاش سریع (خارج از صف) ──────────────────────────────
        fast_success = False
        try:
            total_attachments_count = await fast_pre_check(
                tracking_code=data['tracking_code'],
                category=data['doc_category'],
                subcategory=data.get('doc_subcategory'),
                user_id=message.from_user.id,
                bot=message.bot
            )
            fast_success = True
        except FastPetitionNotFoundError:
            attempts = _record_failed_inquiry(message.from_user.id)
            if attempts >= MAX_INQUIRY_ATTEMPTS:
                await message.answer(
                    f"❌ {SAMANEH_WRONG_TYPE_ERROR}\n\n"
                    f"⚠️ **تعداد دفعات تلاش شما به حداکثر ({MAX_INQUIRY_ATTEMPTS} بار) رسیده است.**\n\n"
                    f"لطفاً کدرهگیری و نوع سند (لایحه، اظهارنامه، شکواییه و ...) را به‌دقت بررسی فرمایید و مجدداً از منوی اصلی شروع کنید.",
                    reply_markup=main_menu_kb,
                    parse_mode="Markdown"
                )
                await state.clear()
            else:
                remaining = MAX_INQUIRY_ATTEMPTS - attempts
                await message.answer(
                    f"❌ پرونده‌ای با کد `{data['tracking_code']}` یافت نگردید.\n\n"
                    f"⚠️ لطفاً کدرهگیری و نوع سند خود را بررسی کنید.\n"
                    f"(تلاش {attempts} از {MAX_INQUIRY_ATTEMPTS})",
                    parse_mode="Markdown"
                )
            return
        except FastInvalidTrackingCodeError:
            attempts = _record_failed_inquiry(message.from_user.id)
            if attempts >= MAX_INQUIRY_ATTEMPTS:
                await message.answer(
                    f"❌ {SAMANEH_WRONG_TYPE_ERROR}\n\n"
                    f"⚠️ **تعداد دفعات تلاش شما به حداکثر ({MAX_INQUIRY_ATTEMPTS} بار) رسیده است.**\n\n"
                    f"لطفاً کدرهگیری و نوع سند (لایحه، اظهارنامه، شکواییه و ...) را به‌دقت بررسی فرمایید و مجدداً از منوی اصلی شروع کنید.",
                    reply_markup=main_menu_kb,
                    parse_mode="Markdown"
                )
                await state.clear()
            else:
                remaining = MAX_INQUIRY_ATTEMPTS - attempts
                await message.answer(
                    f"❌ کدرهگیری یا نوع خدمت را اشتباه وارد نموده‌اید.\n\n"
                    f"⚠️ لطفاً کدرهگیری و نوع سند خود را بررسی کنید.\n"
                    f"(تلاش {attempts} از {MAX_INQUIRY_ATTEMPTS})",
                    parse_mode="Markdown"
                )
            return
        except FastSessionExpiredError:
            logger.warning("[FAST-CHECK] نشست منقضی — فال‌بک به صف مرورگر")
        except FastCheckError as e:
            logger.warning(f"[FAST-CHECK] شکست: {e} — فال‌بک به صف مرورگر")
        
        if fast_success:
            # ✅ استعلام سریع موفق — نمایش فاکتور بدون صف
            calculated_fee = FEES["کد رهگیری با منضمات"] + total_attachments_count * 5000
            await state.update_data(
                payment_fee=calculated_fee,
                need_attachments=True,
                total_attachments=total_attachments_count
            )
            
            kb = confirm_single_kb if flow_type == "single" else confirm_cart_kb
            action_text = (
                "تایید نهایی و دریافت فاکتور پرداخت"
                if flow_type == "single"
                else "تایید و افزودن این مورد به سبد خرید"
            )
            
            confirm_msg = (
                f"📋 **اطلاعات استعلام با منضمات:**\n\n"
                f"کد پیگیری: `{data['tracking_code']}`\n"
                f"سند: **{doc_name}**\n"
                f"📎 تعداد پیوست: **{total_attachments_count} برگ**\n"
                f"💰 فاکتور: ۵۰,۰۰۰ + ({total_attachments_count} × ۵,۰۰۰) = **{calculated_fee:,} تومان**\n\n"
                f"آیا {action_text} فرمایید؟"
            )
            await message.answer(confirm_msg, reply_markup=kb, parse_mode="Markdown")
            await state.set_state(Form.confirm_opt)
        else:
            # ❌ فال‌بک به روش قبلی (صف مرورگر)
            logger.info("[FAST-CHECK] فال‌بک به job_queue برای PRE_CHECK")
            await runtime_state.job_queue.put({
                'user_id': message.from_user.id,
                'query_type': data['query_type'],
                'task_type': 'PRE_CHECK',
                'tracking_code': data['tracking_code'],
                'doc_category': data['doc_category'],
                'doc_subcategory': data.get('doc_subcategory')
            })
    else:
        doc_name = f"{data['doc_category']} - {data['doc_subcategory']}" if data.get('doc_subcategory') else data['doc_category']
        fee = get_fee("کد رهگیری", False)
        await state.update_data(payment_fee=fee)
        
        kb = confirm_single_kb if flow_type == "single" else confirm_cart_kb
        action_text = "تایید نهایی و دریافت فاکتور پرداخت" if flow_type == "single" else "تایید و افزودن این مورد به سبد خرید"
        
        await message.answer(
            f"📋 **مشخصات استعلام (بدون پیوست):**\n\n"
            f"کد پیگیری: `{data['tracking_code']}`\n"
            f"سند: **{doc_name}**\n"
            f"💰 هزینه: **{fee:,} تومان**\n\n"
            f"آیا مایلید این درخواست را {action_text} فرمایید؟",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.confirm_opt)

@router.message(Form.waiting_for_phone_number)
async def process_phone_number(message: types.Message, state: FSMContext):
    if not message.text: return
    if message.text == "🔙 بازگشت":
        await message.answer("لطفاً نوع خدمت را انتخاب نمایید:", reply_markup=main_menu_kb)
        await state.set_state(Form.main_menu)
        return
    clean_phone = message.text.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')).replace(" ", "").strip()
    if not re.match(r'^09[0-9]{9}$', clean_phone):
        await message.answer("⚠️ شماره نامعتبر است (مثال: 09123456789):")
        return
    
    fee = get_fee("شماره تماس", False)
    await state.update_data(payment_fee=fee, query_type="شماره تماس", tracking_code=clean_phone, doc_category="شماره تماس", doc_subcategory=None, need_attachments=False)
    
    data = await state.get_data()
    flow_type = data.get('flow_type', 'single')
    kb = confirm_single_kb if flow_type == "single" else confirm_cart_kb
    action_text = "تایید نهایی و دریافت فاکتور پرداخت" if flow_type == "single" else "تایید و افزودن این مورد به سبد خرید"
    
    await message.answer(
        f"📋 **مشخصات استعلام شماره تماس:**\n\n"
        f"📞 شماره همراه: `{clean_phone}`\n"
        f"💰 هزینه: **{fee:,} تومان**\n\n"
        f"آیا مایلید این درخواست را {action_text} فرمایید؟",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.confirm_opt)

@router.message(Form.waiting_for_national_id)
async def process_national_id(message: types.Message, state: FSMContext):
    if not message.text: return
    if message.text == "🔙 بازگشت":
        await message.answer("لطفاً نوع خدمت را انتخاب نمایید:", reply_markup=main_menu_kb)
        await state.set_state(Form.main_menu)
        return
    clean_id = message.text.translate(str.maketrans('۰۱۲۳۴۵6۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')).replace(" ", "").strip()
    if not re.match(r'^[0-9]{10}$', clean_id):
        await message.answer("⚠️ کد ملی نامعتبر است. لطفاً یک عدد ۱۰ رقمی وارد نمایید:")
        return
    
    fee = get_fee("کد ملی", False)
    await state.update_data(payment_fee=fee, query_type="کد ملی", tracking_code=clean_id, doc_category="کد ملی", doc_subcategory=None, need_attachments=False)
    
    data = await state.get_data()
    flow_type = data.get('flow_type', 'single')
    kb = confirm_single_kb if flow_type == "single" else confirm_cart_kb
    action_text = "تایید نهایی و دریافت فاکتور پرداخت" if flow_type == "single" else "تایید و افزودن این مورد به سبد خرید"
    
    await message.answer(
        f"📋 **مشخصات استعلام کد ملی:**\n\n"
        f"👤 کد ملی: `{clean_id}`\n"
        f"💰 هزینه: **{fee:,} تومان**\n\n"
        f"آیا مایلید این درخواست را {action_text} فرمایید؟",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.confirm_opt)

@router.message(Form.confirm_opt)
async def confirm_opt_process(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    flow_type = data.get('flow_type', 'single')
    
    if "تایید و دریافت فاکتور" in message.text:
        fee = data.get('payment_fee', 0)
        await state.update_data(total_payment_sum=fee)
        
        item = {
            'query_type': data.get('query_type'),
            'tracking_code': data.get('tracking_code'),
            'doc_category': data.get('doc_category'),
            'doc_subcategory': data.get('doc_subcategory'),
            'need_attachments': data.get('need_attachments', False),
            'fee': fee,
            'total_attachments': data.get('total_attachments', 0)
        }
        await state.update_data(cart=[item])
        
        payment_msg = (
            f"💳 **فاکتور پرداخت:**\n\n"
            f"🔹 نوع استعلام: **{data.get('query_type')}**\n"
            f"💰 مبلغ: **{fee:,} تومان**\n\n"
            f"💳 شماره کارت: `{CARD_NUMBER}`\n"
            f"👤 بنام: **{ACCOUNT_NAME}**\n\n"
            f"👇 پس از واریز، **عکس فیش** را ارسال فرمایید."
        )
        await message.answer(payment_msg, reply_markup=payment_cancel_kb, parse_mode="Markdown")
        await state.set_state(Form.waiting_for_payment_receipt)
        
    elif "افزودن به سبد خرید" in message.text:
        cart = data.get("cart", [])
        
        item = {
            'query_type': data.get('query_type'),
            'tracking_code': data.get('tracking_code'),
            'doc_category': data.get('doc_category'),
            'doc_subcategory': data.get('doc_subcategory'),
            'need_attachments': data.get('need_attachments', False),
            'fee': data.get('payment_fee', 0),
            'total_attachments': data.get('total_attachments', 0)
        }
        
        cart.append(item)
        await state.update_data(cart=cart)
        await state.update_data(
            query_type=None, tracking_code=None, doc_category=None, 
            doc_subcategory=None, need_attachments=None, payment_fee=None, total_attachments=None
        )
        
        await message.answer(
            f"🛒 **به سبد خرید اضافه شد!**\n"
            f"تعداد: **{len(cart)} مورد**\n\n"
            f"لطفاً یکی از گزینه‌های زیر را انتخاب فرمایید:",
            reply_markup=cart_kb
        )
        await state.set_state(Form.main_menu)
        
    elif "انصراف و اصلاح" in message.text:
        q_type = data.get('query_type')
        doc_category = data.get('doc_category')
        doc_subcategory = data.get('doc_subcategory')
        doc_name = f"{doc_category} - {doc_subcategory}" if doc_subcategory else doc_category
        await log_event(
            "کنسل", q_type, message.from_user.full_name, message.from_user.id,
            tracking_code=data.get('tracking_code'), doc_name=doc_name,
            payment_status="کنسل شده توسط کاربر (قبل از پرداخت)"
        )
        await message.answer("لغو گردید. لطفاً مجدداً شروع کنید:", reply_markup=main_menu_kb)
        await state.set_state(Form.main_menu)
