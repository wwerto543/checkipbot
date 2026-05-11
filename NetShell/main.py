import subprocess
import sys
import os
import asyncio
import logging
import time
from datetime import datetime

# --- [STAGE 1] КРИТИЧЕСКИЙ БУТСТРАП (УСТАНОВКА СРЕДЫ) ---
def critical_setup():
    """
    Принудительная установка зависимостей. 
    Этот блок выполняется ПЕРВЫМ, до любых импортов проекта.
    """
    required = [
        "aiogram", "sqlalchemy", "asyncpg", "httpx", 
        "shodan", "python-whois", "dnspython", "psutil"
    ]
    
    missing = []
    for pkg in required:
        try:
            if pkg == "python-whois": __import__("whois")
            elif pkg == "dnspython": __import__("dns")
            else: __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"[{datetime.now()}] >>> ВНИМАНИЕ: Среда не готова. Установка: {missing}")
        try:
            # Обновляем pip и ставим пакеты
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print(f"[{datetime.now()}] >>> Установка завершена. Перезапуск процесса...")
            # Полная перезагрузка процесса Python для очистки кэша импортов
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            print(f"КРИТИЧЕСКИЙ СБОЙ УСТАНОВКИ: {e}")
            sys.exit(1)

# Запуск установки
critical_setup()

# --- [STAGE 2] ТЕПЕРЬ ОСНОВНЫЕ ИМПОРТЫ ---
try:
    import psutil
    from aiogram import Bot, Dispatcher, types, F
    from aiogram.filters import Command
    from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    
    # Импорты проекта (теперь они не упадут)
    from config import BOT_TOKEN, ADMIN_ID, CHANNEL_ID, DATA_DIR
    import database.db as db_core
    import database.models as db_models
    from middlewares.check_sub import CheckUserMiddleware
    from handlers import proxy_engine, osint_engine, admin_panel
except ImportError as e:
    print(f"Ошибка импорта после установки: {e}")
    sys.exit(1)

# --- [STAGE 3] ЛОГИРОВАНИЕ И АРХИТЕКТУРА ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(DATA_DIR, "system.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NetShellCore")

class NetShell:
    def __init__(self):
        self.bot = Bot(
            token=BOT_TOKEN, 
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
        )
        self.dp = Dispatcher()
        self.version = "1.2.0-Stable"
        self.start_time = time.time()

    def get_uptime(self):
        delta = time.time() - self.start_time
        hours, rem = divmod(delta, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{int(hours)}ч {int(minutes)}м"

    async def initialize(self):
        """Полная подготовка всех систем бота"""
        logger.info("--- Запуск NetShell Core ---")
        
        # 1. Подключение к БД
        await db_core.init_db()
        logger.info("База данных PostgreSQL синхронизирована.")

        # 2. Регистрация Middleware
        self.dp.message.middleware(CheckUserMiddleware())

        # 3. Подключение модулей (Handlers)
        self.dp.include_router(admin_panel.router)
        self.dp.include_router(proxy_engine.router)
        self.dp.include_router(osint_engine.router)
        logger.info("Все функциональные модули загружены.")

        # --- ГЛАВНОЕ МЕНЮ ---
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            kb = ReplyKeyboardBuilder()
            kb.row(types.KeyboardButton(text="🔍 OSINT Разведка"), types.KeyboardButton(text="🌐 Прокси Чекер"))
            kb.row(types.KeyboardButton(text="🛠 Мультитул"), types.KeyboardButton(text="👤 Мой профиль"))
            if message.from_user.id == ADMIN_ID:
                kb.row(types.KeyboardButton(text="🛡 Админ-панель"))
            
            await message.answer(
                f"🛰 **NetShell Intelligence System**\n"
                f"────────────────────\n"
                f"Приветствую, оператор `{message.from_user.first_name}`.\n"
                f"Система активна и готова к работе.\n\n"
                f"**Версия:** `{self.version}`\n"
                f"**Статус:** `Secure Connection Established`",
                reply_markup=kb.as_markup(resize_keyboard=True)
            )

        # --- РАСШИРЕННЫЙ ПРОФИЛЬ ---
        @self.dp.message(F.text == "👤 Мой профиль")
        async def view_profile(message: types.Message):
            async with db_core.async_session() as session:
                from sqlalchemy import select
                stmt = select(db_models.User).where(db_models.User.id == message.from_user.id)
                res = await session.execute(stmt)
                user = res.scalar_one_or_none()
                
                if user:
                    mem = psutil.virtual_memory()
                    cpu = psutil.cpu_percent()
                    
                    profile_card = (
                        f"🗂 **КАРТОЧКА ДОСТУПА**\n"
                        f"────────────────────\n"
                        f"▫️ **ID:** `{user.id}`\n"
                        f"▫️ **Ранг:** `{'Администратор' if user.is_admin else 'Пользователь'}`\n"
                        f"▫️ **Запросов:** `{user.requests_count}`\n"
                        f"▫️ **В системе с:** `{user.reg_date.strftime('%d.%m.%Y')}`\n"
                        f"────────────────────\n"
                        f"🖥 **СИСТЕМНЫЕ РЕСУРСЫ:**\n"
                        f"▫️ **Uptime:** `{self.get_uptime()}`\n"
                        f"▫️ **CPU:** `{cpu}%` | **RAM:** `{mem.percent}%`"
                    )
                    await message.answer(profile_card)

        # --- МЕНЮ МУЛЬТИТУЛА ---
        @self.dp.message(F.text == "🛠 Мультитул")
        async def tools_menu(message: types.Message):
            ikb = InlineKeyboardBuilder()
            ikb.button(text="📝 Hash Gen", callback_data="mt_hash")
            ikb.button(text="🔐 Base64", callback_data="mt_b64")
            ikb.button(text="📡 My Network Info", callback_data="mt_net")
            ikb.adjust(2)
            
            await message.answer(
                "🛠 **Инструментальный отсек**\n"
                "Выберите утилиту для работы с данными:", 
                reply_markup=ikb.as_markup()
            )

        @self.dp.callback_query(F.data.startswith("mt_"))
        async def tools_callback(call: types.CallbackQuery):
            if call.data == "mt_net":
                await call.message.answer(f"🌐 **Транзитный IP:** `{call.message.chat.id}`\n*(Данные в разработке)*")
            else:
                await call.answer("⚠️ Модуль будет активирован в следующем патче", show_alert=True)
            await call.answer()

    async def start_polling(self):
        """Запуск бесконечного цикла получения обновлений"""
        await self.initialize()
        # Сбрасываем накопленные сообщения, пока бот был выключен
        await self.bot.delete_webhook(drop_pending_updates=True)
        logger.info(">>> NetShell ONLINE <<<")
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    netshell = NetShell()
    try:
        asyncio.run(netshell.start_polling())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Система NetShell остановлена.")
