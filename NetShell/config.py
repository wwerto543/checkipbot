import os

# Папка для хранения данных (базы GeoIP, временные файлы и т.д.)
# Хостинг требует использовать /app/data для сохранения данных между перезапусками
DATA_DIR = os.getenv('DATA_DIR', '/app/data')

# Основные токены и ID (подтягиваются из переменных окружения хостинга)
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Например, @my_channel
SHODAN_API = os.getenv("SHODAN_API")

# Настройка подключения к базе данных PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # SQLALchemy требует протокол postgresql+asyncpg для асинхронной работы
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    # Если переменная пуста, бот выдаст ошибку при старте, что логично
    print("КРИТИЧЕСКАЯ ОШИБКА: Переменная DATABASE_URL не установлена!")

# Проверка наличия папки данных (на всякий случай)
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR)
    except Exception:
        pass
