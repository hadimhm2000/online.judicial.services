"""
حالت‌های مشترک و متغیرهای زنده‌ی برنامه که چند ماژول دیگر باید همزمان بهشون
دسترسی داشته باشن (صف کارها، وضعیت لاگین، صفحه/کانتکست مرورگر).

نکته‌ی مهم برای توسعه‌ی بعدی: هر ماژول دیگه که می‌خواد sana_page یا
browser_context رو *بخونه*، باید حتماً با `import runtime_state` و
`runtime_state.sana_page` بهش دسترسی پیدا کنه، نه با
`from runtime_state import sana_page`. چون این متغیرها بعداً (داخل
browser_worker در scenarios.py) مقداردهی می‌شن؛ اگر با from...import کپی
بگیری، همیشه مقدار None رو می‌بینی، نه مقدار واقعی و به‌روز.
"""
import asyncio

job_queue: asyncio.Queue = asyncio.Queue()
login_event: asyncio.Event = asyncio.Event()

# نمونه‌ی زنده‌ی Dispatcher — در بدو اجرا داخل bot.py مقداردهی می‌شود.
# هرجای دیگر که به dp.fsm.resolve_context نیاز است، از اینجا (runtime_state.dp)
# استفاده کن، هرگز از «from bot import dp» — چون وقتی bot.py مستقیم اجرا می‌شود
# اسم ماژولش می‌شود "__main__"، و اگر جای دیگری بعداً "import bot" بزند، پایتون
# کل فایل bot.py را از نو، این‌بار با نام "bot"، اجرا می‌کند (چون در sys.modules
# نبوده). این یعنی dp دوباره ساخته می‌شود و router (که از قبل به dp اول متصل شده)
# دوباره به همان dp.include_router() می‌رسد و ارور
# "Router is already attached to <Dispatcher ...>" می‌دهد — دقیقاً همان خطایی که
# در لاگ دیدیم و باعث می‌شد شمارش منضمات و دکمه‌های تایید/رد ادمین کار نکنند.
dp = None

# این دو مقدار در ابتدای اجرا None هستن و فقط داخل browser_worker
# (در scenarios.py) یک‌بار مقداردهی می‌شن.
browser_context = None
sana_page = None

# مجموعه‌ی کاربرانی که یک درخواست لایحه فعال دارند.
active_lavayeh_users: set = set()

# دیکشنری فاکتورهای لایحه در انتظار پرداخت.
# کلید: user_id (int)
# مقدار: {
#   "invoice_time": datetime,
#   "final_fee": int,
#   "court_total": int,
#   "tracking_code": str,
#   "national_ids": str,
#   "reminder_sent": bool,
#   "blocked": bool,
# }
pending_lavayeh_payments: dict = {}

# =========================================================
# اطلاعات فرآیند اخذ امضای الکترونیک لایحه
# =========================================================
# کلید: user_id (int)
# مقدار: {
#   "tracking_code": str,          — شماره پرونده
#   "province": str,               — استان
#   "row_number": int,             — ردیف فرعی
#   "lavayeh_category": str,       — دسته لایحه برای مسیریابی سامانه
#   "persons": list,               — لیست اشخاص ارائه‌دهنده
#   "sign_sent_time": datetime,    — زمان ارسال آخرین کد امضا
#   "persons_awaiting_sign": list, — لیست کدملی‌هایی که باید کد وارد شود
#   "sign_codes_received": dict,   — {national_id: code} کدهای دریافت‌شده
#   "resend_notified": bool,       — آیا نوتیف ارسال مجدد داده شده؟
# }
pending_lavayeh_sign: dict = {}
