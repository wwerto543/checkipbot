import asyncio
import aiohttp
import re
import io
import time
import ssl
import json
import random
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from aiohttp_socks import ProxyConnector, ProxyType
from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("UltraProxy")

router = Router()

class ProxyStates(StatesGroup):
    waiting_for_input = State()  # Ожидание файла или текста
    configuring = State()        # Выбор страны/настроек
    processing = State()         # Процесс работы

# --- КОНФИГУРАЦИЯ ЭЛИТНОГО УРОВНЯ ---
SETTINGS = {
    "MAX_CONCURRENCY": 100,      # Потоков одновременно
    "TIMEOUT": 15,               # Секунд на ответ
    "USER_AGENTS": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ],
    "TEST_URLS": [
        "https://api.ipify.org?format=json",
        "https://httpbin.org/ip",
        "https://google.com"
    ]
}

# --- КЛАСС МОДЕЛИ ДАННЫХ ---
class ProxyModel:
    def __init__(self, raw: str):
        self.raw = raw.strip()
        self.ip = ""
        self.port = ""
        self.user = None
        self.password = None
        self.protocol = "http" # по умолчанию
        self._parse()

    def _parse(self):
        # Удаляем протокол из строки если он есть
        clean_raw = self.raw
        if "://" in self.raw:
            self.protocol = self.raw.split("://")[0].lower()
            clean_raw = self.raw.split("://")[1]

        # Парсим user:pass@ip:port
        if "@" in clean_raw:
            auth, addr = clean_raw.split("@")
            self.user, self.password = auth.split(":")
            self.ip, self.port = addr.split(":")
        else:
            self.ip, self.port = clean_raw.split(":")

    def get_url(self, force_proto: str = None) -> str:
        proto = force_proto or self.protocol
        if self.user:
            return f"{proto}://{self.user}:{self.password}@{self.ip}:{self.port}"
        return f"{proto}://{self.ip}:{self.port}"

# --- ЯДРО ВАЛИДАЦИИ ---
class ProxyValidator:
    def __init__(self):
        self.headers = {"User-Agent": random.choice(SETTINGS["USER_AGENTS"])}

    async def fetch_geo(self, ip: str) -> Dict:
        """Получение ГЕО через независимый канал"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"http://ip-api.com/json/{ip}?fields=24841", timeout=5) as r:
                    if r.status == 200:
                        return await r.json()
            except: pass
        return {"countryCode": "UN", "country": "Unknown", "isp": "Unknown", "proxy": False}

    async def check(self, proxy: ProxyModel) -> Optional[Dict]:
        """Многоуровневая проверка прокси"""
        # Проверяем последовательно через разные протоколы если не указан жестко
        protocols_to_try = [proxy.protocol] if "://" in proxy.raw else ["http", "socks5", "socks4"]
        
        for proto in protocols_to_try:
            target_url = proxy.get_url(force_proto=proto)
            start_time = time.perf_counter()
            
            try:
                connector = ProxyConnector.from_url(target_url, ssl=False)
                async with aiohttp.ClientSession(connector=connector, headers=self.headers) as session:
                    # Тест 1: Доступность внешнего API
                    async with session.get(SETTINGS["TEST_URLS"][0], timeout=SETTINGS["TIMEOUT"]) as resp:
                        if resp.status == 200:
                            latency = int((time.perf_counter() - start_time) * 1000)
                            data = await resp.json()
                            
                            # Тест 2: Проверка анонимности
                            is_elite = proxy.ip in data.get("ip", "")
                            
                            return {
                                "proxy": target_url,
                                "latency": latency,
                                "proto": proto.upper(),
                                "anonymity": "Elite" if is_elite else "Transparent",
                                "status": "Success"
                            }
            except Exception as e:
                # logger.debug(f"Failed {proto} for {proxy.ip}: {str(e)}")
                continue
        return None

# --- ГЕНЕРАТОР ИНТЕРФЕЙСА ---
class ProxyUI:
    @staticmethod
    def main_menu():
        return (
            "🛠 **NETSHELL MASTER PROXY ENGINE v6.0**\n"
            "──────────────────────────\n"
            "📥 **Ожидание входных данных...**\n\n"
            "Вы можете отправить:\n"
            "1. **Файл .txt** со списком.\n"
            "2. **Текстовое сообщение** с прокси.\n\n"
            "💡 *Форматы: ip:port, user:pass@ip:port, proto://...*"
        )

    @staticmethod
    def get_country_kb(mapping: Dict):
        kb = InlineKeyboardBuilder()
        sorted_map = sorted(mapping.items(), key=lambda x: len(x[1]), reverse=True)
        
        for code, items in sorted_map[:21]: # Лимит кнопок
            kb.button(text=f"{code} ({len(items)})", callback_data=f"upx_{code}")
        
        kb.button(text="🧨 ПРОВЕРИТЬ ВСЕ", callback_data="upx_ALL")
        kb.button(text="❌ ОТМЕНА", callback_data="upx_CANCEL")
        kb.adjust(3)
        return kb.as_markup()

# --- ОСНОВНЫЕ ОБРАБОТЧИКИ (HANDLERS) ---

@router.message(F.text == "🌐 Прокси Чекер")
async def cmd_proxy_root(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(ProxyStates.waiting_for_input)
    await message.answer(ProxyUI.main_menu(), parse_mode="Markdown")

# Обработка ТЕКСТОВОГО ввода (сообщения в чат)
@router.message(ProxyStates.waiting_for_input, F.text)
async def process_text_input(message: types.Message, state: FSMContext):
    await handle_raw_data(message.text, message, state)

# Обработка ФАЙЛОВОГО ввода
@router.message(ProxyStates.waiting_for_input, F.document)
async def process_file_input(message: types.Message, bot: Bot, state: FSMContext):
    if not message.document.file_name.endswith(('.txt', '.csv')):
        return await message.answer("❌ Поддерживаются только .txt файлы.")
    
    doc = await bot.get_file(message.document.file_id)
    content = await bot.download_file(doc.file_path)
    text = content.read().decode('utf-8', errors='ignore')
    await handle_raw_data(text, message, state)

async def handle_raw_data(text: str, message: types.Message, state: FSMContext):
    # Регулярка для извлечения прокси
    pattern = r'(?:(?:socks4|socks5|http|https)://)?(?:[\w\.-]+:[\w\.-]+@)?\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}'
    found_raw = list(set(re.findall(pattern, text)))

    if not found_raw:
        return await message.answer("❌ Прокси в тексте не обнаружены. Проверьте формат.")

    status_msg = await message.answer("🔍 **Анализ локаций (Гео-фильтр)...**")
    
    # Группировка по странам
    country_map = {}
    validator = ProxyValidator()
    
    # Разбиваем на пачки по 50 для гео-чека
    for i in range(0, len(found_raw), 50):
        batch = found_raw[i:i+50]
        tasks = []
        for p_str in batch:
            ip = re.findall(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', p_str)[0]
            tasks.append(validator.fetch_geo(ip))
        
        geo_results = await asyncio.gather(*tasks)
        for p_str, geo in zip(batch, geo_results):
            code = geo.get('countryCode', 'UN')
            if code not in country_map: country_map[code] = []
            country_map[code].append({"raw": p_str, "geo": geo})

    await state.update_data(mapping=country_map)
    await status_msg.edit_text(
        f"✅ **Данные загружены!**\nУникальных адресов: `{len(found_raw)}`.\n\n"
        "🎯 Выберите страну для начала валидации:",
        reply_markup=ProxyUI.get_country_kb(country_map)
    )
    await state.set_state(ProxyStates.configuring)

@router.callback_query(F.data.startswith("upx_"), ProxyStates.configuring)
async def process_callback(call: types.CallbackQuery, state: FSMContext):
    action = call.data.split("_")[1]
    
    if action == "CANCEL":
        await state.clear()
        return await call.message.edit_text("❌ Операция отменена.")

    data = await state.get_data()
    mapping = data.get("mapping", {})
    
    to_check = []
    if action == "ALL":
        for val in mapping.values(): to_check.extend(val)
    else:
        to_check = mapping.get(action, [])

    await call.message.edit_text(f"⚔️ **Протокол валидации запущен...**\n📍 Регион: `{action}`\n⚡️ Потоков: `{SETTINGS['MAX_CONCURRENCY']}`")
    
    # --- ЗАПУСК ДВИЖКА ПРОВЕРКИ ---
    valid_results = []
    processed = 0
    total = len(to_check)
    semaphore = asyncio.Semaphore(SETTINGS["MAX_CONCURRENCY"])
    validator = ProxyValidator()

    async def validate_task(item):
        nonlocal processed
        async with semaphore:
            proxy_obj = ProxyModel(item['raw'])
            result = await validator.check(proxy_obj)
            processed += 1
            if result:
                result.update({"geo": item['geo']})
                valid_results.append(result)
            return result

    # Создание пула задач
    tasks = [asyncio.create_task(validate_task(it)) for it in to_check]
    
    # Фоновая задача обновления статуса
    async def update_ui():
        while processed < total:
            try:
                await call.message.edit_text(
                    f"⚙️ **Идет сканирование...**\n"
                    f"📊 Прогресс: `[{processed}/{total}]`\n"
                    f"✅ Валидных: `{len(valid_results)}`"
                )
            except TelegramBadRequest: pass
            await asyncio.sleep(2.5)

    ui_task = asyncio.create_task(update_ui())
    await asyncio.gather(*tasks)
    ui_task.cancel()

    # --- ФИНАЛИЗАЦИЯ ---
    if not valid_results:
        await call.message.answer(f"⚠️ Сектор `{action}` пуст. Прокси не прошли проверку.")
    else:
        # Сортировка по пингу
        valid_results.sort(key=lambda x: x['latency'])
        
        # Генерация отчета
        timestamp = datetime.now().strftime("%H:%M:%S")
        report_text = f"🏆 **REPORT: {action} @ {timestamp}**\n──────────────────\n"
        
        file_io = io.BytesIO()
        output_lines = []
        
        for p in valid_results:
            line = f"{p['proxy']} | {p['geo']['country']} | {p['latency']}ms | {p['anonymity']} | {p['geo']['isp']}"
            output_lines.append(line)
        
        file_io.write("\n".join(output_lines).encode())
        file_io.seek(0)

        # Вывод ТОП-5 в чат
        top_5 = "\n".join([f"🔹 `{p['proxy']}` ({p['latency']}ms)" for p in valid_results[:5]])
        
        summary = (
            f"{report_text}"
            f"✅ Всего живых: `{len(valid_results)}` / `{total}`\n"
            f"⚡️ Best Ping: `{valid_results[0]['latency']}ms`\n\n"
            f"🔝 **Top 5 Speed:**\n{top_5}"
        )
        
        await call.message.answer(summary)
        
        doc = types.BufferedInputFile(file_io.read(), filename=f"NetShell_{action}_Result.txt")
        await call.message.answer_document(doc, caption=f"📁 Полный лог валидации ({len(valid_results)} шт.)")

    await state.clear()
    await call.answer()

# --- ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ (OSINT ЭЛЕМЕНТЫ) ---
# Если нужно больше кода, здесь можно добавить логику сохранения в БД PostgreSQL
# или автоматическую отправку отчета админу.
