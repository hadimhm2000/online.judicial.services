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
from config import ADMIN_ID, CARD_NUMBER, ACCOUNT_NAME, get_fee
from states import Form
from sheets import append_to_sheet, log_event
from ocr import verify_payment_receipt
from keyboards import (
    restart_kb, accept_rules_kb, flow_type_kb, main_menu_kb, doc_category_kb,
    attachments_kb, cart_kb, pay_kb, confirm_single_kb, confirm_cart_kb,
    admin_login_kb, SUB_MENUS, create_submenu_kb, back_only_kb
)
from lavayeh_handlers import lavayeh_router
from stamp_calc_handlers import stamp_calc_router
from ezhharnameh_handlers import ezhharnameh_router
from file_tools_handlers import file_tools_router, file_tools_entry

router = Router()

# ── include کردن روترها ───────────────────────────────────────────────────────
router.include_router(lavayeh_router)
router.include_router(stamp_calc_router)
router.include_router(ezhharnameh_router)
router.include_router(file_tools_router)


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
@router.callback_query(F.data.startswith("ok_stamp:"))
async def admin_approve_stamp(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    claim_amount = int(parts[2])

    try:
        from stamp_duty import calculate_stamp_duty, format_result_fa
        result = calculate_stamp_duty(claim_amount)
        result_text = format_result_fa(claim_amount, result)

        user_state = runtime_state.dp.fsm.resolve_context(bot, target_user_id, target_user_id)
        user_data = await user_state.get_data()
        photo_path = user_data.get("stamp_photo_path")
        await user_state.clear()

        await bot.send_message(
            target_user_id,
            f"✅ **پرداخت تایید شد (توسط مدیریت).**\n\n{result_text}",
            reply_markup=restart_kb,
            parse_mode="Markdown"
        )

        if photo_path and os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass

        await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n✅ **تایید شد.**")
    except Exception as e:
        logging.error(f"[ADMIN_APPROVE_STAMP] خطا: {e}")
        await bot.send_message(ADMIN_ID, f"⚠️ خطا در تایید محاسبه تمبر کاربر {target_user_id}: {e}")


@router.callback_query(F.data.startswith("no_stamp:"))
async def admin_reject_stamp(callback: CallbackQuery, bot: Bot):
    await callback.answer()
    parts = callback.data.split(":")
    target_user_id = int(parts[1])

    try:
        user_state = runtime_state.dp.fsm.resolve_context(bot, target_user_id, target_user_id)
        user_data = await user_state.get_data()
        photo_path = user_data.get("stamp_photo_path")
        await user_state.clear()

        await bot.send_message(
            target_user_id,
            "❌ رسید پرداخت تایید نشد. لطفاً مجدداً اقدام فرمایید.",
            reply_markup=restart_kb
        )

        if photo_path and os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass

        await callback.message.edit_caption(caption=f"{callback.message.caption}\n\n❌ **رد شد.**")
    except Exception as e:
        logging.error(f"[ADMIN_REJECT_STAMP] خطا: {e}")
        await bot.send_message(ADMIN_ID, f"⚠️ خطا در رد محاسبه تمبر کاربر {target_user_id}: {e}")


@router.message(Form.waiting_for_payment_receipt)
async def process_payment_receipt_text_only(message: types.Message):
    await message.answer("⚠️ لطفاً تصویر فیش واریزی خود را به صورت **عکس (Photo)** ارسال فرمایید:")

# ================= بخش مکالمات تلگرام =================
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
    welcome_text = "با درود و احترام\n🟢 لطفاً پیش از هرگونه اقدام، آیین‌نامه را مطالعه فرمایید:\n🔗 https://forms.gle/UeevWfg5YiDkC5F37\n\n👇 آیا قوانین را تایید می‌نمایید؟"
    await message.answer(welcome_text, reply_markup=accept_rules_kb)
    await state.set_state(Form.waiting_for_rule_acceptance)

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
        await message.answer(payment_msg, reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
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
    await state.update_data(query_type="کد رهگیری", tracking_code=clean_code)
    await message.answer("مربوط به کدام دسته است؟", reply_markup=doc_category_kb)
    await state.set_state(Form.waiting_for_doc_category)

@router.message(Form.waiting_for_doc_category)
async def process_doc_category(message: types.Message, state: FSMContext):
    category = message.text
    if category == "🔙 بازگشت به منوی قبل":
        await message.answer("کد رهگیری را ارسال کنید:", reply_markup=ReplyKeyboardRemove())
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
    need_attachments = "بله" in message.text
    await state.update_data(need_attachments=need_attachments)
    
    data = await state.get_data()
    flow_type = data.get('flow_type', 'single')
    
    if need_attachments:
        await message.answer("⏳ در حال استعلام تعداد پیوست‌های پرونده... لطفاً صبور باشید.", reply_markup=ReplyKeyboardRemove())
        
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
        await message.answer(payment_msg, reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
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
