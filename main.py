import asyncio
import logging
import threading

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, PORT
from database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def start_bot_polling():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    from bot.handlers import router
    dp.include_router(router)

    logger.info("Starting bot polling...")
    dp.run_polling(bot)


def start_web_server():
    import uvicorn
    from webapp.routes import app
    logger.info(f"Starting web server on port {PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=PORT)


async def main():
    logger.info("Initializing database...")
    await init_db()

    logger.info("Starting threads...")

    bot_thread = threading.Thread(target=start_bot_polling, daemon=True)
    bot_thread.start()

    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()

    logger.info("All services started. Running forever...")

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    asyncio.run(main())
