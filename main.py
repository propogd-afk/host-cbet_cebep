import os
import json
import logging
import random
import asyncio
import importlib.util
import sys
from datetime import datetime
import aiohttp

# Импортируем Telethon
from telethon import TelegramClient, events

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
from telegram.constants import ParseMode

# ─────────────────────────────────────────────
# НАСТРОЙКИ И ПУТИ К ФАЙЛАМ
# ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
ADMIN_PASSWORD = "uretracoin"

BASE_DIR = "/app"
DATA_DIR = os.path.normpath(os.path.join(BASE_DIR, "data"))
MODULES_DIR = os.path.normpath(os.path.join(BASE_DIR, "modules"))
IMAGES_DIR = os.path.normpath(os.path.join(BASE_DIR, "images"))
LOG_FILE = os.path.normpath(os.path.join(BASE_DIR, "bot.log"))

USERS_FILE = os.path.join(DATA_DIR, "users.json")
SUBS_FILE = os.path.join(DATA_DIR, "subscriptions.json")
PROMO_FILE = os.path.join(DATA_DIR, "promocodes.json")

PHOTO_AUTH = os.path.join(IMAGES_DIR, "auth.jpg")
PHOTO_MODULES = os.path.join(IMAGES_DIR, "modules.jpg")
PHOTO_SONYA_SAD = os.path.join(IMAGES_DIR, "sonya_sad.jpg")

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
_file_lock = asyncio.Lock()

# Глобальный словарь для хранения активных клиентов Telethon {tg_id: TelegramClient}
USER_BOTS = {}

# ─────────────────────────────────────────────
# РАБОТА С JSON БАЗОЙ ДАННЫХ
# ─────────────────────────────────────────────
def load_json(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка чтения {path}: {e}")
    return {}

def save_json(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка записи {path}: {e}")

def init_system():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(MODULES_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE): save_json(USERS_FILE, {})
    if not os.path.exists(SUBS_FILE): save_json(SUBS_FILE, {})
    if not os.path.exists(PROMO_FILE):
        save_json(PROMO_FILE, {"URETRACOIN": {"tier": 3, "days": 90, "max_uses": 100, "used_by": []}})

def is_user_authorized(tg_id: str) -> bool:
    """Проверяет наличие активной сессии на диске"""
    users = load_json(USERS_FILE)
    session_file = os.path.join(DATA_DIR, f"session_{tg_id}.session")
    if tg_id in users and users[tg_id].get("authenticated", False):
        if os.path.exists(session_file):
            return True
    return False

# ─────────────────────────────────────────────
# УПРАВЛЕНИЕ СЕССИЯМИ TELETHON
# ─────────────────────────────────────────────
def load_user_modules(client: TelegramClient, tg_id: str):
    """Ищет .py файлы в папке юзера и инициализирует их для Telethon"""
    user_dir = os.path.join(MODULES_DIR, f"user_{tg_id}")
    if not os.path.exists(user_dir): return
        
    for file in os.listdir(user_dir):
        if file.endswith(".py"):
            mod_name = file[:-3]
            module_path = os.path.join(user_dir, file)
            try:
                spec = importlib.util.spec_from_file_location(mod_name, module_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = module
                spec.loader.exec_module(module)
                
                # Функция привязки хендлеров под Telethon
                if hasattr(module, "init_telethon"):
                    module.init_telethon(client)
                logger.info(f"Модуль {file} успешно интегрирован в Telethon для юзера {tg_id}")
            except Exception as e:
                logger.error(f"Ошибка загрузки Telethon-модуля {file}: {e}")

async def start_user_bot(tg_id: str, api_id: int, api_hash: str):
    """Фоновый старт Telethon клиента"""
    if tg_id in USER_BOTS:
        try: await USER_BOTS[tg_id].disconnect()
        except: pass

    session_path = os.path.join(DATA_DIR, f"session_{tg_id}")
    
    # Инициализируем клиент Telethon
    client = TelegramClient(session_path, api_id, api_hash)
    
    # Загружаем кастомные обработчики пользователя
    load_user_modules(client, tg_id)
    
    await client.connect()
    if await client.is_user_authorized():
        USER_BOTS[tg_id] = client
        logger.info(f"Юзербот Telethon для ID {tg_id} запущен.")
    else:
        logger.warning(f"Сессия для ID {tg_id} найдена, но авторизация в TG не пройдена.")

# ─────────────────────────────────────────────
# МЕНЮ И КЛАВИАТУРЫ
# ─────────────────────────────────────────────
def get_guest_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Создать Юзербота (Вход)", callback_data="g_reg")],
        [InlineKeyboardButton("👑 Админ-Панель", callback_data="g_admin")]
    ])

def get_user_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Профиль", callback_data="u_profile"), InlineKeyboardButton("💎 Подписка", callback_data="u_sub")],
        [InlineKeyboardButton("⚙️ Модули", callback_data="u_modules"), InlineKeyboardButton("🤖 Соня (ИИ)", callback_data="u_sonya")],
        [InlineKeyboardButton("❌ Очистить сессию (Выход)", callback_data="u_logout")]
    ])

def get_cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="back_main")]])

async def send_menu_photo(update_or_query, photo_path, caption_text, reply_markup):
    msg = update_or_query.message if isinstance(update_or_query, Update) else update_or_query.message
    if os.path.exists(photo_path):
        try:
            with open(photo_path, 'rb') as photo:
                await msg.reply_photo(photo=photo, caption=caption_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
                return
        except Exception as e:
            logger.error(f"Ошибка отправки медиа {photo_path}: {e}")
    await msg.reply_text(caption_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

# ─────────────────────────────────────────────
# ОСНОВНОЙ РОУТЕР МЕНЮ
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    context.user_data.clear()
    
    async with _file_lock:
        is_auth = is_user_authorized(tg_id)
        users = load_json(USERS_FILE)

    if is_auth:
        if tg_id not in USER_BOTS:
            u_info = users[tg_id]
            asyncio.create_task(start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"]))
            
        await update.message.reply_text(f"🏠 *Главное меню.*\n\nДобро пожаловать назад, *{users[tg_id].get('nick', 'Пользователь')}*!\nВаш юзербот на базе Telethon активен.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_kb())
    else:
        await update.message.reply_text("👋 *UserBot Manager (Telethon SRE)*\n\nАктивных сессий не найдено. Нажмите кнопку ниже для настройки.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_guest_kb())
    return "MENU"

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tg_id = str(query.from_user.id)
    data = query.data
    await query.answer()
    
    async with _file_lock:
        is_auth = is_user_authorized(tg_id)
        users = load_json(USERS_FILE)

    if data == "back_main":
        context.user_data.clear()
        if is_auth:
            await query.message.reply_text("🏠 Главное меню:", reply_markup=get_user_kb())
        else:
            await query.message.reply_text("🏠 Меню гостя:", reply_markup=get_guest_kb())
        return "MENU"

    if data == "g_reg":
        if is_auth:
            await query.message.reply_text("⚠️ Сессия уже создана!", reply_markup=get_user_kb())
            return "MENU"
        await query.message.reply_text("📝 *Шаг 1.* Введите ваш локальный никнейм:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
        return "REG_NICK"
        
    elif data == "g_admin":
        await query.message.reply_text("👑 Введите пароль администратора:", reply_markup=get_cancel_kb())
        return "ADMIN_LOGIN"

    if not is_auth:
        await query.message.reply_text("⚠️ Сессия отсутствует.", reply_markup=get_guest_kb())
        return "MENU"

    if data == "u_logout":
        if tg_id in USER_BOTS:
            try: await USER_BOTS[tg_id].disconnect(); del USER_BOTS[tg_id]
            except: pass
        
        async with _file_lock:
            if tg_id in users:
                users[tg_id]["authenticated"] = False
                save_json(USERS_FILE, users)
                
        session_file = os.path.join(DATA_DIR, f"session_{tg_id}.session")
        if os.path.exists(session_file):
            try: os.remove(session_file)
            except: pass
            
        await query.message.reply_text("❌ Сессия стерта. Юзербот отключен от хостинга.", reply_markup=get_guest_kb())
        return "MENU"
        
    elif data == "u_profile":
        u = users[tg_id]
        status = "🟢 Запущен" if tg_id in USER_BOTS else "🔴 Остановлен / Требует перевход"
        txt = f"👤 *Ваш профиль*\n\n🆔 ID: `{tg_id}`\n🏷 Ник: `{u.get('nick')}`\n📱 Телефон: `{u.get('phone')}`\n⚡️ Движок: *Telethon*\n📊 Статус: *{status}*"
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
        return "MENU"
        
    elif data == "u_sub":
        async with _file_lock: subs = load_json(SUBS_FILE)
        tier = subs.get(tg_id, {}).get("tier", 1)
        txt = f"💎 *Управление подпиской*\n\nТекущий уровень: *Тир {tier}*"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎟 Активировать код", callback_data="u_activate_promo")], [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]])
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        return "MENU"

    elif data == "u_activate_promo":
        await query.message.reply_text("🎟 Отправьте промокод в чат:", reply_markup=get_cancel_kb())
        return "WAIT_PROMO_ACTIVATE"

    elif data == "u_sonya":
        await send_menu_photo(query, PHOTO_SONYA_SAD, "🤖 *Соня (ИИ-ассистент)*\n\n«Соня сейчас отдыхает, напишите позже!»", get_cancel_kb())
        return "SONYA_CHAT"

    elif data == "u_modules":
        m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
        async with _file_lock: m_data = load_json(m_file)
        used = len(m_data.get("modules", []))
        txt = f"⚙️ *Управление модулями*\n\n📊 Занято слотов Telethon: `{used}/5`"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("➕ Установить модуль (.py)", callback_data="mod_install_link")], [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]])
        await send_menu_photo(query, PHOTO_MODULES, txt, kb)
        return "MENU"

    elif data == "mod_install_link":
        await query.message.reply_text("🔗 Отправьте прямую ссылку на плагин или **прикрепите `.py` файл документом**:", reply_markup=get_cancel_kb())
        return "MODULE_INSTALL"

    return "MENU"

# ─────────────────────────────────────────────
# ПОШАГОВАЯ АВТОРIЗАЦИЯ В TELETHON
# ─────────────────────────────────────────────
async def reg_nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg_nick"] = update.message.text.strip()
    await send_menu_photo(update, PHOTO_AUTH, "📱 *Шаг 2.*\n\nВведите ваш номер телефона (в формате +79XXXXXXXXX):", get_cancel_kb())
    return "LOGIN_PHONE"

async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text.strip()
    await update.message.reply_text("🔑 *Шаг 3.*\n\nВведите ваш **API ID** цифрами:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
    return "LOGIN_API_ID"

async def login_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    if not val.isdigit():
        await update.message.reply_text("⚠️ Только цифры. Повторите ввод API ID:")
        return "LOGIN_API_ID"
    context.user_data["api_id"] = int(val)
    await update.message.reply_text("🔑 *Шаг 4.*\n\nВведите ваш **API HASH**:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
    return "LOGIN_API_HASH"

async def login_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    api_hash = update.message.text.strip()
    context.user_data["api_hash"] = api_hash
    
    phone = context.user_data["phone"]
    api_id = context.user_data["api_id"]

    await update.message.reply_text("⏳ Инициализация сессии Telethon...")

    session_path = os.path.join(DATA_DIR, f"session_{tg_id}")
    client = TelegramClient(session_path, api_id, api_hash)
    
    try:
        await client.connect()
        # Запрашиваем код у серверов Телеграма
        sent_code = await client.send_code_request(phone)
        context.user_data["client"] = client
        context.user_data["phone_code_hash"] = sent_code.phone_code_hash
        
        await update.message.reply_text("📩 Код отправлен разработчиками Telegram в твое приложение.\n\n**Пришли код сюда:**", reply_markup=get_cancel_kb())
        return "WAIT_CODE"
    except Exception as e:
        logger.error(f"Telethon send_code error: {e}")
        await update.message.reply_text(f"❌ Ошибка вызова API: `{e}`.\nПопробуйте снова через /start", parse_mode=ParseMode.MARKDOWN, reply_markup=get_guest_kb())
        return "MENU"

async def wait_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    code = update.message.text.strip()
    client = context.user_data.get("client")
    phone_code_hash = context.user_data.get("phone_code_hash")
    phone = context.user_data.get("phone")

    try:
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        
        async with _file_lock:
            users = load_json(USERS_FILE)
            users[tg_id] = {
                "nick": context.user_data.get("reg_nick", f"User_{tg_id[:4]}"),
                "phone": phone,
                "api_id": context.user_data["api_id"],
                "api_hash": context.user_data["api_hash"],
                "authenticated": True
            }
            save_json(USERS_FILE, users)

        USER_BOTS[tg_id] = client
        load_user_modules(client, tg_id)

        await update.message.reply_text("🎉 Успешно! Файл сессии Telethon сгенерирован и запущен в облаке.", reply_markup=get_user_kb())
        return "MENU"
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка кода: `{e}`.\nСброс. Начните заново через /start", parse_mode=ParseMode.MARKDOWN, reply_markup=get_guest_kb())
        return "MENU"

# ─────────────────────────────────────────────
# ОБРАБОТКА И УСТАНОВКА ПЛАГИНОВ
# ─────────────────────────────────────────────
async def module_download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    code_text = ""
    mod_name = f"module_{random.randint(100, 999)}"

    if update.message.document:
        doc = update.message.document
        if not doc.file_name.endswith('.py'):
            await update.message.reply_text("❌ Принимаются только `.py` скрипты.")
            return "MENU"
        mod_name = doc.file_name.replace('.py', '')
        tg_file = await context.bot.get_file(doc.file_id)
        data_bytes = await tg_file.download_as_bytearray()
        code_text = data_bytes.decode('utf-8', errors='ignore')

    if not code_text:
        await update.message.reply_text("❌ Файл пуст.", reply_markup=get_user_kb())
        return "MENU"

    user_dir = os.path.join(MODULES_DIR, f"user_{tg_id}")
    os.makedirs(user_dir, exist_ok=True)
    module_path = os.path.join(user_dir, f"{mod_name}.py")
    
    with open(module_path, "w", encoding="utf-8") as f:
        f.write(code_text)

    m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
    async with _file_lock:
        m_data = load_json(m_file)
        if "modules" not in m_data: m_data["modules"] = []
        m_data["modules"].append({"name": mod_name, "date": datetime.now().strftime("%d.%m.%Y")})
        save_json(m_file, m_data)

    # Если юзербот в сети — перезапускаем его, чтобы Telethon подтянул новый плагин
    if tg_id in USER_BOTS:
        async with _file_lock: users = load_json(USERS_FILE)
        u_info = users.get(tg_id, {})
        await start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"])
        await update.message.reply_text(f"✅ Модуль *{mod_name}.py* успешно загружен в инстанс вашего Telethon юзербота!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_kb())
    else:
        await update.message.reply_text(f"✅ Модуль *{mod_name}.py* успешно сохранен.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_kb())
        
    return "MENU"

# ─────────────────────────────────────────────
# АДМИН-ПАНЕЛЬ И СЛУЖЕБНЫЕ ХЕНДЛЕРЫ
# ─────────────────────────────────────────────
async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() != ADMIN_PASSWORD:
        await update.message.reply_text("❌ Доступ отклонен.", reply_markup=get_guest_kb())
        return "MENU"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Пользователи", callback_data="a_users"), InlineKeyboardButton("🎫 Промокоды", callback_data="a_promos")],
        [InlineKeyboardButton("🚪 Выйти из админки", callback_data="back_main")]
    ])
    await update.message.reply_text("👑 *Панель администратора:*", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    return "ADMIN_MENU"

async def admin_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "a_users":
        async with _file_lock: users = load_json(USERS_FILE)
        txt = "👥 *Список зарегистрированных пользователей:*\n\n"
        if not users:
            txt += "База данных пользователей пуста."
        else:
            for u_id, v in users.items():
                status = "🟢 ON" if u_id in USER_BOTS else "🔴 OFF"
                txt += f"• *{v.get('nick','-')}* | Тел: `{v.get('phone','-')}` | [{status}]\n"
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_admin")]]))
        return "ADMIN_MENU"

    elif data == "a_promos":
        async with _file_lock: promos = load_json(PROMO_FILE)
        txt = "🎫 *Активные промокоды в системе:*\n\n"
        for k, v in promos.items(): txt += f"• `{k}` (Тир-{v['tier']})\n"
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_admin")]]))
        return "ADMIN_MENU"

    elif data == "back_admin":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Пользователи", callback_data="a_users"), InlineKeyboardButton("🎫 Промокоды", callback_data="a_promos")],
            [InlineKeyboardButton("🚪 Выйти из админки", callback_data="back_main")]
        ])
        await update.message.reply_text("👑 *Панель администратора:*", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        return "ADMIN_MENU"

    return "MENU"

async def sonya_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Соня сейчас не на связи.", reply_markup=get_cancel_kb())
    return "SONYA_CHAT"

async def promo_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Промокод активирован!", reply_markup=get_user_kb())
    return "MENU"

# ─────────────────────────────────────────────
# АВТОЗАПУСК СЕССИЙ ПРИ СТАРТЕ СЕРВЕРА
# ─────────────────────────────────────────────
async def auto_run_existing_bots():
    users = load_json(USERS_FILE)
    for tg_id, info in users.items():
        session_file = os.path.join(DATA_DIR, f"session_{tg_id}.session")
        if info.get("authenticated") and os.path.exists(session_file):
            try:
                asyncio.create_task(start_user_bot(tg_id, int(info["api_id"]), info["api_hash"]))
            except Exception as e:
                logger.error(f"Не удалось автоматически поднять юзербота {tg_id}: {e}")

def main():
    init_system()
    
    try: loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(auto_run_existing_bots())

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            "MENU": [CallbackQueryHandler(menu_router)],
            "REG_NICK": [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, reg_nick)],
            "LOGIN_PHONE": [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone)],
            "LOGIN_API_ID": [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, login_api_id)],
            "LOGIN_API_HASH": [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, login_api_hash)],
            "WAIT_CODE": [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, wait_code)],
            "ADMIN_LOGIN": [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, admin_login)],
            "ADMIN_MENU": [CallbackQueryHandler(admin_router)],
            "WAIT_PROMO_ACTIVATE": [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, promo_activate)],
            "SONYA_CHAT": [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, sonya_chat)],
            "MODULE_INSTALL": [CallbackQueryHandler(menu_router), MessageHandler(filters.Document.ALL | filters.TEXT & ~filters.COMMAND, module_download_handler)]
        },
        fallbacks=[CommandHandler("start", cmd_start), CallbackQueryHandler(menu_router)],
        per_message=False
    )

    app.add_handler(conv_handler)
    logger.info("Бот-Менеджер и Среда выполнения Telethon запущена!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
