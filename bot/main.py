import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import os
import logging
from bot.config import load_config
from bot.handlers import dialog



from aiogram.client.default import DefaultBotProperties

load_dotenv()

logging.basicConfig(level=logging.INFO)

async def main():
    config = load_config()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(dialog.router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
