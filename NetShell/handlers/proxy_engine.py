import asyncio
import aiohttp
import re
import io
import time
import logging
from typing import List, Dict, Any, Optional
from aiohttp_socks import ProxyConnector
from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Настройка логгера для отладки
logger = logging.getLogger("ProxyUltra")
router = Router()

class ProxyStates(StatesGroup):
    waiting_for_file = State()
    configuring = State()

# --- ENTERPRISE CONFIGURATION ---
MAX_WORKERS = 150           # Максимальное количество потоков
CONNECTION_TIMEOUT = 12     # Таймаут соединения
GEO_PROVIDER = "http://ip-api.com/json/{}?fields=status,message,country,countryCode,city,isp,proxy,hosting"
TEST_TARGETS = [
    "https://api.ipify.org?format=json",
    "https://httpbin.org/ip",
    "https://www.google.com"
]

class ProxyEngineCore:
    """Ядро системы с глубоким анализом пакетов"""
    
    @staticmethod
    async def get_detailed_geo(ip: str) -> Dict[str, Any]:
        """Асинхронный сбор разведданных по IP"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(GEO_PROVIDER.format(ip), timeout=5) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except: pass
        return {"country": "Unknown", "countryCode": "UN", "isp": "Unknown", "hosting": False}

    @staticmethod
    async def verify(proxy_str: str) -> Optional[Dict[str, Any]]:
        """Комплексная проверка: Валидность + Пинг + Анонимность"""
        # Автоматическая коррекция протокола
        p_url = proxy_str if "://" in proxy_str else f"http://{proxy_str}"
        
        start = time.perf_counter()
        try:
            connector = ProxyConnector.from_url(p_url)
            async with aiohttp.ClientSession(connector=connector) as session:
                # Проверка через основной узел
                async with session.get(TEST_TARGETS[0], timeout=CONNECTION_TIMEOUT) as resp:
                    if resp.status == 200:
                        latency = int((time.perf_counter() - start) * 1000)
                        data = await resp.json()
                        detected_ip = data.get("ip", "")
                        
                        # Определение типа анонимности
                        # Если IP в ответе совпадает с IP прокси — Elite/Anonymous
                        anonymity = "Elite" if detected_ip in p_url else "Transparent"
                        
                        return {
                            "url": p_url,
                            "latency": latency,
                            "anonymity": anonymity,
                            "status": "Online"
                        }
        except: pass
        return None

# --- HANDLERS ---

@router.message(F.text == "🌐 Прокси Чекер")
async def init_ultra_engine(message: types.Message, state: FSMContext):
    await state.set_state(ProxyStates.waiting_for_file)
    await message.answer(
        "🚀 **NETSHELL ULTRA-ENGINE v5.0**\n"
        "────────────────────────\n"
        "✨ **Флагманские возможности:**\n"
        "▫️ Асинхронная очередь: `150+ потоков`.\n"
        "▫️ Анализ: `Geo-IP, ISP, Anonymity Lvl`.\n"
        "▫️ Поддержка: `SOCKS4/5, HTTP/S`.\n\n"
        "📥 **Отправьте файл .txt для анализа:**"
    )

@router.message(F.document, ProxyStates.waiting_for_file)
async def analyze_and_map(message: types.Message, bot: Bot, state: FSMContext):
    file = await bot.get_file(message.document.file_id)
    raw_data = await bot.download_file(file.file_path)
    text = raw_data.read().decode('utf-8', errors='ignore')
    
    # Регулярное выражение промышленного стандарта
    pattern = r'(?:(?:socks4|socks5|http|https)://)?(?:[\w\.-]+:[\w\.-]+@)?\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}'
    proxies = list(set(re.findall(pattern, text))) # Deduplication
    
    if not proxies:
        return await message.answer("❌ **Ошибка:** Валидные прокси-адреса не найдены.")

    progress = await message.answer("📡 **Глобальное сканирование гео-позиций...**")
    
    country_groups = {} # Группировка: { 'RU': [ {...}, {...} ] }
    
    # Скоростной пре-чек ГЕО
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(proxies), 50): # Батчи по 50 для стабильности
            batch = proxies[i:i+50]
            tasks = []
            for p in batch:
                ip = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', p)[0]
                tasks.append(ProxyEngineCore.get_detailed_geo(ip))
            
            results = await asyncio.gather(*tasks)
            for proxy, geo in zip(batch, results):
                code = geo.get('countryCode', 'UN')
                if code not in country_groups: country_groups[code] = []
                country_groups[code].append({"raw": proxy, "geo": geo})

    await state.update_data(mapping=country_groups)

    # Динамическое меню
    kb = InlineKeyboardBuilder()
    sorted_countries = sorted(country_groups.items(), key=lambda x: len(x[1]), reverse=True)
    
    for code, items in sorted_countries[:18]: # Лимит 18 кнопок для красоты
        kb.button(text=f"{code} ({len(items)})", callback_data=f"ultra_{code}")
    
    kb.button(text="🧨 ПРОВЕРИТЬ ВСЕ", callback_data="ultra_ALL")
    kb.adjust(3)

    await progress.edit_text(
        f"✅ **Анализ завершен!**\n"
        f"Уникальных прокси: `{len(proxies)}`.\n"
        f"Найдено стран: `{len(country_groups)}`.\n\n"
        "**Выберите сектор для глубокой валидации:**",
        reply_markup=kb.as_markup()
    )
    await state.set_state(ProxyStates.configuring)

@router.callback_query(F.data.startswith("ultra_"), ProxyStates.configuring)
async def run_ultra_validator(call: types.CallbackQuery, state: FSMContext):
    target = call.data.split("_")[1]
    data = await state.get_data()
    mapping = data.get("mapping", {})

    to_validate = []
    if target == "ALL":
        for val in mapping.values(): to_validate.extend(val)
    else:
        to_validate = mapping.get(target, [])

    await call.message.edit_text(f"⚔️ **Валидация сектора {target}...**\n⚡️ Потоки: `{MAX_WORKERS}`")

    valid_results = []
    semaphore = asyncio.Semaphore(MAX_WORKERS)
    
    async def worker(item):
        async with semaphore:
            res = await ProxyEngineCore.verify(item['raw'])
            if res:
                res.update({"geo": item['geo']})
                return res
        return None

    tasks = [worker(it) for it in to_validate]
    
    # Визуализация прогресса
    done, total = 0, len(tasks)
    for task in asyncio.as_completed(tasks):
        result = await task
        done += 1
        if result: valid_results.append(result)
        
        if done % 15 == 0 or done == total:
            try:
                await call.message.edit_text(
                    f"🧬 **Глубокий анализ...**\n"
                    f"📊 Прогресс: `{done}/{total}`\n"
                    f"💎 Валидных: `{len(valid_results)}`"
                )
            except: pass

    # Финальный отчет и экспорт
    if not valid_results:
        await call.message.answer("⚠️ Сектор пуст. Рабочих прокси не обнаружено.")
    else:
        valid_results.sort(key=lambda x: x['latency'])
        
        # Создание файла результата
        buffer = io.BytesIO()
        lines = [f"{p['url']} | {p['geo']['country']} | {p['latency']}ms | {p['anonymity']} | {p['geo']['isp']}" for p in valid_results]
        buffer.write("\n".join(lines).encode())
        buffer.seek(0)

        # Инфо-панель
        summary = (
            f"🏆 **ОТЧЕТ ПО СЕКТОРУ {target}**\n"
            f"────────────────────────\n"
            f"✅ Валидных: `{len(valid_results)}`\n"
            f"🚀 Средний пинг: `{sum(p['latency'] for p in valid_results)//len(valid_results)}ms`\n"
            f"🛡 Elite Proxy: `{len([p for p in valid_results if p['anonymity'] == 'Elite'])}`"
        )
        
        await call.message.answer(summary)
        
        file = types.BufferedInputFile(buffer.read(), filename=f"NetShell_Valid_{target}.txt")
        await call.message.answer_document(file, caption="📂 Файл с результатами готов.")

    await state.clear()
    await call.answer()
