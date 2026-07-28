# 🔴 رفع باگ بازگشت به منوی اصلی

## مشکل اصلی

منوی اصلی در `handlers.py` با این دکوراتور ثبت شده:

```python
@router.message(Form.main_menu)
async def main_menu_handler(message, state):
    ...
```

یعنی فقط وقتی `state == Form.main_menu` باشد فعال می‌شود.

**اما** در تمام فایل‌های handler، هر جا «🔙 بازگشت به منوی اصلی» مدیریت می‌شود، فقط `state.clear()` صدا زده می‌شود که state را `None` می‌کند — بدون `state.set_state(Form.main_menu)`.

**نتیجه:** کیبورد نمایش داده می‌شود، ولی هیچ دکمه‌ای کار نمی‌کند!

---

## قانون طلایی اصلاح

هر جا این pattern وجود دارد:
```python
# ❌ WRONG
await state.clear()
await message.answer("...", reply_markup=main_menu_kb)
```

باید تبدیل شود به:
```python
# ✅ CORRECT
await state.clear()
await state.set_state(Form.main_menu)  # ← این خط الزامی است!
await message.answer("...", reply_markup=main_menu_kb)
```

---

## فایل‌ها و مکان‌های باگ

### 1️⃣ `lavayeh_handlers.py` — ۴+ مورد

جستجو کنید: `grep -n "state.clear" lavayeh_handlers.py`

هر مورد که بعدش `main_menu_kb` نشان داده می‌شود، باید `set_state` اضافه شود.

**مکان‌های کلیدی:**
- هندلر `بازگشت به منوی اصلی` در `lavayeh_title_handler`
- هندلر `بازگشت به منوی اصلی` در فلوی اعلام وکالت (هر ۴ جا)
- هندلر `بازگشت به منوی اصلی` بعد از انصراف از پرداخت

### 2️⃣ `ezhharnameh_handlers.py` — ۳ مورد

**مکان‌های کلیدی:**
- بازگشت از مرحله تایید اظهارنامه
- انصراف در هر مرحله

### 3️⃣ `stamp_calc_handlers.py` — ۱-۲ مورد

- بعد از اعلام نتیجه دعوی غیرمالی
- بعد از پرداخت موفق

**توجه:** `main_menu_kb` را به imports اضافه کنید:
```python
from keyboards import restart_kb, stamp_calc_claim_type_kb, continue_kb, back_only_kb, main_menu_kb
```

### 4️⃣ `handlers.py` — ۲+ مورد

- بعد از `process_payment_receipt` موفق
- بعد از `admin_approve_cart`

---

## اصلاح `handlers.py` — تقویت main_menu handler

**روش بهتر** برای مقاومت در برابر state=None:

```python
# ❌ فعلی (فقط Form.main_menu):
@router.message(Form.main_menu)
async def main_menu_handler(message, state):
    ...

# ✅ بهتر (StateFilter + F.text):
@router.message(
    StateFilter(Form.main_menu, None),
    F.text.in_({
        "1️⃣ استعلام لوایح، اظهارنامه، دادخواست و ...",
        "2️⃣ استعلام براساس شماره تماس",
        "3️⃣ استعلام براساس کدملی",
    })
)
async def main_menu_handler(message, state):
    await state.set_state(Form.main_menu)  # تضمین صحت state
    ...
```

---

## اسکریپت رفع خودکار

```bash
python fix_back_to_menu.py
```

---

## باگ‌های جانبی

### باگ A — `lavayeh_sign_handlers.py`
در چند جا `state.clear()` + `restart_kb` بدون `set_state`. باید `main_menu_kb` استفاده شود.

### باگ B — `stamp_calc_handlers.py` — واحد پول OCR
این خط **باید** وجود داشته باشد:
```python
expected_amount_toman = STAMP_CALC_FEE // 10  # ریال → تومان
```

### باگ C — `handlers.py` — WorkingHoursMiddleware
```python
# ❌ event.answer (ممکن است در برخی نسخه‌ها مشکل داشته باشد)
await event.answer("...")
# ✅ بهتر با parse_mode:
await event.answer("⛔️ ...", parse_mode="Markdown")
```

---

## Git Commit Message

```
fix: add state.set_state(Form.main_menu) after state.clear() in back handlers

All back-to-main-menu handlers called state.clear() without setting
state to Form.main_menu afterward. Since the main menu handler is
registered with @router.message(Form.main_menu), it only responds
when state is exactly Form.main_menu — not None.

This caused all main menu buttons to be unresponsive after using
any "back to main menu" button, until the user sent /start again.

Files: lavayeh_handlers.py, ezhharnameh_handlers.py,
       stamp_calc_handlers.py, handlers.py
```
