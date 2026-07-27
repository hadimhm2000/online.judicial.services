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

# ================= توابع شبه‌انسانی =================
async def human_delay(min_sec=1.5, max_sec=3.0):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def force_click_by_text(page, text):
    await page.evaluate(f'''() => {{
        const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div'];
        for (let tag of tags) {{
            const elements = Array.from(document.querySelectorAll(tag));
            const target = elements.find(el => el.innerText && el.innerText.trim() === "{text}");
            if (target) {{
                target.click();
                return;
            }}
        }}
        for (let tag of tags) {{
            const elements = Array.from(document.querySelectorAll(tag));
            const target = elements.find(el => el.innerText && el.innerText.trim().includes("{text}"));
            if (target) {{
                target.click();
                return;
            }}
        }}
    }}''')

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

async def handle_session_expired(bot: Bot, user_id: int):
    """مدیریت هوشمند انقضای نشست ثنا"""
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
        
    await bot.send_message(ADMIN_ID, "✅ **نشست با موفقیت تمدید شد.**")
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
        raise Exception("GetLegalPersonType redirect occurred. Navigated back and restarting task...")

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
        await handle_session_expired(bot, user_id)
        raise Exception("Session expired and was renewed. Restarting task from scratch...")
        
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
            await check_and_handle_expiry(page, bot, user_id)
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
            await check_and_handle_expiry(page, bot, user_id)

            btn_exists = await page.evaluate(''' (txt) => {
                const tags = ['button', 'a', 'label', 'span', 'li', 'h5', 'div'];
                for (let tag of tags) {
                    const elements = Array.from(document.querySelectorAll(tag));
                    const target = elements.find(el => el.innerText && el.innerText.trim().includes(txt));
                    if (target) return true;
                }
                return false;
            } ''', text)
            
            if not btn_exists:
                logging.warning(f"Option '{text}' not found. Going back one step...")
                await page.go_back()
                await asyncio.sleep(5)
                continue

            await force_click_by_text(page, text)
            await asyncio.sleep(2.5)
            
            await check_and_handle_expiry(page, bot, user_id)
            
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
            if "Session expired" in str(e):
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
            await check_and_handle_expiry(page, bot, user_id)

            elem_exists = await page.locator(selector).count() > 0
            if not elem_exists:
                logging.warning(f"Selector '{selector}' not found. Going back one step...")
                await page.go_back()
                await asyncio.sleep(5)
                continue

            success = await human_type(page, selector, text)
            if success:
                await check_and_handle_expiry(page, bot, user_id)
                    
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
            if "Session expired" in str(e):
                raise e
            logging.error(f"Error safe_typing in '{selector}' (Attempt {attempt+1}/{retry_count}): {e}")
            try:
                await page.go_back()
                await asyncio.sleep(5)
            except:
                pass
            await asyncio.sleep(2)
            
    raise Exception(f"Failed to type in '{selector}' after multiple retries.")
