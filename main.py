import os
import json
import shutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CallbackQueryHandler, CommandHandler, MessageHandler, Filters, CallbackContext

# ===== КОНФИГУРАЦИЯ =====
BASE_DIR = "/app"
DATA_DIR = os.path.join(BASE_DIR, "data")
PUBLIC_MODS_DIR = os.path.join(BASE_DIR, "public_modules")
MODULES_DIR = os.path.join(BASE_DIR, "modules")

USERS_FILE = os.path.join(DATA_DIR, "users.json")
AUTORESPONDER_FILE = os.path.join(DATA_DIR, "autoresponder_settings.json")

BOT_TOKEN = "8989430238:AAGlmVp6oHHa3y3xZedRL2ov9dj-h65vC3A"
ADMIN_PASSWORD = "uretracoin"

user_states = {}

# ===== БАЗА ДАННЫХ =====
def load_file(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_file(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_user_by_tg_id(tg_id):
    users = load_file(USERS_FILE)
    for phone, data in users.items():
        if data.get("telegram_id") == tg_id: return phone, data
    return None, None

def init_system():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PUBLIC_MODS_DIR, exist_ok=True)
    os.makedirs(MODULES_DIR, exist_ok=True)
    for f in [USERS_FILE, AUTORESPONDER_FILE]:
        if not os.path.exists(f): save_file(f, {})

# ===== ИНТЕРФЕЙС =====
def start(update: Update, context: CallbackContext):
    tg_id = update.effective_user.id
    _, user_data = get_user_by_tg_id(tg_id)
    
    if user_data:
        keyboard = [[InlineKeyboardButton("⚙️ Модули", callback_data="menu_modules")]]
        update.message.reply_text("🏠 Главное меню:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        keyboard = [
            [InlineKeyboardButton("📝 Регистрация", callback_data="auth_reg")],
            [InlineKeyboardButton("🔑 Вход", callback_data="auth_login")]
        ]
        update.message.reply_text("👋 Добро пожаловать! Выберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    tg_id = query.from_user.id

    if data == "auth_reg":
        user_states[tg_id] = {"state": "REG_NICK"}
        query.edit_message_text("📝 Придумай ник:")
    elif data == "menu_modules":
        files = [f for f in os.listdir(PUBLIC_MODS_DIR) if f.endswith('.py')]
        kb = [[InlineKeyboardButton(f"📦 {f}", callback_data=f"mod_{f}")] for f in files]
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_start")])
        query.edit_message_text("⚙️ Список модулей:", reply_markup=InlineKeyboardMarkup(kb))
    elif data == "back_start":
        start(update, context) # Рекурсивный вызов для возврата в меню

def handle_text(update: Update, context: CallbackContext):
    if not update.message: return
    tg_id = update.effective_user.id
    text = update.message.text
    
    # Регистрация (упрощенная)
    if tg_id in user_states and user_states[tg_id]["state"] == "REG_NICK":
        user_states[tg_id] = {"state": "REG_PHONE", "nick": text}
        update.message.reply_text("📱 Введи телефон:")
    elif tg_id in user_states and user_states[tg_id]["state"] == "REG_PHONE":
        nick = user_states[tg_id]["nick"]
        users = load_file(USERS_FILE)
        users[text] = {"nick": nick, "telegram_id": tg_id}
        save_file(USERS_FILE, users)
        del user_states[tg_id]
        update.message.reply_text("✅ Успешно! Теперь ты в базе данных /app/data/users.json")
        start(update, context)

    # Админ-загрузка
    if update.message.document:
        _, user_data = get_user_by_tg_id(tg_id)
        if user_data and user_data.get("password") == ADMIN_PASSWORD:
            doc = update.message.document
            if doc.file_name.endswith(".py"):
                path = os.path.join(PUBLIC_MODS_DIR, doc.file_name)
                context.bot.get_file(doc.file_id).download(path)
                update.message.reply_text(f"✅ Модуль {doc.file_name} добавлен!")

def main():
    init_system()
    updater = Updater(BOT_TOKEN, use_context=True)
    updater.dispatcher.add_handler(CommandHandler("start", start))
    updater.dispatcher.add_handler(CallbackQueryHandler(button_handler))
    updater.dispatcher.add_handler(MessageHandler(Filters.text | Filters.document, handle_text))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
