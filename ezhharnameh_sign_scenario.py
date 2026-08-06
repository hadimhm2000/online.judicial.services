"""
سناریوی اخذ امضای الکترونیک اظهارنامه در سامانه ثنا.

جریان کلی:
  ۱. ناوبری به بخش «ارایه و پیگیری اظهارنامه»
  ۲. وارد کردن کد رهگیری و جستجو
  ۳. بستن پاپ‌آپ تأیید بازیابی
  ۴. ورود به مرحله «اخذ امضای الکترونیک»
  ۵. یافتن جدول اشخاص قابل امضا
  ۶. ارسال کد موقت برای شخص(های) انتخاب‌شده
  ۷. وارد کردن کد تایید و امضا (actions.getPersonDataSign)

تفاوت با لایحه:
  - از منوی «ارایه و پیگیری اظهارنامه» (نه لایحه) وارد می‌شود
  - فیلد کد رهگیری: #txtPetitionNo
  - دکمه جستجو: #btnGetJSSPetition
  - اگر اظهارنامه دارای وکیل بود: فقط برای وکیل کد ارسال می‌شود
  - اگر نماینده/مدیرعامل داشت: برای همه آن‌ها کد ارسال می‌شود
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
    wait_for_horizontal_loading_bar,
)
from config import ADMIN_ID


async def send_ezhhar_sign_codes(
    bot: Bot,
    user_id: int,
    tracking_code: str,
    target_row_indices: list = None,
) -> dict:
    """
    وارد سامانه می‌شود، صفحه اخذ امضا اظهارنامه را باز می‌کند و
    برای اشخاص مشخص‌شده (target_row_indices) کد موقت ارسال می‌کند.

    اگر target_row_indices مشخص نشود، برای همه اشخاص قابل ارسال کد می‌فرستد.

    Returns:
        dict با کلیدهای:
          - success: bool
          - persons: list of dicts (idx, name, person_type, sent)
          - error: str (در صورت خطا)
    """
    sana_page = runtime_state.sana_page
    if sana_page is None:
        logging.error("[EZHHAR_SIGN] sana_page is None")
        return {"success": False, "persons": [], "error": "sana_page is None"}

    try:
        # ── ۱. رفتن به صفحه اصلی ────────────────────────────────────────
        ok = await goto_url_with_retry(
            sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
        )
        if not ok:
            return {"success": False, "persons": [], "error": "خطا در بارگذاری صفحه"}

        await human_delay(3.0, 5.0)

        # ── ۲. کلیک روی «ارایه و پیگیری اظهارنامه» ────────────────────
        clicked = await sana_page.evaluate('''() => {
            const links = Array.from(document.querySelectorAll('a.list-group-item'));
            const t = links.find(el => el.innerText && el.innerText.includes("ارایه و پیگیری اظهارنامه"));
            if (t) { t.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(sana_page, "ارایه و پیگیری اظهارنامه", bot, user_id)
        await resilient_sleep(sana_page, 5, bot, user_id)

        # ── ۳. انتخاب radio «جستجوی اظهارنامه» (value=2) ───────────────
        await sana_page.evaluate('''() => {
            const radio = document.querySelector('input[type="radio"][value="2"]');
            if (radio) { radio.click(); return true; }
            return false;
        }''')
        await asyncio.sleep(1)

        # ── ۴. وارد کردن کد رهگیری ────────────────────────────────────
        await _fill_input(sana_page, "#txtPetitionNo", tracking_code)
        await resilient_sleep(sana_page, 1, bot, user_id)

        # ── ۵. کلیک جستجو ──────────────────────────────────────────────
        await sana_page.evaluate('''() => {
            const btn = document.querySelector('#btnGetJSSPetition');
            if (btn) { btn.click(); return; }
            const btns = Array.from(document.querySelectorAll('button'));
            const s = btns.find(b => b.innerText && b.innerText.includes("جستجو"));
            if (s) s.click();
        }''')

        # صبر اولیه
        await asyncio.sleep(3)

        # منتظر لودینگ
        await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=60)

        # بستن هر پاپ‌آپ خطایی
        await _close_any_popup(sana_page)
        await resilient_sleep(sana_page, 3, bot, user_id)

        # ── ۶. بررسی پاپ‌آپ تأیید بازیابی ───────────────────────────────
        recovery_ok = await _check_recovery_popup(sana_page, bot, user_id)
        if not recovery_ok:
            logging.warning("[EZHHAR_SIGN] پاپ‌آپ بازیابی تأیید نشد — ریلود")
            await sana_page.reload()
            await resilient_sleep(sana_page, 8, bot, user_id)
            await _close_any_popup(sana_page)
            await resilient_sleep(sana_page, 3, bot, user_id)

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

        # ── ۸. بررسی مجدد اگر جدول ظاهر نشد ────────────────────────────
        table_exists = await sana_page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="theBillPersonSignableList"]'
            ));
            return rows.length > 0;
        }''')

        if not table_exists:
            # ریلود و تلاش مجدد
            await sana_page.reload()
            await resilient_sleep(sana_page, 8, bot, user_id)
            await _close_any_popup(sana_page)
            await resilient_sleep(sana_page, 3, bot, user_id)

            # دوباره کلیک روی اخذ امضا
            clicked_sign2 = await sana_page.evaluate('''() => {
                const heads = Array.from(document.querySelectorAll('.box h5'));
                const t = heads.find(el => el.innerText && el.innerText.includes("اخذ امضا"));
                if (t) {
                    const box = t.closest('.box');
                    if (box) { box.click(); return true; }
                }
                return false;
            }''')
            if clicked_sign2:
                await resilient_sleep(sana_page, 6, bot, user_id)

        # ── ۹. یافتن اشخاص قابل امضا ───────────────────────────────────
        persons_info = await sana_page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll(
                'table tbody tr[ng-repeat*="theBillPersonSignableList"]'
            ));
            return rows.map((tr, idx) => {
                // نام شخص
                const nameTd = tr.querySelector(
                    'td.font-yekan.font-size-12.text-right.line-height-20.vertical-align-middle'
                );
                const name = nameTd ? nameTd.innerText.trim() : "";

                // نوع شخص (وکیل، نماینده، مدیرعامل، ...)
                const typeSpans = tr.querySelectorAll('span[ng-if*="PersonType"]');
                let personType = "";
                for (const sp of typeSpans) {
                    if (sp.getBoundingClientRect().width > 0) {
                        personType = sp.innerText.trim();
                    }
                }

                // آیا div ارسال کد نمایش دارد و دکمه فعال هست؟
                const sendDiv = tr.querySelector(
                    'div[ng-if*="!(item.NationalityCode"]'
                );
                const divVisible = sendDiv &&
                    window.getComputedStyle(sendDiv).display !== "none";
                const sendBtn = tr.querySelector(
                    'button[ng-click*="sendTempPassword"]'
                );
                const canSend = divVisible && sendBtn && !sendBtn.disabled;

                return { idx, name, personType, canSend, divVisible };
            });
        }''')

        logging.info(f"[EZHHAR_SIGN] persons_info: {persons_info}")

        sendable = [p for p in persons_info if p.get("divVisible")]

        if not sendable:
            await bot.send_message(
                user_id,
                "⚠️ **در جدول امضا اظهارنامه، شخصی برای ارسال کد موقت یافت نشد.**\n\n"
                "احتمالاً همه اشخاص قبلاً امضا کرده‌اند.\n"
                "لطفاً جهت ثبت امضا به شماره **09306186888** در واتساپ پیام دهید.",
                parse_mode="Markdown"
            )
            return {"success": False, "persons": [], "error": "no sendable persons"}

        # ── ۱۰. ارسال کد برای اشخاص هدف ─────────────────────────────────
        results = []
        rows_to_send = target_row_indices if target_row_indices else [p["idx"] for p in sendable]

        for target_idx in rows_to_send:
            person = next((p for p in sendable if p["idx"] == target_idx), None)
            if not person:
                continue

            name = person.get("name") or f"شخص {target_idx + 1}"
            success = await _send_temp_password_for_row(
                sana_page, target_idx, bot, user_id, name
            )

            results.append({
                "idx": target_idx,
                "name": name,
                "person_type": person.get("person_type", ""),
                "sent": success,
            })

            # فاصله ۳۰ ثانیه بین ارسال کد هر شخص
            if target_idx != rows_to_send[-1]:
                await resilient_sleep(sana_page, 30, bot, user_id)

        return {"success": True, "persons": results}

    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] send_ezhhar_sign_codes error: {e}")
        return {"success": False, "persons": [], "error": str(e)}


async def submit_ezhhar_sign_code(
    bot: Bot,
    user_id: int,
    tracking_code: str,
    row_idx: int,
    code: str,
) -> dict:
    """
    کد دریافت‌شده از کاربر را در سامانه وارد و امضا می‌کند.

    Returns:
        dict: { success: bool, error: str }
    """
    sana_page = runtime_state.sana_page
    if sana_page is None:
        return {"success": False, "error": "sana_page is None"}

    try:
        # ── ناوبری مجدد به صفحه اخذ امضا ─────────────────────────────
        ok = await goto_url_with_retry(
            sana_page, "https://sakha2.adliran.ir/Offices/Index", bot, user_id
        )
        if not ok:
            return {"success": False, "error": "خطا در بارگذاری صفحه"}

        await human_delay(3.0, 5.0)

        clicked = await sana_page.evaluate('''() => {
            const links = Array.from(document.querySelectorAll('a.list-group-item'));
            const t = links.find(el => el.innerText && el.innerText.includes("ارایه و پیگیری اظهارنامه"));
            if (t) { t.click(); return true; }
            return false;
        }''')
        if not clicked:
            await safe_click_by_text(sana_page, "ارایه و پیگیری اظهارنامه", bot, user_id)
        await resilient_sleep(sana_page, 5, bot, user_id)

        await sana_page.evaluate('''() => {
            const radio = document.querySelector('input[type="radio"][value="2"]');
            if (radio) radio.click();
        }''')
        await asyncio.sleep(1)

        await _fill_input(sana_page, "#txtPetitionNo", tracking_code)
        await resilient_sleep(sana_page, 1, bot, user_id)

        await sana_page.evaluate('''() => {
            const btn = document.querySelector('#btnGetJSSPetition');
            if (btn) { btn.click(); return; }
            const btns = Array.from(document.querySelectorAll('button'));
            const s = btns.find(b => b.innerText && b.innerText.includes("جستجو"));
            if (s) s.click();
        }''')

        await asyncio.sleep(3)
        await wait_for_horizontal_loading_bar(sana_page, bot, user_id, timeout=60)
        await _close_any_popup(sana_page)
        await resilient_sleep(sana_page, 3, bot, user_id)

        # بررسی پاپ‌آپ بازیابی
        recovery_ok = await _check_recovery_popup(sana_page, bot, user_id)
        if not recovery_ok:
            await _close_any_popup(sana_page)
            await resilient_sleep(sana_page, 3, bot, user_id)

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

        # ── وارد کردن کد و کلیک امضا ──────────────────────────────────
        success = await _enter_code_and_sign(sana_page, row_idx, code, bot, user_id)
        return {"success": success}

    except Exception as e:
        logging.error(f"[EZHHAR_SIGN] submit_ezhhar_sign_code error: {e}")
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# توابع کمکی داخلی
# ══════════════════════════════════════════════════════════════════════════════

async def _fill_input(page, selector: str, value: str):
    """پر کردن فیلد ورودی"""
    try:
        elem = page.locator(selector).first
        await elem.click()
        await elem.fill("")
        await elem.fill(value)
        await elem.blur()
    except Exception as e:
        logging.warning(f"[EZHHAR_SIGN] _fill_input({selector}) failed: {e}")


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


async def _check_recovery_popup(page, bot: Bot, user_id: int) -> bool:
    """
    بررسی پاپ‌آپ بازیابی اظهارنامه.
    اگر پیام «بازیابی اظهارنامه با موفقیت انجام گردید» بود → بستن و True.
    اگر پیام دیگری بود → ریلود پیشنهاد شده → False.
    """
    result = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return null;
        const h2 = popup.querySelector('h2');
        const text = h2 ? h2.innerText.trim() : "";
        const successIcon = popup.querySelector('.sa-icon.sa-success');
        const isSuccessVisible = successIcon &&
            window.getComputedStyle(successIcon).display !== "none";

        if (isSuccessVisible && text.includes("بازیابی")) {
            return "recovery_success";
        }
        if (isSuccessVisible) {
            return "success";
        }
        return text || "other";
    }''')

    if result == "recovery_success" or result == "success":
        await _close_any_popup(page)
        return True
    elif result and result != "other":
        # پیام غیرمنتظره — بستن
        await _close_any_popup(page)
        return False
    elif result == "other":
        # پاپ‌آپ بدون متن شناخته‌شده
        await _close_any_popup(page)
        return True  # ادامه می‌دهیم

    return True  # پاپ‌آپی نبود — OK


async def _send_temp_password_for_row(
    page, row_idx: int, bot: Bot, user_id: int, person_name: str
) -> bool:
    """
    ارسال کد موقت برای یک ردیف از جدول امضا.
    حداکثر ۳ بار تلاش می‌کند.
    """
    for attempt in range(3):
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
            logging.warning(f"[EZHHAR_SIGN] دکمه ارسال کد برای ردیف {row_idx} پیدا نشد (تلاش {attempt+1})")
            await asyncio.sleep(5)
            continue

        # انتظار برای پاپ‌آپ
        popup_result = await _wait_for_popup_result(page, timeout_sec=55)

        if popup_result == "success":
            await _close_any_popup(page)
            await bot.send_message(
                user_id,
                f"✅ **کد موقت امضا** برای **{person_name}** ارسال شد.\n"
                "⏰ توجه: مهلت استفاده از این کد **۷ دقیقه** می‌باشد.\n\n"
                "لطفاً کد دریافتی را هرچه سریع‌تر ارسال کنید."
            )
            logging.info(f"[EZHHAR_SIGN] کد موقت برای ردیف {row_idx} ({person_name}) ارسال شد.")
            return True

        elif popup_result == "already_sent":
            await _close_any_popup(page)
            await bot.send_message(
                user_id,
                f"✅ **کد موقت امضا** برای **{person_name}** قبلاً ارسال شده و هنوز معتبر است.\n"
                "لطفاً کد دریافتی را ارسال کنید."
            )
            logging.info(f"[EZHHAR_SIGN] کد قبلاً ارسال شده برای ردیف {row_idx}")
            return True

        else:
            await _close_any_popup(page)
            logging.warning(f"[EZHHAR_SIGN] خطا در ارسال کد ردیف {row_idx} (تلاش {attempt+1})")
            await asyncio.sleep(5)
            continue

    return False


async def _wait_for_popup_result(page, timeout_sec: int = 55) -> str:
    """
    منتظر پاپ‌آپ نتیجه ارسال کد.
    Returns: "success" | "already_sent" | "error" | "timeout"
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
    کد را در فیلد وارد می‌کند و دکمه «امضاء ثنا» را می‌زند.
    حداکثر ۳ بار تلاش می‌کند.
    """
    for attempt in range(3):
        # وارد کردن کد
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
            logging.warning(f"[EZHHAR_SIGN] وارد کردن کد در ردیف {row_idx} ناموفق (تلاش {attempt+1})")
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
            logging.warning(f"[EZHHAR_SIGN] دکمه امضاء ثنا در ردیف {row_idx} پیدا نشد (تلاش {attempt+1})")
            await asyncio.sleep(3)
            continue

        # انتظار برای نتیجه
        popup_result = await _wait_for_sign_popup(page, timeout_sec=55)

        if popup_result == "success":
            await _close_any_popup(page)
            logging.info(f"[EZHHAR_SIGN] امضای ردیف {row_idx} موفق.")
            return True
        elif popup_result == "wrong_code":
            await _close_any_popup(page)
            logging.info(f"[EZHHAR_SIGN] رمز موقت نادرست — ردیف {row_idx}")
            return False
        else:
            await _close_any_popup(page)
            logging.warning(f"[EZHHAR_SIGN] امضای ردیف {row_idx} ناموفق: {popup_result} (تلاش {attempt+1})")

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
    منتظر پاپ‌آپ نتیجه امضا.
    Returns: "success" | "wrong_code" | "error" | "timeout"
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

            if (isSuccessVisible) return "success";
            if (isErrorVisible) {
                if (text.includes("رمز موقت نادرست") || text.includes("نادرست")) {
                    return "wrong_code";
                }
                return "error";
            }
            return null;
        }''')
        if result:
            return result
        await asyncio.sleep(0.5)
    return "timeout"
