import os  # Вот этой строки у тебя не хватает

# Основные настройки (берутся из переменных хостинга)
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
CHANNEL_ID = os.getenv("CHANNEL_ID")
SHODAN_API = os.getenv("SHODAN_API")

# Настройка БД
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    # Заменяем для работы с асинхронным драйвером asyncpg
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
