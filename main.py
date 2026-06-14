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

# ═══════════════════════════════════════════════════════════════════
# 🛠 БЛОК ИНИЦИАЛИЗАЦИИ И ГЛОБАЛЬНЫХ ПЕРЕМЕННЫХ
# ═══════════════════════════════════════════════════════════════════

BOT_TOKEN = os.environ.get("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
ADMIN_PASSWORD = "uretracoin"
ADMIN_TG_ID    = "1837883882"  # tg_id админа для уведомлений
CHANNEL_ID     = "@userbotcbet"  # канал для обязательной подписки
CHANNEL_URL    = "https://t.me/userbotcbet"
MAX_MIRRORS    = 10  # максимум зеркал одновременно
CHANNEL_USERNAME = "userbotcbet"  # канал для обязательной подписки

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
MIRROR_APPS: dict    = {}  # {partner_tg_id: Application} — запущенные зеркала
UNPARSER_SESSIONS: dict = {}  # {tg_id: {cfg, history, current_idx}}


# ═══════════════════════════════════════════════════════════════════
# 📦 БЛОК РАБОТЫ С БАЗОЙ ДАННЫХ (JSON)
# ═══════════════════════════════════════════════════════════════════

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
            # Одноразовые — пробная
            "H82ALC4Z": {"plan": "trial", "days": 5,  "max_uses": 1,  "used_by": []},
            "P1I99BCA": {"plan": "trial", "days": 5,  "max_uses": 1,  "used_by": []},
            "COV2RO0X": {"plan": "trial", "days": 5,  "max_uses": 1,  "used_by": []},
            # Одноразовые — базовая
            "ATMO17ZV": {"plan": "basic", "days": 30, "max_uses": 1,  "used_by": []},
            "32URPA1D": {"plan": "basic", "days": 30, "max_uses": 1,  "used_by": []},
            "8TMJ3OJP": {"plan": "basic", "days": 30, "max_uses": 1,  "used_by": []},
            # Одноразовые — про
            "C89CTAHQ": {"plan": "pro",   "days": 30, "max_uses": 1,  "used_by": []},
            "U18MTJR2": {"plan": "pro",   "days": 30, "max_uses": 1,  "used_by": []},
            "SMWAHLW0": {"plan": "pro",   "days": 30, "max_uses": 1,  "used_by": []},
            # Многоразовые x10
            "0U72PZXB": {"plan": "trial", "days": 5,  "max_uses": 10, "used_by": []},
            "C5DZL0T6": {"plan": "basic", "days": 30, "max_uses": 10, "used_by": []},
            "2JOIYJR2": {"plan": "pro",   "days": 30, "max_uses": 10, "used_by": []},
        })
    if not os.path.exists(PHOTO_IDS_FILE):
        save_json(PHOTO_IDS_FILE, {})
    if not os.path.exists(MIRRORS_FILE):
        save_json(MIRRORS_FILE, {})
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
    """Экранирует символы которые ломают Markdown в именах пользователей."""
    return text.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")


# ═══════════════════════════════════════════════════════════════════
# ⚡️ БЛОК ДВИЖКА TELETHON
# ═══════════════════════════════════════════════════════════════════

def _load_sys_module(name: str, client, tg_id: str):
    """Универсальный загрузчик системных модулей."""
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

    # ── Системные модули — грузятся всегда ──
    _load_autoreply_module(client, tg_id)
    _load_sys_module("timenick", client, tg_id)

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
    # Подключаемся СНАЧАЛА, потом вешаем хендлеры
    await client.connect()
    if await client.is_user_authorized():
        USER_BOTS[tg_id] = client
        load_user_modules(client, tg_id)
        logger.info(f"Юзербот для {tg_id} запущен, модули загружены.")
        # Запускаем run_until_disconnected в фоне — иначе хендлеры не работают
        asyncio.create_task(_run_client(tg_id, client))
    else:
        logger.warning(f"Сессия {tg_id} найдена, но авторизация не пройдена.")

async def _run_client(tg_id: str, client):
    """Держит Telethon клиент живым и слушает события."""
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


# ═══════════════════════════════════════════════════════════════════
# 🎛 БЛОК UI: КЛАВИАТУРЫ И МЕНЮ
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# 🔍 ПАРСЕР ЮЗЕРНЕЙМОВ
# ═══════════════════════════════════════════════════════════════════

import random as _random
import string as _string

def _unp_gen(length: int, digits: bool) -> str:
    chars = _string.ascii_lowercase + (_string.digits if digits else "")
    first = _random.choice(_string.ascii_lowercase)
    rest  = ''.join(_random.choices(chars, k=length - 1))
    return first + rest

def _unp_menu_text(cfg: dict) -> str:
    return (
        "🔍 Парсер юзернеймов\n\n"
        f"📏 Длина: {cfg.get('length', 8)} символов\n"
        f"🔢 Цифры: {'✅ Да' if cfg.get('digits', True) else '❌ Нет'}\n"
        f"📦 Количество: {cfg.get('count', 5)} штук\n\n"
        "Нажми Генерировать чтобы начать\n\n"
        "📢 @userbotcbet | 🤖 @cbet_controller_bot"
    )

def _unp_menu_kb(cfg: dict) -> InlineKeyboardMarkup:
    digits_label = "🔢 Цифры: ✅" if cfg.get("digits", True) else "🔢 Цифры: ❌"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➖", callback_data="unp_len_minus"),
         InlineKeyboardButton(f"📏 {cfg.get('length', 8)}", callback_data="unp_noop"),
         InlineKeyboardButton("➕", callback_data="unp_len_plus")],
        [InlineKeyboardButton(digits_label, callback_data="unp_digits")],
        [InlineKeyboardButton("➖", callback_data="unp_count_minus"),
         InlineKeyboardButton(f"📦 {cfg.get('count', 5)} шт.", callback_data="unp_noop"),
         InlineKeyboardButton("➕", callback_data="unp_count_plus")],
        [InlineKeyboardButton("🔍 Генерировать", callback_data="unp_generate")],
        [InlineKeyboardButton("◀️ Назад в меню", callback_data="back_main")],
    ])

def _unp_result_kb(sess: dict) -> InlineKeyboardMarkup:
    has_prev = sess.get("current_idx", 0) > 0
    rows = []
    nav  = []
    if has_prev:
        nav.append(InlineKeyboardButton("◀️ Вернуться", callback_data="unp_prev"))
    nav.append(InlineKeyboardButton("▶️ Вперёд", callback_data="unp_next"))
    rows.append(nav)
    rows.append([
        InlineKeyboardButton("⚙️ Настройки", callback_data="unp_settings"),
        InlineKeyboardButton("◀️ В меню",    callback_data="back_main"),
    ])
    return InlineKeyboardMarkup(rows)

def _unp_format(batch: list, idx: int, total: int) -> str:
    if not batch:
        return "😔 Не нашли свободных юзернеймов. Попробуй ещё раз.\n\n📢 @userbotcbet"
    lines = [f"✅ Свободные юзернеймы (батч {idx+1}/{total}):\n"]
    for un in batch:
        lines.append(f"  {un}")
    lines.append("\n📢 @userbotcbet | 🤖 @cbet_controller_bot")
    return "\n".join(lines)

async def _unp_generate(tg_id: str, cfg: dict) -> list:
    """Мгновенная генерация юзернеймов без проверки занятости."""
    length = max(5, min(32, cfg.get("length", 8)))
    digits = cfg.get("digits", True)
    count  = cfg.get("count", 5)
    # Генерируем мгновенно — проверку занятости делаем через t.me/username
    return [f"@{_unp_gen(length, digits)}" for _ in range(count)]


async def check_subscription(bot, tg_id: str) -> bool:
    """Проверяет подписку юзера на канал."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=int(tg_id))
        return member.status not in ("left", "kicked", "banned")
    except Exception:
        return False

def get_sub_check_kb() -> InlineKeyboardMarkup:
    """Клавиатура с кнопками подписки и проверки."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")],
    ])


def get_guest_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Регистрация", callback_data="g_reg")],
        [InlineKeyboardButton("🔑 Войти (уже есть аккаунт)", callback_data="g_login")],
        [InlineKeyboardButton("👑 Админ-Панель", callback_data="g_admin")]
    ])

def get_user_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Профиль",         callback_data="u_profile"),
         InlineKeyboardButton("💎 Подписка",         callback_data="u_sub")],
        [InlineKeyboardButton("⚙️ Модули",           callback_data="u_modules"),
         InlineKeyboardButton("🤖 Соня (ИИ)",       callback_data="u_sonya")],
        [InlineKeyboardButton("🔧 Системные модули", callback_data="u_sysmods"),
         InlineKeyboardButton("🎟 Ввести код",       callback_data="u_entercode")],
        [InlineKeyboardButton("🪞 Партнёрская программа", callback_data="u_partner"),
         InlineKeyboardButton("🔍 Юзернеймы", callback_data="u_unparser")],
        [InlineKeyboardButton("❌ Выйти (сбросить сессию)", callback_data="u_logout")]
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
    """Отправляет фото по file_id или с диска. Без ParseMode — только plain text."""
    photo_ids = load_json(PHOTO_IDS_FILE)
    key = _get_photo_key(photo_path)
    file_id = photo_ids.get(key)

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

    # Fallback — текст без фото, без Markdown (чтобы не сломалось)
    await msg.reply_text(caption, reply_markup=reply_markup)

async def send_md(msg, text: str, reply_markup):
    """Отправляет текст с Markdown. Только для текстов без юзерских данных."""
    await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def send_plain(msg, text: str, reply_markup):
    """Отправляет plain text — для текстов с юзерскими данными (ник, телефон)."""
    await msg.reply_text(text, reply_markup=reply_markup)


# ═══════════════════════════════════════════════════════════════════
# 🚦 БЛОК РОУТИНГА И СОСТОЯНИЙ
# ═══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    context.user_data.clear()
    logger.info(f"/start от юзера {tg_id}")

    # Проверяем подписку на канал (кроме админа)
    if tg_id != ADMIN_TG_ID:
        is_subbed = await check_subscription(context.bot, int(tg_id))
        if not is_subbed:
            await update.message.reply_text(
                "👋 Добро пожаловать в UserBot | Ru!\n\n"
                "Для использования бота необходимо подписаться на наш канал.\n\n"
                f"📢 Канал: @{CHANNEL_USERNAME}\n\n"
                "После подписки нажми кнопку ниже 👇",
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
            await send_photo(
                update.message, PHOTO_AUTH,
                "⚠️ Обнаружена повреждённая сессия — сброшена.\n\n"
                "Нажми кнопку ниже для настройки.",
                get_guest_kb()
            )
            return "MENU"

        if tg_id not in USER_BOTS:
            asyncio.create_task(
                start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"])
            )
        nick   = u_info.get("nick", "Пользователь")
        status = "🟢 активен" if tg_id in USER_BOTS else "🔴 запускается..."
        await send_photo(
            update.message, PHOTO_MENU,
            f"🏠 Главное меню\n\n"
            f"Добро пожаловать, {nick}!\n"
            f"Юзербот: {status}\n\n"
            f"Выбери раздел:",
            get_user_kb()
        )
    else:
        await send_photo(
            update.message, PHOTO_AUTH,
            "👾 UserBot | Ru\n\n"
            "Добро пожаловать в систему управления юзерботами!\n\n"
            "Подключи свой Telegram-аккаунт и устанавливай модули — "
            "автоответчики, инструменты автоматизации, фильтры и многое другое.\n\n"
            "⚡️ Движок: Telethon\n"
            "🧩 Система модулей: как в Hikka\n"
            "👤 Автор: @cbet_cebep\n\n"
            "👇 Нажми кнопку чтобы начать:",
            get_guest_kb()
        )
    return "MENU"




# ═══════════════════════════════════════════════════════════════════
# 🪞 СИСТЕМА ЗЕРКАЛ (партнёрские боты)
# ═══════════════════════════════════════════════════════════════════

def load_mirrors() -> dict:
    return load_json(MIRRORS_FILE)

def save_mirrors(data: dict):
    save_json(MIRRORS_FILE, data)

def load_referrals() -> dict:
    return load_json(REFERRALS_FILE)

def save_referrals(data: dict):
    save_json(REFERRALS_FILE, data)

def get_mirror_stats(partner_id: str) -> dict:
    """Статистика партнёра — кол-во рефералов и бонусные дни."""
    refs = load_referrals()
    partner_refs = [r for r in refs.values() if r.get("partner_id") == partner_id]
    return {
        "total": len(partner_refs),
        "bonus_days": len(partner_refs)  # +1 день за каждого
    }

def add_referral(new_user_id: str, partner_id: str):
    """Записывает реферала и начисляет партнёру +1 день."""
    refs = load_referrals()
    if new_user_id in refs:
        return  # уже зарегистрирован через реферала

    refs[new_user_id] = {
        "partner_id": partner_id,
        "date": datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    save_referrals(refs)

    # Начисляем партнёру +1 день к подписке
    from datetime import timezone, timedelta
    sub = load_sub(partner_id)
    now_ts = datetime.now(timezone.utc).timestamp()
    base = max(sub.get("expires", now_ts), now_ts)
    sub["expires"] = base + 86400  # +1 день
    if not sub.get("plan"):
        sub["plan"] = "trial"
    save_sub(partner_id, sub)
    logger.info(f"Реферал {new_user_id} от партнёра {partner_id} — начислен +1 день")

async def start_mirror_bot(partner_id: str, token: str, partner_nick: str):
    """Запускает зеркало бота для партнёра."""
    from telegram.ext import ApplicationBuilder as AB

    if partner_id in MIRROR_APPS:
        try:
            await MIRROR_APPS[partner_id].stop()
            await MIRROR_APPS[partner_id].shutdown()
        except Exception:
            pass

    try:
        mirror_app = AB().token(token).build()

        # Регистрируем /start для зеркала
        async def mirror_start(update, context):
            user_id = str(update.effective_user.id)
            context.user_data.clear()

            # Записываем реферала если юзер новый
            users = load_json(USERS_FILE)
            if user_id not in users:
                add_referral(user_id, partner_id)

            # Проверяем подписку на канал
            if user_id != ADMIN_TG_ID:
                try:
                    member = await context.bot.get_chat_member(
                        chat_id=CHANNEL_ID, user_id=int(user_id)
                    )
                    if member.status in ("left", "kicked", "banned"):
                        await update.message.reply_text(
                            f"👋 Добро пожаловать!\n\n"
                            f"Это бот партнёра — {partner_nick}\n\n"
                            "Для использования подпишись на канал @userbotcbet\n\n"
                            "После подписки нажми /start снова.",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL)],
                            ])
                        )
                        return
                        return
                except Exception:
                    pass

            # Показываем обычное меню
            is_auth = is_user_authorized(user_id)
            users_data = load_json(USERS_FILE)
            if is_auth:
                u_info = users_data[user_id]
                if user_id not in USER_BOTS and u_info.get("api_id") and u_info.get("api_hash"):
                    asyncio.create_task(
                        start_user_bot(user_id, int(u_info["api_id"]), u_info["api_hash"])
                    )
                nick = u_info.get("nick", "Пользователь")
                await update.message.reply_text(
                    f"🏠 Главное меню\n\n"
                    f"Добро пожаловать, {nick}!\n\n"
                    f"Реферальный бот партнёра: {partner_nick}",
                    reply_markup=get_user_kb()
                )
            else:
                await update.message.reply_text(
                    "👾 UserBot | Ru\n\n"
                    f"Реферальный бот партнёра: {partner_nick}\n\n"
                    "Зарегистрируйся и получи пробный доступ на 5 дней!",
                    reply_markup=get_guest_kb()
                )

        # Все остальные хендлеры — те же что и в основном боте
        from telegram.ext import CommandHandler as CH, CallbackQueryHandler as CQH
        from telegram.ext import MessageHandler as MH

        conv = ConversationHandler(
            entry_points=[CH("start", mirror_start)],
            states={
                "MENU":                 [CQH(menu_router)],
                "REG_NICK":             [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, reg_nick)],
                "LOGIN_PHONE":          [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, login_phone)],
                "LOGIN_API_ID":         [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, login_api_id)],
                "LOGIN_API_HASH":       [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, login_api_hash)],
                "LOGIN_PHONE_EXISTING": [CQH(menu_router, pattern="^back_main$"), MH(filters.TEXT & ~filters.COMMAND, login_phone_existing)],
                "WAIT_CODE":            [CQH(pinpad_click_handler, pattern="^pin_"), CQH(menu_router, pattern="^back_main$")],
                "WAIT_2FA":             [CQH(menu_router, pattern="^back_main$"), MH(filters.TEXT & ~filters.COMMAND, wait_2fa)],
                "WAIT_TIMENICK":        [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, wait_timenick)],
                "MODULE_INSTALL":       [CQH(menu_router), MH((filters.Document.ALL | filters.TEXT) & ~filters.COMMAND, module_download_handler)],
                "SONYA_CHAT":           [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, sonya_chat)],
                "WAIT_PROMO_ACTIVATE":  [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, promo_activate)],
                "ADMIN_LOGIN":          [CQH(menu_router), MH(filters.TEXT & ~filters.COMMAND, admin_login)],
                "ADMIN_MENU":           [CQH(admin_router)],
                "SET_IMAGES":           [CH("start", mirror_start), MH(filters.PHOTO, setimages_handler)],
            },
            fallbacks=[CH("start", mirror_start), CQH(menu_router)],
            per_message=False, per_chat=True, per_user=True,
            allow_reentry=True, conversation_timeout=600
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
    """Останавливает зеркало."""
    if partner_id in MIRROR_APPS:
        try:
            await MIRROR_APPS[partner_id].updater.stop()
            await MIRROR_APPS[partner_id].stop()
            await MIRROR_APPS[partner_id].shutdown()
            del MIRROR_APPS[partner_id]
            logger.info(f"Зеркало {partner_id} остановлено")
        except Exception as e:
            logger.error(f"Ошибка остановки зеркала {partner_id}: {e}")

async def auto_run_mirrors():
    """Автозапуск зеркал при рестарте сервера."""
    mirrors = load_mirrors()
    for partner_id, info in mirrors.items():
        if info.get("active") and info.get("token"):
            logger.info(f"Автозапуск зеркала партнёра {partner_id}")
            await start_mirror_bot(partner_id, info["token"], info.get("nick", "Партнёр"))

# ═══════════════════════════════════════════════════════════════════
# 💎 СИСТЕМА ПОДПИСОК
# ═══════════════════════════════════════════════════════════════════

SUB_PLANS = {
    "trial": {
        "name":       "Пробная",
        "emoji":      "🆓",
        "days":       5,
        "price":      0,
        "mod_slots":  1,   # слотов обычных модулей
        "sys_slots":  1,   # слотов системных модулей
        "all_mods":   False,
        "all_sys":    False,
    },
    "basic": {
        "name":       "Базовая",
        "emoji":      "⭐️",
        "days":       30,
        "price":      25,  # звёзды
        "mod_slots":  3,
        "sys_slots":  2,
        "all_mods":   False,
        "all_sys":    False,
    },
    "pro": {
        "name":       "Про",
        "emoji":      "👑",
        "days":       30,
        "price":      50,
        "mod_slots":  999,
        "sys_slots":  999,
        "all_mods":   True,
        "all_sys":    True,
    },
}

SYS_MODS_LIST = ["autoreply", "timenick"]  # все системные модули

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
        return SUB_PLANS["trial"]  # без подписки — пробный доступ
    return SUB_PLANS.get(sub.get("plan", "trial"), SUB_PLANS["trial"])

def can_use_sys_mod(tg_id: str, mod_name: str) -> bool:
    plan = get_plan(tg_id)
    # Про — всё доступно
    if plan["all_sys"]:
        return True
    sub    = load_sub(tg_id)
    chosen = sub.get("chosen_sys", [])
    plan_key = sub.get("plan", "trial")
    # Если chosen_sys не заполнен — показываем выбор, не блокируем
    # Пользователь с активной подпиской может выбрать модули
    if not chosen and plan_key in ("basic", "trial", "pro"):
        return True  # Пустой chosen_sys = ещё не выбрал, но подписка есть
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

    chosen_sys  = sub.get("chosen_sys", [])
    chosen_mods = sub.get("chosen_mods", [])

    text = (
        "💎 Подписка\n\n"
        f"Статус: {plan['emoji']} {plan['name']} — {exp_str}\n"
        f"Слотов модулей: {plan['mod_slots'] if plan['mod_slots'] < 999 else '∞'}\n"
        f"Системных модулей: {plan['sys_slots'] if plan['sys_slots'] < 999 else '∞'}\n\n"
        "Планы:\n"
        "🆓 Пробная (5 дн.) — бесплатно\n"
        "⭐️ Базовая (30 дн.) — 25 ⭐\n"
        "👑 Про (30 дн.) — 50 ⭐"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🆓 Активировать пробную", callback_data="sub_buy_trial")],
        [InlineKeyboardButton("⭐️ Купить Базовую — 25 ⭐", callback_data="sub_buy_basic")],
        [InlineKeyboardButton("👑 Купить Про — 50 ⭐", callback_data="sub_buy_pro")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]
    ])
    await msg.reply_text(text, reply_markup=kb)

# ── Проверка подписки на канал ────────────────────────────────────

async def check_subscription(bot, user_id: int) -> bool:
    """Проверяет подписан ли юзер на канал."""
    try:
        member = await bot.get_chat_member(
            chat_id=f"@{CHANNEL_USERNAME}",
            user_id=user_id
        )
        return member.status not in ("left", "kicked", "banned")
    except Exception as e:
        logger.warning(f"Ошибка проверки подписки для {user_id}: {e}")
        return False

def get_sub_required_kb() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой подписки и проверки."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")]
    ])


# ── Вспомогательные функции автоответчика ─────────────────────────

# ── timenick helpers ──────────────────────────────────────────────

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

# ── autoreply helpers ──────────────────────────────────────────────

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

async def _show_sysmods(msg, tg_id: str, section: str = "main"):
    """Отрисовывает меню системных модулей."""

    if section == "autoreply":
        if not can_use_sys_mod(tg_id, "autoreply"):
            await msg.reply_text(
                "🔒 Автоответчик недоступен на вашей подписке.\n\n"
                "Активируй подписку в разделе 💎 Подписка.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods")]]))
            return
        cfg     = _load_autoreply_cfg(tg_id)
        enabled = cfg.get("enabled", False)
        mode    = cfg.get("mode", "all")
        style   = cfg.get("style", "normal")
        e       = "🟢" if enabled else "🔴"

        MODE_LABELS  = {"all": "Все", "contacts": "Контакты", "non_contacts": "Не контакты"}
        STYLE_LABELS = {"official": "Официальный", "normal": "Обычный", "bold": "Дерзкий"}

        mode_row  = [InlineKeyboardButton(
            f"{'✅ ' if mode == m else ''}{l}", callback_data=f"sysmod_mode_{m}"
        ) for m, l in MODE_LABELS.items()]
        style_row = [InlineKeyboardButton(
            f"{'✅ ' if style == s else ''}{l}", callback_data=f"sysmod_style_{s}"
        ) for s, l in STYLE_LABELS.items()]

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{e} Автоответчик — {'включён' if enabled else 'выключен'}",
                                  callback_data="sysmod_autoreply_toggle")],
            mode_row,
            style_row,
            [InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods")]
        ])
        await msg.reply_text(
            "🤖 Автоответчик\n\n"
            f"Статус: {e} {'Включён' if enabled else 'Выключен'}\n"
            f"Режим: {MODE_LABELS.get(mode, mode)}\n"
            f"Стиль: {STYLE_LABELS.get(style, style)}\n\n"
            "Отвечает на входящие личные сообщения пока ты недоступен.",
            reply_markup=kb
        )

    elif section == "timenick":
        if not can_use_sys_mod(tg_id, "timenick"):
            await msg.reply_text(
                "🔒 Ник по времени недоступен на вашей подписке.\n\n"
                "Активируй подписку в разделе 💎 Подписка.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods")]]))
            return
        cfg     = _load_timenick_cfg(tg_id)
        enabled = cfg.get("enabled", False)
        nick    = cfg.get("nickname", "")
        second  = cfg.get("second", 0)
        e       = "🟢" if enabled else "🔴"

        from datetime import datetime
        preview = f"{nick} | {datetime.now().strftime('%H:%M')}" if nick else "не задан"

        tz_offset = cfg.get("tz_offset", 3)
        from datetime import timezone, timedelta
        tz_now    = datetime.now(timezone(timedelta(hours=tz_offset))).strftime("%H:%M")
        preview   = f"{nick} | {tz_now}" if nick else "не задан"

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{e} Ник по времени — {'включён' if enabled else 'выключен'}",
                                  callback_data="sysmod_timenick_toggle")],
            [InlineKeyboardButton("✏️ Изменить никнейм", callback_data="sysmod_timenick_setnick")],
            [InlineKeyboardButton(f"⏱ Секунда обновления: {second}с",
                                  callback_data="sysmod_timenick_setsec")],
            [InlineKeyboardButton(f"🌍 Часовой пояс: UTC+{tz_offset}",
                                  callback_data="sysmod_timenick_settz")],
            [InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods")]
        ])
        await msg.reply_text(
            "🕐 Ник по времени\n\n"
            f"Статус: {e} {'Включён' if enabled else 'Выключен'}\n"
            f"Никнейм: {nick if nick else 'не задан'}\n"
            f"Секунда обновления: {second}с\n"
            f"Часовой пояс: UTC+{tz_offset} (сейчас {tz_now})\n"
            f"Превью: {preview}\n\n"
            "Каждую минуту в заданную секунду обновляет имя профиля.\n"
            "Формат: nickname | HH:MM",
            reply_markup=kb
        )

    else:  # main
        ar_cfg = _load_autoreply_cfg(tg_id)
        tn_cfg = _load_timenick_cfg(tg_id)
        ar_e   = "🟢" if ar_cfg.get("enabled") else "🔴"
        tn_e   = "🟢" if tn_cfg.get("enabled") else "🔴"

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{ar_e} Автоответчик", callback_data="u_sysmods_autoreply")],
            [InlineKeyboardButton(f"{tn_e} Ник по времени", callback_data="u_sysmods_timenick")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]
        ])
        await msg.reply_text(
            "🔧 Системные модули\n\n"
            f"{ar_e} Автоответчик — {'включён' if ar_cfg.get('enabled') else 'выключен'}\n"
            f"{tn_e} Ник по времени — {'включён' if tn_cfg.get('enabled') else 'выключен'}\n\n"
            "Выбери модуль для настройки:",
            reply_markup=kb
        )


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tg_id = str(query.from_user.id)
    data  = query.data
    logger.info(f"menu_router: юзер {tg_id} нажал '{data}'")
    await query.answer()

    async with _file_lock:
        is_auth = is_user_authorized(tg_id)
        users   = load_json(USERS_FILE)

    # ── Проверка подписки ──
    if data == "check_sub":
        tg_id_int = int(tg_id)
        is_subbed = await check_subscription(context.bot, tg_id_int)
        if is_subbed:
            await query.answer("✅ Подписка подтверждена!", show_alert=False)
            # Продолжаем как обычно — показываем главное меню
            async with _file_lock:
                is_auth_now = is_user_authorized(tg_id)
                users_now   = load_json(USERS_FILE)
            if is_auth_now:
                u_info = users_now[tg_id]
                if tg_id not in USER_BOTS and u_info.get("api_id") and u_info.get("api_hash"):
                    asyncio.create_task(
                        start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"])
                    )
                nick   = u_info.get("nick", "Пользователь")
                status = "🟢 активен" if tg_id in USER_BOTS else "🔴 запускается..."
                await send_photo(
                await send_photo(
                    query.message, PHOTO_MENU,
                    f"🏠 Главное меню\n\n"
                    f"Добро пожаловать, {nick}!\n"
                    f"Юзербот: {status}\n\n"
                    "Выбери раздел:",
                    get_user_kb()
                )
                )
            else:
                await send_photo(
                    query.message, PHOTO_AUTH,
                    "✅ Подписка подтверждена!\n\n"
                    "Теперь можешь зарегистрироваться или войти:",
                    get_guest_kb()
                )

    # ── Назад в главное меню ──
    if data == "back_main":
        context.user_data.clear()
        if is_auth:
            nick   = users[tg_id].get("nick", "Пользователь")
            status = "🟢 активен" if tg_id in USER_BOTS else "🔴 запускается..."
            await send_photo(
                query.message, PHOTO_MENU,
                f"🏠 Главное меню\n\n"
                f"Добро пожаловать, {nick}!\n"
                f"Юзербот: {status}\n\n"
                f"Выбери раздел:",
                get_user_kb()
            )
        else:
            await send_photo(
                query.message, PHOTO_AUTH,
                "👾 UserBot | Ru\n\n"
                "Добро пожаловать в систему управления юзерботами!\n\n"
                "Подключи свой Telegram-аккаунт и устанавливай модули — "
                "автоответчики, инструменты автоматизации, фильтры и многое другое.\n\n"
                "⚡️ Движок: Telethon\n"
                "🧩 Система модулей: как в Hikka\n"
                "👤 Автор: @cbet_cebep\n\n"
                "👇 Нажми кнопку чтобы начать:",
                get_guest_kb()
            )
        return "MENU"

    # ── Гостевые кнопки ──
    if data == "g_reg":
        if is_auth:
            await send_plain(query.message, "⚠️ Сессия уже создана!", get_user_kb())
            return "MENU"
        # Проверяем подписку на канал
        is_subbed = await check_subscription(context.bot, tg_id)
        if not is_subbed:
            await send_photo(
                query.message, PHOTO_AUTH,
                "📢 Для регистрации необходимо подписаться на наш канал!\n\n"
                "1. Нажми кнопку ниже и подпишись\n"
                "2. Вернись и нажми Проверить подписку",
                get_sub_check_kb()
            )
            return "MENU"
        await send_photo(
            query.message, PHOTO_AUTH,
            "🔐 Авторизация — Шаг 1 из 4\n\n"
            "Придумай себе никнейм — он будет отображаться в профиле.\n\n"
            "Можно использовать латиницу, кириллицу или цифры.\n"
            "Пример: DarkUser, Артём, xXbotXx\n\n"
            "Канал проекта: @userbotcbet",
            get_cancel_kb()
        )
        return "REG_NICK"

    if data == "check_sub":
        is_subbed = await check_subscription(context.bot, tg_id)
        if is_subbed:
            # Редактируем существующее сообщение вместо отправки нового
            try:
                await query.message.edit_text(
                    "✅ Подписка подтверждена!\n\n"
                    "Теперь можешь зарегистрироваться или войти:",
                    reply_markup=get_guest_kb()
                )
            except Exception:
                await send_photo(
                    query.message, PHOTO_AUTH,
                    "✅ Подписка подтверждена!\n\nТеперь можешь зарегистрироваться или войти:",
                    get_guest_kb()
                )
        else:
            await query.answer("❌ Ты ещё не подписан на канал!", show_alert=True)
        return "MENU"

    if data == "g_login":
        if is_auth:
            await send_plain(query.message, "⚠️ Ты уже авторизован!", get_user_kb())
            return "MENU"
        await send_photo(
            query.message, PHOTO_AUTH,
            "🔑 Вход в существующий аккаунт\n\n"
            "Введи номер телефона привязанный к твоему Telegram-аккаунту.\n\n"
            "Мы найдём твою сессию и восстановим юзербота.\n"
            "Формат: +79001234567",
            get_cancel_kb()
        )
        context.user_data["login_mode"] = "existing"
        return "LOGIN_PHONE_EXISTING"

    if data == "g_admin":
        await send_plain(query.message, "👑 Введите пароль администратора:", get_cancel_kb())
        return "ADMIN_LOGIN"

    # ── Защита: только для авторизованных ──
    if not is_auth:
        await send_photo(
            query.message, PHOTO_AUTH,
            "👾 UserBot | Ru\n\n"
            "Сессия не найдена. Войди или зарегистрируйся.",
            get_guest_kb()
        )
        return "MENU"

    # ── Юзер-кнопки ──

    # ── Парсер юзернеймов ──
    if data == "u_unparser":
        # Запрашиваем пароль для доступа
        await send_plain(query.message,
            "🔍 Парсер юзернеймов\n\n"
            "🔒 Введи пароль для доступа к модулю:",
            InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]))
        context.user_data["await_unparser_pass"] = True
        return "UNPARSER"
        return "UNPARSER"

    if data == "unp_noop":
        return "UNPARSER"

    if data == "unp_settings":
        if tg_id not in UNPARSER_SESSIONS:
            UNPARSER_SESSIONS[tg_id] = {"cfg": {"length": 8, "digits": True, "count": 5}, "history": [], "current_idx": -1, "running": False}
        cfg = UNPARSER_SESSIONS[tg_id]["cfg"]
        await query.message.reply_text(_unp_menu_text(cfg), reply_markup=_unp_menu_kb(cfg))
        return "UNPARSER"

    if data in ("unp_len_minus", "unp_len_plus", "unp_digits", "unp_count_minus", "unp_count_plus"):
        if tg_id not in UNPARSER_SESSIONS:
            UNPARSER_SESSIONS[tg_id] = {"cfg": {"length": 8, "digits": True, "count": 5}, "history": [], "current_idx": -1, "running": False}
        cfg = UNPARSER_SESSIONS[tg_id]["cfg"]
        if data == "unp_len_minus":   cfg["length"] = max(5,  cfg.get("length", 8) - 1)
        elif data == "unp_len_plus":  cfg["length"] = min(32, cfg.get("length", 8) + 1)
        elif data == "unp_digits":    cfg["digits"] = not cfg.get("digits", True)
        elif data == "unp_count_minus": cfg["count"] = max(1,  cfg.get("count", 5) - 1)
        elif data == "unp_count_plus":  cfg["count"] = min(20, cfg.get("count", 5) + 1)
        await query.message.reply_text(_unp_menu_text(cfg), reply_markup=_unp_menu_kb(cfg))
        return "UNPARSER"

    if data == "unp_generate":
        if tg_id not in UNPARSER_SESSIONS:
            UNPARSER_SESSIONS[tg_id] = {"cfg": {"length": 8, "digits": True, "count": 5}, "history": [], "current_idx": -1, "running": False}
        sess = UNPARSER_SESSIONS[tg_id]
        if sess.get("running"):
            await query.answer("⏳ Уже генерирую...", show_alert=True)
            return "UNPARSER"
        sess["running"] = True
        await query.message.reply_text("⏳ Генерирую и проверяю юзернеймы...", reply_markup=None)
        batch = await _unp_generate(tg_id, sess["cfg"])
        sess["running"] = False
        sess["history"].append(batch)
        sess["current_idx"] = len(sess["history"]) - 1
        text = _unp_format(batch, sess["current_idx"], len(sess["history"]))
        await query.message.reply_text(text, reply_markup=_unp_result_kb(sess))
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
            await query.message.reply_text(_unp_format(batch, sess["current_idx"], len(sess["history"])), reply_markup=_unp_result_kb(sess))
        else:
            sess["running"] = True
            await query.message.reply_text("⏳ Генерирую новый батч...", reply_markup=None)
            batch = await _unp_generate(tg_id, sess["cfg"])
            sess["running"] = False
            sess["history"].append(batch)
            sess["current_idx"] = len(sess["history"]) - 1
            await query.message.reply_text(_unp_format(batch, sess["current_idx"], len(sess["history"])), reply_markup=_unp_result_kb(sess))
        return "UNPARSER"

    if data == "unp_prev":
        if tg_id not in UNPARSER_SESSIONS:
            return "UNPARSER"
        sess = UNPARSER_SESSIONS[tg_id]
        if sess["current_idx"] > 0:
            sess["current_idx"] -= 1
            batch = sess["history"][sess["current_idx"]]
            await query.message.reply_text(_unp_format(batch, sess["current_idx"], len(sess["history"])), reply_markup=_unp_result_kb(sess))
        return "UNPARSER"

    if data == "u_partner":
        mirrors   = load_mirrors()
        stats     = get_mirror_stats(tg_id)
        has_mirror = tg_id in mirrors and mirrors[tg_id].get("active")
        token_hint = mirrors[tg_id].get("token", "")[:10] + "..." if has_mirror else "не подключён"

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🔴 Отключить зеркало" if has_mirror else "➕ Подключить свой бот",
                callback_data="partner_toggle"
            )],
            [InlineKeyboardButton("📊 Статистика рефералов", callback_data="partner_stats")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]
        ])
        await send_plain(
            query.message,
            f"🪞 Партнёрская программа\n\n"
            "Подключи своего бота — он станет зеркалом UserBot | Ru.\n"
            "За каждого нового юзера который зарегистрируется через твой бот\n"
            "ты получаешь +1 день к подписке.\n\n"
            f"Статус: {'🟢 Активно' if has_mirror else '🔴 Не подключено'}\n"
            f"Токен: {token_hint}\n"
            f"Рефералов: {stats['total']}\n"
            f"Бонусных дней заработано: {stats['bonus_days']}",
            kb
        )
        return "MENU"

    if data == "partner_stats":
        refs = load_referrals()
        my_refs = [(uid, info) for uid, info in refs.items() if info.get("partner_id") == tg_id]
        users_all = load_json(USERS_FILE)
        lines = []
        for uid, info in my_refs[-10:]:  # последние 10
            nick = users_all.get(uid, {}).get("nick", uid)
            lines.append(f"  • {nick} — {info.get('date','?')}")
        total = len(my_refs)
        txt = (
            f"📊 Ваши рефералы\n\n"
            f"Всего: {total}\n"
            f"Бонусных дней: {total}\n\n"
        )
        if lines:
            txt += "Последние 10:\n" + "\n".join(lines)
        else:
            txt += "Рефералов пока нет."
        await send_plain(query.message, txt,
            InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_partner")]]))
        return "MENU"

    if data == "partner_toggle":
        mirrors = load_mirrors()
        if tg_id in mirrors and mirrors[tg_id].get("active"):
            # Отключаем
            await stop_mirror_bot(tg_id)
            mirrors[tg_id]["active"] = False
            save_mirrors(mirrors)
            await send_plain(query.message, "🔴 Зеркало отключено.", get_user_kb())
        else:
            # Запрашиваем токен
            await send_plain(query.message,
                "➕ Подключение зеркала\n\n"
                "1. Создай бота через @BotFather командой /newbot\n"
                "2. Скопируй токен (выглядит как 123456789:AAF...)\n"
                "3. Отправь токен сюда:",
                InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_partner")]]))
            return "WAIT_MIRROR_TOKEN"
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
        await send_photo(
            query.message, PHOTO_AUTH,
            "❌ Сессия сброшена. Юзербот отключён.\n\n"
            "Нажми кнопку чтобы войти снова:",
            get_guest_kb()
        )
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
        await send_plain(
            query.message,
            f"👤 Ваш профиль\n\n"
            f"🆔 ID: {tg_id}\n"
            f"🏷 Ник: {nick}\n"
            f"📱 Телефон: {phone}\n"
            f"⚡️ Движок: Telethon\n"
            f"📊 Статус: {status}\n"
            f"💎 Подписка: {sub_str}\n"
            f"🧩 Модули: {len(mods)}/{limit}",
            get_cancel_kb()
        )
        return "MENU"

    if data == "u_sub":
        await _show_sub_menu(query.message, tg_id)
        return "MENU"

    if data == "u_entercode":
        await send_plain(query.message,
            "🎟 Введи код подписки:\n\n"
            "Коды выдаются администратором или приобретаются на канале @userbotcbet",
            get_cancel_kb())
        return "WAIT_PROMO_ACTIVATE"

    if data == "sub_buy_trial":
        sub = load_sub(tg_id)
        if sub.get("plan") == "trial":
            await send_plain(query.message, "⚠️ Пробная подписка уже была активирована.", None)
            await _show_sub_menu(query.message, tg_id)
            return "MENU"
        from datetime import timezone, timedelta
        expires = (datetime.now(timezone.utc) + timedelta(days=5)).timestamp()
        sub["plan"]    = "trial"
        sub["expires"] = expires
        sub["chosen_sys"]  = []
        sub["chosen_mods"] = []
        save_sub(tg_id, sub)
        await send_plain(query.message,
            "🆓 Пробная подписка активирована на 5 дней!\n\n"
            "Выбери 1 системный модуль который хочешь использовать:",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Автоответчик", callback_data="sub_choose_sys_autoreply_trial")],
                [InlineKeyboardButton("🕐 Ник по времени", callback_data="sub_choose_sys_timenick_trial")],
            ])
        )
        return "MENU"

    if data == "sub_buy_basic":
        from telegram import LabeledPrice
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="Базовая подписка — UserBot | Ru",
            description="30 дней. 3 модуля из магазина, 2 системных на выбор.",
            payload=f"sub_basic_{tg_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Базовая подписка", 25)],
        )
        return "MENU"

    if data == "sub_buy_pro":
        from telegram import LabeledPrice
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="Про подписка — UserBot | Ru",
            description="30 дней. Все модули из магазина и все системные модули.",
            payload=f"sub_pro_{tg_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Про подписка", 50)],
        )
        return "MENU"

    if data.startswith("sub_choose_sys_"):
        # sub_choose_sys_autoreply_trial / sub_choose_sys_timenick_basic
        parts   = data[len("sub_choose_sys_"):].rsplit("_", 1)
        mod     = parts[0]
        plan_key = parts[1] if len(parts) > 1 else "trial"
        plan    = SUB_PLANS.get(plan_key, SUB_PLANS["trial"])
        sub     = load_sub(tg_id)
        chosen  = sub.get("chosen_sys", [])
        if mod not in chosen:
            chosen.append(mod)
        # Ограничиваем по слотам
        chosen = chosen[:plan["sys_slots"]]
        sub["chosen_sys"] = chosen
        save_sub(tg_id, sub)
        await send_plain(query.message,
            "✅ Системный модуль активирован!\n\n"
            "Теперь иди в 🔧 Системные модули.",
            get_user_kb())
        return "MENU"

    if data == "u_sonya":
        await send_photo(
            query.message, PHOTO_SONYA_SAD,
            "🤖 Соня — ИИ-ассистент\n\n"
            "Соня — персональный ИИ-помощник внутри юзербота.\n\n"
            "Она умеет отвечать на вопросы, помогать с настройкой модулей "
            "и поддержать разговор в любое время суток.\n\n"
            "😴 Сейчас Соня отдыхает...\n"
            "Функция ИИ-чата скоро будет доступна!\n\n"
            "📢 Канал: @userbotcbet",
            get_cancel_kb()
        )
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
            mods_text = "\n".join(_mod_label(m) for m in mods_list)
            mods_text += "\n\n👤 — свой модуль   🛒 — из магазина"
        else:
            mods_text = "  модули не установлены"

        # Строим клавиатуру: кнопка удаления для каждого модуля
        kb_rows = []
        for m in mods_list:
            src = m.get("source", "custom")
            badge = "👤" if src == "custom" or src is None else "🛒"
            kb_rows.append([
                InlineKeyboardButton(f"🗑 {badge} {m['name']}.py", callback_data=f"mod_delete_{m['name']}")
            ])
        kb_rows.append([InlineKeyboardButton("🛒 Магазин модулей", callback_data="mod_shop")])
        kb_rows.append([InlineKeyboardButton("➕ Установить своё .py", callback_data="mod_install")])
        kb_rows.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
        kb = InlineKeyboardMarkup(kb_rows)

        await send_photo(
            query.message, PHOTO_MODULES,
            f"🧩 Модули — UserBot | Ru\n\n"
            f"Здесь ты управляешь плагинами своего юзербота.\n"
            f"Модули загружаются прямо в Telethon-сессию.\n\n"
            f"Слотов занято: {used}/5\n\n"
            f"Установленные модули:\n{mods_text}\n\n"
            f"Нажми на модуль чтобы удалить его.",
            kb
        )
        return "MENU"

    # ── Удаление модуля ──
    if data.startswith("mod_delete_"):
        mod_name = data[len("mod_delete_"):]
        m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")

        async with _file_lock:
            m_data = load_json(m_file)
            before = len(m_data.get("modules", []))
            m_data["modules"] = [m for m in m_data.get("modules", []) if m["name"] != mod_name]
            after = len(m_data["modules"])
            save_json(m_file, m_data)

        # Удаляем .py файл с диска
        mod_path = os.path.join(MODULES_DIR, f"user_{tg_id}", f"{mod_name}.py")
        if os.path.exists(mod_path):
            try:
                os.remove(mod_path)
            except Exception as e:
                logger.error(f"Ошибка удаления файла модуля {mod_path}: {e}")

        # Убираем из кэша загруженных модулей
        if tg_id in LOADED_MODULES and mod_name in LOADED_MODULES[tg_id]:
            LOADED_MODULES[tg_id].remove(mod_name)

        if before != after:
            await send_plain(query.message, f"🗑 Модуль {mod_name}.py удалён.", None)
            # Перезапускаем юзербота если онлайн
            if tg_id in USER_BOTS:
                async with _file_lock:
                    users_reload = load_json(USERS_FILE)
                u_info = users_reload.get(tg_id, {})
                if u_info.get("api_id") and u_info.get("api_hash"):
                    await start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"])
        else:
            await send_plain(query.message, f"⚠️ Модуль {mod_name} не найден.", None)

        # Показываем обновлённый список модулей
        async with _file_lock:
            m_data = load_json(m_file)
        used      = len(m_data.get("modules", []))
        mods_list = m_data.get("modules", [])
        if mods_list:
            mods_text = "\n".join(
                f"  {'👤' if m.get('source','custom') in ('custom', None) else '🛒'} {m['name']}.py — {m.get('date','?')}" 
                for m in mods_list
            ) + "\n\n👤 — свой   🛒 — магазин"
        else:
            mods_text = "  модули не установлены"
        kb_rows = []
        for m in mods_list:
            kb_rows.append([InlineKeyboardButton(f"🗑 {m['name']}.py", callback_data=f"mod_delete_{m['name']}")])
        kb_rows.append([InlineKeyboardButton("➕ Установить модуль", callback_data="mod_install")])
        kb_rows.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
        await send_photo(
            query.message, PHOTO_MODULES,
            f"🧩 Модули — UserBot | Ru\n\n"
            f"Слотов занято: {used}/5\n\n"
            f"Установленные модули:\n{mods_text}\n\n"
            f"Нажми на модуль чтобы удалить его.",
            InlineKeyboardMarkup(kb_rows)
        )
        return "MENU"

    if data == "mod_install":
        await send_plain(
            query.message,
            "🔗 Отправьте прямую ссылку на .py плагин\n"
            "или прикрепите файл документом:",
            get_cancel_kb()
        )
        return "MODULE_INSTALL"

    # ── Системные модули — главное меню ──
    if data == "u_sysmods":
        await _show_sysmods(query.message, tg_id, "main")
        return "MENU"

    if data == "u_sysmods_autoreply":
        await _show_sysmods(query.message, tg_id, "autoreply")
        return "MENU"

    if data == "u_sysmods_timenick":
        await _show_sysmods(query.message, tg_id, "timenick")
        return "MENU"

    # ── Автоответчик ──
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

    # ── Ник по времени ──
    if data == "sysmod_timenick_toggle":
        cfg     = _load_timenick_cfg(tg_id)
        enabled = not cfg.get("enabled", False)
        cfg["enabled"] = enabled
        _save_timenick_cfg(tg_id, cfg)
        # Запускаем или останавливаем цикл
        client = USER_BOTS.get(tg_id)
        if client:
            if enabled and cfg.get("nickname"):
                asyncio.create_task(client._timenick_start(tg_id))
            else:
                client._timenick_stop(tg_id)
        await _show_sysmods(query.message, tg_id, "timenick")
        return "MENU"

    if data == "sysmod_timenick_setnick":
        await send_plain(query.message,
            "✏️ Введи никнейм (без времени):\n"
            "Пример: cbet_cebep\n\n"
            "Бот сам добавит | HH:MM",
            InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods_timenick")]]))
        context.user_data["await_timenick"] = "nick"
        return "WAIT_TIMENICK"

    if data == "sysmod_timenick_setsec":
        await send_plain(query.message,
            "⏱ Введи секунду обновления (0-59):\n\n"
            "Например: 0 — обновление в начале каждой минуты\n"
            "30 — обновление на 30-й секунде каждой минуты",
            InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods_timenick")]]))
        context.user_data["await_timenick"] = "second"
        return "WAIT_TIMENICK"

    if data == "sysmod_timenick_settz":
        cfg = _load_timenick_cfg(tg_id)
        cur = cfg.get("tz_offset", 3)
        # Быстрые кнопки для популярных зон
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("UTC+2", callback_data="sysmod_tz_2"),
             InlineKeyboardButton("UTC+3 (МСК)", callback_data="sysmod_tz_3"),
             InlineKeyboardButton("UTC+4", callback_data="sysmod_tz_4")],
            [InlineKeyboardButton("UTC+5", callback_data="sysmod_tz_5"),
             InlineKeyboardButton("UTC+6", callback_data="sysmod_tz_6"),
             InlineKeyboardButton("UTC+7", callback_data="sysmod_tz_7")],
            [InlineKeyboardButton("✏️ Ввести вручную", callback_data="sysmod_timenick_settz_manual")],
            [InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods_timenick")]
        ])
        await send_plain(query.message,
            f"🌍 Выбери часовой пояс\n\nСейчас: UTC+{cur}",
            kb)
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
        await send_plain(query.message,
            "🌍 Введи смещение от UTC (целое число):\n\n"
            "Примеры: 3 (Москва), 5 (Екб), -5 (США EST)",
            InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_sysmods_timenick")]]))
        context.user_data["await_timenick"] = "tz"
        return "WAIT_TIMENICK"

    # ── Магазин стоковых модулей ──
    if data == "mod_shop":
        # Читаем список доступных стоковых модулей
        stock = []
        if os.path.exists(STOCK_MODULES_DIR):
            for fname in sorted(os.listdir(STOCK_MODULES_DIR)):
                if fname.endswith(".py"):
                    stock.append(fname[:-3])

        if not stock:
            await send_plain(query.message, "🛒 Магазин пока пуст. Скоро появятся модули!", get_cancel_kb())
            return "MENU"

        # Читаем уже установленные модули юзера
        m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
        async with _file_lock:
            m_data = load_json(m_file)
        installed = {m["name"] for m in m_data.get("modules", [])}

        # Строим клавиатуру магазина
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

        await send_photo(
            query.message, PHOTO_MODULES,
            f"🛒 Магазин модулей\n\n"
            f"Выбери модуль для установки:\n\n"
            + "\n".join(lines) +
            f"\n\nНажми на модуль чтобы установить.",
            InlineKeyboardMarkup(kb_rows)
        )
        return "MENU"

    # ── Установка стокового модуля ──
    if data.startswith("mod_get_"):
        mod_name = data[len("mod_get_"):]
        src_path = os.path.join(STOCK_MODULES_DIR, f"{mod_name}.py")

        if not os.path.exists(src_path):
            await send_plain(query.message, f"❌ Модуль {mod_name} не найден в магазине.", get_cancel_kb())
            return "MENU"

        # Проверяем лимит по подписке
        m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
        async with _file_lock:
            m_data = load_json(m_file)
        current = len(m_data.get("modules", []))
        plan    = get_plan(tg_id)
        limit   = plan["mod_slots"]
        if current >= limit:
            await send_plain(query.message,
                f"⚠️ Достигнут лимит модулей ({current}/{limit}) для твоей подписки.\n"

                f"Улучши подписку в разделе 💎 Подписка.",
                get_user_kb())
            return "MENU"

        # Копируем файл в папку юзера
        import shutil
        user_dir = os.path.join(MODULES_DIR, f"user_{tg_id}")
        os.makedirs(user_dir, exist_ok=True)
        dst_path = os.path.join(user_dir, f"{mod_name}.py")
        shutil.copy2(src_path, dst_path)

        # Копируем menu.json модуля если есть
        menu_src = os.path.join(STOCK_MODULES_DIR, f"{mod_name}_menu.json")
        if os.path.exists(menu_src):
            shutil.copy2(menu_src, os.path.join(user_dir, f"{mod_name}_menu.json"))

        # Обновляем реестр
        async with _file_lock:
            m_data.setdefault("modules", [])
            # Не дублируем если уже есть
            if not any(m["name"] == mod_name for m in m_data["modules"]):
                m_data["modules"].append({
                    "name": mod_name,
                    "date": datetime.now().strftime("%d.%m.%Y"),
                    "source": "shop"
                })
            save_json(m_file, m_data)

        # Перезапускаем юзербота если онлайн
        if tg_id in USER_BOTS:
            async with _file_lock:
                users_reload = load_json(USERS_FILE)
            u_info = users_reload.get(tg_id, {})
            if u_info.get("api_id") and u_info.get("api_hash"):
                await start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"])
            await send_plain(query.message, f"✅ Модуль {mod_name}.py установлен и загружен в юзербот!", None)
        else:
            await send_plain(query.message, f"✅ Модуль {mod_name}.py установлен. Запустите юзербота для активации.", None)

        # Возвращаемся в магазин
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
        await send_photo(
            query.message, PHOTO_MODULES,
            f"🛒 Магазин модулей\n\n" + "\n".join(lines) + "\n\nНажми на модуль чтобы установить.",
            InlineKeyboardMarkup(kb_rows)
        )
        return "MENU"

    return "MENU"


# ─── LOGIN_PHONE_EXISTING ──────────────────────────────────────────

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
        await send_photo(
            update.message, PHOTO_AUTH,
            f"❌ Номер {phone} не найден в системе.\n\n"
            "Если ты новый пользователь — используй Регистрацию.",
            get_guest_kb()
        )
        return "MENU"

    if not found_user.get("api_id") or not found_user.get("api_hash"):
        await send_photo(update.message, PHOTO_AUTH, "⚠️ Данные аккаунта повреждены. Необходима повторная регистрация.", get_guest_kb())
        return "MENU"

    context.user_data["phone"]              = phone
    context.user_data["api_id"]             = int(found_user["api_id"])
    context.user_data["api_hash"]           = found_user["api_hash"]
    context.user_data["reg_nick"]           = found_user.get("nick", f"User_{found_id[:4]}")
    context.user_data["login_existing_id"]  = found_id

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
                await send_photo(
                    update.message, PHOTO_MENU,
                    f"🎉 Добро пожаловать обратно, {nick}!\n\n"
                    "Юзербот восстановлен и активен.\n\n"
                    "Выбери раздел:",
                    get_user_kb()
                )
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
        await send_photo(
            update.message, PHOTO_AUTH,
            "📩 Код отправлен!\n\n"
            "Telegram прислал код в приложение.\n"
            "Введи его через пин-пад ниже 👇",
            get_pinpad_kb("")
        )
        return "WAIT_CODE"
    except Exception as e:
        logger.error(f"Ошибка при повторном входе {found_id}: {e}")
        await send_photo(update.message, PHOTO_AUTH, f"❌ Ошибка: {e}\n\nПопробуй снова — /start", get_guest_kb())
        return "MENU"


# ─── REG_NICK ─────────────────────────────────────────────────────

async def reg_nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nick = update.message.text.strip()
    async with _file_lock:
        users = load_json(USERS_FILE)
    taken = any(v.get("nick", "").lower() == nick.lower() for v in users.values())
    if taken:
        await send_plain(update.message, f"⚠️ Никнейм {nick} уже занят. Введите другой:", get_cancel_kb())
        return "REG_NICK"
    context.user_data["reg_nick"] = nick
    await send_photo(
        update.message, PHOTO_AUTH,
        "📱 Авторизация — Шаг 2 из 4\n\n"
        "Введи номер телефона привязанный к твоему Telegram-аккаунту.\n\n"
        "На него придёт код подтверждения от Telegram.\n"
        "Формат: +79001234567 или +380XXXXXXXXX\n\n"
        "Мы не используем номер для рассылок.",
        get_cancel_kb()
    )
    return "LOGIN_PHONE"


# ─── LOGIN_PHONE ───────────────────────────────────────────────────

async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        await send_plain(update.message, "⚠️ Неверный формат. Пример: +79001234567\n\nПовторите ввод:", get_cancel_kb())
        return "LOGIN_PHONE"
    async with _file_lock:
        users = load_json(USERS_FILE)
    taken = any(v.get("phone", "") == phone and v.get("authenticated", False) for v in users.values())
    if taken:
        await send_plain(
            update.message,
            f"⚠️ Номер {phone} уже зарегистрирован в системе.\n\n"
            "Если это ваш номер — используй кнопку Войти.",
            get_cancel_kb()
        )
        return "LOGIN_PHONE"
    context.user_data["phone"] = phone
    await send_photo(
        update.message, PHOTO_AUTH,
        "🔑 Авторизация — Шаг 3 из 4\n\n"
        "Введи свой API ID — числовой идентификатор приложения Telegram.\n\n"
        "Как получить:\n"
        "1. Зайди на my.telegram.org\n"
        "2. Войди в свой аккаунт\n"
        "3. Раздел API development tools\n"
        "4. Скопируй поле api_id\n\n"
        "Выглядит как число: 12345678\n\n"
        "Помощь: @userbotcbet",
        get_cancel_kb()
    )
    return "LOGIN_API_ID"


# ─── LOGIN_API_ID ──────────────────────────────────────────────────

async def login_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    if not val.isdigit():
        await send_plain(update.message, "⚠️ API ID — только цифры. Повторите ввод:", get_cancel_kb())
        return "LOGIN_API_ID"
    context.user_data["api_id"] = int(val)
    await send_photo(
        update.message, PHOTO_AUTH,
        "🔑 Авторизация — Шаг 4 из 4\n\n"
        "Введи свой API Hash — секретный ключ приложения Telegram.\n\n"
        "Где найти:\n"
        "Тот же раздел на my.telegram.org\n"
        "Поле api_hash\n\n"
        "Выглядит так: a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6\n\n"
        "Ключ хранится только на сервере.\n\n"
        "Помощь: @userbotcbet",
        get_cancel_kb()
    )
    return "LOGIN_API_HASH"


# ─── LOGIN_API_HASH ────────────────────────────────────────────────

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
        await send_photo(
            update.message, PHOTO_AUTH,
            "📩 Код подтверждения отправлен!\n\n"
            "Telegram прислал тебе код в приложение или SMS.\n\n"
            "Введи его с помощью пин-пада ниже.\n"
            "Код действителен несколько минут — не затягивай!",
            get_pinpad_kb("")
        )
        return "WAIT_CODE"
    except Exception as e:
        logger.error(f"Telethon send_code error для {tg_id}: {e}")
        try: await client.disconnect()
        except Exception: pass
        await send_photo(update.message, PHOTO_AUTH, f"❌ Ошибка API Telegram: {e}\n\nПопробуйте снова — /start", get_guest_kb())
        return "MENU"


# ─── WAIT_CODE: пин-пад ───────────────────────────────────────────

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
        users[tg_id] = {
            "nick":          nick,
            "phone":         phone,
            "api_id":        context.user_data["api_id"],
            "api_hash":      context.user_data["api_hash"],
            "authenticated": True,
            "created_at":    datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        save_json(USERS_FILE, users)
    USER_BOTS[tg_id] = client
    load_user_modules(client, tg_id)

    msg  = update.callback_query.message if update.callback_query else update.message

    # Выдаём пробную подписку при первой регистрации
    sub    = load_sub(tg_id)
    is_new = not sub.get("plan")
    if is_new:
        from datetime import timezone, timedelta
        expires = (datetime.now(timezone.utc) + timedelta(days=5)).timestamp()
        sub["plan"]        = "trial"
        sub["expires"]     = expires
        sub["chosen_sys"]  = []
        sub["chosen_mods"] = []
        save_sub(tg_id, sub)

    if is_new:
        await send_photo(
            msg, PHOTO_MENU,
            f"🎉 Добро пожаловать, {nick}!\n\n"
            "Твой юзербот успешно запущен в облаке.\n\n"
            "🆓 Тебе выдана пробная подписка на 5 дней!\n\n"
            "Выбери 1 системный модуль который хочешь попробовать:",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Автоответчик",   callback_data="sub_choose_sys_autoreply_trial")],
                [InlineKeyboardButton("🕐 Ник по времени", callback_data="sub_choose_sys_timenick_trial")],
            ])
        )
    else:
        await send_photo(
            msg, PHOTO_MENU,
            f"🎉 Добро пожаловать, {nick}!\n\n"
            "Твой юзербот успешно запущен в облаке.\n\n"
            "⚡️ Сессия Telethon активна\n"
            "🧩 Модули готовы к установке\n\n"
            "Выбери раздел:",
            get_user_kb()
        )
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
        logger.info(f"2FA требуется для {tg_id}")
        context.user_data["awaiting_2fa"] = True
        await send_photo(
            query.message, PHOTO_AUTH,
            "🔐 Двухфакторная аутентификация\n\n"
            "На твоём аккаунте включён облачный пароль (2FA).\n\n"
            "Введи пароль который ты задал в настройках Telegram:\n"
            "Настройки → Конфиденциальность → Облачный пароль\n\n"
            "Пароль передаётся напрямую в Telegram и не сохраняется.",
            get_cancel_kb()
        )
        return "WAIT_2FA"
    except Exception as e:
        logger.error(f"sign_in error для {tg_id}: {e}")
        await _cleanup_failed_session(tg_id, client)
        await send_photo(query.message, PHOTO_AUTH, f"❌ Ошибка входа: {e}\n\nПопробуйте снова — /start", get_guest_kb())
        return "MENU"


# ─── WAIT_2FA ─────────────────────────────────────────────────────

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


# ─── MODULE_INSTALL ────────────────────────────────────────────────

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
        await send_plain(update.message,
            f"⚠️ Достигнут лимит модулей ({current}/{limit}) для твоей подписки.\n"

            f"Улучши подписку в разделе 💎 Подписка.",
            get_user_kb())
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


# ─── UNPARSER PASSWORD: Проверка пароля парсера ──────────────────

async def unparser_password_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)

    if not context.user_data.get("await_unparser_pass"):
        return "UNPARSER"

    password = update.message.text.strip()
    context.user_data.pop("await_unparser_pass", None)

    if password != ADMIN_PASSWORD:
        await send_plain(update.message,
            "❌ Неверный пароль.\n\n"
            "🔍 Парсер юзернеймов пока находится в разработке.\n"
            "Следи за обновлениями на канале @userbotcbet",
            InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_main")]]))
        return "MENU"

    # Пароль верный — открываем парсер
    if tg_id not in UNPARSER_SESSIONS:
        UNPARSER_SESSIONS[tg_id] = {
            "cfg": {"length": 8, "digits": True, "count": 5},
            "history": [],
            "current_idx": -1,
            "running": False,
        }
    cfg = UNPARSER_SESSIONS[tg_id]["cfg"]
    await send_plain(update.message, _unp_menu_text(cfg), _unp_menu_kb(cfg))
    return "UNPARSER"


# ─── WAIT_MIRROR_TOKEN: Ввод токена зеркала ──────────────────────

async def wait_mirror_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    token = update.message.text.strip()

    # Базовая проверка формата токена
    if ":" not in token or len(token) < 30:
        await send_plain(update.message,
            "❌ Неверный формат токена.\n"

            "Токен выглядит так: 123456789:AAFxxxxxxxx\n"

            "Попробуй ещё раз:",
            InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_partner")]]))
        return "WAIT_MIRROR_TOKEN"

    # Проверяем лимит зеркал
    mirrors = load_mirrors()
    active_count = sum(1 for m in mirrors.values() if m.get("active"))
    if active_count >= MAX_MIRRORS and tg_id not in mirrors:
        await send_plain(update.message,
            f"⚠️ Достигнут лимит зеркал ({MAX_MIRRORS}). Попробуй позже.",
            get_user_kb())
        return "MENU"

    # Проверяем что токен рабочий
    await send_plain(update.message, "⏳ Проверяем токен...", None)
    try:
        import aiohttp as _aio
        async with _aio.ClientSession() as sess:
            async with sess.get(f"https://api.telegram.org/bot{token}/getMe") as resp:
                data = await resp.json()
                if not data.get("ok"):
                    raise Exception(data.get("description", "Неверный токен"))
                bot_info = data["result"]
                bot_name = bot_info.get("username", "unknown")
    except Exception as e:
        await send_plain(update.message,
            f"❌ Ошибка токена: {e}\n\nПроверь токен и попробуй снова:",
            InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="u_partner")]]))
        return "WAIT_MIRROR_TOKEN"

    # Сохраняем и запускаем зеркало
    users_all = load_json(USERS_FILE)
    partner_nick = users_all.get(tg_id, {}).get("nick", tg_id)

    mirrors[tg_id] = {
        "token":   token,
        "bot_username": bot_name,
        "nick":    partner_nick,
        "active":  True,
        "created": datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    save_mirrors(mirrors)

    success = await start_mirror_bot(tg_id, token, partner_nick)
    if success:
        await send_plain(update.message,
            f"✅ Зеркало подключено!\n"

            f"Бот: @{bot_name}\n"
            f"За каждого нового юзера через твой бот — +1 день к подписке.\n"

            f"Поделись ссылкой: t.me/{bot_name}",
            get_user_kb())
    else:
        mirrors[tg_id]["active"] = False
        save_mirrors(mirrors)
        await send_plain(update.message,
            "❌ Не удалось запустить зеркало. Проверь что бот не запущен в другом месте.",
            get_user_kb())
    return "MENU"


# ─── WAIT_TIMENICK: Ввод никнейма или секунды ────────────────────

async def wait_timenick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id  = str(update.effective_user.id)
    text   = update.message.text.strip()
    field  = context.user_data.get("await_timenick")

    cfg = _load_timenick_cfg(tg_id)

    if field == "nick":
        if not text:
            await send_plain(update.message, "⚠️ Никнейм не может быть пустым.", None)
            return "WAIT_TIMENICK"
        cfg["nickname"] = text
        _save_timenick_cfg(tg_id, cfg)
        # Перезапускаем если включён
        client = USER_BOTS.get(tg_id)
        if client and cfg.get("enabled"):
            client._timenick_stop(tg_id)
            asyncio.create_task(client._timenick_start(tg_id))
        await send_plain(update.message, f"✅ Никнейм сохранён: {text}", None)

    elif field == "second":
        if not text.lstrip("-").isdigit() or not (0 <= int(text) <= 59):
            await send_plain(update.message, "⚠️ Введи число от 0 до 59.", None)
            return "WAIT_TIMENICK"
        cfg["second"] = int(text)
        _save_timenick_cfg(tg_id, cfg)
        client = USER_BOTS.get(tg_id)
        if client and cfg.get("enabled"):
            client._timenick_stop(tg_id)
            asyncio.create_task(client._timenick_start(tg_id))
        await send_plain(update.message, f"✅ Секунда обновления: {text}с", None)

    elif field == "tz":
        if not text.lstrip("-").isdigit() or not (-12 <= int(text) <= 14):
            await send_plain(update.message, "⚠️ Введи число от -12 до 14.", None)
            return "WAIT_TIMENICK"
        cfg["tz_offset"] = int(text)
        _save_timenick_cfg(tg_id, cfg)
        client = USER_BOTS.get(tg_id)
        if client and cfg.get("enabled"):
            client._timenick_stop(tg_id)
            asyncio.create_task(client._timenick_start(tg_id))
        await send_plain(update.message, f"✅ Часовой пояс: UTC+{text}", None)

    context.user_data.pop("await_timenick", None)
    await _show_sysmods(update.message, tg_id, "timenick")
    return "MENU"


# ─── SONYA_CHAT ───────────────────────────────────────────────────

async def sonya_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_photo(
        update.message, PHOTO_SONYA_SAD,
        "🤖 Соня сейчас не на связи. Попробуйте позже.\n\n"
        "📢 Канал: @userbotcbet",
        get_cancel_kb()
    )
    return "SONYA_CHAT"


# ─── /setimages ───────────────────────────────────────────────────

async def cmd_set_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["setimages_step"] = 0
    context.user_data["setimages_keys"] = ["auth", "modules", "sonya_sad", "menu"]
    context.user_data["setimages_names"] = [
        "auth.jpg (авторизация)",
        "modules.jpg (модули)",
        "sonya_sad.jpg (Соня)",
        "menu.jpg (главное меню)"
    ]
    await send_plain(
        update.message,
        "🖼 Загрузка картинок\n\n"
        "Отправь фото по очереди:\n"
        "1. auth.jpg — экран авторизации\n"
        "2. modules.jpg — экран модулей\n"
        "3. sonya_sad.jpg — экран Сони\n"
        "4. menu.jpg — главное меню\n\n"
        "Отправь первое фото:",
        None
    )
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
    logger.info(f"Сохранён file_id для {keys[step]}: {file_id}")

    step += 1
    context.user_data["setimages_step"] = step

    if step < len(keys):
        await send_plain(update.message, f"✅ {names[step-1]} сохранена!\n\nТеперь отправь: {names[step]}", None)
        return "SET_IMAGES"
    else:
        kb = get_user_kb() if is_user_authorized(str(update.effective_user.id)) else get_guest_kb()
        await send_plain(update.message, "🎉 Все картинки успешно загружены!", kb)
        return "MENU"


# ─── PROMO ────────────────────────────────────────────────────────

async def promo_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    code  = update.message.text.strip().upper()

    async with _file_lock:
        promos = load_json(PROMO_FILE)

    if code not in promos:
        await send_plain(update.message,
            "❌ Код не найден. Проверь правильность ввода.\n"

            "Коды можно получить на канале @userbotcbet",
            get_cancel_kb())
        return "WAIT_PROMO_ACTIVATE"

    promo = promos[code]
    if tg_id in promo.get("used_by", []):
        await send_plain(update.message, "⚠️ Этот код уже был использован тобой.", get_user_kb())
        return "MENU"
    if len(promo.get("used_by", [])) >= promo.get("max_uses", 1):
        await send_plain(update.message, "⚠️ Код исчерпан.", get_user_kb())
        return "MENU"

    # Применяем код
    plan_key = promo.get("plan", "basic")
    days     = promo.get("days", SUB_PLANS.get(plan_key, {}).get("days", 30))

    from datetime import timezone, timedelta
    sub = load_sub(tg_id)
    # Если подписка ещё активна — продлеваем
    now_ts = datetime.now(timezone.utc).timestamp()
    base   = max(sub.get("expires", now_ts), now_ts)
    sub["plan"]    = plan_key
    sub["expires"] = base + days * 86400
    save_sub(tg_id, sub)

    async with _file_lock:
        promos[code]["used_by"].append(tg_id)
        save_json(PROMO_FILE, promos)

    plan = SUB_PLANS.get(plan_key, SUB_PLANS["basic"])

    # Уведомление админу
    try:
        used_count = len(promos[code]["used_by"])
        max_uses   = promos[code].get("max_uses", 1)
        async with _file_lock:
            users_all = load_json(USERS_FILE)
        user_nick = users_all.get(tg_id, {}).get("nick", tg_id)
        await context.bot.send_message(
            chat_id=ADMIN_TG_ID,
            text=(
                f"🎟 Промокод активирован!\n\n"
                f"Код: `{code}`\n"
                f"Юзер: {user_nick} (`{tg_id}`)\n"
                f"План: {plan['emoji']} {plan['name']} — {days} дн.\n"
                f"Использований: {used_count}/{max_uses}"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление админу: {e}")

    if plan_key == "pro":
        # Про — открываем всё без выбора
        await send_plain(update.message,
            f"✅ Код активирован!\n\n"
            f"{plan['emoji']} {plan['name']} — {days} дней\n"
            "Все модули и системные функции доступны.",
            get_user_kb())
    elif plan_key == "basic":
        # Базовая — выбираем 2 системных модуля
        await send_plain(update.message,
            f"✅ Код активирован!\n\n"
            f"{plan['emoji']} {plan['name']} — {days} дней\n\n"
            "Выбери до 2 системных модулей (нажимай по одному):",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Автоответчик",   callback_data="sub_choose_sys_autoreply_basic")],
                [InlineKeyboardButton("🕐 Ник по времени", callback_data="sub_choose_sys_timenick_basic")],
            ]))
    elif plan_key == "trial":
        # Пробная — выбираем 1 системный модуль
        await send_plain(update.message,
            f"✅ Код активирован!\n\n"
            f"{plan['emoji']} {plan['name']} — {days} дней\n\n"
            "Выбери 1 системный модуль:",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Автоответчик",   callback_data="sub_choose_sys_autoreply_trial")],
                [InlineKeyboardButton("🕐 Ник по времени", callback_data="sub_choose_sys_timenick_trial")],
            ]))
    else:
        await send_plain(update.message,
            f"✅ Код активирован! {plan['emoji']} {plan['name']} — {days} дней",
            get_user_kb())
    return "MENU"


# ─── ADMIN ────────────────────────────────────────────────────────

async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() != ADMIN_PASSWORD:
        await send_plain(update.message, "❌ Доступ отклонён.", get_guest_kb())
        return "MENU"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Пользователи", callback_data="a_users"),
         InlineKeyboardButton("🎫 Промокоды",    callback_data="a_promos")],
        [InlineKeyboardButton("🪞 Рефералы",     callback_data="a_referrals")],
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
            [InlineKeyboardButton("👥 Пользователи", callback_data="a_users"),
             InlineKeyboardButton("🎫 Промокоды",    callback_data="a_promos")],
            [InlineKeyboardButton("🪞 Рефералы",     callback_data="a_referrals")],
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
            plan_name = {"trial": "🆓 Пробная", "basic": "⭐️ Базовая", "pro": "👑 Про"}.get(v.get("plan", v.get("tier", "?")), "?")
            lines.append(f"• {k} — {plan_name} {v.get('days','?')} дн. | {used}/{v.get('max_uses','∞')}")
        txt = "🎫 Промокоды:\n\n" + "\n".join(lines)
        await send_plain(query.message, txt, InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_admin")]]))
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
            bot_un = info.get("bot_username", pid)
            nick   = info.get("nick", pid)
            refs   = get_mirror_stats(pid)["total"]
            rows.append([InlineKeyboardButton(
                f"{status} @{bot_un} ({nick}) — {refs} реф.",
                callback_data=f"a_mirror_{pid}"
            )])
            lines_txt.append(f"{status} @{bot_un} | {nick} | {refs} реф.")
        rows.append([InlineKeyboardButton("◀️ Назад", callback_data="back_admin")])
        await send_plain(
            query.message,
            "🪞 Зеркала и рефералы\n\n" + "\n".join(lines_txt) + "\n\nНажми на зеркало:",
            InlineKeyboardMarkup(rows)
        )
        return "ADMIN_MENU"

    if data.startswith("a_mirror_") and not data.startswith("a_mirror_toggle_") and not data.startswith("a_mirror_del_"):
        pid      = data[len("a_mirror_"):]
        mirrors  = load_mirrors()
        info     = mirrors.get(pid, {})
        if not info:
            await send_plain(query.message, "❌ Зеркало не найдено.", admin_kb())
            return "ADMIN_MENU"
        stats    = get_mirror_stats(pid)
        bot_un   = info.get("bot_username", "?")
        nick     = info.get("nick", pid)
        token    = info.get("token", "")
        created  = info.get("created", "?")
        active   = pid in MIRROR_APPS
        status   = "🟢 Активно" if active else "🔴 Остановлено"
        refs_all = load_referrals()
        ref_list = [(uid, d) for uid, d in refs_all.items() if d.get("partner_id") == pid]
        users_all = load_json(USERS_FILE)
        ref_lines = []
        for uid, d in ref_list[-5:]:
            rn = users_all.get(uid, {}).get("nick", uid)
            ref_lines.append(f"  • {rn} — {d.get('date','?')}") 
        ref_txt = "\n".join(ref_lines) if ref_lines else "  нет рефералов"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "⏸ Приостановить" if active else "▶️ Запустить",
                callback_data=f"a_mirror_toggle_{pid}"
            )],
            [InlineKeyboardButton("🗑 Удалить зеркало", callback_data=f"a_mirror_del_{pid}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="a_referrals")]
        ])
        await send_plain(
            query.message,
            f"🪞 Зеркало @{bot_un}\n\n"
            f"Партнёр: {nick} ({pid})\n"
            f"Статус: {status}\n"
            f"Создано: {created}\n"
            f"Токен: {token[:12]}...\n"
            f"Рефералов: {stats['total']}\n"
            f"Бонусных дней: {stats['bonus_days']}\n\n"
            f"Последние рефералы:\n{ref_txt}",
            kb
        )
        return "ADMIN_MENU"

    if data.startswith("a_mirror_toggle_"):
        pid     = data[len("a_mirror_toggle_"):]
        mirrors = load_mirrors()
        info    = mirrors.get(pid, {})
        if pid in MIRROR_APPS:
            await stop_mirror_bot(pid)
            mirrors[pid]["active"] = False
            save_mirrors(mirrors)
            await send_plain(query.message,
                f"⏸ Зеркало @{info.get('bot_username','?')} приостановлено.",
                InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data=f"a_mirror_{pid}")]]))
        else:
            success = await start_mirror_bot(pid, info["token"], info.get("nick", pid))
            mirrors[pid]["active"] = success
            save_mirrors(mirrors)
            msg = f"▶️ Зеркало запущено." if success else "❌ Не удалось запустить."
            await send_plain(query.message, msg,
                InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data=f"a_mirror_{pid}")]]))
        return "ADMIN_MENU"

    if data.startswith("a_mirror_del_"):
        pid     = data[len("a_mirror_del_"):]
        mirrors = load_mirrors()
        info    = mirrors.get(pid, {})
        bot_un  = info.get("bot_username", pid)
        await stop_mirror_bot(pid)
        if pid in mirrors:
            del mirrors[pid]
        save_mirrors(mirrors)
        await send_plain(query.message, f"🗑 Зеркало @{bot_un} удалено.", admin_kb())
        return "ADMIN_MENU"

    return "MENU"


# ─── /reset_me ────────────────────────────────────────────────────

async def cmd_reset_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    async with _file_lock:
        users = load_json(USERS_FILE)
        if tg_id in users:
            del users[tg_id]
            save_json(USERS_FILE, users)
    for ext in (".session", ".session-journal"):
        p = os.path.join(DATA_DIR, f"session_{tg_id}{ext}")
        if os.path.exists(p):
            try: os.remove(p)
            except Exception: pass
    if tg_id in USER_BOTS:
        try:
            await USER_BOTS[tg_id].disconnect()
            del USER_BOTS[tg_id]
        except Exception: pass
    if tg_id in LOADED_MODULES:
        del LOADED_MODULES[tg_id]
    context.user_data.clear()
    logger.info(f"Сброс аккаунта для {tg_id}")
    await send_photo(
        update.message, PHOTO_AUTH,
        "🗑 Аккаунт сброшен.\n\n"
        "Все данные удалены. Теперь можешь зарегистрироваться заново.",
        get_guest_kb()
    )
    return "MENU"


# ═══════════════════════════════════════════════════════════════════
# 🎟 ГЕНЕРАЦИЯ ПРОМОКОДОВ (только для админа)
# ═══════════════════════════════════════════════════════════════════

async def cmd_addpromo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addpromo <план> <дней> <количество>
    Пример: /addpromo pro 30 3
    Планы: trial, basic, pro
    """
    import random, string

    tg_id = str(update.effective_user.id)
    args  = context.args

    if update.message.text.split()[1] if len(update.message.text.split()) > 1 else "" == "":
        await update.message.reply_text(
            "Использование: /addpromo <план> <дней> <количество>\n"
            "Пример: /addpromo pro 30 3"
        )
        return "MENU"

    # Проверка пароля через args или только для известных admin id
    if len(args) < 3:
        await update.message.reply_text(
            "Использование: /addpromo <план> <дней> <количество>\n"
            "Пример: /addpromo pro 30 3"
        )
        return "MENU"

    plan_key = args[0].lower()
    if plan_key not in SUB_PLANS:
        await update.message.reply_text(f"❌ Неизвестный план: {plan_key}\nДоступны: trial, basic, pro")
        return "MENU"

    try:
        days  = int(args[1])
        count = int(args[2])
    except ValueError:
        await update.message.reply_text("❌ Дней и количество должны быть числами.")
        return "MENU"

    if not (1 <= days <= 365):
        await update.message.reply_text("❌ Дней: от 1 до 365.")
        return "MENU"
    if not (1 <= count <= 50):
        await update.message.reply_text("❌ Количество: от 1 до 50.")
        return "MENU"

    async with _file_lock:
        promos = load_json(PROMO_FILE)

    new_codes = []
    attempts  = 0
    while len(new_codes) < count and attempts < count * 10:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if code not in promos:  # гарантируем уникальность
            promos[code] = {"plan": plan_key, "days": days, "max_uses": 1, "used_by": []}
            new_codes.append(code)
        attempts += 1

    async with _file_lock:
        save_json(PROMO_FILE, promos)

    plan = SUB_PLANS[plan_key]
    lines = [f"{plan['emoji']} {plan['name']} — {days} дн.  →  `{c}`" for c in new_codes]
    await update.message.reply_text(
        f"✅ Создано {count} промокодов:\n\n" + "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN
    )
    return "MENU"


# ═══════════════════════════════════════════════════════════════════
# 💳 ОБРАБОТКА ОПЛАТЫ STARS
# ═══════════════════════════════════════════════════════════════════

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждаем любой платёж."""
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выдаём подписку после успешной оплаты."""
    tg_id   = str(update.effective_user.id)
    payload = update.message.successful_payment.payload  # sub_basic_123 или sub_pro_123

    from datetime import timezone, timedelta

    if payload.startswith("sub_basic_"):
        plan_key = "basic"
    elif payload.startswith("sub_pro_"):
        plan_key = "pro"
    else:
        return

    plan = SUB_PLANS[plan_key]
    sub  = load_sub(tg_id)
    now_ts = datetime.now(timezone.utc).timestamp()
    base   = max(sub.get("expires", now_ts), now_ts)
    sub["plan"]    = plan_key
    sub["expires"] = base + plan["days"] * 86400
    save_sub(tg_id, sub)


    # Уведомление админу об оплате Stars
    try:
        async with _file_lock:
            users_all = load_json(USERS_FILE)
        user_nick = users_all.get(tg_id, {}).get("nick", tg_id)
        stars = update.message.successful_payment.total_amount
        await context.bot.send_message(
            chat_id=ADMIN_TG_ID,
            text=(
                f"💳 Оплата Stars!\n\n"
                f"Юзер: {user_nick} (`{tg_id}`)\n"
                f"План: {plan['emoji']} {plan['name']} — {plan['days']} дн.\n"
                f"Сумма: {stars} ⭐"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление об оплате: {e}")

    if plan_key == "basic":
        # Даём выбрать 2 системных модуля
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 Автоответчик", callback_data="sub_choose_sys_autoreply_basic")],
            [InlineKeyboardButton("🕐 Ник по времени", callback_data="sub_choose_sys_timenick_basic")],
        ])
        await update.message.reply_text(
            f"✅ Оплата прошла! {plan['emoji']} {plan['name']} активирована на {plan['days']} дней.\n"

            f"Выбери до 2 системных модулей (нажимай по одному):",
            reply_markup=kb
        )
    else:
        await update.message.reply_text(
            f"✅ Оплата прошла! {plan['emoji']} {plan['name']} активирована на {plan['days']} дней.\n"

            f"Все модули и системные функции доступны.",
            reply_markup=get_user_kb()
        )


# ═══════════════════════════════════════════════════════════════════
# 🚀 ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════════════

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
            "UNPARSER":              [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, unparser_password_handler)],
            "WAIT_MIRROR_TOKEN":     [CallbackQueryHandler(menu_router, pattern="^back_main$|^u_partner$"), MessageHandler(filters.TEXT & ~filters.COMMAND, wait_mirror_token)],
            "WAIT_TIMENICK":         [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, wait_timenick)],
            "SONYA_CHAT":            [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, sonya_chat)],
            "WAIT_PROMO_ACTIVATE":   [CallbackQueryHandler(menu_router), MessageHandler(filters.TEXT & ~filters.COMMAND, promo_activate)],
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
        per_message=False,
        per_chat=True,
        per_user=True,
        allow_reentry=True,
        conversation_timeout=600
    )

    async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Необработанное исключение: {context.error}", exc_info=context.error)
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ Произошла внутренняя ошибка. Попробуйте /start",
                    reply_markup=get_guest_kb()
                )
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
