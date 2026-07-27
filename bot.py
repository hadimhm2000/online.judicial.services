import asyncio
import logging
import socket

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN, PROXY_URL
from handlers import router
from scenarios import browser_worker
import runtime_state

dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)
runtime_state.dp = dp


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
    asyncio.create_task(browser_worker(bot))

    from lavayeh_handlers import lavayeh_payment_reminder_loop
    asyncio.create_task(lavayeh_payment_reminder_loop(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
