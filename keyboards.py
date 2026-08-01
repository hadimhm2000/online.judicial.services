"""همه‌ی کیبوردهای تلگرام (ReplyKeyboardMarkup) و منوی دسته‌بندی‌ها/زیردسته‌ها یک‌جا اینجا هستند."""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

restart_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔄 ثبت درخواست جدید (شروع)")]], resize_keyboard=True)
back_only_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 بازگشت")]], resize_keyboard=True)
accept_rules_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ قوانین و مقررات را تایید می‌نمایم")]], resize_keyboard=True)

flow_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="1️⃣ استعلام (تک درخواست)")],
        [KeyboardButton(text="🛒 ثبت سبد خرید (چند استعلام همزمان)")],
        [KeyboardButton(text="📝 ثبت لایحه")],
        [KeyboardButton(text="📋 ثبت اظهارنامه")],
        [KeyboardButton(text="🧮 محاسبه تمبر مالیاتی وکیل")],
        [KeyboardButton(text="🛠 ابزار فایل (کاهش حجم عکس / تبدیل PDF به عکس)")],
    ], resize_keyboard=True)

# =========================================================
# کیبوردهای بخش ابزار فایل
# =========================================================
file_tools_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🖼 کاهش حجم عکس")],
        [KeyboardButton(text="📄➡️🖼 تبدیل PDF به عکس")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")],
    ], resize_keyboard=True)

file_tools_back_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔙 بازگشت")]], resize_keyboard=True)

main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="1️⃣ استعلام لوایح، اظهارنامه، دادخواست و ...")],
        [KeyboardButton(text="2️⃣ استعلام براساس شماره تماس")],
        [KeyboardButton(text="3️⃣ استعلام براساس کدملی")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")]
    ], resize_keyboard=True)

doc_category_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="لایحه"), KeyboardButton(text="اظهارنامه")],
        [KeyboardButton(text="شکواییه"), KeyboardButton(text="دادخواست بدوی")],
        [KeyboardButton(text="دعاوی دادگاههای صلح")],
        [KeyboardButton(text="دعاوی اعتراضی"), KeyboardButton(text="دعاوی طاری")],
        [KeyboardButton(text="شورای حل اختلاف"), KeyboardButton(text="دیوان عدالت اداری")]
    ], resize_keyboard=True)

attachments_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📎 بله، پیوست‌ها هم ارسال شوند")],
        [KeyboardButton(text="📄 خیر، فقط چاپ اصلی کافی است")]
    ], resize_keyboard=True)

cart_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ ثبت استعلام جدید (افزودن به سبد)")],
        [KeyboardButton(text="🛒 مشاهده سبد خرید و تسویه حساب")],
        [KeyboardButton(text="🧹 خالی کردن سبد استعلام")]
    ], resize_keyboard=True)

pay_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💳 پرداخت و تسویه حساب")],
        [KeyboardButton(text="🔙 بازگشت به سبد خرید")]
    ], resize_keyboard=True)

SUB_MENUS = {
    "دعاوی اعتراضی": [
        "تجدیدنظرخواهی", "واخواهی", "فرجام خواهی",
        "اعاده دادرسی مدنی", "اعاده دادرسی کیفری",
        "اعتراض ثالث", "اعتراض به قرار دادسرا"
    ],
    "دعاوی طاری": [
        "دعوای تقابل", "دعوای ورود ثالث", "دعوای جلب ثالث"
    ],
    "شورای حل اختلاف": [
        "دعاوی حقوقی", "دعاوی کیفری",
        "تجدیدنظرخواهی شورا", "واخواهی شورا", "اعتراض ثالث شورا"
    ],
    "دیوان عدالت اداری": [
        "دادخواست بدوی دیوان عدالت اداری", "تجدیدنظرخواهی دیوان عدالت اداری",
        "ارایه و پیگیری لایحه", "جلب ثالث در بدوی دیوان عدالت اداری",
        "ورود ثالث در بدوی دیوان عدالت اداری", "جلب ثالث درتجدید نظر دیوان عدالت اداری",
        "ورود ثالث درتجدید نظر دیوان عدالت اداری", "دادخواست اعتراض ثالث دیوان عدالت اداری",
        "اعاده دادرسی دیوان عدالت اداری", "اعتراض به آراء و تصمیمات مراجع اختصاصی اداری",
        "درخواست اعمال ماده 79 قانون دیوان عدالت اداری"
    ]
}

confirm_single_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ تایید و دریافت فاکتور پرداخت"), KeyboardButton(text="❌ انصراف و اصلاح اطلاعات")]], resize_keyboard=True)
confirm_cart_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ افزودن به سبد خرید"), KeyboardButton(text="❌ انصراف و اصلاح اطلاعات")]], resize_keyboard=True)
admin_login_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ ورودم تکمیل شد")]], resize_keyboard=True)

def create_submenu_kb(category_name):
    items = SUB_MENUS.get(category_name, [])
    keyboard = []
    for i in range(0, len(items), 2):
        row = [KeyboardButton(text=items[i])]
        if i + 1 < len(items):
            row.append(KeyboardButton(text=items[i+1]))
        keyboard.append(row)
    keyboard.append([KeyboardButton(text="🔙 بازگشت به منوی قبل")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# =========================================================
# کیبوردهای بخش لایحه
# =========================================================

LAVAYEH_TITLES = [
    "لایحه دفاعیه",
    "صدور اجرائیه",
    "اعتراض به نظر کارشناس",
    "اعتراض به قرار رد دفتر",
    "اعلام وکالت",
    "سایر عناوین"
]

lavayeh_title_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="لایحه دفاعیه"), KeyboardButton(text="صدور اجرائیه")],
        [KeyboardButton(text="اعتراض به نظر کارشناس")],
        [KeyboardButton(text="اعتراض به قرار رد دفتر")],
        [KeyboardButton(text="اعلام وکالت")],
        [KeyboardButton(text="سایر عناوین")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")]
    ],
    resize_keyboard=True
)

# کیبورد انتخاب روش ورود شماره پرونده
lavayeh_tracking_method_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="1️⃣ شماره پرونده و ردیف فرعی")],
        [KeyboardButton(text="2️⃣ شعبه رسیدگی کننده و شماره بایگانی")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

# کیبورد انتخاب نحوه ورود نام شعبه
# گزینه ورود دستی حذف شد - فقط انتخاب از لیست
lavayeh_branch_input_method_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔍 انتخاب شعبه از لیست")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

PROVINCES = [
    "آذربایجان شرقی", "آذربایجان غربی", "اردبیل", "اصفهان",
    "البرز", "ایلام", "بوشهر", "تهران",
    "چهارمحال و بختیاری", "خراسان جنوبی", "خراسان رضوی", "خراسان شمالی",
    "خوزستان", "زنجان", "سمنان", "سیستان و بلوچستان",
    "فارس", "قزوین", "قم", "کردستان",
    "کرمان", "کرمانشاه", "کهگیلویه و بویراحمد", "گلستان",
    "گیلان", "لرستان", "مازندران", "مرکزی",
    "هرمزگان", "همدان", "یزد"
]

def create_province_kb():
    keyboard = []
    for i in range(0, len(PROVINCES), 2):
        row = [KeyboardButton(text=PROVINCES[i])]
        if i + 1 < len(PROVINCES):
            row.append(KeyboardButton(text=PROVINCES[i + 1]))
        keyboard.append(row)
    keyboard.append([KeyboardButton(text="🔙 بازگشت")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

PERSON_TYPES = ["شخص حقیقی", "شخص حقوقی", "وکیل"]

def create_person_type_kb(exclude: list = None):
    exclude = exclude or []
    available = [p for p in PERSON_TYPES if p not in exclude]
    keyboard = []
    for i in range(0, len(available), 2):
        row = [KeyboardButton(text=available[i])]
        if i + 1 < len(available):
            row.append(KeyboardButton(text=available[i + 1]))
        keyboard.append(row)
    if exclude:
        keyboard.append([KeyboardButton(text="✅ خیر، ادامه مراحل")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

representative_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="مدیرعامل"), KeyboardButton(text="نماینده")]
    ],
    resize_keyboard=True
)

add_or_finish_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن کدملی دیگر")],
        [KeyboardButton(text="✅ اتمام و ادامه")]
    ],
    resize_keyboard=True
)

lavayeh_attachment_title_kb_first = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (صرفا درج شود مستندات)")],
        [KeyboardButton(text="⏭ رد کردن (بدون مدرک)")]
    ],
    resize_keyboard=True
)

lavayeh_attachment_title_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (صرفا درج شود مستندات)")]
    ],
    resize_keyboard=True
)

lavayeh_attachment_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ بله، عنوان و مدرک دیگر دارم")],
        [KeyboardButton(text="✅ خیر، ادامه بده")]
    ],
    resize_keyboard=True
)

lavayeh_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و شروع ثبت")],
        [KeyboardButton(text="✏️ ویرایش اطلاعات")]
    ],
    resize_keyboard=True
)

lavayeh_edit_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📝 ویرایش عنوان لایحه")],
        [KeyboardButton(text="🔢 ویرایش شماره پرونده")],
        [KeyboardButton(text="🏙 ویرایش استان")],
        [KeyboardButton(text="🔢 ویرایش ردیف فرعی")],
        [KeyboardButton(text="👤 ویرایش اشخاص ارائه‌دهنده")],
        [KeyboardButton(text="📄 ویرایش شرح متن لایحه")],
        [KeyboardButton(text="🖼 ویرایش تصاویر مدارک")],
        [KeyboardButton(text="🔙 بازگشت به پیش‌نمایش")]
    ],
    resize_keyboard=True
)

lavayeh_cancel_reminder_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="بله"), KeyboardButton(text="خیر")]
    ],
    resize_keyboard=True
)

lavayeh_sign_ready_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ آماده‌ام، کد امضا ارسال شود")]
    ],
    resize_keyboard=True
)

lavayeh_sign_resend_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="بله"), KeyboardButton(text="خیر")]
    ],
    resize_keyboard=True
)

lavayeh_sign_later_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="بله"), KeyboardButton(text="خیر")]
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای بخش اعلام وکالت
# =========================================================

ealam_more_lawyers_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ بله، وکیل دیگری هم هست")],
        [KeyboardButton(text="✅ خیر، ادامه مراحل")]
    ],
    resize_keyboard=True
)

ealam_more_contracts_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن شماره قرارداد دیگر")],
        [KeyboardButton(text="✅ ادامه مراحل")]
    ],
    resize_keyboard=True
)

ealam_stamp_amount_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❓ نمیدانم، نیاز به محاسبه دارم")],
        [KeyboardButton(text="🚫 نیاز به ابطال تمبر ندارد")]
    ],
    resize_keyboard=True
)

ealam_claim_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="1️⃣ دعوی مالی است و مبلغ خواسته را می‌دانم")],
        [KeyboardButton(text="2️⃣ دعوی غیر مالی است")],
        [KeyboardButton(text="3️⃣ عدم نیاز به تمبر")]
    ],
    resize_keyboard=True
)

ealam_stamp_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📌 تمبر بدوی")],
        [KeyboardButton(text="📌 تمبر تجدیدنظر")],
        [KeyboardButton(text="📌 تمبر کلی")]
    ],
    resize_keyboard=True
)

continue_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ ادامه مراحل")]
    ],
    resize_keyboard=True
)

ealam_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و شروع ثبت")],
        [KeyboardButton(text="✏️ ویرایش اطلاعات")]
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای بخش محاسبه تمبر مستقل (منوی اصلی)
# =========================================================

stamp_calc_claim_type_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="1️⃣ دعوی مالی است و مبلغ خواسته را می‌دانم")],
        [KeyboardButton(text="2️⃣ دعوی غیر مالی است")]
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای بخش اظهارنامه
# =========================================================

EZHHAR_PERSON_TYPES = ["شخص حقیقی", "شخص حقوقی", "وکیل"]

def create_ezhhar_declarant_person_type_kb(exclude: list = None):
    """کیبورد نوع شخص اظهارکننده - همیشه سه گزینه اول را نشان می‌دهد"""
    exclude = exclude or []
    available = [p for p in EZHHAR_PERSON_TYPES if p not in exclude]
    keyboard = []
    for i in range(0, len(available), 2):
        row = [KeyboardButton(text=available[i])]
        if i + 1 < len(available):
            row.append(KeyboardButton(text=available[i + 1]))
        keyboard.append(row)
    # همیشه دکمه اتمام را نشان بده (حتی اگر exclude خالی باشد)
    keyboard.append([KeyboardButton(text="✅ اتمام و ادامه")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def create_ezhhar_addressee_person_type_kb(exclude: list = None, show_finish: bool = None):
    """کیبورد نوع شخص مخاطب اظهارنامه"""
    exclude = exclude or []
    available = [p for p in ["شخص حقیقی", "شخص حقوقی"] if p not in exclude]
    keyboard = []
    for i in range(0, len(available), 2):
        row = [KeyboardButton(text=available[i])]
        if i + 1 < len(available):
            row.append(KeyboardButton(text=available[i + 1]))
        keyboard.append(row)
    # گزینه استعلام شماره تماس
    keyboard.append([KeyboardButton(text="📞 استعلام شماره تماس")])
    show_finish = bool(exclude) if show_finish is None else show_finish
    if show_finish:
        keyboard.append([KeyboardButton(text="✅ اتمام و ادامه")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

ezhhar_declarant_add_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن شخص اظهارکننده دیگر")],
        [KeyboardButton(text="✅ اتمام و ادامه")]
    ],
    resize_keyboard=True
)

ezhhar_addressee_add_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن مخاطب دیگر")],
        [KeyboardButton(text="✅ اتمام و ادامه")],
        [KeyboardButton(text="📞 استعلام شماره تماس")]
    ],
    resize_keyboard=True
)

ezhhar_subject_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (ادامه مراحل)")]
    ],
    resize_keyboard=True
)

ezhhar_attachment_title_kb_first = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (صرفا درج شود مستندات)")],
        [KeyboardButton(text="⏭ رد کردن (بدون مدرک)")]
    ],
    resize_keyboard=True
)

ezhhar_attachment_title_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔹 عنوان مهم نیست (صرفا درج شود مستندات)")]
    ],
    resize_keyboard=True
)

ezhhar_attachment_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ بله، عنوان و مدرک دیگر دارم")],
        [KeyboardButton(text="✅ خیر، ادامه بده")]
    ],
    resize_keyboard=True
)

ezhhar_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و شروع ثبت")],
        [KeyboardButton(text="✏️ ویرایش اطلاعات")]
    ],
    resize_keyboard=True
)

ezhhar_edit_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 ویرایش اظهارکننده(ها)")],
        [KeyboardButton(text="👥 ویرایش مخاطب(ها)")],
        [KeyboardButton(text="📌 ویرایش عنوان اظهارنامه")],
        [KeyboardButton(text="📄 ویرایش شرح متن")],
        [KeyboardButton(text="🖼 ویرایش مدارک")],
        [KeyboardButton(text="🔙 بازگشت به پیش‌نمایش")]
    ],
    resize_keyboard=True
)

# =========================================================
# کیبوردهای ثبت دسته‌جمعی (بیش از ۵ مورد)
# =========================================================

bulk_choice_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⚡️ ثبت دسته‌جمعی سریع (بدون معطلی - فایل اکسل)")],
        [KeyboardButton(text="1️⃣ ثبت تکی (روال عادی)")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")]
    ],
    resize_keyboard=True
)

# کیبورد روش ورود برای ثبت دسته‌جمعی - فقط اکسل
bulk_input_method_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 دانلود نمونه اکسل و آپلود فایل")],
        [KeyboardButton(text="🔙 بازگشت")]
    ],
    resize_keyboard=True
)

bulk_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و ارسال برای مدیر")],
        [KeyboardButton(text="🔄 ارسال مجدد فایل / اصلاح")],
        [KeyboardButton(text="❌ انصراف و بازگشت")]
    ],
    resize_keyboard=True
)

# کیبورد برای انتخاب پیوست هر ردیف در ثبت دسته‌جمعی
bulk_attachment_row_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📎 افزودن پیوست برای این ردیف")],
        [KeyboardButton(text="⏭ رد شدن از این ردیف (بدون پیوست)")],
        [KeyboardButton(text="✅ اتمام پیوست‌گذاری و ادامه")],
        [KeyboardButton(text="❌ انصراف")]
    ],
    resize_keyboard=True
)

# کیبورد برای ادامه پیوست‌گذاری ردیف
bulk_attachment_more_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ افزودن پیوست دیگر برای این ردیف")],
        [KeyboardButton(text="✅ اتمام پیوست این ردیف و رفتن به ردیف بعدی")],
        [KeyboardButton(text="❌ انصراف")]
    ],
    resize_keyboard=True
)

# کیبورد تایید مدیر برای ثبت دسته‌جمعی
admin_bulk_confirm_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و شروع پردازش")],
        [KeyboardButton(text="❌ رد درخواست")]
    ],
    resize_keyboard=True
)
