from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from database.db import async_session
from database.models import User
from config import ADMIN_ID, CHANNEL_ID

class CheckUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        if not event.from_user:
            return

        user_id = event.from_user.id
        
        async with async_session() as session:
            # 1. Проверяем наличие пользователя в БД
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                # Регистрируем нового пользователя
                is_admin = (user_id == ADMIN_ID)
                user = User(id=user_id, username=event.from_user.username, is_admin=is_admin)
                session.add(user)
                await session.commit()
            
            # 2. Проверка на бан
            if user.is_banned:
                return await event.answer("🚫 Вы заблокированы в этом боте.")

            # 3. Проверка подписки на канал (пропускаем админа)
            if user_id != ADMIN_ID and CHANNEL_ID:
                try:
                    member = await event.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
                    if member.status in ["left", "kicked"]:
                        # Если не подписан — выдаем кнопку
                        kb = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")]
                        ])
                        return await event.answer("❌ Для использования бота необходимо подписаться на наш канал!", reply_markup=kb)
                except Exception as e:
                    print(f"Ошибка проверки подписки: {e}")

            # Обновляем счетчик запросов
            user.requests_count += 1
            await session.commit()

        return await handler(event, data)