import os
import json
import logging
import random
import asyncio
import importlib.util
import sys
from datetime import datetime, timezone
import aiohttp

# Импортируем Pyrogram для работы юзерботов
from pyrogram import Client

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

# Глобальный словарь для хранения активных клиентов юзерботов {tg_id: pyrogram_client}
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

# ─────────────────────────────────────────────
# ПРОВЕРКА АВТОРIЗАЦИИ (ЖЕЛЕЗОБЕТОННАЯ)
# ─────────────────────────────────────────────
def is_user_authorized(tg_id: str) -> bool:
    """Проверяет, авторизован ли юзер (есть ли запись в БД и физический файл сессии)"""
    users = load_json(USERS_FILE)
    session_file = os.path.join(DATA_DIR, f"session_{tg_id}.session")
    
    if tg_id in users and users[tg_id].get("authenticated", False):
        if os.path.exists(session_file):
            return True
    return False

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
# УПРАВЛЕНИЕ СЕССИЯМИ PYROGRAM
# ─────────────────────────────────────────────
def load_user_modules(client: Client, tg_id: str):
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
                
                if hasattr(module, "init_module"):
                    module.init_module(client)
            except Exception as e:
                logger.error(f"Ошибка загрузки модуля {file} для юзера {tg_id}: {e}")

async def start_user_bot(tg_id: str, api_id: int, api_hash: str):
    """Фоновый запуск клиента Pyrogram для юзера"""
    if tg_id in USER_BOTS:
        try: await USER_BOTS[tg_id].stop()
        except: pass

    session_path = os.path.join(DATA_DIR, f"session_{tg_id}")
    client = Client(session_path, api_id=api_id, api_hash=api_hash, workdir=DATA_DIR)
    
    load_user_modules(client, tg_id)
    await client.start()
    USER_BOTS[tg_id] = client
    logger.info(f"Юзербот для ID {tg_id} успешно поднят.")

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
        # Если сессия есть, но почему-то упал процесс клиента (например после перезагрузки сервера) — поднимаем
        if tg_id not in USER_BOTS:
            u_info = users[tg_id]
            asyncio.create_task(start_user_bot(tg_id, u_info["api_id"], u_info["api_hash"]))
            
        await update.message.reply_text(f"🏠 *Главное меню.*\n\nДобро пожаловать назад, *{users[tg_id].get('nick', 'Пользователь')}*!\nВаш юзербот активен.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_kb())
    else:
        await update.message.reply_text("👋 *UserBot Manager*\n\nУ вас нет активных сессий на нашем хостинге. Нажмите кнопку ниже, чтобы привязать аккаунт.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_guest_kb())
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

    # ВЕТКА ДЛЯ ГОСТЕЙ (НОВАЯ РЕГИСТРАЦИЯ)
    if data == "g_reg":
        if is_auth:
            await query.message.reply_text("⚠️ У вас уже есть активная сессия юзербота!", reply_markup=get_user_kb())
            return "MENU"
        await query.message.reply_text("📝 *Шаг 1.* Придумайте ваш локальный никнейм:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
        return "REG_NICK"
        
    elif data == "g_admin":
        await query.message.reply_text("👑 Введите пароль администратора:", reply_markup=get_cancel_kb())
        return "ADMIN_LOGIN"

    # ВЕТКА ДЛЯ АВТОРИЗОВАННЫХ ПОЛЬЗОВАТЕЛЕЙ
    if not is_auth:
        await query.message.reply_text("⚠️ Сессия не найдена. Пожалуйста, пройдите регистрацию.", reply_markup=get_guest_kb())
        return "MENU"

    if data == "u_logout":
        # Полная очистка: останавливаем клиент и удаляем файл сессии
        if tg_id in USER_BOTS:
            try: await USER_BOTS[tg_id].stop(); del USER_BOTS[tg_id]
            except: pass
        
        async with _file_lock:
            if tg_id in users:
                users[tg_id]["authenticated"] = False
                save_json(USERS_FILE, users)
                
        session_file = os.path.join(DATA_DIR, f"session_{tg_id}.session")
        if os.path.exists(session_file):
            try: os.remove(session_file)
            except: pass
            
        await query.message.reply_text("❌ Сессия удалена с хостинга. Юзербот выключен.", reply_markup=get_guest_kb())
        return "MENU"
        
    elif data == "u_profile":
        u = users[tg_id]
        status = "🟢 Запущен" if tg_id in USER_BOTS else "🔴 Спит / Инициализация"
        txt = f"👤 *Ваш профиль*\n\n🆔 ID: `{tg_id}`\n🏷 Ник: `{u.get('nick')}`\n📱 Телефон: `{u.get('phone')}`\n⚡️ Статус на сервере: *{status}*"
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
        return "MENU"
        
    elif data == "u_sub":
        async with _file_lock: subs = load_json(SUBS_FILE)
        tier = subs.get(tg_id, {}).get("tier", 1)
        txt = f"💎 *Управление подпиской*\n\nТекущий уровень: *Тир {tier}*\nДоступные слоты модулей: `5` базовых."
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
        txt = f"⚙️ *Управление модулями*\n\n📊 Занято слотов на хостинге: `{used}/5`"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("➕ Установить модуль (.py)", callback_data="mod_install_link")], [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]])
        await send_menu_photo(query, PHOTO_MODULES, txt, kb)
        return "MENU"

    elif data == "mod_install_link":
        await query.message.reply_text("🔗 Отправьте прямую ссылку на GitHub RAW или **прикрепите файл `.py` документом** сюда:", reply_markup=get_cancel_kb())
        return "MODULE_INSTALL"

    return "MENU"

# ─────────────────────────────────────────────
# ПОШАГОВАЯ ЦЕПОЧКА РЕГИСТРАЦИИ (ТОЛЬКО ДЛЯ НОВЫХ)
# ─────────────────────────────────────────────
async def reg_nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nick = update.message.text.strip()
    if len(nick) < 3:
        await update.message.reply_text("⚠️ Ник слишком короткий. Придумайте другой:")
        return "REG_NICK"
    context.user_data["reg_nick"] = nick
    await send_menu_photo(update, PHOTO_AUTH, "📱 *Шаг 2.*\n\nВведите номер телефона вашего Telegram аккаунта (в формате +79XXXXXXXXX):", get_cancel_kb())
    return "LOGIN_PHONE"

async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text.strip()
    await update.message.reply_text("🔑 *Шаг 3.*\n\nВведите ваш **API ID** (полученный на my.telegram.org):", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
    return "LOGIN_API_ID"

async def login_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.strip().isdigit():
        await update.message.reply_text("⚠️ API ID должен состоять только из цифр. Повторите ввод:")
        return "LOGIN_API_ID"
    context.user_data["api_id"] = int(update.message.text.strip())
    await update.message.reply_text("🔑 *Шаг 4.*\n\nВведите ваш **API HASH**:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
    return "LOGIN_API_HASH"

async def login_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    api_hash = update.message.text.strip()
    context.user_data["api_hash"] = api_hash
    
    phone = context.user_data["phone"]
    api_id = context.user_data["api_id"]

    await update.message.reply_text("⏳ Подключаемся к серверам Telegram и отправляем запрос кода...")

    session_path = os.path.join(DATA_DIR, f"session_{tg_id}")
    client = Client(session_path, api_id=api_id, api_hash=api_hash, workdir=DATA_DIR)
    
    try:
        await client.connect()
        code_hash = await client.send_code(phone)
        context.user_data["client"] = client
        context.user_data["code_hash"] = code_hash
        
        await update.message.reply_text("📩 Telegram прислал код подтверждения в ваши официальные уведомления.\n\n**Введите полученный код сюда:**", reply_markup=get_cancel_kb())
        return "WAIT_CODE"
    except Exception as e:
        logger.error(f"Ошибка отправки кода: {e}")
        await update.message.reply_text(f"❌ Не удалось отправить код.\nОшибка: `{e}`\nПопробуйте заново через /start", parse_mode=ParseMode.MARKDOWN, reply_markup=get_guest_kb())
        return "MENU"

async def wait_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    code = update.message.text.strip()
    client = context.user_data.get("client")
    code_hash = context.user_data.get("code_hash")
    phone = context.user_data.get("phone")

    try:
        await client.sign_in(phone, code_hash.phone_code_hash, code)
        
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

        await update.message.reply_text("🎉 Авторизация успешна! Сессия создана. Ваш юзербот теперь круглосуточно работает на хостинге.", reply_markup=get_user_kb())
        return "MENU"
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка проверки кода: `{e}`.\nНачните заново через команду /start", parse_mode=ParseMode.MARKDOWN, reply_markup=get_guest_kb())
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
            await update.message.reply_text("❌ Поддерживаются только `.py` скрипты.")
            return "MENU"
        mod_name = doc.file_name.replace('.py', '')
        tg_file = await context.bot.get_file(doc.file_id)
        data_bytes = await tg_file.download_as_bytearray()
        code_text = data_bytes.decode('utf-8', errors='ignore')

    if not code_text:
        await update.message.reply_text("❌ Ошибка: скрипт пуст.", reply_markup=get_user_kb())
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

    # Перезапускаем сессию, чтобы применить новый модуль «на лету»
    if tg_id in USER_BOTS:
        async with _file_lock: users = load_json(USERS_FILE)
        u_info = users.get(tg_id, {})
        await start_user_bot(tg_id, u_info["api_id"], u_info["api_hash"])
        await update.message.reply_text(f"✅ Модуль *{mod_name}.py* успешно загружен и интегрирован в активную сессию вашего юзербота!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_kb())
    else:
        await update.message.reply_text(f"✅ Модуль *{mod_name}.py* сохранен на сервере.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_kb())
        
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
    await update.message.reply_text("🤖 Соня сейчас не на связи. Вернитесь в меню кнопкой ниже.", reply_markup=get_cancel_kb())
    return "SONYA_CHAT"

async def promo_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Промокод успешно применен к вашему аккаунту!", reply_markup=get_user_kb())
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
                asyncio.create_task(start_user_bot(tg_id, info["api_id"], info["api_hash"]))
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
    logger.info("Бот-Менеджер и Среда выполнения юзерботов запущена!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
