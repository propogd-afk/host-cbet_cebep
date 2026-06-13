import os
import json
import asyncio
import shutil
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CallbackQueryHandler, CommandHandler, MessageHandler, Filters, CallbackContext

# ПУТИ
BASE_DIR = "/app"
PUBLIC_MODS_DIR = os.path.join(BASE_DIR, "public_modules")
MODULES_DIR = os.path.join(BASE_DIR, "modules")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
SUBS_FILE = os.path.join(BASE_DIR, "subscriptions.json")
AUTORESPONDER_FILE = os.path.join(BASE_DIR, "autoresponder_settings.json")

BOT_TOKEN = "8989430238:AAGlmVp6oHHa3y3xZedRL2ov9dj-h65vC3A"
ADMIN_PASSWORD = "uretracoin"

# Инициализация
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

# Хендлеры
def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Привет! Используй кнопки для управления.", 
                              reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Модули", callback_data="menu_modules")]]))

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    try:
        query.answer()
        data = query.data
        
        if data == "menu_modules":
            if not os.path.exists(PUBLIC_MODS_DIR):
                os.makedirs(PUBLIC_MODS_DIR)
            
            files = [f for f in os.listdir(PUBLIC_MODS_DIR) if f.endswith('.py')]
            if not files:
                query.edit_message_text("⚙️ Список пуст.")
                return

            keyboard = [[InlineKeyboardButton(f"📦 {f}", callback_data=f"mod_view_{f}")] for f in files]
            query.edit_message_text("⚙️ Доступные модули:", reply_markup=InlineKeyboardMarkup(keyboard))
            
        elif data.startswith("mod_view_"):
            filename = data.replace("mod_view_", "")
            query.edit_message_text(f"Выбран: {filename}\nЗагружен в систему.")

    except Exception as e:
        print(f"Ошибка: {e}")

def handle_text(update: Update, context: CallbackContext):
    if update.message.document:
        tg_id = update.effective_user.id
        _, user_data = get_user_by_tg_id(tg_id)
        
        if user_data and user_data.get("password") == ADMIN_PASSWORD:
            doc = update.message.document
            if doc.file_name.endswith(".py"):
                temp_path = os.path.join(BASE_DIR, "temp.py")
                context.bot.get_file(doc.file_id).download(temp_path)
                
                try:
                    with open(temp_path, "r", encoding="utf-8") as f:
                        compile(f.read(), temp_path, 'exec')
                    shutil.move(temp_path, os.path.join(PUBLIC_MODS_DIR, doc.file_name))
                    update.message.reply_text(f"✅ Модуль {doc.file_name} успешно добавлен!")
                except Exception as e:
                    update.message.reply_text(f"❌ Ошибка в коде: {e}")
                    if os.path.exists(temp_path): os.remove(temp_path)

def main():
    # Создание директорий
    os.makedirs(PUBLIC_MODS_DIR, exist_ok=True)
    os.makedirs(MODULES_DIR, exist_ok=True)
    
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.document, handle_text))
    
    print("🚀 Бот запущен!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
