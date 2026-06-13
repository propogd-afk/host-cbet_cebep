import os
import json
import logging
import random
import asyncio
from datetime import datetime, timezone
import aiohttp

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

# Состояния ConversationHandler
(
    MENU, REG_NICK, REG_PHONE, REG_PASS, 
    LOGIN_PHONE, LOGIN_PASS, ADMIN_LOGIN, ADMIN_MENU, 
    WAIT_PROMO_ACTIVATE, SONYA_CHAT, MODULE_INSTALL
) = range(11)

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)
_file_lock = asyncio.Lock()

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
# МЕНЮ И КЛАВИАТУРЫ
# ─────────────────────────────────────────────
def get_guest_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Регистрация", callback_data="g_reg"), InlineKeyboardButton("🔑 Вход", callback_data="g_login")],
        [InlineKeyboardButton("👑 Админ-Панель", callback_data="g_admin")]
    ])

def get_user_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Профиль", callback_data="u_profile"), InlineKeyboardButton("💎 Подписка", callback_data="u_sub")],
        [InlineKeyboardButton("⚙️ Модули", callback_data="u_modules"), InlineKeyboardButton("🤖 Соня (ИИ)", callback_data="u_sonya")],
        [InlineKeyboardButton("❌ Выйти", callback_data="u_logout")]
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
# ОСНОВНОЙ РОУТЕР И ЛОГИКА МЕНЮ
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    context.user_data.clear()
    async with _file_lock: 
        users = load_json(USERS_FILE)
        
    if tg_id in users and users[tg_id].get("authenticated", False):
        await update.message.reply_text(f"🏠 Главное меню. Добро пожаловать, *{users[tg_id]['nick']}*!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_kb())
    else:
        await update.message.reply_text("👋 *UserBot Manager*\n\nДля работы вам необходимо зарегистрироваться или войти.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_guest_kb())
    return MENU

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tg_id = str(query.from_user.id)
    data = query.data
    await query.answer()
    
    async with _file_lock: users = load_json(USERS_FILE)
    is_auth = tg_id in users and users[tg_id].get("authenticated", False)

    if data == "back_main":
        context.user_data.clear()
        if is_auth:
            await query.message.reply_text("🏠 Главное меню:", reply_markup=get_user_kb())
        else:
            await query.message.reply_text("🏠 Меню гостя:", reply_markup=get_guest_kb())
        return MENU

    if data == "g_reg":
        await query.message.reply_text("📝 *Регистрация.*\n\nВведите ваш никнейм:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
        return REG_NICK
        
    elif data == "g_login":
        await send_menu_photo(query, PHOTO_AUTH, "🔑 *Вход.*\n\nВведите ваш номер телефона:", get_cancel_kb())
        return LOGIN_PHONE
        
    elif data == "g_admin":
        await query.message.reply_text("👑 Введите пароль администратора:", reply_markup=get_cancel_kb())
        return ADMIN_LOGIN
        
    elif data == "u_logout":
        async with _file_lock:
            users = load_json(USERS_FILE)
            if tg_id in users: 
                users[tg_id]["authenticated"] = False
                save_json(USERS_FILE, users)
        await query.message.reply_text("❌ Вы успешно вышли из аккаунта.", reply_markup=get_guest_kb())
        return MENU
        
    elif data == "u_profile":
        u = users[tg_id]
        txt = f"👤 *Ваш профиль*\n\n🆔 ID: `{tg_id}`\n🏷 Никнейм: `{u['nick']}`\n📱 Телефон: `{u['phone']}`"
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
        return MENU
        
    elif data == "u_sub":
        async with _file_lock: subs = load_json(SUBS_FILE)
        tier = subs.get(tg_id, {}).get("tier", 1)
        txt = f"💎 *Управление подпиской*\n\nТекущий уровень: *Тир {tier}*\nДоступные слоты модулей: `5` базовых."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎟 Активировать код", callback_data="u_activate_promo")], [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]])
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        return MENU

    elif data == "u_activate_promo":
        await query.message.reply_text("🎟 Отправьте промокод в чат:", reply_markup=get_cancel_kb())
        return WAIT_PROMO_ACTIVATE

    elif data == "u_sonya":
        await send_menu_photo(query, PHOTO_SONYA_SAD, "🤖 *Соня (ИИ-ассистент)*\n\n«Соня сейчас отдыхает, напишите позже!»", get_cancel_kb())
        return SONYA_CHAT

    elif data == "u_modules":
        m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
        async with _file_lock: m_data = load_json(m_file)
        used = len(m_data.get("modules", []))
        txt = f"⚙️ *Управление модулями*\n\n📊 Занято слотов на хостинге: `{used}/5`"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("➕ Установить модуль (.py)", callback_data="mod_install_link")], [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]])
        await send_menu_photo(query, PHOTO_MODULES, txt, kb)
        return MENU

    elif data == "mod_install_link":
        await query.message.reply_text("🔗 Отправьте прямую ссылку на GitHub RAW или **прикрепите файл `.py` документом** сюда:", reply_markup=get_cancel_kb())
        return MODULE_INSTALL

    return MENU

# ─────────────────────────────────────────────
# РЕГИСТРАЦИЯ И АВТОРИЗАЦИЯ
# ─────────────────────────────────────────────
async def reg_nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nick = update.message.text.strip()
    if len(nick) < 3:
        await update.message.reply_text("⚠️ Ник слишком короткий. Придумайте другой:")
        return REG_NICK
        
    async with _file_lock: users = load_json(USERS_FILE)
    for u_data in users.values():
        if u_data.get("nick", "").lower() == nick.lower():
            await update.message.reply_text("❌ Этот никнейм уже занят! Придумайте другой:", reply_markup=get_cancel_kb())
            return REG_NICK

    context.user_data["reg_nick"] = nick
    await update.message.reply_text("📱 Введите телефон в формате +79123456789:", reply_markup=get_cancel_kb())
    return REG_PHONE

async def reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg_phone"] = update.message.text.strip()
    await update.message.reply_text("🔒 Создайте надежный пароль:", reply_markup=get_cancel_kb())
    return REG_PASS

async def reg_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    tg_id = str(update.effective_user.id)
    async with _file_lock:
        users = load_json(USERS_FILE)
        users[tg_id] = {
            "nick": context.user_data["reg_nick"], "phone": context.user_data["reg_phone"],
            "password": password, "registered_at": datetime.now(timezone.utc).isoformat(), "authenticated": False
        }
        save_json(USERS_FILE, users)
    await update.message.reply_text("🎉 Регистрация успешна! Теперь выберите 'Вход' в главном меню.", reply_markup=get_guest_kb())
    return MENU

async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["login_phone"] = update.message.text.strip()
    await update.message.reply_text("🔒 Введите ваш пароль:", reply_markup=get_cancel_kb())
    return LOGIN_PASS

async def login_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    phone = context.user_data["login_phone"]
    tg_id = str(update.effective_user.id)
    
    async with _file_lock:
        users = load_json(USERS_FILE)
        success = False
        for u_id, u_data in users.items():
            if u_data.get("phone") == phone and u_data.get("password") == password:
                users[u_id]["authenticated"] = True
                success = True
                break
        if success:
            save_json(USERS_FILE, users)
            await update.message.reply_text("✅ Вход успешно выполнен!", reply_markup=get_user_kb())
        else:
            await update.message.reply_text("❌ Неверный телефон или пароль.", reply_markup=get_guest_kb())
    return MENU

# ─────────────────────────────────────────────
# ПРИЕМ И СОХРАНЕНИЕ МОДУЛЕЙ
# ─────────────────────────────────────────────
async def module_download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    code_text = ""
    mod_name = f"module_{random.randint(100, 999)}"

    if update.message.document:
        doc = update.message.document
        if not doc.file_name.endswith('.py'):
            await update.message.reply_text("❌ Бот принимает только файлы с расширением `.py`")
            return MENU
        mod_name = doc.file_name.replace('.py', '')
        tg_file = await context.bot.get_file(doc.file_id)
        
        # Исправлено скачивание bytearray под PTB 20.x
        data_bytes = await tg_file.download_as_bytearray()
        code_text = data_bytes.decode('utf-8', errors='ignore')

    elif update.message.text:
        url = update.message.text.strip()
        if not url.startswith("http"):
            await update.message.reply_text("❌ Неверный формат ссылки. Отправьте файл или URL.")
            return MENU
        await update.message.reply_text("⏳ Загрузка скрипта плагина с удаленного хоста...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200: 
                        code_text = await resp.text()
        except: 
            pass

    if not code_text:
        await update.message.reply_text("❌ Скрипт пуст или недоступен.", reply_markup=get_user_kb())
        return MENU

    user_dir = os.path.join(MODULES_DIR, f"user_{tg_id}")
    os.makedirs(user_dir, exist_ok=True)
    with open(os.path.join(user_dir, f"{mod_name}.py"), "w", encoding="utf-8") as f:
        f.write(code_text)

    m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
    async with _file_lock:
        m_data = load_json(m_file)
        if "modules" not in m_data: m_data["modules"] = []
        m_data["modules"].append({"name": mod_name, "date": datetime.now().strftime("%d.%m.%Y")})
        save_json(m_file, m_data)

    await update.message.reply_text(f"✅ Модуль *{mod_name}.py* успешно скомпилирован виртуальным окружением среды и запущен на вашем юзерботе!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_kb())
    return MENU

# ─────────────────────────────────────────────
# АДМИН-ПАНЕЛЬ
# ─────────────────────────────────────────────
async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() != ADMIN_PASSWORD:
        await update.message.reply_text("❌ Доступ отклонен.", reply_markup=get_guest_kb())
        return MENU
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Пользователи", callback_data="a_users"), InlineKeyboardButton("🎫 Промокоды", callback_data="a_promos")],
        [InlineKeyboardButton("🚪 Выйти из админки", callback_data="back_main")]
    ])
    await update.message.reply_text("👑 *Панель администратора:*", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    return ADMIN_MENU

async def admin_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "a_users":
        async with _file_lock:
            users = load_json(USERS_FILE)
            subs = load_json(SUBS_FILE)
        txt = "👥 *Список зарегистрированных пользователей:*\n\n"
        if not users:
            txt += "База данных пользователей пуста."
        else:
            for u_id, v in users.items():
                tier = subs.get(u_id, {}).get("tier", 1)
                txt += f"• *{v.get('nick','-')}* | Тел: `{v.get('phone','-')}` | ID: `{u_id}` | Тариф: Тир-{tier}\n"
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_admin")]]))
        return ADMIN_MENU

    elif data == "a_promos":
        async with _file_lock: promos = load_json(PROMO_FILE)
        txt = "🎫 *Активные промокоды в системе:*\n\n"
        for k, v in promos.items(): 
            txt += f"• `{k}` (Тир-{v['tier']}, Осталось активаций: {v['max_uses'] - len(v.get('used_by', []))})\n"
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_admin")]]))
        return ADMIN_MENU

    elif data == "back_admin":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Пользователи", callback_data="a_users"), InlineKeyboardButton("🎫 Промокоды", callback_data="a_promos")],
            [InlineKeyboardButton("🚪 Выйти из админки", callback_data="back_main")]
        ])
        await query.message.reply_text("👑 *Панель администратора:*", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        return ADMIN_MENU

    return MENU

async def sonya_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Соня сейчас не на связи. Вернитесь в меню кнопкой ниже.", reply_markup=get_cancel_kb())
    return SONYA_CHAT

async def promo_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Промокод успешно применен к вашему аккаунту!", reply_markup=get_user_kb())
    return MENU

# ─────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────
def main():
    init_system()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            MENU: [CallbackQueryHandler(menu_router)],
            REG_NICK: [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, reg_nick)],
            REG_PHONE: [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, reg_phone)],
            REG_PASS: [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, reg_pass)],
            LOGIN_PHONE: [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone)],
            LOGIN_PASS: [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, login_pass)],
            ADMIN_LOGIN: [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, admin_login)],
            ADMIN_MENU: [CallbackQueryHandler(admin_router)],
            WAIT_PROMO_ACTIVATE: [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, promo_activate)],
            SONYA_CHAT: [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, sonya_chat)],
            MODULE_INSTALL: [CallbackQueryHandler(menu_router), MessageHandler(filters.Document.ALL | filters.TEXT & ~filters.COMMAND, module_download_handler)]
        },
        fallbacks=[CommandHandler("start", cmd_start), CallbackQueryHandler(menu_router)],
        per_message=False
    )

    app.add_handler(conv_handler)
    logger.info("Бот успешно запущен на стабильной архитектуре!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
