
```python
"""
توابع کمکی مرورگر: کلیک/تایپ ایمن، تشخیص و مدیریت انقضای نشست و باگ GetLegalPersonType،
خواب هوشمند، لود ایمن صفحه.
"""
import asyncio
import logging
import random

from aiogram import Bot
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import runtime_state
from config import ADMIN_ID
from keyboards import admin_login_kb


class NavigationResetError(Exception):
    """
    خطایی که وقتی رخ می‌ده که یک انحراف/گم‌شدگی در صفحه (مثل باگ GetLegalPersonType
    یا پیدا نشدن یک عنصر حتی بعد از صبر کافی) تشخیص داده شده و صفحه از قبل به یک
    نقطه‌ی امن (Offices/Index) navigate شده. گرفتن این خطا نباید دوباره go_back یا
    هر ناوبری دیگه‌ای انجام بده — فقط باید مستقیم به بالا raise بشه تا حلقه‌ی
    بیرونی سناریو، کل تسک رو از نو (از همون نقطه‌ی امن) شروع کنه.
    """
    pass


# ================= توابع شبه‌انسانی =================
async def human_delay(min_sec=1.5, max_sec=3.0):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def force_click_by_text(page, text):
    # اصلاحیه امنیتی: استفاده از آرگومان به جای f-string برای جلوگیری از JS Injection
    await page.evaluate('''(txt) => {
        const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div'];
        for (let tag of tags) {
            const elements = Array.from(document.querySelectorAll(tag));
            const target = elements.find(el => el.innerText && el.innerText.trim() === txt);
            if (target) {
                target.click();
                return;
            }
        }
        for (let tag of tags) {
            const elements = Array.from(document.querySelectorAll(tag));
            const target = elements.find(el => el.innerText && el.innerText.trim().includes(txt));
            if (target) {
                target.click();
                return;
            }
        }
    }''', text)

async def soft_click_if_exists(page, text):
    """کلیک اختیاری — فقط اگر عنصر موجود باشد"""
    exists = await page.evaluate('''(txt) => {
        const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div'];
        for (let tag of tags) {
            const elements = Array.from(document.querySelectorAll(tag));
            const target = elements.find(el => el.innerText && el.innerText.trim().includes(txt));
            if (target) {
                const rect = target.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) return true;
            }
        }
        return false;
    }''', text)
    if exists:
        await force_click_by_text(page, text)
        await asyncio.sleep(1.5)
        logging.info(f"soft_click_if_exists: clicked '{text}'.")
    else:
        logging.info(f"soft_click_if_exists: '{text}' not present — skipping.")

async def human_type(page, locator_string, text):
    try:
        input_elem = page.locator(locator_string).first
        await input_elem.hover()
        await human_delay(0.5, 1.0)
        await input_elem.click()
        await input_elem.fill("")
        for char in text:
            await input_elem.type(char, delay=random.randint(100, 300))
        await human_delay(0.5, 1.0)
        await input_elem.blur()
        return True
    except Exception as e:
        logging.warning(f"human_type failed for selector '{locator_string}': {e}")
        return False

# ================= توابع ایمن و ضد اختلال =================

async def dismiss_expiry_popup(page) -> bool:
    """
    بعد از این‌که مدیر مجدداً لاگین کرد، این تابع روی صفحه‌ی اصلی (همان تبی که
    پاپ‌آپ خطای انقضا رویش باز شده) دکمه‌ی «بستن» را پیدا کرده و می‌زند تا
    صفحه برای ادامه‌ی همان مرحله (بدون ری‌لود یا ریست) آماده شود.
    اگر پاپ‌آپی پیدا نشود (مثلاً خودش قبلاً بسته شده) به‌آرامی ادامه می‌دهد.
    """
    try:
        closed = await page.evaluate('''() => {
            let btn = document.querySelector('.sweet-alert.showSweetAlert button.confirm, button.confirm');
            if (btn) {
                const rect = btn.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) { btn.click(); return true; }
            }
            const tags = ['button', 'a', 'span', 'div'];
            for (const tag of tags) {
                const elements = Array.from(document.querySelectorAll(tag));
                const target = elements.find(el => el.innerText && el.innerText.trim() === "بستن");
                if (target) {
                    const rect = target.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) { target.click(); return true; }
                }
            }
            return false;
        }''')
    except Exception as e:
        logging.warning(f"dismiss_expiry_popup: error while closing popup: {e}")
        return False

    if closed:
        logging.info("dismiss_expiry_popup: 'بستن' دکمه‌ی پاپ‌آپ انقضا زده شد.")
        await asyncio.sleep(1.5)
    else:
        logging.info("dismiss_expiry_popup: پاپ‌آپی برای بستن پیدا نشد (احتمالاً از قبل بسته بوده).")
    return closed


async def handle_session_expired(bot: Bot, user_id: int, page=None):
    """
    مدیریت هوشمند انقضای نشست ثنا:
      ۱) به مدیر اطلاع می‌دهد و یک تب جدید برای لاگین مجدد باز می‌کند
      ۲) منتظر می‌ماند تا مدیر دکمه‌ی تایید لاگین را در ربات بزند.
      ۳) تب لاگین را می‌بندد.
      ۴) روی همان صفحه‌ی اصلی (page)، دکمه‌ی «بستن» پاپ‌آپ خطا را می‌زند.
    """
    await bot.send_message(ADMIN_ID, "⚠️ **اعتبار نشست سامانه (ثنا) به اتمام رسیده است.**\nدر حال باز کردن تب جدید...")

    login_page = await runtime_state.browser_context.new_page()
    try:
        await login_page.goto("https://sakha2.adliran.ir/Offices/Index", timeout=60000)
        runtime_state.login_event.clear()

        await bot.send_message(ADMIN_ID, "🔑 **لاگین مجدد ثنا:**\nپنجره ورود جدید باز شده است. لطفا لاگین کنید و دکمه زیر را بفشارید 👇", reply_markup=admin_login_kb)
        await runtime_state.login_event.wait()
    except Exception as e:
        logging.error(f"Error in handle_session_expired page navigation: {e}")
    finally:
        await login_page.close()

    if page is not None:
        try:
            await dismiss_expiry_popup(page)
        except Exception as e:
            logging.warning(f"handle_session_expired: could not dismiss popup on main page: {e}")

    await bot.send_message(ADMIN_ID, "✅ **نشست با موفقیت تمدید شد.** ادامه‌ی فرآیند از همان مرحله...")
    await asyncio.sleep(2)

async def wait_for_angular_idle(page):
    """منتظر ماندن برای پایداری انگولار"""
    try:
        await page.evaluate('''() => {
            return new Promise((resolve) => {
                let attempts = 0;
                const check = () => {
                    attempts++;
                    if (attempts > 50) { resolve(); return; }
                    if (typeof angular !== 'undefined') {
                        const body = document.body || document.querySelector('[ng-app]');
                        if (body) {
                            try {
                                const injector = angular.element(body).injector();
                                if (injector) {
                                    const $http = injector.get('$http');
                                    if ($http && $http.pendingRequests && $http.pendingRequests.length > 0) {
                                        setTimeout(check, 100);
                                        return;
                                    }
                                }
                            } catch (e) { setTimeout(check, 100); return; }
                        }
                    }
                    resolve();
                };
                check();
            });
        }''')
    except Exception as e:
        logging.warning(f"Error waiting for angular idle: {e}")

async def check_and_handle_expiry(page, bot: Bot, user_id: int):
    """بررسی انقضای نشست"""
    if "GetLegalPersonType" in page.url:
        logging.warning("⚠️ انحراف به GetLegalPersonType شناسایی شد!")
        try:
            await page.goto("https://sakha2.adliran.ir/Offices/Index")
            await asyncio.sleep(4)
        except:
            pass
        raise NavigationResetError("GetLegalPersonType redirect occurred. Navigated to Offices/Index and restarting task...")

    is_expired = await page.evaluate('''() => {
        const text = document.body ? document.body.innerText : "";
        const hasExpiryText = text.includes("منقضی") || text.includes("منقضي") || 
                              text.includes("رایانه ای دیگر") || text.includes("رایانه ای ديگر") || 
                              text.includes("ورود قبلی") || text.includes("ورود قبلي") ||
                              text.includes("خطای دسترسی کاربر") || text.includes("نشست شما") || 
                              text.includes("اعتبار ورود");
        const isLoginPage = document.querySelector('#txtUsername, #txtPassword, input[name="txtUsername"], input[placeholder*="کد ملی"]') !== null;
        return hasExpiryText || isLoginPage;
    }''')
    
    if is_expired:
        logging.warning("⚠️ انقضای نشست شناسایی شد — شروع فرآیند لاگین مجدد مدیر...")
        await handle_session_expired(bot, user_id, page=page)
        return True

    return False

async def check_and_handle_load_error(page):
    """بررسی خطاهای لود صفحه"""
    has_load_error = await page.evaluate('''() => {
        const text = document.body ? document.body.innerText : "";
        const isErr = text.includes("تاخیر در اجرای سرویس") || text.includes("سرویس با خطا") || text.includes("خطا در فراخوانی");
        const closeBtn = document.querySelector('.sweet-alert.showSweetAlert button.confirm, button.confirm');
        if (isErr && closeBtn) {
            const rect = closeBtn.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(closeBtn).display !== 'none') {
                closeBtn.click();
                return true;
            }
        }
        return false;
    }''')
    
    if has_load_error:
        logging.warning("Initial load error detected. Closing modal and reloading page...")
        await asyncio.sleep(3)
        await page.reload()
        await asyncio.sleep(5)
        return True
    return False

async def resilient_sleep(page, seconds, bot: Bot, user_id: int):
    """خواب هوشمند با چک انقضا"""
    for _ in range(int(seconds)):
        had_expiry = await check_and_handle_expiry(page, bot, user_id)
        if had_expiry:
            logging.info("Session expiry intercepted during sleep.")
            return True
        await asyncio.sleep(1)
    return False

async def goto_url_with_retry(page, url, bot: Bot, user_id: int, timeout=30000):
    """لود ایمن صفحه با retry"""
    for load_attempt in range(3):
        try:
            await page.goto(url, timeout=timeout)
            await page.wait_for_load_state("load", timeout=timeout)
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                await page.goto(url, timeout=timeout)
                await page.wait_for_load_state("load", timeout=timeout)
            had_error = await check_and_handle_load_error(page)
            if had_error:
                continue
            return True
        except PlaywrightTimeoutError:
            logging.warning(f"Timeout loading page {url} (Attempt {load_attempt+1}/3)")
            await asyncio.sleep(3)
        except Exception as e:
            logging.error(f"Error loading page {url} (Attempt {load_attempt+1}/3): {e}")
            await asyncio.sleep(3)
            
    await bot.send_message(user_id, "⚠️ متاسفانه ارتباط با سامانه قضایی در حال حاضر با اختلال مواجه است.")
    return False

async def safe_click_by_text(page, text, bot: Bot, user_id: int, retry_count=3):
    """کلیک ایمن روی دکمه‌ها"""
    for attempt in range(retry_count):
        try:
            for _ in range(60):
                is_loading = await page.evaluate('''() => {
                    const loaders = document.querySelectorAll('.blockUI, .blockOverlay, .loading-mask, .ajax-loader, .spinner, .loading, #loading');
                    for (let loader of loaders) {
                        const rect = loader.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(loader).display !== "none") {
                            return true;
                        }
                    }
                    return false;
                }''')
                if not is_loading:
                    break
                await asyncio.sleep(0.5)

            await wait_for_angular_idle(page)
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                logging.info(f"safe_click_by_text: session renewed mid-step for '{text}', retrying this step.")
                continue

            btn_exists = False
            for _grace in range(6):
                btn_exists = await page.evaluate(''' (txt) => {
                    const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div'];
                    for (let tag of tags) {
                        const elements = Array.from(document.querySelectorAll(tag));
                        const target = elements.find(el => el.innerText && el.innerText.trim().includes(txt));
                        if (target) return true;
                    }
                    return false;
                } ''', text)
                if btn_exists:
                    break
                await asyncio.sleep(1)

            if not btn_exists:
                logging.warning(
                    f"Option '{text}' not found even after grace period. "
                    f"go_back() is unreliable on this site (lands on stale/unrelated "
                    f"history entries like GetLegalPersonType) — resetting to Offices/Index instead."
                )
                try:
                    await page.goto("https://sakha2.adliran.ir/Offices/Index")
                    await asyncio.sleep(4)
                except Exception:
                    pass
                raise NavigationResetError(
                    f"'{text}' not found on page. Navigated to Offices/Index and restarting task..."
                )

            await force_click_by_text(page, text)
            await asyncio.sleep(2.5)
            
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                logging.info(f"safe_click_by_text: session renewed right after clicking '{text}', retrying this step.")
                continue
            
            error_details = await page.evaluate('''() => {
                const closeBtn = document.querySelector('.sweet-alert.showSweetAlert button.confirm, button.confirm');
                if (closeBtn) {
                    const rect = closeBtn.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(closeBtn).display !== 'none') {
                        closeBtn.click();
                        return { found: true };
                    }
                }
                const hasAlert = document.querySelector('.sweet-alert.showSweetAlert, .alert-danger, .error') !== null;
                return { found: false, hasAlert: hasAlert };
            }''')
            
            if error_details['found']:
                logging.warning(f"Error dialog detected on clicking '{text}'. Retrying...")
                await asyncio.sleep(3)
                continue
                
            if error_details['hasAlert']:
                logging.warning("Error alert visible. Going back one page...")
                await page.go_back()
                await asyncio.sleep(5)
                continue
            
            return True
            
        except Exception as e:
            if isinstance(e, NavigationResetError) or "Session expired" in str(e):
                raise e
            logging.error(f"Error in safe_click_by_text '{text}' (Attempt {attempt+1}/{retry_count}): {e}")
            try:
                await page.go_back()
                await asyncio.sleep(5)
            except:
                pass
            await asyncio.sleep(2)
            
    raise Exception(f"Failed to click '{text}' after multiple retries.")

async def safe_type(page, selector, text, bot: Bot, user_id: int, retry_count=3):
    """تایپ ایمن اطلاعات داخل اینپوت‌ها"""
    for attempt in range(retry_count):
        try:
            for _ in range(60):
                is_loading = await page.evaluate('''() => {
                    const loaders = document.querySelectorAll('.blockUI, .blockOverlay, .loading-mask, .ajax-loader, .spinner, .loading, #loading');
                    for (let loader of loaders) {
                        const rect = loader.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(loader).display !== "none") {
                            return true;
                        }
                    }
                    return false;
                }''')
                if not is_loading:
                    break
                await asyncio.sleep(0.5)

            await wait_for_angular_idle(page)
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                logging.info(f"safe_type: session renewed mid-step for '{selector}', retrying this step.")
                continue

            elem_exists = False
            for _grace in range(6):
                elem_exists = await page.locator(selector).count() > 0
                if elem_exists:
                    break
                await asyncio.sleep(1)

            if not elem_exists:
                logging.warning(
                    f"Selector '{selector}' not found even after grace period. "
                    f"go_back() is unreliable on this site — resetting to Offices/Index instead."
                )
                try:
                    await page.goto("https://sakha2.adliran.ir/Offices/Index")
                    await asyncio.sleep(4)
                except Exception:
                    pass
                raise NavigationResetError(
                    f"Selector '{selector}' not found. Navigated to Offices/Index and restarting task..."
                )

            success = await human_type(page, selector, text)
            if success:
                had_expiry = await check_and_handle_expiry(page, bot, user_id)
                if had_expiry:
                    logging.info(f"safe_type: session renewed right after typing into '{selector}', retrying this step.")
                    continue

                error_details = await page.evaluate('''() => {
                    const closeBtn = document.querySelector('.sweet-alert.showSweetAlert button.confirm, button.confirm');
                    if (closeBtn) {
                        const rect = closeBtn.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(closeBtn).display !== 'none') {
                            closeBtn.click();
                            return { found: true };
                        }
                    }
                    const hasAlert = document.querySelector('.sweet-alert.showSweetAlert, .alert-danger, .error') !== null;
                    return { found: false, hasAlert: hasAlert };
                }''')
                
                if error_details['found']:
                    await asyncio.sleep(3)
                    continue
                    
                if error_details['hasAlert']:
                    await page.go_back()
                    await asyncio.sleep(5)
                    continue
                    
                return True
            await asyncio.sleep(2)
        except Exception as e:
            if isinstance(e, NavigationResetError) or "Session expired" in str(e):
                raise e
            logging.error(f"Error safe_typing in '{selector}' (Attempt {attempt+1}/{retry_count}): {e}")
            try:
                await page.go_back()
                await asyncio.sleep(5)
            except:
                pass
            await asyncio.sleep(2)
            
    raise Exception(f"Failed to type in '{selector}' after multiple retries.")
```
 