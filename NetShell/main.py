import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from config import BOT_TOKEN
from database.db import init_db
from middlewares.check_sub import CheckUserMiddleware

# Настройка логов (важно для мониторинга ресурсов на хостинге)
logging.basicConfig(level=logging.INFO)

async def main():
    # Создаем таблицы в БД при запуске
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем наш фильтр подписки и регистрации
    dp.message.middleware(CheckUserMiddleware())

    # --- Главное меню ---
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        builder = ReplyKeyboardBuilder()
        builder.row(types.KeyboardButton(text="🔍 OSINT Разведка"))
        builder.row(types.KeyboardButton(text="🌐 Прокси Чекер"), types.KeyboardButton(text="🛠 Мультитул"))
        builder.row(types.KeyboardButton(text="👤 Мой профиль"))
        
        # Кнопка админа появится только у тебя
        from config import ADMIN_ID
        if message.from_user.id == ADMIN_ID:
            builder.row(types.KeyboardButton(text="🛡 Админ-панель"))

        await message.answer(
            f"Привет, {message.from_user.first_name}! 👋\nДобро пожаловать в мультитул пентестера.",
            reply_markup=builder.as_markup(resize_keyboard=True)
        )

    # Запуск бота
    try:
        print("Бот запущен и готов к работе...")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())