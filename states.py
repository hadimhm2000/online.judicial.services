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
    lavayeh_sign_ready = State()
    lavayeh_sign_code_input = State()
    lavayeh_sign_resend_prompt = State()
    lavayeh_sign_later_prompt = State()

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

    # =========================================================
    # State های بخش ثبت دسته‌جمعی (بیش از ۵ مورد - لایحه و اظهارنامه)
    # =========================================================
    bulk_mode_select = State()      # انتخاب روش ثبت (تکی یا دسته‌جمعی سریع)
    bulk_input_method = State()     # انتخاب نوع فایل (اکسل، تصویر، متن)
    bulk_file_upload = State()      # دریافت فایل اکسل / تصویر / متن
    bulk_confirm = State()          # تایید نهایی و صدور کد رهگیری دسته‌جمعی
