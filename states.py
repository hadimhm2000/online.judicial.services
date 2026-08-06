"""حالت‌های مکالمه‌ی تلگرام (FSM) — تمام State های ربات فقط اینجا تعریف می‌شوند."""
from aiogram.fsm.state import State, StatesGroup

class Form(StatesGroup):
    waiting_for_rule_acceptance = State()
    waiting_for_flow_type = State()
    main_menu = State()
    waiting_for_tracking_code = State()
    waiting_for_phone_number = State()
    waiting_for_national_id = State()
    waiting_for_doc_category = State()
    waiting_for_doc_subcategory = State()
    waiting_for_attachments_opt = State()
    confirm_opt = State()
    waiting_for_payment_receipt = State()

    # =========================================================
    # State های بخش لایحه (ثبت لایحه)
    # =========================================================
    lavayeh_title = State()
    lavayeh_tracking_method = State()  # انتخاب روش: شماره پرونده یا شماره بایگانی
    lavayeh_tracking_code = State()
    lavayeh_archive_number = State()  # شماره بایگانی
    lavayeh_branch_input_method = State()  # انتخاب نحوه ورود نام شعبه
    lavayeh_branch_name = State()  # نام شعبه
    lavayeh_province = State()
    lavayeh_row_number = State()
    lavayeh_person_type = State()
    lavayeh_company_id = State()
    lavayeh_representative_type = State()
    lavayeh_national_id = State()
    lavayeh_more_persons = State()
    lavayeh_text = State()
    lavayeh_attachment_title = State()
    lavayeh_images = State()
    lavayeh_attachment_more = State()
    lavayeh_confirm = State()
    lavayeh_edit_choice = State()
    waiting_for_lavayeh_payment_receipt = State()
    lavayeh_payment_reminder_response = State()

    # =========================================================
    # State های بخش اخذ امضای الکترونیک لایحه
    # =========================================================
    lavayeh_sign_ready = State()               # آمادگی برای ارسال کد
    lavayeh_sign_person_select = State()       # انتخاب شخص برای ارسال کد
    lavayeh_sign_code_input = State()          # دریافت کد از کاربر
    lavayeh_sign_resend_prompt = State()       # سوال ارسال مجدد کد
    lavayeh_sign_later_prompt = State()        # سوال اقدام بعدی
    lavayeh_sign_wrong_code_wait = State()     # منتظر ۲۰ دقیقه بعد از کد اشتباه
    lavayeh_sign_no_action_timeout = State()   # ۶۰ دقیقه بدون اقدام

    # =========================================================
    # State های بخش اخذ امضای الکترونیک اظهارنامه
    # =========================================================
    ezhhar_sign_ready = State()               # آمادگی برای ارسال کد
    ezhhar_sign_person_select = State()       # انتخاب شخص برای ارسال کد
    ezhhar_sign_code_input = State()          # دریافت کد از کاربر
    ezhhar_sign_resend_prompt = State()       # سوال ارسال مجدد کد
    ezhhar_sign_later_prompt = State()        # سوال اقدام بعدی
    ezhhar_sign_wrong_code_wait = State()     # منتظر ۲۰ دقیقه بعد از کد اشتباه
    ezhhar_sign_no_action_timeout = State()  # ۶۰ دقیقه بدون اقدام

    # =========================================================
    # State های بخش اعلام وکالت
    # =========================================================
    ealam_vakalaht_national_id = State()
    ealam_vakalaht_more_lawyers = State()
    ealam_vakalaht_contract_number = State()
    ealam_vakalaht_more_contracts = State()
    ealam_vakalaht_stamp_amount = State()
    ealam_vakalaht_claim_type = State()
    ealam_vakalaht_claim_amount = State()
    ealam_vakalaht_stamp_type = State()
    ealam_vakalaht_text = State()
    ealam_vakalaht_attachment_title = State()
    ealam_vakalaht_images = State()
    ealam_vakalaht_attachment_more = State()
    ealam_vakalaht_confirm = State()
    ealam_vakalaht_edit_choice = State()
    waiting_for_ealam_payment_receipt = State()

    # =========================================================
    # State های بخش محاسبه تمبر مالیاتی (مستقل)
    # =========================================================
    stamp_calc_claim_type = State()
    stamp_calc_claim_amount = State()
    stamp_calc_waiting_payment = State()

    # =========================================================
    # State های بخش ثبت اظهارنامه
    # =========================================================
    # مرحله ۱: نوع شخصیت اظهارکننده
    ezhhar_declarant_person_type = State()
    ezhhar_declarant_company_id = State()
    ezhhar_declarant_representative_type = State()
    ezhhar_declarant_national_id = State()
    ezhhar_declarant_more_persons = State()

    # مرحله ۲: نوع شخصیت مخاطب
    ezhhar_addressee_person_type = State()
    ezhhar_addressee_company_id = State()
    ezhhar_addressee_company_id_no_rep = State()  # مخاطب حقوقی بدون پرسیدن کدملی نماینده
    ezhhar_addressee_representative_type = State()
    ezhhar_addressee_national_id = State()
    ezhhar_addressee_more_persons = State()

    # مرحله ۳: عنوان اظهارنامه
    ezhhar_subject = State()

    # مرحله ۴: شرح متن
    ezhhar_text = State()

    # مرحله ۵: مدارک (پیوست‌ها)
    ezhhar_attachment_title = State()
    ezhhar_images = State()
    ezhhar_attachment_images = State()
    ezhhar_attachment_more = State()

    # مرحله ۶: پیش‌نمایش و تایید
    ezhhar_confirm = State()
    ezhhar_edit_choice = State()

    # خطای استعلام ثنا در اظهارنامه — ویرایش شناسه ملی یا حذف درخواست
    ezhhar_sana_error_action = State()
    ezhhar_sana_error_new_national_id = State()

    # =========================================================
    # State های بخش ثبت دسته‌جمعی (بیش از ۵ مورد - لایحه و اظهارنامه)
    # =========================================================
    bulk_mode_select = State()      # انتخاب روش ثبت (تکی یا دسته‌جمعی سریع)
    bulk_input_method = State()     # انتخاب نوع فایل (اکسل، تصویر، متن)
    bulk_file_upload = State()      # دریافت فایل اکسل / تصویر / متن
    bulk_attachment_row = State()   # انتخاب پیوست برای هر ردیف اکسل
    bulk_attachment_title = State() # انتخاب عنوان پیوست برای ردیف جاری
    bulk_attachment_images = State() # دریافت تصاویر پیوست
    bulk_attachment_more = State()  # آیا پیوست بیشتری برای این ردیف هست؟
    bulk_confirm = State()          # تایید نهایی و صدور کد رهگیری دسته‌جمعی
    bulk_admin_pending = State()    # در انتظار تایید مدیر

    # =========================================================
    # State های بخش ابزار فایل (کاهش حجم عکس / تبدیل PDF به عکس)
    # =========================================================
    file_tools_menu = State()          # انتخاب نوع ابزار
    file_tools_waiting_image = State()  # منتظر دریافت عکس برای فشرده‌سازی
    file_tools_waiting_pdf = State()    # منتظر دریافت PDF برای تبدیل به عکس

    # =========================================================
    # State های بخش اشتراک ماهیانه
    # =========================================================
    subscription_main = State()                  # منوی اشتراک
    subscription_waiting_payment = State()       # منتظر دریافت رسید پرداخت اشتراک
    subscription_waiting_admin_review = State()   # منتظر تایید مدیر
