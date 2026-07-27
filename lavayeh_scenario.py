"""
سناریوی کامل ثبت لایحه در سامانه قضایی ثنا.
"""
import asyncio
import logging
import os
import base64

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


class LavayehFatalError(Exception):
    """خطای قطعی که retry را متوقف می‌کند."""
    pass


TITLE_SEARCH_MAP = {
    "لایحه دفاعیه":                 ("دفا",    0),
    "صدور اجرائیه":                  ("اجرائ",  0),
    "اعتراض به نظر کارشناس":         ("کارشن",  1),
    "اعتراض به قرار رد دفتر":        ("قرار",   1),
    "سایر عناوین":                   ("دفا",    0),
}

AGENT_TYPE_VALUES = {
    "مدیرعامل":  "0091000010000008",
    "نماینده":   "0091000010000007",
}


async def process_lavayeh_task(data: dict, bot: Bot):
    sana_page       = runtime_state.sana_page
    browser_context = runtime_state.browser_context
    user_id         = data["user_id"]

    title        = data.get("lavayeh_title", "لایحه دفاعیه")
    system_title = data.get("lavayeh_system_title", "لایحه دفاعیه")
    tracking_code = data.get("lavayeh_tracking_code", "")
    province      = data.get("lavayeh_province", "")
    row_number    = data.get("lavayeh_row_number", 1)
    persons       = data.get("lavayeh_persons", [])
    lavayeh_text  = data.get("lavayeh_text", "")
    attachment_groups = data.get("lavayeh_attachments", [])
    has_images    = len(attachment_groups) > 0
    total_image_count = sum(len(g.get("images", [])) for g in attachment_groups)

    logging.info(
        f"[LAVAYEH] user={user_id} title={title} code={tracking_code} "
        f"province={province} row={row_number} persons={len(persons)} "
        f"attachment_groups={len(attachment_groups)} images={total_image_count}"
    )

    await bot.send_message(
        user_id,
        f"⏳ در حال ثبت لایحه...\nعنوان: **{title}** | کد: `{tracking_code}`",
        parse_mode="Markdown"
    )
    await bot.send_message(
        ADMIN_ID,
        f"🔄 [LAVAYEH] شروع ثبت برای کاربر {user_id}\n"
        f"عنوان: {title} | کد: {tracking_code} | استان: {province}"
    )

    max_attempts = 3
    lavayeh_bill_no = ""
    for attempt in range(max_attempts):
        try:
            ok = await goto_url_with_retry(sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id)
            if not ok:
                return
            await human_delay(3.0, 5.0)

            await _click_menu_item(sana_page, "ارایه و پیگیری لایحه", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            search_kw, row_idx = TITLE_SEARCH_MAP.get(title, ("دفا", 0))
            await _select_bill_type(sana_page, search_kw, row_idx, bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

            await _click_taqdim_lavayeh(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            await _click_step_box(sana_page, "ثبت و ويرايش لايحه", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            await _click_step_label(sana_page, "اطلاعات پرونده", bot, user_id)
            await resilient_sleep(sana_page, 3, bot, user_id)

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
                    "🔢 شماره پرونده\n🔢 ردیف فرعی\n🏙 استان\n\n"
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

            await _click_step_label(sana_page, "ارائه كننده لايحه", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            for person in persons:
                ptype = person.get("person_type", "شخص حقیقی")

                if ptype in ("شخص حقیقی", "وکیل"):
                    await _click_add_person(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)

                    await _fill_input(sana_page, "#txtRealIrNationalityCode1", person["national_id"], bot, user_id)
                    await resilient_sleep(sana_page, 1, bot, user_id)

                    await _click_sana_query_with_retry(sana_page, "actions.callNationalityCode", bot, user_id)
                    await resilient_sleep(sana_page, 8, bot, user_id)

                elif ptype == "شخص حقوقی":
                    await _click_add_person(sana_page, bot, user_id)
                    await resilient_sleep(sana_page, 3, bot, user_id)

                    await sana_page.evaluate('''() => {
                        const rdb = document.querySelector('input[type="radio"][value="3"]');
                        if (rdb) rdb.click();
                    }''')
                    await resilient_sleep(sana_page, 2, bot, user_id)

                    await _fill_input(sana_page, "#txtLegalIrNationalityCode", person.get("company_id", ""), bot, user_id)
                    await resilient_sleep(sana_page, 1, bot, user_id)

                    await _click_sana_query_with_retry(sana_page, "actions.callLegalNationalityCode", bot, user_id)
                    await resilient_sleep(sana_page, 8, bot, user_id)

                    await sana_page.evaluate('''() => {
                        const rdb = document.querySelector('input[type="radio"][value="7"]');
                        if (rdb) rdb.click();
                    }''')
                    await resilient_sleep(sana_page, 2, bot, user_id)

                    rep_type = person.get("representative_type", "نماینده")
                    agent_value = AGENT_TYPE_VALUES.get(rep_type, "0091000010000007")
                    await sana_page.evaluate(f'''() => {{
                        const sel = document.querySelector('select[ng-model="viewModel.currentDeclarantPerson.AgentTypeId"]');
                        if (sel) {{
                            sel.value = "{agent_value}";
                            sel.dispatchEvent(new Event("change"));
                        }}
                    }}''')
                    await resilient_sleep(sana_page, 1, bot, user_id)

                    await _fill_input(sana_page, "#txtRealIrNationalityCode", person["national_id"], bot, user_id)
                    await resilient_sleep(sana_page, 1, bot, user_id)

                    await _click_sana_query_with_retry(
                        sana_page, "actions.callNationalityCode", bot, user_id,
                        btn_id="btnCallNationalityCode"
                    )
                    await resilient_sleep(sana_page, 8, bot, user_id)

            await _click_step_label(sana_page, "متن", bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            await sana_page.evaluate(f'''() => {{
                const editor = document.querySelector('[contenteditable="true"][ta-bind]');
                if (editor) {{
                    editor.focus();
                    editor.innerHTML = `<p>{lavayeh_text.replace("`", "'")}</p>`;
                    editor.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    editor.dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
            }}''')
            await resilient_sleep(sana_page, 2, bot, user_id)

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
                    editor.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));
                }
            }''')
            await asyncio.sleep(0.5)

            clicked_h3 = await sana_page.evaluate('''() => {
                const btn = document.querySelector('button[name="h3"]') ||
                            Array.from(document.querySelectorAll('button')).find(b => b.title === "Heading 3");
                if (btn && !btn.disabled) { btn.click(); return true; }
                return false;
            }''')
            if not clicked_h3:
                logging.warning(f"[LAVAYEH] دکمه H3 پیدا نشد (user={user_id})")
            await resilient_sleep(sana_page, 1, bot, user_id)

            await _click_save_temp_with_retry(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            lavayeh_bill_no = await _extract_bill_no(sana_page)
            logging.info(f"[LAVAYEH] bill_no: {lavayeh_bill_no} (user={user_id})")

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            if has_images:
                await _click_step_box(sana_page, "منضمات", bot, user_id)
                await resilient_sleep(sana_page, 5, bot, user_id)

                groups_with_paths = []
                for group in attachment_groups:
                    group_title = group.get("title", "مستندات")
                    group_file_ids = group.get("images", [])
                    group_paths = await _download_images_from_telegram(bot, group_file_ids, user_id)
                    groups_with_paths.append({"title": group_title, "paths": group_paths})

                upload_ok = await _upload_attachment_groups(sana_page, groups_with_paths, bot, user_id)

                for group in groups_with_paths:
                    for p in group["paths"]:
                        try:
                            if os.path.exists(p):
                                os.remove(p)
                        except Exception:
                            pass

                if not upload_ok:
                    await bot.send_message(ADMIN_ID, f"⚠️ [LAVAYEH] آپلود پیوست‌ها برای کاربر {user_id} ناموفق.")
                    await bot.send_message(user_id, "⚠️ سامانه در آپلود پیوست‌ها مشکل داشت.")
                    await log_event(
                        "خطای سامانه", "لایحه", str(user_id), user_id,
                        tracking_code=tracking_code, doc_name=title,
                        note=f"آپلود پیوست‌ها ناموفق (کد لایحه: {lavayeh_bill_no})"
                    )

                await _click_goto_main(sana_page, bot, user_id)
                await resilient_sleep(sana_page, 4, bot, user_id)

            await _click_step_box(sana_page, "آماده سازي جهت محاسبه هزينه و ارسال", bot, user_id)
            await resilient_sleep(sana_page, 5, bot, user_id)

            preparation_ok = await _click_preparation_with_retry(sana_page, bot, user_id)
            if not preparation_ok:
                await bot.send_message(ADMIN_ID, f"⚠️ [LAVAYEH] آماده‌سازی ناموفق — کاربر {user_id}")
                await bot.send_message(user_id, "⚠️ مرحله آماده‌سازی با مشکل مواجه شد.")
                runtime_state.active_lavayeh_users.discard(user_id)
                await log_event(
                    "خطای سامانه", "لایحه", str(user_id), user_id,
                    tracking_code=tracking_code, doc_name=title,
                    note=f"آماده‌سازی ناموفق (کد لایحه: {lavayeh_bill_no})"
                )
                return

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            await _click_step_box(sana_page, "محاسبه و دريافت هزينه", bot, user_id)
            await resilient_sleep(sana_page, 8, bot, user_id)

            court_total = await _calculate_cost_with_retry(sana_page, bot, user_id)
            logging.info(f"[LAVAYEH] court_total: {court_total}")

            await _click_goto_main(sana_page, bot, user_id)
            await resilient_sleep(sana_page, 4, bot, user_id)

            pdf_path = await _print_lavayeh(sana_page, browser_context, tracking_code, bot, user_id)

            from lavayeh_handlers import send_lavayeh_result
            national_ids = ", ".join([p.get("national_id", "") for p in persons if p.get("national_id")])
            combined_tracking = (
                f"{tracking_code} | کد لایحه: {lavayeh_bill_no}"
                if lavayeh_bill_no else tracking_code
            )
            # ── ارسال نتیجه به همراه اطلاعات لازم برای مرحله امضا ──────
            await send_lavayeh_result(
                bot, user_id, pdf_path, court_total,
                tracking_code=combined_tracking,
                national_ids=national_ids,
                lavayeh_title=title,
                lavayeh_province=province,
                lavayeh_row_number=row_number,
                lavayeh_persons=persons,
            )

            await bot.send_message(
                ADMIN_ID,
                f"✅ [LAVAYEH] ثبت لایحه کاربر {user_id} موفق. هزینه: {court_total:,} تومان"
            )
            runtime_state.active_lavayeh_users.discard(user_id)
            return

        except LavayehFatalError as e:
            runtime_state.active_lavayeh_users.discard(user_id)
            logging.info(f"[LAVAYEH] خطای قطعی برای user={user_id}: {e}")
            await log_event(
                "خطای سامانه", "لایحه", str(user_id), user_id,
                tracking_code=tracking_code, doc_name=title,
                note=f"خطای قطعی: {str(e)[:200]}"
            )
            return

        except Exception as e:
            logging.error(f"[LAVAYEH] تلاش {attempt + 1} ناموفق برای user={user_id}: {e}")
            if attempt < max_attempts - 1:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ [LAVAYEH] تلاش {attempt + 1} ناموفق. ریلود...\nخطا: {str(e)[:300]}"
                )
                try:
                    await sana_page.reload()
                    await asyncio.sleep(6)
                except Exception:
                    pass
            else:
                await bot.send_message(
                    user_id,
                    "⚠️ ثبت لایحه با اختلال مواجه شد. پشتیبانی پیگیری خواهد کرد."
                )
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [LAVAYEH] کاربر {user_id} پس از {max_attempts} تلاش ناموفق."
                )
                runtime_state.active_lavayeh_users.discard(user_id)
                await log_event(
                    "خطای سامانه", "لایحه", str(user_id), user_id,
                    tracking_code=tracking_code, doc_name=title,
                    note=f"پس از {max_attempts} تلاش ناموفق: {str(e)[:200]}"
                )


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی داخلی
# ══════════════════════════════════════════════════════════════════════════════

async def _click_menu_item(page, text: str, bot: Bot, user_id: int):
    clicked = await page.evaluate(f'''() => {{
        const links = Array.from(document.querySelectorAll('a.list-group-item'));
        const target = links.find(el => el.innerText && el.innerText.trim().includes("{text}"));
        if (target) {{ target.click(); return true; }}
        return false;
    }}''')
    if not clicked:
        await safe_click_by_text(page, text, bot, user_id)


async def _select_bill_type(page, search_kw: str, row_idx: int, bot: Bot, user_id: int):
    search_input = page.locator('.ui-select-search').first
    opened = False

    for open_attempt in range(4):
        await page.evaluate('''() => {
            const btn = document.querySelector('.ui-select-toggle');
            if (btn) btn.click();
        }''')
        try:
            await search_input.wait_for(state="visible", timeout=4000)
            opened = True
            break
        except PlaywrightTimeoutError:
            logging.warning(f"[LAVAYEH] dropdown باز نشد (تلاش {open_attempt + 1})")
            await asyncio.sleep(1.5)

    if not opened:
        raise Exception("ui-select dropdown باز نشد.")

    await search_input.fill("")
    await search_input.type(search_kw, delay=150)
    await asyncio.sleep(2)

    clicked = await page.evaluate(f'''(idx) => {{
        const choices = Array.from(document.querySelectorAll('.ui-select-choices-row, .ui-select-choices div[ng-repeat]'));
        const visible = choices.filter(el => {{
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }});
        if (visible.length > idx) {{ visible[idx].click(); return true; }}
        const lis = Array.from(document.querySelectorAll('.ui-select-choices li'));
        const visLis = lis.filter(el => {{
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }});
        if (visLis.length > idx) {{ visLis[idx].click(); return true; }}
        return false;
    }}''', row_idx)

    if not clicked:
        logging.warning(f"[LAVAYEH] نتوانست ردیف {row_idx} برای '{search_kw}' را کلیک کند")


async def _click_taqdim_lavayeh(page, bot: Bot, user_id: int):
    for attempt in range(5):
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('button[ng-click*="setJSSBillType"]');
            if (btn) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "تقدیم لایحه", bot, user_id)
        await asyncio.sleep(3)

        closed = await _close_error_popup(page)
        if closed:
            await asyncio.sleep(4)
            continue

        loaded = await page.evaluate('''() => {
            const steps = Array.from(document.querySelectorAll('.box h5, .step'));
            return steps.some(el => el.innerText && el.innerText.includes("ثبت"));
        }''')
        if loaded:
            return
        await asyncio.sleep(5)


async def _click_step_box(page, step_name: str, bot: Bot, user_id: int):
    clicked = await page.evaluate(f'''() => {{
        const heads = Array.from(document.querySelectorAll('.box h5'));
        const target = heads.find(el => el.innerText && el.innerText.trim().includes("{step_name}"));
        if (target) {{
            const box = target.closest('.box');
            if (box) {{ box.click(); return true; }}
        }}
        return false;
    }}''')
    if not clicked:
        await safe_click_by_text(page, step_name, bot, user_id)


async def _click_step_label(page, step_name: str, bot: Bot, user_id: int):
    clicked = await page.evaluate(f'''() => {{
        const steps = Array.from(document.querySelectorAll('.step'));
        const target = steps.find(el => el.innerText && el.innerText.trim().includes("{step_name}"));
        if (target) {{ target.click(); return true; }}
        return false;
    }}''')
    if not clicked:
        await safe_click_by_text(page, step_name, bot, user_id)


async def _fill_input(page, selector: str, value: str, bot: Bot, user_id: int):
    try:
        elem = page.locator(selector).first
        await elem.click()
        await elem.fill("")
        await elem.fill(value)
        await elem.blur()
    except Exception as e:
        logging.warning(f"[LAVAYEH] _fill_input({selector}) failed: {e}")


async def _select_province(page, province: str, bot: Bot, user_id: int):
    await page.evaluate('''() => {
        const btn = Array.from(document.querySelectorAll('button.ui-select-toggle')).find(b => {
            return b.closest('[name="caseServer"]') ||
                   (b.innerText && b.innerText.includes("دادگستری"));
        });
        if (btn) btn.click();
    }''')
    await asyncio.sleep(2)

    is_tehran_excl = ("به‌جز" in province or "به جز" in province) and "تهران" in province
    is_tehran_city_only = (not is_tehran_excl) and province.strip() == "شهر تهران"

    clicked = await page.evaluate('''(args) => {
        const { province, isTehranExcl, isTehranCityOnly } = args;

        // سامانه سنا از حروف عربی (ي، ك) استفاده می‌کند در حالی که مقدار ذخیره‌شده
        // در ربات با حروف فارسی (ی، ک) است. بدون یکسان‌سازی، هیچ گزینه‌ای مچ نمی‌شد
        // و همین باعث ارور «استان انتخاب نشد» بود.
        const normalize = (s) => (s || '')
            .replace(/\\u064A/g, '\\u06CC')   // ي عربی -> ی فارسی
            .replace(/\\u0643/g, '\\u06A9')   // ك عربی -> ک فارسی
            .replace(/\\u200c/g, ' ')          // نیم‌فاصله -> فاصله ساده
            .trim();

        const normProvince = normalize(province);
        const items = Array.from(document.querySelectorAll('.ui-select-choices-row-inner, .ui-select-choices div'));

        if (isTehranExcl) {
            const target = items.find(el => el.innerText &&
                normalize(el.innerText).includes("تهران") &&
                (normalize(el.innerText).includes("به جز") || normalize(el.innerText).includes("بجز")));
            if (target) { target.click(); return true; }
        } else if (isTehranCityOnly) {
            const target = items.find(el => el.innerText &&
                normalize(el.innerText).includes("تهران") &&
                !normalize(el.innerText).includes("به جز") && !normalize(el.innerText).includes("بجز"));
            if (target) { target.click(); return true; }
        }

        const exact = items.find(el => el.innerText && normalize(el.innerText) === normProvince);
        if (exact) { exact.click(); return true; }
        const fallback = items.find(el => el.innerText && normalize(el.innerText).includes(normProvince));
        if (fallback) { fallback.click(); return true; }
        return false;
    }''', {"province": province, "isTehranExcl": is_tehran_excl, "isTehranCityOnly": is_tehran_city_only})

    if not clicked:
        logging.warning(f"[LAVAYEH] نتوانست استان '{province}' را انتخاب کند")


async def _click_validate_with_retry(page, bot: Bot, user_id: int):
    for attempt in range(5):
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('#btnAddHst1');
            if (btn) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "صحت سنجی اطلاعات", bot, user_id)
        await asyncio.sleep(12)

        closed = await _close_error_popup(page)
        if closed:
            await asyncio.sleep(5)
            continue

        has_table = await page.evaluate('''() => {
            const table = document.querySelector('table tbody tr');
            return table !== null;
        }''')
        if has_table:
            return
        await asyncio.sleep(5)


async def _wait_for_case_table(page, bot: Bot, user_id: int, timeout_sec: int = 30) -> bool:
    for _ in range(timeout_sec):
        has_table = await page.evaluate('''() => {
            const tbody = document.querySelector('table tbody');
            return tbody && tbody.querySelectorAll('tr').length > 0;
        }''')
        if has_table:
            return True
        await asyncio.sleep(1)
    return False


async def _click_add_person(page, bot: Bot, user_id: int):
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#btnAddSection');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        await safe_click_by_text(page, "افزودن", bot, user_id)


async def _click_sana_query_with_retry(
    page, ng_click_contains: str, bot: Bot, user_id: int,
    btn_id: str = None, max_retries: int = 5
):
    for attempt in range(max_retries):
        by_id_js = (
            f'const byId = document.querySelector("#{btn_id}"); '
            f'if (byId && !byId.disabled) {{ byId.click(); return true; }}'
            if btn_id else ""
        )
        clicked = await page.evaluate(f'''() => {{
            {by_id_js}
            const btns = Array.from(document.querySelectorAll('button[ng-click*="{ng_click_contains}"]'));
            const btn = btns.find(b => !b.disabled);
            if (btn) {{ btn.click(); return true; }}
            return false;
        }}''')

        if not clicked:
            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button.btn-warning'));
                const btn = btns.find(b => {
                    const tip = b.getAttribute("tooltip") || b.getAttribute("title") || "";
                    return tip.includes("استعلام") || tip.includes("ثنا");
                });
                if (btn && !btn.disabled) btn.click();
            }''')

        await asyncio.sleep(10)

        closed = await _close_error_popup(page)
        if closed:
            await asyncio.sleep(5)
            continue

        extracted = await page.evaluate('''() => {
            const disabled = document.querySelector(
                'input[ng-disabled*="ExtractedFromSana"][ng-disabled*="1"],' +
                'input[disabled]'
            );
            return disabled !== null;
        }''')
        if extracted:
            return
        await asyncio.sleep(3)


async def _click_save_temp_with_retry(page, bot: Bot, user_id: int, max_retries: int = 5):
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
            const h2 = popup.querySelector('h2');
            return icon && window.getComputedStyle(icon).display !== 'none' &&
                   h2 && (h2.innerText.includes("ثبت") || h2.innerText.includes("ویرایش") || h2.innerText.includes("موفقیت"));
        }''')

        if success:
            await _close_success_popup(page)
            return

        error_text = await _get_and_close_error_popup_text(page)
        if error_text:
            if "درج نشده" in error_text or ("شخص" in error_text and "سامانه" in error_text):
                await bot.send_message(
                    user_id,
                    f"⚠️ **خطا در ثبت موقت:**\n\n«{error_text}»\n\n"
                    "فرآیند متوقف شد. اطلاعات اشخاص را بررسی و مجدداً اقدام نمایید.",
                    parse_mode="Markdown"
                )
                await bot.send_message(
                    ADMIN_ID,
                    f"❌ [LAVAYEH] خطای قطعی در ثبت موقت کاربر {user_id}: {error_text}"
                )
                raise LavayehFatalError(error_text)

            logging.warning(f"[LAVAYEH] ثبت موقت: «{error_text}» (تلاش {attempt + 1})")
            await asyncio.sleep(5)
            continue

        await asyncio.sleep(5)


async def _click_goto_main(page, bot: Bot, user_id: int):
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#gotoMainPage');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }''')
    if not clicked:
        await soft_click_if_exists(page, "بازگشت به فهرست")


MAX_IMAGE_BYTES = 450 * 1024


def _compress_image_if_needed(path: str, max_bytes: int = MAX_IMAGE_BYTES) -> str:
    try:
        if os.path.getsize(path) <= max_bytes:
            return path
    except OSError:
        return path

    try:
        from PIL import Image
    except ImportError:
        logging.warning(f"[LAVAYEH] Pillow نصب نیست؛ فشرده‌سازی '{path}' انجام نشد.")
        return path

    try:
        img = Image.open(path).convert("RGB")
        out_path = os.path.splitext(path)[0] + "_compressed.jpg"

        quality = 90
        width, height = img.size
        while True:
            img.save(out_path, "JPEG", quality=quality, optimize=True)
            if os.path.getsize(out_path) <= max_bytes or (quality <= 30 and width <= 600):
                break
            if quality > 30:
                quality -= 15
            else:
                width = int(width * 0.8)
                height = int(height * 0.8)
                img = img.resize((width, height), Image.LANCZOS)

        logging.info(f"[LAVAYEH] فشرده‌سازی '{path}': {os.path.getsize(out_path)} بایت")
        try:
            os.remove(path)
        except OSError:
            pass
        return out_path
    except Exception as e:
        logging.error(f"[LAVAYEH] خطا در فشرده‌سازی '{path}': {e}")
        return path


async def _download_images_from_telegram(bot: Bot, file_ids: list, user_id: int) -> list:
    paths = []
    for i, file_id in enumerate(file_ids):
        try:
            file_info = await bot.get_file(file_id)
            ext = "jpg"
            if file_info.file_path:
                ext = file_info.file_path.split(".")[-1].lower()
                if ext not in ("jpg", "jpeg", "png"):
                    ext = "jpg"

            path = f"lavayeh_img_{user_id}_{i}.{ext}"
            await bot.download_file(file_info.file_path, path)
            path = _compress_image_if_needed(path)
            paths.append(path)
        except Exception as e:
            logging.error(f"[LAVAYEH] خطا در دانلود تصویر {i} برای user {user_id}: {e}")
    return paths


async def _upload_attachment_groups(page, groups_with_paths: list, bot: Bot, user_id: int) -> bool:
    for group in groups_with_paths:
        ok = await _upload_single_attachment_group(page, group["title"], group["paths"], bot, user_id)
        if not ok:
            return False
    return True


async def _upload_single_attachment_group(page, doc_title: str, image_paths: list, bot: Bot, user_id: int) -> bool:
    image_count = len(image_paths)
    for upload_attempt in range(2):
        try:
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

            await page.evaluate('''() => {
                const inputs = Array.from(document.querySelectorAll('input#txtNo'));
                if (inputs.length > 0) {
                    inputs[0].value = "0";
                    inputs[0].dispatchEvent(new Event("input", { bubbles: true }));
                }
            }''')

            escaped_title = doc_title.replace("`", "'").replace("\\", "")
            await page.evaluate(f'''() => {{
                const inputs = Array.from(document.querySelectorAll('input#txtName'));
                if (inputs.length > 0) {{
                    inputs[0].value = "{escaped_title}";
                    inputs[0].dispatchEvent(new Event("input", {{ bubbles: true }}));
                }}
            }}''')

            await page.evaluate(f'''() => {{
                const inp = document.querySelector('#txt001');
                if (inp) {{
                    inp.value = "{image_count}";
                    inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
                }}
            }}''')

            await page.evaluate('''() => {
                const btn = document.querySelector('#incAttach0');
                if (btn && !btn.disabled) btn.click();
            }''')
            await asyncio.sleep(3)

            await _click_save_doc_with_retry(page, bot, user_id)
            await asyncio.sleep(5)

            await _close_success_popup(page)
            await asyncio.sleep(3)

            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button[ng-click*="editDocument"]'));
                if (btns.length > 0) btns[btns.length - 1].click();
            }''')
            await asyncio.sleep(4)

            file_input = page.locator('input[type="file"]').first
            if image_paths:
                await file_input.set_input_files(image_paths)
                await asyncio.sleep(3)

            await page.evaluate('''() => {
                const btn = document.querySelector('#btnUploadAll');
                if (btn && !btn.disabled) btn.click();
            }''')

            all_uploaded = await _wait_for_upload_alerts(page, image_count)

            if not all_uploaded:
                await asyncio.sleep(30)
                await _click_step_box(page, "منضمات", bot, user_id)
                await asyncio.sleep(5)
                await page.evaluate('''() => {
                    const btns = Array.from(document.querySelectorAll('button[ng-click*="editDocument"]'));
                    if (btns.length > 0) btns[btns.length - 1].click();
                }''')
                await asyncio.sleep(4)
                await _delete_uploaded_files(page)
                await asyncio.sleep(3)
                continue

            all_confirmed = await _click_apply_all_with_retry(page, image_count, bot, user_id)
            if all_confirmed:
                return True

        except Exception as e:
            logging.error(f"[LAVAYEH] آپلود '{doc_title}' تلاش {upload_attempt + 1} ناموفق: {e}")
            await asyncio.sleep(5)

    bill_no = await _extract_bill_no(page)
    await bot.send_message(ADMIN_ID, f"❌ [LAVAYEH] آپلود «{doc_title}» ناموفق. کد: {bill_no} | کاربر: {user_id}")
    await bot.send_message(user_id, f"⚠️ سامانه در آپلود «{doc_title}» مشکل داشت.")
    return False


async def _click_save_doc_with_retry(page, bot: Bot, user_id: int, max_retries: int = 3):
    for attempt in range(max_retries):
        await page.evaluate('''() => {
            const btn = document.querySelector('#btnSaveDoc');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(8)

        success = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const icon = popup.querySelector('.sa-icon.sa-success');
            return icon && window.getComputedStyle(icon).display !== 'none';
        }''')
        if success:
            return

        await _close_error_popup(page)
        await asyncio.sleep(4)


async def _wait_for_upload_alerts(page, expected_count: int, timeout_sec: int = 120) -> bool:
    for _ in range(timeout_sec * 2):
        count = await page.evaluate('''() => {
            const alerts = Array.from(document.querySelectorAll('.alert-success [ng-bind-html]'));
            return alerts.filter(el => el.innerText && el.innerText.includes("پیوست مورد نظر با موفقیت ثبت گردید")).length;
        }''')
        if count >= expected_count:
            return True
        await asyncio.sleep(0.5)
    return False


async def _delete_uploaded_files(page):
    while True:
        deleted = await page.evaluate('''() => {
            const btn = document.querySelector('button[ng-click*="removeAttachment"]');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }''')
        if not deleted:
            break
        await asyncio.sleep(2)


async def _click_apply_all_with_retry(page, expected_count: int, bot: Bot, user_id: int, max_retries: int = 2) -> bool:
    for attempt in range(max_retries):
        await page.evaluate('''() => {
            const btn = document.querySelector('#btnApplyAll');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(10)

        confirmed = await page.evaluate(f'''() => {{
            const alerts = Array.from(document.querySelectorAll('[ng-bind-html]'));
            return alerts.filter(el => el.innerText && el.innerText.includes("پیوست مورد نظر با موفقیت تایید شد")).length >= {expected_count};
        }}''')
        if confirmed:
            return True
        await asyncio.sleep(30)

    return False


async def _click_preparation_with_retry(page, bot: Bot, user_id: int, max_retries: int = 3) -> bool:
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

        closed = await _close_error_popup(page)
        if closed:
            await asyncio.sleep(30)
            await _close_success_popup(page)
            continue

        await asyncio.sleep(5)

    return False


async def _calculate_cost_with_retry(page, bot: Bot, user_id: int, max_retries: int = 3) -> int:
    for attempt in range(max_retries):
        await _close_error_popup(page)
        await asyncio.sleep(2)

        await page.evaluate('''() => {
            const btn = document.querySelector('#btnCalculateCash');
            if (btn && !btn.disabled) btn.click();
        }''')
        await asyncio.sleep(40)

        closed = await _close_error_popup(page)
        if closed:
            await asyncio.sleep(30)
            continue

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


async def _print_lavayeh(page, browser_context, tracking_code: str, bot: Bot, user_id: int):
    pdf_path = f"lavayeh_{tracking_code}.pdf"

    try:
        async def click_print():
            await page.evaluate('''() => {
                const heads = Array.from(document.querySelectorAll('.box h5'));
                const target = heads.find(el => el.innerText && (
                    el.innerText.includes("چاپ اوليه") || el.innerText.includes("چاپ اولیه")
                ));
                if (target) {
                    const box = target.closest('.box');
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
        logging.error(f"[LAVAYEH] خطا در چاپ: {e}")
        try:
            await page.pdf(path=pdf_path, format="A4")
        except Exception:
            pass

    return pdf_path


async def _extract_bill_no(page) -> str:
    try:
        val = await page.evaluate('''() => {
            const inp = document.querySelector('#txtBillNo');
            return inp ? inp.value : "";
        }''')
        return val or "نامشخص"
    except Exception:
        return "نامشخص"


async def _close_error_popup(page) -> bool:
    closed = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;
        const successIcon = popup.querySelector('.sa-icon.sa-success');
        if (successIcon && window.getComputedStyle(successIcon).display !== 'none') return false;
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); return true; }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


async def _get_and_close_error_popup_text(page):
    text = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return null;
        const successIcon = popup.querySelector('.sa-icon.sa-success');
        if (successIcon && window.getComputedStyle(successIcon).display !== 'none') return null;
        const h2 = popup.querySelector('h2');
        const p = popup.querySelector('p');
        const msg = [h2 ? h2.innerText : '', p ? p.innerText : ''].filter(Boolean).join(' - ').trim();
        const btn = popup.querySelector('button.confirm');
        if (btn) { btn.click(); }
        return msg || 'خطای نامشخص';
    }''')
    if text:
        await asyncio.sleep(1)
    return text


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
