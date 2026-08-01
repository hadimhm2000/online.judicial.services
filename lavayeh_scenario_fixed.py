# ============================================================
# lavayeh_scenario.py — نسخه اصلاح‌شده
# ============================================================
# تغییرات اعمال‌شده:
#   ۱. رفع باگ عدم کلیک دکمه استعلام ثنا بعد از وارد کردن کدملی
#   ۲. رفع باگ عدم کلیک دکمه «بستن» در پاپ‌آپ دوم آماده‌سازی
#   ۳. رفع باگ عدم کلیک «بازگشت به فهرست» بعد از آماده‌سازی
# ============================================================

""" سناریوی کامل ثبت لایحه در سامانه قضایی ثنا. """
import asyncio
import logging
import os
import base64
import html as html_lib

from aiogram import Bot
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import runtime_state
from config import ADMIN_ID
from sheets import log_event
from browser_helpers import (
    resilient_sleep,
    check_and_handle_expiry,
    soft_click_if_exists,
    goto_url_with_retry,
    human_delay,
    force_click_by_text,
    safe_click_by_text,
    safe_type,
    wait_for_angular_idle,
)


class LavayehFatalError(Exception):
    """خطای قطعی که retry را متوقف می‌کند."""
    pass


TITLE_SEARCH_MAP = {
    "لایحه دفاعیه": ("دفا", 0),
    "صدور اجرائیه": ("اجرائ", 0),
    "اعتراض به نظر کارشناس": ("کارشن", 1),
    "اعتراض به قرار رد دفتر": ("قرار", 1),
    "سایر عناوین": ("دفا", 0),
}

AGENT_TYPE_VALUES = {
    "مدیرعامل": "0091000010000008",
    "نماینده": "0091000010000007",
}


def _text_to_editor_html(text: str) -> str:
    """
    متن خام دریافتی از کاربر (تلگرام) را به HTML تبدیل می‌کند
    """
    if not text:
        return " "
    lines = text.split("\n")
    parts = []
    for line in lines:
        escaped = html_lib.escape(line, quote=False)
        if escaped.startswith(" "):
            leading = len(escaped) - len(escaped.lstrip(" "))
            escaped = ("&nbsp;" * leading) + escaped[leading:]
        escaped = escaped.replace("  ", "&nbsp; ")
        parts.append(f" {escaped} " if escaped else " ")
    return "".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# اصلاح ۱: تابع _click_sana_query_with_retry
# ═══════════════════════════════════════════════════════════════════════════

async def _click_sana_query_with_retry(
    page, ng_click_contains: str, bot: Bot, user_id: int,
    btn_id: str = None, max_retries: int = 5
):
    """
    کلیک روی دکمه استعلام ثنا بعد از وارد کردن کدملی.
    سه روش مختلف برای پیدا کردن و کلیک دکمه استفاده می‌شود.
    
    ساختار HTML دکمه:
    <div class="element-back blue pull-right ng-scope" ng-if="viewModel.needSanaVerification=='1'">
        <button class="btn btn-warning btn-sm" tooltip-placement="top" tooltip="استعلام ثنا" 
                ng-disabled="viewModel.loading || viewModel.currentDeclarantPerson.ExtractedFromSana==1" 
                ng-click="actions.callNationalityCode(viewModel.currentDeclarantPerson,false)">
            <i class="glyphicon glyphicon-refresh"></i>
        </button>
    </div>
    """
    for attempt in range(max_retries):
        clicked = False
        
        # ── روش ۱: کلیک با شناسه دکمه (اگر داده شده) یا ng-click ──
        by_id_js = (
            f'const byId = document.querySelector("#{btn_id}"); '
            f'if (byId && !byId.disabled) {{ byId.click(); return true; }}'
            if btn_id else ""
        )
        clicked = await page.evaluate(f"""() => {{
            {by_id_js}
            const btns = Array.from(
                document.querySelectorAll(
                    'button[ng-click*="{ng_click_contains}"]'
                )
            );
            const btn = btns.find(b => !b.disabled);
            if (btn) {{ btn.click(); return true; }}
            return false;
        }}""")

        # ── روش ۲: جستجوی دکمه استعلام ثنا در div.element-back ──
        if not clicked:
            clicked = await page.evaluate("""() => {
                // جستجوی دکمه استعلام ثنا در بلوک element-back
                const wrappers = document.querySelectorAll(
                    'div.element-back.blue'
                );
                for (const wrapper of wrappers) {
                    const btn = wrapper.querySelector(
                        'button.btn-warning'
                    );
                    if (btn && !btn.disabled) {
                        btn.click();
                        return true;
                    }
                }
                // fallback: جستجو در تمام دکمه‌های btn-warning با tooltip
                const btns = Array.from(
                    document.querySelectorAll('button.btn-warning')
                );
                const btn = btns.find(b => {
                    const tip = b.getAttribute("tooltip")
                             || b.getAttribute("title") || "";
                    return tip.includes("استعلام")
                        || tip.includes("ثنا");
                });
                if (btn && !btn.disabled) {
                    btn.click();
                    return true;
                }
                return false;
            }""")

        # ── روش ۳: کلیک مستقیم با Playwright locator ──
        if not clicked:
            try:
                # تلاش با tooltip
                sana_btn = page.locator(
                    'button.btn-warning[tooltip="استعلام ثنا"]'
                ).first
                if await sana_btn.count() > 0:
                    await sana_btn.click(timeout=5000)
                    clicked = True
                    logging.info(
                        "[LAVAYEH] دکمه استعلام ثنا با "
                        "Playwright locator کلیک شد"
                    )
            except Exception as e:
                logging.warning(
                    f"[LAVAYEH] کلیک Playwright locator ناموفق: {e}"
                )

        # ── روش ۴: کلیک با ng-click شامل callNationalityCode ──
        if not clicked:
            try:
                sana_btn = page.locator(
                    'button[ng-click*="callNationalityCode"]'
                ).first
                if await sana_btn.count() > 0:
                    is_disabled = await sana_btn.is_disabled()
                    if not is_disabled:
                        await sana_btn.click(timeout=5000)
                        clicked = True
                        logging.info(
                            "[LAVAYEH] دکمه استعلام با ng-click کلیک شد"
                        )
            except Exception as e:
                logging.warning(
                    f"[LAVAYEH] کلیک با ng-click ناموفق: {e}"
                )

        if clicked:
            logging.info(
                f"[LAVAYEH] دکمه استعلام ثنا کلیک شد "
                f"(تلاش {attempt + 1})"
            )

        await asyncio.sleep(10)

        closed = await _close_error_popup(page)
        if closed:
            await asyncio.sleep(5)
            continue

        # بررسی اینکه اطلاعات از ثنا استخراج شده
        extracted = await page.evaluate("""() => {
            // بررسی ExtractedFromSana==1 از طریق Angular scope
            try {
                const el = document.querySelector(
                    '[ng-click*="callNationalityCode"]'
                );
                if (el) {
                    const scope = angular.element(el).scope();
                    if (scope && scope.viewModel
                        && scope.viewModel.currentDeclarantPerson
                        && scope.viewModel.currentDeclarantPerson
                            .ExtractedFromSana == 1) {
                        return true;
                    }
                }
            } catch(e) {}
            // بررسی غیرفعال شدن فیلدها
            const disabled = document.querySelector(
                'input[ng-disabled*="ExtractedFromSana"][ng-disabled*="1"],' +
                'input[disabled]'
            );
            return disabled !== null;
        }""")
        if extracted:
            logging.info("[LAVAYEH] اطلاعات از ثنا استخراج شد")
            return

        await asyncio.sleep(3)

    logging.warning(
        f"[LAVAYEH] استعلام ثنا بعد از {max_retries} تلاش "
        f"ناموفق بود (user={user_id})"
    )


# ═══════════════════════════════════════════════════════════════════════════
# اصلاح ۲: تابع _click_preparation_with_retry
# ═══════════════════════════════════════════════════════════════════════════

async def _click_preparation_with_retry(
    page, bot: Bot, user_id: int, max_retries: int = 3
) -> bool:
    """
    کلیک روی دکمه آماده‌سازی و مدیریت دو پاپ‌آپ متوالی.
    
    پاپ‌آپ اول: موفقیت آماده‌سازی
    پاپ‌آپ دوم: دکمه «بستن» که باید کلیک شود
    
    ساختار دکمه بستن:
    <button class="confirm" tabindex="1" style="display: inline-block; 
            background-color: rgb(174, 222, 244); ...">بستن</button>
    """
    for attempt in range(max_retries):
        await page.evaluate("""() => {
            const btn = document.querySelector('#btnPreparation');
            if (btn && !btn.disabled) btn.click();
        }""")
        await asyncio.sleep(40 if attempt > 0 else 12)

        # ── بررسی پاپ‌آپ اول (موفقیت) ──
        success = await page.evaluate("""() => {
            const popup = document.querySelector(
                '.sweet-alert.showSweetAlert'
            );
            if (!popup) return false;
            const icon = popup.querySelector('.sa-icon.sa-success');
            const h2 = popup.querySelector('h2');
            return icon
                && window.getComputedStyle(icon).display !== 'none'
                && h2
                && h2.innerText.includes("آماده سازی");
        }""")
        
        if success:
            # بستن پاپ‌آپ اول
            await _close_success_popup(page)
            logging.info("[LAVAYEH] پاپ‌آپ اول آماده‌سازی بسته شد")
            await asyncio.sleep(3)

            # ── بررسی و بستن پاپ‌آپ دوم ──
            for wait in range(15):
                second_popup = await page.evaluate("""() => {
                    const popup = document.querySelector(
                        '.sweet-alert.showSweetAlert'
                    );
                    if (!popup) return false;
                    const btn = popup.querySelector(
                        'button.confirm'
                    );
                    return btn !== null;
                }""")
                if second_popup:
                    logging.info("[LAVAYEH] پاپ‌آپ دوم شناسایی شد")
                    break
                await asyncio.sleep(1)

            # کلیک دکمه «بستن» در پاپ‌آپ دوم
            closed_second = await page.evaluate("""() => {
                const popup = document.querySelector(
                    '.sweet-alert.showSweetAlert'
                );
                if (!popup) return false;
                const btn = popup.querySelector(
                    'button.confirm'
                );
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            }""")
            
            if closed_second:
                logging.info(
                    "[LAVAYEH] پاپ‌آپ دوم آماده‌سازی "
                    "(دکمه بستن) کلیک شد"
                )
            else:
                # fallback: جستجوی دکمه بستن با متن
                clicked_by_text = await page.evaluate("""() => {
                    const btns = Array.from(
                        document.querySelectorAll('button')
                    );
                    const btn = btns.find(
                        b => b.innerText
                          && b.innerText.trim() === 'بستن'
                    );
                    if (btn) {
                        btn.click();
                        return true;
                    }
                    return false;
                }""")
                if clicked_by_text:
                    logging.info(
                        "[LAVAYEH] دکمه بستن با جستجوی "
                        "متنی کلیک شد"
                    )
                else:
                    # fallback نهایی: Playwright locator
                    try:
                        close_btn = page.locator('button.confirm').first
                        if await close_btn.count() > 0:
                            await close_btn.click(timeout=5000)
                            logging.info(
                                "[LAVAYEH] دکمه بستن با Playwright کلیک شد"
                            )
                    except Exception as e:
                        logging.warning(f"[LAVAYEH] کلیک بستن ناموفق: {e}")

            await asyncio.sleep(3)
            return True

        closed = await _close_error_popup(page)
        if closed:
            await asyncio.sleep(30)
            await _close_success_popup(page)
            continue

        await asyncio.sleep(5)
    return False


# ═══════════════════════════════════════════════════════════════════════════
# اصلاح ۳: تابع _click_goto_main_after_preparation
# ═══════════════════════════════════════════════════════════════════════════

async def _click_goto_main_after_preparation(page, bot: Bot, user_id: int):
    """
    کلیک روی دکمه «بازگشت به فهرست» بعد از مرحله آماده‌سازی.
    
    ساختار دکمه:
    <div class="element-back blue ng-scope" ng-if="viewModel.directivesApiStep['navigation_main'].getCurrentStep().level>0">
        <button class="btn btn-default btn-block font-size-12 font-yekan" 
                id="gotoMainPage" name="gotoMainPage" 
                ng-disabled="viewModel.loading" 
                ng-click="actions.gotoMainStep()">
            <i class="glyphicon glyphicon-share-alt"></i>
            بازگشت به فهرست
        </button>
    </div>
    """
    # ابتدا منتظر می‌مانیم تا دکمه در DOM ظاهر شود
    await asyncio.sleep(3)
    
    # ── روش ۱: کلیک با ID ──
    goto_main_clicked = await page.evaluate("""() => {
        const btn = document.querySelector('#gotoMainPage');
        if (btn && !btn.disabled) {
            btn.click();
            return true;
        }
        return false;
    }""")
    
    if goto_main_clicked:
        logging.info(
            "[LAVAYEH] بازگشت به فهرست با #gotoMainPage کلیک شد"
        )
        return True
    
    # ── روش ۲: جستجو در div.element-back.blue ──
    goto_main_clicked = await page.evaluate("""() => {
        const wrapper = document.querySelector('div.element-back.blue');
        if (wrapper) {
            const btn = wrapper.querySelector('#gotoMainPage');
            if (btn && !btn.disabled) {
                btn.click();
                return true;
            }
        }
        return false;
    }""")
    
    if goto_main_clicked:
        logging.info(
            "[LAVAYEH] بازگشت به فهرست در element-back کلیک شد"
        )
        return True
    
    # ── روش ۳: جستجو با ng-click ──
    goto_main_clicked = await page.evaluate("""() => {
        const btn = document.querySelector(
            'button[ng-click*="gotoMainStep"]'
        );
        if (btn && !btn.disabled) {
            btn.click();
            return true;
        }
        return false;
    }""")
    
    if goto_main_clicked:
        logging.info(
            "[LAVAYEH] بازگشت به فهرست با ng-click کلیک شد"
        )
        return True
    
    # ── روش ۴: جستجوی متنی ──
    goto_main_clicked = await page.evaluate("""() => {
        const btns = Array.from(
            document.querySelectorAll('button')
        );
        const fallback = btns.find(
            b => b.innerText
              && b.innerText.includes('بازگشت به فهرست')
        );
        if (fallback && !fallback.disabled) {
            fallback.click();
            return true;
        }
        return false;
    }""")
    
    if goto_main_clicked:
        logging.info(
            "[LAVAYEH] بازگشت به فهرست با جستجوی متنی کلیک شد"
        )
        return True
    
    # ── روش ۵: Playwright locator ──
    try:
        btn = page.locator('#gotoMainPage').first
        if await btn.count() > 0:
            is_disabled = await btn.is_disabled()
            if not is_disabled:
                await btn.click(timeout=5000)
                logging.info(
                    "[LAVAYEH] بازگشت به فهرست با Playwright کلیک شد"
                )
                return True
    except Exception as e:
        logging.warning(f"[LAVAYEH] Playwright locator ناموفق: {e}")
    
    # ── روش ۶: soft_click_if_exists ──
    await soft_click_if_exists(page, "بازگشت به فهرست")
    logging.warning(
        "[LAVAYEH] بازگشت به فهرست با soft_click_if_exists انجام شد"
    )
    return False


# ═══════════════════════════════════════════════════════════════════════════
# بخش اصلاح‌شده در process_lavayeh_task
# ═══════════════════════════════════════════════════════════════════════════
# 
# در تابع process_lavayeh_task، بعد از فراخوانی 
# _click_preparation_with_retry، کد زیر را جایگزین کنید:
#
# --- کد قدیمی ---
#         await _click_goto_main(sana_page, bot, user_id)
#         await resilient_sleep(sana_page, 4, bot, user_id)
#
# --- کد جدید ---
#         # ── کلیک «بازگشت به فهرست» بعد از آماده‌سازی ──
#         await _click_goto_main_after_preparation(sana_page, bot, user_id)
#         await resilient_sleep(sana_page, 4, bot, user_id)
#


# ═══════════════════════════════════════════════════════════════════════════
# توابع کمکی (بدون تغییر - برای مرجع)
# ═══════════════════════════════════════════════════════════════════════════

async def _close_error_popup(page) -> bool:
    """بستن پاپ‌آپ خطا"""
    closed = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;
        const successIcon = popup.querySelector('.sa-icon.sa-success');
        if (successIcon && window.getComputedStyle(successIcon).display !== 'none') 
            return false;
        const btn = popup.querySelector('button.confirm');
        if (btn) {
            btn.click();
            return true;
        }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


async def _close_success_popup(page) -> bool:
    """بستن پاپ‌آپ موفقیت"""
    closed = await page.evaluate('''() => {
        const popup = document.querySelector('.sweet-alert.showSweetAlert');
        if (!popup) return false;
        const btn = popup.querySelector('button.confirm');
        if (btn) {
            btn.click();
            return true;
        }
        return false;
    }''')
    if closed:
        await asyncio.sleep(1)
    return closed


async def _click_goto_main(page, bot: Bot, user_id: int):
    """کلیک روی دکمه بازگشت به فهرست (نسخه قدیمی)"""
    clicked = await page.evaluate('''() => {
        const btn = document.querySelector('#gotoMainPage');
        if (btn && !btn.disabled) {
            btn.click();
            return true;
        }
        return false;
    }''')
    if not clicked:
        await soft_click_if_exists(page, "بازگشت به فهرست")


# ═══════════════════════════════════════════════════════════════════════════
# راهنمای استفاده
# ═══════════════════════════════════════════════════════════════════════════
#
# ۱. تابع _click_sana_query_with_retry را با نسخه بالا جایگزین کنید
#
# ۲. تابع _click_preparation_with_retry را با نسخه بالا جایگزین کنید
#
# ۳. تابع جدید _click_goto_main_after_preparation را اضافه کنید
#
# ۴. در تابع process_lavayeh_task، بعد از preparation_ok:
#    به جای:
#        await _click_goto_main(sana_page, bot, user_id)
#    
#    بنویسید:
#        await _click_goto_main_after_preparation(sana_page, bot, user_id)
#
# ═══════════════════════════════════════════════════════════════════════════
