from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from .models import Base
from config import DATABASE_URL

# Создаем асинхронный движок
engine = create_async_engine(DATABASE_URL, echo=False)

# Создаем фабрику сессий
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    """Функция создания таблиц в базе данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)