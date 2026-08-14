#!/usr/bin/env python3
"""
apply-inquiry-panel-fix.py — اسکریپت اعمال اصلاحات ثبت استعلام در پنل ادمین

این اسکریپت ۳ تغییر اعمال می‌کند:
۱. فایل جدید panel_sync.py ایجاد می‌کند
۲. handlers.py را اصلاح می‌کند (اضافه کردن full_name و fee به job_queue)
۳. scenarios.py را اصلاح می‌کند (ثبت استعلام در پنل ادمین پس از موفقیت)

طریقه استفاده:
    python apply-inquiry-panel-fix.py --project-dir /path/to/online.judicial.services

    یا بدون آرگومان (پیش‌فرض: مسیر فعلی):
    python apply-inquiry-panel-fix.py
"""
import os
import re
import sys
import shutil
import argparse
from datetime import datetime


def backup_file(filepath):
    """ایجاد پشتیبان از فایل."""
    if os.path.exists(filepath):
        backup = filepath + f".bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(filepath, backup)
        print(f"  [پشتیبان] {backup}")
        return backup
    return None


def create_panel_sync(project_dir):
    """ایجاد فایل panel_sync.py."""
    filepath = os.path.join(project_dir, "panel_sync.py")
    if os.path.exists(filepath):
        backup_file(filepath)

    content = '''"""
panel_sync.py — ثبت رویدادهای استعلام در پنل ادمین (Next.js API)

این ماژول وظیفه ارسال داده‌های استعلام، لایحه و سایر خدمات
به API پنل ادمین را بر عهده دارد تا در دیتابیس SQLite ذخیره شوند
و در پنل ادمین قابل مشاهده باشند.
"""
import logging

import aiohttp

from config import ADMIN_API_BASE

logger = logging.getLogger(__name__)


async def register_case_to_panel(
    telegram_id,
    full_name,
    service_type,
    status="COMPLETED",
    tracking_code=None,
    document_category=None,
    sub_category=None,
    branch_name=None,
    branch_code=None,
    province=None,
    fee=0,
    fee_status="UNPAID",
    result_summary=None,
    error_details=None,
    error_step=None,
):
    """
    ثبت یک Case در پنل ادمین از طریق API.
    """
    url = f"{ADMIN_API_BASE}/admin/cases"

    payload = {
        "telegramId": str(telegram_id),
        "fullName": full_name,
        "serviceType": service_type,
        "status": status,
        "trackingCode": tracking_code,
        "documentCategory": document_category,
        "subCategory": sub_category,
        "branchName": branch_name,
        "branchCode": branch_code,
        "province": province,
        "fee": fee,
        "feeStatus": fee_status,
        "resultSummary": result_summary,
        "errorDetails": error_details,
        "errorStep": error_step,
    }

    # حذف فیلدهای None
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    logger.info(
                        f"[PANEL_SYNC] Case ثبت شد: id={data.get('id', '?')} "
                        f"type={service_type} user={telegram_id} tracking={tracking_code}"
                    )
                    return data
                else:
                    text = await resp.text()
                    logger.warning(
                        f"[PANEL_SYNC] خطا در ثبت Case: HTTP {resp.status} -- {text[:200]}"
                    )
                    return None
    except Exception as e:
        logger.error(f"[PANEL_SYNC] خطا در ارتباط با پنل ادمین: {e}")
        return None


async def register_inquiry_to_panel(
    user_id,
    full_name,
    tracking_code,
    doc_category,
    doc_subcategory=None,
    fee=0,
    result_summary=None,
):
    """
    ثبت یک استعلام (INQUIRY) در پنل ادمین.
    """
    return await register_case_to_panel(
        telegram_id=str(user_id),
        full_name=full_name,
        service_type="INQUIRY",
        status="COMPLETED",
        tracking_code=tracking_code,
        document_category=doc_category,
        sub_category=doc_subcategory,
        fee=fee,
        fee_status="UNPAID",
        result_summary=result_summary,
    )


async def register_failed_inquiry_to_panel(
    user_id,
    full_name,
    tracking_code,
    doc_category,
    doc_subcategory=None,
    error_details=None,
    error_step=None,
):
    """
    ثبت یک استعلام ناموفق در پنل ادمین با وضعیت FAILED.
    """
    return await register_case_to_panel(
        telegram_id=str(user_id),
        full_name=full_name,
        service_type="INQUIRY",
        status="FAILED",
        tracking_code=tracking_code,
        document_category=doc_category,
        sub_category=doc_subcategory,
        fee=0,
        fee_status="UNPAID",
        error_details=error_details,
        error_step=error_step,
    )
'''

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  [ایجاد] panel_sync.py")


def fix_handlers(project_dir):
    """اصلاح handlers.py — اضافه کردن full_name و fee به job_queue.put()."""
    filepath = os.path.join(project_dir, "handlers.py")
    if not os.path.exists(filepath):
        print(f"  [خطا] handlers.py یافت نشد: {filepath}")
        return False

    backup_file(filepath)

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    changes = []

    # ── تغییر ۱: اضافه کردن import panel_sync در بالای فایل ──
    if 'from panel_sync import' not in content:
        # اضافه کردن بعد از import sheets
        content = content.replace(
            'from sheets import append_to_sheet, log_event',
            'from sheets import append_to_sheet, log_event\nfrom panel_sync import register_inquiry_to_panel'
        )
        changes.append("اضافه شدن import panel_sync")

    # ── تغییر ۲: job_queue.put در پرداخت اصلی (خط 184) ──
    # الگو:
    #   'user_id': message.from_user.id,
    #   'query_type': q_type,
    #   'tracking_code': tracking_code,
    #   'doc_category': doc_category,
    #   'doc_subcategory': doc_subcategory,
    #   'doc_type': doc_name,
    #   'need_attachments': need_attachments

    old_pattern_1 = """            await runtime_state.job_queue.put({
                'user_id': message.from_user.id, 
                'query_type': q_type, 
                'tracking_code': tracking_code, 
                'doc_category': doc_category, 
                'doc_subcategory': doc_subcategory, 
                'doc_type': doc_name,
                'need_attachments': need_attachments
            })"""

    new_pattern_1 = """            await runtime_state.job_queue.put({
                'user_id': message.from_user.id, 
                'query_type': q_type, 
                'tracking_code': tracking_code, 
                'doc_category': doc_category, 
                'doc_subcategory': doc_subcategory, 
                'doc_type': doc_name,
                'need_attachments': need_attachments,
                'full_name': message.from_user.full_name,
                'payment_fee': item.get('fee', 0),
            })"""

    if old_pattern_1 in content:
        content = content.replace(old_pattern_1, new_pattern_1)
        changes.append("اضافه شدن full_name و payment_fee به job_queue (پرداخت اصلی)")

    # ── تغییر ۳: job_queue.put در تایید دستی سبد (okcart) ──
    old_pattern_2 = """        await runtime_state.job_queue.put({
            'user_id': target_user_id, 
            'query_type': q_type, 
            'tracking_code': tracking_code, 
            'doc_category': doc_category, 
            'doc_subcategory': doc_subcategory, 
            'doc_type': doc_name,
            'need_attachments': need_attachments
        })"""

    new_pattern_2 = """        await runtime_state.job_queue.put({
            'user_id': target_user_id, 
            'query_type': q_type, 
            'tracking_code': tracking_code, 
            'doc_category': doc_category, 
            'doc_subcategory': doc_subcategory, 
            'doc_type': doc_name,
            'need_attachments': need_attachments,
            'full_name': user_data.get('full_name', ''),
            'payment_fee': item.get('fee', 0),
        })"""

    if old_pattern_2 in content:
        content = content.replace(old_pattern_2, new_pattern_2)
        changes.append("اضافه شدن full_name و payment_fee به job_queue (تایید دستی سبد)")

    # ── تغییر ۴: job_queue.put در پرداخت معاف (exempt) ──
    old_pattern_3 = """            await runtime_state.job_queue.put({
                'user_id': message.from_user.id,
                'query_type': data.get('query_type'),
                'tracking_code': data.get('tracking_code'),
                'doc_category': data.get('doc_category'),
                'doc_subcategory': data.get('doc_subcategory'),
                'doc_type': f"{data.get('doc_category')} - {data.get('doc_subcategory')}" if data.get('doc_subcategory') else data.get('doc_category'),
                'need_attachments': data.get('need_attachments', False)
            })"""

    new_pattern_3 = """            await runtime_state.job_queue.put({
                'user_id': message.from_user.id,
                'query_type': data.get('query_type'),
                'tracking_code': data.get('tracking_code'),
                'doc_category': data.get('doc_category'),
                'doc_subcategory': data.get('doc_subcategory'),
                'doc_type': f"{data.get('doc_category')} - {data.get('doc_subcategory')}" if data.get('doc_subcategory') else data.get('doc_category'),
                'need_attachments': data.get('need_attachments', False),
                'full_name': message.from_user.full_name,
                'payment_fee': fee,
            })"""

    if old_pattern_3 in content:
        content = content.replace(old_pattern_3, new_pattern_3)
        changes.append("اضافه شدن full_name و payment_fee به job_queue (معاف از پرداخت)")

    # ── تغییر ۵: ذخیره full_name در state هنگام شروع ──
    # بعد از rules_accepted: ذخیره full_name کاربر
    if "await state.update_data(full_name=" not in content:
        content = content.replace(
            "await message.answer(\"\\u2753 **\\u0644\\u0637\\u0641\\u0627\\u064b \\u0646\\u062d\\u0648\\u0647 \\u062b\\u0628\\u062a \\u062f\\u0631\\u062e\\u0648\\u0627\\u0633\\u062a \\u062e\\u0648\\u062f \\u0631\\u0627 \\u0627\\u0646\\u062a\\u062e\\u0627\\u0628 \\u0641\\u0631\\u0645\\u0627\\u06cc\\u06cc\\u062f:**\", reply_markup=flow_type_kb)",
            "await state.update_data(full_name=message.from_user.full_name)\n    await message.answer(\"❓ **لطفاً نحوه ثبت درخواست خود را انتخاب فرمایید:**\", reply_markup=flow_type_kb)"
        )
        if content == original:
            # تلاش با متن فارسی
            pass
        else:
            changes.append("ذخیره full_name در state هنگام شروع")

    if content == original:
        print("  [هشدار] هیچ تغییری در handlers.py اعمال نشد")
        return False

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    for c in changes:
        print(f"  [تغییر] {c}")
    return True


def fix_scenarios(project_dir):
    """اصلاح scenarios.py — ثبت استعلام در پنل ادمین پس از موفقیت."""
    filepath = os.path.join(project_dir, "scenarios.py")
    if not os.path.exists(filepath):
        print(f"  [خطا] scenarios.py یافت نشد: {filepath}")
        return False

    backup_file(filepath)

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    changes = []

    # ── تغییر ۱: اضافه کردن import panel_sync ──
    if 'from panel_sync import' not in content:
        content = content.replace(
            'from sheets import log_event',
            'from sheets import log_event\nfrom panel_sync import register_inquiry_to_panel'
        )
        changes.append("اضافه شدن import panel_sync")

    # ── تغییر ۲: ثبت در پنل ادمین پس از ارسال نتیجه (بدون پیوست) ──
    # بعد از خط ارسال doc به کاربر (بدون منضمات):
    #   await bot.send_document(user_id, document=doc, caption=f"...{tracking_code}")
    #   os.remove(pdf_path)
    # و قبل از بسته شدن except:
    old_send_no_attach = """                        else:
                            doc = FSInputFile(pdf_path)
                            await bot.send_document(user_id, document=doc, caption=f"\\u06f5\\u0644\\u0627 \\u0627\\u0633\\u062a\\u0639\\u0644\\u0627\\u0645 \\u06a9\\u062f \\u067e\\u06cc\\u06af\\u06cc\\u0631\\u06cc: `{tracking_code}`")
                            os.remove(pdf_path)"""

    # Trying with the actual text
    old_send_no_attach2 = """                        else:
                            doc = FSInputFile(pdf_path)
                            await bot.send_document(user_id, document=doc, caption=f"📄 استعلام کد پیگیری: `{tracking_code}`")
                            os.remove(pdf_path)"""

    new_send_no_attach = """                        else:
                            doc = FSInputFile(pdf_path)
                            await bot.send_document(user_id, document=doc, caption=f"📄 استعلام کد پیگیری: `{tracking_code}`")
                            os.remove(pdf_path)

                            # ── ثبت استعلام در پنل ادمین ──
                            try:
                                await register_inquiry_to_panel(
                                    user_id=user_id,
                                    full_name=data.get('full_name', ''),
                                    tracking_code=tracking_code,
                                    doc_category=category,
                                    doc_subcategory=subcategory,
                                    fee=data.get('payment_fee', 0),
                                    result_summary=f"استعلام کد رهگیری - {doc_name}"
                                )
                            except Exception as panel_err:
                                logger.warning(f"[PANEL_SYNC] خطا در ثبت استعلام (بدون پیوست): {panel_err}")"""

    if old_send_no_attach2 in content:
        content = content.replace(old_send_no_attach2, new_send_no_attach)
        changes.append("ثبت استعلام در پنل پس از ارسال نتیجه (بدون پیوست)")

    # ── تغییر ۳: ثبت در پنل ادمین پس از ارسال فایل‌ها با منضمات ──
    # بعد از "✅ استخراج منضمات کاملاً تمام شد."
    old_attach_done = 'await bot.send_message(user_id, "✅ استخراج منضمات کاملاً تمام شد.")'

    new_attach_done = '''await bot.send_message(user_id, "✅ استخراج منضمات کاملاً تمام شد.")

                            # ── ثبت استعلام در پنل ادمین ──
                            try:
                                await register_inquiry_to_panel(
                                    user_id=user_id,
                                    full_name=data.get('full_name', ''),
                                    tracking_code=tracking_code,
                                    doc_category=category,
                                    doc_subcategory=subcategory,
                                    fee=data.get('payment_fee', 0),
                                    result_summary=f"استعلام با منضمات - {doc_name} - {len(real_rows)} پیوست"
                                )
                            except Exception as panel_err:
                                logger.warning(f"[PANEL_SYNC] خطا در ثبت استعلام (با منضمات): {panel_err}")'''

    if old_attach_done in content:
        content = content.replace(old_attach_done, new_attach_done)
        changes.append("ثبت استعلام در پنل پس از ارسال منضمات")

    # ── تغییر ۴: ثبت در پنل ادمین برای استعلام بدون تب منضمات ──
    old_no_mozamatat = 'await bot.send_message(user_id, "📄 این درخواست فاقد بخش منضمات است.")'

    new_no_mozamatat = '''await bot.send_message(user_id, "📄 این درخواست فاقد بخش منضمات است.")

                            # ── ثبت استعلام در پنل ادمین ──
                            try:
                                await register_inquiry_to_panel(
                                    user_id=user_id,
                                    full_name=data.get('full_name', ''),
                                    tracking_code=tracking_code,
                                    doc_category=category,
                                    doc_subcategory=subcategory,
                                    fee=data.get('payment_fee', 0),
                                    result_summary=f"استعلام بدون منضمات - {doc_name}"
                                )
                            except Exception as panel_err:
                                logger.warning(f"[PANEL_SYNC] خطا در ثبت استعلام (بدون منضمات): {panel_err}")'''

    if old_no_mozamatat in content:
        content = content.replace(old_no_mozamatat, new_no_mozamatat)
        changes.append("ثبت استعلام در پنل برای درخواست بدون منضمات")

    # ── تغییر ۵: ثبت در پنل ادمین برای استعلام بدون پیوست واقعی ──
    old_no_real_attach = 'await bot.send_message(user_id, "📄 این درخواست فاقد پیوست واقعی است.")'

    new_no_real_attach = '''await bot.send_message(user_id, "📄 این درخواست فاقد پیوست واقعی است.")

                            # ── ثبت استعلام در پنل ادمین ──
                            try:
                                await register_inquiry_to_panel(
                                    user_id=user_id,
                                    full_name=data.get('full_name', ''),
                                    tracking_code=tracking_code,
                                    doc_category=category,
                                    doc_subcategory=subcategory,
                                    fee=data.get('payment_fee', 0),
                                    result_summary=f"استعلام بدون پیوست واقعی - {doc_name}"
                                )
                            except Exception as panel_err:
                                logger.warning(f"[PANEL_SYNC] خطا در ثبت استعلام (بدون پیوست واقعی): {panel_err}")'''

    if old_no_real_attach in content:
        content = content.replace(old_no_real_attach, new_no_real_attach)
        changes.append("ثبت استعلام در پنل برای درخواست بدون پیوست واقعی")

    if content == original:
        print("  [هشدار] هیچ تغییری در scenarios.py اعمال نشد")
        return False

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    for c in changes:
        print(f"  [تغییر] {c}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="اعمال اصلاحات ثبت استعلام در پنل ادمین"
    )
    parser.add_argument(
        "--project-dir",
        default=os.getcwd(),
        help="مسیر پروژه (پیش‌فرض: مسیر فعلی)"
    )
    args = parser.parse_args()

    project_dir = args.project_dir

    print("=" * 60)
    print("  اعمال اصلاحات ثبت استعلام در پنل ادمین")
    print("=" * 60)
    print(f"  مسیر پروژه: {project_dir}")
    print()

    # بررسی وجود پروژه
    if not os.path.isdir(project_dir):
        print(f"[خطا] مسیر پروژه یافت نشد: {project_dir}")
        sys.exit(1)

    # ۱. ایجاد panel_sync.py
    print("[۱/۳] ایجاد panel_sync.py ...")
    create_panel_sync(project_dir)
    print()

    # ۲. اصلاح handlers.py
    print("[۲/۳] اصلاح handlers.py ...")
    h_ok = fix_handlers(project_dir)
    print()

    # ۳. اصلاح scenarios.py
    print("[۳/۳] اصلاح scenarios.py ...")
    s_ok = fix_scenarios(project_dir)
    print()

    print("=" * 60)
    if h_ok and s_ok:
        print("  ✅ همه اصلاحات با موفقیت اعمال شد!")
    else:
        print("  ⚠️  برخی اصلاحات اعمال نشد — بررسی دستی لازم است")
    print("=" * 60)
    print()
    print("تغییرات اعمال‌شده:")
    print("  - فایل جدید: panel_sync.py (ثبت Case در API پنل ادمین)")
    print("  - handlers.py: full_name و payment_fee به job_queue اضافه شد")
    print("  - scenarios.py: ثبت خودکار استعلام در پنل پس از موفقیت")
    print()
    print("⚠️  پس از اعمال، ربات را ری‌استارت کنید.")


if __name__ == "__main__":
    main()
