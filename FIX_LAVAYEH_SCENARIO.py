# ═══════════════════════════════════════════════════════════════════════════════
# راهنمای کامل اصلاح lavayeh_scenario.py
# ═══════════════════════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────────────────────
# مرحله 1: در ابتدای تابع process_lavayeh_task، بعد از استخراج متغیرها
# ───────────────────────────────────────────────────────────────────────────────

# این خط را پیدا کنید:
# tracking_method = data.get("tracking_method", "case_number")

# و بعد از آن این لاگ‌ها را اضافه کنید تا ببینید چه مقادیری دارید:
"""
    # بررسی روش ثبت: شماره پرونده یا شماره بایگانی
    tracking_method = data.get("tracking_method", "case_number")
    archive_number = data.get("lavayeh_archive_number", "")
    branch_name = data.get("lavayeh_branch_name", "")
    branch_code = data.get("lavayeh_branch_code", "")
    
    # ═══ اضافه کنید: لاگ برای دیباگ ═══
    logging.info(f"[LAVAYEH] tracking_method={tracking_method}")
    logging.info(f"[LAVAYEH] archive_number={archive_number}")
    logging.info(f"[LAVAYEH] branch_code={branch_code}")
    logging.info(f"[LAVAYEH] branch_name={branch_name}")
    # ═══════════════════════════════════
"""


# ───────────────────────────────────────────────────────────────────────────────
# مرحله 2: بخش اصلی - بعد از کلیک روی "اطلاعات پرونده"
# ───────────────────────────────────────────────────────────────────────────────

# این قسمت را در کد پیدا کنید:
"""
await _click_step_label(sana_page, "اطلاعات پرونده", bot, user_id)
await resilient_sleep(sana_page, 3, bot, user_id)

# بررسی روش ثبت: شماره پرونده یا شماره بایگانی
if tracking_method == "archive_number":
"""

# و کل بلوک if/else را با کد زیر جایگزین کنید:

"""
await _click_step_label(sana_page, "اطلاعات پرونده", bot, user_id)
await resilient_sleep(sana_page, 3, bot, user_id)

# ═══════════════════════════════════════════════════════════════════════
# بررسی روش ثبت: شماره پرونده یا شماره بایگانی
# ═══════════════════════════════════════════════════════════════════════

logging.info(f"[LAVAYEH] Checking tracking_method: {tracking_method}")

if tracking_method == "archive_number":
    # ═══════════════════════════════════════════════════════════════
    # مسیر شماره بایگانی (اصلاح شده)
    # ═══════════════════════════════════════════════════════════════
    
    logging.info(f"[LAVAYEH] ═══ ARCHIVE NUMBER METHOD STARTED ═══")
    logging.info(f"[LAVAYEH] branch_code={branch_code}, archive_number={archive_number}")
    
    # مرحله 1: کلیک روی رادیو باتن شماره بایگانی (id="rdbCaseInfo2", value="2")
    logging.info(f"[LAVAYEH] Step 1: Clicking radio button rdbCaseInfo2...")
    await sana_page.evaluate('''() => {
        const rdb = document.querySelector('input#rdbCaseInfo2');
        if (rdb) {
            rdb.click();
            rdb.checked = true;
            rdb.dispatchEvent(new Event('change', { bubbles: true }));
            try {
                const scope = angular.element(rdb).scope();
                if (scope) scope.$apply();
            } catch(e) {}
            return true;
        }
        return false;
    }''')
    await resilient_sleep(sana_page, 2, bot, user_id)
    
    # مرحله 2: وارد کردن کد 5 رقمی واحد قضایی (شعبه)
    if branch_code:
        logging.info(f"[LAVAYEH] Step 2: Filling txtCourtCode with {branch_code}...")
        await sana_page.evaluate('''(code) => {
            const inp = document.querySelector('#txtCourtCode');
            if (inp) {
                inp.value = code;
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
                inp.dispatchEvent(new Event('blur', { bubbles: true }));
                try {
                    const scope = angular.element(inp).scope();
                    if (scope && scope.actions && scope.actions.getUnitByCodeWithBranch) {
                        scope.viewModel.unitCode = code;
                        scope.actions.getUnitByCodeWithBranch(code);
                        scope.$apply();
                    }
                } catch(e) {}
            }
        }''', branch_code)
        await resilient_sleep(sana_page, 3, bot, user_id)
    else:
        logging.warning(f"[LAVAYEH] branch_code is empty!")
    
    # مرحله 3: وارد کردن شماره بایگانی
    if archive_number:
        logging.info(f"[LAVAYEH] Step 3: Filling txtCaseArchiveNo with {archive_number}...")
        await sana_page.evaluate('''(num) => {
            const inp = document.querySelector('#txtCaseArchiveNo');
            if (inp) {
                inp.value = num;
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
                try {
                    const scope = angular.element(inp).scope();
                    if (scope) {
                        scope.viewModel.caseArchiveNo = num;
                        scope.$apply();
                    }
                } catch(e) {}
            }
        }''', archive_number)
        await resilient_sleep(sana_page, 2, bot, user_id)
    else:
        logging.warning(f"[LAVAYEH] archive_number is empty!")
    
    # مرحله 4: کلیک روی دکمه صحت‌سنجی (btnAddHst2)
    logging.info(f"[LAVAYEH] Step 4: Clicking validate button (btnAddHst2)...")
    await _click_validate_with_retry_archive(sana_page, bot, user_id)
    await resilient_sleep(sana_page, 10, bot, user_id)
    
    # بررسی موفقیت
    table_ok = await _wait_for_case_table(sana_page, bot, user_id)
    if not table_ok:
        logging.error(f"[LAVAYEH] Archive validation failed!")
        await bot.send_message(
            user_id,
            "⚠️ **استعلام پرونده با خطا مواجه شد.**\n\n"
            "لطفاً موارد زیر را بررسی و اصلاح نمایید:\n"
            "🔢 شماره بایگانی\n"
            "🏛 کد شعبه (5 رقمی)\n\n"
            "سپس مجدداً «ثبت لایحه» را شروع کنید.",
            parse_mode="Markdown"
        )
        await bot.send_message(
            ADMIN_ID, 
            f"❌ [LAVAYEH] صحت‌سنجی بایگانی کاربر {user_id} ناموفق.\n"
            f"branch_code={branch_code}, archive_number={archive_number}"
        )
        runtime_state.active_lavayeh_users.discard(user_id)
        await log_event(
            "خطای سامانه", "لایحه", str(user_id), user_id,
            tracking_code=archive_number, doc_name=title,
            note="صحت‌سنجی شماره بایگانی ناموفق"
        )
        return
    
    logging.info(f"[LAVAYEH] ═══ ARCHIVE NUMBER METHOD SUCCESSFUL ═══")

else:
    # ═══════════════════════════════════════════════════════════════
    # مسیر شماره پرونده (کد قبلی - بدون تغییر)
    # ═══════════════════════════════════════════════════════════════
    
    logging.info(f"[LAVAYEH] ═══ CASE NUMBER METHOD STARTED ═══")
    logging.info(f"[LAVAYEH] tracking_code={tracking_code}, province={province}, row={row_number}")
    
    await _fill_input(sana_page, "#txtCaseNo", tracking_code, bot, user_id)
    await resilient_sleep(sana_page, 1, bot, user_id)
    
    await _fill_input(sana_page, "#txtSubNo", str(row_number), bot, user_id)
    await resilient_sleep(sana_page, 1, bot, user_id)
    
    await _select_province(sana_page, province, bot, user_id)
    await resilient_sleep(sana_page, 2, bot, user_id)
    
    await _click_validate_with_retry(sana_page, bot, user_id)
    await resilient_sleep(sana_page, 10, bot, user_id)
    
    table_ok = await _wait_for_case_table(sana_page, bot, user_id)
    if not table_ok:
        await bot.send_message(
            user_id,
            "⚠️ **استعلام پرونده با خطا مواجه شد.**\n\n"
            "لطفاً موارد زیر را بررسی و اصلاح نمایید:\n"
            "🔢 شماره پرونده\n"
            "🔢 ردیف فرعی\n"
            "🏙 استان\n\n"
            "سپس مجدداً «ثبت لایحه» را شروع کنید.",
            parse_mode="Markdown"
        )
        await bot.send_message(ADMIN_ID, f"❌ [LAVAYEH] صحت‌سنجی پرونده کاربر {user_id} ناموفق.")
        runtime_state.active_lavayeh_users.discard(user_id)
        await log_event(
            "خطای سامانه", "لایحه", str(user_id), user_id,
            tracking_code=tracking_code, doc_name=title,
            note="صحت‌سنجی پرونده ناموفق"
        )
        return
    
    logging.info(f"[LAVAYEH] ═══ CASE NUMBER METHOD SUCCESSFUL ═══")
"""


# ───────────────────────────────────────────────────────────────────────────────
# مرحله 3: تابع _click_validate_with_retry_archive را پیدا و جایگزین کنید
# ───────────────────────────────────────────────────────────────────────────────

async def _click_validate_with_retry_archive(page, bot: Bot, user_id: int):
    """
    کلیک روی دکمه صحت‌سنجی اطلاعات برای شماره بایگانی.
    از دکمه btnAddHst2 استفاده می‌کند.
    """
    for attempt in range(5):
        logging.info(f"[LAVAYEH] _click_validate_with_retry_archive attempt {attempt + 1}")
        
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnAddHst2');
            if (btn && !btn.disabled) {
                btn.click();
                return true;
            }
            return false;
        }''')
        
        if not clicked:
            logging.warning(f"[LAVAYEH] btnAddHst2 not found or disabled")
            await safe_click_by_text(page, "صحت سنجی اطلاعات", bot, user_id)
        
        await asyncio.sleep(12)
        
        closed = await _close_error_popup(page)
        if closed:
            logging.warning(f"[LAVAYEH] Error popup closed, retrying...")
            await asyncio.sleep(5)
            continue
        
        has_table = await page.evaluate('''() => {
            const table = document.querySelector('table tbody tr');
            return table !== null;
        }''')
        
        if has_table:
            logging.info(f"[LAVAYEH] Archive validation successful on attempt {attempt + 1}")
            return
        
        await asyncio.sleep(5)
    
    logging.warning(f"[LAVAYEH] Archive validation failed after 5 attempts")


# ═══════════════════════════════════════════════════════════════════════════════
# تست: بعد از اعمال تغییرات، لاگ باید اینطور باشد:
# ═══════════════════════════════════════════════════════════════════════════════
"""
2026-07-31 23:40:00,000 - INFO - [LAVAYEH] user=509108833 title=لایحه دفاعیه code=None province=None row=None persons=1 attachment_groups=1 images=1
2026-07-31 23:40:00,100 - INFO - [LAVAYEH] tracking_method=archive_number          ← باید archive_number باشد
2026-07-31 23:40:00,100 - INFO - [LAVAYEH] archive_number=9812345                  ← باید مقدار داشته باشد
2026-07-31 23:40:00,100 - INFO - [LAVAYEH] branch_code=12345                       ← باید مقدار داشته باشد
2026-07-31 23:40:00,100 - INFO - [LAVAYEH] branch_name=شعبه اول حقوقی تهران        ← باید مقدار داشته باشد
2026-07-31 23:40:05,000 - INFO - [LAVAYEH] Checking tracking_method: archive_number
2026-07-31 23:40:05,000 - INFO - [LAVAYEH] ═══ ARCHIVE NUMBER METHOD STARTED ═══   ← باید این مسیر را برود
2026-07-31 23:40:05,100 - INFO - [LAVAYEH] Step 1: Clicking radio button rdbCaseInfo2...
2026-07-31 23:40:07,000 - INFO - [LAVAYEH] Step 2: Filling txtCourtCode with 12345...
2026-07-31 23:40:10,000 - INFO - [LAVAYEH] Step 3: Filling txtCaseArchiveNo with 9812345...
2026-07-31 23:40:12,000 - INFO - [LAVAYEH] Step 4: Clicking validate button (btnAddHst2)...
2026-07-31 23:40:22,000 - INFO - [LAVAYEH] ═══ ARCHIVE NUMBER METHOD SUCCESSFUL ═══
"""
