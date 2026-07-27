"""
هندلرهای بخش ثبت اظهارنامه — فلوی مکالمه تلگرام.

جریان:
  ۱. ورود به بخش اظهارنامه
  ۲. دریافت نوع شخصیت اظهارکننده(ها)  ← مانند بخش لایحه
     ⚠ اگر وکیل انتخاب شد، حتماً باید حقیقی یا حقوقی هم باشد
  ۳. دریافت نوع شخصیت مخاطب(ها)
     ← گزینه استعلام شماره تماس هم وجود دارد
  ۴. عنوان (موضوع) اظهارنامه
  ۵. شرح متن
  ۶. مدارک (پیوست‌ها) — مانند بخش لایحه
     ⚠ اگر اظهارکننده حقوقی داشت: مدرک نمایندگی اجباری است
  ۷. پیش‌نمایش و تایید
"""

import asyncio
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

import runtime_state
from states import Form
from keyboards import (
    main_menu_kb, restart_kb, back_only_kb,
    representative_type_kb,
    lavayeh_attachment_more_kb,
    ezhhar_confirm_kb, ezhhar_edit_kb,
    ezhhar_subject_kb,
    ezhhar_declarant_add_more_kb,
    ezhhar_addressee_add_more_kb,
    ezhhar_attachment_title_kb_first,
    ezhhar_attachment_title_kb,
    ezhhar_attachment_more_kb,
    create_ezhhar_declarant_person_type_kb,
    create_ezhhar_addressee_person_type_kb,
)

ezhharnameh_router = Router()

_FA_AR = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789"
)

def _to_en(text: str) -> str:
    return text.translate(_FA_AR).replace(" ", "").strip()

def _fmt(n: int) -> str:
    return f"{n:,}"


# ══════════════════════════════════════════════════════════════════════════════
# ورود به بخش اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(StateFilter("*"), F.text == "📋 ثبت اظهارنامه")
async def ezhharnameh_entry(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(
        ezhhar_declarants=[],        # لیست اظهارکنندگان
        ezhhar_addressees=[],        # لیست مخاطبین
        ezhhar_subject="",
        ezhhar_text="",
        ezhhar_attachments=[],       # پیوست‌ها
        ezhhar_images=[],
    )
    await message.answer(
        "📋 **ثبت اظهارنامه**\n\n"
        "**مرحله ۱:** لطفاً **نوع شخصیت اظهارکننده** را انتخاب فرمایید:\n\n"
        "⚠️ توجه: اگر **وکیل** را انتخاب می‌کنید، باید حداقل یک **شخص حقیقی یا حقوقی** نیز اضافه کنید.",
        reply_markup=create_ezhhar_declarant_person_type_kb(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.ezhhar_declarant_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۱ — نوع شخصیت اظهارکننده
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_declarant_person_type)
async def ezhhar_declarant_person_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    declarants = data.get("ezhhar_declarants", [])
    used_types = [p.get("person_type") for p in declarants]

    if text == "✅ اتمام و ادامه":
        if not declarants:
            await message.answer("⚠️ حداقل یک اظهارکننده باید اضافه شود.")
            return

        # بررسی: اگر وکیل داشتیم، باید حقیقی یا حقوقی هم داشته باشیم
        has_lawyer = any(p.get("person_type") == "وکیل" for p in declarants)
        has_real_or_legal = any(p.get("person_type") in ("شخص حقیقی", "شخص حقوقی") for p in declarants)
        if has_lawyer and not has_real_or_legal:
            await message.answer(
                "⚠️ **توجه مهم:**\n\n"
                "چون **وکیل** اضافه کرده‌اید، باید حداقل یک **شخص حقیقی یا حقوقی** نیز وجود داشته باشد.\n\n"
                "لطفاً نوع شخص دیگری انتخاب کنید:",
                reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types),
                parse_mode="Markdown"
            )
            return

        # رفتن به مرحله مخاطب
        await message.answer(
            "**مرحله ۲:** لطفاً **نوع شخصیت مخاطب** اظهارنامه را انتخاب فرمایید:\n\n"
            "📌 درصورتی که کدملی مخاطب را ندارید و صرفاً شماره تماس شخص مورد نظر را دارید، "
            "می‌توانید از گزینه **«استعلام شماره تماس»** استفاده کنید.",
            reply_markup=create_ezhhar_addressee_person_type_kb(),
            parse_mode="Markdown"
        )
        await state.set_state(Form.ezhhar_addressee_person_type)
        return

    if text not in ["شخص حقیقی", "شخص حقوقی", "وکیل"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if declarants else [])
        )
        return

    await state.update_data(_ezhhar_current_declarant={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            "🏢 لطفاً **شناسه ملی شرکت** اظهارکننده را وارد فرمایید:\n_(۱۱ رقمی)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ezhhar_declarant_company_id)
    else:
        type_label = "وکیل" if text == "وکیل" else "شخص"
        await message.answer(
            f"🔢 لطفاً **کد ملی {type_label}** اظهارکننده را وارد کنید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ezhhar_declarant_national_id)


@ezhharnameh_router.message(Form.ezhhar_declarant_company_id)
async def ezhhar_declarant_company_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        declarants = data.get("ezhhar_declarants", [])
        used_types = [p.get("person_type") for p in declarants]
        await message.answer(
            "👤 لطفاً نوع شخص اظهارکننده را انتخاب کنید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if declarants else [])
        )
        await state.set_state(Form.ezhhar_declarant_person_type)
        return

    company_id = _to_en(message.text)
    if not company_id.isdigit() or len(company_id) != 11:
        await message.answer("⚠️ شناسه ملی شرکت باید **۱۱ رقمی** باشد:", parse_mode="Markdown")
        return

    data = await state.get_data()
    current = data.get("_ezhhar_current_declarant", {})
    current["company_id"] = company_id
    await state.update_data(_ezhhar_current_declarant=current)

    await message.answer("👔 نماینده شرکت چه سمتی دارد؟", reply_markup=representative_type_kb)
    await state.set_state(Form.ezhhar_declarant_representative_type)


@ezhharnameh_router.message(Form.ezhhar_declarant_representative_type)
async def ezhhar_declarant_representative_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text not in ["مدیرعامل", "نماینده"]:
        await message.answer("⚠️ لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=representative_type_kb)
        return

    data = await state.get_data()
    current = data.get("_ezhhar_current_declarant", {})
    current["representative_type"] = text
    await state.update_data(_ezhhar_current_declarant=current)

    await message.answer(
        f"🔢 لطفاً **کد ملی {text}** شرکت اظهارکننده را وارد کنید:\n_(۱۰ رقمی)_",
        reply_markup=back_only_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.ezhhar_declarant_national_id)


@ezhharnameh_router.message(Form.ezhhar_declarant_national_id)
async def ezhhar_declarant_national_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        declarants = data.get("ezhhar_declarants", [])
        used_types = [p.get("person_type") for p in declarants]
        await message.answer(
            "👤 لطفاً نوع شخص اظهارکننده را انتخاب کنید:",
            reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types if declarants else [])
        )
        await state.set_state(Form.ezhhar_declarant_person_type)
        return

    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ کد ملی باید **۱۰ رقمی** باشد:", parse_mode="Markdown")
        return

    data = await state.get_data()
    current = data.get("_ezhhar_current_declarant", {})
    current["national_id"] = nat_id
    declarants = data.get("ezhhar_declarants", [])
    declarants.append(current)
    await state.update_data(ezhhar_declarants=declarants, _ezhhar_current_declarant={})

    person_type = current.get("person_type", "")
    used_types = [p.get("person_type") for p in declarants]

    await message.answer(
        f"✅ **{person_type}** با کدملی `{nat_id}` ثبت شد.\n\n"
        f"آیا اظهارکننده دیگری نیز وجود دارد؟",
        reply_markup=create_ezhhar_declarant_person_type_kb(exclude=used_types),
        parse_mode="Markdown"
    )
    await state.set_state(Form.ezhhar_declarant_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۲ — نوع شخصیت مخاطب
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_addressee_person_type)
async def ezhhar_addressee_person_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    addressees = data.get("ezhhar_addressees", [])
    used_types = [p.get("person_type") for p in addressees]

    # استعلام شماره تماس — متوقف کردن اظهارنامه
    if text == "📞 استعلام شماره تماس":
        await message.answer(
            "📞 **فرایند اظهارنامه متوقف گردید.**\n\n"
            "در حال انتقال به بخش استعلام شماره تماس...\n"
            "پس از دریافت نتیجه استعلام، می‌توانید مجدداً ثبت اظهارنامه را آغاز کنید.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await state.clear()
        # راه‌اندازی فلوی استعلام شماره تماس
        await message.answer(
            "📞 لطفاً شماره تماس مورد نظر را ارسال فرمایید:\n(با فرمت 09 آغاز شود)",
            reply_markup=back_only_kb
        )
        await state.set_state(Form.waiting_for_phone_number)
        return

    if text == "✅ اتمام و ادامه":
        if not addressees:
            await message.answer(
                "⚠️ حداقل یک مخاطب باید اضافه شود.",
                reply_markup=create_ezhhar_addressee_person_type_kb()
            )
            return
        # رفتن به مرحله عنوان
        await message.answer(
            "**مرحله ۳:** لطفاً **عنوان (موضوع) اظهارنامه** را وارد فرمایید:\n\n"
            "یا از گزینه زیر استفاده کنید اگر عنوان مهم نیست:",
            reply_markup=ezhhar_subject_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ezhhar_subject)
        return

    if text not in ["شخص حقیقی", "شخص حقوقی"]:
        await message.answer(
            "⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:",
            reply_markup=create_ezhhar_addressee_person_type_kb(exclude=used_types if addressees else [])
        )
        return

    await state.update_data(_ezhhar_current_addressee={"person_type": text})

    if text == "شخص حقوقی":
        await message.answer(
            "🏢 لطفاً **شناسه ملی شرکت** مخاطب را وارد فرمایید:\n_(۱۱ رقمی)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ezhhar_addressee_company_id)
    else:
        await message.answer(
            "🔢 لطفاً **کد ملی مخاطب** را وارد کنید:\n_(۱۰ رقمی)_",
            reply_markup=back_only_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ezhhar_addressee_national_id)


@ezhharnameh_router.message(Form.ezhhar_addressee_company_id)
async def ezhhar_addressee_company_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        addressees = data.get("ezhhar_addressees", [])
        used_types = [p.get("person_type") for p in addressees]
        await message.answer(
            "👥 لطفاً نوع شخص مخاطب را انتخاب کنید:",
            reply_markup=create_ezhhar_addressee_person_type_kb(exclude=used_types if addressees else [])
        )
        await state.set_state(Form.ezhhar_addressee_person_type)
        return

    company_id = _to_en(message.text)
    if not company_id.isdigit() or len(company_id) != 11:
        await message.answer("⚠️ شناسه ملی شرکت باید **۱۱ رقمی** باشد:", parse_mode="Markdown")
        return

    data = await state.get_data()
    current = data.get("_ezhhar_current_addressee", {})
    current["company_id"] = company_id
    await state.update_data(_ezhhar_current_addressee=current)

    await message.answer("👔 نماینده شرکت مخاطب چه سمتی دارد؟", reply_markup=representative_type_kb)
    await state.set_state(Form.ezhhar_addressee_representative_type)


@ezhharnameh_router.message(Form.ezhhar_addressee_representative_type)
async def ezhhar_addressee_representative_type_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text not in ["مدیرعامل", "نماینده"]:
        await message.answer("⚠️ لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=representative_type_kb)
        return

    data = await state.get_data()
    current = data.get("_ezhhar_current_addressee", {})
    current["representative_type"] = text
    await state.update_data(_ezhhar_current_addressee=current)

    await message.answer(
        f"🔢 لطفاً **کد ملی {text}** شرکت مخاطب را وارد کنید:\n_(۱۰ رقمی)_",
        reply_markup=back_only_kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.ezhhar_addressee_national_id)


@ezhharnameh_router.message(Form.ezhhar_addressee_national_id)
async def ezhhar_addressee_national_id_handler(message: Message, state: FSMContext):
    if not message.text:
        return
    if message.text == "🔙 بازگشت":
        data = await state.get_data()
        addressees = data.get("ezhhar_addressees", [])
        used_types = [p.get("person_type") for p in addressees]
        await message.answer(
            "👥 لطفاً نوع شخص مخاطب را انتخاب کنید:",
            reply_markup=create_ezhhar_addressee_person_type_kb(exclude=used_types if addressees else [])
        )
        await state.set_state(Form.ezhhar_addressee_person_type)
        return

    nat_id = _to_en(message.text)
    if not re.match(r"^[0-9]{10}$", nat_id):
        await message.answer("⚠️ کد ملی باید **۱۰ رقمی** باشد:", parse_mode="Markdown")
        return

    data = await state.get_data()
    current = data.get("_ezhhar_current_addressee", {})
    current["national_id"] = nat_id
    addressees = data.get("ezhhar_addressees", [])
    addressees.append(current)
    await state.update_data(ezhhar_addressees=addressees, _ezhhar_current_addressee={})

    person_type = current.get("person_type", "")
    used_types = [p.get("person_type") for p in addressees]

    await message.answer(
        f"✅ **مخاطب ({person_type})** با کدملی `{nat_id}` ثبت شد.\n\n"
        f"آیا مخاطب دیگری نیز وجود دارد؟\n\n"
        f"📌 اگر کدملی مخاطب بعدی را ندارید، می‌توانید «استعلام شماره تماس» را انتخاب کنید.",
        reply_markup=create_ezhhar_addressee_person_type_kb(exclude=used_types),
        parse_mode="Markdown"
    )
    await state.set_state(Form.ezhhar_addressee_person_type)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۳ — عنوان اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_subject)
async def ezhhar_subject_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ لطفاً عنوان را وارد کنید یا از گزینه زیر استفاده کنید:", reply_markup=ezhhar_subject_kb)
        return

    if text == "🔹 عنوان مهم نیست (ادامه مراحل)":
        subject = "سایر"
    else:
        subject = text

    await state.update_data(ezhhar_subject=subject)

    await message.answer(
        f"✅ عنوان «**{subject}**» ثبت شد.\n\n"
        "**مرحله ۴:** لطفاً **شرح متن اظهارنامه** را به صورت کامل و تایپ‌شده ارسال فرمایید:\n\n"
        "⚠️ **توجه:** متن پس از ارسال قابل ویرایش نمی‌باشد.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.ezhhar_text)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۴ — شرح متن اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_text)
async def ezhhar_text_handler(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ لطفاً شرح متن را به صورت **متن** ارسال فرمایید.")
        return

    await state.update_data(ezhhar_text=message.text, ezhhar_attachments=[], ezhhar_images=[])

    data = await state.get_data()
    declarants = data.get("ezhhar_declarants", [])
    has_legal = any(p.get("person_type") == "شخص حقوقی" for p in declarants)

    if has_legal:
        # مدرک نمایندگی اجباری است
        await message.answer(
            "**مرحله ۵ — مدارک:**\n\n"
            "⚠️ **توجه مهم:** چون اظهارکننده شخص **حقوقی** دارید، ارسال تصویر **مدرک نمایندگی اجباری** است.\n\n"
            "لطفاً ابتدا عنوان مدرک نمایندگی را وارد کنید\n"
            "_(مثلاً: روزنامه رسمی، آگهی تأسیس، وکالت‌نامه رسمی)_",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        await state.update_data(_ezhhar_mandatory_proxy_sent=False)
        await state.set_state(Form.ezhhar_attachment_title)
    else:
        await _ask_ezhhar_attachment(message, state, is_first=True)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۵ — پیوست‌ها (مدارک)
# ══════════════════════════════════════════════════════════════════════════════
async def _ask_ezhhar_attachment(message: Message, state: FSMContext, is_first: bool):
    await state.update_data(ezhhar_images=[])
    kb = ezhhar_attachment_title_kb_first if is_first else ezhhar_attachment_title_kb
    intro = "✅ متن اظهارنامه ثبت شد.\n\n" if is_first else ""
    await message.answer(
        f"{intro}📄 **عنوان مدرک:**\n\n"
        "در صورتی که تصویری برای ضمیمه دارید، عنوان آن را تایپ کنید\n"
        "یا یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(Form.ezhhar_attachment_title)


@ezhharnameh_router.message(Form.ezhhar_attachment_title)
async def ezhhar_attachment_title_handler(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ لطفاً عنوان را وارد کنید.")
        return

    data = await state.get_data()
    attachments = data.get("ezhhar_attachments", [])
    mandatory_sent = data.get("_ezhhar_mandatory_proxy_sent", True)

    # رد کردن (فقط اگر مدرک نمایندگی اجباری قبلاً ارسال شده یا نیاز نبود)
    if text == "⏭ رد کردن (بدون مدرک)" and not attachments and mandatory_sent:
        await state.update_data(ezhhar_attachments=[])
        await _go_to_ezhhar_preview(message, state)
        return

    if text == "🔹 عنوان مهم نیست (صرفا درج شود مستندات)":
        title = "مستندات"
    else:
        title = text

    await state.update_data(_ezhhar_current_att_title=title)

    await message.answer(
        f"✅ عنوان «**{title}**» ثبت شد.\n\n"
        "🖼 لطفاً تصاویر مربوط به این مدرک را به صورت **عکس (Photo)** ارسال فرمایید.\n"
        "⚠️ فقط فرمت **JPG / JPEG** قابل قبول است.\n\n"
        "پس از ارسال همه تصاویر، دکمه **«اتمام ارسال تصاویر»** را بفشارید.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.ezhhar_images)


@ezhharnameh_router.message(Form.ezhhar_images, F.photo)
async def ezhhar_receive_image(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    images = data.get("ezhhar_images", [])
    images.append(message.photo[-1].file_id)
    await state.update_data(ezhhar_images=images)

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    manage_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
            [KeyboardButton(text="🗑 حذف تصویر")]
        ],
        resize_keyboard=True
    )
    await message.reply(
        f"✅ تصویر شماره **{len(images)}** دریافت شد.\n"
        f"مجموع تصاویر این مدرک: **{len(images)} تصویر**",
        reply_markup=manage_kb,
        parse_mode="Markdown"
    )


@ezhharnameh_router.message(Form.ezhhar_images, F.document)
async def ezhhar_reject_document(message: Message, state: FSMContext):
    await message.answer(
        "⚠️ لطفاً تصاویر را به صورت **عکس (Photo)** ارسال کنید، نه فایل.",
        parse_mode="Markdown"
    )


@ezhharnameh_router.message(Form.ezhhar_images, F.text == "🗑 حذف تصویر")
async def ezhhar_ask_delete_image(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    images = data.get("ezhhar_images", [])
    if not images:
        await message.answer("⚠️ لیست تصاویر خالی است.")
        return
    await message.answer("🗑 **حذف تصویر:**\n\nعکس‌های ارسالی:", parse_mode="Markdown")
    for i, file_id in enumerate(images):
        await bot.send_photo(message.chat.id, photo=file_id, caption=f"تصویر شماره {i + 1}")
    await message.answer(
        "لطفاً **شماره تصویر** برای حذف را ارسال فرمایید:",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.update_data(_ezhhar_deleting_image=True)


@ezhharnameh_router.message(Form.ezhhar_images)
async def ezhhar_images_text(message: Message, state: FSMContext):
    text = message.text or ""
    data = await state.get_data()
    images = data.get("ezhhar_images", [])
    deleting = data.get("_ezhhar_deleting_image", False)

    if deleting:
        num_str = _to_en(text)
        if num_str.isdigit():
            idx = int(num_str) - 1
            if 0 <= idx < len(images):
                images.pop(idx)
                await state.update_data(ezhhar_images=images, _ezhhar_deleting_image=False)
                from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
                if images:
                    manage_kb = ReplyKeyboardMarkup(
                        keyboard=[
                            [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
                            [KeyboardButton(text="🗑 حذف تصویر")]
                        ],
                        resize_keyboard=True
                    )
                else:
                    manage_kb = ReplyKeyboardRemove()
                await message.answer(
                    f"✅ تصویر شماره **{idx+1}** حذف شد.\n"
                    f"مجموع باقیمانده: **{len(images)} تصویر**",
                    reply_markup=manage_kb,
                    parse_mode="Markdown"
                )
                return
            else:
                await message.answer(f"⚠️ شماره نامعتبر. لطفاً عددی بین ۱ تا {len(images)} وارد کنید:")
                return
        else:
            await state.update_data(_ezhhar_deleting_image=False)

    if text == "✅ اتمام ارسال تصاویر":
        if not images:
            await message.answer("⚠️ حداقل یک تصویر برای این مدرک ارسال کنید.")
            return

        attachments = data.get("ezhhar_attachments", [])
        title = data.get("_ezhhar_current_att_title", "مستندات")
        attachments.append({"title": title, "images": images})
        await state.update_data(
            ezhhar_attachments=attachments,
            ezhhar_images=[],
            _ezhhar_mandatory_proxy_sent=True
        )

        await message.answer(
            f"✅ مدرک «**{title}**» با **{len(images)} تصویر** ثبت شد.\n\nآیا مدرک دیگری دارید؟",
            reply_markup=ezhhar_attachment_more_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ezhhar_attachment_more)
        return

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    if images:
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ اتمام ارسال تصاویر")],
                [KeyboardButton(text="🗑 حذف تصویر")]
            ],
            resize_keyboard=True
        )
    else:
        kb = None
    await message.answer("⚠️ لطفاً تصویر این مدرک را ارسال کنید:", reply_markup=kb)


@ezhharnameh_router.message(Form.ezhhar_attachment_more)
async def ezhhar_attachment_more_handler(message: Message, state: FSMContext):
    text = message.text or ""
    if text == "➕ بله، عنوان و مدرک دیگر دارم":
        await _ask_ezhhar_attachment(message, state, is_first=False)
        return
    if text == "✅ خیر، ادامه بده":
        await _go_to_ezhhar_preview(message, state)
        return
    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=ezhhar_attachment_more_kb)


# ══════════════════════════════════════════════════════════════════════════════
# ساخت پیش‌نمایش اظهارنامه
# ══════════════════════════════════════════════════════════════════════════════
def build_ezhhar_preview(data: dict) -> str:
    declarants = data.get("ezhhar_declarants", [])
    addressees = data.get("ezhhar_addressees", [])
    subject = data.get("ezhhar_subject", "---")
    ezhhar_text = data.get("ezhhar_text", "---")
    attachments = data.get("ezhhar_attachments", [])

    def _person_line(p, idx):
        ptype = p.get("person_type", "")
        nat_id = p.get("national_id", "")
        if ptype == "شخص حقوقی":
            company_id = p.get("company_id", "")
            rep = p.get("representative_type", "")
            return f"  {idx}. {ptype} | شناسه: `{company_id}` | {rep}: `{nat_id}`"
        return f"  {idx}. {ptype} | کدملی: `{nat_id}`"

    declarants_text = "\n".join([_person_line(p, i+1) for i, p in enumerate(declarants)]) or "  (ندارد)"
    addressees_text = "\n".join([_person_line(p, i+1) for i, p in enumerate(addressees)]) or "  (ندارد)"

    text_preview = ezhhar_text[:200] + "..." if len(ezhhar_text) > 200 else ezhhar_text

    att_text = ""
    total_imgs = 0
    for i, att in enumerate(attachments, 1):
        n = len(att.get("images", []))
        total_imgs += n
        att_text += f"  {i}. {att.get('title', 'مستندات')} — {n} تصویر\n"
    if not att_text:
        att_text = "  (بدون مدرک)\n"

    return (
        f"📋 **پیش‌نمایش اظهارنامه:**\n\n"
        f"👤 اظهارکننده(ها):\n{declarants_text}\n\n"
        f"👥 مخاطب(ها):\n{addressees_text}\n\n"
        f"📌 موضوع: **{subject}**\n\n"
        f"📄 شرح متن:\n{text_preview}\n\n"
        f"🖼 مدارک ({total_imgs} تصویر در {len(attachments)} عنوان):\n{att_text}\n"
        f"آیا اطلاعات فوق صحیح است؟"
    )


async def _go_to_ezhhar_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    preview = build_ezhhar_preview(data)
    await message.answer(preview, reply_markup=ezhhar_confirm_kb, parse_mode="Markdown")
    await state.set_state(Form.ezhhar_confirm)


# ══════════════════════════════════════════════════════════════════════════════
# مرحله ۶ — تایید یا ویرایش
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_confirm)
async def ezhhar_confirm_handler(message: Message, state: FSMContext, bot: Bot):
    text = message.text or ""

    if text == "✅ تایید و شروع ثبت":
        data = await state.get_data()
        user_id = message.from_user.id

        await message.answer(
            "⏳ **درخواست اظهارنامه تایید شد.**\n\nدر حال ارسال به صف پردازش...",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )

        await runtime_state.job_queue.put({
            "user_id": user_id,
            "query_type": "اظهارنامه_ثبت",
            "task_type": "EZHHARNAMEH_SUBMIT",
            "ezhhar_declarants": data.get("ezhhar_declarants", []),
            "ezhhar_addressees": data.get("ezhhar_addressees", []),
            "ezhhar_subject": data.get("ezhhar_subject", "سایر"),
            "ezhhar_text": data.get("ezhhar_text", ""),
            "ezhhar_attachments": data.get("ezhhar_attachments", []),
        })

        await state.clear()
        return

    if text == "✏️ ویرایش اطلاعات":
        await message.answer(
            "✏️ **ویرایش اطلاعات:**\n\nکدام بخش را می‌خواهید ویرایش کنید؟",
            reply_markup=ezhhar_edit_kb,
            parse_mode="Markdown"
        )
        await state.set_state(Form.ezhhar_edit_choice)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=ezhhar_confirm_kb)


# ══════════════════════════════════════════════════════════════════════════════
# منوی ویرایش
# ══════════════════════════════════════════════════════════════════════════════
@ezhharnameh_router.message(Form.ezhhar_edit_choice)
async def ezhhar_edit_choice_handler(message: Message, state: FSMContext):
    text = message.text or ""

    if text == "🔙 بازگشت به پیش‌نمایش":
        await _go_to_ezhhar_preview(message, state)
        return

    if text == "👤 ویرایش اظهارکننده(ها)":
        await state.update_data(ezhhar_declarants=[], _ezhhar_current_declarant={})
        await message.answer(
            "👤 لیست اظهارکنندگان پاک شد.\nلطفاً مجدداً **نوع شخصیت اظهارکننده** را انتخاب فرمایید:",
            reply_markup=create_ezhhar_declarant_person_type_kb()
        )
        await state.set_state(Form.ezhhar_declarant_person_type)
        return

    if text == "👥 ویرایش مخاطب(ها)":
        await state.update_data(ezhhar_addressees=[], _ezhhar_current_addressee={})
        await message.answer(
            "👥 لیست مخاطبین پاک شد.\nلطفاً مجدداً **نوع شخصیت مخاطب** را انتخاب فرمایید:",
            reply_markup=create_ezhhar_addressee_person_type_kb()
        )
        await state.set_state(Form.ezhhar_addressee_person_type)
        return

    if text == "📌 ویرایش عنوان اظهارنامه":
        await message.answer(
            "📌 لطفاً عنوان جدید اظهارنامه را وارد کنید:",
            reply_markup=ezhhar_subject_kb
        )
        await state.set_state(Form.ezhhar_subject)
        return

    if text == "📄 ویرایش شرح متن":
        await message.answer("📄 لطفاً متن جدید را ارسال فرمایید:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.ezhhar_text)
        return

    if text == "🖼 ویرایش مدارک":
        await state.update_data(ezhhar_attachments=[], _ezhhar_mandatory_proxy_sent=False)
        await message.answer("🖼 مدارک قبلی پاک شدند.")
        data = await state.get_data()
        declarants = data.get("ezhhar_declarants", [])
        has_legal = any(p.get("person_type") == "شخص حقوقی" for p in declarants)
        if has_legal:
            await message.answer(
                "⚠️ چون اظهارکننده شخص **حقوقی** دارید، ارسال **مدرک نمایندگی اجباری** است.\n\n"
                "لطفاً ابتدا عنوان مدرک نمایندگی را وارد کنید:",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown"
            )
            await state.set_state(Form.ezhhar_attachment_title)
        else:
            await _ask_ezhhar_attachment(message, state, is_first=True)
        return

    await message.answer("⚠️ لطفاً یکی از گزینه‌های موجود را انتخاب کنید:", reply_markup=ezhhar_edit_kb)
