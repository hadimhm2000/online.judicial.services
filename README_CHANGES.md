# تغییرات اعمال‌شده

## فایل‌های جدید

### `stamp_duty.py`
محاسبه تمبر مالیاتی وکیل براساس مبلغ خواسته.

### `ealam_vakalaht_handlers.py`
هندلرهای تلگرام برای فلوی مستقل اعلام وکالت (از منوی اصلی).

### `ealam_vakalaht_scenario.py`
سناریوی ثبت اعلام وکالت در سامانه ثنا.

### `stamp_calc_handlers.py`
هندلرهای محاسبه تمبر مالیاتی وکیل (مستقل، قابل دسترس از منوی اصلی).

## فایل‌های تغییر یافته

### `keyboards.py`
- اضافه شدن «اعلام وکالت» و «اعلام وکالت» به `LAVAYEH_TITLES`
- اضافه شدن «⚖️ اعلام وکالت» و «🧮 محاسبه تمبر مالیاتی وکیل» به `flow_type_kb`
- اضافه شدن کیبوردهای جدید:
  - `ealam_more_lawyers_kb`
  - `ealam_more_contracts_kb`
  - `ealam_stamp_amount_kb`
  - `ealam_claim_type_kb`
  - `ealam_stamp_type_kb`
  - `continue_kb`
  - `ealam_confirm_kb`
  - `stamp_calc_claim_type_kb`

### `states.py`
اضافه شدن state های جدید:
- `ealam_vakalaht_national_id` — دریافت کدملی وکیل
- `ealam_vakalaht_more_lawyers` — آیا وکیل دیگری هم هست؟
- `ealam_vakalaht_contract_number` — شماره قرارداد وکالت
- `ealam_vakalaht_more_contracts` — آیا قرارداد دیگری هم هست؟
- `ealam_vakalaht_stamp_amount` — مقدار تمبر
- `ealam_vakalaht_claim_type` — نوع دعوی برای محاسبه تمبر
- `ealam_vakalaht_claim_amount` — مبلغ خواسته
- `ealam_vakalaht_stamp_type` — انتخاب نوع تمبر (بدوی/تجدیدنظر/کلی)
- `ealam_vakalaht_text` — متن لایحه
- `ealam_vakalaht_attachment_title` — عنوان پیوست
- `ealam_vakalaht_images` — دریافت تصاویر
- `ealam_vakalaht_attachment_more` — آیا پیوست دیگری هست؟
- `ealam_vakalaht_confirm` — تایید نهایی
- `waiting_for_ealam_payment_receipt` — انتظار برای رسید پرداخت
- `stamp_calc_claim_type` — نوع دعوی در محاسبه تمبر مستقل
- `stamp_calc_claim_amount` — مبلغ خواسته در محاسبه تمبر مستقل
- `stamp_calc_waiting_payment` — انتظار برای رسید پرداخت محاسبه تمبر

### `lavayeh_handlers.py`
- اضافه شدن عنوان «اعلام وکالت» به لیست عناوین
- هنگام انتخاب «اعلام وکالت»، جریان خاص شروع می‌شود:
  1. کدملی وکیل
  2. آیا وکیل دیگری هم هست؟
  3. شماره قرارداد (۱۶ رقمی)
  4. مقدار تمبر (عدد / محاسبه / بدون تمبر)
  5. متن لایحه
  6. پیوست‌ها (اختیاری)

### `scenarios.py`
اضافه شدن پشتیبانی از task نوع `EALAM_VAKALAHT_SUBMIT`

### `handlers.py`
اضافه شدن include روتر `stamp_calc_router` و پشتیبانی از «محاسبه تمبر» در منوی flow_type

## فلوی اعلام وکالت در سامانه ثنا

### `ealam_vakalaht_scenario.py`

جریان ثبت در سامانه:
1. «ارایه و پیگیری لایحه» → جستجوی «اعلام و» → انتخاب اولین ردیف
2. «تقدیم لایحه»
3. پر کردن اطلاعات پرونده (شماره، ردیف، استان)
4. صحت‌سنجی
5. مرحله «ارائه کننده» → انتخاب وکیل + کدملی
6. مرحله «متن» → متن لایحه
7. ثبت موقت
8. مرحله «منضمات» → انتخاب «تصویر الکترونیک وکالت نامه»:
   - پر کردن `#txtNo` با شماره قرارداد
   - پر کردن `#txtLawyerAmount` با: `stamp_amount * 100 / 3`
   - ثبت با `#btnSaveDoc`
9. آپلود سایر پیوست‌ها (در صورت وجود)
10. آماده‌سازی → محاسبه هزینه → چاپ PDF → ارسال نتیجه

## محاسبه مبلغ `txtLawyerAmount`

فرمول: `مبلغ تمبر × 100 ÷ 3` (فقط عدد، بدون کاراکتر اضافی)

## محاسبه تمبر مستقل

- دعوی مالی: محاسبه براساس تعرفه + هزینه ۲۰۰,۰۰۰ ریال + ارسال نتیجه پس از تایید
- دعوی غیر مالی: ۲۰۰,۰۰۰ ریال به ازای هر خواسته، بدون پرداخت
- اگر ۲ ساعت رسید نیامد: پاکسازی state و اطلاع به کاربر
