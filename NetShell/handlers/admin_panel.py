import asyncio
import psutil
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile
from sqlalchemy import select, func
from database.db import async_session
from database.models import User, ProxyPool
from config import ADMIN_ID

router = Router()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_ban_id = State()

# Фильтр: только для админа
def is_admin(message: types.Message):
    return message.from_user.id == ADMIN_ID

@router.message(F.text == "🛡 Админ-панель", is_admin)
async def admin_main_menu(message: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [types.InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [types.InlineKeyboardButton(text="📥 Выгрузить базу прокси", callback_data="admin_export_proxy")],
        [types.InlineKeyboardButton(text="🚫 Бан по ID", callback_data="admin_ban_user")],
        [types.InlineKeyboardButton(text="🖥 Ресурсы системы", callback_data="admin_resources")]
    ])
    await message.answer("🛠 Панель управления администратора:", reply_markup=kb)

# --- СТАТИСТИКА ---
@router.callback_query(F.data == "admin_stats", is_admin)
async def admin_stats(callback: types.CallbackQuery):
    async with async_session() as session:
        users_count = await session.scalar(select(func.count(User.id)))
        proxies_count = await session.scalar(select(func.count(ProxyPool.id)))
        total_reqs = await session.scalar(select(func.sum(User.requests_count)))
        
    res = (f"📈 **Статистика бота:**\n\n"
           f"👤 Всего пользователей: `{users_count}`\n"
           f"🌐 Прокси в базе: `{proxies_count}`\n"
           f"⚡ Всего запросов: `{total_reqs or 0}`")
    await callback.message.edit_text(res, parse_mode="Markdown")
    await callback.answer()

# --- РАССЫЛКА ---
@router.callback_query(F.data == "admin_broadcast", is_admin)
async def broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.message.edit_text("📝 Введите сообщение для рассылки всем пользователям:")
    await callback.answer()

@router.message(AdminStates.waiting_for_broadcast, is_admin)
async def broadcast_exec(message: types.Message, state: FSMContext):
    async with async_session() as session:
        result = await session.execute(select(User.id))
        user_ids = result.scalars().all()

    await message.answer(f"🚀 Начинаю рассылку на {len(user_ids)} чел...")
    count = 0
    for u_id in user_ids:
        try:
            await message.copy_to(u_id)
            count += 1
            await asyncio.sleep(0.05) # Защита от флуд-контроля ТГ
        except Exception:
            continue
    
    await message.answer(f"✅ Рассылка завершена! Получили: {count} пользователей.")
    await state.clear()

# --- ВЫГРУЗКА БАЗЫ ПРОКСИ ---
@router.callback_query(F.data == "admin_export_proxy", is_admin)
async def export_proxies(callback: types.CallbackQuery):
    async with async_session() as session:
        result = await session.execute(select(ProxyPool.address, ProxyPool.proxy_type))
        proxies = result.all()
    
    if not proxies:
        return await callback.answer("База прокси пуста!", show_alert=True)
    
    # Формируем список в формате протокол://адрес
    data = "\n".join([f"{p[1]}://{p[0]}" for p in proxies])
    file = BufferedInputFile(data.encode(), filename="proxy_export_full.txt")
    
    await callback.message.answer_document(file, caption=f"📦 Полная выгрузка базы ({len(proxies)} шт.)")
    await callback.answer()

# --- БАН ПО ID ---
@router.callback_query(F.data == "admin_ban_user", is_admin)
async def ban_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_ban_id)
    await callback.message.edit_text("🆔 Введите Telegram ID пользователя для бана:")
    await callback.answer()

@router.message(AdminStates.waiting_for_ban_id, is_admin)
async def ban_exec(message: types.Message, state: FSMContext):
    try:
        target_id = int(message.text)
        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == target_id))
            user = result.scalar_one_or_none()
            if user:
                user.is_banned = True
                await session.commit()
                await message.answer(f"✅ Пользователь {target_id} заблокирован.")
            else:
                await message.answer("❌ Пользователь не найден в базе.")
    except:
        await message.answer("❌ Введите корректный числовой ID.")
    await state.clear()

# --- МОНИТОРИНГ РЕСУРСОВ ---
@router.callback_query(F.data == "admin_resources", is_admin)
async def check_resources(callback: types.CallbackQuery):
    process = psutil.Process()
    mem_info = process.memory_info().rss / 1024 / 1024 # в МБ
    cpu_usage = psutil.cpu_percent()
    
    res = (f"🖥 **Состояние сервера:**\n\n"
           f"🧠 Занято ОЗУ: `{mem_info:.2f} MB` / 1024 MB\n"
           f"📊 Загрузка CPU: `{cpu_usage}%`\n"
           f"⚙️ Потоков: `{process.num_threads()}`")
    
    await callback.message.edit_text(res, parse_mode="Markdown")
    await callback.answer()