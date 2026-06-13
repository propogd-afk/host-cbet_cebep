from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CallbackQueryHandler, CommandHandler, MessageHandler, Filters, CallbackContext
import json
import os
import asyncio
import shutil
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PasswordHashInvalidError

# ===== КОНФИГУРАЦИЯ =====
BOT_TOKEN = "8989430238:AAGlmVp6oHHa3y3xZedRL2ov9dj-h65vC3A"
ADMIN_PASSWORD = "uretracoin"
USERS_FILE = "users.json"
SUBS_FILE = "subscriptions.json"
AUTORESPONDER_FILE = "autoresponder_settings.json"
MODULES_DIR = "modules"
PUBLIC_MODS_DIR = "public_modules"
# =======================

user_states = {} 
global_loop = asyncio.get_event_loop()

# Функции базы данных
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

def get_sub(tg_id):
    subs = load_file(SUBS_FILE)
    if str(tg_id) not in subs:
        subs[str(tg_id)] = {"tier": 1, "expires": (datetime.now() + timedelta(days=10)).isoformat()}
        save_file(SUBS_FILE, subs)
    return subs[str(tg_id)]

def get_user_modules_dir(tg_id):
    u_dir = os.path.join(MODULES_DIR, "user_" + str(tg_id))
    os.makedirs(u_dir, exist_ok=True)
    return u_dir

def get_ar_settings(tg_id):
    data = load_file(AUTORESPONDER_FILE)
    s_id = str(tg_id)
    if s_id not in data:
        data[s_id] = {"enabled": False, "target": "all", "mode": "normal", "custom_text": ""}
        save_file(AUTORESPONDER_FILE, data)
    return data[s_id]

def save_ar_settings(tg_id, settings):
    data = load_file(AUTORESPONDER_FILE)
    data[str(tg_id)] = settings
    save_file(AUTORESPONDER_FILE, data)

# Авто-создание модулей
def create_base_modules():
    os.makedirs(PUBLIC_MODS_DIR, exist_ok=True)
    # Создаем 3 файла, если их нет
    if not os.path.exists(os.path.join(PUBLIC_MODS_DIR, "trollbaza.py")):
        with open(os.path.join(PUBLIC_MODS_DIR, "trollbaza.py"), "w", encoding="utf-8") as f:
            f.write("# meta developer: @Cbet_Hosting\nimport asyncio\nfrom telethon import events\n\n@events.register(events.NewMessage(pattern=r'\\.trollbaza (\\d+) (.+)'))\nasync def troll_start(event):\n    if event.out:\n        delay = int(event.pattern_match.group(1))\n        text = event.pattern_match.group(2)\n        await event.delete()\n        for word in text.split():\n            await event.respond(word)\n            if delay > 0: await asyncio.sleep(min(delay, 5))")
    
    if not os.path.exists(os.path.join(PUBLIC_MODS_DIR, "spam.py")):
        with open(os.path.join(PUBLIC_MODS_DIR, "spam.py"), "w", encoding="utf-8") as f:
            f.write("# meta developer: @Cbet_Hosting\nfrom telethon import events\n\n@events.register(events.NewMessage(pattern=r'\\.spam (.+) (\\d+)'))\nasync def spam_start(event):\n    if event.out:\n        text = event.pattern_match.group(1)\n        count = int(event.pattern_match.group(2))\n        await event.delete()\n        for _ in range(count): await event.respond(text)")

    if not os.path.exists(os.path.join(PUBLIC_MODS_DIR, "autoresponder.py")):
        with open(os.path.join(PUBLIC_MODS_DIR, "autoresponder.py"), "w", encoding="utf-8") as f:
            f.write("# meta developer: @Cbet_Hosting\nfrom telethon import events\n\n@events.register(events.NewMessage(incoming=True))\nasync def ar_handler(event):\n    pass")

# Хендлеры и логика меню (упрощено для компактности)
def start(update: Update, context: CallbackContext):
    tg_id = update.effective_user.id
    _, user_data = get_user_by_tg_id(tg_id)
    if user_data:
        update.message.reply_text("✅ Вы уже авторизованы в системе.")
    else:
        update.message.reply_text("👋 Добро пожаловать! Используйте /start или кнопки.")

def handle_text(update: Update, context: CallbackContext):
    if not update.message: return
    tg_id = update.effective_user.id
    
    # Продвинутая загрузка модулей с проверкой
    if update.message.document:
        _, user_data = get_user_by_tg_id(tg_id)
        if user_data and user_data.get("password") == ADMIN_PASSWORD:
            doc = update.message.document
            if doc.file_name.endswith(".py"):
                temp_path = "temp_module.py"
                context.bot.get_file(doc.file_id).download(temp_path)
                try:
                    with open(temp_path, "r", encoding="utf-8") as f:
                        compile(f.read(), temp_path, 'exec')
                    shutil.move(temp_path, os.path.join(PUBLIC_MODS_DIR, doc.file_name))
                    update.message.reply_text(f"✅ Модуль {doc.file_name} проверен и добавлен!")
                except SyntaxError as e:
                    os.remove(temp_path)
                    update.message.reply_text(f"❌ Ошибка в коде (строка {e.lineno}): {e.text.strip()}")
                return

def main():
    os.makedirs(MODULES_DIR, exist_ok=True)
    create_base_modules()
    
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text | Filters.document, handle_text))
    
    print("🚀 Бот запущен!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
