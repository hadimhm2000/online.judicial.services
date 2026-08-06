"""
سناریوهای اصلی اتوماسیون: ورود دستی به سامانه، پردازش هر تسک و worker پس‌زمینه.
"""
import asyncio
import logging
import os

from aiogram import Bot
from aiogram.types import FSInputFile
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

import runtime_state
from config import ADMIN_ID, DEBUG_LOG_REQUESTS, FEES, get_fee
from sheets import log_event
from keyboards import admin_login_kb, confirm_single_kb, confirm_cart_kb
from browser_helpers import (
    human_delay, force_click_by_text, soft_click_if_exists, human_type,
    handle_session_expired, wait_for_angular_idle, check_and_handle_expiry,
    check_and_handle_load_error, resilient_sleep, goto_url_with_retry,
    safe_click_by_text, safe_type, NavigationResetError,
    wait_for_horizontal_loading_bar,
)
from sana_profile_report import extract_sana_profile, build_sana_profile_pdf

async def _wait_for_mobile_search_table(page, timeout_sec: int = 30) -> bool:
    for _ in range(timeout_sec):
        has_table = await page.evaluate('''() => {
            const tbody = document.querySelector('tbody');
            return tbody !== null && tbody.querySelectorAll('tr').length > 0;
        }''')
        if has_table:
            return True
        await asyncio.sleep(1)
    return False


async def wait_for_manual_login(bot: Bot):
    sana_page = runtime_state.sana_page
    try:
        await sana_page.goto("https://sakha2.adliran.ir/Offices/Index", timeout=60000)
        runtime_state.login_event.clear()
        await bot.send_message(
            ADMIN_ID,
            "⚠️ **نیاز به لاگین دستی:**\nپنجره مرورگر باز شده است. "
            "لطفاً وارد سامانه شوید و دکمه زیر را کلیک نمایید 👇",
            reply_markup=admin_login_kb
        )
        await runtime_state.login_event.wait()
        return True
    except Exception as e:
        return False


async def process_task(data, bot: Bot):
    sana_page = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id = data['user_id']
    query_type = data.get('query_type')
    tracking_code = data.get('tracking_code')
    category = data.get('doc_category')
    subcategory = data.get('doc_subcategory')
    need_attachments = data.get('need_attachments', False)
    task_type = data.get('task_type', 'PRINT')

    # ── سناریوی لایحه ثبت ─────────────────────────────────────────────────
    if task_type == "LAVAYEH_SUBMIT":
        from lavayeh_scenario import process_lavayeh_task
        await process_lavayeh_task(data, bot)
        return

    # ── سناریوی اعلام وکالت ────────────────────────────────────────────────
    if task_type == "EALAM_VAKALAHT_SUBMIT":
        from ealam_vakalaht_scenario import process_ealam_vakalaht_task
        await process_ealam_vakalaht_task(data, bot)
        return

    # ── سناریوی ثبت اظهارنامه ─────────────────────────────────────────────
    if task_type == "EZHHARNAMEH_SUBMIT":
        from ezhharnameh_scenario import process_ezhharnameh_task
        await process_ezhharnameh_task(data, bot)
        return

    # ── سناریوی ارسال کد امضا ─────────────────────────────────────────────
    if task_type == "LAVAYEH_SEND_SIGN_CODE":
        await _process_lavayeh_send_sign_code(data, bot)
        return

    # ── سناریوی ثبت کد امضا ───────────────────────────────────────────────
    if task_type == "LAVAYEH_SUBMIT_SIGN":
        await _process_lavayeh_submit_sign(data, bot)
        return

    # ── سناریوی ارسال کد امضا اظهارنامه ────────────────────────────────────
    if task_type == "EZHHARNAMEH_SEND_SIGN_CODE":
        await _process_ezhharnameh_send_sign_code(data, bot)
        return

    # ── سناریوی ثبت کد امضا اظهارنامه ────────────────────────────────────
    if task_type == "EZHHARNAMEH_SUBMIT_SIGN":
        await _process_ezhharnameh_submit_sign(data, bot)
        return

    max_task_attempts = 3
    for task_attempt in range(max_task_attempts):
        try:
            if (await sana_page.locator('text="خطای دسترسی کاربر!"').is_visible() or
                    await sana_page.locator("text=ورود قبلی منقضی").is_visible()):
                await bot.send_message(ADMIN_ID, "⚠️ نشست سامانه منقضی شده است.")
                await wait_for_manual_login(bot)

            success = await goto_url_with_retry(
                sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
            )
            if not success:
                return

            await human_delay(4.0, 6.0)

            # ────────────────────────────────────────────────────────────────
            # سناریوی ۱: استعلام شماره تماس
            # ────────────────────────────────────────────────────────────────
            if query_type == "شماره تماس":
                phone_number = tracking_code
                await bot.send_message(ADMIN_ID, f"🔄 شروع استخراج اشخاص برای موبایل {phone_number}...")

                await safe_click_by_text(sana_page, "ارایه و پیگیری شکواییه", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                await safe_type(sana_page, '#txtPetitionNo, #billNo', "1400220968161114", bot, user_id)
                await sana_page.evaluate('''() => {
                    const exactBtn = document.querySelector('#btnGetJSSPetition') || document.querySelector('#btnGetJSSBill');
                    if(exactBtn) exactBtn.click();
                }''')
                await resilient_sleep(sana_page, 8, bot, user_id)

                await sana_page.evaluate('''() => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const closeBtn = btns.find(b => (b.innerText && b.innerText.trim() === "بستن") || b.classList.contains("confirm"));
                    if(closeBtn) closeBtn.click();
                }''')
                await resilient_sleep(sana_page, 2, bot, user_id)

                await safe_click_by_text(sana_page, "ثبت و اصلاح شكوائيه", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)
                await safe_click_by_text(sana_page, "مشتكي عنه", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                await sana_page.evaluate('''() => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const btn = btns.find(b => b.hasAttribute('tooltip') && b.getAttribute('tooltip').includes("خوانده یابی"));
                    if(btn) btn.click();
                }''')
                await resilient_sleep(sana_page, 3, bot, user_id)

                await sana_page.evaluate('''() => {
                    const radio = document.querySelector('#searchPersonTypeByMobileNo');
                    if(radio) radio.click();
                }''')
                await safe_type(sana_page, '#txtMobileNoFromSearch', phone_number, bot, user_id)

                search_clicked = await sana_page.evaluate('''() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const searchBtn = buttons.find(b => b.innerText && b.innerText.trim().includes("جستجوی شماره همراه"));
                    if (searchBtn) { searchBtn.click(); return true; }
                    return false;
                }''')
                if not search_clicked:
                    await safe_click_by_text(sana_page, "جستجوی شماره همراه", bot, user_id)

                # منتظر ناپدید شدن لودینگ افقی بالای صفحه
                await asyncio.sleep(2)
                await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=30)

                # بررسی وجود پیام خطای ثنا (عدم ثبت شماره همراه)
                await asyncio.sleep(3)
                alert_message = await sana_page.evaluate('''() => {
                    const alerts = document.querySelectorAll('div.alert-info, div.alert-dismissable');
                    for (let alert of alerts) {
                        const msgDiv = alert.querySelector('div[ng-bind-html]');
                        if (msgDiv && msgDiv.innerText) {
                            const text = msgDiv.innerText.trim();
                            if (text.includes('پایگاه داده ثنا') && text.includes('ثبت نشده است')) {
                                return text;
                            }
                        }
                    }
                    return null;
                }''')
                
                if alert_message:
                    logging.warning(f"[PHONE_SEARCH] پیام خطای ثنا برای شماره {phone_number}: {alert_message}")
                    await bot.send_message(
                        user_id,
                        f"⚠️ **پیام سامانه:**\\n\\n{alert_message}\\n\\n"
                        "فرآیند متوقف شد.",
                        parse_mode="Markdown"
                    )
                    await bot.send_message(ADMIN_ID, f"⚠️ [PHONE_SEARCH] خطای ثنا برای {phone_number} (کاربر {user_id}): {alert_message}")
                    return

                table_ready = await _wait_for_mobile_search_table(sana_page, timeout_sec=30)
                if not table_ready:
                    retry_clicked = await sana_page.evaluate('''() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const searchBtn = buttons.find(b => b.innerText && b.innerText.trim().includes("جستجوی شماره همراه"));
                        if (searchBtn) { searchBtn.click(); return true; }
                        return false;
                    }''')
                    if not retry_clicked:
                        await safe_click_by_text(sana_page, "جستجوی شماره همراه", bot, user_id)
                    # منتظر ناپدید شدن لودینگ
                    await asyncio.sleep(2)
                    await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=30)
                    table_ready = await _wait_for_mobile_search_table(sana_page, timeout_sec=30)

                if not table_ready:
                    await bot.send_message(
                        user_id,
                        f"⚠️ **استعلام شماره تماس {phone_number} با تاخیر سامانه مواجه شد و نتیجه‌ای دریافت نشد.**\n\n"
                        "لطفاً کمی بعد دوباره تلاش کنید.",
                        parse_mode="Markdown"
                    )
                    await bot.send_message(ADMIN_ID, f"⚠️ [PHONE_SEARCH] جدول نتایج برای موبایل {phone_number} (کاربر {user_id}) حتی بعد از تلاش دوم ظاهر نشد.")
                    return

                persons = await sana_page.evaluate('''() => {
                    function toEng(str) {
                        const p = ['۰','۱','۲','۳','۴','۵','۶','۷','۸','۹'];
                        const a = ['٠','١','٢','٣','٤','٥','٦','٧','٨','٩'];
                        let res = str;
                        for(let i=0; i<10; i++) {
                            res = res.split(p[i]).join(i).split(a[i]).join(i);
                        }
                        return res;
                    }
                    const rows = Array.from(document.querySelectorAll('tbody tr'));
                    const data = [];
                    rows.forEach(tr => {
                        const tds = tr.querySelectorAll('td');
                        if(tds.length > 5) {
                            let nat_id = "";
                            for(let td of tds) {
                                const text = toEng(td.innerText.trim());
                                if(/^[0-9]{10}$/.test(text)) nat_id = text;
                            }
                            if(nat_id) data.push({nat_id: nat_id});
                        }
                    });
                    return data;
                }''')

                await safe_click_by_text(sana_page, "بستن", bot, user_id)
                await resilient_sleep(sana_page, 2, bot, user_id)
                if not persons:
                    await bot.send_message(user_id, f"❌ برای شماره تماس {phone_number} هیچ شخصی یافت نشد.")
                    return

                await bot.send_message(ADMIN_ID, f"✅ تعداد {len(persons)} شخص یافت شد.")

                for idx, person in enumerate(persons):
                    nat_id = person['nat_id']
                    try:
                        print_url = f"https://sakha2.adliran.ir/Report/RealPersonPrint.aspx?no={nat_id}"
                        success_print = await goto_url_with_retry(sana_page, print_url, bot, user_id)
                        if not success_print:
                            return
                        await check_and_handle_expiry(sana_page, bot, user_id)
                        try:
                            await sana_page.wait_for_selector('text=شناسنامه', timeout=15000)
                            await asyncio.sleep(2)
                        except Exception:
                            await asyncio.sleep(5)

                        # ── استخراج تمیز داده (عکس + اطلاعات) از صفحه‌ی چاپ ──
                        # توجه: صفحه‌ی اصلی sana_page اصلاً دست‌کاری نمی‌شود؛
                        # فقط داده خوانده می‌شود و در یک صفحه‌ی جدید و تمیز رندر
                        # و پرینت می‌گردد (مستقل از لوگو/نکات امنیتی/فوتر و ...).
                        profile_data = await extract_sana_profile(sana_page)

                        if not profile_data:
                            await bot.send_message(
                                ADMIN_ID,
                                f"⚠️ استخراج اطلاعات پروفایل {nat_id} ناموفق بود (ساختار صفحه یافت نشد)."
                            )
                        else:
                            pdf_path = f"report_phone_{phone_number}_{idx}.pdf"
                            built = await build_sana_profile_pdf(
                                browser_context, profile_data, pdf_path, national_id=nat_id
                            )
                            if built and os.path.exists(pdf_path):
                                doc = FSInputFile(pdf_path)
                                await bot.send_document(
                                    user_id, document=doc, caption=f"📄 مشخصات ثنا (پروفایل {idx+1})"
                                )
                                os.remove(pdf_path)
                            else:
                                await bot.send_message(
                                    ADMIN_ID, f"⚠️ ساخت PDF برای پروفایل {nat_id} ناموفق بود."
                                )

                        await sana_page.go_back()
                        await asyncio.sleep(3)

                    except Exception as e:
                        if isinstance(e, NavigationResetError) or "Session expired" in str(e):
                            raise e
                        await bot.send_message(ADMIN_ID, f"❌ خطا در پروفایل {nat_id}: {e}")

                await sana_page.goto("https://sakha2.adliran.ir/Offices/Index")
                await bot.send_message(ADMIN_ID, f"✅ پردازش موبایل {phone_number} تمام شد.")
                return

            # ────────────────────────────────────────────────────────────────
            # سناریوی ۳: استعلام کد ملی
            # ────────────────────────────────────────────────────────────────
            elif query_type == "کد ملی":
                national_id = tracking_code
                await bot.send_message(ADMIN_ID, f"🔄 استعلام ثنا برای کد ملی {national_id}...")

                print_url = f"https://sakha2.adliran.ir/Report/RealPersonPrint.aspx?no={national_id}"
                success_print = await goto_url_with_retry(sana_page, print_url, bot, user_id)
                if not success_print:
                    return
                await asyncio.sleep(3)
                await check_and_handle_expiry(sana_page, bot, user_id)

                has_error = await sana_page.evaluate('''() => {
                    const text = document.body.innerText || "";
                    return text.includes("اطلاعاتی با این شماره ملی ثبت نشده است") || text.includes("ثبت نشده است");
                }''')

                if has_error:
                    await bot.send_message(user_id, f"❌ کدملی `{national_id}` فاقد ثبت‌نام ثنا می‌باشد.")
                    await sana_page.goto("https://sakha2.adliran.ir/Offices/Index")
                    return

                try:
                    await sana_page.wait_for_selector('text=شناسنامه', timeout=15000)
                    await asyncio.sleep(2)
                except Exception:
                    await asyncio.sleep(5)

                # ── استخراج تمیز داده (عکس + اطلاعات) از صفحه‌ی چاپ ──
                # صفحه‌ی اصلی sana_page اصلاً دست‌کاری نمی‌شود؛ فقط داده خوانده
                # می‌شود و در یک صفحه‌ی جدید و کاملاً تمیز رندر و پرینت می‌گردد
                # (مستقل از لوگو/نکات امنیتی/فوتر/افزونه‌های مرورگر و غیره).
                profile_data = await extract_sana_profile(sana_page)

                if not profile_data:
                    await bot.send_message(
                        user_id, f"❌ استخراج اطلاعات ثنا برای کدملی `{national_id}` ناموفق بود."
                    )
                    await sana_page.goto("https://sakha2.adliran.ir/Offices/Index")
                    return

                pdf_path = f"report_national_{national_id}.pdf"
                built = await build_sana_profile_pdf(
                    browser_context, profile_data, pdf_path, national_id=national_id
                )

                if built and os.path.exists(pdf_path):
                    doc = FSInputFile(pdf_path)
                    await bot.send_document(user_id, document=doc, caption=f"📄 مشخصات ثنا برای کدملی: `{national_id}`")
                    os.remove(pdf_path)
                else:
                    await bot.send_message(
                        user_id, f"❌ ساخت PDF برای کدملی `{national_id}` ناموفق بود."
                    )

                await sana_page.goto("https://sakha2.adliran.ir/Offices/Index")
                await bot.send_message(ADMIN_ID, f"✅ پردازش کد ملی {national_id} تمام شد.")
                return

            # ────────────────────────────────────────────────────────────────
            # سناریوی ۲: استعلام کد رهگیری پرونده
            # ────────────────────────────────────────────────────────────────
            elif query_type == "کد رهگیری":
                from states import Form

                if category == "لایحه":
                    await safe_click_by_text(sana_page, "ارایه و پیگیری لایحه", bot, user_id)
                elif category == "اظهارنامه":
                    await safe_click_by_text(sana_page, "ارایه و پیگیری اظهارنامه", bot, user_id)
                elif category == "شکواییه":
                    await safe_click_by_text(sana_page, "ارایه و پیگیری شکواییه", bot, user_id)
                elif category == "دادخواست بدوی":
                    await safe_click_by_text(sana_page, "ارایه و پیگیری دادخواست", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await safe_click_by_text(sana_page, "دادخواست بدوی", bot, user_id)
                elif category == "دعاوی دادگاههای صلح":
                    await safe_click_by_text(sana_page, "دعاوی دادگاههای صلح", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await safe_click_by_text(sana_page, "دعاوی حقوقی", bot, user_id)
                elif category == "دعاوی اعتراضی":
                    await safe_click_by_text(sana_page, "دعاوی اعتراضی", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await safe_click_by_text(sana_page, subcategory, bot, user_id)
                elif category == "دعاوی طاری":
                    await safe_click_by_text(sana_page, "ارایه و پیگیری دعاوی طاری", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await safe_click_by_text(sana_page, subcategory, bot, user_id)
                elif category == "دیوان عدالت اداری":
                    await safe_click_by_text(sana_page, "دیوان عدالت اداری", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await safe_click_by_text(sana_page, subcategory, bot, user_id)
                elif category == "شورای حل اختلاف":
                    await safe_click_by_text(sana_page, "شورای حل اختلاف (صلح و سازش)", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await safe_click_by_text(sana_page, subcategory, bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                if category == "لایحه" or (
                    category == "دیوان عدالت اداری" and subcategory == "ارایه و پیگیری لایحه"
                ):
                    await safe_click_by_text(sana_page, "جستجوی لایحه", bot, user_id)
                    await resilient_sleep(sana_page, 4, bot, user_id)

                try:
                    await sana_page.wait_for_selector('#txtPetitionNo, #billNo', timeout=15000)
                except Exception:
                    raise Exception("صفحه کارتابل لود نشد.")

                selector = '#txtPetitionNo, #billNo, input[name="txtPetitionNo"], input[name="billNo"]'
                await safe_type(sana_page, selector, tracking_code, bot, user_id)
                await resilient_sleep(sana_page, 2, bot, user_id)

                if category == "لایحه" or (
                    category == "دیوان عدالت اداری" and subcategory == "ارایه و پیگیری لایحه"
                ):
                    await soft_click_if_exists(sana_page, "بازیابی")
                    await resilient_sleep(sana_page, 2, bot, user_id)

                await sana_page.evaluate('''() => {
                    const exactBtn = document.querySelector('#btnGetJSSPetition');
                    if (exactBtn) { exactBtn.click(); return; }
                    const btns = Array.from(document.querySelectorAll('button'));
                    const searchBtn = btns.find(b => b.innerText && b.innerText.includes("جستجو"));
                    if (searchBtn) searchBtn.click();
                }''')

                doc_name = subcategory if subcategory else category
                await bot.send_message(ADMIN_ID, f"⏳ استعلام «{doc_name}»...")

                # منتظر ناپدید شدن لودینگ افقی بالای صفحه
                await asyncio.sleep(3)
                await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=60)

                if (
                    await sana_page.locator('text="لطفا اطلاعات خواسته شده را به درستی وارد نمایید"').is_visible()
                    or await sana_page.locator('button:has-text("بستن")').is_visible()
                ):
                    await safe_click_by_text(sana_page, "بستن", bot, user_id)
                    await resilient_sleep(sana_page, 2, bot, user_id)
                    await sana_page.evaluate('''() => {
                        const exactBtn = document.querySelector('#btnGetJSSPetition');
                        if (exactBtn) { exactBtn.click(); return; }
                        const btns = Array.from(document.querySelectorAll('button'));
                        const searchBtn = btns.find(b => b.innerText && b.innerText.includes("جستجو"));
                        if (searchBtn) searchBtn.click();
                    }''')
                    # منتظر ناپدید شدن لودینگ
                    await asyncio.sleep(3)
                    await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=60)

                await sana_page.evaluate('''() => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const closeBtn = btns.find(b =>
                        (b.innerText && b.innerText.trim() === "بستن") || b.classList.contains("confirm")
                    );
                    if(closeBtn) closeBtn.click();
                }''')
                await resilient_sleep(sana_page, 2, bot, user_id)

                if (
                    await sana_page.locator(".alert-danger").is_visible()
                    or await sana_page.locator('text="اطلاعاتی یافت نشد"').is_visible()
                ):
                    await bot.send_message(user_id, f"❌ پرونده‌ای با کد `{tracking_code}` یافت نگردید.")
                    return

                # ── PRE_CHECK ─────────────────────────────────────────────
                if task_type == 'PRE_CHECK':
                    await safe_click_by_text(sana_page, "منضمات", bot, user_id)
                    await resilient_sleep(sana_page, 5, bot, user_id)

                    total_attachments_count = await sana_page.evaluate('''() => {
                        const tbody = document.querySelector('tbody');
                        if (!tbody) return 0;
                        const trs = Array.from(tbody.querySelectorAll('tr'));
                        const isIgnored = (title) => {
                            const t = title.replace(/\\u200c/g, ' ');
                            return t.includes("قرارداد الکترونیک") &&
                                   (t.includes("وکالت نامه") || t.includes("وکالتنامه"));
                        };
                        const rows_data = trs.map((tr, index) => {
                            const tds = tr.querySelectorAll('td');
                            if (tds.length >= 6) {
                                const title = tds[2].innerText.trim();
                                const countText = tds[5].innerText.trim();
                                const count = parseInt(countText) || 0;
                                return { index, title, count };
                            }
                            return null;
                        }).filter(r => r !== null && !isIgnored(r.title));
                        const has_sig = rows_data.length > 0 &&
                            (rows_data[0].title.includes("امضا") || rows_data[0].title.includes("امضاء"));
                        const start = has_sig ? 1 : 0;
                        let sum = 0;
                        for (let i = start; i < rows_data.length; i++) { sum += rows_data[i].count; }
                        return sum;
                    }''')

                    calculated_fee = FEES["کد رهگیری با منضمات"] + total_attachments_count * 5000

                    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)
                    user_data = await user_state.get_data()
                    flow_type = user_data.get('flow_type', 'single')

                    await user_state.update_data(
                        payment_fee=calculated_fee,
                        need_attachments=True,
                        total_attachments=total_attachments_count
                    )

                    from states import Form
                    await user_state.set_state(Form.confirm_opt)

                    kb = confirm_single_kb if flow_type == "single" else confirm_cart_kb
                    action_text = (
                        "تایید نهایی و دریافت فاکتور پرداخت"
                        if flow_type == "single"
                        else "تایید و افزودن این مورد به سبد خرید"
                    )

                    confirm_msg = (
                        f"📋 **اطلاعات استعلام با منضمات:**\n\n"
                        f"کد پیگیری: `{tracking_code}`\n"
                        f"سند: **{doc_name}**\n"
                        f"📎 تعداد پیوست: **{total_attachments_count} برگ**\n"
                        f"💰 فاکتور: ۵۰,۰۰۰ + ({total_attachments_count} × ۵,۰۰۰) = **{calculated_fee:,} تومان**\n\n"
                        f"آیا {action_text} فرمایید؟"
                    )
                    await bot.send_message(user_id, confirm_msg, reply_markup=kb, parse_mode="Markdown")
                    return

                # ── PRINT ─────────────────────────────────────────────────
                else:
                    saved_attachments = []
                    try:
                        async def click_print_box():
                            await sana_page.evaluate('''() => {
                                const headings = Array.from(document.querySelectorAll('h5, button, a'));
                                const printHeading = headings.find(h => h.innerText && (
                                    h.innerText.includes("چاپ اوليه") ||
                                    h.innerText.includes("چاپ اولیه") ||
                                    h.innerText.includes("چاپ")
                                ));
                                if (printHeading) {
                                    const box = printHeading.closest('.box');
                                    if (box) box.click();
                                    else printHeading.click();
                                }
                            }''')

                        async with browser_context.expect_page(timeout=15000) as new_page_info:
                            await click_print_box()

                        print_page = await new_page_info.value
                        await print_page.wait_for_load_state()
                        await resilient_sleep(print_page, 8, bot, user_id)
                        await check_and_handle_expiry(print_page, bot, user_id)

                        pdf_path = f"report_{tracking_code}.pdf"
                        await print_page.pdf(path=pdf_path, format="A4")
                        await print_page.close()

                        if need_attachments:
                            saved_attachments.append((pdf_path, f"📄 استعلام کد پیگیری: `{tracking_code}`"))
                        else:
                            doc = FSInputFile(pdf_path)
                            await bot.send_document(user_id, document=doc, caption=f"📄 استعلام کد پیگیری: `{tracking_code}`")
                            os.remove(pdf_path)

                    except Exception as print_err:
                        logging.error(f"خطا در چاپ: {print_err}")
                        await bot.send_message(user_id, "⚠️ چاپ پرونده با خطا مواجه شد.")
                        raise Exception("Failed to print the document.")

                    if need_attachments:
                        await safe_click_by_text(sana_page, "منضمات", bot, user_id)
                        await resilient_sleep(sana_page, 5, bot, user_id)

                        rows_data = await sana_page.evaluate('''() => {
                            const tbody = document.querySelector('tbody');
                            if (!tbody) return [];
                            const trs = Array.from(tbody.querySelectorAll('tr'));
                            return trs.map((tr, index) => {
                                const tds = tr.querySelectorAll('td');
                                if (tds.length >= 6) {
                                    const title = tds[2].innerText.trim();
                                    const countText = tds[5].innerText.trim();
                                    const count = parseInt(countText) || 0;
                                    return { index, title, count };
                                }
                                return null;
                            }).filter(r => r !== null);
                        }''')

                        def _is_ignored_attachment(title: str) -> bool:
                            t = (title or "").replace("\u200c", " ")
                            return "قرارداد الکترونیک" in t and ("وکالت نامه" in t or "وکالتنامه" in t)

                        rows_data = [r for r in rows_data if not _is_ignored_attachment(r.get('title', ''))]

                        has_signature_row = (
                            len(rows_data) > 0 and
                            ("امضا" in rows_data[0]['title'] or "امضاء" in rows_data[0]['title'])
                        )
                        data_rows = rows_data[1:] if has_signature_row else rows_data
                        real_rows = [r for r in data_rows if r['count'] > 0]

                        if not real_rows:
                            for path, caption in saved_attachments:
                                if os.path.exists(path):
                                    doc = FSInputFile(path)
                                    await bot.send_document(user_id, document=doc, caption=caption)
                                    os.remove(path)
                            await bot.send_message(user_id, "📄 این درخواست فاقد پیوست واقعی است.")
                        else:
                            await bot.send_message(
                                user_id,
                                f"📎 تعداد {len(real_rows)} ردیف پیوست کشف شد. در حال استخراج..."
                            )
                            try:
                                for r in real_rows:
                                    row_idx = r['index']
                                    row_title = r['title']
                                    row_count = r['count']

                                    await sana_page.evaluate('window.scrollTo(0, 0)')
                                    await resilient_sleep(sana_page, 2, bot, user_id)

                                    await sana_page.evaluate('''(idx) => {
                                        const tbody = document.querySelector('tbody');
                                        if (tbody) {
                                            const trs = tbody.querySelectorAll('tr');
                                            if (trs.length > idx) {
                                                const btn = trs[idx].querySelector('button[ng-click*="editDocument"]');
                                                if (btn) btn.click();
                                            }
                                        }
                                    }''', row_idx)
                                    await resilient_sleep(sana_page, 5, bot, user_id)

                                    btn_count = await sana_page.evaluate('''() => {
                                        const btns = Array.from(document.querySelectorAll('button'));
                                        return btns.filter(b => b.innerText && b.innerText.includes("نمایش و چاپ")).length;
                                    }''')

                                    if btn_count == 0:
                                        await bot.send_message(
                                            user_id, f"⚠️ فایل پیوستی در بخش «{row_title}» یافت نشد."
                                        )
                                    else:
                                        for btn_idx in range(btn_count):
                                            btn_success = False
                                            for attempt in range(4):
                                                att_page = None
                                                try:
                                                    async with browser_context.expect_page(timeout=20000) as att_page_info:
                                                        await sana_page.evaluate(f'''(b_idx) => {{
                                                            const btns = Array.from(document.querySelectorAll('button'));
                                                            const printBtns = btns.filter(b => b.innerText && b.innerText.includes("نمایش و چاپ"));
                                                            if (printBtns.length > b_idx) {{ printBtns[b_idx].click(); }}
                                                        }}''', btn_idx)

                                                    att_page = await att_page_info.value
                                                    await resilient_sleep(att_page, 5, bot, user_id)
                                                    await check_and_handle_expiry(att_page, bot, user_id)

                                                    import base64
                                                    pdf_data_base64 = await att_page.evaluate('''async () => {
                                                        const embed = document.querySelector('embed[type="application/pdf"], embed[src*="pdf"], iframe[src*="pdf"]');
                                                        let pdfUrl = null;
                                                        if (embed && embed.src) pdfUrl = embed.src;
                                                        else {
                                                            const iframe = document.querySelector('iframe');
                                                            if (iframe && iframe.src) pdfUrl = iframe.src;
                                                        }
                                                        if (pdfUrl) {
                                                            try {
                                                                const response = await fetch(pdfUrl);
                                                                const blob = await response.blob();
                                                                return new Promise((resolve, reject) => {
                                                                    const reader = new FileReader();
                                                                    reader.onloadend = () => resolve(reader.result.split(',')[1]);
                                                                    reader.onerror = reject;
                                                                    reader.readAsDataURL(blob);
                                                                });
                                                            } catch(e) { return null; }
                                                        }
                                                        return null;
                                                    }''')

                                                    att_pdf_path = f"attachment_{tracking_code}_{row_idx}_{btn_idx}.pdf"
                                                    if pdf_data_base64:
                                                        with open(att_pdf_path, 'wb') as pdf_file:
                                                            pdf_file.write(base64.b64decode(pdf_data_base64))
                                                    else:
                                                        await resilient_sleep(att_page, 8, bot, user_id)
                                                        await att_page.pdf(path=att_pdf_path, format="A4")

                                                    await att_page.close()
                                                    saved_attachments.append(
                                                        (att_pdf_path, f"📎 پیوست {btn_idx+1} — «{row_title}»")
                                                    )
                                                    btn_success = True
                                                    break

                                                except Exception as att_err:
                                                    if "Session expired" in str(att_err):
                                                        raise att_err
                                                    logging.error(f"خطا در پیوست {btn_idx}: {att_err}")
                                                    try:
                                                        await att_page.close()
                                                    except Exception:
                                                        pass
                                                    await asyncio.sleep(3)

                                            if not btn_success:
                                                await bot.send_message(
                                                    user_id, f"❌ پیوست {btn_idx+1} از «{row_title}» ناموفق."
                                                )

                                    await sana_page.evaluate('window.scrollTo(0, 0)')
                                    await resilient_sleep(sana_page, 2.5, bot, user_id)

                                if saved_attachments:
                                    await bot.send_message(user_id, f"📥 در حال ارسال {len(saved_attachments)} فایل...")
                                    for path, caption in saved_attachments:
                                        try:
                                            if os.path.exists(path):
                                                att_doc = FSInputFile(path)
                                                await bot.send_document(user_id, document=att_doc, caption=caption)
                                                os.remove(path)
                                        except Exception as send_err:
                                            logging.error(f"خطا در ارسال {path}: {send_err}")

                                await bot.send_message(user_id, "✅ استخراج منضمات کاملاً تمام شد.")

                            except Exception as loop_err:
                                if "Session expired" in str(loop_err):
                                    raise loop_err
                                for path, _ in saved_attachments:
                                    try:
                                        if os.path.exists(path):
                                            os.remove(path)
                                    except Exception:
                                        pass
                                raise loop_err
                    return

            break

        except Exception as task_err:
            logging.error(f"تلاش {task_attempt+1} ناموفق: {task_err}")
            if task_attempt < max_task_attempts - 1:
                await bot.send_message(ADMIN_ID, f"⚠️ فرآیند با خطا مواجه شد. تلاش مجدد {task_attempt+2}...")
                await sana_page.reload()
                await asyncio.sleep(5)
            else:
                await bot.send_message(
                    user_id,
                    "⚠️ سامانه قضایی با اختلال مواجه است. لطفاً ۳۰ دقیقه دیگر مجدداً تلاش فرمایید."
                )
                doc_name = f"{category} - {subcategory}" if subcategory else category
                await log_event(
                    "خطای سامانه", query_type, str(user_id), user_id,
                    tracking_code=tracking_code or "", doc_name=doc_name or "",
                    note=f"پس از {max_task_attempts} تلاش: {str(task_err)[:200]}"
                )


# ══════════════════════════════════════════════════════════════════════════════
# پردازش ارسال کد امضا
# ══════════════════════════════════════════════════════════════════════════════
async def _process_lavayeh_send_sign_code(data: dict, bot: Bot):
    user_id = data["user_id"]
    tracking_code = data.get("tracking_code", "")
    phase = data.get("phase", "navigate")

    from lavayeh_sign_scenario import (
        navigate_to_sign_page,
        get_signable_persons,
        send_sign_code_for_person,
    )
    from lavayeh_sign_handlers import (
        on_lavayeh_sign_persons_loaded,
        on_lavayeh_sign_code_sent_success,
        on_lavayeh_sign_code_sent_failure,
    )

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)

    try:
        if phase == "navigate":
            # فاز ۱: ناوبری به صفحه امضا و دریافت لیست اشخاص
            await bot.send_message(ADMIN_ID, f"🔄 [SIGN] ناوبری به صفحه امضا برای کاربر {user_id}")
            nav_ok = await navigate_to_sign_page(bot, user_id, tracking_code)

            if not nav_ok:
                await on_lavayeh_sign_code_sent_failure(bot, user_id, user_state)
                await bot.send_message(ADMIN_ID, f"❌ [SIGN] ناوبری ناموفق برای کاربر {user_id}")
                return

            # دریافت لیست اشخاص
            persons = await get_signable_persons(bot, user_id)
            await on_lavayeh_sign_persons_loaded(bot, user_id, persons, user_state)

        elif phase == "send_code":
            # فاز ۲: ارسال کد برای شخص انتخاب‌شده
            target_row_indices = data.get("target_row_indices", [])
            await bot.send_message(ADMIN_ID, f"🔄 [SIGN] ارسال کد امضا برای کاربر {user_id}")

            sign_info = runtime_state.pending_lavayeh_sign.get(user_id, {})
            all_persons = sign_info.get("sign_persons", [])

            results = []
            for row_idx in target_row_indices:
                person = next((p for p in all_persons if p["idx"] == row_idx), None)
                person_name = person.get("name", f"شخص {row_idx + 1}") if person else f"شخص {row_idx + 1}"
                success = await send_sign_code_for_person(bot, user_id, row_idx, person_name)
                results.append({
                    "idx": row_idx,
                    "name": person_name,
                    "person_type": person.get("personType", "") if person else "",
                    "sent": success,
                })
                # فاصله ۳۰ ثانیه بین ارسال کد هر شخص
                if row_idx != target_row_indices[-1]:
                    await asyncio.sleep(30)

            any_sent = any(r["sent"] for r in results)
            if any_sent:
                await on_lavayeh_sign_code_sent_success(bot, user_id, results, user_state)
                await bot.send_message(ADMIN_ID, f"✅ [SIGN] کد امضا برای کاربر {user_id} ارسال شد.")
            else:
                await on_lavayeh_sign_code_sent_failure(bot, user_id, user_state)
                await bot.send_message(ADMIN_ID, f"❌ [SIGN] ارسال کد امضا برای کاربر {user_id} ناموفق.")

    except Exception as e:
        logging.error(f"[SIGN] خطا در _process_lavayeh_send_sign_code: {e}")
        await on_lavayeh_sign_code_sent_failure(bot, user_id, user_state)


# ══════════════════════════════════════════════════════════════════════════════
# پردازش ثبت کد امضا
# ══════════════════════════════════════════════════════════════════════════════
async def _process_lavayeh_submit_sign(data: dict, bot: Bot):
    user_id = data["user_id"]
    tracking_code = data.get("tracking_code", "")
    row_idx = data.get("row_idx", 0)
    code = data.get("code", "")

    from lavayeh_sign_scenario import submit_sign_code_for_person
    from lavayeh_sign_handlers import (
        on_lavayeh_sign_submit_success,
        on_lavayeh_sign_submit_failure,
        on_lavayeh_sign_wrong_code,
    )

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)

    try:
        await bot.send_message(ADMIN_ID, f"🔄 [SIGN] ثبت امضا برای کاربر {user_id}")
        result = await submit_sign_code_for_person(
            bot, user_id, row_idx, code
        )

        if result["success"]:
            await on_lavayeh_sign_submit_success(bot, user_id, row_idx, user_state)
            await bot.send_message(ADMIN_ID, f"✅ [SIGN] امضای لایحه کاربر {user_id} موفق (ردیف {row_idx}).")
        else:
            error = result.get("error", "")
            if "wrong_code" in error:
                await on_lavayeh_sign_wrong_code(bot, user_id, row_idx, user_state)
            else:
                await on_lavayeh_sign_submit_failure(bot, user_id, user_state)

    except Exception as e:
        logging.error(f"[SIGN] خطا در _process_lavayeh_submit_sign: {e}")
        await on_lavayeh_sign_submit_failure(bot, user_id, user_state)


# ══════════════════════════════════════════════════════════════════════════════
# پردازش ارسال کد امضا اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════
async def _process_ezhharnameh_send_sign_code(data: dict, bot: Bot):
    user_id = data["user_id"]
    tracking_code = data.get("tracking_code", "")
    target_row_indices = data.get("target_row_indices", [])

    from ezhharnameh_sign_scenario import send_ezhhar_sign_codes
    from lavayeh_sign_handlers import on_ezhhar_sign_code_sent_success, on_ezhhar_sign_code_sent_failure

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)

    try:
        await bot.send_message(ADMIN_ID, f"🔄 [EZHHAR_SIGN] ارسال کد امضا اظهارنامه برای کاربر {user_id}")
        result = await send_ezhhar_sign_codes(
            bot, user_id, tracking_code, target_row_indices
        )

        if result["success"]:
            await on_ezhhar_sign_code_sent_success(
                bot, user_id, result["persons"], user_state
            )
            await bot.send_message(ADMIN_ID, f"✅ [EZHHAR_SIGN] کد امضا اظهارنامه برای کاربر {user_id} ارسال شد.")
        else:
            await on_ezhhar_sign_code_sent_failure(bot, user_id, user_state)
            await bot.send_message(ADMIN_ID, f"❌ [EZHHAR_SIGN] ارسال کد امضا اظهارنامه برای کاربر {user_id} ناموفق.")

    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] خطا در _process_ezhharnameh_send_sign_code: {e}")
        await on_ezhhar_sign_code_sent_failure(bot, user_id, user_state)


# ══════════════════════════════════════════════════════════════════════════════
# پردازش ثبت کد امضا اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════
async def _process_ezhharnameh_submit_sign(data: dict, bot: Bot):
    user_id = data["user_id"]
    tracking_code = data.get("tracking_code", "")
    row_idx = data.get("row_idx", 0)
    code = data.get("code", "")

    from ezhharnameh_sign_scenario import submit_ezhhar_sign_code
    from lavayeh_sign_handlers import on_ezhhar_sign_submit_success, on_ezhhar_sign_submit_failure, on_ezhhar_sign_wrong_code

    user_state = runtime_state.dp.fsm.resolve_context(bot, user_id, user_id)

    try:
        await bot.send_message(ADMIN_ID, f"🔄 [EZHHAR_SIGN] ثبت امضا اظهارنامه برای کاربر {user_id}")
        result = await submit_ezhhar_sign_code(
            bot, user_id, tracking_code, row_idx, code
        )

        if result["success"]:
            await on_ezhhar_sign_submit_success(bot, user_id, row_idx, user_state)
        else:
            error = result.get("error", "")
            if "نادرست" in error or "wrong_code" in str(result):
                await on_ezhhar_sign_wrong_code(bot, user_id, row_idx, user_state)
            else:
                await on_ezhhar_sign_submit_failure(bot, user_id, user_state)

    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] خطا در _process_ezhharnameh_submit_sign: {e}")
        await on_ezhhar_sign_submit_failure(bot, user_id, user_state)


# ══════════════════════════════════════════════════════════════════════════════
# Browser Worker
# ══════════════════════════════════════════════════════════════════════════════
async def browser_worker(bot: Bot):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        runtime_state.browser_context = await browser.new_context(
            viewport={'width': 1366, 'height': 768}
        )
        runtime_state.sana_page = await runtime_state.browser_context.new_page()
        browser_context = runtime_state.browser_context
        sana_page = runtime_state.sana_page

        if DEBUG_LOG_REQUESTS:
            sana_page.on(
                "request",
                lambda req: logging.info(f"[DEBUG-REQ] {req.method} {req.url}")
                if "GetLegalPersonType" in req.url else None
            )
            sana_page.on(
                "framenavigated",
                lambda frame: logging.info(f"[DEBUG-NAV] {frame.url}")
                if frame == sana_page.main_frame else None
            )

        await wait_for_manual_login(bot)
        while True:
            data = await runtime_state.job_queue.get()
            await process_task(data, bot)
            runtime_state.job_queue.task_done()
