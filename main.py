import os
import json
import logging
import fcntl
from datetime import datetime, timezone

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ParseMode,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)

# ─────────────────────────────────────────────
# КОНФИГУРАЦИЯ
# ─────────────────────────────────────────────
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS_RAW  = os.environ.get("ADMIN_IDS", "")          # "123456,789012"
ADMIN_IDS      = set(ADMIN_IDS_RAW.split(",")) if ADMIN_IDS_RAW else set()

if not BOT_TOKEN:
    raise RuntimeError("Переменная окружения BOT_TOKEN не задана!")

BASE_DIR        = "/app"
DATA_DIR        = os.path.join(BASE_DIR, "data")
PUBLIC_MODS_DIR = os.path.join(BASE_DIR, "public_modules")
MODULES_DIR     = os.path.join(BASE_DIR, "modules")

USERS_FILE         = os.path.join(DATA_DIR, "users.json")
AUTORESPONDER_FILE = os.path.join(DATA_DIR, "autoresponder_settings.json")

# ─────────────────────────────────────────────
# ЛОГИРОВАНИЕ
# ─────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# JSON — атомарное чтение/запись
# ─────────────────────────────────────────────
def load_file(filepath: str) -> dict:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
            return data
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        logger.error("Повреждён JSON %s: %s", filepath, e)
        return {}


def save_file(filepath: str, data: dict) -> None:
    tmp = filepath + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f, fcntl.LOCK_UN)
        os.replace(tmp, filepath)
    except OSError as e:
        logger.error("Ошибка записи %s: %s", filepath, e)
        raise


# ─────────────────────────────────────────────
# ПОЛЬЗОВАТЕЛИ
# ─────────────────────────────────────────────
def get_user_by_tg_id(tg_id: int):
    """Ищем пользователя по telegram_id. Возвращаем (phone, data) или (None, None)."""
    users = load_file(USERS_FILE)
    tg_id_str = str(tg_id)
    for phone, data in users.items():
        if str(data.get("telegram_id")) == tg_id_str:
            return phone, data
    return None, None


def is_admin(tg_id: int) -> bool:
    """Проверяем: либо в ADMIN_IDS из env, либо флаг is_admin в users.json."""
    if str(tg_id) in ADMIN_IDS:
        return True
    _, data = get_user_by_tg_id(tg_id)
    return bool(data and data.get("is_admin"))


# ─────────────────────────────────────────────
# ИНИЦИАЛИЗАЦИЯ
# ─────────────────────────────────────────────
def init_system():
    for d in (DATA_DIR, PUBLIC_MODS_DIR, MODULES_DIR):
        os.makedirs(d, exist_ok=True)
        logger.info("Директория: %s", d)
    for fp in (USERS_FILE, AUTORESPONDER_FILE):
        if not os.path.exists(fp):
            save_file(fp, {})
            logger.info("Создан файл: %s", fp)


# ─────────────────────────────────────────────
# КЛАВИАТУРЫ
# ─────────────────────────────────────────────
def kb_welcome() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Регистрация", callback_data="auth_reg")],
        [InlineKeyboardButton("🔑 Вход",        callback_data="auth_login")],
    ])


def kb_main(tg_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("⚙️ Модули",  callback_data="menu_modules")],
        [InlineKeyboardButton("👤 Профиль", callback_data="menu_profile")],
    ]
    if is_admin(tg_id):
        rows.append([InlineKeyboardButton("🔧 Админ-панель", callback_data="menu_admin")])
    return InlineKeyboardMarkup(rows)


def kb_back(target: str = "back_start") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад", callback_data=target)]
    ])


# ─────────────────────────────────────────────
# ХЕЛПЕР: отправить или отредактировать сообщение
# ─────────────────────────────────────────────
def send_or_edit(update: Update, text: str, markup=None, parse_mode=None):
    """
    Универсальная отправка.
    Если пришёл callback — редактируем существующее сообщение.
    Если пришло message — отправляем новое.
    Это решает краш при вызове start() из callback-контекста.
    """
    kwargs = {"text": text}
    if markup:
        kwargs["reply_markup"] = markup
    if parse_mode:
        kwargs["parse_mode"] = parse_mode

    if update.callback_query:
        update.callback_query.edit_message_text(**kwargs)
    elif update.message:
        update.message.reply_text(**kwargs)


# ─────────────────────────────────────────────
# ЭКРАНЫ
# ─────────────────────────────────────────────
def screen_start(update: Update, context: CallbackContext):
    """Главный экран — определяет авторизован ли пользователь."""
    tg_id = update.effective_user.id
    _, user_data = get_user_by_tg_id(tg_id)

    if user_data:
        nick = user_data.get("nick", "пользователь")
        send_or_edit(
            update,
            f"🏠 *Главное меню*\nПривет, *{nick}*!",
            markup=kb_main(tg_id),
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        send_or_edit(
            update,
            "👋 *Добро пожаловать в UserBot Hosting!*\n\nВыберите действие:",
            markup=kb_welcome(),
            parse_mode=ParseMode.MARKDOWN,
        )


def screen_modules(update: Update):
    """Список модулей из /app/public_modules/."""
    try:
        files = sorted(f for f in os.listdir(PUBLIC_MODS_DIR) if f.endswith(".py"))
    except OSError:
        files = []

    if files:
        rows = [[InlineKeyboardButton(f"📦 {f}", callback_data=f"mod_{f}")] for f in files]
    else:
        rows = [[InlineKeyboardButton("📭 Модулей пока нет", callback_data="noop")]]

    rows.append([InlineKeyboardButton("◀️ Назад", callback_data="back_start")])

    send_or_edit(
        update,
        f"⚙️ *Список модулей* ({len(files)} шт.):",
        markup=InlineKeyboardMarkup(rows),
        parse_mode=ParseMode.MARKDOWN,
    )


def screen_profile(update: Update):
    tg_id = update.effective_user.id
    phone, data = get_user_by_tg_id(tg_id)

    if not data:
        send_or_edit(update, "❌ Профиль не найден. Зарегистрируйтесь через /start")
        return

    text = (
        f"👤 *Профиль*\n\n"
        f"📛 Ник: *{data.get('nick', '—')}*\n"
        f"📱 Телефон: `{phone}`\n"
        f"🆔 Telegram ID: `{tg_id}`\n"
        f"📅 Регистрация: {data.get('registered_at', '—')}\n"
        f"🔧 Админ: {'✅' if data.get('is_admin') else '❌'}"
    )
    send_or_edit(update, text, markup=kb_back(), parse_mode=ParseMode.MARKDOWN)


def screen_admin(update: Update):
    tg_id = update.effective_user.id
    if not is_admin(tg_id):
        send_or_edit(update, "🚫 Нет доступа.")
        return

    users = load_file(USERS_FILE)
    mods  = [f for f in os.listdir(PUBLIC_MODS_DIR) if f.endswith(".py")]

    text = (
        f"🔧 *Админ-панель*\n\n"
        f"👥 Пользователей: *{len(users)}*\n"
        f"📦 Модулей: *{len(mods)}*\n\n"
        f"Для загрузки модуля — пришли `.py` файл в чат."
    )
    send_or_edit(update, text, markup=kb_back(), parse_mode=ParseMode.MARKDOWN)


# ─────────────────────────────────────────────
# ХЕНДЛЕРЫ КОМАНД
# ─────────────────────────────────────────────
def cmd_start(update: Update, context: CallbackContext):
    # Сбрасываем состояние при /start — пользователь всегда может «выйти»
    context.user_data.clear()
    screen_start(update, context)


# ─────────────────────────────────────────────
# РОУТЕР CALLBACK-КНОПОК
# ─────────────────────────────────────────────
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    tg_id = query.from_user.id
    data  = query.data or ""

    # Всегда отвечаем на callback — иначе кнопка «зависает»
    try:
        query.answer()
    except Exception:
        pass

    # ── Навигация ────────────────────────────────────────────────
    if data == "back_start":
        screen_start(update, context)

    elif data == "noop":
        pass  # Кнопка-заглушка, уже ответили answer()

    elif data == "menu_modules":
        screen_modules(update)

    elif data == "menu_profile":
        screen_profile(update)

    elif data == "menu_admin":
        screen_admin(update)

    # ── Регистрация ──────────────────────────────────────────────
    elif data == "auth_reg":
        _, existing = get_user_by_tg_id(tg_id)
        if existing:
            query.edit_message_text("✅ Вы уже зарегистрированы! Используйте /start")
            return
        context.user_data["state"] = "REG_NICK"
        query.edit_message_text(
            "📝 *Регистрация (1/2)*\n\nПридумайте никнейм (2–32 символа, без пробелов):",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data == "auth_login":
        _, existing = get_user_by_tg_id(tg_id)
        if existing:
            screen_start(update, context)
        else:
            context.user_data["state"] = "LOGIN_PHONE"
            query.edit_message_text(
                "🔑 *Вход*\n\nВведите номер телефона, указанный при регистрации:",
                parse_mode=ParseMode.MARKDOWN,
            )

    # ── Просмотр модуля ──────────────────────────────────────────
    elif data.startswith("mod_"):
        filename = data[4:]
        filepath = os.path.join(PUBLIC_MODS_DIR, filename)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            text = (
                f"📦 *{filename}*\n\n"
                f"📏 Размер: {size} байт\n\n"
                f"Для подключения модуля обратитесь к администратору."
            )
            send_or_edit(update, text, markup=kb_back("menu_modules"),
                         parse_mode=ParseMode.MARKDOWN)
        else:
            query.answer("❌ Файл не найден", show_alert=True)

    else:
        logger.warning("Неизвестный callback: '%s' от %s", data, tg_id)
        query.answer("⚠️ Неизвестная команда", show_alert=True)


# ─────────────────────────────────────────────
# ХЕНДЛЕР ТЕКСТОВЫХ СООБЩЕНИЙ (машина состояний)
# ─────────────────────────────────────────────
def handle_text(update: Update, context: CallbackContext):
    if not update.message:
        return

    tg_id = update.effective_user.id
    text  = update.message.text.strip() if update.message.text else ""
    state = context.user_data.get("state")

    # ── Регистрация: шаг 1 — ник ─────────────────────────────────
    if state == "REG_NICK":
        if len(text) < 2 or len(text) > 32 or " " in text:
            update.message.reply_text(
                "⚠️ Никнейм: 2–32 символа, без пробелов. Попробуйте ещё раз:"
            )
            return

        users = load_file(USERS_FILE)
        if any(d.get("nick", "").lower() == text.lower() for d in users.values()):
            update.message.reply_text(f"❌ Ник *{text}* занят. Введите другой:",
                                      parse_mode=ParseMode.MARKDOWN)
            return

        context.user_data.update({"state": "REG_PHONE", "nick": text})
        update.message.reply_text(
            f"✅ Ник *{text}* свободен!\n\n📱 *Регистрация (2/2)*\nВведите номер телефона:",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Регистрация: шаг 2 — телефон ─────────────────────────────
    if state == "REG_PHONE":
        # Простая нормализация: оставляем только цифры и '+'
        phone = "".join(c for c in text if c.isdigit() or c == "+")
        if len(phone) < 7:
            update.message.reply_text("⚠️ Некорректный номер. Попробуйте ещё раз (например: +79001234567):")
            return

        users = load_file(USERS_FILE)
        if phone in users:
            update.message.reply_text("❌ Этот номер уже зарегистрирован. Используйте /start → Вход")
            context.user_data.clear()
            return

        nick = context.user_data.get("nick", "user")
        now  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        users[phone] = {
            "nick":          nick,
            "telegram_id":   tg_id,
            "registered_at": now,
            "is_admin":      False,
            "modules":       [],
        }
        save_file(USERS_FILE, users)
        context.user_data.clear()

        logger.info("Новый пользователь: %s (%s) tg_id=%s", nick, phone, tg_id)

        update.message.reply_text(
            f"🎉 *Регистрация завершена!*\n\n"
            f"Добро пожаловать, *{nick}*!\n"
            f"Используй меню ниже 👇",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_main(tg_id),
        )
        return

    # ── Вход: телефон ─────────────────────────────────────────────
    if state == "LOGIN_PHONE":
        phone = "".join(c for c in text if c.isdigit() or c == "+")
        users = load_file(USERS_FILE)

        if phone in users and str(users[phone].get("telegram_id")) == str(tg_id):
            context.user_data.clear()
            update.message.reply_text(
                f"✅ Добро пожаловать, *{users[phone].get('nick')}*!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb_main(tg_id),
            )
        else:
            update.message.reply_text(
                "❌ Номер не найден или привязан к другому аккаунту.\n"
                "Попробуйте ещё раз или зарегистрируйтесь: /start"
            )
            context.user_data.clear()
        return

    # ── Нет активного состояния ────────────────────────────────────
    update.message.reply_text("Используйте /start для навигации.")


# ─────────────────────────────────────────────
# ХЕНДЛЕР ДОКУМЕНТОВ (загрузка модулей)
# ─────────────────────────────────────────────
def handle_document(update: Update, context: CallbackContext):
    """
    Только для администраторов.
    Проверяем файл через compile() перед сохранением.
    """
    if not update.message or not update.message.document:
        return

    tg_id = update.effective_user.id

    if not is_admin(tg_id):
        update.message.reply_text("🚫 Загрузка модулей доступна только администраторам.")
        return

    doc = update.message.document
    if not doc.file_name.endswith(".py"):
        update.message.reply_text("⚠️ Принимаются только файлы `.py`")
        return

    if doc.file_size > 512 * 1024:  # 512 KB максимум
        update.message.reply_text("⚠️ Файл слишком большой (максимум 512 КБ)")
        return

    # Скачиваем во временный файл
    tmp_path  = os.path.join(DATA_DIR, f"_tmp_{doc.file_name}")
    dest_path = os.path.join(PUBLIC_MODS_DIR, doc.file_name)

    try:
        tg_file = context.bot.get_file(doc.file_id)
        tg_file.download(tmp_path)

        # Проверяем синтаксис Python
        with open(tmp_path, "r", encoding="utf-8") as f:
            source = f.read()

        try:
            compile(source, doc.file_name, "exec")
        except SyntaxError as e:
            os.remove(tmp_path)
            update.message.reply_text(
                f"❌ *Синтаксическая ошибка в модуле:*\n\n"
                f"`{e.msg}` (строка {e.lineno})\n\n"
                f"Исправьте и загрузите снова.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Всё ок — перемещаем в public_modules
        os.replace(tmp_path, dest_path)
        logger.info("Модуль загружен: %s (admin tg_id=%s)", doc.file_name, tg_id)

        update.message.reply_text(
            f"✅ Модуль *{doc.file_name}* успешно загружен!\n"
            f"Он доступен пользователям в разделе «Модули».",
            parse_mode=ParseMode.MARKDOWN,
        )

    except Exception as e:
        logger.error("Ошибка загрузки модуля: %s", e)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        update.message.reply_text(f"❌ Ошибка при загрузке: {e}")


# ─────────────────────────────────────────────
# ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК
# ─────────────────────────────────────────────
def error_handler(update: object, context: CallbackContext):
    logger.error("Необработанное исключение:", exc_info=context.error)
    if isinstance(update, Update):
        try:
            msg = "⚠️ Внутренняя ошибка. Попробуйте /start"
            if update.callback_query:
                update.callback_query.answer(msg, show_alert=True)
            elif update.message:
                update.message.reply_text(msg)
        except Exception:
            pass


# ─────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────
def main():
    init_system()

    updater = Updater(BOT_TOKEN, use_context=True)
    dp      = updater.dispatcher

    dp.add_handler(CommandHandler("start", cmd_start))

    dp.add_handler(CallbackQueryHandler(button_handler))

    # ВАЖНО: два отдельных хендлера — текст и документы
    # Filters.text & ~Filters.command — исключаем команды из text handler
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    dp.add_handler(MessageHandler(Filters.document, handle_document))

    dp.add_error_handler(error_handler)

    logger.info("🚀 Бот запущен!")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()


if __name__ == "__main__":
    main()
