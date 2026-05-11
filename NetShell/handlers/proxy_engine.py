import asyncio
import httpx
import re
import io
import time
from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

router = Router()

class ProxyStates(StatesGroup):
    waiting_for_file = State()
    configuring = State()

# --- СИСТЕМНЫЕ НАСТРОЙКИ ---
PROTOCOLS = ["http://", "socks4://", "socks5://"]
GEO_API = "http://ip-api.com/json/{}?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as,query"

class ProxyAnalyzer:
    def __init__(self, proxy_url: str):
        self.proxy = proxy_url
        self.info = {"url": proxy_url, "alive": False}

    async def check(self, target_country: str = "ALL"):
        # Пытаемся определить протокол, если его нет
        protocols_to_test = PROTOCOLS if "://" not in self.proxy else [self.proxy.split("://")[0] + "://"]
        base_addr = self.proxy.split("://")[-1]

        for proto in protocols_to_test:
            full_url = f"{proto}{base_addr}"
            try:
                async with httpx.AsyncClient(proxies=full_url, timeout=10.0, follow_redirects=True) as client:
                    start = time.perf_counter()
                    # Проверка на анонимность через специальный эндпоинт
                    resp = await client.get("http://httpbin.org/get", timeout=8.0)
                    
                    if resp.status_code == 200:
                        self.info["latency"] = int((time.perf_counter() - start) * 1000)
                        self.info["alive"] = True
                        self.info["proto"] = proto.replace("://", "").upper()
                        
                        # Определяем уровень анонимности
                        origin_ip = resp.json().get("origin", "")
                        self.info["anonymity"] = "Elite" if len(origin_ip.split(",")) == 1 else "Transparent"

                        # Гео-аналитика
                        ip_clean = base_addr.split('@')[-1].split(':')[0]
                        async with httpx.AsyncClient() as geo_client:
                            geo_resp = await geo_client.get(GEO_API.format(ip_clean))
                            geo_data = geo_resp.json()
                            
                            self.info["country"] = geo_data.get("country", "Unknown")
                            self.info["code"] = geo_data.get("countryCode", "UN")
                            self.info["isp"] = geo_data.get("isp", "Unknown ISP")
                            self.info["city"] = geo_data.get("city", "Unknown")

                        # Фильтр по стране
                        if target_country != "ALL" and self.info["code"] != target_country:
                            return None
                        
                        return self.info
            except:
                continue
        return None

# --- ОБРАБОТЧИКИ ---

@router.message(F.text == "🌐 Прокси Чекер")
async def cmd_proxy(message: types.Message, state: FSMContext):
    await state.set_state(ProxyStates.waiting_for_file)
    await message.answer(
        "🛠 **NETSHELL PROXY ENGINE v4.0**\n"
        "────────────────────\n"
        "📥 **Пришлите файл .txt**\n\n"
        "Я автоматически распознаю:\n"
        "• HTTP / HTTPS / SOCKS 4-5\n"
        "• Формат IP:PORT и USER:PASS@IP:PORT\n"
        "• Любой мусор в файле будет отфильтрован."
    )

@router.message(F.document, ProxyStates.waiting_for_file)
async def process_file(message: types.Message, bot: Bot, state: FSMContext):
    file = await bot.get_file(message.document.file_id)
    content = await bot.download_file(file.file_path)
    text = content.read().decode('utf-8', errors='ignore')
    
    # Регулярка для захвата всех типов прокси
    found = re.findall(r'(?:[a-zA-Z0-9]+://)?(?:[\w\.-]+:[\w\.-]+@)?\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}', text)
    
    if not found:
        return await message.answer("❌ Прокси не обнаружены. Проверьте формат файла.")

    await state.update_data(proxies=found)
    
    kb = InlineKeyboardBuilder()
    countries = [("🇺🇸 US", "US"), ("🇷🇺 RU", "RU"), ("🇩🇪 DE", "DE"), ("🌍 ALL", "ALL")]
    for text_btn, code in countries:
        kb.button(text=text_btn, callback_data=f"check_{code}")
    kb.adjust(2)

    await message.answer(
        f"📊 **Анализ завершен:** Найдено `{len(found)}` объектов.\n\n"
        "🌍 **Выберите локацию фильтрации:**",
        reply_markup=kb.as_markup()
    )
    await state.set_state(ProxyStates.configuring)

@router.callback_query(F.data.startswith("check_"), ProxyStates.configuring)
async def run_engine(call: types.CallbackQuery, state: FSMContext):
    country = call.data.split("_")[1]
    data = await state.get_data()
    proxies = data.get("proxies")
    
    await call.message.edit_text(f"🚀 **Запуск Ultra-Engine...**\n📍 Локация: `{country}`\n⚡️ Потоков: `50`")

    valid_results = []
    sem = asyncio.Semaphore(50) # Ограничиваем нагрузку на процессор

    async def safe_check(p):
        async with sem:
            analyzer = ProxyAnalyzer(p)
            return await analyzer.check(country)

    tasks = [safe_check(p) for p in proxies]
    
    # Чтобы не "вешать" бота, обновляем прогресс каждые 5 секунд
    start_time = time.time()
    completed = 0
    for task in asyncio.as_completed(tasks):
        res = await task
        completed += 1
        if res: valid_results.append(res)
        
        if completed % 10 == 0 or completed == len(proxies):
            try:
                await call.message.edit_text(
                    f"⚙️ **Сканирование...**\n"
                    f"📈 Прогресс: `{completed}/{len(proxies)}` (`{int(completed/len(proxies)*100)}%`)\n"
                    f"✅ Найдено ({country}): `{len(valid_results)}`"
                )
            except: pass

    # Итоговый отчет
    if not valid_results:
        await call.message.answer(f"⚠️ Ни один прокси `{country}` не прошел тесты.")
    else:
        # Сортировка и генерация файла
        valid_results.sort(key=lambda x: x['latency'])
        
        output = io.BytesIO()
        file_content = ""
        for v in valid_results:
            file_content += f"{v['url']} | {v['proto']} | {v['country']} | {v['latency']}ms | {v['anonymity']}\n"
        
        output.write(file_content.encode('utf-8'))
        output.seek(0)
        
        # Красивый вывод в чат (ТОП-10)
        report = [f"🏆 **TOP-10 ВЫСОКОСКОРОСТНЫХ ({country})**\n"]
        for p in valid_results[:10]:
            report.append(f"🔹 `{p['url']}`\n ⚡️ `{p['latency']}ms` | {p['proto']} | `{p['isp'][:15]}`")

        await call.message.answer("\n".join(report))
        
        # Отправка полного файла
        document = types.BufferedInputFile(output.read(), filename=f"valid_{country}_proxies.txt")
        await call.message.answer_document(document, caption=f"📁 Полный список рабочих прокси ({len(valid_results)} шт.)")

    await state.clear()
