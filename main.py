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

BASE_DIR   = "/app"
DATA_DIR   = os.path.join(BASE_DIR, "data")
MODULES_DIR= os.path.join(BASE_DIR, "modules")
IMAGES_DIR = os.path.join(BASE_DIR, "images")
LOG_FILE   = os.path.join(BASE_DIR, "bot.log")

USERS_FILE = os.path.join(DATA_DIR, "users.json")
SUBS_FILE  = os.path.join(DATA_DIR, "subscriptions.json")
PROMO_FILE = os.path.join(DATA_DIR, "promocodes.json")

PHOTO_AUTH     = os.path.join(IMAGES_DIR, "auth.jpg")
PHOTO_MODULES  = os.path.join(IMAGES_DIR, "modules.jpg")
PHOTO_SONYA_SAD= os.path.join(IMAGES_DIR, "sonya_sad.jpg")

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

# Глобальные кэши в памяти
USER_BOTS: dict       = {}   # {tg_id: TelegramClient}
LOADED_MODULES: dict  = {}   # {tg_id: [module_name, ...]}


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
    if not os.path.exists(USERS_FILE):
        save_json(USERS_FILE, {})
    if not os.path.exists(SUBS_FILE):
        save_json(SUBS_FILE, {})
    if not os.path.exists(PROMO_FILE):
        save_json(PROMO_FILE, {
            "URETRACOIN": {"tier": 3, "days": 90, "max_uses": 100, "used_by": []}
        })

def is_user_authorized(tg_id: str) -> bool:
    users = load_json(USERS_FILE)
    session_file = os.path.join(DATA_DIR, f"session_{tg_id}.session")
    return (
        tg_id in users
        and users[tg_id].get("authenticated", False)
        and os.path.exists(session_file)
    )


# ═══════════════════════════════════════════════════════════════════
# ⚡️ БЛОК ДВИЖКА TELETHON (ЯДРО ЮЗЕРБОТОВ)
# ═══════════════════════════════════════════════════════════════════

def load_user_modules(client: TelegramClient, tg_id: str):
    """Динамический импорт .py плагинов через importlib."""
    user_dir = os.path.join(MODULES_DIR, f"user_{tg_id}")
    if not os.path.exists(user_dir):
        return

    LOADED_MODULES.setdefault(tg_id, [])

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
            logger.info(f"Модуль {file} загружен для юзера {tg_id}")
        except Exception as e:
            logger.error(f"Ошибка загрузки модуля {file} для {tg_id}: {e}")

async def start_user_bot(tg_id: str, api_id: int, api_hash: str):
    """Коннект клиента, авторизация и запуск модулей."""
    if tg_id in USER_BOTS:
        try:
            await USER_BOTS[tg_id].disconnect()
        except Exception:
            pass

    session_path = os.path.join(DATA_DIR, f"session_{tg_id}")
    client = TelegramClient(session_path, api_id, api_hash)

    load_user_modules(client, tg_id)

    await client.connect()
    if await client.is_user_authorized():
        USER_BOTS[tg_id] = client
        logger.info(f"Юзербот для {tg_id} запущен.")
    else:
        logger.warning(f"Сессия {tg_id} найдена, но авторизация не пройдена.")

async def auto_run_existing_bots():
    """Автоподнятие всех активных сессий при рестарте сервера."""
    users = load_json(USERS_FILE)
    for tg_id, info in users.items():
        session_file = os.path.join(DATA_DIR, f"session_{tg_id}.session")
        if info.get("authenticated") and os.path.exists(session_file):
            try:
                asyncio.create_task(
                    start_user_bot(tg_id, int(info["api_id"]), info["api_hash"])
                )
                logger.info(f"Автозапуск юзербота {tg_id}")
            except Exception as e:
                logger.error(f"Не удалось поднять юзербота {tg_id}: {e}")


# ═══════════════════════════════════════════════════════════════════
# 🎛 БЛОК UI: КЛАВИАТУРЫ И МЕНЮ
# ═══════════════════════════════════════════════════════════════════

def get_guest_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Создать Юзербота (Вход)", callback_data="g_reg")],
        [InlineKeyboardButton("👑 Админ-Панель", callback_data="g_admin")]
    ])

def get_user_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Профиль",     callback_data="u_profile"),
         InlineKeyboardButton("💎 Подписка",    callback_data="u_sub")],
        [InlineKeyboardButton("⚙️ Модули",      callback_data="u_modules"),
         InlineKeyboardButton("🤖 Соня (ИИ)",  callback_data="u_sonya")],
        [InlineKeyboardButton("❌ Выйти (сбросить сессию)", callback_data="u_logout")]
    ])

def get_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отмена", callback_data="back_main")]
    ])

def get_pinpad_kb(entered: str = "") -> InlineKeyboardMarkup:
    """
    Генератор виртуального пин-пада (калькулятор) для безопасного ввода кода.
    Показывает маскированный прогресс ввода в виде первой строки.
    """
    display = "🔢 " + ("•" * len(entered) if entered else "_ _ _ _ _")
    rows = [
        [InlineKeyboardButton(display, callback_data="pin_noop")]
    ]
    digits = [["1","2","3"],["4","5","6"],["7","8","9"]]
    for row in digits:
        rows.append([
            InlineKeyboardButton(d, callback_data=f"pin_digit_{d}") for d in row
        ])
    rows.append([
        InlineKeyboardButton("⌫ Стереть",  callback_data="pin_back"),
        InlineKeyboardButton("0",           callback_data="pin_digit_0"),
        InlineKeyboardButton("✅ Отправить",callback_data="pin_submit")
    ])
    return InlineKeyboardMarkup(rows)

async def send_menu_photo(
    update_or_query,
    photo_path: str,
    caption_text: str,
    reply_markup: InlineKeyboardMarkup
):
    msg = (
        update_or_query.message
        if isinstance(update_or_query, Update)
        else update_or_query.message
    )
    if os.path.exists(photo_path):
        try:
            with open(photo_path, "rb") as photo:
                await msg.reply_photo(
                    photo=photo,
                    caption=caption_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                return
        except Exception as e:
            logger.error(f"Ошибка отправки медиа {photo_path}: {e}")
    await msg.reply_text(caption_text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


# ═══════════════════════════════════════════════════════════════════
# 🚦 БЛОК РОУТИНГА И СОСТОЯНИЙ
# ═══════════════════════════════════════════════════════════════════

# ─── Entry Point ───────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка сессии — выдача гостевого или юзер-меню."""
    tg_id = str(update.effective_user.id)
    context.user_data.clear()

    async with _file_lock:
        is_auth = is_user_authorized(tg_id)
        users   = load_json(USERS_FILE)

    if is_auth:
        if tg_id not in USER_BOTS:
            u_info = users[tg_id]
            asyncio.create_task(
                start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"])
            )
        nick = users[tg_id].get("nick", "Пользователь")
        await update.message.reply_text(
            f"🏠 *Главное меню*\n\nДобро пожаловать, *{nick}*!\n"
            f"Ваш юзербот {'🟢 активен' if tg_id in USER_BOTS else '🔴 запускается...'}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_user_kb()
        )
    else:
        await update.message.reply_text(
            "👋 *UserBot Manager*\n\nАктивных сессий не найдено.\n"
            "Нажмите кнопку ниже для настройки.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_guest_kb()
        )
    return "MENU"


# ─── MENU: Обработка кликов главного меню ─────────────────────────

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query  = update.callback_query
    tg_id  = str(query.from_user.id)
    data   = query.data
    await query.answer()

    async with _file_lock:
        is_auth = is_user_authorized(tg_id)
        users   = load_json(USERS_FILE)

    # ── Назад в главное меню ──
    if data == "back_main":
        context.user_data.clear()
        if is_auth:
            nick = users[tg_id].get("nick", "Пользователь")
            await query.message.reply_text(
                f"🏠 *Главное меню*, *{nick}*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_user_kb()
            )
        else:
            await query.message.reply_text(
                "🏠 *Меню гостя*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_guest_kb()
            )
        return "MENU"

    # ── Гостевые кнопки ──
    if data == "g_reg":
        if is_auth:
            await query.message.reply_text("⚠️ Сессия уже создана!", reply_markup=get_user_kb())
            return "MENU"
        await query.message.reply_text(
            "📝 *Шаг 1 из 4*\n\nВведите ваш локальный никнейм:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_kb()
        )
        return "REG_NICK"

    if data == "g_admin":
        await query.message.reply_text(
            "👑 Введите пароль администратора:",
            reply_markup=get_cancel_kb()
        )
        return "ADMIN_LOGIN"

    # ── Защита: только для авторизованных ──
    if not is_auth:
        await query.message.reply_text("⚠️ Сессия отсутствует.", reply_markup=get_guest_kb())
        return "MENU"

    # ── Юзер-кнопки ──
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
            try:
                os.remove(session_file)
            except Exception:
                pass

        await query.message.reply_text(
            "❌ Сессия сброшена. Юзербот отключён.",
            reply_markup=get_guest_kb()
        )
        return "MENU"

    if data == "u_profile":
        u = users[tg_id]
        mods = LOADED_MODULES.get(tg_id, [])
        status = "🟢 Запущен" if tg_id in USER_BOTS else "🔴 Остановлен"
        txt = (
            f"👤 *Ваш профиль*\n\n"
            f"🆔 ID: `{tg_id}`\n"
            f"🏷 Ник: `{u.get('nick', '—')}`\n"
            f"📱 Телефон: `{u.get('phone', '—')}`\n"
            f"⚡️ Движок: *Telethon*\n"
            f"📊 Статус: *{status}*\n"
            f"🧩 Модули: *{len(mods)}* загружено"
        )
        await query.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=get_cancel_kb())
        return "MENU"

    if data == "u_sub":
        async with _file_lock:
            subs = load_json(SUBS_FILE)
        tier = subs.get(tg_id, {}).get("tier", 1)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎟 Активировать промокод", callback_data="u_activate_promo")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]
        ])
        await query.message.reply_text(
            f"💎 *Управление подпиской*\n\nТекущий уровень: *Тир {tier}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb
        )
        return "MENU"

    if data == "u_activate_promo":
        await query.message.reply_text(
            "🎟 Отправьте промокод в чат:",
            reply_markup=get_cancel_kb()
        )
        return "WAIT_PROMO_ACTIVATE"

    if data == "u_sonya":
        await send_menu_photo(
            query, PHOTO_SONYA_SAD,
            "🤖 *Соня (ИИ-ассистент)*\n\n«Соня сейчас отдыхает, напишите позже!»",
            get_cancel_kb()
        )
        return "SONYA_CHAT"

    if data == "u_modules":
        m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
        async with _file_lock:
            m_data = load_json(m_file)
        used = len(m_data.get("modules", []))
        mods_list = m_data.get("modules", [])
        txt = f"⚙️ *Управление модулями*\n\n📊 Слотов занято: `{used}/5`\n"
        if mods_list:
            txt += "\n".join(f"  • `{m['name']}.py`" for m in mods_list)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Установить модуль", callback_data="mod_install")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]
        ])
        await send_menu_photo(query, PHOTO_MODULES, txt, kb)
        return "MENU"

    if data == "mod_install":
        await query.message.reply_text(
            "🔗 Отправьте *прямую ссылку* на `.py` плагин "
            "или **прикрепите файл документом**:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_kb()
        )
        return "MODULE_INSTALL"

    return "MENU"


# ─── REG_NICK: Ввод локального имени юзера ────────────────────────

async def reg_nick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg_nick"] = update.message.text.strip()
    await send_menu_photo(
        update, PHOTO_AUTH,
        "📱 *Шаг 2 из 4*\n\nВведите номер телефона в формате `+79XXXXXXXXX`:",
        get_cancel_kb()
    )
    return "LOGIN_PHONE"


# ─── LOGIN_PHONE: Ввод номера телефона ────────────────────────────

async def login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        await update.message.reply_text(
            "⚠️ Неверный формат. Пример: `+79001234567`\n\nПовторите ввод:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_kb()
        )
        return "LOGIN_PHONE"
    context.user_data["phone"] = phone
    await update.message.reply_text(
        "🔑 *Шаг 3 из 4*\n\nВведите ваш **API ID** (только цифры):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_kb()
    )
    return "LOGIN_API_ID"


# ─── LOGIN_API_ID: Ввод API ID ────────────────────────────────────

async def login_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    if not val.isdigit():
        await update.message.reply_text(
            "⚠️ API ID — только цифры. Повторите ввод:",
            reply_markup=get_cancel_kb()
        )
        return "LOGIN_API_ID"
    context.user_data["api_id"] = int(val)
    await update.message.reply_text(
        "🔑 *Шаг 4 из 4*\n\nВведите ваш **API HASH**:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_kb()
    )
    return "LOGIN_API_HASH"


# ─── LOGIN_API_HASH: Инициализация Telethon, отправка СМС ─────────

async def login_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id    = str(update.effective_user.id)
    api_hash = update.message.text.strip()
    phone    = context.user_data["phone"]
    api_id   = context.user_data["api_id"]
    context.user_data["api_hash"] = api_hash

    await update.message.reply_text("⏳ Инициализация сессии Telethon...")

    session_path = os.path.join(DATA_DIR, f"session_{tg_id}")
    client = TelegramClient(session_path, api_id, api_hash)

    try:
        await client.connect()
        sent_code = await client.send_code_request(phone)
        context.user_data["client"]          = client
        context.user_data["phone_code_hash"] = sent_code.phone_code_hash

        # Показываем пин-пад с пустым вводом
        context.user_data["pin_entered"] = ""
        await update.message.reply_text(
            "📩 Код отправлен в приложение Telegram.\n\n"
            "Введите код через пин-пад ниже:",
            reply_markup=get_pinpad_kb("")
        )
        return "WAIT_CODE"

    except Exception as e:
        logger.error(f"Telethon send_code error для {tg_id}: {e}")
        try:
            await client.disconnect()
        except Exception:
            pass
        await update.message.reply_text(
            f"❌ Ошибка API Telegram: `{e}`\n\nПопробуйте снова — /start",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_guest_kb()
        )
        return "MENU"


# ─── WAIT_CODE: Защищённый ввод кода через пин-пад ───────────────

async def pinpad_click_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок пин-пада."""
    query  = update.callback_query
    tg_id  = str(query.from_user.id)
    data   = query.data
    await query.answer()

    entered = context.user_data.get("pin_entered", "")

    if data == "pin_noop":
        return "WAIT_CODE"

    if data.startswith("pin_digit_"):
        digit = data.split("_")[-1]
        if len(entered) < 10:
            entered += digit
        context.user_data["pin_entered"] = entered
        try:
            await query.edit_message_reply_markup(reply_markup=get_pinpad_kb(entered))
        except Exception:
            pass
        return "WAIT_CODE"

    if data == "pin_back":
        entered = entered[:-1]
        context.user_data["pin_entered"] = entered
        try:
            await query.edit_message_reply_markup(reply_markup=get_pinpad_kb(entered))
        except Exception:
            pass
        return "WAIT_CODE"

    if data == "pin_submit":
        if not entered:
            await query.answer("⚠️ Введите код!", show_alert=True)
            return "WAIT_CODE"
        return await _do_sign_in(update, context, tg_id, entered)

    return "WAIT_CODE"

async def _cleanup_failed_session(tg_id: str, client):
    """Чистит битую сессию с диска и из памяти."""
    try:
        await client.disconnect()
    except Exception:
        pass
    # Удаляем файлы сессии чтобы повторная регистрация не давала "сессия уже создана"
    for ext in (".session", ".session-journal"):
        path = os.path.join(DATA_DIR, f"session_{tg_id}{ext}")
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
    if tg_id in USER_BOTS:
        del USER_BOTS[tg_id]

async def _finish_auth(update, context, tg_id: str, client):
    """Сохраняет юзера и запускает юзербота после успешной авторизации."""
    phone = context.user_data.get("phone")
    async with _file_lock:
        users = load_json(USERS_FILE)
        users[tg_id] = {
            "nick":          context.user_data.get("reg_nick", f"User_{tg_id[:4]}"),
            "phone":         phone,
            "api_id":        context.user_data["api_id"],
            "api_hash":      context.user_data["api_hash"],
            "authenticated": True,
            "created_at":    datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        save_json(USERS_FILE, users)

    USER_BOTS[tg_id] = client
    load_user_modules(client, tg_id)

    msg = update.callback_query.message if update.callback_query else update.message
    await msg.reply_text(
        "🎉 *Успешно!* Юзербот запущен в облаке.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_user_kb()
    )
    return "MENU"

async def _do_sign_in(update, context, tg_id: str, code: str):
    """Финальная авторизация через Telethon после ввода кода с пин-пада."""
    query           = update.callback_query
    client          = context.user_data.get("client")
    phone_code_hash = context.user_data.get("phone_code_hash")
    phone           = context.user_data.get("phone")

    try:
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        # Авторизация прошла без 2FA
        return await _finish_auth(update, context, tg_id, client)

    except SessionPasswordNeededError:
        # У юзера включена двухфакторная аутентификация — запрашиваем пароль
        logger.info(f"2FA требуется для {tg_id}")
        context.user_data["awaiting_2fa"] = True
        await query.message.reply_text(
            "🔐 *Двухфакторная аутентификация*\n\n"
            "На вашем аккаунте включена 2FA.\n"
            "Введите облачный пароль Telegram:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_cancel_kb()
        )
        return "WAIT_2FA"

    except Exception as e:
        logger.error(f"sign_in error для {tg_id}: {e}")
        await _cleanup_failed_session(tg_id, client)
        await query.message.reply_text(
            f"❌ Ошибка входа: `{e}`\n\nПопробуйте снова — /start",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_guest_kb()
        )
        return "MENU"


# ─── WAIT_2FA: Ввод облачного пароля 2FA ──────────────────────────

async def wait_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимает облачный пароль и завершает авторизацию."""
    tg_id    = str(update.effective_user.id)
    password = update.message.text.strip()
    client   = context.user_data.get("client")

    try:
        await client.sign_in(password=password)
        return await _finish_auth(update, context, tg_id, client)

    except Exception as e:
        logger.error(f"2FA error для {tg_id}: {e}")
        await _cleanup_failed_session(tg_id, client)
        await update.message.reply_text(
            f"❌ Неверный пароль 2FA: `{e}`\n\nПопробуйте снова — /start",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_guest_kb()
        )
        return "MENU"


# ─── MODULE_INSTALL: Приём .py файла или ссылки ───────────────────

async def module_download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id     = str(update.effective_user.id)
    code_text = ""
    mod_name  = f"module_{random.randint(1000, 9999)}"

    # Файл документом
    if update.message.document:
        doc = update.message.document
        if not doc.file_name.endswith(".py"):
            await update.message.reply_text(
                "❌ Принимаются только `.py` файлы.",
                reply_markup=get_cancel_kb()
            )
            return "MODULE_INSTALL"
        mod_name = doc.file_name[:-3]
        tg_file  = await context.bot.get_file(doc.file_id)
        raw      = await tg_file.download_as_bytearray()
        code_text = raw.decode("utf-8", errors="ignore")

    # Прямая ссылка на .py
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
                            await update.message.reply_text(
                                f"❌ Ошибка загрузки: HTTP {resp.status}",
                                reply_markup=get_cancel_kb()
                            )
                            return "MODULE_INSTALL"
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Не удалось скачать файл: `{e}`",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_cancel_kb()
                )
                return "MODULE_INSTALL"
        else:
            await update.message.reply_text(
                "❌ Отправьте прямую ссылку на `.py` файл или прикрепите файл документом.",
                reply_markup=get_cancel_kb()
            )
            return "MODULE_INSTALL"

    if not code_text:
        await update.message.reply_text("❌ Файл пуст.", reply_markup=get_user_kb())
        return "MENU"

    # Проверка лимита слотов
    m_file = os.path.join(DATA_DIR, f"user_modules_{tg_id}.json")
    async with _file_lock:
        m_data = load_json(m_file)
    if len(m_data.get("modules", [])) >= 5:
        await update.message.reply_text(
            "⚠️ Достигнут лимит модулей (5/5). Удалите один для установки нового.",
            reply_markup=get_user_kb()
        )
        return "MENU"

    # Сохраняем файл модуля
    user_dir = os.path.join(MODULES_DIR, f"user_{tg_id}")
    os.makedirs(user_dir, exist_ok=True)
    module_path = os.path.join(user_dir, f"{mod_name}.py")
    with open(module_path, "w", encoding="utf-8") as f:
        f.write(code_text)

    # Обновляем реестр модулей
    async with _file_lock:
        m_data.setdefault("modules", [])
        m_data["modules"].append({
            "name": mod_name,
            "date": datetime.now().strftime("%d.%m.%Y")
        })
        save_json(m_file, m_data)

    # Перезапуск юзербота если онлайн
    if tg_id in USER_BOTS:
        async with _file_lock:
            users = load_json(USERS_FILE)
        u_info = users.get(tg_id, {})
        await start_user_bot(tg_id, int(u_info["api_id"]), u_info["api_hash"])
        await update.message.reply_text(
            f"✅ Модуль *{mod_name}.py* установлен и загружен в юзербот!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_user_kb()
        )
    else:
        await update.message.reply_text(
            f"✅ Модуль *{mod_name}.py* сохранён. Запустите юзербота для активации.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_user_kb()
        )
    return "MENU"


# ─── SONYA_CHAT: Заглушка чата с ИИ Соней ────────────────────────

async def sonya_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Соня сейчас не на связи. Попробуйте позже.",
        reply_markup=get_cancel_kb()
    )
    return "SONYA_CHAT"


# ─── WAIT_PROMO_ACTIVATE: Ввод и валидация купонов ────────────────

async def promo_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    code  = update.message.text.strip().upper()

    async with _file_lock:
        promos = load_json(PROMO_FILE)
        subs   = load_json(SUBS_FILE)

    if code not in promos:
        await update.message.reply_text(
            "❌ Промокод не найден. Проверьте правильность ввода.",
            reply_markup=get_cancel_kb()
        )
        return "WAIT_PROMO_ACTIVATE"

    promo = promos[code]

    if tg_id in promo.get("used_by", []):
        await update.message.reply_text(
            "⚠️ Вы уже использовали этот промокод.",
            reply_markup=get_user_kb()
        )
        return "MENU"

    if len(promo.get("used_by", [])) >= promo.get("max_uses", 1):
        await update.message.reply_text(
            "⚠️ Промокод исчерпан.",
            reply_markup=get_user_kb()
        )
        return "MENU"

    # Применяем промокод
    async with _file_lock:
        promos[code]["used_by"].append(tg_id)
        save_json(PROMO_FILE, promos)

        subs.setdefault(tg_id, {})
        subs[tg_id]["tier"] = promo["tier"]
        save_json(SUBS_FILE, subs)

    await update.message.reply_text(
        f"✅ Промокод активирован!\n\n💎 Ваш новый тир: *{promo['tier']}*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_user_kb()
    )
    return "MENU"


# ─── ADMIN_LOGIN: Проверка пароля ─────────────────────────────────

async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() != ADMIN_PASSWORD:
        await update.message.reply_text("❌ Доступ отклонён.", reply_markup=get_guest_kb())
        return "MENU"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Пользователи", callback_data="a_users"),
         InlineKeyboardButton("🎫 Промокоды",    callback_data="a_promos")],
        [InlineKeyboardButton("🚪 Выйти из админки", callback_data="back_main")]
    ])
    await update.message.reply_text(
        "👑 *Панель администратора*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb
    )
    return "ADMIN_MENU"


# ─── ADMIN_MENU: Управление пользователями и промокодами ──────────

async def admin_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    await query.answer()

    def admin_kb():
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Пользователи", callback_data="a_users"),
             InlineKeyboardButton("🎫 Промокоды",    callback_data="a_promos")],
            [InlineKeyboardButton("🚪 Выйти из админки", callback_data="back_main")]
        ])

    if data == "back_admin":
        await query.message.reply_text(
            "👑 *Панель администратора*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=admin_kb()
        )
        return "ADMIN_MENU"

    if data == "a_users":
        async with _file_lock:
            users = load_json(USERS_FILE)
        txt = "👥 *Пользователи:*\n\n"
        if not users:
            txt += "База данных пользователей пуста."
        else:
            for u_id, v in users.items():
                status = "🟢" if u_id in USER_BOTS else "🔴"
                mods   = len(LOADED_MODULES.get(u_id, []))
                txt   += (
                    f"{status} *{v.get('nick','—')}* | "
                    f"`{v.get('phone','—')}` | "
                    f"ID: `{u_id}` | Модули: {mods}\n"
                )
        await query.message.reply_text(
            txt,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="back_admin")]
            ])
        )
        return "ADMIN_MENU"

    if data == "a_promos":
        async with _file_lock:
            promos = load_json(PROMO_FILE)
        txt = "🎫 *Промокоды:*\n\n"
        for k, v in promos.items():
            used = len(v.get("used_by", []))
            txt += (
                f"• `{k}` — Тир *{v['tier']}* | "
                f"Использован: {used}/{v.get('max_uses','∞')}\n"
            )
        await query.message.reply_text(
            txt,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="back_admin")]
            ])
        )
        return "ADMIN_MENU"

    # Если кликнули "Выйти из админки" — роутим в main menu_router
    return "MENU"


# ═══════════════════════════════════════════════════════════════════
# 🚀 ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════════════

def main():
    init_system()

    # Автоподнятие сессий
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(auto_run_existing_bots())

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            "MENU": [
                CallbackQueryHandler(menu_router)
            ],
            "REG_NICK": [
                CallbackQueryHandler(menu_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, reg_nick)
            ],
            "LOGIN_PHONE": [
                CallbackQueryHandler(menu_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_phone)
            ],
            "LOGIN_API_ID": [
                CallbackQueryHandler(menu_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_api_id)
            ],
            "LOGIN_API_HASH": [
                CallbackQueryHandler(menu_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_api_hash)
            ],
            "WAIT_CODE": [
                # Пин-пад — только callback кнопки
                CallbackQueryHandler(pinpad_click_handler, pattern="^pin_"),
                CallbackQueryHandler(menu_router, pattern="^back_main$")
            ],
            "WAIT_2FA": [
                CallbackQueryHandler(menu_router, pattern="^back_main$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, wait_2fa)
            ],
            "MODULE_INSTALL": [
                CallbackQueryHandler(menu_router),
                MessageHandler(
                    (filters.Document.ALL | filters.TEXT) & ~filters.COMMAND,
                    module_download_handler
                )
            ],
            "SONYA_CHAT": [
                CallbackQueryHandler(menu_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, sonya_chat)
            ],
            "WAIT_PROMO_ACTIVATE": [
                CallbackQueryHandler(menu_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, promo_activate)
            ],
            "ADMIN_LOGIN": [
                CallbackQueryHandler(menu_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_login)
            ],
            "ADMIN_MENU": [
                CallbackQueryHandler(admin_router)
            ],
        },
        fallbacks=[
            CommandHandler("start", cmd_start),
            CallbackQueryHandler(menu_router)
        ],
        per_message=False,
        allow_reentry=True
    )

    app.add_handler(conv)
    logger.info("✅ UserBot Manager запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
