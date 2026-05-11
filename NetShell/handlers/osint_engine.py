import httpx
import shodan
import whois
import socket
from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import SHODAN_API

router = Router()

# Состояния для корректной работы FSM
class OSINTStates(StatesGroup):
    waiting_for_target = State()  # Ожидание ввода цели (IP/Домен/Ник)

# --- ГЛАВНОЕ МЕНЮ OSINT ---
@router.message(F.text == "🔍 OSINT Разведка")
async def osint_main_menu(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🌐 Поиск по IP (Shodan)", callback_data="osint_ip")
    kb.button(text="🔎 WHOIS Домена", callback_data="osint_whois")
    kb.button(text="👤 Поиск ника (Social)", callback_data="osint_nick")
    kb.button(text="🌍 DNS Записи", callback_data="osint_dns")
    kb.adjust(1)
    
    await message.answer(
        "🛰 **ЦЕНТРАЛЬНЫЙ МОДУЛЬ РАЗВЕДКИ**\n"
        "────────────────────\n"
        "Выберите вектор атаки/поиска для начала работы:",
        reply_markup=kb.as_markup()
    )

# --- ОБРАБОТКА ВЫБОРА КАТЕГОРИИ ---
@router.callback_query(F.data.startswith("osint_"))
async def start_investigation(call: types.CallbackQuery, state: FSMContext):
    action = call.data.split("_")[1]
    await state.update_data(action=action)
    
    prompts = {
        "ip": "Введите целевой **IP-адрес** для сканирования портов:",
        "whois": "Введите **домен** (напр. google.com) для получения данных владельца:",
        "nick": "Введите **никнейм** для поиска по социальным сетям:",
        "dns": "Введите **домен** для извлечения DNS-записей:"
    }
    
    await call.message.answer(f"🛠 {prompts.get(action, 'Введите данные:')}")
    await state.set_state(OSINTStates.waiting_for_target)
    await call.answer()

# --- ОСНОВНОЙ ОБРАБОТЧИК ПОИСКА ---
@router.message(OSINTStates.waiting_for_target)
async def process_osint_logic(message: types.Message, state: FSMContext):
    target = message.text.strip()
    data = await state.get_data()
    action = data.get("action")
    
    wait_msg = await message.answer(f"⏳ **Запуск протокола {action.upper()}...**\nОбъект: `{target}`")

    try:
        if action == "ip":
            # Логика Shodan
            api = shodan.Shodan(SHODAN_API)
            info = api.host(target)
            res = (f"✅ **Результаты Shodan:**\n"
                   f"📍 Страна: `{info.get('country_name', 'н/д')}`\n"
                   f"🏢 Провайдер: `{info.get('isp', 'н/д')}`\n"
                   f"🚪 Открытые порты: `{info.get('ports', [])}`")
        
        elif action == "whois":
            w = whois.whois(target)
            res = (f"✅ **Данные WHOIS:**\n"
                   f"🏢 Регистратор: `{w.registrar}`\n"
                   f"📅 Создан: `{w.creation_date}`\n"
                   f"🔚 Истекает: `{w.expiration_date}`")

        elif action == "nick":
            # Заглушка для поиска ника (Sherlock style)
            res = f"🔍 Поиск ника `{target}` запущен по 150 базам... \n(Здесь будет вывод ссылок)"
            
        else:
            res = "❌ Неизвестный метод поиска."

        await wait_msg.edit_text(res, parse_mode="Markdown")

    except Exception as e:
        await wait_msg.edit_text(f"❌ **Ошибка модуля:**\n`{str(e)}`")
    
    await state.clear() # Сбрасываем состояние, чтобы бот не ждал ввода бесконечно
