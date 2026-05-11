import subprocess
import sys
import os
import asyncio
import logging
import time
from datetime import datetime

# --- СИСТЕМА САМОВОССТАНОВЛЕНИЯ И ЗАВИСИМОСТЕЙ ---
def bootstrap():
    """Проверяет наличие библиотек и устанавливает их при отсутствии"""
    required_packages = [
        "aiogram", "sqlalchemy", "asyncpg", "httpx", 
        "shodan", "python-whois", "dnspython", "psutil"
    ]
    
    missing = []
    for pkg in required_packages:
        try:
            # Маппинг имен пакетов (некоторые импорты отличаются от pip install)
            if pkg == "python-whois": __import__("whois")
            elif pkg == "dnspython": __import__("dns")
            else: __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"[{datetime.now()}] Обнаружены отсутствующие модули: {missing}")
        print(f"[{datetime.now()}] Запуск процесса инсталляции...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print(f"[{datetime.now()}] Установка завершена успешно. Выполняю перезагрузку...")
            # Перезапускаем скрипт, чтобы Python увидел новые библиотеки
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            print(f"КРИТИЧЕСКАЯ ОШИБКА ПРИ УСТАНОВКЕ: {e}")
            sys.exit(1)

# Запускаем bootstrap перед любыми тяжелыми импортами
bootstrap()

# --- ТЕПЕРЬ ОСНОВНЫЕ ИМПОРТЫ ---
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Импорты проекта
from config import BOT_TOKEN, ADMIN_ID, CHANNEL_ID, DATA_DIR
from database.db import init_db, async_session
from database.models import User
from middlewares.check_sub import CheckUserMiddleware
from handlers import proxy_engine, osint_engine, admin_panel

# --- ГЛОБАЛЬНАЯ НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(DATA_DIR, "bot_log.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NetShellCore")

class NetShellBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
        self.dp = Dispatcher()
        self.start_time = time.time()

    async def setup_handlers(self):
        """Регистрация всех роутеров и системных команд"""
        # Подключаем Middleware
        self.dp.message.middleware(CheckUserMiddleware())
        
        # Подключаем функциональные модули
        self.dp.include_router(admin_panel.router)
        self.dp.include_router(proxy_engine.router)
        self.dp.include_router(osint_engine.router)

        # --- Базовые команды ---
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            builder = ReplyKeyboardBuilder()
            builder.button(text="🔍 OSINT Разведка")
            builder.button(text="🌐 Прокси Чекер")
            builder.button(text="🛠 Мультитул")
            builder.button(text="👤 Мой профиль")
            if message.from_user.id == ADMIN_ID:
                builder.button(text="🛡 Админ-панель")
            builder.adjust(2)

            welcome_text = (
                f"🛰 **NetShell v1.0 — Система Разведки**\n"
                f"────────────────────\n"
                f"Приветствую, `{message.from_user.first_name}`.\n\n"
                f"Бот готов к выполнению задач. Выберите нужный модуль на панели управления."
            )
            await message.answer(welcome_text, reply_markup=builder.as_markup(resize_keyboard=True))

        @self.dp.message(F.text == "👤 Мой профиль")
        async def cmd_profile(message: types.Message):
            async with async_session() as session:
                from sqlalchemy import select
                stmt = select(User).where(User.id == message.from_user.id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user: return
                
                uptime = time.time() - self.start_time
                profile_msg = (
                    f"👤 **КАРТОЧКА ПОЛЬЗОВАТЕЛЯ**\n"
                    f"────────────────────\n"
                    f"▫️ **ID:** `{user.id}`\n"
                    f"▫️ **Статус:** `{'Administrator' if user.is_admin else 'Active User'}`\n"
                    f"▫️ **Запросов:** `{user.requests_count}`\n"
                    f"▫️ **Регистрация:** `{user.reg_date.strftime('%Y-%m-%d')}`\n"
                    f"────────────────────\n"
                    f"📡 **Система:** Online ({int(uptime // 3600)}h {int((uptime % 3600) // 60)}m)"
                )
                await message.answer(profile_msg)

        @self.dp.message(F.text == "🛠 Мультитул")
        async def cmd_multitool(message: types.Message):
            kb = InlineKeyboardBuilder()
            kb.button(text="🔐 Hash Generator", callback_data="tool_hash")
            kb.button(text="🔑 Base64 Decode", callback_data="tool_b64")
            kb.button(text="🌍 My IP Info", callback_data="tool_myip")
            kb.adjust(1)
            
            await message.answer("🛠 **Инженерный отсек:**\nДополнительные утилиты для быстрой работы:", 
                                reply_markup=kb.as_markup())

        # --- Дополнительные Callback-обработчики для Мультитула ---
        @self.dp.callback_query(F.data.startswith("tool_"))
        async def tool_callbacks(callback: types.CallbackQuery):
            if callback.data == "tool_myip":
                import httpx
                res = await httpx.AsyncClient().get("https://ipapi.co/json/")
                data = res.json()
                await callback.message.answer(f"🌐 **Ваш IP:** `{data['ip']}`\n📍 **Локация:** `{data['city']}, {data['country_name']}`")
            else:
                await callback.answer("⏳ Эта функция появится в следующем обновлении!", show_alert=True)
            await callback.answer()

    async def run(self):
        """Запуск жизненного цикла бота"""
        logger.info("Инициализация базы данных...")
        await init_db()
        
        logger.info("Регистрация команд и обработчиков...")
        await self.setup_handlers()
        
        logger.info("Удаление старых вебхуков и запуск Long Polling...")
        await self.bot.delete_webhook(drop_pending_updates=True)
        
        try:
            await self.dp.start_polling(self.bot)
        except Exception as e:
            logger.critical(f"Критическая ошибка выполнения: {e}")
        finally:
            await self.bot.session.close()

if __name__ == "__main__":
    bot_app = NetShellBot()
    try:
        asyncio.run(bot_app.run())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем.")
