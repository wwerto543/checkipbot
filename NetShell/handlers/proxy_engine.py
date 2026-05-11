import asyncio
import re
import httpx
from aiogram import Router, types, F
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from database.db import async_session
from database.models import ProxyPool
from config import ADMIN_ID

router = Router()

# Регулярка для поиска ip:port
PROXY_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}:\d{1,5})")

# Ограничитель одновременных запросов (чтобы вписаться в 1 ГБ ОЗУ)
semaphore = asyncio.Semaphore(100)

async def check_single_proxy(proxy_str: str):
    """Проверка одного прокси: определяет тип, страну и валидность"""
    # Мы будем проверять через HTTP и SOCKS5 по очереди
    protocols = ["http://", "socks5://"]
    timeout = httpx.Timeout(10.0)
    
    async with semaphore:
        for proto in protocols:
            try:
                proxy_url = f"{proto}{proxy_str}"
                async with httpx.AsyncClient(proxies=proxy_url, timeout=timeout) as client:
                    # Проверяем на публичном API для определения IP и страны
                    response = await client.get("http://ip-api.com/json/", timeout=5.0)
                    if response.status_code == 200:
                        data = response.json()
                        return {
                            "address": proxy_str,
                            "type": proto.replace("://", ""),
                            "country": data.get("countryCode", "UN"),
                            "valid": True
                        }
            except Exception:
                continue
    return {"address": proxy_str, "valid": False}

@router.message(F.text == "🌐 Прокси Чекер")
async def proxy_menu(message: types.Message):
    await message.answer("📥 Пришли мне файл `.txt` с прокси или просто отправь их текстом в формате `ip:port`.")

@router.message(F.document | F.text)
async def handle_proxy_input(message: types.Message):
    # Игнорируем системные команды
    if message.text and message.text.startswith("/"): return
    
    input_data = ""
    if message.document:
        if not message.document.file_name.endswith(".txt"):
            return await message.answer("❌ Принимаются только .txt файлы")
        
        # Скачиваем файл в память (небольшие файлы до 20-30мб легко входят в 1гб)
        file = await message.bot.get_file(message.document.file_id)
        result = await message.bot.download_file(file.file_path)
        input_data = result.read().decode("utf-8", errors="ignore")
    else:
        input_data = message.text

    # Парсим все совпадения ip:port
    found_proxies = list(set(PROXY_RE.findall(input_data)))
    
    if not found_proxies:
        return await message.answer("❌ Прокси не найдены. Используй формат `1.2.3.4:8080`")

    status_msg = await message.answer(f"⏳ Начинаю проверку {len(found_proxies)} прокси...")

    # Запускаем асинхронную проверку всей пачки
    tasks = [check_single_proxy(p) for p in found_proxies]
    results = await asyncio.gather(*tasks)
    
    valid_proxies = [r for r in results if r["valid"]]
    
    # Сортируем по странам для кнопок
    countries = {}
    for p in valid_proxies:
        countries[p["country"]] = countries.get(p["country"], []) + [f"{p['type']}://{p['address']}"]

    # --- ТИХОЕ СОХРАНЕНИЕ В ТВОЮ БД ---
    async with async_session() as session:
        for p in valid_proxies:
            # Используем ON CONFLICT (upsert), чтобы не было ошибок дублей
            stmt = insert(ProxyPool).values(
                address=p["address"],
                proxy_type=p["type"],
                country=p["country"]
            ).on_conflict_do_nothing()
            await session.execute(stmt)
        await session.commit()

    if not valid_proxies:
        return await status_msg.edit_text("❌ Ни один прокси не прошел проверку.")

    # Формируем отчет
    report = f"✅ Проверка завершена!\n\n"
    report += f"📊 Всего найдено: {len(found_proxies)}\n"
    report += f"✅ Валидных: {len(valid_proxies)}\n"
    report += f"🌍 Стран: {len(countries)}\n\n"
    report += "Выбери страну для скачивания или забери весь список:"

    # Создаем кнопки стран
    builder = InlineKeyboardBuilder()
    for code, proxies in countries.items():
        builder.button(text=f"{code} ({len(proxies)})", callback_data=f"get_proxy:{code}")
    
    builder.button(text="📄 Весь список (TXT)", callback_data="get_proxy:all")
    builder.adjust(3) # по 3 кнопки в ряд

    # Сохраняем временные результаты в состоянии бота (через глобальную переменную для простоты при 1гб озу)
    # В идеале тут использовать Redis, но мы договорились про "всё в БД"
    # Для простоты передадим список через глобальный кэш (очистим его через 10 минут)
    global proxy_cache
    proxy_cache[message.from_user.id] = countries

    await status_msg.edit_text(report, reply_markup=builder.as_markup())

# Глобальный кэш для временного хранения результатов сессии чека
proxy_cache = {}

@router.callback_query(F.data.startswith("get_proxy:"))
async def send_filtered_proxies(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    target = callback.data.split(":")[1]
    
    if user_id not in proxy_cache:
        return await callback.answer("❌ Данные устарели, запусти чек заново.", show_alert=True)
    
    data = proxy_cache[user_id]
    
    if target == "all":
        output_list = [item for sublist in data.values() for item in sublist]
        filename = "all_proxies.txt"
    else:
        output_list = data.get(target, [])
        filename = f"proxies_{target}.txt"

    if not output_list:
        return await callback.answer("Прокси не найдены.")

    file_content = "\n".join(output_list).encode("utf-8")
    document = BufferedInputFile(file_content, filename=filename)
    
    await callback.message.answer_document(document, caption=f"Вот твои прокси ({target})")
    await callback.answer()