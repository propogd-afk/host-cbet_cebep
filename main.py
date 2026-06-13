import os
import json
import logging
import shutil
import asyncio
from datetime import datetime, timedelta, timezone
import aiohttp

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
from telegram.constants import ParseMode

# ─────────────────────────────────────────────
# НАСТРОЙКИ И ПУТИ
# ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
ADMIN_PASSWORD = "uretracoin"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODULES_DIR = os.path.join(BASE_DIR, "modules")
LOG_FILE = os.path.join(BASE_DIR, "bot.log")

USERS_FILE = os.path.join(DATA_DIR, "users.json")
SUBS_FILE = os.path.join(DATA_DIR, "subscriptions.json")
PROMO_FILE = os.path.join(DATA_DIR, "promocodes.json")
RANKS_FILE = os.path.join(DATA_DIR, "user_ranks.json")

PHOTO_AUTH = os.path.join(BASE_DIR, "images", "auth.jpg")
PHOTO_MODULES = os.path.join(BASE_DIR, "images", "modules.jpg")
PHOTO_SONYA_SAD = os.path.join(BASE_DIR, "images", "sonya_sad.jpg")
PHOTO_SONYA_HAPPY = os.path.join(BASE_DIR, "images", "sonya_happy.jpg")

# Состояния
(
    REG_NICK, REG_PHONE, REG_PASS, 
    LOGIN_PHONE, LOGIN_PASS, 
    ADMIN_LOGIN, ADMIN_MENU, ADMIN_PROMO_GEN, ADMIN_SPAM,
    WAIT_PROMO_ACTIVATE, SONYA_CHAT, MODULE_INSTALL
) = range(12)

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# ПОТОКОБЕЗОПАСНЫЙ И АСИНХРОННЫЙ ДОСТУП К ФАЙЛАМ
# ─────────────────────────────────────────────
_file_lock = asyncio.Lock()

def load_json(path: str) -> dict:
    try:
        if os.path.exists(path):
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
    os.makedirs(os.path.join(BASE_DIR, "images"), exist_ok=True)
    
    if not os.path.exists(USERS_FILE): save_json(USERS_FILE, {})
    if not os.path.exists(SUBS_FILE): save_json(SUBS_FILE, {})
    if not os.path.exists(RANKS_FILE): save_json(RANKS_FILE, {})
    if not os.path.exists(PROMO_FILE):
        save_json(PROMO_FILE, {
            "COFFEETIME": {"tier": 2, "days": 30, "max_uses": 100, "used_by": []},
            "NEWBIE_2026": {"tier": 2, "days": 30, "max_uses": 100, "used_by": []},
            "GETSTARTED": {"tier": 2, "days": 30, "max_uses": 100, "used_by": []},
            "MIDNIGHT_CODER": {"tier": 3, "days": 90, "max_uses": 100, "used_by": []},
            "URETRACOIN": {"tier": 3, "days": 90, "max_uses": 100, "used_by": []},
            "GHOST_MODE": {"tier": 3, "days": 90, "max_uses": 100, "used_by": []},
            "NEVER_SLEEP": {"tier": 4, "days": 365, "max_uses": 100, "used_by": []},
            "TELEGRAM_GOD": {"tier": 4, "days": 365, "max_uses": 100, "used_by": []},
            "THE_ONE_RING": {"tier": 4, "days": 365, "max_uses": 100, "used_by": []},
        })

# ─────────────────────────────────────────────
# КОНФИГУРАЦИЯ РАНГОВ И ТАРИФОВ
# ─────────────────────────────────────────────
SUBS_CONFIG = {
    1: {"name": "Пробная", "days": 10, "modules": 3, "private": 0},
    2: {"name": "Базовый", "days": 30, "modules": 5, "private": 0},
    3: {"name": "Премиум", "days": 90, "modules": 7, "private": 1},
    4: {"name": "VIP", "days": 365, "modules": 20, "private": 3}
}

RANKS_CONFIG = [
    {"level": 6, "name": "Легенда", "days": 730, "bonus": 20},
    {"level": 5, "name": "Мастер", "days": 365, "bonus": 10},
    {"level": 4, "name": "Эксперт", "days": 180, "bonus": 5},
    {"level": 3, "name": "Продвинутый", "days": 90, "bonus": 3},
    {"level": 2, "name": "Активный", "days": 30, "bonus": 2},
    {"level": 1, "name": "Пользователь", "days": 7, "bonus": 1},
    {"level": 0, "name": "Новичок", "days": 0, "bonus": 0}
]

async def update_and_get_rank(tg_idStr: str) -> dict:
    async with _file_lock:
        ranks = load_json(RANKS_FILE)
        if tg_idStr not in ranks:
            ranks[tg_idStr] = {
                "rank": 0,
                "joined_at": datetime.now(timezone.utc).isoformat(),
                "bonus_modules": 0
            }
            save_json(RANKS_FILE, ranks)
            return ranks[tg_idStr]
        
        joined_at = datetime.fromisoformat(ranks[tg_idStr]["joined_at"])
        days_passed = (datetime.now(timezone.utc) - joined_at).days
        
        current_rank = RANKS_CONFIG[-1]
        for r in RANKS_CONFIG:
            if days_passed >= r["days"]:
                current_rank = r
                break
                
        if current_rank["level"] > ranks[tg_idStr]["rank"]:
            ranks[tg_idStr]["rank"] = current_rank["level"]
            ranks[tg_idStr]["bonus_modules"] = current_rank["bonus"]
            save_json(RANKS_FILE, ranks)
            
        return ranks[tg_idStr]

async def get_sub_info(tg_id_str: str) -> dict:
    async with _file_lock:
        subs = load_json(SUBS_FILE)
        if tg_id_str not in subs:
            expires = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
            subs[tg_id_str] = {"tier": 1, "expires": expires}
            save_json(SUBS_FILE, subs)
            
        sub = subs[tg_id_str]
        expires_dt = datetime.fromisoformat(sub["expires"])
        
        if datetime.now(timezone.utc) > expires_dt:
            sub["tier"] = 1
            sub["expires"] = (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat()
            save_json(SUBS_FILE, subs)
            expires_dt = datetime.fromisoformat(sub["expires"])
            
        days_left = (expires_dt - datetime.now(timezone.utc)).days
        cfg = SUBS_CONFIG[sub["tier"]]
        
        return {
            "tier": sub["tier"],
            "name": cfg["name"],
            "days_left": max(0, days_left),
            "expires": expires_dt.strftime("%d.%m.%Y"),
            "base_modules": cfg["modules"],
            "private_slots": cfg["private"]
        }

# ─────────────────────────────────────────────
# КЛАВИАТУРЫ
# ─────────────────────────────────────────────
def get_guest_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Регистрация", callback_data="g_reg"),
         InlineKeyboardButton("🔑 Вход", callback_data="g_login")],
        [InlineKeyboardButton("👑 Админ-Панель", callback_data="g_admin")]
    ])

def get_user_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Профиль", callback_data="u_profile"),
         InlineKeyboardButton("💎 Подписка", callback_data="u_sub")],
        [InlineKeyboardButton("⚙️ Модули", callback_data="u_modules"),
         InlineKeyboardButton("🤖 Соня (помощник)", callback_data="u_sonya")],
        [InlineKeyboardButton("👑 Админ", callback_data="g_admin"),
         InlineKeyboardButton("❌ Выйти", callback_data="u_logout")]
    ])

def get_cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="back_main")]])

# ─────────────────────────────────────────────
# ХЕНДЛЕРЫ И РОУТИНГ МЕНЮ
# ─────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    context.user_data.clear()
    
    async with _file_lock:
        users = load_json(USERS_FILE)
    
    if tg_id in users and users[tg_id].get("authenticated", False):
        await update.message.reply_text(
            f"🏠 Главное меню проекта. Добро пожаловать, *{users[tg_id]['nick']}*!",
            parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_kb()
        )
    else:
        await update.message.reply_text(
            "👋 *UserBot Manager*\n\nДля работы с хостингом модулей вам необходимо зарегистрироваться или авторизоваться.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=get_guest_kb()
        )
    return ConversationHandler.END

async def inline_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tg_id = str(query.from_user.id)
    data = query.data
    await query.answer()
    
    async with _file_lock:
        users = load_json(USERS_FILE)
    is_auth = tg_id in users and users[tg_id].get("authenticated", False)
    
    if data == "back_main":
        context.user_data.clear()
        if is_auth:
            await query.message.reply_text("🏠 Вы вернулись в главное меню.", reply_markup=get_user_kb())
        else:
            await query.message.reply_text("🏠 Главное меню гостя:", reply_markup=get_guest_kb())
        try: await query.message.delete()
        except: pass
        return ConversationHandler.END

    if data == "g_reg":
        if is_auth: return ConversationHandler.END
        await query.message.reply_text("📝 *Начало регистрации.*\n\nВведите ваш желаемый никнейм (от 3 до 32 символов):", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
        return REG_NICK
        
    elif data == "g_login":
        if is_auth: return ConversationHandler.END
        if os.path.exists(PHOTO_AUTH):
            await query.message.reply_photo(photo=open(PHOTO_AUTH, 'rb'), caption="🔑 *Вход в систему.*\n\nВведите ваш номер телефона:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
        else:
            await query.message.reply_text("🔑 *Вход в систему.*\n\nВведите ваш номер телефона:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
        return LOGIN_PHONE
        
    elif data == "g_admin":
        await query.message.reply_text("👑 Введите секретный пароль администратора:", reply_markup=get_cancel_kb())
        return ADMIN_LOGIN
        
    elif data == "u_logout":
        async with _file_lock:
            users = load_json(USERS_FILE)
            if tg_id in users:
                users[tg_id]["authenticated"] = False
                save_json(USERS_FILE, users)
        await query.message.reply_text("❌ Вы вышли из аккаунта.", reply_markup=get_guest_kb())
        return ConversationHandler.END
        
    elif data == "u_profile":
        r_info = await update_and_get_rank(tg_id)
        user = users[tg_id]
        r_names = {0:"Новичок", 1:"Пользователь", 2:"Активный", 3:"Продвинутый", 4:"Эксперт", 5:"Мастер", 6:"Легенда"}
        
        text = (
            f"👤 *Ваш профиль*\n\n"
            f"🆔 Telegram ID: `{tg_id}`\n"
            f"🏷 Ник: `{user['nick']}`\n"
            f"📱 Телефон: `{user['phone']}`\n"
            f"📊 Ранг: *{r_names.get(r_info['rank'], 'Новичок')}*\n"
            f"➕ Бонусных слотов: `+{r_info['bonus_modules']}`\n"
            f"📅 Регистрация: `{user['registered_at'][:10]}`"
        )
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ В меню", callback_data="back_main")]]))
        
    elif data == "u_sub":
        s_info = await get_sub_info(tg_id)
        text = (
            f"💎 *Управление подпиской*\n\n"
            f"Текущий уровень: *{s_info['name']}*\n"
            f"Осталось дней: `{s_info['days_left']}`\n"
            f"Дата окончания: `{s_info['expires']}`\n"
            f"Слоты модулей: `{s_info['base_modules']}` базовых\n"
            f"Приватные слоты: `{s_info['private_slots']}`"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎟 Активировать промокод", callback_data="u_activate_promo")],
            [InlineKeyboardButton("◀️ В меню", callback_data="back_main")]
        ])
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        
    elif data == "u_activate_promo":
        await query.message.reply_text("🎟 Отправьте промокод текстом в чат:", reply_markup=get_cancel_kb())
        return WAIT_PROMO_ACTIVATE

    elif data == "u_sonya":
        if os.path.exists(PHOTO_SONYA_SAD):
            await query.message.reply_photo(photo=open(PHOTO_SONYA_SAD, 'rb'), caption="🤖 *Соня (ИИ-ассистент)*\n\nВы зашли в раздел ИИ-помощника. Задайте свой вопрос по работе бота или оплате подписки:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
        else:
            await query.message.reply_text("🤖 *Соня (ИИ-ассистент)*\n\nВы зашли в раздел ИИ-помощника. Задайте свой вопрос по работе бота или оплате подписки:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
        return SONYA_CHAT

    elif data == "u_modules":
        await _show_modules_menu(query.message, tg_id)

    return ConversationHandler.END

# ─────────────────────────────────────────────
# УПРАВЛЕНИЕ МОДУЛЯМИ
# ─────────────────────────────────────────────
async def _show_modules_menu(message, tg_id):
    s_info = await get_sub_info(tg_id)
    r_info = await update_and_get_rank(tg_id)
    total_slots = s_info['base_modules'] + r_info['bonus_modules']
    
    m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
    async with _file_lock:
        m_data = load_json(m_file) if os.path.exists(m_file) else {"modules": [], "private_modules": []}
    
    used_slots = len(m_data.get("modules", []))
    text = f"⚙️ *Управление модулями*\n\n📊 Занято слотов: `{used_slots}/{total_slots}`\n🔒 Доступно приватных слотов: `{s_info['private_slots']}`"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Установить модуль", callback_data="mod_install_link")],
        [InlineKeyboardButton("◀️ Назад в меню", callback_data="back_main")]
    ])
    
    if os.path.exists(PHOTO_MODULES):
        await message.reply_photo(photo=open(PHOTO_MODULES, 'rb'), caption=text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def mod_install_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "mod_install_link":
        await query.message.reply_text("🔗 Отправьте прямую ссылку на GitHub RAW (.py файл) вашего модуля:", reply_markup=get_cancel_kb())
        return MODULE_INSTALL

# ─────────────────────────────────────────────
# ВВОД ДАННЫХ И ДИАЛОГИ (CONVERSATION STATES)
# ─────────────────────────────────────────────
async def reg_nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nick = update.message.text.strip()
    if len(nick) < 3 or len(nick) > 32:
        await update.message.reply_text("⚠️ Длина ника должна быть от 3 до 32 символов. Попробуйте еще раз:", reply_markup=get_cancel_kb())
        return REG_NICK
    context.user_data["reg_nick"] = nick
    await update.message.reply_text("📱 Теперь введите ваш номер телефона в формате +79123456789:", reply_markup=get_cancel_kb())
    return REG_PHONE

async def reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    async with _file_lock:
        users = load_json(USERS_FILE)
    
    for u_data in users.values():
        if u_data.get("phone") == phone:
            await update.message.reply_text("❌ Номер телефона уже зарегистрирован. Введите другой номер:", reply_markup=get_cancel_kb())
            return REG_PHONE
            
    context.user_data["reg_phone"] = phone
    await update.message.reply_text("🔒 Придумайте пароль (от 4 до 20 символов):", reply_markup=get_cancel_kb())
    return REG_PASS

async def reg_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    if len(password) < 4 or len(password) > 20:
        await update.message.reply_text("⚠️ Слишком короткий или длинный пароль. Попробуйте еще раз:", reply_markup=get_cancel_kb())
        return REG_PASS
        
    tg_id = str(update.effective_user.id)
    async with _file_lock:
        users = load_json(USERS_FILE)
        users[tg_id] = {
            "nick": context.user_data["reg_nick"],
            "phone": context.user_data["reg_phone"],
            "password": password,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "authenticated": False
        }
        save_json(USERS_FILE, users)
    
    await update.message.reply_text("🎉 *Регистрация завершена!*\nТеперь выполните вход через Главное Меню.", parse_mode=ParseMode.MARKDOWN, reply_markup=get_guest_kb())
    return ConversationHandler.END

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
        found_user_id = None
        for u_id, u_data in users.items():
            if u_data.get("phone") == phone and u_data.get("password") == password:
                found_user_id = u_id
                break
                
        if found_user_id:
            if found_user_id != tg_id:
                users[tg_id] = users.pop(found_user_id)
            users[tg_id]["authenticated"] = True
            save_json(USERS_FILE, users)
            await update.message.reply_text(f"✅ Успешный вход! Рады видеть вас, {users[tg_id]['nick']}.", reply_markup=get_user_kb())
        else:
            await update.message.reply_text("❌ Неверный номер телефона или пароль.", reply_markup=get_guest_kb())
            
    return ConversationHandler.END

async def promo_activate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    tg_id = str(update.effective_user.id)
    
    async with _file_lock:
        promos = load_json(PROMO_FILE)
        subs = load_json(SUBS_FILE)
        
        if code not in promos:
            await update.message.reply_text("❌ Такого промокода не существует.", reply_markup=get_user_kb())
            return ConversationHandler.END
            
        p = promos[code]
        if tg_id in p.get("used_by", []):
            await update.message.reply_text("❌ Вы уже активировали этот код.", reply_markup=get_user_kb())
            return ConversationHandler.END
            
        if len(p.get("used_by", [])) >= p.get("max_uses", 1):
            await update.message.reply_text("❌ Лимит активаций исчерпан.", reply_markup=get_user_kb())
            return ConversationHandler.END
            
        p["used_by"].append(tg_id)
        current_sub = subs.get(tg_id, {"tier": 1, "expires": datetime.now(timezone.utc).isoformat()})
        current_expires = datetime.fromisoformat(current_sub["expires"])
        
        if current_expires < datetime.now(timezone.utc):
            current_expires = datetime.now(timezone.utc)
            
        subs[tg_id] = {"tier": p["tier"], "expires": (current_expires + timedelta(days=p.get("days", 30))).isoformat()}
        save_json(PROMO_FILE, promos)
        save_json(SUBS_FILE, subs)
        
    await update.message.reply_text("🎉 Промокод успешно активирован!", reply_markup=get_user_kb())
    return ConversationHandler.END

async def sonya_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(PHOTO_SONYA_HAPPY):
        await update.message.reply_photo(photo=open(PHOTO_SONYA_HAPPY, 'rb'), caption="*«Соня сейчас отдыхает, задайте вопрос позже!»*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
    else:
        await update.message.reply_text("*«Соня сейчас отдыхает, задайте вопрос позже!»*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
    return SONYA_CHAT

async def module_download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    tg_id = str(update.effective_user.id)
    
    s_info = await get_sub_info(tg_id)
    r_info = await update_and_get_rank(tg_id)
    total_slots = s_info['base_modules'] + r_info['bonus_modules']
    
    m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
    async with _file_lock:
        m_data = load_json(m_file) if os.path.exists(m_file) else {"modules": [], "private_modules": []}
    
    if len(m_data["modules"]) >= total_slots:
        await update.message.reply_text("❌ Нет свободных слотов модулей!", reply_markup=get_user_kb())
        return ConversationHandler.END

    await update.message.reply_text("⏳ Скачивание плагина...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    await update.message.reply_text("❌ Ошибка загрузки файла.", reply_markup=get_user_kb())
                    return ConversationHandler.END
                code_text = await resp.text()
                
        if "MODULE_NAME" not in code_text or "init_module" not in code_text:
            await update.message.reply_text("❌ Некорректная структура модуля.", reply_markup=get_user_kb())
            return ConversationHandler.END
            
        mod_name = "downloaded_mod"
        for line in code_text.splitlines():
            if "MODULE_NAME =" in line:
                mod_name = line.split("=")[1].replace('"', '').replace("'", "").strip()
                break
                
        user_mod_dir = os.path.join(MODULES_DIR, f"user_{tg_id}")
        os.makedirs(user_mod_dir, exist_ok=True)
        with open(os.path.join(user_mod_dir, f"{mod_name}.py"), "w", encoding="utf-8") as f:
            f.write(code_text)
            
        async with _file_lock:
            m_data["modules"].append({"name": mod_name, "version": "1.0", "installed_at": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")})
            save_json(m_file, m_data)
        await update.message.reply_text(f"✅ Модуль *{mod_name}* успешно установлен!", parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_kb())
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=get_user_kb())
    return ConversationHandler.END

# ─────────────────────────────────────────────
# АДМИН-ПАНЕЛЬ
# ─────────────────────────────────────────────
async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() != ADMIN_PASSWORD:
        await update.message.reply_text("❌ Неверный пароль.", reply_markup=get_guest_kb())
        return ConversationHandler.END
        
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика", callback_data="a_stat"), InlineKeyboardButton("🎫 Список промокодов", callback_data="a_promos")],
        [InlineKeyboardButton("➕ Создать промокод", callback_data="a_create_promo"), InlineKeyboardButton("👥 Пользователи", callback_data="a_users")],
        [InlineKeyboardButton("📨 Рассылка", callback_data="a_spam"), InlineKeyboardButton("💾 Бэкап БД", callback_data="a_backup")],
        [InlineKeyboardButton("⚙️ Логи системы", callback_data="a_logs"), InlineKeyboardButton("🚪 Выход", callback_data="back_main")]
    ])
    await update.message.reply_text("👑 *Добро пожаловать в Админ-Панель!*", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    return ADMIN_MENU

async def admin_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()
    
    if data == "a_stat":
        async with _file_lock: subs = load_json(SUBS_FILE)
        stats = {1:0, 2:0, 3:0, 4:0}
        for u in subs.values(): stats[u["tier"]] = stats.get(u["tier"], 0) + 1
        txt = f"📊 *Статистика подписок:*\n\nУровень 1: {stats[1]}\nУровень 2: {stats[2]}\nУровень 3: {stats[3]}\nУровень 4: {stats[4]}"
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_admin_panel")]]))
        
    elif data == "a_promos":
        async with _file_lock: promos = load_json(PROMO_FILE)
        txt = "🎫 *Промокоды:*\n\n"
        for c, v in promos.items(): txt += f"`{c}` -> Уровень {v['tier']} [{len(v.get('used_by',[]))}/{v['max_uses']}]\n"
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_admin_panel")]]))
        
    elif data == "a_create_promo":
        await query.message.reply_text("Введите: `УРОВЕНЬ(2-4) ДНИ ЛИМИТ` (Пример: 3 90 50)", reply_markup=get_cancel_kb())
        return ADMIN_PROMO_GEN
        
    elif data == "a_users":
        async with _file_lock:
            users = load_json(USERS_FILE)
            subs = load_json(SUBS_FILE)
        txt = "👥 *Пользователи:*\n\n"
        for u_id, v in users.items(): txt += f"• {v['nick']} ({v['phone']}) | ID: `{u_id}` | Тир: {subs.get(u_id,{'tier':1})['tier']}\n"
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_admin_panel")]]))
        
    elif data == "a_spam":
        await query.message.reply_text("📨 Введите текст рассылки:", reply_markup=get_cancel_kb())
        return ADMIN_SPAM
        
    elif data == "a_backup":
        shutil.make_archive(DATA_DIR + "_backup", 'zip', DATA_DIR)
        await query.message.reply_text("💾 Бэкап ZIP успешно создан в папке проекта!")
        
    elif data == "a_logs":
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f: logs = f.readlines()[-15:]
            await query.message.reply_text(f"⚙️ *Логи:*\n\n```{''.join(logs)}```", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_admin_panel")]]))
            
    elif data == "back_admin_panel":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Статистика", callback_data="a_stat"), InlineKeyboardButton("🎫 Список промокодов", callback_data="a_promos")],
            [InlineKeyboardButton("➕ Создать промокод", callback_data="a_create_promo"), InlineKeyboardButton("👥 Пользователи", callback_data="a_users")],
            [InlineKeyboardButton("📨 Рассылка", callback_data="a_spam"), InlineKeyboardButton("💾 Бэкап БД", callback_data="a_backup")],
            [InlineKeyboardButton("⚙️ Логи системы", callback_data="a_logs"), InlineKeyboardButton("🚪 Выход", callback_data="back_main")]
        ])
        await query.message.reply_text("👑 *Панель Администратора:*", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        return ADMIN_MENU

async def admin_generate_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        tier, days, max_uses = map(int, update.message.text.strip().split())
        import random, string
        rnd = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        prefixes = {2: 'BASIC_', 3: 'PREMIUM_', 4: 'VIP_'}
        code = f"{prefixes[tier]}{rnd}"
        
        async with _file_lock:
            promos = load_json(PROMO_FILE)
            promos[code] = {"tier": tier, "days": days, "max_uses": max_uses, "used_by": []}
            save_json(PROMO_FILE, promos)
        await update.message.reply_text(f"✅ Создан код: `{code}`", parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_kb())
    except:
        await update.message.reply_text("❌ Ошибка ввода.")
    return ConversationHandler.END

async def admin_spam_sender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    async with _file_lock: users = load_json(USERS_FILE)
    for u_id in users:
        try: await context.bot.send_message(chat_id=int(u_id), text=f"📨 *Оповещение:*\n\n{text}", parse_mode=ParseMode.MARKDOWN)
        except: pass
    await update.message.reply_text("✅ Рассылка завершена.", reply_markup=get_user_kb())
    return ConversationHandler.END

# ─────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────
def main():
    init_system()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CallbackQueryHandler(inline_router, pattern="^(g_|u_|back_main)"),
            CallbackQueryHandler(mod_install_router, pattern="^mod_")
        ],
        states={
            REG_NICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_nick)],
            REG_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_phone)],
            REG_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_pass)],
            LOGIN_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone)],
            LOGIN_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_pass)],
            ADMIN_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_login)],
            ADMIN_MENU: [CallbackQueryHandler(admin_menu_router, pattern="^(a_|back_admin_panel)")],
            ADMIN_PROMO_GEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_generate_promo)],
            ADMIN_SPAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_spam_sender)],
            WAIT_PROMO_ACTIVATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, promo_activate_handler)],
            SONYA_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sonya_message_handler)],
            MODULE_INSTALL: [MessageHandler(filters.TEXT & ~filters.COMMAND, module_download_handler)]
        },
        fallbacks=[
            CallbackQueryHandler(inline_router, pattern="^back_main"),
            CommandHandler("start", cmd_start)
        ],
        per_message=False
    )
    
    app.add_handler(conv_handler)
    logger.info("Бот запущен на новой архитектуре без конфликтов потоков!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
