import os  # Обязательно импортируем os, чтобы работал getenv

# Вытягиваем переменные из настроек хостинга
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
CHANNEL_ID = os.getenv("CHANNEL_ID")
SHODAN_API = os.getenv("SHODAN_API")

# Настройка БД
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    # Автоматически меняем на асинхронный драйвер
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
