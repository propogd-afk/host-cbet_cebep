"""
Регистрация UserBot через Telethon.
Код вводится через инлайн-кнопки — Telegram не банит.
"""

import os
import json
import logging
import asyncio
import threading
import fcntl
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler,
    MessageHandler, Filters, CallbackContext,
)
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError,
    FloodWaitError,
)

# ─────────────────────────────────────────────
# КОНФИГУРАЦИЯ
# ─────────────────────────────────────────────
BOT_TOKEN   = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS   = set(os.environ.get("ADMIN_IDS", "1837883882").split(","))

BASE_DIR      = "/app"
DATA_DIR      = os.path.join(BASE_DIR, "data")
SESSIONS_DIR  = os.path.join(DATA_DIR, "sessions")   # Telethon .session файлы
USERS_FILE    = os.path.join(DATA_DIR, "users.json")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан!")

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# JSON
# ─────────────────────────────────────────────
def load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            d = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
            return d
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_json(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush(); os.fsync(f.fileno())
        fcntl.flock(f, fcntl.LOCK_UN)
    os.replace(tmp, path)


# ─────────────────────────────────────────────
# ASYNCIO в отдельном потоке
# (python-telegram-bot 13.x синхронный, Telethon асинхронный)
# ─────────────────────────────────────────────
_loop = asyncio.new_event_loop()

def _start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=_start_loop, args=(_loop,), daemon=True).start()

def run_async(coro):
    """Запускаем корутину из синхронного кода и ждём результата."""
    fut = asyncio.run_coroutine_threadsafe(coro, _loop)
    return fut.result(timeout=60)


# ─────────────────────────────────────────────
# КЛАВИАТУРА: цифровая панель для ввода кода
# ─────────────────────────────────────────────
def kb_code_pad(entered: str, total: int = 5) -> InlineKeyboardMarkup:
    """
    Цифровая клавиатура. entered — уже введённые цифры.
    Отображаем прогресс: ● ● ○ ○ ○
    """
    dots = "●" * len(entered) + "○" * (total - len(entered))
    rows = [
        # Прогресс (не кнопка)
        [InlineKeyboardButton(f"Код: {dots}", callback_data="noop")],
        # Цифры
        [
            InlineKeyboardButton("1", callback_data="code_1"),
            InlineKeyboardButton("2", callback_data="code_2"),
            InlineKeyboardButton("3", callback_data="code_3"),
        ],
        [
            InlineKeyboardButton("4", callback_data="code_4"),
            InlineKeyboardButton("5", callback_data="code_5"),
            InlineKeyboardButton("6", callback_data="code_6"),
        ],
        [
            InlineKeyboardButton("7", callback_data="code_7"),
            InlineKeyboardButton("8", callback_data="code_8"),
            InlineKeyboardButton("9", callback_data="code_9"),
        ],
        [
            InlineKeyboardButton("⌫ Стереть", callback_data="code_del"),
            InlineKeyboardButton("0", callback_data="code_0"),
            InlineKeyboardButton("✅ ОК",      callback_data="code_ok"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def kb_2fa_pad(entered: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для 2FA пароля — символы скрыты (звёздочки).
    Добавляем цифры + кнопку «ввести буквы» через сообщение.
    """
    hidden = "●" * len(entered)
    rows = [
        [InlineKeyboardButton(f"Пароль: {hidden or '○○○○○'}", callback_data="noop")],
        [
            InlineKeyboardButton("1", callback_data="2fa_1"),
            InlineKeyboardButton("2", callback_data="2fa_2"),
            InlineKeyboardButton("3", callback_data="2fa_3"),
        ],
        [
            InlineKeyboardButton("4", callback_data="2fa_4"),
            InlineKeyboardButton("5", callback_data="2fa_5"),
            InlineKeyboardButton("6", callback_data="2fa_6"),
        ],
        [
            InlineKeyboardButton("7", callback_data="2fa_7"),
            InlineKeyboardButton("8", callback_data="2fa_8"),
            InlineKeyboardButton("9", callback_data="2fa_9"),
        ],
        [
            InlineKeyboardButton("⌫ Стереть",       callback_data="2fa_del"),
            InlineKeyboardButton("0",                callback_data="2fa_0"),
            InlineKeyboardButton("✅ Войти",          callback_data="2fa_ok"),
        ],
        # Если пароль содержит буквы — пусть напишет текстом
        [InlineKeyboardButton("⌨️ Ввести текстом", callback_data="2fa_text")],
    ]
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────
# ИНИЦИАЛИЗАЦИЯ
# ─────────────────────────────────────────────
def init_system():
    for d in (DATA_DIR, SESSIONS_DIR):
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        save_json(USERS_FILE, {})


# ─────────────────────────────────────────────
# TELETHON: создать клиент для пользователя
# ─────────────────────────────────────────────
def make_client(tg_id: int, api_id: int, api_hash: str) -> TelegramClient:
    session_path = os.path.join(SESSIONS_DIR, str(tg_id))
    return TelegramClient(session_path, api_id, api_hash, loop=_loop)


# ─────────────────────────────────────────────
# ХЕНДЛЕРЫ КОМАНД
# ─────────────────────────────────────────────
def cmd_start(update: Update, context: CallbackContext):
    context.user_data.clear()
    tg_id = str(update.effective_user.id)
    users = load_json(USERS_FILE)

    if tg_id in users:
        nick = users[tg_id].get("nick", "пользователь")
        update.message.reply_text(
            f"🏠 Привет, *{nick}*! Главное меню:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Модули",  callback_data="menu_modules")],
                [InlineKeyboardButton("👤 Профиль", callback_data="menu_profile")],
            ])
        )
    else:
        update.message.reply_text(
            "👋 *UserBot Hosting*\n\nДля начала нужно привязать ваш Telegram-аккаунт.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Привязать аккаунт", callback_data="reg_start")],
            ])
        )


# ─────────────────────────────────────────────
# РОУТЕР CALLBACK-КНОПОК
# ─────────────────────────────────────────────
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    data  = query.data or ""
    tg_id = query.from_user.id

    try:
        query.answer()
    except Exception:
        pass

    # ── Старт регистрации ────────────────────────────────────────
    if data == "reg_start":
        context.user_data.clear()
        context.user_data["state"] = "REG_PHONE"
        query.edit_message_text(
            "📱 *Шаг 1 из 3: Номер телефона*\n\n"
            "Введите ваш номер в формате:\n`+79001234567`\n\n"
            "Просто напишите его в чат:",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── Ввод кода через кнопки ───────────────────────────────────
    elif data.startswith("code_"):
        _handle_code_input(update, context, data)

    # ── Ввод 2FA через кнопки ────────────────────────────────────
    elif data.startswith("2fa_"):
        _handle_2fa_input(update, context, data)

    # ── Меню ─────────────────────────────────────────────────────
    elif data == "menu_modules":
        query.edit_message_text("⚙️ Раздел модулей (в разработке).")

    elif data == "menu_profile":
        _show_profile(update, context)

    elif data == "noop":
        pass  # индикаторные кнопки

    else:
        query.answer("Неизвестная команда.", show_alert=True)


# ─────────────────────────────────────────────
# ОБРАБОТКА ВВОДА КОДА (инлайн-клавиатура)
# ─────────────────────────────────────────────
def _handle_code_input(update: Update, context: CallbackContext, data: str):
    query = update.callback_query
    entered: str = context.user_data.get("code_entered", "")

    action = data[5:]  # "1".."0", "del", "ok"

    if action == "del":
        entered = entered[:-1]
    elif action == "ok":
        if len(entered) < 5:
            query.answer("Введите все 5 цифр!", show_alert=True)
            return
        _submit_code(update, context, entered)
        return
    elif action.isdigit() and len(entered) < 5:
        entered += action

    context.user_data["code_entered"] = entered

    query.edit_message_text(
        "🔑 *Шаг 2 из 3: Код подтверждения*\n\n"
        "Telegram отправил вам код.\nВведите его цифра за цифрой:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_code_pad(entered),
    )


def _submit_code(update: Update, context: CallbackContext, code: str):
    """Отправляем код в Telethon."""
    query  = update.callback_query
    tg_id  = query.from_user.id
    phone  = context.user_data.get("phone", "")
    api_id = context.user_data.get("api_id")
    api_hash = context.user_data.get("api_hash")

    if not all([phone, api_id, api_hash]):
        query.edit_message_text("❌ Сессия устарела. Начните заново: /start")
        return

    query.edit_message_text("⏳ Проверяем код...")

    try:
        client = make_client(tg_id, int(api_id), api_hash)
        phone_code_hash = context.user_data.get("phone_code_hash", "")

        async def do_sign_in():
            await client.connect()
            return await client.sign_in(phone, code, phone_code_hash=phone_code_hash)

        run_async(do_sign_in())

        # Успех — сохраняем пользователя
        _save_user(tg_id, context)
        query.message.reply_text(
            "✅ *Аккаунт успешно привязан!*\n\nТеперь вы можете пользоваться модулями.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Главное меню", callback_data="noop")],
            ])
        )

    except SessionPasswordNeededError:
        # Включена 2FA
        context.user_data["state"]        = "WAIT_2FA"
        context.user_data["2fa_entered"]  = ""
        context.user_data["tg_client_id"] = tg_id
        query.message.reply_text(
            "🔐 *Шаг 3 из 3: Двухэтапная проверка*\n\n"
            "На вашем аккаунте включён пароль 2FA.\nВведите его:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_2fa_pad(""),
        )

    except PhoneCodeInvalidError:
        context.user_data["code_entered"] = ""
        query.message.reply_text(
            "❌ *Неверный код.* Попробуйте ещё раз:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_code_pad(""),
        )

    except PhoneCodeExpiredError:
        query.message.reply_text(
            "❌ Код истёк. Начните регистрацию заново: /start"
        )

    except FloodWaitError as e:
        query.message.reply_text(
            f"⏳ Слишком много попыток. Подождите {e.seconds} секунд."
        )

    except Exception as e:
        logger.error("Ошибка sign_in: %s", e)
        query.message.reply_text(f"❌ Ошибка: {e}\n\nПопробуйте /start")


# ─────────────────────────────────────────────
# ОБРАБОТКА 2FA (инлайн-клавиатура)
# ─────────────────────────────────────────────
def _handle_2fa_input(update: Update, context: CallbackContext, data: str):
    query   = update.callback_query
    entered = context.user_data.get("2fa_entered", "")
    action  = data[4:]  # "1".."0", "del", "ok", "text"

    if action == "text":
        context.user_data["state"] = "WAIT_2FA_TEXT"
        query.edit_message_text(
            "⌨️ Введите пароль 2FA текстом в чат:\n_(он не будет виден другим)_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    elif action == "del":
        entered = entered[:-1]

    elif action == "ok":
        if not entered:
            query.answer("Введите пароль!", show_alert=True)
            return
        _submit_2fa(update, context, entered)
        return

    elif action.isdigit():
        entered += action

    context.user_data["2fa_entered"] = entered
    query.edit_message_text(
        "🔐 *Двухэтапная проверка*\n\nВведите пароль 2FA:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb_2fa_pad(entered),
    )


def _submit_2fa(update: Update, context: CallbackContext, password: str):
    """Отправляем 2FA пароль в Telethon."""
    query  = update.callback_query if update.callback_query else None
    tg_id  = update.effective_user.id
    api_id   = context.user_data.get("api_id")
    api_hash = context.user_data.get("api_hash")

    msg_func = query.message.reply_text if query else update.message.reply_text

    msg_func("⏳ Проверяем пароль...")

    try:
        client = make_client(tg_id, int(api_id), api_hash)

        async def do_2fa():
            await client.connect()
            return await client.sign_in(password=password)

        run_async(do_2fa())

        _save_user(tg_id, context)
        msg_func(
            "✅ *Аккаунт успешно привязан!*",
            parse_mode=ParseMode.MARKDOWN,
        )

    except PasswordHashInvalidError:
        msg_func(
            "❌ Неверный пароль 2FA. Попробуйте ещё раз:",
            reply_markup=kb_2fa_pad(""),
        )
        context.user_data["2fa_entered"] = ""

    except Exception as e:
        logger.error("Ошибка 2FA: %s", e)
        msg_func(f"❌ Ошибка: {e}")


# ─────────────────────────────────────────────
# ХЕНДЛЕР ТЕКСТОВЫХ СООБЩЕНИЙ
# ─────────────────────────────────────────────
def handle_text(update: Update, context: CallbackContext):
    if not update.message:
        return

    tg_id = update.effective_user.id
    text  = update.message.text.strip()
    state = context.user_data.get("state")

    # ── Шаг 1: номер телефона ────────────────────────────────────
    if state == "REG_PHONE":
        phone = "".join(c for c in text if c.isdigit() or c == "+")
        if len(phone) < 7:
            update.message.reply_text("⚠️ Некорректный номер. Пример: `+79001234567`",
                                      parse_mode=ParseMode.MARKDOWN)
            return

        context.user_data["phone"] = phone
        context.user_data["state"] = "REG_API_ID"
        update.message.reply_text(
            "🔑 *Шаг 1.5: API данные*\n\n"
            "Для работы UserBot нужны ваши `api_id` и `api_hash`.\n\n"
            "Получить их: [my.telegram.org](https://my.telegram.org) → "
            "API development tools\n\n"
            "Введите `api_id` (число):",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        return

    # ── Шаг 1.5а: api_id ─────────────────────────────────────────
    if state == "REG_API_ID":
        if not text.isdigit():
            update.message.reply_text("⚠️ api_id — это число. Попробуйте ещё раз:")
            return
        context.user_data["api_id"] = int(text)
        context.user_data["state"]  = "REG_API_HASH"
        update.message.reply_text("Теперь введите `api_hash` (длинная строка):",
                                  parse_mode=ParseMode.MARKDOWN)
        return

    # ── Шаг 1.5б: api_hash ───────────────────────────────────────
    if state == "REG_API_HASH":
        context.user_data["api_hash"] = text
        context.user_data["state"]    = "WAIT_CODE"
        _send_phone_code(update, context)
        return

    # ── Шаг 3 (текстовый ввод 2FA) ───────────────────────────────
    if state == "WAIT_2FA_TEXT":
        context.user_data["state"] = None
        _submit_2fa(update, context, text)
        return

    update.message.reply_text("Используйте /start")


# ─────────────────────────────────────────────
# ОТПРАВКА КОДА НА ТЕЛЕФОН
# ─────────────────────────────────────────────
def _send_phone_code(update: Update, context: CallbackContext):
    """Вызываем Telethon: отправить SMS/код в Telegram."""
    tg_id    = update.effective_user.id
    phone    = context.user_data.get("phone")
    api_id   = context.user_data.get("api_id")
    api_hash = context.user_data.get("api_hash")

    update.message.reply_text("📲 Отправляем код на ваш номер...")

    try:
        client = make_client(tg_id, api_id, api_hash)

        async def do_send():
            await client.connect()
            result = await client.send_code_request(phone)
            return result.phone_code_hash

        phone_code_hash = run_async(do_send())
        context.user_data["phone_code_hash"] = phone_code_hash
        context.user_data["code_entered"]    = ""

        update.message.reply_text(
            "📬 *Код отправлен!*\n\n"
            "Telegram прислал вам код.\nВведите его цифра за цифрой:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_code_pad(""),
        )

    except FloodWaitError as e:
        update.message.reply_text(
            f"⏳ Слишком много запросов. Подождите {e.seconds} сек. и попробуйте /start"
        )
    except Exception as e:
        logger.error("Ошибка send_code: %s", e)
        update.message.reply_text(f"❌ Ошибка при отправке кода: {e}\n\nПопробуйте /start")


# ─────────────────────────────────────────────
# СОХРАНЕНИЕ ПОЛЬЗОВАТЕЛЯ
# ─────────────────────────────────────────────
def _save_user(tg_id: int, context: CallbackContext):
    users = load_json(USERS_FILE)
    now   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tg_id_str = str(tg_id)

    users[tg_id_str] = {
        "nick":          context.user_data.get("nick", f"user_{tg_id}"),
        "phone":         context.user_data.get("phone", ""),
        "api_id":        context.user_data.get("api_id"),
        "registered_at": now,
        "is_admin":      tg_id_str in ADMIN_IDS,
        "modules":       [],
    }
    save_json(USERS_FILE, users)
    context.user_data.clear()
    logger.info("Пользователь сохранён: tg_id=%s", tg_id)


# ─────────────────────────────────────────────
# ПРОФИЛЬ
# ─────────────────────────────────────────────
def _show_profile(update: Update, context: CallbackContext):
    query = update.callback_query
    tg_id = str(query.from_user.id)
    users = load_json(USERS_FILE)
    user  = users.get(tg_id, {})

    session_path = os.path.join(SESSIONS_DIR, f"{tg_id}.session")
    connected = "✅ Активна" if os.path.exists(session_path) else "❌ Нет сессии"

    query.edit_message_text(
        f"👤 *Профиль*\n\n"
        f"🆔 ID: `{tg_id}`\n"
        f"📱 Телефон: `{user.get('phone', '—')}`\n"
        f"📅 Регистрация: {user.get('registered_at', '—')}\n"
        f"🔗 Сессия: {connected}\n"
        f"🔧 Админ: {'✅' if user.get('is_admin') else '❌'}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Назад", callback_data="noop")]
        ]),
    )


# ─────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────
def main():
    init_system()

    updater = Updater(BOT_TOKEN, use_context=True)
    dp      = updater.dispatcher

    dp.add_handler(CommandHandler("start", cmd_start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    dp.add_error_handler(lambda u, c: logger.error("Ошибка:", exc_info=c.error))

    logger.info("Бот запущен!")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()


if __name__ == "__main__":
    main()
