import os
import json
import logging
import random
import asyncio
import importlib.util
import sys
from datetime import datetime
import aiohttp

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)
from telegram.constants import ParseMode

BOT_TOKEN = os.environ.get("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
ADMIN_PASSWORD = "uretracoin"
ADMIN_TG_ID    = "1837883882"
CHANNEL_ID     = "@userbotcbet"
CHANNEL_URL    = "https://t.me/userbotcbet"
MAX_MIRRORS    = 10
CHANNEL_USERNAME = "userbotcbet"

BASE_DIR    = "/app"
DATA_DIR    = os.path.join(BASE_DIR, "data")
MODULES_DIR = os.path.join(DATA_DIR, "modules")
IMAGES_DIR  = os.path.join(BASE_DIR, "images")
LOG_FILE    = os.path.join(BASE_DIR, "bot.log")

USERS_FILE = os.path.join(DATA_DIR, "users.json")
SUBS_FILE  = os.path.join(DATA_DIR, "subscriptions.json")
PROMO_FILE = os.path.join(DATA_DIR, "promocodes.json")

IMAGES_DATA_DIR = os.path.join(DATA_DIR, "images")
PHOTO_AUTH      = os.path.join(IMAGES_DATA_DIR, "auth.jpg")
PHOTO_MODULES   = os.path.join(IMAGES_DATA_DIR, "modules.jpg")
PHOTO_SONYA_SAD = os.path.join(IMAGES_DATA_DIR, "sonya_sad.jpg")
PHOTO_MENU      = os.path.join(IMAGES_DATA_DIR, "menu.jpg")

PHOTO_IDS_FILE    = os.path.join(DATA_DIR, "photo_ids.json")
MIRRORS_FILE      = os.path.join(DATA_DIR, "mirrors.json")
SO2_FILE          = os.path.join(DATA_DIR, "so2_users.json")
REFERRALS_FILE    = os.path.join(DATA_DIR, "referrals.json")
STOCK_MODULES_DIR = os.path.join(DATA_DIR, "stock_modules")

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

_file_lock = asyncio.Lock()

USER_BOTS: dict      = {}
LOADED_MODULES: dict = {}
MIRROR_APPS: dict    = {}
UNPARSER_SESSIONS: dict = {}
OSINT_SESSIONS: dict    = {}
SO2_WAIT: dict          = {}
SO2_AWAIT: dict         = {}


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
    os.makedirs(IMAGES_DATA_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        save_json(USERS_FILE, {})
    if not os.path.exists(SUBS_FILE):
        save_json(SUBS_FILE, {})
    if not os.path.exists(PROMO_FILE):
        save_json(PROMO_FILE, {
            # Одноразовые — Про 30 дней
            "PRO-1KEP": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-2UE9": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-58WV": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-9A2X": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-9G4Z": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-D8Z8": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-EBCO": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-EHND": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-F8SK": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-G4MX": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-H2HN": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-HH81": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-I3SH": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-I9QR": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            "PRO-KC6G": {"plan": "pro", "days": 30, "max_uses": 1,  "used_by": []},
            # Многоразовые x10 — Про 30 дней
            "PRO-L007": {"plan": "pro", "days": 30, "max_uses": 10, "used_by": []},
            "PRO-LAZW": {"plan": "pro", "days": 30, "max_uses": 10, "used_by": []},
            "PRO-TT0O": {"plan": "pro", "days": 30, "max_uses": 10, "used_by": []},
            "PRO-WAME": {"plan": "pro", "days": 30, "max_uses": 10, "used_by": []},
            "PRO-X4ND": {"plan": "pro", "days": 30, "max_uses": 10, "used_by": []},
        })
    if not os.path.exists(PHOTO_IDS_FILE):
        save_json(PHOTO_IDS_FILE, {})
    if not os.path.exists(MIRRORS_FILE):
        save_json(MIRRORS_FILE, {})
    if not os.path.exists(SO2_FILE):
        old_file = os.path.join(DATA_DIR, "so2_accounts.json")
        if os.path.exists(old_file):
            import shutil
            shutil.copy(old_file, SO2_FILE)
        else:
            save_json(SO2_FILE, {})
    if not os.path.exists(REFERRALS_FILE):
        save_json(REFERRALS_FILE, {})
    os.makedirs(STOCK_MODULES_DIR, exist_ok=True)

def is_user_authorized(tg_id: str) -> bool:
    users = load_json(USERS_FILE)
    session_file = os.path.join(DATA_DIR, f"session_{tg_id}.session")
    return (
        tg_id in users
        and users[tg_id].get("authenticated", False)
        and os.path.exists(session_file)
    )

def safe_md(text: str) -> str:
    return text.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")


def _load_sys_module(name: str, client, tg_id: str):
    import importlib.util, sys as _sys
    src = os.path.join(DATA_DIR, f"{name}.py")
    if not os.path.exists(src):
        src = os.path.join(BASE_DIR, f"{name}.py")
    if not os.path.exists(src):
        logger.warning(f"Системный модуль {name}.py не найден")
        return
    try:
        mod_key = f"{name}_{tg_id}"
        spec    = importlib.util.spec_from_file_location(mod_key, src)
        module  = importlib.util.module_from_spec(spec)
        _sys.modules[mod_key] = module
        spec.loader.exec_module(module)
        if hasattr(module, "init_telethon"):
            module.init_telethon(client)
        logger.info(f"Системный модуль {name} загружен для {tg_id}")
    except Exception as e:
        logger.error(f"Ошибка загрузки {name} для {tg_id}: {e}")

def _load_autoreply_module(client, tg_id: str):
    _load_sys_module("autoreply", client, tg_id)

def load_user_modules(client: TelegramClient, tg_id: str):
    user_dir = os.path.join(MODULES_DIR, f"user_{tg_id}")
    LOADED_MODULES.setdefault(tg_id, [])
    _load_autoreply_module(client, tg_id)
    _load_sys_module("timenick", client, tg_id)
    _load_sys_module("cryptobio", client, tg_id)
    if not os.path.exists(user_dir):
        return
    for file in os.listdir(user_dir):
        if not file.endswith(".py"):
            continue
        mod_name = file[:-3]
        module_path = os.path.join(user_dir, file)
        try:
            spec   = importlib.util.spec_from_file_location(mod_name, module_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            if hasattr(module, "init_telethon"):
                module.init_telethon(client)
            if mod_name not in LOADED_MODULES[tg_id]:
                LOADED_MODULES[tg_id].append(mod_name)
            logger.info(f"Модуль {file} загружен для {tg_id}")
        except Exception as e:
            logger.error(f"Ошибка загрузки модуля {file} для {tg_id}: {e}")

async def start_user_bot(tg_id: str, api_id: int, api_hash: str):
    if tg_id in USER_BOTS:
        try:
            await USER_BOTS[tg_id].disconnect()
        except Exception:
            pass
    session_path = os.path.join(DATA_DIR, f"session_{tg_id}")
    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()
    if await client.is_user_authorized():
        USER_BOTS[tg_id] = client
        load_user_modules(client, tg_id)
        logger.info(f"Юзербот для {tg_id} запущен, модули загружены.")
        asyncio.create_task(_run_client(tg_id, client))
    else:
        logger.warning(f"Сессия {tg_id} найдена, но авторизация не пройдена.")

async def _run_client(tg_id: str, client):
    try:
        logger.info(f"Запуск event loop для юзербота {tg_id}")
        await client.run_until_disconnected()
    except Exception as e:
        logger.warning(f"Юзербот {tg_id} отключился: {e}")
    finally:
        if tg_id in USER_BOTS and USER_BOTS[tg_id] is client:
            del USER_BOTS[tg_id]
            logger.info(f"Юзербот {tg_id} удалён из кэша")

async def auto_run_existing_bots():
    users = load_json(USERS_FILE)
    for tg_id, info in users.items():
        session_file = os.path.join(DATA_DIR, f"session_{tg_id}.session")
        if not info.get("authenticated") or not os.path.exists(session_file):
            continue
        if not info.get("api_id") or not info.get("api_hash"):
            continue
        try:
            logger.info(f"Автозапуск юзербота {tg_id}")
            await start_user_bot(tg_id, int(info["api_id"]), info["api_hash"])
        except Exception as e:
            logger.error(f"Не удалось поднять юзербота {tg_id}: {e}")

import random as _random
import string as _string

_PRETTY_PARTS = [
    "dark", "light", "neo", "pro", "max", "ultra", "super", "hyper",
    "fire", "ice", "star", "moon", "sun", "sky", "void", "zero",
    "fast", "cool", "hot", "real", "true", "pure", "wild", "free",
    "night", "day", "black", "white", "red", "blue", "gold", "neon",
    "flash", "boost", "turbo", "mega", "epic", "omega", "alpha", "beta",
    "cyber", "ghost", "storm", "blade", "nova", "pulse", "sonic", "apex",
]

def _unp_gen(length: int, digits: bool) -> str:
    chars = _string.ascii_lowercase + (_string.digits if digits else "")
    first = _random.choice(_string.ascii_lowercase)
    rest  = "".join(_random.choices(chars, k=length - 1))
    return first + rest

def _unp_gen_pretty() -> str:
    a = _random.choice(_PRETTY_PARTS)
    b = _random.choice(_PRETTY_PARTS)
    while b == a:
        b = _random.choice(_PRETTY_PARTS)
    num = str(_random.randint(0, 99)) if _random.random() > 0.5 else ""
    return f"{a}_{b}{num}"

def _unp_is_pro(tg_id: str) -> bool:
    sub = load_sub(tg_id)
    return sub_active(tg_id) and sub.get("plan") == "pro"

def _unp_menu_text(cfg: dict, tg_id: str = "") -> str:
    mode = cfg.get("mode", "random")
    mode_txt = "✨ Красивые" if mode == "pretty" else "🎲 Случайные"
    if mode == "pretty":
        settings = f"📦 Количество: {cfg.get('count', 5)} штук"
    else:
        settings = (
            f"📏 Длина: {cfg.get('length', 8)} символов\n"
            f"🔢 Цифры: {'✅ Да' if cfg.get('digits', True) else '❌ Нет'}\n"
            f"📦 Количество: {cfg.get('count', 5)} штук"
        )
    return (
        "🔍 Парсер юзернеймов\n\n"
        f"{settings}\n"
        f"🎨 Режим: {mode_txt}\n\n"
        "ℹ️ Проверь доступность: поищи юзернейм в Telegram\n\n"
        "📢 @userbotcbet"
    )

def _unp_menu_kb(cfg: dict, tg_id: str = "") -> InlineKeyboardMarkup:
    mode = cfg.get("mode", "random")
    is_pro = _unp_is_pro(tg_id) if tg_id else False
    pretty_label = "✨ Красивые (Pro)" if not is_pro else ("✨ Красивые ✅" if mode == "pretty" else "✨ Красивые")
    rows = []
    if mode == "random":
        digits_label = "🔢 Цифры: ✅" if cfg.get("digits", True) else "🔢 Цифры: ❌"
        rows.append([
            InlineKeyboardButton("➖", callback_data="unp_len_minus"),
            InlineKeyboardButton(f"📏 {cfg.get('length', 8)}", callback_data="unp_noop"),
            InlineKeyboardButton("➕", callback_data="unp_len_plus"),
        ])
        rows.append([InlineKeyboardButton(digits_label, callback_data="unp_digits")])
    rows.append([
        InlineKeyboardButton("➖", callback_data="unp_count_minus"),
        InlineKeyboardButton(f"📦 {cfg.get('count', 5)} шт.", callback_data="unp_noop"),
        InlineKeyboardButton("➕", callback_data="unp_count_plus"),
    ])
    rows.append([
        InlineKeyboardButton("🎲 Случайные ✅" if mode == "random" else "🎲 Случайные", callback_data="unp_mode_random"),
        InlineKeyboardButton(pretty_label, callback_data="unp_mode_pretty"),
    ])
    rows.append([
        InlineKeyboardButton("🔍 Генерировать", callback_data="unp_generate"),
        InlineKeyboardButton("ℹ️ Инфо", callback_data="unp_info"),
    ])
    rows.append([InlineKeyboardButton("◀️ Назад в меню", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)

def _unp_result_kb(sess: dict) -> InlineKeyboardMarkup:
    has_prev = sess.get("current_idx", 0) > 0
    nav = []
    if has_prev:
        nav.append(InlineKeyboardButton("◀️ Вернуться", callback_data="unp_prev"))
    nav.append(InlineKeyboardButton("▶️ Вперёд", callback_data="unp_next"))
    return InlineKeyboardMarkup([
        nav,
        [InlineKeyboardButton("⚙️ Настройки", callback_data="unp_settings"),
         InlineKeyboardButton("◀️ В меню",    callback_data="back_main")],
    ])

def _unp_format(batch: list, idx: int, total: int) -> str:
    if not batch:
        return "😔 Юзернеймов нет. Попробуй ещё раз."
    lines = [f"✅ Юзернеймы (батч {idx+1}/{total}):\n"]
    for un in batch:
        name = un.lstrip("@")
        lines.append(f"  `@{name}`")
    lines.append("\n📢 @userbotcbet")
    return "\n".join(lines)

async def _unp_generate(tg_id: str, cfg: dict) -> list:
    length = max(5, min(32, cfg.get("length", 8)))
    digits = cfg.get("digits", True)
    count  = cfg.get("count", 5)
    mode   = cfg.get("mode", "random")
    results = []
    for _ in range(count):
        if mode == "pretty":
            results.append(_unp_gen_pretty())
        else:
            results.append(_unp_gen(length, digits))
    return results


async def check_subscription(bot, tg_id) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=f"@{CHANNEL_USERNAME}", user_id=int(tg_id))
        return member.status not in ("left", "kicked", "banned")
    except Exception:
        return False

def get_sub_check_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")],
    ])

def get_sub_required_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")]
    ])

def get_guest_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Регистрация", callback_data="g_reg")],
        [InlineKeyboardButton("🔑 Войти (уже есть аккаунт)", callback_data="g_login")],
        [InlineKeyboardButton("👑 Админ-Панель", callback_data="g_admin")]
    ])

# ═══════════════════════════════════════════════════════════════════
# 🎛 НОВОЕ ГЛАВНОЕ МЕНЮ
# ═══════════════════════════════════════════════════════════════════

def get_user_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Профиль",    callback_data="u_profile"),
         InlineKeyboardButton("💎 Подписка",   callback_data="u_sub")],
        [InlineKeyboardButton("📦 Модули",     callback_data="u_modules_menu"),
         InlineKeyboardButton("🤖 Соня (ИИ)", callback_data="u_sonya")],
        [InlineKeyboardButton("🔧 Другое",     callback_data="u_other")],
        [InlineKeyboardButton("🔄 Обновить",   callback_data="u_refresh"),
         InlineKeyboardButton("ℹ️ Инфо",       callback_data="u_info"),
         InlineKeyboardButton("❌ Выйти",      callback_data="u_logout")]
    ])

def get_modules_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧩 Мои модули",       callback_data="u_modules")],
        [InlineKeyboardButton("🔧 Системные модули", callback_data="u_sysmods")],
        [InlineKeyboardButton("🎮 Standoff 2",       callback_data="u_so2")],
        [InlineKeyboardButton("🔒 ScreenLock",       callback_data="u_screenlock")],
        [InlineKeyboardButton("🔍 Юзернеймы",        callback_data="u_unparser")],
        [InlineKeyboardButton("🕵️ OSINT",            callback_data="u_osint")],
        [InlineKeyboardButton("◀️ Назад",            callback_data="back_main")]
    ])

def get_other_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪞 Партнёрская программа", callback_data="u_partner")],
        [InlineKeyboardButton("🎟 Ввести промокод",       callback_data="u_entercode")],
        [InlineKeyboardButton("◀️ Назад",                 callback_data="back_main")]
    ])

def get_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]
    ])

def get_pinpad_kb(entered: str = "") -> InlineKeyboardMarkup:
    display = "🔢 " + ("•" * len(entered) if entered else "_ _ _ _ _")
    rows = [[InlineKeyboardButton(display, callback_data="pin_noop")]]
    for row in [["1","2","3"],["4","5","6"],["7","8","9"]]:
        rows.append([InlineKeyboardButton(d, callback_data=f"pin_digit_{d}") for d in row])
    rows.append([
        InlineKeyboardButton("⌫ Стереть",   callback_data="pin_back"),
        InlineKeyboardButton("0",            callback_data="pin_digit_0"),
        InlineKeyboardButton("✅ Отправить", callback_data="pin_submit")
    ])
    return InlineKeyboardMarkup(rows)

def _get_photo_key(photo_path: str) -> str:
    return os.path.basename(photo_path).replace(".jpg", "")

async def send_photo(msg, photo_path: str, caption: str, reply_markup):
    from telegram import InputMediaPhoto
    photo_ids = load_json(PHOTO_IDS_FILE)
    key = _get_photo_key(photo_path)
    file_id = photo_ids.get(key)
    if file_id:
        try:
            await msg.edit_media(
                media=InputMediaPhoto(media=file_id, caption=caption),
                reply_markup=reply_markup
            )
            return
        except Exception:
            pass
    if file_id:
        try:
            await msg.reply_photo(photo=file_id, caption=caption, reply_markup=reply_markup)
            return
        except Exception as e:
            logger.warning(f"file_id устарел для {key}: {e}")
    if os.path.exists(photo_path):
        try:
            with open(photo_path, "rb") as photo:
                sent = await msg.reply_photo(photo=photo, caption=caption, reply_markup=reply_markup)
                photo_ids[key] = sent.photo[-1].file_id
                save_json(PHOTO_IDS_FILE, photo_ids)
                return
        except Exception as e:
            logger.error(f"Ошибка отправки файла {photo_path}: {e}")
    try:
        await msg.edit_text(caption, reply_markup=reply_markup)
    except Exception:
        await msg.reply_text(caption, reply_markup=reply_markup)

async def send_md(msg, text: str, reply_markup):
    await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def send_plain(msg, text: str, reply_markup):
    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await msg.reply_text(text, reply_markup=reply_markup)


SUB_PLANS = {
    "trial": {"name": "Пробная", "emoji": "🆓", "days": 5,  "price": 0,   "mod_slots": 1,   "sys_slots": 1,   "all_mods": False, "all_sys": False},
    "pro":   {"name": "Про",     "emoji": "👑", "days": 30, "price": 100, "mod_slots": 999, "sys_slots": 999, "all_mods": True,  "all_sys": True},
}
SYS_MODS_LIST = ["autoreply", "timenick"]

def _sub_path(tg_id: str) -> str:
    return os.path.join(DATA_DIR, f"sub_{tg_id}.json")

def load_sub(tg_id: str) -> dict:
    path = _sub_path(tg_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"plan": None, "expires": None, "chosen_sys": [], "chosen_mods": []}

def save_sub(tg_id: str, sub: dict):
    save_json(_sub_path(tg_id), sub)

def sub_active(tg_id: str) -> bool:
    sub = load_sub(tg_id)
    if not sub.get("plan") or not sub.get("expires"):
        return False
    from datetime import timezone
    return datetime.now(timezone.utc).timestamp() < sub["expires"]

def get_plan(tg_id: str) -> dict:
    sub = load_sub(tg_id)
    if not sub_active(tg_id):
        return SUB_PLANS["trial"]
    return SUB_PLANS.get(sub.get("plan", "trial"), SUB_PLANS["trial"])

def can_use_sys_mod(tg_id: str, mod_name: str) -> bool:
    plan = get_plan(tg_id)
    if plan["all_sys"]:
        return True
    sub = load_sub(tg_id)
    chosen = sub.get("chosen_sys", [])
    plan_key = sub.get("plan", "trial")
    if not chosen and plan_key in ("basic", "trial", "pro"):
        return True
    return mod_name in chosen

def can_install_mod(tg_id: str, current_count: int) -> bool:
    plan = get_plan(tg_id)
    return current_count < plan["mod_slots"]

def _sub_status_text(tg_id: str) -> str:
    sub  = load_sub(tg_id)
    plan = get_plan(tg_id)
    if not sub_active(tg_id):
        return f"{plan['emoji']} Подписка не активна"
    from datetime import timezone
    exp  = datetime.fromtimestamp(sub["expires"], tz=timezone.utc)
    days = (exp - datetime.now(timezone.utc)).days
    return f"{plan['emoji']} {plan['name']} — ещё {days} дн."

async def _show_sub_menu(msg, tg_id: str):
    sub  = load_sub(tg_id)
    plan = get_plan(tg_id)
    active = sub_active(tg_id)
    from datetime import timezone
    if active and sub.get("expires"):
        exp  = datetime.fromtimestamp(sub["expires"], tz=timezone.utc)
        days = (exp - datetime.now(timezone.utc)).days
        exp_str = f"до {exp.strftime('%d.%m.%Y')} ({days} дн.)"
    else:
        exp_str = "не активна"
    text = (
        "💎 Подписка\n\n"
        f"Статус: {plan['emoji']} {plan['name']} — {exp_str}\n\n"
        "Планы:\n"
        "🆓 Пробная (5 дн.) — выдаётся при регистрации\n"
        "👑 Про (30 дн.) — 100 ⭐ | Всё разблокировано"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Купить Про — 100 ⭐", callback_data="sub_buy_pro")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]
    ])
    await msg.reply_text(text, reply_markup=kb)


def load_so2_users() -> dict:
    return load_json(SO2_FILE) if os.path.exists(SO2_FILE) else {}

def save_so2_users(data: dict):
    save_json(SO2_FILE, data)

def get_so2_user(tg_id: str) -> dict:
    return load_so2_users().get(tg_id, {})

def save_so2_user(tg_id: str, data: dict):
    users = load_so2_users()
    users[tg_id] = data
    save_so2_users(users)

def so2_main_kb(registered: bool) -> InlineKeyboardMarkup:
    if registered:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Мой профиль",      callback_data="so2_myprofile")],
            [InlineKeyboardButton("🔍 Найти игрока",     callback_data="so2_search")],
            [InlineKeyboardButton("✏️ Изменить данные",  callback_data="so2_edit")],
            [InlineKeyboardButton("ℹ️ Инфо",             callback_data="so2_info")],
            [InlineKeyboardButton("◀️ Назад",            callback_data="u_modules_menu")],
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Зарегистрироваться", callback_data="so2_register")],
            [InlineKeyboardButton("🔍 Найти игрока",       callback_data="so2_search")],
            [InlineKeyboardButton("ℹ️ Инфо",               callback_data="so2_info")],
            [InlineKeyboardButton("◀️ Назад",              callback_data="u_modules_menu")],
        ])

def _so2_clean(text: str) -> str:
    lines = text.split("\n")
    clean = []
    for line in lines:
        if "Astandy" in line or "astandy" in line:
            continue
        if "подпишись" in line.lower():
            continue
        if "t.me/astandy" in line:
            continue
        if "Проект от" in line:
            continue
        clean.append(line)
    while clean and not clean[-1].strip():
        clean.pop()
    return "\n".join(clean)

async def so2_fetch(tg_id: str, so2_id: str) -> str:
    from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
    client = USER_BOTS.get(tg_id)
    if not client:
        return None
    try:
        await client.send_message("so2checker_bot", "/start")
        await asyncio.sleep(2)
        msgs = await client.get_messages("so2checker_bot", limit=1)
        if not msgs:
            return None
        msg = msgs[0]
        if msg.reply_markup:
            first_btn = None
            for row in msg.reply_markup.rows:
                for btn in row.buttons:
                    first_btn = btn
                    break
                if first_btn:
                    break
            if first_btn and hasattr(first_btn, "data"):
                try:
                    await client(GetBotCallbackAnswerRequest(peer="so2checker_bot", msg_id=msg.id, data=first_btn.data))
                except Exception as e:
                    logger.warning(f"SO2 button click error: {e}")
        await asyncio.sleep(2)
        await client.send_message("so2checker_bot", so2_id)
        await asyncio.sleep(5)
        msgs2 = await client.get_messages("so2checker_bot", limit=5)
        for m in msgs2:
            if not m.out and m.text and len(m.text) > 50:
                return _so2_clean(m.text)
        return None
    except Exception as e:
        logger.error(f"SO2 fetch error: {e}")
        return None


OSINT_FIELDS = [
    ("investigator",  "👤 Имя следователя (ты)",        False),
    ("target_name",   "🎯 Имя/псевдоним жертвы",        False),
    ("target_phone",  "📱 Номер телефона жертвы",       True),
    ("target_tg",     "💬 Telegram жертвы (@username)", True),
    ("target_vk",     "🔵 VK жертвы (ссылка или @id)", True),
    ("target_inst",   "📸 Instagram жертвы (@username)",True),
    ("target_tiktok", "🎵 TikTok жертвы (@username)",  True),
    ("target_email",  "📧 Email жертвы",                True),
    ("target_addr",   "🏠 Адрес жертвы",               True),
    ("target_tz",     "🌍 Часовой пояс жертвы",        True),
    ("target_ip",     "🌐 IP адрес жертвы",            True),
    ("target_links",  "🔗 Доп. ссылки/аккаунты",      True),
    ("notes",         "📝 Заметки и доп. информация",  True),
]

def _osint_step_text(step: int, data: dict) -> str:
    _, desc, skippable = OSINT_FIELDS[step]
    skip_txt = " (или /skip чтобы пропустить)" if skippable else ""
    progress = f"[{step+1}/{len(OSINT_FIELDS)}]"
    return f"🕵️ OSINT Органайзер {progress}\n\nВведи {desc}{skip_txt}:"

def _osint_skip_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ Пропустить", callback_data="osint_skip")],
        [InlineKeyboardButton("❌ Отменить",   callback_data="back_main")],
    ])

def _osint_required_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отменить", callback_data="back_main")],
    ])

def _osint_build_tree(data: dict) -> str:
    now  = datetime.now().strftime("%d.%m.%Y %H:%M")
    inv  = data.get("investigator", "Неизвестно")
    name = data.get("target_name", "Неизвестно")
    lines = [
        "🕵️ OSINT РАССЛЕДОВАНИЕ",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📋 Следователь: {inv}",
        f"📅 Дата: {now}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"🎯 ОБЪЕКТ: {name}",
        "│",
    ]
    fields_map = {
        "target_phone":  ("📱", "Телефон"),
        "target_tg":     ("💬", "Telegram"),
        "target_vk":     ("🔵", "VK"),
        "target_inst":   ("📸", "Instagram"),
        "target_tiktok": ("🎵", "TikTok"),
        "target_email":  ("📧", "Email"),
        "target_addr":   ("🏠", "Адрес"),
        "target_tz":     ("🌍", "Часовой пояс"),
        "target_ip":     ("🌐", "IP"),
        "target_links":  ("🔗", "Доп. ссылки"),
        "notes":         ("📝", "Заметки"),
    }
    items = [(k, emoji, label) for k, (emoji, label) in fields_map.items() if data.get(k)]
    for i, (key, emoji, label) in enumerate(items):
        branch = "└──" if i == len(items) - 1 else "├──"
        lines.append(f"{branch} {emoji} {label}: {data[key]}")
    if not items:
        lines.append("└── ⚠️ Нет данных")
    lines += ["", "━━━━━━━━━━━━━━━━━━━━━━", "📢 @userbotcbet | 🤖 @cbet_controller_bot"]
    return "\n".join(lines)


def _timenick_cfg_path(tg_id: str) -> str:
    return os.path.join(DATA_DIR, f"timenick_{tg_id}.json")

def _load_timenick_cfg(tg_id: str) -> dict:
    path = _timenick_cfg_path(tg_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"enabled": False, "nickname": "", "second": 0}

def _save_timenick_cfg(tg_id: str, cfg: dict):
    save_json(_timenick_cfg_path(tg_id), cfg)

def _autoreply_cfg_path(tg_id: str) -> str:
    return os.path.join(DATA_DIR, f"autoreply_{tg_id}.json")

def _load_autoreply_cfg(tg_id: str) -> dict:
    path = _autoreply_cfg_path(tg_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"enabled": False, "mode": "all", "style": "normal"}

def _save_autoreply_cfg(tg_id: str, cfg: dict):
    save_json(_autoreply_cfg_path(tg_id), cfg)

# ═══════════════════════════════════════════════════════════════════
# 💰 CRYPTOBIO — вспомогательные функции UI
# ═══════════════════════════════════════════════════════════════════

def _cryptobio_cfg_path(tg_id: str) -> str:
    return os.path.join(DATA_DIR, f"cryptobio_{tg_id}.json")

def _load_cryptobio_cfg(tg_id: str) -> dict:
    path = _cryptobio_cfg_path(tg_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"enabled": False, "bio_text": "", "coins": ["TON", "SOL", "USDT"], "interval": 5}

def _save_cryptobio_cfg(tg_id: str, cfg: dict):
    save_json(_cryptobio_cfg_path(tg_id), cfg)

CRYPTOBIO_COINS = ["TON", "SOL", "USDT"]

def _cryptobio_kb(tg_id: str) -> InlineKeyboardMarkup:
    cfg     = _load_cryptobio_cfg(tg_id)
    enabled = cfg.get("enabled", False)
    coins   = cfg.get("coins", ["TON", "SOL", "USDT"])
    interval = cfg.get("interval", 5)
    e = "🟢" if enabled else "🔴"

    coin_row = []
    for c in CRYPTOBIO_COINS:
        mark = "✅ " if c in coins else ""
        coin_row.append(InlineKeyboardButton(f"{mark}{c}", callback_data=f"cbio_coin_{c}"))

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{e} CryptoBio — {'включён' if enabled else 'выключен'}",
            callback_data="cbio_toggle"
        )],
        [InlineKeyboardButton("✏️ Изменить текст описания", callback_data="cbio_settext")],
        coin_row,
        [
            InlineKeyboardButton("➖", callback_data="cbio_int_minus"),
            InlineKeyboardButton(f"⏱ {interval} мин.", callback_data="cbio_noop"),
            InlineKeyboardButton("➕", callback_data="cbio_int_plus"),
        ],
        [InlineKeyboardButton("🔄 Обновить сейчас", callback_data="cbio_now")],
        [InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods")]
    ])

def _cryptobio_text(tg_id: str) -> str:
    cfg     = _load_cryptobio_cfg(tg_id)
    enabled = cfg.get("enabled", False)
    bio     = cfg.get("bio_text", "") or "(пусто)"
    coins   = cfg.get("coins", [])
    interval = cfg.get("interval", 5)
    e = "🟢" if enabled else "🔴"
    coins_str = ", ".join(coins) if coins else "не выбраны"
    return (
        f"💰 CryptoBio\n\n"
        f"Статус: {e} {'Включён' if enabled else 'Выключен'}\n"
        f"Текст: {bio}\n"
        f"Монеты: {coins_str}\n"
        f"Интервал: {interval} мин.\n\n"
        f"Telegram ограничивает bio до 70 символов.\n"
        f"📢 @userbotcbet"
    )


async def _show_sysmods(msg, tg_id: str, section: str = "main"):
    if section == "autoreply":
        if not can_use_sys_mod(tg_id, "autoreply"):
            await msg.reply_text(
                "🔒 Автоответчик недоступен на вашей подписке.\n\nАктивируй подписку в разделе 💎 Подписка.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods")]]))
            return
        cfg     = _load_autoreply_cfg(tg_id)
        enabled = cfg.get("enabled", False)
        mode    = cfg.get("mode", "all")
        style   = cfg.get("style", "normal")
        e       = "🟢" if enabled else "🔴"
        MODE_LABELS  = {"all": "Все", "contacts": "Контакты", "non_contacts": "Не контакты"}
        STYLE_LABELS = {"official": "Официальный", "normal": "Обычный", "bold": "Дерзкий"}
        mode_row  = [InlineKeyboardButton(f"{'✅ ' if mode == m else ''}{l}", callback_data=f"sysmod_mode_{m}") for m, l in MODE_LABELS.items()]
        style_row = [InlineKeyboardButton(f"{'✅ ' if style == s else ''}{l}", callback_data=f"sysmod_style_{s}") for s, l in STYLE_LABELS.items()]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{e} Автоответчик — {'включён' if enabled else 'выключен'}", callback_data="sysmod_autoreply_toggle")],
            mode_row, style_row,
            [InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods")]
        ])
        await msg.reply_text(
            f"🤖 Автоответчик\n\nСтатус: {e} {'Включён' if enabled else 'Выключен'}\n"
            f"Режим: {MODE_LABELS.get(mode, mode)}\nСтиль: {STYLE_LABELS.get(style, style)}\n\n"
            "Отвечает на входящие личные сообщения пока ты недоступен.",
            reply_markup=kb
        )

    elif section == "timenick":
        if not can_use_sys_mod(tg_id, "timenick"):
            await msg.reply_text(
                "🔒 Ник по времени недоступен на вашей подписке.\n\nАктивируй подписку в разделе 💎 Подписка.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods")]]))
            return
        cfg     = _load_timenick_cfg(tg_id)
        enabled = cfg.get("enabled", False)
        nick    = cfg.get("nickname", "")
        second  = cfg.get("second", 0)
        e       = "🟢" if enabled else "🔴"
        tz_offset = cfg.get("tz_offset", 3)
        from datetime import timezone, timedelta
        tz_now    = datetime.now(timezone(timedelta(hours=tz_offset))).strftime("%H:%M")
        preview   = f"{nick} | {tz_now}" if nick else "не задан"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{e} Ник по времени — {'включён' if enabled else 'выключен'}", callback_data="sysmod_timenick_toggle")],
            [InlineKeyboardButton("✏️ Изменить никнейм", callback_data="sysmod_timenick_setnick")],
            [InlineKeyboardButton(f"⏱ Секунда обновления: {second}с", callback_data="sysmod_timenick_setsec")],
            [InlineKeyboardButton(f"🌍 Часовой пояс: UTC+{tz_offset}", callback_data="sysmod_timenick_settz")],
            [InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods")]
        ])
        await msg.reply_text(
            f"🕐 Ник по времени\n\nСтатус: {e} {'Включён' if enabled else 'Выключен'}\n"
            f"Никнейм: {nick if nick else 'не задан'}\nСекунда обновления: {second}с\n"
            f"Часовой пояс: UTC+{tz_offset} (сейчас {tz_now})\nПревью: {preview}\n\n"
            "Каждую минуту в заданную секунду обновляет имя профиля.\nФормат: nickname | HH:MM",
            reply_markup=kb
        )

    else:
        ar_cfg = _load_autoreply_cfg(tg_id)
        tn_cfg = _load_timenick_cfg(tg_id)
        ar_e   = "🟢" if ar_cfg.get("enabled") else "🔴"
        tn_e   = "🟢" if tn_cfg.get("enabled") else "🔴"
        cb_cfg = _load_cryptobio_cfg(tg_id)
        cb_e   = "🟢" if cb_cfg.get("enabled") else "🔴"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{ar_e} Автоответчик",   callback_data="u_sysmods_autoreply")],
            [InlineKeyboardButton(f"{tn_e} Ник по времени", callback_data="u_sysmods_timenick")],
            [InlineKeyboardButton(f"{cb_e} CryptoBio",      callback_data="u_sysmods_cryptobio")],
            [InlineKeyboardButton("◀️ Назад",               callback_data="u_modules_menu")]
        ])
        await msg.reply_text(
            f"🔧 Системные модули\n\n"
            f"{ar_e} Автоответчик — {'включён' if ar_cfg.get('enabled') else 'выключен'}\n"
            f"{tn_e} Ник по времени — {'включён' if tn_cfg.get('enabled') else 'выключен'}\n"
            f"{cb_e} CryptoBio — {'включён' if cb_cfg.get('enabled') else 'выключен'}\n\n"
            "Выбери модуль для настройки:",
            reply_markup=kb
        )


SCREENLOCK_PASSWORD = "uretra2026"

def _screenlock_generate_code(token: str) -> str:
    import textwrap
    return textwrap.dedent(f"""
import os, subprocess, psutil, platform
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import pyautogui

TOKEN   = "{token}"
SAVEDIR = os.path.join(os.path.expanduser("~"), "ScreenLock")
os.makedirs(SAVEDIR, exist_ok=True)

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статус системы", callback_data="sl_status")],
        [InlineKeyboardButton("🖥️ Скриншот", callback_data="sl_screenshot")],
        [InlineKeyboardButton("📁 Файлы", callback_data="sl_files")],
        [InlineKeyboardButton("⌨️ CMD команда", callback_data="sl_cmd_help")],
        [InlineKeyboardButton("📤 Запустить .exe", callback_data="sl_run_help")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔒 ScreenLock\n\nПК онлайн и готов к управлению.\nВыбери действие:", reply_markup=main_kb())

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    if d == "sl_status":
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        boot = datetime.fromtimestamp(psutil.boot_time()).strftime("%d.%m.%Y %H:%M")
        await q.message.reply_text(f"🖥️ Статус\n\n💻 ОС: {{platform.system()}} {{platform.release()}}\n⚙️ CPU: {{cpu}}%\n🧠 RAM: {{ram.percent}}%\n💾 Диск C: {{disk.percent}}%\n🕐 Запущен: {{boot}}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="sl_status")],[InlineKeyboardButton("◀️ Меню", callback_data="sl_back")]]))
    elif d == "sl_screenshot":
        path = os.path.join(SAVEDIR, "screen.png")
        pyautogui.screenshot(path)
        with open(path, "rb") as f:
            await q.message.reply_photo(f, caption="🖥️ Скриншот", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Новый скрин", callback_data="sl_screenshot")],[InlineKeyboardButton("◀️ Меню", callback_data="sl_back")]]))
    elif d == "sl_files":
        files = os.listdir(SAVEDIR)
        text = "📁 Пусто" if not files else "📁 Файлы:\n\n" + "\n".join([f"• {{f}}" for f in files])
        await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Обновить", callback_data="sl_files")],[InlineKeyboardButton("◀️ Меню", callback_data="sl_back")]]))
    elif d == "sl_cmd_help":
        await q.message.reply_text("⌨️ CMD\n\nОтправь: cmd: <команда>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Меню", callback_data="sl_back")]]))
    elif d == "sl_run_help":
        files = [f for f in os.listdir(SAVEDIR) if f.endswith(".exe")]
        if not files:
            await q.message.reply_text("📤 Нет .exe файлов.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Меню", callback_data="sl_back")]]))
        else:
            kb = [[InlineKeyboardButton(f"▶️ {{f}}", callback_data=f"sl_run_{{f}}")] for f in files]
            kb.append([InlineKeyboardButton("◀️ Меню", callback_data="sl_back")])
            await q.message.reply_text("📤 Выбери .exe:", reply_markup=InlineKeyboardMarkup(kb))
    elif d.startswith("sl_run_"):
        fname = d[7:]
        fpath = os.path.join(SAVEDIR, fname)
        if os.path.exists(fpath):
            subprocess.Popen(fpath)
            await q.message.reply_text(f"🚀 Запущен: {{fname}}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Меню", callback_data="sl_back")]]))
        else:
            await q.answer("❌ Файл не найден", show_alert=True)
    elif d == "sl_back":
        await q.message.reply_text("🔒 ScreenLock\n\nВыбери действие:", reply_markup=main_kb())

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    path = os.path.join(SAVEDIR, doc.file_name)
    f = await context.bot.get_file(doc.file_id)
    await f.download_to_drive(path)
    if doc.file_name.endswith(".exe"):
        await update.message.reply_text(f"✅ Сохранён: {{doc.file_name}}\n\nЗапустить?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"▶️ Запустить {{doc.file_name}}", callback_data=f"sl_run_{{doc.file_name}}")],[InlineKeyboardButton("◀️ Меню", callback_data="sl_back")]]))
    else:
        await update.message.reply_text(f"✅ Сохранён: {{doc.file_name}}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower().startswith("cmd:"):
        command = text[4:].strip()
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30, encoding="cp866")
            out = result.stdout or result.stderr or "✅ Выполнено"
            if len(out) > 3500:
                out = out[:3500] + "\n...(обрезано)"
            await update.message.reply_text(f"```\n{{out}}\n```", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Меню", callback_data="sl_back")]]))
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {{e}}")
    else:
        await update.message.reply_text("Отправь команду: cmd: <команда>\nИли используй кнопки:", reply_markup=main_kb())

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(btn))
app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
print("🔒 ScreenLock агент запущен!")
app.run_polling()
""").strip()

def _screenlock_readme() -> str:
    return (
        "╔══════════════════════════════════════╗\n"
        "║         ScreenLock Agent             ║\n"
        "║         by @userbotcbet              ║\n"
        "╚══════════════════════════════════════╝\n\n"
        "ТРЕБОВАНИЯ:\n"
        "  - Windows 7/10/11\n"
        "  - Python 3.10+\n\n"
        "БЫСТРЫЙ СТАРТ:\n"
        "  1. Установи Python\n"
        "  2. Дважды кликни на start.bat\n"
        "  3. Открой Telegram и напиши боту /start\n\n"
        "  @userbotcbet"
    )

async def screenlock_token_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    step  = context.user_data.get("sl_step")
    text  = update.message.text.strip()
    if step == "wait_password":
        if text != SCREENLOCK_PASSWORD:
            await update.message.reply_text("❌ Неверный пароль.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Попробовать снова", callback_data="u_screenlock")],[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]))
            context.user_data["sl_step"] = None
            return "MENU"
        context.user_data["sl_step"] = None
        await update.message.reply_text(
            "🔒 ScreenLock\n\n⚠️ Тестовый модуль\n\nСоздай агента для удалённого управления ПК.\n\nКак работает:\n1. Вводишь токен Telegram-бота\n2. Выбираешь формат\n3. Получаешь архив\n4. Запускаешь на ПК\n5. Управляешь через бота\n\n1 токен = 1 ПК\n\n📢 @userbotcbet",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Создать агента", callback_data="sl_create")],[InlineKeyboardButton("◀️ Назад", callback_data="u_modules_menu")]])
        )
        return "SCREENLOCK"
    if step == "wait_token":
        if ":" not in text or len(text) < 30:
            await update.message.reply_text("❌ Неверный формат токена.\n\nФормат: 1234567890:AAFxxxxxxxxxxxxxxxxxxxxxxx", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="sl_menu")]]))
            return "SCREENLOCK"
        context.user_data["sl_token"] = text
        context.user_data["sl_step"]  = "wait_format"
        await update.message.reply_text(
            "🔒 ScreenLock — Создание агента\n\nШаг 2/2: Выбери формат",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🖥️ .exe (Windows)", callback_data="sl_format_exe")],[InlineKeyboardButton("📱 .apk (Android) — скоро", callback_data="sl_format_apk")],[InlineKeyboardButton("◀️ Отмена", callback_data="sl_menu")]])
        )
        return "SCREENLOCK"
    return "SCREENLOCK"


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    context.user_data.clear()
    logger.info(f"/start от юзера {tg_id}")
    if tg_id != ADMIN_TG_ID:
        is_subbed = await check_subscription(context.bot, int(tg_id))
        if not is_subbed:
            await update.message.reply_text(
                f"👋 Добро пожаловать в UserBot | Ru!\n\nДля использования бота необходимо подписаться на наш канал.\n\n📢 Канал: @{CHANNEL_USERNAME}\n\nПосле подписки нажми кнопку ниже 👇",
                reply_markup=get_sub_required_kb()
            )
            return "MENU"
    async with _file_lock:
        is_auth = is_user_authorized(tg_id)
        users   = load_json(USERS_FILE)
    if is_auth:
        u_info = users[tg_id]
        if not u_info.get("api_id") or not u_info.get("api_hash"):
            logger.warning(f"Битая запись для {tg_id}, сбрасываем.")
            async with _file_lock:
                users_w = load_json(USERS_FILE)
                if tg_id in users_w:
                    users_w[tg_id]["authenticated"] = False
                    save_json(USERS_FILE, users_w)
            for ext in (".session", ".session-journal"):
                p = os.path.join(DATA_DIR, f"session_{tg_id}{ext}")
                if os.path.exists(p):
                    try: os.remove(p)
                    except Exception: pass
            await send_photo(update.message, PHOTO_AUTH, "⚠️ Обнаружена повреждённая сессия — сброшена.\n\nНажми кнопку ниже для настройки.", get_guest_kb())
            return "MENU"
        if tg_id not in USER_BOTS:
            asyncio.create_task(start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"]))
        nick   = u_info.get("nick", "Пользователь")
        status = "🟢 активен" if tg_id in USER_BOTS else "🔴 запускается..."
        await send_photo(update.message, PHOTO_MENU, f"🏠 Главное меню\n\nДобро пожаловать, {nick}!\nЮзербот: {status}\n\nВыбери раздел:", get_user_kb())
    else:
        await send_photo(update.message, PHOTO_AUTH,
            "👾 UserBot | Ru\n\nДобро пожаловать в систему управления юзерботами!\n\nПодключи свой Telegram-аккаунт и устанавливай модули — автоответчики, инструменты автоматизации, фильтры и многое другое.\n\n⚡️ Движок: Telethon\n🧩 Система модулей: как в Hikka\n👤 Автор: @cbet_cebep\n\n👇 Нажми кнопку чтобы начать:",
            get_guest_kb())
    return "MENU"


def load_mirrors() -> dict:
    return load_json(MIRRORS_FILE)

def save_mirrors(data: dict):
    save_json(MIRRORS_FILE, data)

def load_referrals() -> dict:
    return load_json(REFERRALS_FILE)

def save_referrals(data: dict):
    save_json(REFERRALS_FILE, data)

def get_mirror_stats(partner_id: str) -> dict:
    refs = load_referrals()
    partner_refs = [r for r in refs.values() if r.get("partner_id") == partner_id]
    return {"total": len(partner_refs), "bonus_days": len(partner_refs)}

def add_referral(new_user_id: str, partner_id: str):
    refs = load_referrals()
    if new_user_id in refs:
        return
    refs[new_user_id] = {"partner_id": partner_id, "date": datetime.now().strftime("%d.%m.%Y %H:%M")}
    save_referrals(refs)
    from datetime import timezone, timedelta
    sub = load_sub(partner_id)
    now_ts = datetime.now(timezone.utc).timestamp()
    base = max(sub.get("expires", now_ts), now_ts)
    sub["expires"] = base + 86400
    if not sub.get("plan"):
        sub["plan"] = "trial"
    save_sub(partner_id, sub)

async def start_mirror_bot(partner_id: str, token: str, partner_nick: str):
    from telegram.ext import ApplicationBuilder as AB
    if partner_id in MIRROR_APPS:
        try:
            await MIRROR_APPS[partner_id].stop()
            await MIRROR_APPS[partner_id].shutdown()
        except Exception:
            pass
    try:
        mirror_app = AB().token(token).build()
        async def mirror_start(update, context):
            user_id = str(update.effective_user.id)
            context.user_data.clear()
            users = load_json(USERS_FILE)
            if user_id not in users:
                add_referral(user_id, partner_id)
            if user_id != ADMIN_TG_ID:
                try:
                    member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=int(user_id))
                    if member.status in ("left", "kicked", "banned"):
                        await update.message.reply_text(
                            f"👋 Добро пожаловать!\n\nЭто бот партнёра — {partner_nick}\n\nДля использования подпишись на канал @userbotcbet\n\nПосле подписки нажми /start снова.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL)]]))
                        return
                except Exception:
                    pass
            is_auth = is_user_authorized(user_id)
            users_data = load_json(USERS_FILE)
            if is_auth:
                u_info = users_data[user_id]
                if user_id not in USER_BOTS and u_info.get("api_id") and u_info.get("api_hash"):
                    asyncio.create_task(start_user_bot(user_id, int(u_info["api_id"]), u_info["api_hash"]))
                nick = u_info.get("nick", "Пользователь")
                await update.message.reply_text(f"🏠 Главное меню\n\nДобро пожаловать, {nick}!\n\nРеферальный бот партнёра: {partner_nick}", reply_markup=get_user_kb())
            else:
                await update.message.reply_text(f"👾 UserBot | Ru\n\nРеферальный бот партнёра: {partner_nick}\n\nЗарегистрируйся и получи пробный доступ на 5 дней!", reply_markup=get_guest_kb())

        from telegram.ext import CommandHandler as CH, CallbackQueryHandler as CQH, MessageHandler as MH
        conv = ConversationHandler(
            entry_points=[CH("start", mirror_start)],
            states={
                "MENU": [CQH(menu_router)],
                "REG_NICK": [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, reg_nick)],
                "LOGIN_PHONE": [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, login_phone)],
                "LOGIN_API_ID": [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, login_api_id)],
                "LOGIN_API_HASH": [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, login_api_hash)],
                "LOGIN_PHONE_EXISTING": [CQH(menu_router, pattern="^back_main$"), MH(filters.TEXT & ~filters.COMMAND, login_phone_existing)],
                "WAIT_CODE": [CQH(pinpad_click_handler, pattern="^pin_"), CQH(menu_router, pattern="^back_main$")],
                "WAIT_2FA": [CQH(menu_router, pattern="^back_main$"), MH(filters.TEXT & ~filters.COMMAND, wait_2fa)],
                "WAIT_TIMENICK": [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, wait_timenick)],
                "MODULE_INSTALL": [CQH(menu_router), MH((filters.Document.ALL | filters.TEXT) & ~filters.COMMAND, module_download_handler)],
                "SONYA_CHAT": [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, sonya_chat)],
                "WAIT_PROMO_ACTIVATE": [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, promo_activate)],
                "ADMIN_LOGIN": [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, admin_login)],
                "ADMIN_MENU": [CQH(admin_router)],
                "SET_IMAGES": [CH("start", mirror_start), MH(filters.PHOTO, setimages_handler)],
            },
            fallbacks=[CH("start", mirror_start), CQH(menu_router)],
            per_message=False, per_chat=True, per_user=True, allow_reentry=True, conversation_timeout=600
        )
        mirror_app.add_handler(conv)
        async def mirror_error(update, context):
            logger.error(f"Ошибка в зеркале {partner_id}: {context.error}")
        mirror_app.add_error_handler(mirror_error)
        await mirror_app.initialize()
        await mirror_app.start()
        await mirror_app.updater.start_polling(drop_pending_updates=True)
        MIRROR_APPS[partner_id] = mirror_app
        logger.info(f"Зеркало для партнёра {partner_id} запущено")
        return True
    except Exception as e:
        logger.error(f"Ошибка запуска зеркала для {partner_id}: {e}")
        return False

async def stop_mirror_bot(partner_id: str):
    if partner_id in MIRROR_APPS:
        try:
            await MIRROR_APPS[partner_id].updater.stop()
            await MIRROR_APPS[partner_id].stop()
            await MIRROR_APPS[partner_id].shutdown()
            del MIRROR_APPS[partner_id]
        except Exception as e:
            logger.error(f"Ошибка остановки зеркала {partner_id}: {e}")

async def auto_run_mirrors():
    mirrors = load_mirrors()
    for partner_id, info in mirrors.items():
        if info.get("active") and info.get("token"):
            await start_mirror_bot(partner_id, info["token"], info.get("nick", "Партнёр"))


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tg_id = str(query.from_user.id)
    data  = query.data
    logger.info(f"menu_router: юзер {tg_id} нажал '{data}'")
    await query.answer()

    async with _file_lock:
        is_auth = is_user_authorized(tg_id)
        users   = load_json(USERS_FILE)

    if data == "check_sub":
        is_subbed = await check_subscription(context.bot, int(tg_id))
        if is_subbed:
            async with _file_lock:
                is_auth_now = is_user_authorized(tg_id)
                users_now   = load_json(USERS_FILE)
            if is_auth_now:
                u_info = users_now[tg_id]
                if tg_id not in USER_BOTS and u_info.get("api_id") and u_info.get("api_hash"):
                    asyncio.create_task(start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"]))
                nick   = u_info.get("nick", "Пользователь")
                status = "🟢 активен" if tg_id in USER_BOTS else "🔴 запускается..."
                await send_photo(query.message, PHOTO_MENU, f"🏠 Главное меню\n\nДобро пожаловать, {nick}!\nЮзербот: {status}\n\nВыбери раздел:", get_user_kb())
            else:
                await send_photo(query.message, PHOTO_AUTH, "✅ Подписка подтверждена!\n\nТеперь можешь зарегистрироваться или войти:", get_guest_kb())
        else:
            await query.answer("❌ Ты ещё не подписан на канал!", show_alert=True)
        return "MENU"

    if data == "back_main":
        context.user_data.clear()
        if is_auth:
            nick   = users[tg_id].get("nick", "Пользователь")
            status = "🟢 активен" if tg_id in USER_BOTS else "🔴 запускается..."
            await send_photo(query.message, PHOTO_MENU, f"🏠 Главное меню\n\nДобро пожаловать, {nick}!\nЮзербот: {status}\n\nВыбери раздел:", get_user_kb())
        else:
            await send_photo(query.message, PHOTO_AUTH, "👾 UserBot | Ru\n\nДобро пожаловать в систему управления юзерботами!\n\nПодключи свой Telegram-аккаунт и устанавливай модули — автоответчики, инструменты автоматизации, фильтры и многое другое.\n\n⚡️ Движок: Telethon\n🧩 Система модулей: как в Hikka\n👤 Автор: @cbet_cebep\n\n👇 Нажми кнопку чтобы начать:", get_guest_kb())
        return "MENU"

    if data == "g_reg":
        if is_auth:
            await send_plain(query.message, "⚠️ Сессия уже создана!", get_user_kb())
            return "MENU"
        is_subbed = await check_subscription(context.bot, tg_id)
        if not is_subbed:
            await send_photo(query.message, PHOTO_AUTH, "📢 Для регистрации необходимо подписаться на наш канал!\n\n1. Нажми кнопку ниже и подпишись\n2. Вернись и нажми Проверить подписку", get_sub_check_kb())
            return "MENU"
        await send_photo(query.message, PHOTO_AUTH, "🔐 Авторизация — Шаг 1 из 4\n\nПридумай себе никнейм — он будет отображаться в профиле.\n\nМожно использовать латиницу, кириллицу или цифры.\nПример: DarkUser, Артём, xXbotXx\n\nКанал проекта: @userbotcbet", get_cancel_kb())
        return "REG_NICK"

    if data == "g_login":
        if is_auth:
            await send_plain(query.message, "⚠️ Ты уже авторизован!", get_user_kb())
            return "MENU"
        await send_photo(query.message, PHOTO_AUTH, "🔑 Вход в существующий аккаунт\n\nВведи номер телефона привязанный к твоему Telegram-аккаунту.\n\nМы найдём твою сессию и восстановим юзербота.\nФормат: +79001234567", get_cancel_kb())
        context.user_data["login_mode"] = "existing"
        return "LOGIN_PHONE_EXISTING"

    if data == "g_admin":
        await send_plain(query.message, "👑 Введите пароль администратора:", get_cancel_kb())
        return "ADMIN_LOGIN"

    if not is_auth:
        await send_photo(query.message, PHOTO_AUTH, "👾 UserBot | Ru\n\nСессия не найдена. Войди или зарегистрируйся.", get_guest_kb())
        return "MENU"

    # ══════════════════════════════════════════════════════════════
    # 📦 ПОДМЕНЮ МОДУЛИ
    # ══════════════════════════════════════════════════════════════

    if data == "u_modules_menu":
        await send_photo(query.message, PHOTO_MODULES, "📦 Модули\n\nВыбери раздел:", get_modules_kb())
        return "MENU"

    # ══════════════════════════════════════════════════════════════
    # 🔧 ПОДМЕНЮ ДРУГОЕ
    # ══════════════════════════════════════════════════════════════

    if data == "u_other":
        await send_plain(query.message, "🔧 Другое\n\nВыбери раздел:", get_other_kb())
        return "MENU"

    if data == "u_so2":
        context.user_data["so2_await_pass"] = True
        await send_plain(query.message, "🎮 Standoff 2\n\n🔒 Введи пароль для доступа к разделу:", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_modules_menu")]]))
        return "SO2"

    if data == "u_so2_enter":
        profile = get_so2_user(tg_id)
        registered = bool(profile.get("so2_id"))
        if registered:
            nick  = profile.get("nick", "—")
            so2id = profile.get("so2_id", "—")
            gold  = profile.get("gold", "не указан")
            text = f"🎮 Standoff 2\n\n👤 Ник: {nick}\n🆔 ID: {so2id}\n💰 Баланс Gold: {gold}\n\nВыбери действие:"
        else:
            text = "🎮 Standoff 2\n\nТы ещё не зарегистрирован.\nЗарегистрируйся чтобы сохранить профиль\nи быстро смотреть статистику.\n\nИли сразу ищи игрока по ID."
        await send_plain(query.message, text, so2_main_kb(registered))
        return "SO2"

    if data == "so2_info":
        await send_plain(query.message, "Standoff 2 — модуль\n\nЧто умеет:\n- Сохраняй профиль (ник, ID, баланс голды)\n- Ищи игрока по SO2 ID\n- Статистика: ранг, время, дата рег.\n\nКак найти свой ID:\n1. Открой Standoff 2\n2. Нажми на аватар (верхний левый угол)\n3. ID под никнеймом\n\n@userbotcbet | @cbet_controller_bot", InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="u_so2")]]))
        return "SO2"

    if data == "so2_register":
        context.user_data["so2_step"] = "nick"
        context.user_data["so2_data"] = {}
        await send_plain(query.message, "📝 Регистрация — Шаг 1/2\n\nВведи свой никнейм в Standoff 2:", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="u_so2")]]))
        return "SO2"

    if data == "so2_edit":
        context.user_data["so2_step"] = "nick"
        context.user_data["so2_data"] = {}
        await send_plain(query.message, "✏️ Изменение данных — Шаг 1/3\nВведи свой никнейм в Standoff 2:", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="u_so2")]]))
        return "SO2"

    if data == "so2_search":
        context.user_data["so2_step"] = "search"
        await send_plain(query.message, "🔍 Поиск игрока\nВведи Standoff 2 ID игрока:", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="u_so2")]]))
        return "SO2"

    if data == "so2_myprofile":
        profile = get_so2_user(tg_id)
        so2_id  = profile.get("so2_id")
        if not so2_id:
            await query.answer("Сначала зарегистрируйся!", show_alert=True)
            return "SO2"
        if tg_id not in USER_BOTS:
            await send_plain(query.message, "⚠️ Юзербот не запущен. Нажми Обновить или /start.", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_so2")]]))
            return "SO2"
        msg = await query.message.reply_text("⏳ Загружаю профиль...")
        result = await so2_fetch(tg_id, so2_id)
        gold = profile.get("gold", "")
        nick = profile.get("nick", "—")
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_so2")]])
        if result:
            await msg.edit_text(f"🎮 Мой профиль Standoff 2\n\n👤 Ник: {nick}\n🆔 ID: {so2_id}\n\n{result}", reply_markup=back_kb)
        else:
            await msg.edit_text("❌ Не удалось получить данные. Попробуй позже.", reply_markup=back_kb)

    if data == "u_osint":
        OSINT_SESSIONS[tg_id] = {"step": 0, "data": {}}
        step_text = _osint_step_text(0, {})
        _, _, skippable = OSINT_FIELDS[0]
        kb = _osint_skip_kb() if skippable else _osint_required_kb()
        await send_plain(query.message, step_text, kb)
        return "OSINT"

    if data == "osint_skip":
        if tg_id not in OSINT_SESSIONS:
            return "MENU"
        sess = OSINT_SESSIONS[tg_id]
        step = sess["step"]
        _, _, skippable = OSINT_FIELDS[step]
        if not skippable:
            await query.answer("Это поле обязательное!", show_alert=True)
            return "OSINT"
        step += 1
        if step >= len(OSINT_FIELDS):
            tree = _osint_build_tree(sess["data"])
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Новое расследование", callback_data="u_osint")],[InlineKeyboardButton("◀️ В меню", callback_data="back_main")]])
            await send_plain(query.message, tree, kb)
            del OSINT_SESSIONS[tg_id]
            return "MENU"
        sess["step"] = step
        _, _, skippable_next = OSINT_FIELDS[step]
        kb = _osint_skip_kb() if skippable_next else _osint_required_kb()
        await send_plain(query.message, _osint_step_text(step, sess["data"]), kb)
        return "OSINT"

    if data == "osint_done":
        await query.answer("✅ Скопируй текст выше!", show_alert=True)
        return "MENU"

    if data == "u_unparser":
        if tg_id not in UNPARSER_SESSIONS:
            UNPARSER_SESSIONS[tg_id] = {"cfg": {"length": 8, "digits": True, "count": 5, "mode": "random"}, "history": [], "current_idx": -1, "running": False}
        cfg = UNPARSER_SESSIONS[tg_id]["cfg"]
        await query.message.reply_text(_unp_menu_text(cfg, tg_id), reply_markup=_unp_menu_kb(cfg, tg_id), disable_web_page_preview=True)
        return "UNPARSER"

    if data == "unp_noop":
        return "UNPARSER"

    if data == "unp_settings":
        if tg_id not in UNPARSER_SESSIONS:
            UNPARSER_SESSIONS[tg_id] = {"cfg": {"length": 8, "digits": True, "count": 5, "mode": "random"}, "history": [], "current_idx": -1, "running": False}
        cfg = UNPARSER_SESSIONS[tg_id]["cfg"]
        try:
            await query.message.edit_text(_unp_menu_text(cfg, tg_id), reply_markup=_unp_menu_kb(cfg, tg_id), disable_web_page_preview=True)
        except Exception:
            await query.message.reply_text(_unp_menu_text(cfg, tg_id), reply_markup=_unp_menu_kb(cfg, tg_id), disable_web_page_preview=True)
        return "UNPARSER"

    if data == "unp_info":
        await send_plain(query.message, "ℹ️ Парсер юзернеймов\n\nГенерирует юзернеймы для Telegram.\n\n🎲 Случайные — рандомные буквы и цифры нужной длины\n✨ Красивые — осмысленные сочетания слов (dark neo, fire blade)\n\n⚙️ Настройки:\n📏 Длина — от 5 до 32 символов\n🔢 Цифры — включить/выключить цифры\n📦 Количество — от 1 до 20 штук\n\nПосле генерации проверь доступность:\nt.me/username — если открывается профиль — занят\nЕсли не найден — свободен!\n\n📢 @userbotcbet | 🤖 @cbet_controller_bot", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="unp_settings")]]))
        return "UNPARSER"

    if data in ("unp_len_minus", "unp_len_plus", "unp_digits", "unp_count_minus", "unp_count_plus", "unp_mode_random", "unp_mode_pretty"):
        if tg_id not in UNPARSER_SESSIONS:
            UNPARSER_SESSIONS[tg_id] = {"cfg": {"length": 8, "digits": True, "count": 5, "mode": "random"}, "history": [], "current_idx": -1, "running": False}
        cfg = UNPARSER_SESSIONS[tg_id]["cfg"]
        if data == "unp_len_minus":     cfg["length"] = max(5,  cfg.get("length", 8) - 1)
        elif data == "unp_len_plus":    cfg["length"] = min(32, cfg.get("length", 8) + 1)
        elif data == "unp_digits":      cfg["digits"] = not cfg.get("digits", True)
        elif data == "unp_count_minus": cfg["count"]  = max(1,  cfg.get("count", 5) - 1)
        elif data == "unp_count_plus":  cfg["count"]  = min(20, cfg.get("count", 5) + 1)
        elif data == "unp_mode_random": cfg["mode"]   = "random"
        elif data == "unp_mode_pretty":
            if not _unp_is_pro(tg_id):
                await query.answer("👑 Только для Pro подписки!", show_alert=True)
                return "UNPARSER"
            cfg["mode"] = "pretty"
        try:
            await query.message.edit_text(_unp_menu_text(cfg, tg_id), reply_markup=_unp_menu_kb(cfg, tg_id), disable_web_page_preview=True)
        except Exception:
            await query.message.reply_text(_unp_menu_text(cfg, tg_id), reply_markup=_unp_menu_kb(cfg, tg_id), disable_web_page_preview=True)
        return "UNPARSER"

    if data == "unp_generate":
        if tg_id not in UNPARSER_SESSIONS:
            UNPARSER_SESSIONS[tg_id] = {"cfg": {"length": 8, "digits": True, "count": 5, "mode": "random"}, "history": [], "current_idx": -1, "running": False}
        sess = UNPARSER_SESSIONS[tg_id]
        if sess.get("running"):
            await query.answer("⏳ Уже генерирую...", show_alert=True)
            return "UNPARSER"
        sess["running"] = True
        await query.message.reply_text("⏳ Генерирую юзернеймы...", reply_markup=None)
        batch = await _unp_generate(tg_id, sess["cfg"])
        sess["running"] = False
        sess["history"].append(batch)
        sess["current_idx"] = len(sess["history"]) - 1
        await query.message.reply_text(_unp_format(batch, sess["current_idx"], len(sess["history"])), reply_markup=_unp_result_kb(sess), disable_web_page_preview=True)
        return "UNPARSER"

    if data == "unp_next":
        if tg_id not in UNPARSER_SESSIONS:
            return "UNPARSER"
        sess = UNPARSER_SESSIONS[tg_id]
        if sess.get("running"):
            return "UNPARSER"
        if sess["current_idx"] < len(sess["history"]) - 1:
            sess["current_idx"] += 1
            batch = sess["history"][sess["current_idx"]]
            await query.message.reply_text(_unp_format(batch, sess["current_idx"], len(sess["history"])), reply_markup=_unp_result_kb(sess), disable_web_page_preview=True)
        else:
            sess["running"] = True
            await query.message.reply_text("⏳ Генерирую новый батч...", reply_markup=None)
            batch = await _unp_generate(tg_id, sess["cfg"])
            sess["running"] = False
            sess["history"].append(batch)
            sess["current_idx"] = len(sess["history"]) - 1
            await query.message.reply_text(_unp_format(batch, sess["current_idx"], len(sess["history"])), reply_markup=_unp_result_kb(sess), disable_web_page_preview=True)
        return "UNPARSER"

    if data == "unp_prev":
        if tg_id not in UNPARSER_SESSIONS:
            return "UNPARSER"
        sess = UNPARSER_SESSIONS[tg_id]
        if sess["current_idx"] > 0:
            sess["current_idx"] -= 1
            batch = sess["history"][sess["current_idx"]]
            await query.message.reply_text(_unp_format(batch, sess["current_idx"], len(sess["history"])), reply_markup=_unp_result_kb(sess), disable_web_page_preview=True)
        return "UNPARSER"

    if data == "u_partner":
        mirrors   = load_mirrors()
        stats     = get_mirror_stats(tg_id)
        has_mirror = tg_id in mirrors and mirrors[tg_id].get("active")
        token_hint = mirrors[tg_id].get("token", "")[:10] + "..." if has_mirror else "не подключён"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 Отключить зеркало" if has_mirror else "➕ Подключить свой бот", callback_data="partner_toggle")],
            [InlineKeyboardButton("📊 Статистика рефералов", callback_data="partner_stats")],
            [InlineKeyboardButton("◀️ Назад", callback_data="u_other")]
        ])
        await send_plain(query.message, f"🪞 Партнёрская программа\n\nПодключи своего бота — он станет зеркалом UserBot | Ru.\nЗа каждого нового юзера который зарегистрируется через твой бот\nты получаешь +1 день к подписке.\n\nСтатус: {'🟢 Активно' if has_mirror else '🔴 Не подключено'}\nТокен: {token_hint}\nРефералов: {stats['total']}\nБонусных дней заработано: {stats['bonus_days']}", kb)
        return "MENU"

    if data == "partner_stats":
        refs = load_referrals()
        my_refs = [(uid, info) for uid, info in refs.items() if info.get("partner_id") == tg_id]
        users_all = load_json(USERS_FILE)
        lines = []
        for uid, info in my_refs[-10:]:
            nick = users_all.get(uid, {}).get("nick", uid)
            lines.append(f"  • {nick} — {info.get('date','?')}")
        total = len(my_refs)
        txt = f"📊 Ваши рефералы\n\nВсего: {total}\nБонусных дней: {total}\n\n"
        txt += "Последние 10:\n" + "\n".join(lines) if lines else "Рефералов пока нет."
        await send_plain(query.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_partner")]]))
        return "MENU"

    if data == "partner_toggle":
        mirrors = load_mirrors()
        if tg_id in mirrors and mirrors[tg_id].get("active"):
            await stop_mirror_bot(tg_id)
            mirrors[tg_id]["active"] = False
            save_mirrors(mirrors)
            await send_plain(query.message, "🔴 Зеркало отключено.", get_user_kb())
        else:
            await send_plain(query.message, "➕ Подключение зеркала\n\n1. Создай бота через @BotFather командой /newbot\n2. Скопируй токен (выглядит как 123456789:AAF...)\n3. Отправь токен сюда:", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_partner")]]))
            return "WAIT_MIRROR_TOKEN"
        return "MENU"

    if data == "u_info":
        await send_plain(query.message, "ℹ️ UserBot | Ru — Справка\n\n🤖 Бот: @cbet_controller_bot\n📢 Канал: @userbotcbet\n👤 Автор: @cbet_cebep\n\n── Что умеет бот ──\n⚡️ Подключает твой аккаунт через Telethon\n🧩 Модули: спамер, троллинг, roast и др.\n🔧 Системные: автоответчик, ник по времени\n🔍 Парсер юзернеймов\n🪞 Партнёрка — свой зеркальный бот\n\n── Подписки ──\n🆓 Пробная — 5 дней бесплатно\n⭐️ Базовая — 25 звёзд / 30 дней\n👑 Про — 50 звёзд / 30 дней\n\n── Если бот не отвечает ──\n1. Нажми 🔄 Обновить\n2. Напиши /start\n3. Напиши @cbet_cebep\n\n── Команды ──\n/start — главное меню\n/reset_me — сбросить сессию если что-то сломалось", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]))
        return "MENU"

    if data == "u_refresh":
        context.user_data.clear()
        async with _file_lock:
            users = load_json(USERS_FILE)
        u_info = users.get(tg_id, {})
        nick   = u_info.get("nick", "Пользователь")
        status = "🟢 активен" if tg_id in USER_BOTS else "🔴 запускается..."
        if tg_id not in USER_BOTS and u_info.get("api_id") and u_info.get("api_hash"):
            asyncio.create_task(start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"]))
        await send_photo(query.message, PHOTO_MENU, f"🔄 Обновлено!\n\nДобро пожаловать, {nick}!\nЮзербот: {status}", get_user_kb())
        return "MENU"

    if data == "u_logout":
        if tg_id in USER_BOTS:
            try:
                await USER_BOTS[tg_id].disconnect()
                del USER_BOTS[tg_id]
            except Exception:
                pass
        if tg_id in LOADED_MODULES:
            del LOADED_MODULES[tg_id]
        async with _file_lock:
            users_w = load_json(USERS_FILE)
            if tg_id in users_w:
                users_w[tg_id]["authenticated"] = False
                save_json(USERS_FILE, users_w)
        session_file = os.path.join(DATA_DIR, f"session_{tg_id}.session")
        if os.path.exists(session_file):
            try: os.remove(session_file)
            except Exception: pass
        await send_photo(query.message, PHOTO_AUTH, "❌ Сессия сброшена. Юзербот отключён.\n\nНажми кнопку чтобы войти снова:", get_guest_kb())
        return "MENU"

    if data == "u_profile":
        u      = users[tg_id]
        mods   = LOADED_MODULES.get(tg_id, [])
        status = "🟢 Запущен" if tg_id in USER_BOTS else "🔴 Остановлен"
        nick   = u.get("nick", "—")
        phone  = u.get("phone", "—")
        sub_str = _sub_status_text(tg_id)
        plan    = get_plan(tg_id)
        limit   = plan["mod_slots"] if plan["mod_slots"] < 999 else "∞"
        await send_plain(query.message, f"👤 Ваш профиль\n\n🆔 ID: {tg_id}\n🏷 Ник: {nick}\n📱 Телефон: {phone}\n⚡️ Движок: Telethon\n📊 Статус: {status}\n💎 Подписка: {sub_str}\n🧩 Модули: {len(mods)}/{limit}", get_cancel_kb())
        return "MENU"

    if data == "u_sub":
        await _show_sub_menu(query.message, tg_id)
        return "MENU"

    if data == "u_entercode":
        await send_plain(query.message, "🎟 Введи код подписки:\n\nКоды выдаются администратором или приобретаются на канале @userbotcbet", get_cancel_kb())
        return "WAIT_PROMO_ACTIVATE"

    if data == "sub_buy_trial":
        await send_plain(query.message, "ℹ️ Пробная подписка выдаётся автоматически при регистрации.", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_sub")]]))
        return "MENU"

    if data == "sub_buy_pro":
        from telegram import LabeledPrice
        await context.bot.send_invoice(chat_id=query.message.chat_id, title="Про подписка — UserBot | Ru", description="30 дней. Все модули и системные функции разблокированы.", payload=f"sub_pro_{tg_id}", provider_token="", currency="XTR", prices=[LabeledPrice("Про подписка", 100)])
        return "MENU"

    if data.startswith("sub_choose_sys_"):
        parts    = data[len("sub_choose_sys_"):].rsplit("_", 1)
        mod      = parts[0]
        plan_key = parts[1] if len(parts) > 1 else "trial"
        plan     = SUB_PLANS.get(plan_key, SUB_PLANS["trial"])
        sub      = load_sub(tg_id)
        chosen   = sub.get("chosen_sys", [])
        if mod not in chosen:
            chosen.append(mod)
        chosen = chosen[:plan["sys_slots"]]
        sub["chosen_sys"] = chosen
        save_sub(tg_id, sub)
        await send_plain(query.message, "✅ Системный модуль активирован!\n\nТеперь иди в 🔧 Системные модули.", get_user_kb())
        return "MENU"

    if data == "u_sonya":
        await send_photo(query.message, PHOTO_SONYA_SAD, "🤖 Соня — ИИ-ассистент\n\nСоня — персональный ИИ-помощник внутри юзербота.\n\nОна умеет отвечать на вопросы, помогать с настройкой модулей и поддержать разговор в любое время суток.\n\n😴 Сейчас Соня отдыхает...\nФункция ИИ-чата скоро будет доступна!\n\n📢 Канал: @userbotcbet", get_cancel_kb())
        return "SONYA_CHAT"

    if data == "u_modules":
        m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
        async with _file_lock:
            m_data = load_json(m_file)
        used      = len(m_data.get("modules", []))
        mods_list = m_data.get("modules", [])
        if mods_list:
            def _mod_label(m):
                src = m.get("source", "custom")
                badge = "👤" if src == "custom" or src is None else "🛒"
                return f"  {badge} {m['name']}.py — {m.get('date','?')}"
            mods_text = "\n".join(_mod_label(m) for m in mods_list) + "\n\n👤 — свой модуль   🛒 — из магазина"
        else:
            mods_text = "  модули не установлены"
        kb_rows = []
        for m in mods_list:
            src = m.get("source", "custom")
            badge = "👤" if src == "custom" or src is None else "🛒"
            kb_rows.append([InlineKeyboardButton(f"🗑 {badge} {m['name']}.py", callback_data=f"mod_delete_{m['name']}")])
        kb_rows.append([InlineKeyboardButton("🛒 Магазин модулей", callback_data="mod_shop")])
        kb_rows.append([InlineKeyboardButton("➕ Установить своё .py", callback_data="mod_install")])
        kb_rows.append([InlineKeyboardButton("◀️ Назад", callback_data="u_modules_menu")])
        await send_photo(query.message, PHOTO_MODULES, f"🧩 Модули — UserBot | Ru\n\nЗдесь ты управляешь плагинами своего юзербота.\nМодули загружаются прямо в Telethon-сессию.\n\nСлотов занято: {used}/5\n\nУстановленные модули:\n{mods_text}\n\nНажми на модуль чтобы удалить его.", InlineKeyboardMarkup(kb_rows))
        return "MENU"

    if data.startswith("mod_delete_"):
        mod_name = data[len("mod_delete_"):]
        m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
        async with _file_lock:
            m_data = load_json(m_file)
            before = len(m_data.get("modules", []))
            m_data["modules"] = [m for m in m_data.get("modules", []) if m["name"] != mod_name]
            after = len(m_data["modules"])
            save_json(m_file, m_data)
        mod_path = os.path.join(MODULES_DIR, f"user_{tg_id}", f"{mod_name}.py")
        if os.path.exists(mod_path):
            try: os.remove(mod_path)
            except Exception as e: logger.error(f"Ошибка удаления {mod_path}: {e}")
        if tg_id in LOADED_MODULES and mod_name in LOADED_MODULES[tg_id]:
            LOADED_MODULES[tg_id].remove(mod_name)
        if before != after:
            await send_plain(query.message, f"🗑 Модуль {mod_name}.py удалён.", None)
            if tg_id in USER_BOTS:
                async with _file_lock:
                    users_reload = load_json(USERS_FILE)
                u_info = users_reload.get(tg_id, {})
                if u_info.get("api_id") and u_info.get("api_hash"):
                    await start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"])
        else:
            await send_plain(query.message, f"⚠️ Модуль {mod_name} не найден.", None)
        async with _file_lock:
            m_data = load_json(m_file)
        used      = len(m_data.get("modules", []))
        mods_list = m_data.get("modules", [])
        mods_text = "\n".join(f"  {'👤' if m.get('source','custom') in ('custom', None) else '🛒'} {m['name']}.py — {m.get('date','?')}" for m in mods_list) + "\n\n👤 — свой   🛒 — магазин" if mods_list else "  модули не установлены"
        kb_rows = [[InlineKeyboardButton(f"🗑 {m['name']}.py", callback_data=f"mod_delete_{m['name']}")] for m in mods_list]
        kb_rows.append([InlineKeyboardButton("➕ Установить модуль", callback_data="mod_install")])
        kb_rows.append([InlineKeyboardButton("◀️ Назад", callback_data="u_modules_menu")])
        await send_photo(query.message, PHOTO_MODULES, f"🧩 Модули — UserBot | Ru\n\nСлотов занято: {used}/5\n\nУстановленные модули:\n{mods_text}\n\nНажми на модуль чтобы удалить его.", InlineKeyboardMarkup(kb_rows))
        return "MENU"

    if data == "mod_install":
        await send_plain(query.message, "🔗 Отправьте прямую ссылку на .py плагин\nили прикрепите файл документом:", get_cancel_kb())
        return "MODULE_INSTALL"

    if data == "u_sysmods":
        await _show_sysmods(query.message, tg_id, "main")
        return "MENU"

    if data == "u_sysmods_autoreply":
        await _show_sysmods(query.message, tg_id, "autoreply")
        return "MENU"

    if data == "u_sysmods_timenick":
        await _show_sysmods(query.message, tg_id, "timenick")
        return "MENU"

    if data == "sysmod_autoreply_toggle":
        cfg = _load_autoreply_cfg(tg_id)
        cfg["enabled"] = not cfg.get("enabled", False)
        _save_autoreply_cfg(tg_id, cfg)
        await _show_sysmods(query.message, tg_id, "autoreply")
        return "MENU"

    if data.startswith("sysmod_mode_"):
        cfg = _load_autoreply_cfg(tg_id)
        cfg["mode"] = data[len("sysmod_mode_"):]
        _save_autoreply_cfg(tg_id, cfg)
        await _show_sysmods(query.message, tg_id, "autoreply")
        return "MENU"

    if data.startswith("sysmod_style_"):
        cfg = _load_autoreply_cfg(tg_id)
        cfg["style"] = data[len("sysmod_style_"):]
        _save_autoreply_cfg(tg_id, cfg)
        await _show_sysmods(query.message, tg_id, "autoreply")
        return "MENU"

    if data == "sysmod_timenick_toggle":
        cfg     = _load_timenick_cfg(tg_id)
        enabled = not cfg.get("enabled", False)
        cfg["enabled"] = enabled
        _save_timenick_cfg(tg_id, cfg)
        client = USER_BOTS.get(tg_id)
        if client:
            if enabled and cfg.get("nickname"):
                asyncio.create_task(client._timenick_start(tg_id))
            else:
                client._timenick_stop(tg_id)
        await _show_sysmods(query.message, tg_id, "timenick")
        return "MENU"

    if data == "sysmod_timenick_setnick":
        await send_plain(query.message, "✏️ Введи никнейм (без времени):\nПример: cbet_cebep\n\nБот сам добавит | HH:MM", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods_timenick")]]))
        context.user_data["await_timenick"] = "nick"
        return "WAIT_TIMENICK"

    if data == "sysmod_timenick_setsec":
        await send_plain(query.message, "⏱ Введи секунду обновления (0-59):\n\nНапример: 0 — обновление в начале каждой минуты\n30 — обновление на 30-й секунде каждой минуты", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods_timenick")]]))
        context.user_data["await_timenick"] = "second"
        return "WAIT_TIMENICK"

    if data == "sysmod_timenick_settz":
        cfg = _load_timenick_cfg(tg_id)
        cur = cfg.get("tz_offset", 3)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("UTC+2", callback_data="sysmod_tz_2"), InlineKeyboardButton("UTC+3 (МСК)", callback_data="sysmod_tz_3"), InlineKeyboardButton("UTC+4", callback_data="sysmod_tz_4")],
            [InlineKeyboardButton("UTC+5", callback_data="sysmod_tz_5"), InlineKeyboardButton("UTC+6", callback_data="sysmod_tz_6"), InlineKeyboardButton("UTC+7", callback_data="sysmod_tz_7")],
            [InlineKeyboardButton("✏️ Ввести вручную", callback_data="sysmod_timenick_settz_manual")],
            [InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods_timenick")]
        ])
        await send_plain(query.message, f"🌍 Выбери часовой пояс\n\nСейчас: UTC+{cur}", kb)
        return "MENU"

    if data.startswith("sysmod_tz_"):
        offset = int(data[len("sysmod_tz_"):])
        cfg = _load_timenick_cfg(tg_id)
        cfg["tz_offset"] = offset
        _save_timenick_cfg(tg_id, cfg)
        if USER_BOTS.get(tg_id) and cfg.get("enabled"):
            client = USER_BOTS[tg_id]
            client._timenick_stop(tg_id)
            asyncio.create_task(client._timenick_start(tg_id))
        await _show_sysmods(query.message, tg_id, "timenick")
        return "MENU"

    if data == "sysmod_timenick_settz_manual":
        await send_plain(query.message, "🌍 Введи смещение от UTC (целое число):\n\nПримеры: 3 (Москва), 5 (Екб), -5 (США EST)", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods_timenick")]]))
        context.user_data["await_timenick"] = "tz"
        return "WAIT_TIMENICK"

    if data == "mod_shop":
        stock = []
        if os.path.exists(STOCK_MODULES_DIR):
            for fname in sorted(os.listdir(STOCK_MODULES_DIR)):
                if fname.endswith(".py"):
                    stock.append(fname[:-3])
        if not stock:
            await send_plain(query.message, "🛒 Магазин пока пуст. Скоро появятся модули!", get_cancel_kb())
            return "MENU"
        m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
        async with _file_lock:
            m_data = load_json(m_file)
        installed = {m["name"] for m in m_data.get("modules", [])}
        kb_rows = []
        lines = []
        for mod in stock:
            if mod in installed:
                kb_rows.append([InlineKeyboardButton(f"✅ {mod} (установлен)", callback_data="mod_shop")])
                lines.append(f"  ✅ {mod}.py — установлен")
            else:
                kb_rows.append([InlineKeyboardButton(f"📥 {mod}", callback_data=f"mod_get_{mod}")])
                lines.append(f"  📥 {mod}.py")
        kb_rows.append([InlineKeyboardButton("◀️ Назад", callback_data="u_modules")])
        await send_photo(query.message, PHOTO_MODULES, "🛒 Магазин модулей\n\nВыбери модуль для установки:\n\n" + "\n".join(lines) + "\n\nНажми на модуль чтобы установить.", InlineKeyboardMarkup(kb_rows))
        return "MENU"

    if data.startswith("mod_get_"):
        mod_name = data[len("mod_get_"):]
        src_path = os.path.join(STOCK_MODULES_DIR, f"{mod_name}.py")
        if not os.path.exists(src_path):
            await send_plain(query.message, f"❌ Модуль {mod_name} не найден в магазине.", get_cancel_kb())
            return "MENU"
        m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
        async with _file_lock:
            m_data = load_json(m_file)
        current = len(m_data.get("modules", []))
        plan    = get_plan(tg_id)
        limit   = plan["mod_slots"]
        if current >= limit:
            await send_plain(query.message, f"⚠️ Достигнут лимит модулей ({current}/{limit}) для твоей подписки.\nУлучши подписку в разделе 💎 Подписка.", get_user_kb())
            return "MENU"
        import shutil
        user_dir = os.path.join(MODULES_DIR, f"user_{tg_id}")
        os.makedirs(user_dir, exist_ok=True)
        shutil.copy2(src_path, os.path.join(user_dir, f"{mod_name}.py"))
        menu_src = os.path.join(STOCK_MODULES_DIR, f"{mod_name}_menu.json")
        if os.path.exists(menu_src):
            shutil.copy2(menu_src, os.path.join(user_dir, f"{mod_name}_menu.json"))
        async with _file_lock:
            m_data.setdefault("modules", [])
            if not any(m["name"] == mod_name for m in m_data["modules"]):
                m_data["modules"].append({"name": mod_name, "date": datetime.now().strftime("%d.%m.%Y"), "source": "shop"})
            save_json(m_file, m_data)
        if tg_id in USER_BOTS:
            async with _file_lock:
                users_reload = load_json(USERS_FILE)
            u_info = users_reload.get(tg_id, {})
            if u_info.get("api_id") and u_info.get("api_hash"):
                await start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"])
            await send_plain(query.message, f"✅ Модуль {mod_name}.py установлен и загружен в юзербот!", None)
        else:
            await send_plain(query.message, f"✅ Модуль {mod_name}.py установлен. Запустите юзербота для активации.", None)
        stock = [f[:-3] for f in sorted(os.listdir(STOCK_MODULES_DIR)) if f.endswith(".py")]
        async with _file_lock:
            m_data = load_json(m_file)
        installed = {m["name"] for m in m_data.get("modules", [])}
        kb_rows = []
        lines = []
        for mod in stock:
            if mod in installed:
                kb_rows.append([InlineKeyboardButton(f"✅ {mod} (установлен)", callback_data="mod_shop")])
                lines.append(f"  ✅ {mod}.py — установлен")
            else:
                kb_rows.append([InlineKeyboardButton(f"📥 {mod}", callback_data=f"mod_get_{mod}")])
                lines.append(f"  📥 {mod}.py")
        kb_rows.append([InlineKeyboardButton("◀️ Назад", callback_data="u_modules")])
        await send_photo(query.message, PHOTO_MODULES, "🛒 Магазин модулей\n\n" + "\n".join(lines) + "\n\nНажми на модуль чтобы установить.", InlineKeyboardMarkup(kb_rows))
        return "MENU"

    if data == "u_screenlock":
        context.user_data["sl_step"] = "wait_password"
        await send_plain(query.message, "🔒 ScreenLock\n\n⚠️ Тестовый модуль\n\nВведи пароль для доступа:", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_modules_menu")]]))
        return "SCREENLOCK"

    if data == "sl_menu":
        await send_plain(query.message, "🔒 ScreenLock\n\nСоздай агента для удалённого управления ПК компании.\n\nКак работает:\n1. Вводишь токен Telegram-бота\n2. Выбираешь формат\n3. Получаешь архив с программой\n4. Запускаешь на нужном ПК\n5. Управляешь через того бота\n\n1 токен = 1 ПК\n\n📢 @userbotcbet", InlineKeyboardMarkup([[InlineKeyboardButton("➕ Создать агента", callback_data="sl_create")],[InlineKeyboardButton("◀️ Назад", callback_data="u_modules_menu")]]))
        return "SCREENLOCK"

    if data == "sl_create":
        context.user_data["sl_step"] = "wait_token"
        await send_plain(query.message, "🔒 ScreenLock — Создание агента\n\nШаг 1/2: Введи токен бота\n\nПолучить токен: @BotFather → /newbot\nФормат: 1234567890:AAFxxxxxxxxxxxxxxxxxxxxxxx", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="sl_menu")]]))
        return "SCREENLOCK"

    if data == "sl_format_exe":
        token = context.user_data.get("sl_token", "")
        if not token:
            await query.answer("❌ Токен не найден, начни заново.", show_alert=True)
            return "SCREENLOCK"
        context.user_data["sl_step"] = None
        msg = await query.message.reply_text("⚙️ Генерирую агента, подожди...")
        try:
            import zipfile, io
            pc_code = _screenlock_generate_code(token)
            readme  = _screenlock_readme()
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("ScreenLock_agent/bot.py",          pc_code)
                zf.writestr("ScreenLock_agent/requirements.txt", "python-telegram-bot==20.7\npsutil\npyautogui\nPillow\n")
                zf.writestr("ScreenLock_agent/README.txt",       readme)
                zf.writestr("ScreenLock_agent/start.bat",        "@echo off\npip install -r requirements.txt\npython bot.py\npause\n")
            zip_buf.seek(0)
            await msg.delete()
            await query.message.reply_document(document=zip_buf, filename="ScreenLock_agent.zip", caption="✅ ScreenLock агент готов!\n\n📋 Инструкция внутри архива (README.txt)\n\nБыстрый старт:\n1. Распакуй архив на ПК\n2. Запусти start.bat\n3. Открой бота в Telegram → /start\n\n🔒 @userbotcbet")
        except Exception as e:
            await msg.edit_text(f"❌ Ошибка: {e}")
        return "SCREENLOCK"

    if data == "sl_format_apk":
        await query.answer("🚧 APK — скоро будет!", show_alert=True)
        return "SCREENLOCK"

    if data == "u_sysmods_cryptobio":
        return await cryptobio_router(update, context)

    if data.startswith("cbio_"):
        return await cryptobio_router(update, context)

    return "MENU"


async def login_phone_existing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        await send_plain(update.message, "⚠️ Неверный формат. Пример: +79001234567\n\nПовторите ввод:", get_cancel_kb())
        return "LOGIN_PHONE_EXISTING"
    async with _file_lock:
        users = load_json(USERS_FILE)
    found_id, found_user = None, None
    for uid, udata in users.items():
        if udata.get("phone") == phone:
            found_id, found_user = uid, udata
            break
    if not found_id:
        await send_photo(update.message, PHOTO_AUTH, f"❌ Номер {phone} не найден в системе.\n\nЕсли ты новый пользователь — используй Регистрацию.", get_guest_kb())
        return "MENU"
    if not found_user.get("api_id") or not found_user.get("api_hash"):
        await send_photo(update.message, PHOTO_AUTH, "⚠️ Данные аккаунта повреждены. Необходима повторная регистрация.", get_guest_kb())
        return "MENU"
    context.user_data["phone"]             = phone
    context.user_data["api_id"]            = int(found_user["api_id"])
    context.user_data["api_hash"]          = found_user["api_hash"]
    context.user_data["reg_nick"]          = found_user.get("nick", f"User_{found_id[:4]}")
    context.user_data["login_existing_id"] = found_id
    session_file = os.path.join(DATA_DIR, f"session_{found_id}.session")
    if os.path.exists(session_file):
        await send_plain(update.message, "⏳ Восстанавливаем сессию...", None)
        try:
            await start_user_bot(found_id, int(found_user["api_id"]), found_user["api_hash"])
            if found_id in USER_BOTS:
                async with _file_lock:
                    users_w = load_json(USERS_FILE)
                    users_w[found_id]["authenticated"] = True
                    save_json(USERS_FILE, users_w)
                nick = found_user.get("nick", "Пользователь")
                await send_photo(update.message, PHOTO_MENU, f"🎉 Добро пожаловать обратно, {nick}!\n\nЮзербот восстановлен и активен.\n\nВыбери раздел:", get_user_kb())
                return "MENU"
        except Exception as e:
            logger.warning(f"Не удалось восстановить сессию {found_id}: {e}")
    await send_plain(update.message, "⏳ Сессия истекла, запрашиваем новый код...", None)
    session_path = os.path.join(DATA_DIR, f"session_{found_id}")
    client = TelegramClient(session_path, int(found_user["api_id"]), found_user["api_hash"])
    try:
        await client.connect()
        sent_code = await client.send_code_request(phone, force_sms=True)
        context.user_data["client"]          = client
        context.user_data["phone_code_hash"] = sent_code.phone_code_hash
        context.user_data["pin_entered"]     = ""
        await send_photo(update.message, PHOTO_AUTH, "📩 Код отправлен!\n\nTelegram прислал код в приложение.\nВведи его через пин-пад ниже 👇", get_pinpad_kb(""))
        return "WAIT_CODE"
    except Exception as e:
        logger.error(f"Ошибка при повторном входе {found_id}: {e}")
        await send_photo(update.message, PHOTO_AUTH, f"❌ Ошибка: {e}\n\nПопробуй снова — /start", get_guest_kb())
        return "MENU"


async def reg_nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nick = update.message.text.strip()
    async with _file_lock:
        users = load_json(USERS_FILE)
    taken = any(v.get("nick", "").lower() == nick.lower() for v in users.values())
    if taken:
        await send_plain(update.message, f"⚠️ Никнейм {nick} уже занят. Введите другой:", get_cancel_kb())
        return "REG_NICK"
    context.user_data["reg_nick"] = nick
    await send_photo(update.message, PHOTO_AUTH, "📱 Авторизация — Шаг 2 из 4\n\nВведи номер телефона привязанный к твоему Telegram-аккаунту.\n\nНа него придёт код подтверждения от Telegram.\nФормат: +79001234567 или +380XXXXXXXXX\n\nМы не используем номер для рассылок.", get_cancel_kb())
    return "LOGIN_PHONE"


async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        await send_plain(update.message, "⚠️ Неверный формат. Пример: +79001234567\n\nПовторите ввод:", get_cancel_kb())
        return "LOGIN_PHONE"
    async with _file_lock:
        users = load_json(USERS_FILE)
    taken = any(v.get("phone", "") == phone and v.get("authenticated", False) for v in users.values())
    if taken:
        await send_plain(update.message, f"⚠️ Номер {phone} уже зарегистрирован в системе.\n\nЕсли это ваш номер — используй кнопку Войти.", get_cancel_kb())
        return "LOGIN_PHONE"
    context.user_data["phone"] = phone
    await send_photo(update.message, PHOTO_AUTH, "🔑 Авторизация — Шаг 3 из 4\n\nВведи свой API ID — числовой идентификатор приложения Telegram.\n\nКак получить:\n1. Зайди на my.telegram.org\n2. Войди в свой аккаунт\n3. Раздел API development tools\n4. Скопируй поле api_id\n\nВыглядит как число: 12345678\n\nПомощь: @userbotcbet", get_cancel_kb())
    return "LOGIN_API_ID"


async def login_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    if not val.isdigit():
        await send_plain(update.message, "⚠️ API ID — только цифры. Повторите ввод:", get_cancel_kb())
        return "LOGIN_API_ID"
    context.user_data["api_id"] = int(val)
    await send_photo(update.message, PHOTO_AUTH, "🔑 Авторизация — Шаг 4 из 4\n\nВведи свой API Hash — секретный ключ приложения Telegram.\n\nГде найти:\nТот же раздел на my.telegram.org\nПоле api_hash\n\nВыглядит так: a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6\n\nКлюч хранится только на сервере.\n\nПомощь: @userbotcbet", get_cancel_kb())
    return "LOGIN_API_HASH"


async def login_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id    = str(update.effective_user.id)
    api_hash = update.message.text.strip()
    phone    = context.user_data["phone"]
    api_id   = context.user_data["api_id"]
    context.user_data["api_hash"] = api_hash
    await send_plain(update.message, "⏳ Инициализация сессии Telethon...", None)
    session_path = os.path.join(DATA_DIR, f"session_{tg_id}")
    client = TelegramClient(session_path, api_id, api_hash)
    try:
        await client.connect()
        sent_code = await client.send_code_request(phone, force_sms=True)
        context.user_data["client"]          = client
        context.user_data["phone_code_hash"] = sent_code.phone_code_hash
        context.user_data["pin_entered"]     = ""
        await send_photo(update.message, PHOTO_AUTH, "📩 Код подтверждения отправлен!\n\nTelegram прислал тебе код в приложение или SMS.\n\nВведи его с помощью пин-пада ниже.\nКод действителен несколько минут — не затягивай!", get_pinpad_kb(""))
        return "WAIT_CODE"
    except Exception as e:
        logger.error(f"Telethon send_code error для {tg_id}: {e}")
        try: await client.disconnect()
        except Exception: pass
        await send_photo(update.message, PHOTO_AUTH, f"❌ Ошибка API Telegram: {e}\n\nПопробуйте снова — /start", get_guest_kb())
        return "MENU"


async def pinpad_click_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    tg_id   = str(query.from_user.id)
    data    = query.data
    await query.answer()
    entered = context.user_data.get("pin_entered", "")
    if data == "pin_noop":
        return "WAIT_CODE"
    if data.startswith("pin_digit_"):
        digit = data.split("_")[-1]
        if len(entered) < 10:
            entered += digit
        context.user_data["pin_entered"] = entered
        try: await query.edit_message_reply_markup(reply_markup=get_pinpad_kb(entered))
        except Exception: pass
        return "WAIT_CODE"
    if data == "pin_back":
        entered = entered[:-1]
        context.user_data["pin_entered"] = entered
        try: await query.edit_message_reply_markup(reply_markup=get_pinpad_kb(entered))
        except Exception: pass
        return "WAIT_CODE"
    if data == "pin_submit":
        if not entered:
            await query.answer("⚠️ Введите код!", show_alert=True)
            return "WAIT_CODE"
        return await _do_sign_in(update, context, tg_id, entered)
    return "WAIT_CODE"

async def _cleanup_failed_session(tg_id: str, client):
    try: await client.disconnect()
    except Exception: pass
    for ext in (".session", ".session-journal"):
        p = os.path.join(DATA_DIR, f"session_{tg_id}{ext}")
        if os.path.exists(p):
            try: os.remove(p)
            except Exception: pass
    if tg_id in USER_BOTS:
        del USER_BOTS[tg_id]

async def _finish_auth(update, context, tg_id: str, client):
    phone = context.user_data.get("phone")
    nick  = context.user_data.get("reg_nick", f"User_{tg_id[:4]}")
    async with _file_lock:
        users = load_json(USERS_FILE)
        users[tg_id] = {"nick": nick, "phone": phone, "api_id": context.user_data["api_id"], "api_hash": context.user_data["api_hash"], "authenticated": True, "created_at": datetime.now().strftime("%d.%m.%Y %H:%M")}
        save_json(USERS_FILE, users)
    USER_BOTS[tg_id] = client
    load_user_modules(client, tg_id)
    msg = update.callback_query.message if update.callback_query else update.message
    sub    = load_sub(tg_id)
    is_new = not sub.get("plan")
    if is_new:
        from datetime import timezone, timedelta
        expires = (datetime.now(timezone.utc) + timedelta(days=5)).timestamp()
        sub["plan"] = "trial"; sub["expires"] = expires; sub["chosen_sys"] = []; sub["chosen_mods"] = []
        save_sub(tg_id, sub)
    if is_new:
        await send_photo(msg, PHOTO_MENU, f"🎉 Добро пожаловать, {nick}!\n\nТвой юзербот успешно запущен в облаке.\n\n🆓 Тебе выдана пробная подписка на 5 дней!\n\nДля полного доступа купи 👑 Про подписку в разделе 💎 Подписка.\n\nВыбери раздел:", get_user_kb())
    else:
        await send_photo(msg, PHOTO_MENU, f"🎉 Добро пожаловать, {nick}!\n\nТвой юзербот успешно запущен в облаке.\n\n⚡️ Сессия Telethon активна\n🧩 Модули готовы к установке\n\nВыбери раздел:", get_user_kb())
    return "MENU"

async def _do_sign_in(update, context, tg_id: str, code: str):
    query           = update.callback_query
    client          = context.user_data.get("client")
    phone_code_hash = context.user_data.get("phone_code_hash")
    phone           = context.user_data.get("phone")
    try:
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        return await _finish_auth(update, context, tg_id, client)
    except SessionPasswordNeededError:
        context.user_data["awaiting_2fa"] = True
        await send_photo(query.message, PHOTO_AUTH, "🔐 Двухфакторная аутентификация\n\nНа твоём аккаунте включён облачный пароль (2FA).\n\nВведи пароль который ты задал в настройках Telegram:\nНастройки → Конфиденциальность → Облачный пароль\n\nПароль передаётся напрямую в Telegram и не сохраняется.", get_cancel_kb())
        return "WAIT_2FA"
    except Exception as e:
        logger.error(f"sign_in error для {tg_id}: {e}")
        await _cleanup_failed_session(tg_id, client)
        await send_photo(query.message, PHOTO_AUTH, f"❌ Ошибка входа: {e}\n\nПопробуйте снова — /start", get_guest_kb())
        return "MENU"


async def wait_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id    = str(update.effective_user.id)
    password = update.message.text.strip()
    client   = context.user_data.get("client")
    try:
        await client.sign_in(password=password)
        return await _finish_auth(update, context, tg_id, client)
    except Exception as e:
        logger.error(f"2FA error для {tg_id}: {e}")
        await _cleanup_failed_session(tg_id, client)
        await send_photo(update.message, PHOTO_AUTH, f"❌ Неверный пароль 2FA: {e}\n\nПопробуйте снова — /start", get_guest_kb())
        return "MENU"


async def module_download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id     = str(update.effective_user.id)
    code_text = ""
    mod_name  = f"module_{random.randint(1000, 9999)}"
    if update.message.document:
        doc = update.message.document
        if not doc.file_name.endswith(".py"):
            await send_plain(update.message, "❌ Принимаются только .py файлы.", get_cancel_kb())
            return "MODULE_INSTALL"
        mod_name  = doc.file_name[:-3]
        tg_file   = await context.bot.get_file(doc.file_id)
        raw       = await tg_file.download_as_bytearray()
        code_text = raw.decode("utf-8", errors="ignore")
    elif update.message.text:
        url = update.message.text.strip()
        if url.startswith("http") and url.endswith(".py"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            code_text = await resp.text()
                            mod_name  = url.split("/")[-1][:-3]
                        else:
                            await send_plain(update.message, f"❌ Ошибка загрузки: HTTP {resp.status}", get_cancel_kb())
                            return "MODULE_INSTALL"
            except Exception as e:
                await send_plain(update.message, f"❌ Не удалось скачать файл: {e}", get_cancel_kb())
                return "MODULE_INSTALL"
        else:
            await send_plain(update.message, "❌ Отправьте прямую ссылку на .py файл или прикрепите файл документом.", get_cancel_kb())
            return "MODULE_INSTALL"
    if not code_text:
        await send_plain(update.message, "❌ Файл пуст.", get_user_kb())
        return "MENU"
    m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
    async with _file_lock:
        m_data = load_json(m_file)
    current = len(m_data.get("modules", []))
    plan    = get_plan(tg_id)
    limit   = plan["mod_slots"]
    if current >= limit:
        await send_plain(update.message, f"⚠️ Достигнут лимит модулей ({current}/{limit}) для твоей подписки.\nУлучши подписку в разделе 💎 Подписка.", get_user_kb())
        return "MENU"
    user_dir = os.path.join(MODULES_DIR, f"user_{tg_id}")
    os.makedirs(user_dir, exist_ok=True)
    with open(os.path.join(user_dir, f"{mod_name}.py"), "w", encoding="utf-8") as f:
        f.write(code_text)
    async with _file_lock:
        m_data.setdefault("modules", [])
        m_data["modules"].append({"name": mod_name, "date": datetime.now().strftime("%d.%m.%Y"), "source": "custom"})
        save_json(m_file, m_data)
    if tg_id in USER_BOTS:
        async with _file_lock:
            users = load_json(USERS_FILE)
        u_info = users.get(tg_id, {})
        await start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"])
        await send_plain(update.message, f"✅ Модуль {mod_name}.py установлен и загружен в юзербот!", get_user_kb())
    else:
        await send_plain(update.message, f"✅ Модуль {mod_name}.py сохранён. Запустите юзербота для активации.", get_user_kb())
    return "MENU"


async def so2_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    text  = update.message.text.strip()

    if context.user_data.get("so2_await_pass"):
        context.user_data.pop("so2_await_pass", None)
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_modules_menu")]])
        if text != ADMIN_PASSWORD:
            await send_plain(update.message, "❌ Неверный пароль.\n\n🎮 Standoff 2 модуль сейчас в разработке.\nСледи за обновлениями на канале @userbotcbet", back_kb)
            return "MENU"
        profile = get_so2_user(tg_id)
        registered = bool(profile.get("so2_id"))
        if registered:
            so2_id = profile.get("so2_id", "—"); gold = profile.get("gold", "не указан"); nick = profile.get("nick", "—")
            text_msg = f"🎮 Standoff 2\n\n👤 Ник: {nick}\n🆔 ID: {so2_id}\n💰 Gold: {gold}\n\nВыбери действие:"
        else:
            text_msg = "🎮 Standoff 2\n\nТы ещё не зарегистрирован.\nЗарегистрируйся чтобы сохранить профиль."
        await send_plain(update.message, text_msg, so2_main_kb(registered))
        return "SO2"

    step  = context.user_data.get("so2_step")
    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_so2")]])
    if not step:
        return "SO2"

    if step == "search":
        context.user_data.pop("so2_step", None)
        if tg_id not in USER_BOTS:
            await send_plain(update.message, "⚠️ Юзербот не запущен. Нажми Обновить или /start.", back_kb)
            return "SO2"
        msg = await update.message.reply_text(f"⏳ Ищу игрока {text}...")
        result = await so2_fetch(tg_id, text)
        if result:
            await msg.edit_text(f"Профиль игрока:\n\n{result}\n\n@userbotcbet", reply_markup=back_kb)
        else:
            await msg.edit_text("Игрок не найден или ошибка. Проверь ID.", reply_markup=back_kb)
        return "SO2"

    if step == "login_nick":
        context.user_data["so2_data"]["nick"] = text
        context.user_data["so2_step"] = "login_id"
        await send_plain(update.message, "🔑 Вход — Шаг 2/2\n\nВведи свой Standoff 2 ID:", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="u_so2")]]))
        return "SO2"

    if step == "login_id":
        nick = context.user_data.get("so2_data", {}).get("nick", "")
        so2_id = text
        context.user_data.pop("so2_step", None); context.user_data.pop("so2_data", None)
        save_so2_user(tg_id, {"so2_id": so2_id, "nick": nick, "gold": ""})
        await send_plain(update.message, f"✅ Вход выполнен!\n\n👤 Ник: {nick}\n🆔 ID: {so2_id}\n\nТеперь можешь смотреть профиль", InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Открыть SO2", callback_data="u_so2_enter")]]))
        return "SO2"

    if step == "nick":
        context.user_data["so2_data"]["nick"] = text
        context.user_data["so2_step"] = "id"
        await send_plain(update.message, "📝 Регистрация — Шаг 2/2\n\nВведи свой Standoff 2 ID:\n(Найти в профиле игры под никнеймом)", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="u_so2")]]))
        return "SO2"

    if step == "id":
        context.user_data["so2_data"]["so2_id"] = text
        context.user_data["so2_data"]["gold"] = ""
        data = context.user_data.pop("so2_data", {}); context.user_data.pop("so2_step", None)
        save_so2_user(tg_id, data)
        await send_plain(update.message, f"Профиль сохранён!\n\nНик: {data.get('nick','?')}\nID: {data.get('so2_id','?')}\n\nТеперь можешь смотреть статистику.", InlineKeyboardMarkup([[InlineKeyboardButton("Открыть SO2", callback_data="u_so2")]]))
        return "SO2"

    return "SO2"


async def osint_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    text  = update.message.text.strip()
    if tg_id not in OSINT_SESSIONS:
        return "MENU"
    sess = OSINT_SESSIONS[tg_id]
    step = sess["step"]
    if text.lower() == "/skip":
        _, _, skippable = OSINT_FIELDS[step]
        if not skippable:
            await send_plain(update.message, "⚠️ Это поле обязательное, его нельзя пропустить.", _osint_required_kb())
            return "OSINT"
        step += 1
    else:
        key = OSINT_FIELDS[step][0]
        sess["data"][key] = text
        step += 1
    if step >= len(OSINT_FIELDS):
        tree = _osint_build_tree(sess["data"])
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Новое расследование", callback_data="u_osint")],[InlineKeyboardButton("◀️ В меню", callback_data="back_main")]])
        await send_plain(update.message, tree, kb)
        del OSINT_SESSIONS[tg_id]
        return "MENU"
    sess["step"] = step
    _, _, skippable = OSINT_FIELDS[step]
    kb = _osint_skip_kb() if skippable else _osint_required_kb()
    await send_plain(update.message, _osint_step_text(step, sess["data"]), kb)
    return "OSINT"


async def unparser_password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    if not context.user_data.get("await_unparser_pass"):
        return "UNPARSER"
    password = update.message.text.strip()
    context.user_data.pop("await_unparser_pass", None)
    if password != ADMIN_PASSWORD:
        await send_plain(update.message, "❌ Неверный пароль.", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]))
        return "MENU"
    if tg_id not in UNPARSER_SESSIONS:
        UNPARSER_SESSIONS[tg_id] = {"cfg": {"length": 8, "digits": True, "count": 5}, "history": [], "current_idx": -1, "running": False}
    cfg = UNPARSER_SESSIONS[tg_id]["cfg"]
    await send_plain(update.message, _unp_menu_text(cfg), _unp_menu_kb(cfg))
    return "UNPARSER"


async def wait_mirror_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    token = update.message.text.strip()
    if ":" not in token or len(token) < 30:
        await send_plain(update.message, "❌ Неверный формат токена.\nТокен выглядит так: 123456789:AAFxxxxxxxx\nПопробуй ещё раз:", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_partner")]]))
        return "WAIT_MIRROR_TOKEN"
    mirrors = load_mirrors()
    active_count = sum(1 for m in mirrors.values() if m.get("active"))
    if active_count >= MAX_MIRRORS and tg_id not in mirrors:
        await send_plain(update.message, f"⚠️ Достигнут лимит зеркал ({MAX_MIRRORS}). Попробуй позже.", get_user_kb())
        return "MENU"
    await send_plain(update.message, "⏳ Проверяем токен...", None)
    try:
        import aiohttp as _aio
        async with _aio.ClientSession() as sess:
            async with sess.get(f"https://api.telegram.org/bot{token}/getMe") as resp:
                data = await resp.json()
                if not data.get("ok"):
                    raise Exception(data.get("description", "Неверный токен"))
                bot_name = data["result"].get("username", "unknown")
    except Exception as e:
        await send_plain(update.message, f"❌ Ошибка токена: {e}\n\nПроверь токен и попробуй снова:", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_partner")]]))
        return "WAIT_MIRROR_TOKEN"
    users_all = load_json(USERS_FILE)
    partner_nick = users_all.get(tg_id, {}).get("nick", tg_id)
    mirrors[tg_id] = {"token": token, "bot_username": bot_name, "nick": partner_nick, "active": True, "created": datetime.now().strftime("%d.%m.%Y %H:%M")}
    save_mirrors(mirrors)
    success = await start_mirror_bot(tg_id, token, partner_nick)
    if success:
        await send_plain(update.message, f"✅ Зеркало подключено!\nБот: @{bot_name}\nЗа каждого нового юзера через твой бот — +1 день к подписке.\nПоделись ссылкой: t.me/{bot_name}", get_user_kb())
    else:
        mirrors[tg_id]["active"] = False; save_mirrors(mirrors)
        await send_plain(update.message, "❌ Не удалось запустить зеркало. Проверь что бот не запущен в другом месте.", get_user_kb())
    return "MENU"


async def wait_timenick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id  = str(update.effective_user.id)
    text   = update.message.text.strip()
    field  = context.user_data.get("await_timenick")
    cfg = _load_timenick_cfg(tg_id)
    if field == "nick":
        if not text:
            await send_plain(update.message, "⚠️ Никнейм не может быть пустым.", None)
            return "WAIT_TIMENICK"
        cfg["nickname"] = text; _save_timenick_cfg(tg_id, cfg)
        client = USER_BOTS.get(tg_id)
        if client and cfg.get("enabled"):
            client._timenick_stop(tg_id); asyncio.create_task(client._timenick_start(tg_id))
        await send_plain(update.message, f"✅ Никнейм сохранён: {text}", None)
    elif field == "second":
        if not text.lstrip("-").isdigit() or not (0 <= int(text) <= 59):
            await send_plain(update.message, "⚠️ Введи число от 0 до 59.", None)
            return "WAIT_TIMENICK"
        cfg["second"] = int(text); _save_timenick_cfg(tg_id, cfg)
        client = USER_BOTS.get(tg_id)
        if client and cfg.get("enabled"):
            client._timenick_stop(tg_id); asyncio.create_task(client._timenick_start(tg_id))
        await send_plain(update.message, f"✅ Секунда обновления: {text}с", None)
    elif field == "tz":
        if not text.lstrip("-").isdigit() or not (-12 <= int(text) <= 14):
            await send_plain(update.message, "⚠️ Введи число от -12 до 14.", None)
            return "WAIT_TIMENICK"
        cfg["tz_offset"] = int(text); _save_timenick_cfg(tg_id, cfg)
        client = USER_BOTS.get(tg_id)
        if client and cfg.get("enabled"):
            client._timenick_stop(tg_id); asyncio.create_task(client._timenick_start(tg_id))
        await send_plain(update.message, f"✅ Часовой пояс: UTC+{text}", None)
    context.user_data.pop("await_timenick", None)
    await _show_sysmods(update.message, tg_id, "timenick")
    return "MENU"


async def sonya_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_photo(update.message, PHOTO_SONYA_SAD, "🤖 Соня сейчас не на связи. Попробуйте позже.\n\n📢 Канал: @userbotcbet", get_cancel_kb())
    return "SONYA_CHAT"


async def cmd_set_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["setimages_step"] = 0
    context.user_data["setimages_keys"] = ["auth", "modules", "sonya_sad", "menu"]
    context.user_data["setimages_names"] = ["auth.jpg (авторизация)", "modules.jpg (модули)", "sonya_sad.jpg (Соня)", "menu.jpg (главное меню)"]
    await send_plain(update.message, "🖼 Загрузка картинок\n\nОтправь фото по очереди:\n1. auth.jpg\n2. modules.jpg\n3. sonya_sad.jpg\n4. menu.jpg\n\nОтправь первое фото:", None)
    return "SET_IMAGES"

async def setimages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await send_plain(update.message, "❌ Отправь именно фото (не файлом).", None)
        return "SET_IMAGES"
    step  = context.user_data.get("setimages_step", 0)
    keys  = context.user_data.get("setimages_keys", [])
    names = context.user_data.get("setimages_names", [])
    if step >= len(keys):
        await send_plain(update.message, "✅ Все картинки уже загружены!", None)
        return "MENU"
    file_id = update.message.photo[-1].file_id
    photo_ids = load_json(PHOTO_IDS_FILE)
    photo_ids[keys[step]] = file_id
    save_json(PHOTO_IDS_FILE, photo_ids)
    step += 1
    context.user_data["setimages_step"] = step
    if step < len(keys):
        await send_plain(update.message, f"✅ {names[step-1]} сохранена!\n\nТеперь отправь: {names[step]}", None)
        return "SET_IMAGES"
    else:
        kb = get_user_kb() if is_user_authorized(str(update.effective_user.id)) else get_guest_kb()
        await send_plain(update.message, "🎉 Все картинки успешно загружены!", kb)
        return "MENU"


async def promo_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    code  = update.message.text.strip().upper()
    async with _file_lock:
        promos = load_json(PROMO_FILE)
    if code not in promos:
        await send_plain(update.message, "❌ Код не найден. Проверь правильность ввода.\nКоды можно получить на канале @userbotcbet", get_cancel_kb())
        return "WAIT_PROMO_ACTIVATE"
    promo = promos[code]
    if tg_id in promo.get("used_by", []):
        await send_plain(update.message, "⚠️ Этот код уже был использован тобой.", get_user_kb())
        return "MENU"
    if len(promo.get("used_by", [])) >= promo.get("max_uses", 1):
        await send_plain(update.message, "⚠️ Код исчерпан.", get_user_kb())
        return "MENU"
    plan_key = promo.get("plan", "basic")
    days     = promo.get("days", SUB_PLANS.get(plan_key, {}).get("days", 30))
    from datetime import timezone, timedelta
    sub = load_sub(tg_id)
    now_ts = datetime.now(timezone.utc).timestamp()
    base   = max(sub.get("expires", now_ts), now_ts)
    sub["plan"] = plan_key; sub["expires"] = base + days * 86400
    save_sub(tg_id, sub)
    async with _file_lock:
        promos[code]["used_by"].append(tg_id)
        save_json(PROMO_FILE, promos)
    plan = SUB_PLANS.get(plan_key, SUB_PLANS["basic"])
    try:
        async with _file_lock:
            users_all = load_json(USERS_FILE)
        user_nick = users_all.get(tg_id, {}).get("nick", tg_id)
        await context.bot.send_message(chat_id=ADMIN_TG_ID, text=f"🎟 Промокод активирован!\n\nКод: `{code}`\nЮзер: {user_nick} (`{tg_id}`)\nПлан: {plan['emoji']} {plan['name']} — {days} дн.\nИспользований: {len(promos[code]['used_by'])}/{promos[code].get('max_uses',1)}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление админу: {e}")
    await send_plain(update.message,
        f"✅ Код активирован!\n\n{plan['emoji']} {plan['name']} — {days} дней\n"
        + ("Все модули и системные функции разблокированы! 🔓" if plan_key == "pro" else ""),
        get_user_kb())
    return "MENU"


async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() != ADMIN_PASSWORD:
        await send_plain(update.message, "❌ Доступ отклонён.", get_guest_kb())
        return "MENU"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Пользователи", callback_data="a_users"), InlineKeyboardButton("🎫 Промокоды", callback_data="a_promos")],
        [InlineKeyboardButton("🪞 Рефералы", callback_data="a_referrals")],
        [InlineKeyboardButton("🚪 Выйти из админки", callback_data="back_main")]
    ])
    await send_plain(update.message, "👑 Панель администратора", kb)
    return "ADMIN_MENU"

async def admin_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    await query.answer()

    def admin_kb():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Пользователи", callback_data="a_users"), InlineKeyboardButton("🎫 Промокоды", callback_data="a_promos")],
            [InlineKeyboardButton("🪞 Рефералы", callback_data="a_referrals")],
            [InlineKeyboardButton("🚪 Выйти из админки", callback_data="back_main")]
        ])

    if data == "back_admin":
        await send_plain(query.message, "👑 Панель администратора", admin_kb())
        return "ADMIN_MENU"

    if data == "a_users":
        async with _file_lock:
            users = load_json(USERS_FILE)
        lines = []
        for u_id, v in users.items():
            status = "🟢" if u_id in USER_BOTS else "🔴"
            mods   = len(LOADED_MODULES.get(u_id, []))
            lines.append(f"{status} {v.get('nick','—')} | {v.get('phone','—')} | Модули: {mods}")
        txt = "👥 Пользователи:\n\n" + ("\n".join(lines) if lines else "База пуста.")
        await send_plain(query.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_admin")]]))
        return "ADMIN_MENU"

    if data == "a_promos":
        async with _file_lock:
            promos = load_json(PROMO_FILE)
        lines = []
        for k, v in promos.items():
            used = len(v.get("used_by", []))
            plan_name = {"trial": "🆓 Пробная", "basic": "⭐️ Базовая", "pro": "👑 Про"}.get(v.get("plan", "?"), "?")
            lines.append(f"• {k} — {plan_name} {v.get('days','?')} дн. | {used}/{v.get('max_uses','∞')}")
        await send_plain(query.message, "🎫 Промокоды:\n\n" + "\n".join(lines), InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_admin")]]))
        return "ADMIN_MENU"

    if data == "a_referrals":
        mirrors = load_mirrors()
        if not mirrors:
            await send_plain(query.message, "🪞 Зеркал пока нет.", admin_kb())
            return "ADMIN_MENU"
        rows = []
        lines_txt = []
        for pid, info in mirrors.items():
            status = "🟢" if pid in MIRROR_APPS else "🔴"
            bot_un = info.get("bot_username", pid); nick = info.get("nick", pid); refs = get_mirror_stats(pid)["total"]
            rows.append([InlineKeyboardButton(f"{status} @{bot_un} ({nick}) — {refs} реф.", callback_data=f"a_mirror_{pid}")])
            lines_txt.append(f"{status} @{bot_un} | {nick} | {refs} реф.")
        rows.append([InlineKeyboardButton("◀️ Назад", callback_data="back_admin")])
        await send_plain(query.message, "🪞 Зеркала и рефералы\n\n" + "\n".join(lines_txt) + "\n\nНажми на зеркало:", InlineKeyboardMarkup(rows))
        return "ADMIN_MENU"

    if data.startswith("a_mirror_") and not data.startswith("a_mirror_toggle_") and not data.startswith("a_mirror_del_"):
        pid = data[len("a_mirror_"):]; mirrors = load_mirrors(); info = mirrors.get(pid, {})
        if not info:
            await send_plain(query.message, "❌ Зеркало не найдено.", admin_kb())
            return "ADMIN_MENU"
        stats = get_mirror_stats(pid); bot_un = info.get("bot_username", "?"); nick = info.get("nick", pid)
        token = info.get("token", ""); created = info.get("created", "?"); active = pid in MIRROR_APPS
        refs_all = load_referrals()
        ref_list = [(uid, d) for uid, d in refs_all.items() if d.get("partner_id") == pid]
        users_all = load_json(USERS_FILE)
        ref_lines = [f"  • {users_all.get(uid,{}).get('nick',uid)} — {d.get('date','?')}" for uid, d in ref_list[-5:]]
        ref_txt = "\n".join(ref_lines) if ref_lines else "  нет рефералов"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸ Приостановить" if active else "▶️ Запустить", callback_data=f"a_mirror_toggle_{pid}")],
            [InlineKeyboardButton("🗑 Удалить зеркало", callback_data=f"a_mirror_del_{pid}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="a_referrals")]
        ])
        await send_plain(query.message, f"🪞 Зеркало @{bot_un}\n\nПартнёр: {nick} ({pid})\nСтатус: {'🟢 Активно' if active else '🔴 Остановлено'}\nСоздано: {created}\nТокен: {token[:12]}...\nРефералов: {stats['total']}\nБонусных дней: {stats['bonus_days']}\n\nПоследние рефералы:\n{ref_txt}", kb)
        return "ADMIN_MENU"

    if data.startswith("a_mirror_toggle_"):
        pid = data[len("a_mirror_toggle_"):]; mirrors = load_mirrors(); info = mirrors.get(pid, {})
        if pid in MIRROR_APPS:
            await stop_mirror_bot(pid); mirrors[pid]["active"] = False; save_mirrors(mirrors)
            await send_plain(query.message, f"⏸ Зеркало @{info.get('bot_username','?')} приостановлено.", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data=f"a_mirror_{pid}")]]))
        else:
            success = await start_mirror_bot(pid, info["token"], info.get("nick", pid))
            mirrors[pid]["active"] = success; save_mirrors(mirrors)
            await send_plain(query.message, "▶️ Зеркало запущено." if success else "❌ Не удалось запустить.", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data=f"a_mirror_{pid}")]]))
        return "ADMIN_MENU"

    if data.startswith("a_mirror_del_"):
        pid = data[len("a_mirror_del_"):]; mirrors = load_mirrors(); info = mirrors.get(pid, {}); bot_un = info.get("bot_username", pid)
        await stop_mirror_bot(pid)
        if pid in mirrors: del mirrors[pid]
        save_mirrors(mirrors)
        await send_plain(query.message, f"🗑 Зеркало @{bot_un} удалено.", admin_kb())
        return "ADMIN_MENU"

    return "MENU"


async def cmd_reset_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    async with _file_lock:
        users = load_json(USERS_FILE)
        if tg_id in users: del users[tg_id]; save_json(USERS_FILE, users)
    for ext in (".session", ".session-journal"):
        p = os.path.join(DATA_DIR, f"session_{tg_id}{ext}")
        if os.path.exists(p):
            try: os.remove(p)
            except Exception: pass
    if tg_id in USER_BOTS:
        try: await USER_BOTS[tg_id].disconnect(); del USER_BOTS[tg_id]
        except Exception: pass
    if tg_id in LOADED_MODULES: del LOADED_MODULES[tg_id]
    context.user_data.clear()
    await send_photo(update.message, PHOTO_AUTH, "🗑 Аккаунт сброшен.\n\nВсе данные удалены. Теперь можешь зарегистрироваться заново.", get_guest_kb())
    return "MENU"


async def cmd_addpromo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import random, string
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("Использование: /addpromo <план> <дней> <количество>\nПример: /addpromo pro 30 3")
        return "MENU"
    plan_key = args[0].lower()
    if plan_key not in SUB_PLANS:
        await update.message.reply_text(f"❌ Неизвестный план: {plan_key}\nДоступны: trial, basic, pro")
        return "MENU"
    try:
        days  = int(args[1]); count = int(args[2])
    except ValueError:
        await update.message.reply_text("❌ Дней и количество должны быть числами.")
        return "MENU"
    if not (1 <= days <= 365): await update.message.reply_text("❌ Дней: от 1 до 365."); return "MENU"
    if not (1 <= count <= 50): await update.message.reply_text("❌ Количество: от 1 до 50."); return "MENU"
    async with _file_lock:
        promos = load_json(PROMO_FILE)
    new_codes = []
    attempts  = 0
    while len(new_codes) < count and attempts < count * 10:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if code not in promos:
            promos[code] = {"plan": plan_key, "days": days, "max_uses": 1, "used_by": []}
            new_codes.append(code)
        attempts += 1
    async with _file_lock:
        save_json(PROMO_FILE, promos)
    plan = SUB_PLANS[plan_key]
    lines = [f"{plan['emoji']} {plan['name']} — {days} дн.  →  `{c}`" for c in new_codes]
    await update.message.reply_text(f"✅ Создано {count} промокодов:\n\n" + "\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    return "MENU"


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id   = str(update.effective_user.id)
    payload = update.message.successful_payment.payload
    from datetime import timezone, timedelta
    if payload.startswith("sub_pro_"): plan_key = "pro"
    else: return
    plan = SUB_PLANS[plan_key]; sub = load_sub(tg_id)
    now_ts = datetime.now(timezone.utc).timestamp()
    base   = max(sub.get("expires", now_ts), now_ts)
    sub["plan"] = plan_key; sub["expires"] = base + plan["days"] * 86400
    save_sub(tg_id, sub)
    try:
        async with _file_lock:
            users_all = load_json(USERS_FILE)
        user_nick = users_all.get(tg_id, {}).get("nick", tg_id)
        stars = update.message.successful_payment.total_amount
        await context.bot.send_message(chat_id=ADMIN_TG_ID, text=f"💳 Оплата Stars!\n\nЮзер: {user_nick} (`{tg_id}`)\nПлан: {plan['emoji']} {plan['name']} — {plan['days']} дн.\nСумма: {stars} ⭐", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление об оплате: {e}")
    await update.message.reply_text(f"✅ Оплата прошла! {plan['emoji']} {plan['name']} активирована на {plan['days']} дней.\nВсе модули и системные функции разблокированы! 🔓", reply_markup=get_user_kb())



# ═══════════════════════════════════════════════════════════════════
# 💰 CRYPTOBIO — обработчики (вставить в menu_router и состояния)
# ═══════════════════════════════════════════════════════════════════

async def cryptobio_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Роутер для всех кнопок CryptoBio. Вызывается из menu_router."""
    query = update.callback_query
    tg_id = str(query.from_user.id)
    data  = query.data

    cfg = _load_cryptobio_cfg(tg_id)

    if data == "u_sysmods_cryptobio":
        await query.message.reply_text(_cryptobio_text(tg_id), reply_markup=_cryptobio_kb(tg_id))
        return "MENU"

    if data == "cbio_toggle":
        cfg["enabled"] = not cfg.get("enabled", False)
        _save_cryptobio_cfg(tg_id, cfg)
        client = USER_BOTS.get(tg_id)
        if client:
            if cfg["enabled"]:
                # импортируем и запускаем модуль
                _start_cryptobio(client, tg_id)
            else:
                _stop_cryptobio(tg_id)
        try:
            await query.message.edit_text(_cryptobio_text(tg_id), reply_markup=_cryptobio_kb(tg_id))
        except Exception:
            await query.message.reply_text(_cryptobio_text(tg_id), reply_markup=_cryptobio_kb(tg_id))
        return "MENU"

    if data == "cbio_noop":
        return "MENU"

    if data.startswith("cbio_coin_"):
        coin = data[len("cbio_coin_"):]
        coins = cfg.get("coins", [])
        if coin in coins:
            coins.remove(coin)
        else:
            coins.append(coin)
        cfg["coins"] = coins
        _save_cryptobio_cfg(tg_id, cfg)
        try:
            await query.message.edit_text(_cryptobio_text(tg_id), reply_markup=_cryptobio_kb(tg_id))
        except Exception:
            await query.message.reply_text(_cryptobio_text(tg_id), reply_markup=_cryptobio_kb(tg_id))
        return "MENU"

    if data == "cbio_int_minus":
        cfg["interval"] = max(1, cfg.get("interval", 5) - 1)
        _save_cryptobio_cfg(tg_id, cfg)
        try:
            await query.message.edit_text(_cryptobio_text(tg_id), reply_markup=_cryptobio_kb(tg_id))
        except Exception:
            await query.message.reply_text(_cryptobio_text(tg_id), reply_markup=_cryptobio_kb(tg_id))
        return "MENU"

    if data == "cbio_int_plus":
        cfg["interval"] = min(60, cfg.get("interval", 5) + 1)
        _save_cryptobio_cfg(tg_id, cfg)
        try:
            await query.message.edit_text(_cryptobio_text(tg_id), reply_markup=_cryptobio_kb(tg_id))
        except Exception:
            await query.message.reply_text(_cryptobio_text(tg_id), reply_markup=_cryptobio_kb(tg_id))
        return "MENU"

    if data == "cbio_settext":
        context.user_data["await_cryptobio"] = "text"
        await query.message.reply_text(
            "✏️ Введи текст описания:\n\n"
            "Пример: привет, это моё описание\n\n"
            "Курсы крипты добавятся автоматически.\n"
            "Помни: Telegram ограничивает bio до 70 символов.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods_cryptobio")
            ]])
        )
        return "WAIT_CRYPTOBIO"

    if data == "cbio_now":
        client = USER_BOTS.get(tg_id)
        if not client:
            await query.answer("⚠️ Юзербот не запущен!", show_alert=True)
            return "MENU"
        coins    = cfg.get("coins", ["TON", "SOL", "USDT"])
        bio_text = cfg.get("bio_text", "")
        msg = await query.message.reply_text("⏳ Получаю курсы...")
        try:
            # Импортируем функции из модуля cryptobio
            import importlib.util, sys as _sys
            src = os.path.join(DATA_DIR, "cryptobio.py")
            if not os.path.exists(src):
                src = os.path.join("/app", "cryptobio.py")
            spec   = importlib.util.spec_from_file_location("cryptobio_tmp", src)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            prices  = await module.fetch_prices(coins)
            new_bio = module.build_bio(bio_text, prices, coins)
            if len(new_bio) > 70:
                new_bio = new_bio[:70]

            from telethon.tl.functions.account import UpdateProfileRequest
            await client(UpdateProfileRequest(about=new_bio))
            await msg.edit_text(
                f"✅ Описание обновлено!\n\n{new_bio}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods_cryptobio")
                ]])
            )
        except Exception as e:
            await msg.edit_text(
                f"❌ Ошибка: {e}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods_cryptobio")
                ]])
            )
        return "MENU"

    return "MENU"


async def wait_cryptobio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод текста описания."""
    tg_id = str(update.effective_user.id)
    text  = update.message.text.strip()
    field = context.user_data.get("await_cryptobio")

    if field == "text":
        cfg = _load_cryptobio_cfg(tg_id)
        cfg["bio_text"] = text
        _save_cryptobio_cfg(tg_id, cfg)
        context.user_data.pop("await_cryptobio", None)
        await update.message.reply_text(
            f"✅ Текст сохранён: {text}\n\n"
            "Курсы крипты добавятся при следующем обновлении.",
        )
        await update.message.reply_text(_cryptobio_text(tg_id), reply_markup=_cryptobio_kb(tg_id))
        return "MENU"

    return "WAIT_CRYPTOBIO"


def _start_cryptobio(client, tg_id: str):
    """Запускает фоновый loop CryptoBio."""
    try:
        import importlib.util
        src = os.path.join(DATA_DIR, "cryptobio.py")
        if not os.path.exists(src):
            src = os.path.join("/app", "cryptobio.py")
        if not os.path.exists(src):
            logger.error("cryptobio.py не найден")
            return
        spec   = importlib.util.spec_from_file_location(f"cryptobio_{tg_id}", src)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.start_loop(client, tg_id)
        logger.info(f"CryptoBio started for {tg_id}")
    except Exception as e:
        logger.error(f"CryptoBio start error for {tg_id}: {e}")


def _stop_cryptobio(tg_id: str):
    """Останавливает loop CryptoBio."""
    try:
        import importlib.util
        src = os.path.join(DATA_DIR, "cryptobio.py")
        if not os.path.exists(src):
            src = os.path.join("/app", "cryptobio.py")
        if os.path.exists(src):
            spec   = importlib.util.spec_from_file_location(f"cryptobio_{tg_id}", src)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.stop_loop(tg_id)
            logger.info(f"CryptoBio stopped for {tg_id}")
    except Exception as e:
        logger.error(f"CryptoBio stop error for {tg_id}: {e}")


def main():
    init_system()

    async def post_init(application):
        await auto_run_existing_bots()
        await auto_run_mirrors()

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("setimages", cmd_set_images),
            CommandHandler("reset_me", cmd_reset_me),
            CommandHandler("addpromo", cmd_addpromo),
        ],
        states={
            "MENU":                  [CallbackQueryHandler(menu_router)],
            "REG_NICK":              [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, reg_nick)],
            "LOGIN_PHONE":           [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone)],
            "LOGIN_API_ID":          [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, login_api_id)],
            "LOGIN_API_HASH":        [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, login_api_hash)],
            "LOGIN_PHONE_EXISTING":  [CallbackQueryHandler(menu_router, pattern="^back_main$"), MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone_existing)],
            "WAIT_CODE":             [CallbackQueryHandler(pinpad_click_handler, pattern="^pin_"), CallbackQueryHandler(menu_router, pattern="^back_main$")],
            "WAIT_2FA":              [CallbackQueryHandler(menu_router, pattern="^back_main$"), MessageHandler(filters.TEXT & ~filters.COMMAND, wait_2fa)],
            "MODULE_INSTALL":        [CallbackQueryHandler(menu_router), MessageHandler((filters.Document.ALL | filters.TEXT) & ~filters.COMMAND, module_download_handler)],
            "SO2":                   [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, so2_text_handler)],
            "OSINT":                 [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, osint_input_handler)],
            "UNPARSER":              [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, unparser_password_handler)],
            "WAIT_MIRROR_TOKEN":     [CallbackQueryHandler(menu_router, pattern="^back_main$|^u_partner$"), MessageHandler(filters.TEXT & ~filters.COMMAND, wait_mirror_token)],
            "WAIT_TIMENICK":         [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, wait_timenick)],
            "SONYA_CHAT":            [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, sonya_chat)],
            "WAIT_PROMO_ACTIVATE":   [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, promo_activate)],
            "SCREENLOCK":            [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, screenlock_token_handler)],
            "WAIT_CRYPTOBIO":        [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, wait_cryptobio)],
            "ADMIN_LOGIN":           [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, admin_login)],
            "ADMIN_MENU":            [CallbackQueryHandler(admin_router)],
            "SET_IMAGES":            [CommandHandler("start", cmd_start), MessageHandler(filters.PHOTO, setimages_handler), MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("❌ Отправь фото, не текст.") or "SET_IMAGES")],
        },
        fallbacks=[
            CommandHandler("start", cmd_start),
            CommandHandler("reset_me", cmd_reset_me),
            CommandHandler("addpromo", cmd_addpromo),
            CallbackQueryHandler(menu_router)
        ],
        per_message=False, per_chat=True, per_user=True, allow_reentry=True, conversation_timeout=600
    )

    async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Необработанное исключение: {context.error}", exc_info=context.error)
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text("⚠️ Произошла внутренняя ошибка. Попробуйте /start", reply_markup=get_guest_kb())
            except Exception:
                pass

    app.add_error_handler(global_error_handler)
    app.add_handler(conv)
    app.add_handler(__import__("telegram.ext", fromlist=["PreCheckoutQueryHandler"]).PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    logger.info("✅ UserBot Manager запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
