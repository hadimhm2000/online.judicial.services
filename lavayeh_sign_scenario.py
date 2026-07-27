"""
سناریوی اخذ امضای الکترونیک لایحه در سامانه ثنا.

جریان کلی:
  ۱. ناوبری به بخش «ارایه و پیگیری لایحه» → جستجو با کد رهگیری
  ۲. ورود به مرحله «اخذ امضای الکترونیک»
  ۳. یافتن جدول اشخاص قابل امضا
  ۴. ارسال کد موقت برای هر شخص (actions.sendTempPassword)
  ۵. اعلام موفقیت به کاربر
  ۶. دریافت کد(های) تایید از کاربر
  ۷. وارد کردن کد و کلیک «امضاء ثنا» (actions.getPersonDataSign)
"""

import asyncio
import logging

from aiogram import Bot

import runtime_state
from browser_helpers import (
    check_and_handle_expiry,
    goto_url_with_retry,
    human_delay,
    resilient_sleep,
    safe_click_by_text,
    wait_for_angular_idle,
)
from config import ADMIN_ID

# ── نگاشت عنوان لایحه به مسیر منو (همانند lavayeh_scenario.py) ─────────────
TITLE_SEARCH_MAP = {
    "لایحه دفاعیه":              ("دفا",   0),
    "صدور اجرائیه":               ("اجرائ", 0),
    "اعتراض به نظر کارشناس":      ("کارشن", 1),
    "اعتراض به قرار رد دفتر":     ("قرار",  1),
    "سایر عناوین":                ("دفا",   0),
}


async def send_sign_codes(
    bot: Bot,
    user_id: int,
    tracking_code: str,
    province: str,
    row_number: int,
    lavayeh_title: str,
) -> bool:
    """
    وارد سامانه می‌شود، صفحه اخذ امضا را باز می‌کند و
    برای هر شخص واجد شرایط کد موقت ارسال می‌کند.

    Returns:
        True  اگر حداقل یک کد با موفقیت ارسال شد
        False در صورت هر نوع خطای قطعی
    """
    sana_page = runtime_state.sana_page
    if sana_page is None:
        logging.error("[SIGN] sana_page is None")
        return False

    try:
        # ── ۱. رفتن به صفحه اصلی ────────────────────────────────────────
        ok = await goto_url_with_retry(
            sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
        )
        if not ok:
            return False
        await human_delay(3.0, 5.0)

        # ── ۲. کلیک روی «ارایه و پیگیری لایحه» ─────────────────────────
        clicked = await sana_page.evaluate('''() => {
            const links = Array.from(document.querySelectorAll('a.list-group-item'));
            const t = links.find(el => el.innerText && el.innerText.includes("ارایه و پیگیری لایحه"));
            if (t) { t.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(sana_page, "ارایه و پیگیری لایحه", bot, user_id)
        await resilient_sleep(sana_page, 5, bot, user_id)

        # ── ۳. انتخاب نوع لایحه ─────────────────────────────────────────
        search_kw, row_idx = TITLE_SEARCH_MAP.get(lavayeh_title, ("دفا", 0))
        await _select_bill_type(sana_page, search_kw, row_idx)
        await resilient_sleep(sana_page, 3, bot, user_id)

        # ── ۴. کلیک «تقدیم لایحه» ───────────────────────────────────────
        await _click_taqdim(sana_page, bot, user_id)
        await resilient_sleep(sana_page, 8, bot, user_id)

        # ── ۵. کلیک «جستجوی لایحه» ──────────────────────────────────────
        await safe_click_by_text(sana_page, "جستجوی لایحه", bot, user_id)
        await resilient_sleep(sana_page, 4, bot, user_id)

        # ── ۶. وارد کردن کد رهگیری و جستجو ──────────────────────────────
        await _fill_input(sana_page, "#txtPetitionNo, #billNo", tracking_code)
        await resilient_sleep(sana_page, 1, bot, user_id)

        await sana_page.evaluate('''() => {
            const btn = document.querySelector('#btnGetJSSPetition');
            if (btn) { btn.click(); return; }
            const btns = Array.from(document.querySelectorAll('button'));
            const s = btns.find(b => b.innerText && b.innerText.includes("جستجو"));
            if (s) s.click();
        }''')
        await resilient_sleep(sana_page, 8, bot, user_id)

        # بستن هر پنجره خطایی
        await _close_any_popup(sana_page)
        await resilient_sleep(sana_page, 2, bot, user_id)

        # ── ۷. ورود به مرحله «اخذ امضای الکترونیک» ─────────────────────
        clicked_sign = await sana_page.evaluate('''() => {
            const heads = Array.from(document.querySelectorAll('.box h5'));
            const t = heads.find(el => el.innerText && el.innerText.includes("اخذ امضا"));
            if (t) {
                const box = t.closest('.box');
                if (box) { box.click(); return true; }
            }
            return false;
        }''')
        if not clicked_sign:
            await safe_click_by_text(sana_page, "اخذ امضاي الكترونيك", bot, user_id)
        await resilient_sleep(sana_page, 6, bot, user_id)

        # ── ۸. یافتن اشخاص قابل امضا و ارسال کد ────────────────────────
        persons_info = await sana_page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="theBillPersonSignableList"]'
            ));
            return rows.map((tr, idx) => {
                // نام شخص از ستون آخرولی
                const nameTd = tr.querySelector(
                    'td.font-yekan.font-size-12.text-right.line-height-20.vertical-align-middle'
                );
                const name = nameTd ? nameTd.innerText.trim() : "";
                // آیا دکمه ارسال کد موجود و فعال هست؟
                const sendBtn = tr.querySelector(
                    'button[ng-click*="sendTempPassword"]'
                );
                const canSend = sendBtn && !sendBtn.disabled;
                // آیا اصلاً div ارسال کد نمایش دارد؟
                const sendDiv = tr.querySelector(
                    'div[ng-if*="!(item.NationalityCode"]'
                );
                const divVisible = sendDiv &&
                    window.getComputedStyle(sendDiv).display !== "none";
                return { idx, name, canSend, divVisible };
            });
        }''')

        logging.info(f"[SIGN] persons_info: {persons_info}")

        # اشخاصی که باید کد برایشان ارسال شود
        sendable = [p for p in persons_info if p.get("divVisible")]

        if not sendable:
            await bot.send_message(
                user_id,
                "⚠️ **در جدول امضا، شخصی برای ارسال کد موقت یافت نشد.**\n\n"
                "احتمالاً همه اشخاص قبلاً امضا کرده‌اند یا نوع امضا متفاوت است.\n"
                "چاپ لایحه خود را جهت ادامه تکمیل نمودن به واتساپ به شماره "
                "**09306186888** ارسال فرمائید.",
                parse_mode="Markdown"
            )
            return False

        sent_count = 0
        for person in sendable:
            idx = person["idx"]
            name = person["name"] or f"شخص {idx + 1}"
            success = await _send_temp_password_for_row(sana_page, idx, bot, user_id, name)
            if success:
                sent_count += 1

        return sent_count > 0

    except Exception as e:
        logging.error(f"[SIGN] send_sign_codes error: {e}")
        return False


async def submit_sign_codes(
    bot: Bot,
    user_id: int,
    tracking_code: str,
    province: str,
    row_number: int,
    lavayeh_title: str,
    sign_codes: dict,  # {row_index_str: code} یا {national_id: code}
) -> bool:
    """
    کدهای دریافت‌شده از کاربر را در سامانه وارد و امضا می‌کند.

    sign_codes: دیکشنری {row_idx (int): code (str)}

    Returns True اگر حداقل یک امضا موفق بود.
    """
    sana_page = runtime_state.sana_page
    if sana_page is None:
        return False

    try:
        # ── ناوبری مجدد به صفحه اخذ امضا ─────────────────────────────
        ok = await goto_url_with_retry(
            sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
        )
        if not ok:
            return False
        await human_delay(3.0, 5.0)

        clicked = await sana_page.evaluate('''() => {
            const links = Array.from(document.querySelectorAll('a.list-group-item'));
            const t = links.find(el => el.innerText && el.innerText.includes("ارایه و پیگیری لایحه"));
            if (t) { t.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(sana_page, "ارایه و پیگیری لایحه", bot, user_id)
        await resilient_sleep(sana_page, 5, bot, user_id)

        search_kw, row_idx = TITLE_SEARCH_MAP.get(lavayeh_title, ("دفا", 0))
        await _select_bill_type(sana_page, search_kw, row_idx)
        await resilient_sleep(sana_page, 3, bot, user_id)

        await _click_taqdim(sana_page, bot, user_id)
        await resilient_sleep(sana_page, 8, bot, user_id)

        await safe_click_by_text(sana_page, "جستجوی لایحه", bot, user_id)
        await resilient_sleep(sana_page, 4, bot, user_id)

        await _fill_input(sana_page, "#txtPetitionNo, #billNo", tracking_code)
        await resilient_sleep(sana_page, 1, bot, user_id)

        await sana_page.evaluate('''() => {
            const btn = document.querySelector('#btnGetJSSPetition');
            if (btn) { btn.click(); return; }
            const btns = Array.from(document.querySelectorAll('button'));
            const s = btns.find(b => b.innerText && b.innerText.includes("جستجو"));
            if (s) s.click();
        }''')
        await resilient_sleep(sana_page, 8, bot, user_id)
        await _close_any_popup(sana_page)
        await resilient_sleep(sana_page, 2, bot, user_id)

        clicked_sign = await sana_page.evaluate('''() => {
            const heads = Array.from(document.querySelectorAll('.box h5'));
            const t = heads.find(el => el.innerText && el.innerText.includes("اخذ امضا"));
            if (t) {
                const box = t.closest('.box');
                if (box) { box.click(); return true; }
            }
            return false;
        }''')
        if not clicked_sign:
            await safe_click_by_text(sana_page, "اخذ امضاي الكترونيك", bot, user_id)
        await resilient_sleep(sana_page, 6, bot, user_id)

        # ── وارد کردن کد و کلیک امضا برای هر شخص ─────────────────────
        success_count = 0
        for row_idx_key, code in sign_codes.items():
            row_idx_int = int(row_idx_key)
            ok = await _enter_code_and_sign(sana_page, row_idx_int, code, bot, user_id)
            if ok:
                success_count += 1

        return success_count > 0

    except Exception as e:
        logging.error(f"[SIGN] submit_sign_codes error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی داخلی
# ══════════════════════════════════════════════════════════════════════════════

async def _select_bill_type(page, search_kw: str, row_idx: int):
    """انتخاب نوع لایحه از dropdown"""
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    search_input = page.locator('.ui-select-search').first
    opened = False
    for _ in range(4):
        await page.evaluate('''() => {
            const btn = document.querySelector('.ui-select-toggle');
            if (btn) btn.click();
        }''')
        try:
            await search_input.wait_for(state="visible", timeout=4000)
            opened = True
            break
        except PlaywrightTimeoutError:
            await asyncio.sleep(1.5)

    if not opened:
        return

    await search_input.fill("")
    await search_input.type(search_kw, delay=150)
    await asyncio.sleep(2)

    await page.evaluate(f'''(idx) => {{
        const choices = Array.from(document.querySelectorAll(
            '.ui-select-choices-row, .ui-select-choices div[ng-repeat]'
        ));
        const visible = choices.filter(el => {{
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        }});
        if (visible.length > idx) {{ visible[idx].click(); return; }}
        const lis = Array.from(document.querySelectorAll('.ui-select-choices li'));
        const vl = lis.filter(el => {{
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        }});
        if (vl.length > idx) vl[idx].click();
    }}''', row_idx)


async def _click_taqdim(page, bot: Bot, user_id: int):
    """کلیک روی دکمه تقدیم لایحه"""
    for _ in range(5):
        clicked = await page.evaluate('''() => {
            const btn = document.querySelector('button[ng-click*="setJSSBillType"]');
            if (btn) { btn.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(page, "تقدیم لایحه", bot, user_id)
        await asyncio.sleep(3)
        await _close_any_popup(page)
        await asyncio.sleep(4)

        loaded = await page.evaluate('''() => {
            const steps = Array.from(document.querySelectorAll('.box h5, .step'));
            return steps.some(el => el.innerText && el.innerText.includes("ثبت"));
        }''')
        if loaded:
            return
        await asyncio.sleep(5)


async def _fill_input(page, selector: str, value: str):
    """پر کردن فیلد ورودی"""
    try:
        elem = page.locator(selector).first
        await elem.click()
        await elem.fill("")
        await elem.fill(value)
        await elem.blur()
    except Exception as e:
        logging.warning(f"[SIGN] _fill_input({selector}) failed: {e}")


async def _close_any_popup(page) -> bool:
    """بستن هر پنجره پاپ‌آپ (موفق یا خطا)"""
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


async def _send_temp_password_for_row(
    page, row_idx: int, bot: Bot, user_id: int, person_name: str
) -> bool:
    """
    ارسال کد موقت برای یک ردیف از جدول امضا.
    حداکثر ۳ بار تلاش می‌کند.
    Returns True اگر کد ارسال شد (یا قبلاً ارسال شده بود).
    """
    for attempt in range(3):
        # کلیک دکمه ارسال کد
        clicked = await page.evaluate(f'''(idx) => {{
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="theBillPersonSignableList"]'
            ));
            if (rows.length <= idx) return false;
            const btn = rows[idx].querySelector('button[ng-click*="sendTempPassword"]');
            if (btn && !btn.disabled) {{ btn.click(); return true; }}
            return false;
        }}''', row_idx)

        if not clicked:
            logging.warning(f"[SIGN] دکمه ارسال کد برای ردیف {row_idx} پیدا نشد (تلاش {attempt+1})")
            await asyncio.sleep(5)
            continue

        # انتظار برای پاپ‌آپ (10 تا 50 ثانیه)
        popup_result = await _wait_for_popup_result(page, timeout_sec=55)

        if popup_result == "success":
            # «رمز موقت به شماره همراه ارسال شد»
            await _close_any_popup(page)
            await bot.send_message(
                user_id,
                f"✅ **کد موقت امضا** برای **{person_name}** ارسال شد.\n"
                "⏰ توجه: مهلت استفاده از این کد **۷ دقیقه** می‌باشد.\n\n"
                "لطفاً کد دریافتی را هرچه سریع‌تر ارسال کنید."
            )
            logging.info(f"[SIGN] کد موقت برای ردیف {row_idx} ({person_name}) ارسال شد.")
            return True

        elif popup_result == "already_sent":
            # «رمز موقت امضاء لایحه طی ۱۰ دقیقه گذشته ارسال شده است»
            await _close_any_popup(page)
            await bot.send_message(
                user_id,
                f"✅ **کد موقت امضا** برای **{person_name}** قبلاً ارسال شده است و هنوز معتبر می‌باشد.\n"
                "لطفاً کد دریافتی را هرچه سریع‌تر ارسال کنید."
            )
            logging.info(f"[SIGN] کد قبلاً ارسال شده برای ردیف {row_idx}")
            return True

        else:
            # خطای دیگر — تلاش مجدد
            await _close_any_popup(page)
            logging.warning(f"[SIGN] خطای ناشناخته در ارسال کد ردیف {row_idx} (تلاش {attempt+1})")
            await asyncio.sleep(5)
            continue

    return False


async def _wait_for_popup_result(page, timeout_sec: int = 55) -> str:
    """
    منتظر می‌ماند تا پاپ‌آپ نتیجه ظاهر شود.
    Returns:
        "success"      — ارسال موفق
        "already_sent" — قبلاً ارسال شده
        "error"        — هر خطای دیگر
        "timeout"      — timeout
    """
    for _ in range(timeout_sec * 2):
        result = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const h2 = popup.querySelector('h2');
            const text = h2 ? h2.innerText.trim() : "";
            const successIcon = popup.querySelector('.sa-icon.sa-success');
            const errorIcon = popup.querySelector('.sa-icon.sa-error');
            const isSuccessVisible = successIcon &&
                window.getComputedStyle(successIcon).display !== "none";
            const isErrorVisible = errorIcon &&
                window.getComputedStyle(errorIcon).display !== "none";

            if (isSuccessVisible) {
                if (text.includes("ارسال شد")) return "success";
                return "success";
            }
            if (isErrorVisible) {
                if (text.includes("10 دقیقه") || text.includes("۱۰ دقیقه")) {
                    return "already_sent";
                }
                return "error";
            }
            return null;
        }''')
        if result:
            return result
        await asyncio.sleep(0.5)

    return "timeout"


async def _enter_code_and_sign(
    page, row_idx: int, code: str, bot: Bot, user_id: int
) -> bool:
    """
    کد را در فیلد txtTempPassword وارد می‌کند و دکمه «امضاء ثنا» را می‌زند.
    حداکثر ۳ بار تلاش می‌کند.
    Returns True اگر امضا با موفقیت انجام شد.
    """
    for attempt in range(3):
        # پاک کردن و وارد کردن کد
        filled = await page.evaluate(f'''(args) => {{
            const idx = args.idx;
            const code = args.code;
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="theBillPersonSignableList"]'
            ));
            if (rows.length <= idx) return false;
            const inp = rows[idx].querySelector('input[id^="txtTempPassword"]');
            if (!inp) return false;
            inp.value = code;
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
            inp.dispatchEvent(new Event("change", {{ bubbles: true }}));
            // trigger angular ng-model
            const scope = angular.element(inp).scope();
            if (scope) {{
                scope.$apply(() => {{
                    const key = inp.getAttribute("ng-model");
                    if (key) {{
                        const parts = key.split(".");
                        let obj = scope;
                        for (let i = 0; i < parts.length - 1; i++) obj = obj[parts[i]];
                        obj[parts[parts.length - 1]] = code;
                    }}
                }});
            }}
            return true;
        }}''', {"idx": row_idx, "code": code})

        if not filled:
            logging.warning(f"[SIGN] وارد کردن کد در ردیف {row_idx} ناموفق (تلاش {attempt+1})")
            await asyncio.sleep(3)
            continue

        await asyncio.sleep(1)

        # کلیک دکمه «امضاء ثنا»
        clicked = await page.evaluate(f'''(idx) => {{
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="theBillPersonSignableList"]'
            ));
            if (rows.length <= idx) return false;
            const btn = rows[idx].querySelector(
                'button[ng-click*="getPersonDataSign"]'
            );
            if (btn) {{
                btn.disabled = false;
                btn.click();
                return true;
            }}
            return false;
        }}''', row_idx)

        if not clicked:
            logging.warning(f"[SIGN] دکمه امضاء ثنا در ردیف {row_idx} پیدا نشد (تلاش {attempt+1})")
            await asyncio.sleep(3)
            continue

        # انتظار برای نتیجه (10 تا 50 ثانیه)
        popup_result = await _wait_for_sign_popup(page, timeout_sec=55)

        if popup_result == "success":
            await _close_any_popup(page)
            logging.info(f"[SIGN] امضای ردیف {row_idx} موفق.")
            return True

        else:
            # خطا — تلاش مجدد از مرحله ناوبری به اخذ امضا
            await _close_any_popup(page)
            logging.warning(f"[SIGN] امضای ردیف {row_idx} ناموفق: {popup_result} (تلاش {attempt+1})")

            # بازگشت به مرحله اخذ امضا
            clicked_sign = await page.evaluate('''() => {
                const heads = Array.from(document.querySelectorAll('.box h5'));
                const t = heads.find(el => el.innerText && el.innerText.includes("اخذ امضا"));
                if (t) {
                    const box = t.closest('.box');
                    if (box) { box.click(); return true; }
                }
                return false;
            }''')
            if not clicked_sign:
                await safe_click_by_text(page, "اخذ امضاي الكترونيك", bot, user_id)
            await asyncio.sleep(6)

    return False


async def _wait_for_sign_popup(page, timeout_sec: int = 55) -> str:
    """
    منتظر پاپ‌آپ نتیجه امضا می‌ماند.
    Returns: "success" | "error" | "timeout"
    """
    for _ in range(timeout_sec * 2):
        result = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return null;
            const successIcon = popup.querySelector('.sa-icon.sa-success');
            const errorIcon = popup.querySelector('.sa-icon.sa-error');
            const isSuccessVisible = successIcon &&
                window.getComputedStyle(successIcon).display !== "none";
            const isErrorVisible = errorIcon &&
                window.getComputedStyle(errorIcon).display !== "none";
            if (isSuccessVisible) return "success";
            if (isErrorVisible) return "error";
            return null;
        }''')
        if result:
            return result
        await asyncio.sleep(0.5)
    return "timeout"
