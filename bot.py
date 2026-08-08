import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import BOT_TOKEN, TELEGRAM_API_BASE
from handlers import router
from scenarios import browser_worker
import runtime_state

dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)
runtime_state.dp = dp


async def main():
    # سرور ایرانی مستقیم به api.telegram.org دسترسی ندارد، برای همین
    # همه‌ی درخواست‌ها از طریق Cloudflare Worker (که خودش با تلگرام حرف می‌زند)
    # رد می‌شوند. TELEGRAM_API_BASE در config.py تنظیم شده است.
    logging.info(f"🔌 اتصال از طریق Cloudflare Worker: {TELEGRAM_API_BASE}")
    custom_api_server = TelegramAPIServer.from_base(TELEGRAM_API_BASE)
    session = AiohttpSession(api=custom_api_server)

    bot = Bot(token=BOT_TOKEN, session=session)
    await bot.set_my_commands([BotCommand(command="start", description="شروع مجدد ربات / ثبت استعلام جدید")])
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(browser_worker(bot))

    from lavayeh_handlers import lavayeh_payment_reminder_loop
    asyncio.create_task(lavayeh_payment_reminder_loop(bot))

    from subscription_handlers import subscription_expiry_checker
    asyncio.create_task(subscription_expiry_checker(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
