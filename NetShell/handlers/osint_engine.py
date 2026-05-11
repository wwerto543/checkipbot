import shodan
import whois
import dns.resolver
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import SHODAN_API

router = Router()

# Состояния для пошагового ввода данных (FSM)
class OsintStates(StatesGroup):
    waiting_for_ip = State()
    waiting_for_domain = State()

@router.message(F.text == "🔍 OSINT Разведка")
async def osint_main_menu(message: types.Message):
    # Создаем инлайн-кнопки для выбора типа разведки
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🌐 Shodan (Анализ IP)", callback_data="osint_shodan")],
        [types.InlineKeyboardButton(text="🔍 Whois (Домен)", callback_data="osint_whois")],
        [types.InlineKeyboardButton(text="📡 DNS Записи", callback_data="osint_dns")]
    ])
    await message.answer("Выберите инструмент разведки:", reply_markup=kb)

# --- SHODAN LOGIC ---

@router.callback_query(F.data == "osint_shodan")
async def shodan_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(OsintStates.waiting_for_ip)
    await callback.message.edit_text("🎯 Отправьте IP-адрес для сканирования через Shodan:")
    await callback.answer()

@router.message(OsintStates.waiting_for_ip)
async def shodan_scan(message: types.Message, state: FSMContext):
    ip = message.text.strip()
    await state.clear()
    
    status_msg = await message.answer(f"⏳ Запрашиваю данные Shodan для {ip}...")
    
    try:
        api = shodan.Shodan(SHODAN_API)
        host = api.host(ip)

        # Формируем отчет
        res = f"📍 **Результаты Shodan для {ip}:**\n"
        res += f"🏠 **Организация:** {host.get('org', 'N/A')}\n"
        res += f"🌍 **Страна:** {host.get('country_name', 'N/A')}\n"
        res += f"📂 **Порты:** {', '.join(map(str, host['ports']))}\n\n"

        if host.get('vulns'):
            res += "⚠️ **Возможные уязвимости (CVE):**\n"
            res += "\n".join([f"• `{v}`" for v in host['vulns'][:10]]) # Лимит 10 для читабельности
        else:
            res += "✅ Известных уязвимостей в базе Shodan не найдено."

        await status_msg.edit_text(res, parse_mode="Markdown")

    except shodan.APIError as e:
        await status_msg.edit_text(f"❌ Ошибка Shodan API: {e}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Произошла ошибка: {str(e)}")

# --- WHOIS LOGIC ---

@router.callback_query(F.data == "osint_whois")
async def whois_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(OsintStates.waiting_for_domain)
    await callback.message.edit_text("🔎 Введите домен (например, example.com) для Whois-запроса:")
    await callback.answer()

@router.message(OsintStates.waiting_for_domain)
async def whois_scan(message: types.Message, state: FSMContext):
    domain = message.text.strip()
    await state.clear()
    
    status_msg = await message.answer(f"⏳ Получаю данные Whois для {domain}...")
    
    try:
        w = whois.whois(domain)
        
        res = f"📊 **Whois данные: {domain}**\n"
        res += f"🏢 **Регистратор:** {w.registrar}\n"
        res += f"📅 **Дата создания:** {w.creation_date}\n"
        res += f"⌛ **Истекает:** {w.expiration_date}\n"
        res += f"🌐 **NS-серверы:** {', '.join(w.name_servers) if w.name_servers else 'N/A'}"
        
        await status_msg.edit_text(res, parse_mode="Markdown")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка при получении Whois: {str(e)}")

# --- DNS LOGIC ---

@router.callback_query(F.data == "osint_dns")
async def dns_start(callback: types.CallbackQuery):
    await callback.message.edit_text("📡 Отправьте домен, и я выведу основные DNS-записи (A, MX, TXT).")
    # Здесь можно добавить FSM, но для краткости сделаем через хендлер ниже
    await callback.answer()

@router.message(F.text.regexp(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"))
async def dns_scan(message: types.Message):
    domain = message.text.strip()
    res = f"📡 **DNS записи для {domain}:**\n\n"
    
    record_types = ['A', 'MX', 'TXT', 'NS']
    
    for r_type in record_types:
        try:
            answers = dns.resolver.resolve(domain, r_type)
            res += f"🔹 **{r_type}:**\n"
            for rdata in answers:
                res += f"`{rdata.to_text()}`\n"
        except:
            continue
            
    if res == f"📡 **DNS записи для {domain}:**\n\n":
        await message.answer("❌ Не удалось найти DNS записи для этого домена.")
    else:
        await message.answer(res, parse_mode="Markdown")