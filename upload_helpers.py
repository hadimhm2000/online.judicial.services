'''
لایه یکپارچه آپلود منضمات — مقاوم در برابر خطا با قابلیت بازیابی
Unified resilient upload layer for judicial system attachments.

هر ۳ سناریو (لایحه، اظهارنامه، اعلام وکالت) از این ماژول استفاده می‌کنند.

ویژگی‌ها:
  - اعتبارسنجی و فشرده‌سازی پیش‌آپلود
  - شناسایی هوشمند نوع خطا از popup سامانه
  - حذف کامل ردیف پیوست (فایل‌ها دانه‌به‌دانه + خود ردیف)
  - تلاش مجدد هوشمند با رفع خودکار مشکل
  - ذخیره/بازیابی نقاط بازیابی (Checkpoint/Resume)
'''

import os
import time
import asyncio
import logging
from typing import Optional, Callable, Tuple, List, Dict, Any

from aiogram import Bot

from browser_helpers import (
    resilient_sleep, check_and_handle_expiry, wait_for_angular_idle,
    soft_click_if_exists,
)

# =========================================================
# تنظیمات
# =========================================================
MAX_IMAGE_BYTES = 450 * 1024       # 450 KB
UPLOAD_CONFIRM_TIMEOUT = 120       # ثانیه
MAX_UPLOAD_ATTEMPTS = 3            # تلاش هر ردیف
MAX_SAVE_DOC_RETRIES = 3          # تلاش ذخیره سند
MAX_APPLY_ALL_RETRIES = 3         # تلاش اعمال همه
CHECKPOINT_EXPIRY_HOURS = 24


def _log(prefix, msg, level='info'):
    """لاگ ساده با پیشوند."""
    fn = getattr(logging, level, logging.info)
    fn(f"[{prefix}] {msg}")


def _title_log(prefix, action, title):
    """لاگ با عنوان — از guillemets استفاده نمی‌کند."""
    return f"{action} [{title}]"


# =========================================================
# ۱. اعتبارسنجی و آماده‌سازی فایل
# =========================================================

def _compress_image(path: str, max_bytes: int = MAX_IMAGE_BYTES) -> str:
    try:
        if os.path.getsize(path) <= max_bytes:
            return path
    except OSError:
        return path

    try:
        from PIL import Image
    except ImportError:
        logging.warning(f"[UPLOAD] Pillow نصب نیست؛ فشرده‌سازی '{path}' انجام نشد.")
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

        if out_path != path and os.path.exists(out_path):
            try:
                os.remove(path)
            except OSError:
                pass
            return out_path
        return path
    except Exception as e:
        logging.error(f"[UPLOAD] خطا در فشرده‌سازی '{path}': {e}")
        return path


def _convert_to_jpeg_if_needed(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        return path

    try:
        from PIL import Image
    except ImportError:
        return path

    try:
        img = Image.open(path).convert("RGB")
        out_path = os.path.splitext(path)[0] + ".jpg"
        img.save(out_path, "JPEG", quality=92, optimize=True)
        try:
            os.remove(path)
        except OSError:
            pass
        logging.info(f"[UPLOAD] تبدیل '{ext}' به JPEG: '{out_path}'")
        return out_path
    except Exception as e:
        logging.error(f"[UPLOAD] خطا در تبدیل '{path}' به JPEG: {e}")
        return path


def _validate_file(path: str) -> Tuple[bool, str]:
    if not os.path.exists(path):
        return False, f"فایل وجود ندارد: {path}"
    try:
        size = os.path.getsize(path)
        if size == 0:
            return False, f"فایل خالی است: {path}"
        if size > 5 * 1024 * 1024:
            return False, f"حجم فایل بیش از ۵ مگابایت: {path} ({size/1024/1024:.1f} MB)"
    except OSError as e:
        return False, f"خطا در خواندن فایل: {e}"
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
    except ImportError:
        pass
    except Exception as e:
        return False, f"فایل آسیب‌دیده (corrupt): {path} - {e}"
    return True, ""


async def prepare_files_for_upload(
    image_paths: List[str],
    bot: Bot = None,
    user_id: int = None,
    prefix: str = "UPLOAD",
    compress: bool = True,
    convert_to_jpeg: bool = True,
) -> Tuple[List[str], List[Dict[str, str]]]:
    """
    آماده‌سازی فایل‌ها: اعتبارسنجی، تبدیل به JPEG، فشرده‌سازی.
    بازگشت: (prepared_paths, errors)
    """
    prepared = []
    errors = []

    for i, path in enumerate(image_paths):
        valid, err = _validate_file(path)
        if not valid:
            errors.append({"path": path, "error": err, "index": i})
            _log(prefix, f"فایل نامعتبر #{i}: {err}", 'error')
            continue

        current_path = path
        if convert_to_jpeg:
            current_path = _convert_to_jpeg_if_needed(current_path)
        if compress:
            current_path = _compress_image(current_path)

        try:
            final_size = os.path.getsize(current_path)
            if final_size > MAX_IMAGE_BYTES * 2:
                _log(prefix, f"فایل #{i} بعد از فشرده‌سازی بزرگ: {final_size/1024:.0f} KB", 'warning')
        except OSError:
            pass

        prepared.append(current_path)

    if errors and bot and user_id:
        error_summary = "\n".join(f"  - {e['error']}" for e in errors)
        _log(prefix, f"{len(errors)} فایل نامعتبر:\n{error_summary}", 'warning')

    return prepared, errors


# =========================================================
# ۲. شناسایی هوشمند خطا
# =========================================================

async def get_and_close_error_popup_text(page) -> Optional[str]:
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
        return msg || null;
    }''')
    if text:
        await asyncio.sleep(1)
    return text


async def close_error_popup(page) -> bool:
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


async def close_success_popup(page) -> bool:
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


async def close_any_popup(page) -> bool:
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


def detect_error_type(error_text: str) -> str:
    if not error_text:
        return "unknown"
    text = error_text.strip()
    if any(kw in text for kw in ["تعداد صفحات", "صفحات اشتباه", "صفحه اشتباه", "تعداد صفحه"]):
        return "page_count"
    if any(kw in text for kw in ["حجم فایل", "حجم بیش", "حجم مجاز", "سایز فایل", "اندازه فایل"]):
        return "file_size"
    if any(kw in text for kw in ["نوع فایل", "فرمت فایل", "پسوند فایل"]):
        return "file_type"
    if any(kw in text for kw in [
        "انقض", "نشست", "session", "ورود", "لاگین",
        "از ساعت ورود شما می‌گذرد",
        "اصل اولویت", "احراز هویت", "تمدید",
    ]):
        return "session"
    if any(kw in text for kw in ["تکراری", "قبلا", "موجود"]):
        return "duplicate"
    if any(kw in text for kw in ["خطا", "مشکل", "امکان", "سرور"]):
        return "general"
    return "unknown"


# =========================================================
# ۳. حذف کامل ردیف پیوست
# =========================================================

async def delete_all_files_in_row(page, bot: Bot = None, user_id: int = None, prefix: str = "UPLOAD") -> int:
    """
    حذف دانه‌به‌دانه تمام فایل‌های آپلودشده در ردیف فعلی.
    از دکمه btnDelete3 و removeAttachment استفاده می‌کند.
    بازگشت: تعداد فایل‌های حذفشده
    """
    deleted_count = 0
    max_deletes = 50

    while deleted_count < max_deletes:
        if bot and user_id:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                _log(prefix, "نشست حین حذف فایل‌های ردیف تمدید شد.")
                await asyncio.sleep(2)

        deleted = await page.evaluate('''() => {
            const btn3 = document.querySelector('button#btnDelete3:not([disabled])');
            if (btn3) { btn3.click(); return 'btnDelete3'; }
            const btnAttach = document.querySelector('button[ng-click*="removeAttachment"]:not([disabled])');
            if (btnAttach) { btnAttach.click(); return 'removeAttachment'; }
            return null;
        }''')

        if not deleted:
            break

        deleted_count += 1
        _log(prefix, f"فایل #{deleted_count} حذف شد ({deleted})")
        await asyncio.sleep(2)

    _log(prefix, f"مجموعاً {deleted_count} فایل از ردیف حذف شد")
    return deleted_count


async def delete_document_row_by_title(page, title: str, prefix: str = "UPLOAD") -> bool:
    """
    حذف یک ردیف پیوست از فهرست (سطل زباله removeDocument).
    ردیف را بر اساس عنوان پیدا می‌کند.
    """
    escaped = title.replace("`", "'").replace("\\", "").replace('"', '\\"')

    result = await page.evaluate(f'''() => {{
        const rows = Array.from(document.querySelectorAll('table tbody tr, .table tbody tr'));
        let targetRow = null;
        for (const row of rows) {{
            const cells = row.querySelectorAll('td');
            for (const cell of cells) {{
                if (cell.innerText && cell.innerText.includes("{escaped}")) {{
                    targetRow = row;
                    break;
                }}
            }}
            if (targetRow) break;
        }}
        if (targetRow) {{
            let trashBtn = targetRow.querySelector('button[ng-click*="removeDocument"]');
            if (!trashBtn) {{
                const nextRow = targetRow.nextElementSibling;
                if (nextRow) trashBtn = nextRow.querySelector('button[ng-click*="removeDocument"]');
            }}
            if (trashBtn && !trashBtn.disabled) {{
                trashBtn.click();
                return 'found_and_clicked';
            }}
            return 'btn_disabled';
        }}
        // ردیف پیدا نشد - تلاش با آخرین removeDocument
        const allTrash = Array.from(document.querySelectorAll('button[ng-click*="removeDocument"]'));
        if (allTrash.length > 0) {{
            allTrash[allTrash.length - 1].click();
            return 'last_row_clicked';
        }}
        return 'not_found';
    }}''')

    if result == 'found_and_clicked':
        _log(prefix, f"ردیف [{title}] حذف شد (removeDocument)")
        await asyncio.sleep(2)
        await close_any_popup(page)
        await asyncio.sleep(1)
        return True
    elif result == 'last_row_clicked':
        _log(prefix, "آخرین ردیف پیوست حذف شد")
        await asyncio.sleep(2)
        await close_any_popup(page)
        await asyncio.sleep(1)
        return True
    elif result == 'btn_disabled':
        _log(prefix, f"دکمه removeDocument برای [{title}] غیرفعال است", 'warning')
        return False
    else:
        _log(prefix, f"ردیف [{title}] برای حذف پیدا نشد", 'warning')
        return False


async def full_delete_attachment_row(
    page,
    title: str,
    bot: Bot = None,
    user_id: int = None,
    prefix: str = "UPLOAD",
) -> bool:
    """
    حذف کامل یک ردیف پیوست:
      ۱. وارد حالت ویرایش ردیف
      ۲. حذف تمام فایل‌ها (btnDelete3)
      ۳. بازگشت به فهرست
      ۴. حذف ردیف (removeDocument)
    """
    _log(prefix, f"شروع حذف کامل ردیف [{title}]...")

    try:
        # مرحله ۱: وارد حالت ویرایش ردیف شویم
        escaped = title.replace("`", "'").replace("\\", "").replace('"', '\\"')
        edit_clicked = await page.evaluate(f'''() => {{
            const rows = Array.from(document.querySelectorAll('table tbody tr, .table tbody tr'));
            for (const row of rows) {{
                const cells = row.querySelectorAll('td');
                for (const cell of cells) {{
                    if (cell.innerText && cell.innerText.includes("{escaped}")) {{
                        let editBtn = row.querySelector('button[ng-click*="editDocument"]');
                        if (!editBtn) {{
                            const nextRow = row.nextElementSibling;
                            if (nextRow) editBtn = nextRow.querySelector('button[ng-click*="editDocument"]');
                        }}
                        if (editBtn && !editBtn.disabled) {{
                            editBtn.click();
                            return true;
                        }}
                    }}
                }}
            }}
            return false;
        }}''')

        if edit_clicked:
            await asyncio.sleep(4)
            _log(prefix, f"وارد حالت ویرایش ردیف [{title}] شدیم")

        # مرحله ۲: حذف تمام فایل‌ها
        files_deleted = await delete_all_files_in_row(page, bot, user_id, prefix)
        _log(prefix, f"{files_deleted} فایل از ردیف [{title}] حذف شد")

        # مرحله ۳: بازگشت به فهرست منضمات
        await soft_click_if_exists(page, "بازگشت به فهرست")
        await asyncio.sleep(3)
        await close_any_popup(page)
        await asyncio.sleep(1)

        # مرحله ۴: حذف خود ردیف (سطل زباله)
        row_deleted = await delete_document_row_by_title(page, title, prefix)
        if not row_deleted:
            _log(prefix, f"حذف ردیف [{title}] ناموفق با عنوان، تلاش با آخرین ردیف...", 'warning')
            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button[ng-click*="removeDocument"]'));
                if (btns.length > 0) btns[btns.length - 1].click();
            }''')
            await asyncio.sleep(2)
            await close_any_popup(page)

        await asyncio.sleep(2)
        await close_any_popup(page)
        _log(prefix, f"حذف کامل ردیف [{title}] پایان یافت")
        return True

    except Exception as e:
        _log(prefix, f"خطا در حذف ردیف [{title}]: {e}", 'error')
        return False


# =========================================================
# ۴. توابع مشترک آپلود
# =========================================================

async def click_save_doc_with_retry(
    page, bot: Bot = None, user_id: int = None,
    max_retries: int = MAX_SAVE_DOC_RETRIES,
    prefix: str = "UPLOAD",
) -> bool:
    for attempt in range(max_retries):
        await page.evaluate('''() => {
            const btn = document.querySelector('#btnSaveDoc');
            if (btn && !btn.disabled) btn.click();
        }''')

        if bot and user_id:
            had_expiry = await resilient_sleep(page, 8, bot, user_id)
            if had_expiry:
                _log(prefix, "نشست حین ذخیره سند تمدید شد")
                continue
        else:
            await asyncio.sleep(8)

        success = await page.evaluate('''() => {
            const popup = document.querySelector('.sweet-alert.showSweetAlert');
            if (!popup) return false;
            const icon = popup.querySelector('.sa-icon.sa-success');
            return icon && window.getComputedStyle(icon).display !== 'none';
        }''')
        if success:
            await close_success_popup(page)
            return True

        error_text = await get_and_close_error_popup_text(page)
        if error_text:
            _log(prefix, f"خطا در ذخیره سند (تلاش {attempt+1}/{max_retries}): {error_text}", 'warning')
            await asyncio.sleep(4)
            continue

        _log(prefix, f"ذخیره سند: پاسخی دریافت نشد (تلاش {attempt+1}/{max_retries})")
        await asyncio.sleep(4)

    return False


async def wait_for_upload_confirmation(
    page,
    expected_count: int,
    bot: Bot = None,
    user_id: int = None,
    timeout_sec: int = UPLOAD_CONFIRM_TIMEOUT,
    prefix: str = "UPLOAD",
) -> bool:
    for i in range(timeout_sec * 2):
        if i % 4 == 0 and bot and user_id:
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                _log(prefix, "نشست حین انتظار تایید آپلود تمدید شد")
                await asyncio.sleep(1)

        count = await page.evaluate('''() => {
            const alerts = Array.from(document.querySelectorAll('.alert-success [ng-bind-html]'));
            return alerts.filter(el => el.innerText && el.innerText.includes("پیوست مورد نظر با موفقیت ثبت گردید")).length;
        }''')
        if count >= expected_count:
            return True
        await asyncio.sleep(0.5)
    return False


async def click_apply_all_with_retry(
    page,
    expected_count: int,
    bot: Bot = None,
    user_id: int = None,
    max_retries: int = MAX_APPLY_ALL_RETRIES,
    prefix: str = "UPLOAD",
) -> bool:
    for attempt in range(max_retries):
        await page.evaluate('''() => {
            const btn = document.querySelector('#btnApplyAll');
            if (btn && !btn.disabled) btn.click();
        }''')

        if bot and user_id:
            had_expiry = await resilient_sleep(page, 10, bot, user_id)
            if had_expiry:
                _log(prefix, "نشست حین اعمال همه تمدید شد")
                continue
        else:
            await asyncio.sleep(10)

        confirmed = await page.evaluate(f'''() => {{
            const alerts = Array.from(document.querySelectorAll('[ng-bind-html]'));
            return alerts.filter(el => el.innerText && el.innerText.includes("پیوست مورد نظر با موفقیت تایید شد")).length >= {expected_count};
        }}''')
        if confirmed:
            return True

        # بررسی popup خطا — فقط اگر خطایی واقعاً وجود داشت ناموفق است
        error_text = await get_and_close_error_popup_text(page)
        if error_text:
            _log(prefix, f"خطا در اعمال همه (تلاش {attempt+1}): {error_text}", 'warning')
            await asyncio.sleep(5)
            continue

        # هیچ popup خطایی نیست → اعمال با موفقیت انجام شده
        _log(prefix, f"اعمال همه: بدون خطا (تایید متنی یافت نشد ولی popup خطا هم نبود) — موفق")
        return True

    return False


# =========================================================
# ۵. تابع اصلی: آپلود مقاوم یک ردیف
# =========================================================

async def resilient_upload_attachment(
    page,
    doc_title: str,
    image_paths: List[str],
    bot: Bot,
    user_id: int,
    prefix: str = "LAVAYEH",
    form_fill_fn: Optional[Callable] = None,
    task_key: Optional[str] = None,
    incomplete_tasks: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    آپلود مقاوم یک ردیف پیوست.

    form_fill_fn: async def fn(page, doc_title, image_paths, force_page_count=None) -> bool
        اگر None باشد، از فرم پیش‌فرض سایر ضمائم استفاده می‌شود.

    بازگشت: {"success": bool, "error": str|None, "error_type": str|None, "attempts": int}
    """
    result = {"success": False, "error": None, "error_type": None, "attempts": 0}

    # مرحله صفر: آماده‌سازی فایل‌ها
    prepared_paths, validation_errors = await prepare_files_for_upload(
        image_paths, bot, user_id, prefix, compress=True, convert_to_jpeg=True,
    )

    if not prepared_paths:
        result["error"] = "هیچ فایل معتبری برای آپلود وجود ندارد"
        result["error_type"] = "validation"
        if validation_errors:
            result["error"] += ": " + "; ".join(e["error"] for e in validation_errors)
        return result

    if validation_errors:
        _log(prefix, f"{len(validation_errors)} فایل نامعتبر حذف شد، {len(prepared_paths)} فایل باقی‌مانده", 'warning')

    image_count = len(prepared_paths)

    for attempt in range(1, MAX_UPLOAD_ATTEMPTS + 1):
        result["attempts"] = attempt
        _log(prefix, f"آپلود [{doc_title}] - تلاش {attempt}/{MAX_UPLOAD_ATTEMPTS}")

        try:
            # ذخیره checkpoint
            if task_key and incomplete_tasks is not None:
                _save_checkpoint(incomplete_tasks, task_key,
                                f"آپلود [{doc_title}] (تلاش {attempt})",
                                {"doc_title": doc_title, "image_count": image_count, "attempt": attempt})

            # بررسی انقضای نشست
            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                _log(prefix, f"نشست قبل از آپلود [{doc_title}] تمدید شد")
                await asyncio.sleep(2)

            # مرحله ۱: پر کردن فرم
            if form_fill_fn:
                form_ok = await form_fill_fn(page, doc_title, prepared_paths)
                if not form_ok:
                    _log(prefix, f"form_fill_fn برای [{doc_title}] ناموفق", 'warning')
                    await asyncio.sleep(3)
                    continue
            else:
                form_ok = await _default_fill_other_attachment_form(page, doc_title, image_count)
                if not form_ok:
                    _log(prefix, f"فرم پیش‌فرض [{doc_title}] ناموفق", 'warning')
                    await asyncio.sleep(3)
                    continue

            await asyncio.sleep(2)

            # مرحله ۲: ذخیره سند
            save_ok = await click_save_doc_with_retry(page, bot, user_id, prefix=prefix)
            if not save_ok:
                error_text = await get_and_close_error_popup_text(page)
                error_type = detect_error_type(error_text) if error_text else "save_failed"
                _log(prefix, f"ذخیره سند [{doc_title}] ناموفق: {error_text} (نوع: {error_type})", 'error')

                # اگر خطای تعداد صفحات: تلاش با تعداد جایگزین
                if error_type == "page_count":
                    for alt_count in [image_count + 1, image_count - 1, image_count + 2]:
                        if alt_count < 1:
                            continue
                        _log(prefix, f"تلاش با تعداد صفحات جایگزین: {alt_count}")
                        await close_any_popup(page)
                        await asyncio.sleep(1)
                        if form_fill_fn:
                            await form_fill_fn(page, doc_title, prepared_paths, force_page_count=alt_count)
                        else:
                            await _default_fill_other_attachment_form(page, doc_title, alt_count)
                        save_ok2 = await click_save_doc_with_retry(page, bot, user_id, prefix=prefix)
                        if save_ok2:
                            save_ok = True
                            break
                    if not save_ok:
                        await close_any_popup(page)
                        await asyncio.sleep(3)
                        continue
                else:
                    await close_any_popup(page)
                    await asyncio.sleep(3)
                    continue

            await asyncio.sleep(3)

            # مرحله ۳: ویرایش و آپلود فایل‌ها
            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button[ng-click*="editDocument"]'));
                if (btns.length > 0) btns[btns.length - 1].click();
            }''')
            await asyncio.sleep(4)

            file_input = page.locator('input[type="file"]').first
            if prepared_paths:
                await file_input.set_input_files(prepared_paths)
                await asyncio.sleep(3)

            # مرحله ۴: کلیک آپلود همه
            await page.evaluate('''() => {
                const btn = document.querySelector('#btnUploadAll');
                if (btn && !btn.disabled) btn.click();
            }''')

            had_expiry = await check_and_handle_expiry(page, bot, user_id)
            if had_expiry:
                _log(prefix, f"نشست بعد از آپلود همه [{doc_title}] تمدید شد")
                await asyncio.sleep(3)
                await full_delete_attachment_row(page, doc_title, bot, user_id, prefix)
                await asyncio.sleep(2)
                continue

            # مرحله ۵: انتظار تایید آپلود
            all_uploaded = await wait_for_upload_confirmation(
                page, image_count, bot, user_id, prefix=prefix
            )

            if not all_uploaded:
                error_text = await get_and_close_error_popup_text(page)
                error_type = detect_error_type(error_text) if error_text else "upload_timeout"
                _log(prefix, f"آپلود [{doc_title}] تایید نشد (نوع: {error_type}): {error_text}", 'warning')
                await full_delete_attachment_row(page, doc_title, bot, user_id, prefix)
                await asyncio.sleep(2)
                continue

            # مرحله ۶: اعمال همه
            all_confirmed = await click_apply_all_with_retry(
                page, image_count, bot, user_id, prefix=prefix
            )

            if all_confirmed:
                await close_success_popup(page)
                await asyncio.sleep(1)
                await close_error_popup(page)
                await asyncio.sleep(0.5)
                await wait_for_angular_idle(page)
                await asyncio.sleep(2)

                if task_key and incomplete_tasks is not None:
                    _clear_checkpoint(incomplete_tasks, task_key)

                _log(prefix, f"آپلود [{doc_title}] موفق (تلاش {attempt})")
                result["success"] = True
                return result

            # اعمال همه ناموفق
            error_text = await get_and_close_error_popup_text(page)
            error_type = detect_error_type(error_text) if error_text else "apply_failed"
            _log(prefix, f"اعمال همه [{doc_title}] ناموفق (نوع: {error_type}): {error_text}", 'warning')

            await full_delete_attachment_row(page, doc_title, bot, user_id, prefix)
            await asyncio.sleep(2)

        except Exception as e:
            _log(prefix, f"استثنای آپلود [{doc_title}] (تلاش {attempt}): {e}", 'error')
            try:
                await close_any_popup(page)
                await asyncio.sleep(2)
                await full_delete_attachment_row(page, doc_title, bot, user_id, prefix)
                await asyncio.sleep(2)
            except Exception as cleanup_err:
                _log(prefix, f"خطا در پاکسازی: {cleanup_err}", 'error')
            await asyncio.sleep(5)

    result["error"] = f"آپلود [{doc_title}] پس از {MAX_UPLOAD_ATTEMPTS} تلاش ناموفق"
    result["error_type"] = "exhausted"

    if task_key and incomplete_tasks is not None:
        _save_checkpoint(incomplete_tasks, task_key,
                        f"شکست نهایی آپلود [{doc_title}]",
                        {"doc_title": doc_title, "image_count": image_count, "exhausted": True})

    return result


# =========================================================
# ۶. فرم پیش‌فرض: سایر ضمائم
# =========================================================

async def _default_fill_other_attachment_form(page, doc_title: str, page_count: int) -> bool:
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
            inp.value = "{page_count}";
            inp.dispatchEvent(new Event("input", {{ bubbles: true }}));
        }}
    }}''')

    await page.evaluate('''() => {
        const btn = document.querySelector('#incAttach0');
        if (btn && !btn.disabled) btn.click();
    }''')
    await asyncio.sleep(3)

    return True


# =========================================================
# ۷. آپلود گروهی
# =========================================================

async def resilient_upload_attachment_groups(
    page,
    groups: List[Dict[str, Any]],
    bot: Bot,
    user_id: int,
    prefix: str = "LAVAYEH",
    form_fill_fn: Optional[Callable] = None,
    task_key: Optional[str] = None,
    incomplete_tasks: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    آپلود مقاوم چندین گروه پیوست.
    بازگشت: {"success": bool, "failed_groups": [...], "successful_groups": [...]}
    """
    overall = {"success": True, "failed_groups": [], "successful_groups": []}
    completed = 0
    total = len(groups)

    for idx, group in enumerate(groups):
        title = group.get("title", "مستندات")
        paths = group.get("paths", [])

        if not paths:
            _log(prefix, f"گروه [{title}] فایلی ندارد، رد شدن")
            overall["successful_groups"].append(title)
            completed += 1
            continue

        # اگر این گروه دوم به بعد است، دکمه «پیوست جدید» را بزن
        if completed > 0:
            _log(prefix, f"کلیک «پیوست جدید» قبل از گروه {completed+1}/{total}: [{title}]")
            await asyncio.sleep(2)
            clicked = await page.evaluate('''() => {
                const btn = document.querySelector('#newAttachmentType');
                if (btn && !btn.disabled) { btn.click(); return true; }
                return false;
            }''')
            if not clicked:
                clicked = await soft_click_if_exists(page, "پیوست جدید")
            if clicked:
                await asyncio.sleep(3)
                await wait_for_angular_idle(page)
                await asyncio.sleep(1)
            else:
                _log(prefix, "دکمه «پیوست جدید» پیدا نشد — ادامه بدون کلیک", 'warning')

        _log(prefix, f"آپلود گروه {completed+1}/{total}: [{title}] ({len(paths)} فایل)")

        upload_result = await resilient_upload_attachment(
            page, title, paths, bot, user_id, prefix,
            form_fill_fn=form_fill_fn,
            task_key=task_key,
            incomplete_tasks=incomplete_tasks,
        )

        if upload_result["success"]:
            overall["successful_groups"].append(title)
            completed += 1

            # ذخیره checkpoint گروهی
            if task_key and incomplete_tasks is not None:
                save_upload_checkpoint(
                    incomplete_tasks, task_key,
                    completed_titles=overall["successful_groups"],
                    current_group=None,
                    total_groups=total,
                )
        else:
            overall["success"] = False
            overall["failed_groups"].append({
                "title": title,
                "error": upload_result.get("error", "نامشخص"),
                "error_type": upload_result.get("error_type", "نامشخص"),
                "attempts": upload_result.get("attempts", 0),
            })
            break

    return overall


# =========================================================
# ۸. مدیریت نقاط بازیابی
# =========================================================

def _save_checkpoint(incomplete_tasks: dict, task_key: str, step: str, extra_data: dict = None):
    if task_key in incomplete_tasks:
        incomplete_tasks[task_key]["last_completed_step"] = step
        incomplete_tasks[task_key]["upload_checkpoint"] = extra_data or {}
        incomplete_tasks[task_key]["updated_at"] = time.time()


def _clear_checkpoint(incomplete_tasks: dict, task_key: str):
    if task_key in incomplete_tasks:
        incomplete_tasks[task_key].pop("upload_checkpoint", None)


def save_upload_checkpoint(
    incomplete_tasks: dict,
    task_key: str,
    completed_titles: list,
    current_group: str = None,
    total_groups: int = 0,
):
    if task_key in incomplete_tasks:
        incomplete_tasks[task_key]["upload_checkpoint"] = {
            "completed_groups": completed_titles,
            "current_group": current_group,
            "total_groups": total_groups,
            "saved_at": time.time(),
        }
        incomplete_tasks[task_key]["updated_at"] = time.time()


def get_upload_checkpoint(incomplete_tasks: dict, task_key: str) -> Optional[dict]:
    if task_key in incomplete_tasks:
        checkpoint = incomplete_tasks[task_key].get("upload_checkpoint")
        if checkpoint:
            saved_at = checkpoint.get("saved_at", 0)
            age_hours = (time.time() - saved_at) / 3600
            if age_hours > CHECKPOINT_EXPIRY_HOURS:
                _log("UPLOAD", f"checkpoint منقضی ({age_hours:.1f} ساعت)", 'warning')
                return None
            return checkpoint
    return None


def build_incomplete_task_entry(
    bill_no: str,
    user_id: int,
    task_type: str,
    next_step: str,
    task_data: dict,
    last_completed_step: str,
    attachment_groups: list = None,
) -> dict:
    entry = {
        "bill_no": bill_no,
        "user_id": user_id,
        "type": task_type,
        "last_completed_step": last_completed_step,
        "next_step": next_step,
        "task_data": task_data,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    if attachment_groups is not None:
        entry["attachment_groups"] = attachment_groups
    return entry
