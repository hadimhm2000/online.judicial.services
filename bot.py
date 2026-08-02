```python
import asyncio
import logging
import socket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
# اصلاحیه معماری: استفاده از SQLite به جای MemoryStorage برای ماندگاری State ها
from aiogram.fsm.storage.sqlite import SQLiteStorage
from aiogram.types import BotCommand, ErrorEvent

from config import BOT_TOKEN, PROXY_URL, ADMIN_ID
from handlers import router
from scenarios import browser_worker
import runtime_state

# ذخیره‌سازی حالت‌ها در دیتابیس SQLite (فایل bot_state.db ساخته می‌شود)
storage = SQLiteStorage(db_path="bot_state.db")
dp = Dispatcher(storage=storage)
dp.include_router(router)
runtime_state.dp = dp


# ================= هندلر سراسری خطاها =================
@dp.error()
async def on_unhandled_error(event: ErrorEvent):
    """
    این تابع از هنگ کردن ربات جلوگیری می‌کند.
    اگر خطای پردازش نشده‌ای رخ دهد، لاگ می‌شود، به ادمین اطلاع داده می‌شود و به کاربر پیام داده می‌شود.
    """
    logging.critical(f"❌ خطای پردازش نشده: {event.exception}", exc_info=True)
    
    update = event.update
    bot = event.bot
    
    # ارسال پیام به کاربر برای جلوگیری از سکوت ربات
    try:
        if update.callback_query:
            await update.callback_query.message.answer("⚠️ یک خطای سیستمی رخ داد. لطفا مجددا تلاش کنید یا /start را بزنید.")
        elif update.message:
            await update.message.answer("⚠️ یک خطای سیستمی رخ داد. لطفا مجددا تلاش کنید یا /start را بزنید.")
    except Exception:
        pass
        
    # ارسال لاگ خطا به ادمین
    try:
        err_msg = str(event.exception)[:500]
        await bot.send_message(ADMIN_ID, f"🚨 **خطای سیستمی رخ داد:**\n`{err_msg}`", parse_mode="Markdown")
    except Exception:
        pass
        
    return True


async def main():
    # بررسی پویای دسترسی پروکسی
    proxy_active = False
    if PROXY_URL:
        try:
            clean_url = PROXY_URL.replace("http://", "").replace("https://", "")
            if "@" in clean_url:
                clean_url = clean_url.split("@")[-1]
            host, port = clean_url.split(":")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.5)
                s.connect((host, int(port)))
                proxy_active = True
        except Exception:
            logging.warning(f"⚠️ پروکسی ({PROXY_URL}) در دسترس نیست. اتصال مستقیم...")

    if proxy_active:
        logging.info(f"🔌 اتصال از طریق پروکسی: {PROXY_URL}")
        session = AiohttpSession(proxy=PROXY_URL)
    else:
        logging.info("🔌 اتصال مستقیم به سرورهای تلگرام...")
        session = AiohttpSession()

    bot = Bot(token=BOT_TOKEN, session=session)
    await bot.set_my_commands([BotCommand(command="start", description="شروع مجدد ربات / ثبت استعلام جدید")])
    await bot.delete_webhook(drop_pending_updates=True)
    
    # شروع تسک‌های پس‌زمینه
    asyncio.create_task(browser_worker(bot))

    from lavayeh_handlers import lavayeh_payment_reminder_loop
    asyncio.create_task(lavayeh_payment_reminder_loop(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
```
 