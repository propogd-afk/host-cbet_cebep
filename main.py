from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes
import json
import os
import random
import string
import importlib.util
import sys
import asyncio
from datetime import datetime, timedelta

# Импортируем Telethon для работы с сессиями
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PasswordHashInvalidError

# ===== КОНФИГУРАЦИЯ =====
BOT_TOKEN = "8989430238:AAGlmVp6oHHa3y3xZedRL2ov9dj-h65vC3A"  # <-- Твой токен от @BotFather
ADMIN_PASSWORD = "uretracoin"
USERS_FILE = "users.json"
SUBS_FILE = "subscriptions.json"
PROMOS_FILE = "promocodes.json"
MODULES_DIR = "modules"
# =======================

TIERS = {
    1: {"name": "Пробная", "limit": 3, "modules_desc": "3 модуля"},
    2: {"name": "Базовый", "limit": 5, "modules_desc": "5 модулей"},
    3: {"name": "Премиум", "limit": 7, "modules_desc": "7 модулей, 1 приватный"},
    4: {"name": "VIP", "limit": 20, "modules_desc": "20 модулей, 3 приватных"}
}

user_states = {} 
DYNAMIC_HANDLERS = {}

# Вспомогательные функции для БД
def load_file(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except json.JSONDecodeError: return {}
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
    u_dir = os.path.join(MODULES_DIR, f"user_{tg_id}")
    os.makedirs(u_dir, exist_ok=True)
    return u_dir

# ===== ИНИЦИАЛИЗАЦИЯ И ХЕНДЛЕРЫ БОТА =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    phone, user_data = get_user_by_tg_id(tg_id)
    if tg_id in user_states: del user_states[tg_id]
        
    if user_data:
        await show_main_menu(update, context, user_data, is_callback=False)
    else:
        keyboard = [
            [InlineKeyboardButton("📝 Регистрация", callback_data="auth_reg")],
            [InlineKeyboardButton("🔑 Вход", callback_data="auth_login")]
        ]
        await update.message.reply_text(
            "👋 Добро пожаловать в Хостинг Юзерботов Hikka!\n\nЗарегистрируйтесь, чтобы создать свой процесс юзербота:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data, is_callback=True):
    tg_id = update.effective_user.id
    sub = get_sub(tg_id)
    phone, _ = get_user_by_tg_id(tg_id)
    
    # Проверяем, создана ли сессия (живой ли юзербот на сервере)
    u_dir = get_user_modules_dir(tg_id)
    session_exists = os.path.exists(os.path.join(u_dir, f"{phone}.session"))
    status_ub = "🟢 Запущен" if session_exists else "🔴 Не авторизован"

    text = (
        f"🏠 <b>Панель Управления Юзерботом</b>\n\n"
        f"Аккаунт: <code>{user_data['nick']}</code>\n"
        f"Статус юзербота: <b>{status_ub}</b>\n"
        f"Тариф: <b>{TIERS[sub['tier']]['name']}</b>\n"
        f"Доступен до: {sub['expires'][:10]}"
    )
    keyboard = [
        [InlineKeyboardButton("👤 Профиль", callback_data="menu_profile"), InlineKeyboardButton("⚙️ Модули", callback_data="menu_modules")],
        [InlineKeyboardButton("❌ Отключить юзербота", callback_data="reset_api") if session_exists else InlineKeyboardButton("🚀 Авторизовать / Запустить", callback_data="start_ub_auth")],
        [InlineKeyboardButton("❌ Выйти из панели", callback_data="menu_logout")]
    ]
    if is_callback: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ===== ОБРАБОТКА НАЖАТИЙ КНОПОК =====

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tg_id = query.from_user.id
    data = query.data
    phone, user_data = get_user_by_tg_id(tg_id)
    
    if data == "auth_reg":
        user_states[tg_id] = {"state": "REG_NICK", "data": {}}
        await query.edit_message_text("📝 <b>Регистрация</b>\n\nПридумай публичный ник:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="to_welcome")]]))
    elif data == "auth_login":
        user_states[tg_id] = {"state": "LOGIN_PHONE", "data": {}}
        await query.edit_message_text("🔑 <b>Вход</b>\n\nВведи номер телефона (+79123456789):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="to_welcome")]]))
    elif data == "to_welcome":
        if tg_id in user_states: del user_states[tg_id]
        await query.edit_message_text("👋 Добро пожаловать!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 Регистрация", callback_data="auth_reg")], [InlineKeyboardButton("🔑 Вход", callback_data="auth_login")]]))
    elif data == "to_main_menu":
        if tg_id in user_states: del user_states[tg_id]
        if user_data: await show_main_menu(update, context, user_data, is_callback=True)
    elif data == "menu_profile":
        if not user_data: return
        sub = get_sub(tg_id)
        has_session = "✅ Активна" if os.path.exists(os.path.join(get_user_modules_dir(tg_id), f"{phone}.session")) else "❌ Отсутствует"
        text = f"👤 <b>Личный кабинет</b>\n\n<b>Ник:</b> {user_data['nick']}\n<b>Телефон:</b> {phone}\n<b>Сессия на сервере:</b> {has_session}"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="to_main_menu")]]), parse_mode="HTML")
    elif data == "menu_logout":
        if phone:
            users = load_file(USERS_FILE)
            users[phone]["telegram_id"] = None
            save_file(USERS_FILE, users)
        await query.edit_message_text("❌ Вы вышли из панели.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ На главную", callback_data="to_welcome")]]))
    
    # Запуск триггера авторизации юзербота из меню
    elif data == "start_ub_auth":
        user_states[tg_id] = {"state": "REG_API_ID", "data": {"phone": phone, "nick": user_data["nick"], "password": user_data["password"]}}
        await query.edit_message_text("⚙️ <b>Настройка сессии Telethon</b>\n\nВведите ваш <b>api_id</b> с сайта my.telegram.org (или 'пропустить'):")

    elif data == "reset_api":
        if phone:
            u_dir = get_user_modules_dir(tg_id)
            sess_path = os.path.join(u_dir, f"{phone}.session")
            if os.path.exists(sess_path): 
                try: os.remove(sess_path)
                except: pass
            users = load_file(USERS_FILE)
            users[phone]["api_id"] = None
            users[phone]["api_hash"] = None
            save_file(USERS_FILE, users)
        await query.edit_message_text("🛑 Юзербот остановлен, сессия удалена с сервера.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ В меню", callback_data="to_main_menu")]]))

# ===== МАГИЯ АВТОРЗАТИИ TELETHON (СМС, КОД, 2FA) =====

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    text = update.message.text.strip()
    phone, user_data = get_user_by_tg_id(tg_id)
    
    if tg_id not in user_states: return
    state = user_states[tg_id].get("state")
    is_skip = text.lower() in ["/skip", "skip", "пропустить"]

    # --- ЦЕПОЧКА РЕГИСТРАЦИИ ---
    if state == "REG_NICK":
        if 3 <= len(text) <= 32:
            user_states[tg_id]["data"]["nick"] = text
            user_states[tg_id]["state"] = "REG_PHONE"
            await update.message.reply_text("Введи номер телефона аккаунта Telegram (+79123456789):")
    elif state == "REG_PHONE":
        # Проверяем маску номера телефона
        if not text.startswith("+") or not text[1:].isdigit():
            await update.message.reply_text("❌ Номер должен быть в международном формате, например: +79123456789")
            return
        user_states[tg_id]["data"]["phone"] = text
        user_states[tg_id]["state"] = "REG_PASS"
        await update.message.reply_text("Придумай пароль для входа в панель бота:")
    elif state == "REG_PASS":
        user_states[tg_id]["data"]["password"] = text
        user_states[tg_id]["state"] = "REG_API_ID"
        await update.message.reply_text("⚙️ <b>Регистрация профиля успешна!</b>\n\nТеперь настроим юзербота.\nВведите ваш <b>api_id</b> (или напишите 'пропустить'):")
        
    elif state == "REG_API_ID":
        if is_skip:
            await finalize_registration(update, context, skip_ub=True)
        else:
            if not text.isdigit():
                await update.message.reply_text("❌ api_id должен состоять только из цифр:")
                return
            user_states[tg_id]["data"]["api_id"] = text
            user_states[tg_id]["state"] = "REG_API_HASH"
            await update.message.reply_text("✅ api_id принят. Теперь введите ваш <b>api_hash</b>:")
            
    elif state == "REG_API_HASH":
        user_states[tg_id]["data"]["api_hash"] = text
        
        # Данные собраны, начинаем коннект через Telethon для генерации сессии!
        u_phone = user_states[tg_id]["data"]["phone"]
        u_dir = get_user_modules_dir(tg_id)
        sess_path = os.path.join(u_dir, u_phone) # Будет создан файл {phone}.session
        
        await update.message.reply_text("⏳ Подключаюсь к серверам Telegram для отправки СМС-кода...")
        
        try:
            # Создаем экземпляр клиента Telethon внутри папки пользователя
            client = TelegramClient(sess_path, int(user_states[tg_id]["data"]["api_id"]), user_states[tg_id]["data"]["api_hash"])
            await client.connect()
            
            # Отправляем код подтверждения на номер юзера
            send_code_obj = await client.send_code_request(u_phone)
            
            # Сохраняем клиент и хэш кода в сессию стейта, чтобы использовать на следующем шаге
            user_states[tg_id]["client"] = client
            user_states[tg_id]["phone_code_hash"] = send_code_obj.phone_code_hash
            user_states[tg_id]["state"] = "INPUT_TG_CODE"
            
            await update.message.reply_text("📩 Telegram отправил вам код подтверждения. \n\n<b>Введите полученный код:</b>", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка инициализации Telethon: {e}\nРегистрация завершена без юзербота. Вы можете настроить его позже.")
            await finalize_registration(update, context, skip_ub=True)

    # --- ПРИЕМ КОДА ИЗ СМС / ПРИЛОЖЕНИЯ TELEGRAM ---
    elif state == "INPUT_TG_CODE":
        client = user_states[tg_id]["client"]
        phone_code_hash = user_states[tg_id]["phone_code_hash"]
        u_phone = user_states[tg_id]["data"]["phone"]
        
        await update.message.reply_text("⏳ Проверяю код...")
        try:
            # Пытаемся залогиниться по коду
            await client.sign_in(phone=u_phone, code=text, phone_code_hash=phone_code_hash)
            
            # Если вошли без пароля 2FA:
            await update.message.reply_text("✅ Авторизация успешна! Сессия сохранена на сервере.")
            await client.disconnect()
            await finalize_registration(update, context, skip_ub=False)
            
        except SessionPasswordNeededError:
            # Опа, у юзера стоит Облачный Пароль (Двухфакторка)
            user_states[tg_id]["state"] = "INPUT_TG_2FA"
            await update.message.reply_text("🔒 Аккаунт защищен двухфакторной аутентификацией.\n\n<b>Введите ваш Облачный Пароль (2FA):</b>", parse_mode="HTML")
        except PhoneCodeInvalidError:
            await update.message.reply_text("❌ Неверный код! Введите код еще раз:")
        except Exception as e:
            await update.message.reply_text(f"❌ Непредвиденная ошибка: {e}")
            await client.disconnect()
            del user_states[tg_id]

    # --- ПРИЕМ ОБЛАЧНОГО ПАРОЛЯ (2FA) ---
    elif state == "INPUT_TG_2FA":
        client = user_states[tg_id]["client"]
        try:
            await client.sign_in(password=text)
            await update.message.reply_text("✅ Двухфакторный пароль принят! Юзербот успешно запущен в фон.")
            await client.disconnect()
            await finalize_registration(update, context, skip_ub=False)
        except PasswordHashInvalidError:
            await update.message.reply_text("❌ Неверный облачный пароль! Попробуйте еще раз:")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка 2FA: {e}")
            await client.disconnect()
            del user_states[tg_id]

    # --- ХЕНДЛЕР ВХОДА ПО ТЕЛЕФОНУ В ПАНЕЛЬ ---
    elif state == "LOGIN_PHONE":
        users = load_file(USERS_FILE)
        if text not in users:
            await update.message.reply_text("❌ Пользователь с таким номером не найден.")
            return
        user_states[tg_id]["data"]["phone"] = text
        user_states[tg_id]["state"] = "LOGIN_PASS"
        await update.message.reply_text("🔒 Введи пароль от панели:")
    elif state == "LOGIN_PASS":
        p = user_states[tg_id]["data"]["phone"]
        users = load_file(USERS_FILE)
        if users[p]["password"] == text:
            users[p]["telegram_id"] = tg_id
            save_file(USERS_FILE, users)
            del user_states[tg_id]
            await update.message.reply_text("✅ Вход выполнен успешно!")
            await show_main_menu(update, context, users[p], is_callback=False)
        else:
            await update.message.reply_text("❌ Неверный пароль!")

# ===== ЗАВЕРШЕНИЕ СЦЕНАРИЯ И СОХРАНЕНИЕ В JSON =====

async def finalize_registration(update: Update, context: ContextTypes.DEFAULT_TYPE, skip_ub=False):
    tg_id = update.effective_user.id
    users = load_file(USERS_FILE)
    d = user_states[tg_id]["data"]
    phone = d["phone"]
    
    users[phone] = {
        "nick": d["nick"],
        "password": d["password"],
        "telegram_id": tg_id,
        "api_id": d.get("api_id") if not skip_ub else None,
        "api_hash": d.get("api_hash") if not skip_ub else None
    }
    save_file(USERS_FILE, users)
    get_sub(tg_id)
    
    # Очищаем сессию стейтов, кроме самого клиента (чтобы не разорвать коннект преждевременно)
    del user_states[tg_id]
    
    await update.message.reply_text("🎉 Профиль сохранен в базе данных хостинга!")
    await show_main_menu(update, context, users[phone], is_callback=False)

def main():
    os.makedirs(MODULES_DIR, exist_ok=True)
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🚀 Хостинг-панель запущена! Telethon авторизация в реальном времени работает.")
    app.run_polling()

if __name__ == "__main__": main()
