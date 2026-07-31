# ═══════════════════════════════════════════════════════════════════════════════
# 🔥 راه حل قطعی و فوری برای مشکل ثبت لایحه با شماره بایگانی
# ═══════════════════════════════════════════════════════════════════════════════
#
# ❌ مشکل فعلی:
#   - کاربر روش "شماره بایگانی" را انتخاب می‌کند
#   - اما در لاگ می‌بینیم: code=None و کد سراغ #txtCaseNo می‌رود
#   - یعنی tracking_method هنوز "case_number" است!
#
# ✅ دلیل:
#   در lavayeh_handlers.py، متغیر tracking_method در State ذخیره نمی‌شود
#
# ═══════════════════════════════════════════════════════════════════════════════


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  تغییر #1 - در lavayeh_handlers.py                                      ║
# ║  پیدا کنید: وقتی کاربر روش "شماره بایگانی" را انتخاب می‌کند              ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# این تابع را پیدا کنید و اصلاح کنید:

@lavayeh_router.message(Form.lavayeh_tracking_method)
async def lavayeh_tracking_method_handler(message: Message, state: FSMContext):
    text = message.text or ""
    
    if text == "🔙 بازگشت":
        await message.answer("📝 لطفاً عنوان لایحه را انتخاب فرمایید:", reply_markup=lavayeh_title_kb)
        await state.set_state(Form.lavayeh_title)
        return
    
    # ─────────────────────────────────────────────────────────────
    # روش شماره پرونده
    # ─────────────────────────────────────────────────────────────
    if "شماره پرونده" in text or "1️⃣" in text:
        await state.update_data(
            tracking_method="case_number"  # ← این را اضافه کنید
        )
        await message.answer(
            "🔢 لطفاً **شماره پرونده** را وارد کنید:\n_(۱۶ یا ۱۸ رقمی)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_tracking_code)
    
    # ─────────────────────────────────────────────────────────────
    # روش شماره بایگانی
    # ─────────────────────────────────────────────────────────────
    elif "بایگانی" in text or "2️⃣" in text:
        # ═══ مهم: این خط را اضافه کنید ═══
        await state.update_data(
            tracking_method="archive_number"  # ← ← ← مهم! این خط باید باشد!
        )
        # ═══════════════════════════════════
        
        await message.answer(
            "🏛 لطفاً شعبه رسیدگی‌کننده را انتخاب فرمایید:",
            reply_markup=lavayeh_branch_input_method_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.lavayeh_branch_input_method)
    
    else:
        await message.answer("⚠️ لطفاً یکی از گزینه‌ها را انتخاب کنید:")


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  تغییر #2 - در lavayeh_handlers.py (بعد از انتخاب شعبه)                 ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# وقتی کاربر شعبه را از درخت انتخاب می‌کند:

async def save_selected_branch(
    message: Message, 
    state: FSMContext, 
    branch_code: str, 
    branch_name: str, 
    province: str
):
    """ذخیره شعبه انتخاب شده و رفتن به مرحله شماره بایگانی"""
    
    # ═══ مهم: همه این فیلدها را ذخیره کنید ═══
    await state.update_data(
        lavayeh_branch_code=branch_code,      # کد 5 رقمی شعبه
        lavayeh_branch_name=branch_name,      # نام شعبه
        lavayeh_province=province,            # استان (از درخت شعب)
        tracking_method="archive_number",     # ← دوباره ست کنید (محکم کاری)
    )
    # ═══════════════════════════════════════════
    
    await message.answer(
        f"✅ شعبه انتخاب شد:\n"
        f"🏛 **{branch_name}**\n"
        f"🔢 کد شعبه: `{branch_code}`\n\n"
        f"🔢 لطفاً شماره بایگانی پرونده را وارد کنید:",
        reply_markup=back_only_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.lavayeh_archive_number)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  تغییر #3 - در lavayeh_handlers.py (بعد از دریافت شماره بایگانی)        ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

@lavayeh_router.message(Form.lavayeh_archive_number)
async def lavayeh_archive_number_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    
    if message.text == "🔙 بازگشت":
        await message.answer(
            "🏛 لطفاً شعبه رسیدگی‌کننده را انتخاب فرمایید:",
            reply_markup=lavayeh_branch_input_method_kb
        )
        await state.set_state(Form.lavayeh_branch_input_method)
        return
    
    archive_num = _to_en(message.text)
    
    # اعتبارسنجی
    is_valid, result = validate_archive_number(archive_num)
    if not is_valid:
        await message.answer(result, parse_mode="Markdown")
        return
    
    # ═══ مهم: ذخیره شماره بایگانی ═══
    await state.update_data(
        lavayeh_archive_number=archive_num,
        tracking_method="archive_number"  # ← محکم کاری: دوباره ست کنید
    )
    # ═══════════════════════════════════
    
    # دیباگ: لاگ بگیرید تا مطمئن شوید
    data = await state.get_data()
    import logging
    logging.info(f"[HANDLER] archive_number={data.get('lavayeh_archive_number')}")
    logging.info(f"[HANDLER] branch_code={data.get('lavayeh_branch_code')}")
    logging.info(f"[HANDLER] tracking_method={data.get('tracking_method')}")
    
    await message.answer(
        "✅ شماره بایگانی ثبت شد.\n\n"
        "👤 لطفاً نوع شخصیت ارائه‌دهنده لایحه را انتخاب فرمایید:",
        reply_markup=create_person_type_kb(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.lavayeh_person_type)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  تغییر #4 - در lavayeh_handlers.py (تایید نهایی)                        ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# وقتی کاربر تایید نهایی می‌کند و job به صف اضافه می‌شود:

async def add_lavayeh_to_queue(message: Message, state: FSMContext):
    data = await state.get_data()
    
    # ═══ مهم: لاگ بگیرید تا مطمئن شوید داده‌ها درست هستند ═══
    import logging
    logging.info(f"[FINAL] tracking_method = {data.get('tracking_method')}")
    logging.info(f"[FINAL] branch_code = {data.get('lavayeh_branch_code')}")
    logging.info(f"[FINAL] archive_number = {data.get('lavayeh_archive_number')}")
    # ═══════════════════════════════════════════════════════════
    
    # ساخت job با همه فیلدها
    job_data = {
        'user_id': message.from_user.id,
        'lavayeh_title': data.get("lavayeh_title", "لایحه دفاعیه"),
        'tracking_method': data.get("tracking_method", "case_number"),  # ← مهم!
        'lavayeh_persons': data.get("lavayeh_persons", []),
        'lavayeh_text': data.get("lavayeh_text", ""),
        'lavayeh_attachments': data.get("lavayeh_attachments", []),
        
        # فیلدهای شماره بایگانی
        'lavayeh_archive_number': data.get("lavayeh_archive_number", ""),
        'lavayeh_branch_code': data.get("lavayeh_branch_code", ""),
        'lavayeh_branch_name': data.get("lavayeh_branch_name", ""),
        
        # فیلدهای شماره پرونده
        'lavayeh_tracking_code': data.get("lavayeh_tracking_code", ""),
        'lavayeh_province': data.get("lavayeh_province", ""),
        'lavayeh_row_number': data.get("lavayeh_row_number", 1),
    }
    
    # اضافه به صف
    await runtime_state.lavayeh_queue.put(job_data)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  تغییر #5 - در lavayeh_scenario.py (ابتدای تابع)                        ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

async def process_lavayeh_task(data: dict, bot: Bot):
    # ...
    
    # ═══ مهم: این مقادیر را بخوانید ═══
    tracking_method = data.get("tracking_method", "case_number")
    archive_number = data.get("lavayeh_archive_number", "") or ""
    branch_code = data.get("lavayeh_branch_code", "") or ""
    branch_name = data.get("lavayeh_branch_name", "") or ""
    tracking_code = data.get("lavayeh_tracking_code", "") or ""
    province = data.get("lavayeh_province", "") or ""
    row_number = data.get("lavayeh_row_number", 1)
    
    # ═══ لاگ برای دیباگ (این را حتماً نگه دارید) ═══
    logging.info(f"[LAVAYEH] ═══════════════════════════════════")
    logging.info(f"[LAVAYEH] tracking_method = {tracking_method}")
    logging.info(f"[LAVAYEH] branch_code = {branch_code}")
    logging.info(f"[LAVAYEH] archive_number = {archive_number}")
    logging.info(f"[LAVAYEH] tracking_code = {tracking_code}")
    logging.info(f"[LAVAYEH] ═══════════════════════════════════")
    # ════════════════════════════════════════════════
    
    # ...


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  نحوه تست                                                                ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

"""
بعد از اعمال تغییرات:

1. ربات را ریستارت کنید
2. ثبت لایحه را شروع کنید
3. روش "شماره بایگانی" را انتخاب کنید
4. شعبه را انتخاب کنید
5. شماره بایگانی را وارد کنید
6. لاگ را بررسی کنید:

لاگ صحیح باید اینطور باشد:
─────────────────────────────────────────
[HANDLER] archive_number=9812345
[HANDLER] branch_code=12345
[HANDLER] tracking_method=archive_number   ← ← ← باید archive_number باشد!
[FINAL] tracking_method = archive_number   ← ← ← باید archive_number باشد!
[FINAL] branch_code = 12345
[FINAL] archive_number = 9812345
[LAVAYEH] ═══════════════════════════════════
[LAVAYEH] tracking_method = archive_number ← ← ← باید archive_number باشد!
[LAVAYEH] branch_code = 12345
[LAVAYEH] archive_number = 9812345
[LAVAYEH] ═══════════════════════════════════
[LAVAYEH] ═══ ARCHIVE NUMBER METHOD STARTED ═══  ← باید این مسیر را برود
─────────────────────────────────────────

اگر هنوز tracking_method=case_number است،
یعنی در lavayeh_handlers.py خط await state.update_data(tracking_method="archive_number") 
در جای درست اضافه نشده است.
"""
