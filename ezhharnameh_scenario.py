"""
سناریوی ثبت اظهارنامه در سامانه قضایی ثنا.

جریان کلی:
  ۱. کلیک «ارایه و پیگیری اظهارنامه»
  ۲. کلیک «ثبت و اصلاح اظهارنامه»
  ۳. مرحله «شروع» — انتخاب نوع ارائه‌دهنده (حقیقی / حقوقی / وکیل)
  ۴. مرحله «اظهارکننده» — افزودن اشخاص اظهارکننده
  ۵. مرحله «وکیل» (در صورت وجود وکیل) — افزودن وکیل
  ۶. مرحله «موضوع اظهارنامه» (در صورت وجود حقوقی) — ثبت نماینده
  ۷. مرحله «متن» — وارد کردن شرح متن
  ۸. ثبت موقت
  ۹. مرحله «منضمات»:
     - اگر حقوقی: ثبت مدرک نمایندگی (اجباری) + سایر پیوست‌ها
     - اگر وکیل داشت: مانند اعلام وکالت (تصویر الکترونیک وکالت‌نامه)
     - در غیر این صورت: سایر ضمائم
  ۱۰. آماده‌سازی جهت محاسبه هزینه
  ۱۱. محاسبه و دریافت هزینه
  ۱۲. چاپ PDF
  ۱۳. ارسال نتیجه به کاربر
"""

import asyncio
import logging
import os
import html as html_lib

from aiogram import Bot
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import runtime_state
from config import ADMIN_ID
from sheets import log_event
from browser_helpers import (
    resilient_sleep, check_and_handle_expiry, soft_click_if_exists,
    goto_url_with_retry, human_delay, force_click_by_text,
    safe_click_by_text, safe_type, wait_for_angular_idle,
)


class EzhharFatalError(Exception):
    """خطای قطعی که retry را متوقف می‌کند."""
    pass


# مقدار value برای نوع نماینده در سامانه
AGENT_TYPE_VALUES = {
    "مدیرعامل": "0091000010000008",
    "نماینده":  "0091000010000007",
}


def _text_to_editor_html(text: str) -> str:
    """متن کاربر را با حفظ فاصله‌ها/اینترها به HTML امن برای ادیتور تبدیل می‌کند."""
    if not text:
        return "<p><br></p>"
    lines = text.split("\n")
    parts = []
    for line in lines:
        escaped = html_lib.escape(line, quote=False)
        if escaped.startswith(" "):
            leading = len(escaped) - len(escaped.lstrip(" "))
            escaped = ("&nbsp;" * leading) + escaped[leading:]
        escaped = escaped.replace("  ", "&nbsp; ")
        parts.append(f"<p>{escaped}</p>" if escaped else "<p><br></p>")
    return "".join(parts)


async def process_ezhharnameh_task(data: dict, bot: Bot):
    """پردازش تسک ثبت اظهارنامه"""
    sana_page = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id = data["user_id"]

    declarants = data.get("ezhhar_declarants", [])
    addressees = data.get("ezhhar_addressees", [])
    subject = data.get("ezhhar_subject", "سایر")
    ezhhar_text = data.get("ezhhar_text", "")
    attachment_groups = data.get("ezhhar_attachments", [])

    # تشخیص وجود وکیل و حقوقی در اظهارکنندگان
    has_lawyer = any(p.get("person_type") == "وکیل" for p in declarants)
    has_legal_declarant = any(p.get("person_type") == "شخص حقوقی" for p in declarants)
    has_real_declarant = any(p.get("person_type") == "شخص حقیقی" for p in declarants)
    # تنها حقیقی (بدون حقوقی و وکیل)
    only_real_declarant = has_real_declarant and not has_legal_declarant and not has_lawyer

    logging.info(
        f"[EZHHAR] user={user_id} declarants={declarants} addressees={addressees} "
        f"subject={subject} has_lawyer={has_lawyer} has_legal={has_legal_declarant}"
    )

    await bot.send_message(
        user_id,
        f"⏳ **در حال ثبت اظهارنامه...**\n"
        f"موضوع: **{subject}**",
        parse_mode="Markdown"
    )
    await bot.send_message(
        ADMIN_ID,
        f"🔄 [EZHHAR] شروع ثبت اظهارنامه برای کاربر {user_id}\n"
        f"موضوع: {subject} | اظهارکنندگان: {len(declarants)} | مخاطبین: {len(addressees)}"
    )

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            ok = await goto_url_with_retry(
                sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
            )
            if not ok:
                return
            await human_delay(3.0, 5.0)

            # ── ۱. کلیک «ارایه و پیگیری اظهارنامه» ─────────────────────
            clicked = await sana_page.evaluate('''() => {
                const links = Array.from(document.querySelectorAll('a.list-group-item'));
                const t = links.find(el => el.innerText && el.innerText.includes("ارایه و پیگیری اظهارنامه"));
                if (t) { t.click(); return true; }
                return false;
            }''')
            if not clicked:
                await safe_click_by_text(sana_page, "ارایه و پیگیری اظهارنامه", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۲. کلیک «ثبت و اصلاح اظهارنامه» ────────────────────────
            await _click_step_box(sana_page, "ثبت و اصلاح اظهارنامه", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            # ── ۳. مرحله «شروع» — انتخاب نوع ارائه ─────────────────────
            await _click_step_label(sana_page, "شروع", bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            if only_real_declarant:
                # فقط حقیقی — مستقیم وارد بخش اظهارکننده می‌شویم
                logging.info("[EZHHAR] only real declarant — skipping start step selection")
            elif has_lawyer:
                # دارد وکیل + (احتمالاً حقیقی/حقوقی)
                await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('#rdbLawyerOffer');
                    if (rdb) rdb.click();
                }''')
                await asyncio.sleep(2)
            else:
                # حقوقی بدون وکیل
                await sana_page.evaluate('''() => {
                    const rdb = document.querySelector('#rdbAgentOffer');
                    if (rdb) rdb.click();
                }''')
                await asyncio.sleep(2)

            # ── ۴. مرحله «اظهارکننده» ────────────────────────────────────
            await _click_step_label(sana_page, "اظهاركننده", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for person in declarants:
                ptype = person.get("person_type", "شخص حقیقی")
                if ptype in ("شخص حقیقی", "وکیل"):
                    # وکیل در بخش اظهارکننده با کدملی حقیقی اضافه می‌شود
                    # (وکیل بعداً در step وکیل اضافه می‌شود)
                    if ptype == "وکیل":
                        continue  # وکیل را در step وکیل اضافه می‌کنیم
                    await _click_add_btn(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_real_person(sana_page, person["national_id"], bot, user_id)
                    await resilient_sleep(sana_page, 10, bot, user_id)

                elif ptype == "شخص حقوقی":
                    await _click_add_btn(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_legal_person(sana_page, person, bot, user_id)
                    await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۴.۵. مرحله «مخاطب» ────────────────────────────────────
            await _click_step_label(sana_page, "مخاطب", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for person in addressees:
                ptype = person.get("person_type", "شخص حقیقی")
                if ptype == "شخص حقیقی":
                    await _click_add_btn(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_real_person(sana_page, person["national_id"], bot, user_id)
                    await resilient_sleep(sana_page, 10, bot, user_id)

                elif ptype == "شخص حقوقی":
                    await _click_add_btn(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_legal_person(sana_page, person, bot, user_id)
                    await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۵. مرحله «وکیل» (اگر وکیل داشتیم) ─────────────────────
            if has_lawyer:
                await _click_step_label(sana_page, "وكيل", bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

                for person in declarants:
                    if person.get("person_type") != "وکیل":
                        continue
                    await _click_add_btn(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)
                    await _fill_lawyer_person(sana_page, person["national_id"], bot, user_id)
                    await resilient_sleep(sana_page, 10, bot, user_id)

            # ── ۶. مرحله «موضوع اظهارنامه» ──────────────────────────────
            # این مرحله همیشه باید طی شود (چه اظهارکننده حقیقی باشد چه حقوقی)
            await _click_step_label(sana_page, "موضوع اظهارنامه", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # کلیک «افزودن»
            await _click_add_btn(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            # باز کردن dropdown «موضوع» و جستجوی «سایر»
            search_input = sana_page.locator('.ui-select-search').first
            opened = False
            for open_attempt in range(4):
                await sana_page.evaluate('''() => {
                    const btn = document.querySelector('.ui-select-toggle');
                    if (btn) btn.click();
                }''')
                try:
                    await search_input.wait_for(state="visible", timeout=4000)
                    opened = True
                    break
                except PlaywrightTimeoutError:
                    logging.warning(f"[EZHHAR] dropdown موضوع باز نشد (تلاش {open_attempt + 1})")
                    await asyncio.sleep(1.5)

            if opened:
                await search_input.fill("")
                await search_input.type("سایر", delay=150)
                await asyncio.sleep(3)

                subject_clicked = await sana_page.evaluate('''() => {
                    // اولویت با آیتم دقیق typeahead که شامل «سایر موضوعات اظهارنامه» است
                    const highlighted = Array.from(document.querySelectorAll('[ng-bind-html*="typeaheadHighlight"]'));
                    const visibleHighlighted = highlighted.filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    if (visibleHighlighted.length > 0) {
                        let target = visibleHighlighted[0];
                        // کلیک روی والد قابل‌کلیک (ردیف) در صورت وجود، وگرنه خود المان
                        const row = target.closest('a, .ui-select-choices-row, li') || target;
                        row.click();
                        target.click();
                        return true;
                    }
                    const choices = Array.from(document.querySelectorAll('.ui-select-choices-row, .ui-select-choices div[ng-repeat]'));
                    const visible = choices.filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    if (visible.length > 0) { visible[0].click(); return true; }
                    const lis = Array.from(document.querySelectorAll('.ui-select-choices li'));
                    const visLis = lis.filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    if (visLis.length > 0) { visLis[0].click(); return true; }
                    return false;
                }''')
                await asyncio.sleep(3)

                if not subject_clicked:
                    logging.warning("[EZHHAR] گزینه اول dropdown موضوع پیدا/کلیک نشد — تلاش مجدد")
                    # تلاش دوم: کلیک با locator روی آیتم typeahead
                    try:
                        option_locator = sana_page.locator('[ng-bind-html*="typeaheadHighlight"]').first
                        await option_locator.wait_for(state="visible", timeout=3000)
                        await option_locator.click()
                        await asyncio.sleep(3)
                    except PlaywrightTimeoutError:
                        logging.warning("[EZHHAR] تلاش دوم انتخاب موضوع نیز ناموفق بود")
            else:
                logging.warning("[EZHHAR] dropdown موضوع باز نشد — ادامه بدون انتخاب موضوع")

            # اگر کاربر عنوانی متفاوت از پیش‌فرض انتخاب کرده باشد، در فیلد توضیحات درج می‌شود
            if subject and subject != "سایر":
                await sana_page.evaluate('''(desc) => {
                    const inp = document.querySelector('input[name="txtDescription"]');
                    if (inp) {
                        inp.value = desc;
                        inp.dispatchEvent(new Event("input", { bubbles: true }));
                        inp.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                }''', subject)
                await asyncio.sleep(1)

            # ── ۷. مرحله «شرح» ───────────────────────────────────────────
            await _click_step_label(sana_page, "شرح", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            ezhhar_text_html = _text_to_editor_html(ezhhar_text)
            await sana_page.evaluate('''(html) => {
                const editor = document.querySelector('[contenteditable="true"][ta-bind]');
                if (editor) {
                    editor.focus();
                    editor.innerHTML = html;
                    editor.dispatchEvent(new Event("input", { bubbles: true }));
                    editor.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''', ezhhar_text_html)
            await resilient_sleep(sana_page, 2, bot, user_id)

            # اعمال H3
            await sana_page.evaluate('''() => {
                const editor = document.querySelector('[contenteditable="true"][ta-bind]');
                if (editor) {
                    const range = document.createRange();
                    range.selectNodeContents(editor);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    document.dispatchEvent(new Event("selectionchange", { bubbles: true }));
                    editor.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
                }
            }''')
            await asyncio.sleep(0.5)
            await sana_page.evaluate('''() => {
                const btn = document.querySelector('button[name="h3"]') ||
                    Array.from(document.querySelectorAll('button')).find(b => b.title === "Heading 3");
                if (btn && !btn.disabled) btn.click();
            }''')
            await asyncio.sleep(0.5)

            # ── ۸. ثبت موقت ──────────────────────────────────────────────
            await _click_save_temp(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            bill_no = await _extract_bill_no(sana_page)
            logging.info(f"[EZHHAR] bill_no={bill_no}")

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۹. مرحله «منضمات» ────────────────────────────────────────
            # دانلود تصاویر از تلگرام
            groups_with_paths = []
            for group in attachment_groups:
                paths = await _download_images(bot, group.get("images", []), user_id)
                groups_with_paths.append({"title": group.get("title", "مستندات"), "paths": paths})

            if has_legal_declarant or attachment_groups:
                await _click_step_box(sana_page, "منضمات", bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                # اگر حقوقی داشتیم، مدرک نمایندگی اجباری است
                if has_legal_declarant:
                    # اولین گروه پیوست‌ها را به عنوان مدرک نمایندگی ثبت می‌کنیم
                    proxy_group = groups_with_paths[0] if groups_with_paths else {"title": "مدرک نمایندگی", "paths": []}
                    await _upload_proxy_document(sana_page, proxy_group["paths"], bot, user_id)
                    remaining_groups = groups_with_paths[1:]
                else:
                    remaining_groups = groups_with_paths

                # اگر وکیل داشتیم، وکالت‌نامه الکترونیک
                if has_lawyer:
                    # یافتن اولین وکیل برای شماره قرارداد
                    first_lawyer = next((p for p in declarants if p.get("person_type") == "وکیل"), {})
                    contract_no = first_lawyer.get("contract_number", "")
                    stamp_val = first_lawyer.get("stamp_amount_value", 0)
                    await _upload_electronic_vakalaht(sana_page, contract_no, stamp_val, bot, user_id)

                # سایر پیوست‌ها
                for group in remaining_groups:
                    if group["paths"]:
                        await _upload_other_attachment(sana_page, group["title"], group["paths"], bot, user_id)

                # پاکسازی فایل‌های موقت
                for group in groups_with_paths:
                    for p in group["paths"]:
                        try:
                            if os.path.exists(p):
                                os.remove(p)
                        except Exception:
                            pass

                await _click_goto_main(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۰. آماده‌سازی ───────────────────────────────────────────
            await _click_step_box(sana_page, "آماده سازي جهت محاسبه هزينه و ارسال", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            prep_ok = await _click_preparation(sana_page, bot, user_id)
            if not prep_ok:
                await bot.send_message(
                    user_id,
                    f"⚠️ مرحله آماده‌سازی با مشکل مواجه شد.\n"
                    f"کد رهگیری لایحه: `{bill_no}`\n"
                    f"با شماره **09306186888** در واتساپ پیام دهید.",
                    parse_mode="Markdown"
                )
                return

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۱. محاسبه هزینه ─────────────────────────────────────────
            await _click_step_box(sana_page, "محاسبه و دريافت هزينه", bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            court_total = await _calculate_cost(sana_page, bot, user_id)
            logging.info(f"[EZHHAR] court_total={court_total}")

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            # ── ۱۲. چاپ PDF ──────────────────────────────────────────────
            pdf_path = await _print_ezhharnameh(sana_page, browser_context, bill_no, bot, user_id)

            # ── ۱۳. ارسال نتیجه ──────────────────────────────────────────
            from lavayeh_handlers import send_lavayeh_result
            nat_ids = ", ".join([
                p.get("national_id", "") for p in declarants if p.get("national_id")
            ])
            await send_lavayeh_result(
                bot, user_id, pdf_path, court_total,
                tracking_code=bill_no,
                national_ids=nat_ids,
                lavayeh_title=f"اظهارنامه — {subject}",
                lavayeh_province="",
                lavayeh_row_number=1,
                lavayeh_persons=declarants,
            )

            await bot.send_message(
                ADMIN_ID,
                f"✅ [EZHHAR] ثبت اظهارنامه کاربر {user_id} موفق. هزینه: {court_total:,} تومان"
            )
            return

        except EzhharFatalError as e:
            logging.error(f"[EZHHAR] خطای قطعی user={user_id}: {e}")
            await bot.send_message(user_id, f"⚠️ **خطای قطعی:** {str(e)[:200]}", parse_mode="Markdown")
            await log_event(
                "خطای سامانه", "اظهارنامه", str(user_id), user_id,
                doc_name=subject, note=f"خطای قطعی: {str(e)[:200]}"
            )
            return

        except Exception as e:
            logging.error(f"[EZHHAR] تلاش {attempt+1} ناموفق user={user_id}: {e}")
            if attempt < max_attempts - 1:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [EZHHAR] تلاش {attempt+1} ناموفق. ریلود...\nخطا: {str(e)[:300]}"
                )
                try:
                    await sana_page.reload()
                    await asyncio.sleep(6)
                except Exception:
                    pass
            else:
                await bot.send_message(
                    user_id,
                    "⚠️ ثبت اظهارنامه با اختلال مواجه شد. پشتیبانی پیگیری خواهد کرد."
                )
                await bot.send_message(ADMIN_ID, f"❌ [EZHHAR] کاربر {user_id} پس از {max_attempts} تلاش ناموفق.")
                await log_event(
                    "خطای سامانه", "اظهارنامه", str(user_id), user_id,
                    doc_name=subject,
                    note=f"پس از {max_attempts} تلاش ناموفق: {str(e)[:200]}"
                )


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی
# ══════════════════════════════════════════════════════════════════════════════

async def _click_step_box(page, step_name: str, bot: Bot, user_id: int):
    clicked = await page.evaluate(f'''() => {{
        const heads = Array.from(document.querySelectorAll('.box h5'));
        const t = heads.find(el => el.innerText && el.innerText.trim().includes("{step_name}"));
        if (t) {{
            const box = t.closest('.box');
            if (box) {{ box.click(); return true; }}
        }}
        return false;
    }}''')
    if not clicked:
        await safe_click_by_text(page, step_name, bot, user_id)


async def _click_step_label(page, step_name: str, bot: Bot, user_id: int):
    clicked = await page.evaluate(f'''() => {{
        const steps = Array.from(document.querySelectorAll('.step'));
        const t = steps.find(el => el.innerText && el.innerText.trim().includes("{step_name}"));
        if (t) {{ t.click(); return true; }}
        return false;
    }}''')
    if not clicked:
        await safe_click_by_text(page, step_name, bot, user_id)


async def _click_add_btn(page, bot: Bot, user_id: int):
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#btnAddSection');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        await safe_click_by_text(page, "افزودن", bot, user_id)
    await asyncio.sleep(2)


async def _fill_real_person(page, national_id: str, bot: Bot, user_id: int):
    """پر کردن کدملی شخص حقیقی و استعلام"""
    # پر کردن فیلد کدملی
    for sel in ["#txtRealIrNationalityCode1", "#txtRealIrNationalityCode"]:
        elem_count = await page.locator(sel).count()
        if elem_count > 0:
            await page.evaluate(f'''() => {{
                const inp = document.querySelector('{sel}');
                if (inp && inp.offsetParent !== null) {{
                    inp.value = "{national_id}";
                    inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
            }}''')
            await asyncio.sleep(1)
            break

    # استعلام ثنا
    await _query_sana(page, "actions.callNationalityCode", bot, user_id)


async def _fill_legal_person(page, person: dict, bot: Bot, user_id: int):
    """پر کردن اطلاعات شخص حقوقی و استعلام"""
    company_id = person.get("company_id", "")
    national_id = person.get("national_id", "")
    rep_type = person.get("representative_type", "نماینده")

    # انتخاب رادیوباتن «شخص حقوقی» (value=3)
    await page.evaluate('''() => {
        const rdb = document.querySelector('#rdb3, input[value="3"][name="personType"]');
        if (rdb) rdb.click();
    }''')
    await asyncio.sleep(2)

    # انتخاب «غیردولتی / خصوصی» (value=4)
    await page.evaluate('''() => {
        const rdb = document.querySelector('#rdbPrivate, input[value="4"][name="LegalPersonType"]');
        if (rdb) rdb.click();
    }''')
    await asyncio.sleep(2)

    # وارد کردن شناسه ملی شرکت
    await page.evaluate(f'''() => {{
        const inp = document.querySelector('#txtLegalIrNationalityCode');
        if (inp) {{
            inp.value = "{company_id}";
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
        }}
    }}''')
    await asyncio.sleep(1)

    # استعلام شرکت
    await _query_sana(page, "actions.callLegalNationalityCode", bot, user_id, is_legal=True)
    await asyncio.sleep(5)

    # وارد کردن کدملی نماینده
    await page.evaluate(f'''() => {{
        const inp = document.querySelector('#txtRealIrNationalityCode, #txtRealIrNationalityCode1');
        if (inp && inp.offsetParent !== null) {{
            inp.value = "{national_id}";
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
        }}
    }}''')
    await asyncio.sleep(1)

    # استعلام نماینده
    await _query_sana(page, "actions.callNationalityCode", bot, user_id)


async def _fill_lawyer_person(page, national_id: str, bot: Bot, user_id: int):
    """پر کردن کدملی وکیل در step وکیل"""
    await page.evaluate(f'''() => {{
        const inp = document.querySelector('#txtNationalityCode');
        if (inp) {{
            inp.value = "{national_id}";
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
        }}
    }}''')
    await asyncio.sleep(1)

    # استعلام وکیل از ثنا
    await _query_sana(page, "actions.getLawyerDataWithSana", bot, user_id)


async def _query_sana(page, ng_click: str, bot: Bot, user_id: int, is_legal: bool = False, max_retries: int = 5):
    """
    استعلام از ثنا — کلیک دکمه استعلام و بررسی نتیجه.
    وقتی استعلام موفق باشد، فیلدهای صفحه پر و غیرقابل ویرایش می‌شوند.
    """
    for attempt in range(max_retries):
        clicked = await page.evaluate(f'''() => {{
            const btns = Array.from(document.querySelectorAll('button[ng-click*="{ng_click}"]'));
            const btn = btns.find(b => !b.disabled);
            if (btn) {{ btn.click(); return true; }}
            // fallback: دکمه warning با tooltip استعلام
            const warns = Array.from(document.querySelectorAll('button.btn-warning'));
            const w = warns.find(b => !b.disabled && (
                (b.getAttribute("tooltip") || "").includes("استعلام") ||
                (b.getAttribute("title") || "").includes("استعلام")
            ));
            if (w) {{ w.click(); return true; }}
            return false;
        }}''')

        if not clicked:
            logging.warning(f"[EZHHAR] دکمه استعلام ({ng_click}) پیدا نشد — تلاش {attempt+1}")

        await asyncio.sleep(12)

        # بستن هر پاپ‌آپ خطا
        await _close_popup(page)
        await asyncio.sleep(2)

        # بررسی موفقیت استعلام: فیلد ExtractedFromSana=1 یا disabled
        success = await page.evaluate('''() => {
            const disabled = document.querySelector(
                'input[ng-disabled*="ExtractedFromSana"][ng-disabled*="1"]'
            );
            return disabled !== null;
        }''')
        if success:
            logging.info(f"[EZHHAR] استعلام موفق ({ng_click})")
            return

        # retry
        await asyncio.sleep(5)

    logging.warning(f"[EZHHAR] استعلام ({ng_click}) پس از {max_retries} تلاش نتیجه نداد")


async def _close_popup(page) -> bool:
    closed = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


async def _click_save_temp(page, bot: Bot, user_id: int, max_retries: int = 5):
    for attempt in range(max_retries):
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnSave');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "ثبت موقت", bot, user_id)
        await asyncio.sleep(10)

        success = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const icon = popup.querySelector('.sa-icon.sa-success');
            return icon && window.getComputedStyle(icon).display !== 'none';
        }''')
        if success:
            await _close_success_popup(page)
            return

        error_text = await _get_error_text(page)
        if error_text:
            raise EzhharFatalError(error_text)
        await asyncio.sleep(5)


async def _click_goto_main(page, bot: Bot, user_id: int):
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#gotoMainPage');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        await soft_click_if_exists(page, "بازگشت به فهرست")


async def _upload_proxy_document(page, image_paths: list, bot: Bot, user_id: int):
    """
    آپلود مدرک نمایندگی (تصویر مدرک نمایندگی) در بخش منضمات.
    این مدرک برای اظهارکننده حقوقی اجباری است.
    """
    try:
        # انتخاب «تصوير مدرک نمايندگي»
        selected = await page.evaluate('''() => {
            const sel = document.querySelector('#attachmentType');
            if (!sel) return false;
            const opts = Array.from(sel.options);
            const opt = opts.find(o =>
                o.text.includes("تصوير مدرک نمايندگي") ||
                o.text.includes("تصویر مدرک نمایندگی")
            );
            if (opt) {
                sel.value = opt.value;
                sel.dispatchEvent(new Event("change"));
                return true;
            }
            return false;
        }''')
        if not selected:
            logging.warning("[EZHHAR] گزینه «تصویر مدرک نمایندگی» در لیست پیوست پیدا نشد")
            return
        await asyncio.sleep(3)

        # پر کردن txtNo با صفر
        await page.evaluate('''() => {
            const inp = document.querySelector('#txtNo');
            if (inp) {
                inp.value = "0";
                inp.dispatchEvent(new Event("input", { bubbles: true }));
            }
        }''')
        await asyncio.sleep(1)

        # کلیک دکمه تقویم و انتخاب «امروز»
        await page.evaluate('''() => {
            const calBtn = document.querySelector('button.btn-primary i.glyphicon-calendar');
            if (calBtn) calBtn.closest('button').click();
        }''')
        await asyncio.sleep(2)
        await page.evaluate('''() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const todayBtn = btns.find(b => b.innerText && b.innerText.trim() === "امروز");
            if (todayBtn) todayBtn.click();
        }''')
        await asyncio.sleep(1)

        # تعداد صفحات (اگر بیشتر از یک برگ)
        page_count = len(image_paths) if image_paths else 1
        if page_count > 1:
            await page.evaluate(f'''() => {{
                const inp = document.querySelector('#txt001');
                if (inp && !(inp.disabled)) {{
                    inp.value = "{page_count}";
                    inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                }}
            }}''')
            await asyncio.sleep(1)

        # افزودن پیوست
        await page.evaluate('''() => {
            const btn = document.querySelector('#incAttach0');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(3)

        # ثبت و ویرایش پیوست
        await page.evaluate('''() => {
            const btn = document.querySelector('#btnSaveDoc');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(8)
        await _close_success_popup(page)
        await asyncio.sleep(3)

        # آپلود تصاویر
        if image_paths:
            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button[ng-click*="editDocument"]'));
                if (btns.length > 0) btns[btns.length - 1].click();
            }''')
            await asyncio.sleep(4)

            file_input = page.locator('input[type="file"]').first
            await file_input.set_input_files(image_paths)
            await asyncio.sleep(3)

            await page.evaluate('''() => {
                const btn = document.querySelector('#btnUploadAll');
                if (btn && !btn.disabled) btn.click();
            }''')
            await asyncio.sleep(30)

            await page.evaluate('''() => {
                const btn = document.querySelector('#btnApplyAll');
                if (btn && !btn.disabled) btn.click();
            }''')
            await asyncio.sleep(10)

        logging.info("[EZHHAR] مدرک نمایندگی با موفقیت آپلود شد")

    except Exception as e:
        logging.error(f"[EZHHAR] خطا در آپلود مدرک نمایندگی: {e}")


async def _upload_electronic_vakalaht(page, contract_number: str, lawyer_amount_value: int, bot: Bot, user_id: int):
    """آپلود وکالت‌نامه الکترونیک (مانند اعلام وکالت)"""
    try:
        selected = await page.evaluate('''() => {
            const sel = document.querySelector('#attachmentType');
            if (!sel) return false;
            const opts = Array.from(sel.options);
            const opt = opts.find(o =>
                o.text.includes("تصوير الكترونيك وكالت نامه") ||
                o.text.includes("تصویر الکترونیک وکالت نامه")
            );
            if (opt) {
                sel.value = opt.value;
                sel.dispatchEvent(new Event("change"));
                return true;
            }
            return false;
        }''')
        if not selected:
            logging.warning("[EZHHAR] گزینه «تصویر الکترونیک وکالت‌نامه» پیدا نشد")
            return
        await asyncio.sleep(3)

        if contract_number:
            await page.evaluate(f'''() => {{
                const inp = document.querySelector('#txtNo');
                if (inp) {{
                    inp.value = "{contract_number}";
                    inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
            }}''')
            await asyncio.sleep(1)
        else:
            await page.evaluate('''() => {
                const inp = document.querySelector('#txtNo');
                if (inp) {
                    inp.value = "0";
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }''')
            await asyncio.sleep(1)

        if lawyer_amount_value > 0:
            await page.evaluate(f'''() => {{
                const inp = document.querySelector('#txtLawyerAmount');
                if (inp) {{
                    inp.removeAttribute('disabled');
                    inp.value = "{lawyer_amount_value}";
                    inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
            }}''')
            await asyncio.sleep(1)

        await page.evaluate('''() => {
            const btn = document.querySelector('#btnSaveDoc');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(8)
        await _close_success_popup(page)

    except Exception as e:
        logging.error(f"[EZHHAR] خطا در آپلود وکالت‌نامه الکترونیک: {e}")


async def _upload_other_attachment(page, title: str, image_paths: list, bot: Bot, user_id: int):
    """آپلود سایر ضمائم"""
    if not image_paths:
        return
    try:
        # انتخاب «ساير ضمائم»
        await page.evaluate('''() => {
            const sel = document.querySelector('#attachmentType');
            if (sel) {
                const opts = Array.from(sel.options);
                const opt = opts.find(o => o.text.includes("ساير ضمائم") || o.text.includes("سایر ضمائم"));
                if (opt) {
                    sel.value = opt.value;
                    sel.dispatchEvent(new Event("change"));
                }
            }
        }''')
        await asyncio.sleep(3)

        # پر کردن txtNo با صفر (فیلد الزامی برای ادامه روند)
        await page.evaluate('''() => {
            const inp = document.querySelector('#txtNo');
            if (inp) {
                inp.value = "0";
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }''')
        await asyncio.sleep(1)

        escaped = title.replace("`", "'").replace("\\", "")
        await page.evaluate(f'''() => {{
            const inp = document.querySelector('#txtName');
            if (inp) {{
                inp.value = "{escaped}";
                inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            }}
        }}''')

        await page.evaluate(f'''() => {{
            const inp = document.querySelector('#txt001');
            if (inp) {{
                inp.value = "{len(image_paths)}";
                inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            }}
        }}''')

        await page.evaluate('''() => {
            const btn = document.querySelector('#incAttach0');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(3)

        await page.evaluate('''() => {
            const btn = document.querySelector('#btnSaveDoc');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(8)
        await _close_success_popup(page)
        await asyncio.sleep(3)

        # ویرایش و آپلود فایل
        await page.evaluate('''() => {
            const btns = Array.from(document.querySelectorAll('button[ng-click*="editDocument"]'));
            if (btns.length > 0) btns[btns.length - 1].click();
        }''')
        await asyncio.sleep(4)

        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(image_paths)
        await asyncio.sleep(3)

        await page.evaluate('''() => {
            const btn = document.querySelector('#btnUploadAll');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(30)

        await page.evaluate('''() => {
            const btn = document.querySelector('#btnApplyAll');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(10)

    except Exception as e:
        logging.error(f"[EZHHAR] خطا در آپلود پیوست «{title}»: {e}")


async def _click_preparation(page, bot: Bot, user_id: int, max_retries: int = 3) -> bool:
    for attempt in range(max_retries):
        await page.evaluate('''() => {
            const btn = document.querySelector('#btnPreparation');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(40 if attempt > 0 else 12)

        success = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const icon = popup.querySelector('.sa-icon.sa-success');
            const h2 = popup.querySelector('h2');
            return icon && window.getComputedStyle(icon).display !== 'none' &&
                   h2 && h2.innerText.includes("آماده سازی");
        }''')
        if success:
            await _close_success_popup(page)
            return True

        await _close_popup(page)
        await asyncio.sleep(30)
        await _close_success_popup(page)

    return False


async def _calculate_cost(page, bot: Bot, user_id: int, max_retries: int = 3) -> int:
    for attempt in range(max_retries):
        await _close_popup(page)
        await asyncio.sleep(2)
        await page.evaluate('''() => {
            const btn = document.querySelector('#btnCalculateCash');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(40)
        await _close_popup(page)

        raw = await page.evaluate('''() => {
            const tds = Array.from(document.querySelectorAll('table td'));
            for (let td of tds) {
                const text = td.innerText.trim().replace(/,/g, '').replace(/،/g, '');
                if (/^[0-9]+$/.test(text) && parseInt(text) > 10000 && parseInt(text) < 100000000000) {
                    return text;
                }
            }
            return null;
        }''')
        if raw:
            try:
                amount = int(raw.replace(",", "").strip())
                if amount > 100_000_000:
                    amount = amount // 10
                return amount
            except Exception:
                pass
        await asyncio.sleep(10)
    return 0


async def _print_ezhharnameh(page, browser_context, bill_no: str, bot: Bot, user_id: int) -> str:
    pdf_path = f"ezhharnameh_{bill_no}.pdf"
    try:
        async def click_print():
            await page.evaluate('''() => {
                const heads = Array.from(document.querySelectorAll('.box h5'));
                const t = heads.find(el => el.innerText && (
                    el.innerText.includes("چاپ اوليه") || el.innerText.includes("چاپ اولیه")
                ));
                if (t) {
                    const box = t.closest('.box');
                    if (box) box.click();
                }
            }''')

        async with browser_context.expect_page(timeout=20000) as new_page_info:
            await click_print()

        print_page = await new_page_info.value
        await print_page.wait_for_load_state("load", timeout=30000)
        await asyncio.sleep(8)
        await check_and_handle_expiry(print_page, bot, user_id)
        await print_page.pdf(path=pdf_path, format="A4")
        await print_page.close()
    except Exception as e:
        logging.error(f"[EZHHAR] خطا در چاپ: {e}")
        try:
            await page.pdf(path=pdf_path, format="A4")
        except Exception:
            pass
    return pdf_path


async def _extract_bill_no(page) -> str:
    try:
        val = await page.evaluate('''() => {
            const inp = document.querySelector('#txtBillNo, #txtPetitionNo');
            return inp ? inp.value : "";
        }''')
        return val or "نامشخص"
    except Exception:
        return "نامشخص"


async def _close_success_popup(page) -> bool:
    closed = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


async def _get_error_text(page):
    text = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return null;
        const successIcon = popup.querySelector('.sa-icon.sa-success');
        if (successIcon && window.getComputedStyle(successIcon).display !== 'none') return null;
        const h2 = popup.querySelector('h2');
        const p = popup.querySelector('p');
        const msg = [h2 ? h2.innerText : '', p ? p.innerText : ''].filter(Boolean).join(' - ').trim();
        const btn = popup.querySelector('button.confirm');
        if (btn) btn.click();
        return msg || null;
    }''')
    if text:
        await asyncio.sleep(1)
    return text


async def _download_images(bot: Bot, file_ids: list, user_id: int) -> list:
    paths = []
    for i, file_id in enumerate(file_ids):
        try:
            file_info = await bot.get_file(file_id)
            ext = "jpg"
            if file_info.file_path:
                ext = file_info.file_path.split(".")[-1].lower()
                if ext not in ("jpg", "jpeg", "png"):
                    ext = "jpg"
            path = f"ezhhar_img_{user_id}_{i}.{ext}"
            await bot.download_file(file_info.file_path, path)
            paths.append(path)
        except Exception as e:
            logging.error(f"[EZHHAR] خطا در دانلود تصویر {i}: {e}")
    return paths
