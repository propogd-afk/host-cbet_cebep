from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
# Используем синтаксис python-telegram-bot v13
from telegram.ext import Updater, CallbackQueryHandler, CommandHandler, MessageHandler, Filters, CallbackContext
import json
import os
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
global_loop = asyncio.get_event_loop()

# Вспомогательные функции для БД
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

# Проверка уникальности ника
def is_nick_taken(nick):
    users = load_file(USERS_FILE)
    for phone, data in users.items():
        if data.get("nick", "").lower() == nick.lower():
            return True
    return False

# ===== ИНЛАЙН КЛАВИАТУРА ДЛЯ ВВОДА СМС-КОДА =====
def get_number_keyboard(current_code=""):
    keyboard = [
        [InlineKeyboardButton("1", callback_data="num_1"), InlineKeyboardButton("2", callback_data="num_2"), InlineKeyboardButton("3", callback_data="num_3")],
        [InlineKeyboardButton("4", callback_data="num_4"), InlineKeyboardButton("5", callback_data="num_5"), InlineKeyboardButton("6", callback_data="num_6")],
        [InlineKeyboardButton("7", callback_data="num_7"), InlineKeyboardButton("8", callback_data="num_8"), InlineKeyboardButton("9", callback_data="num_9")],
        [InlineKeyboardButton("❌ Стереть", callback_data="num_clear"), InlineKeyboardButton("0", callback_data="num_0"), InlineKeyboardButton("✅ Войти", callback_data="num_submit")]
    ]
    stars = " " + ("*" * len(current_code)) if current_code else " пусто"
    text = "📩 Telegram отправил вам код подтверждения.\n\n<b>Кликайте по кнопкам ниже для ввода (так безопаснее):</b>\n👉 <code>Введено:" + stars + "</code>"
    return text, InlineKeyboardMarkup(keyboard)

# ===== ИНИЦИАЛИЗАЦИЯ И ХЕНДЛЕРЫ БОТА =====

def start(update: Update, context: CallbackContext):
    if not update.message: return
    tg_id = update.effective_user.id
    phone, user_data = get_user_by_tg_id(tg_id)
    if tg_id in user_states: del user_states[tg_id]
        
    if user_data:
        show_main_menu(update, context, user_data, is_callback=False)
    else:
        keyboard = [
            [InlineKeyboardButton("📝 Регистрация", callback_data="auth_reg")],
            [InlineKeyboardButton("🔑 Вход", callback_data="auth_login")]
        ]
        update.message.reply_text(
            "👋 Добро пожаловать в Хостинг Юзерботов Hikka!\n\nЗарегистрируйтесь, чтобы создать свой процесс юзербота:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

def show_main_menu(update: Update, context: CallbackContext, user_data, is_callback=True):
    tg_id = update.effective_user.id
    sub = get_sub(tg_id)
    phone, _ = get_user_by_tg_id(tg_id)
    
    u_dir = get_user_modules_dir(tg_id)
    session_exists = os.path.exists(os.path.join(u_dir, str(phone) + ".session"))
    status_ub = "🟢 Запущен" if session_exists else "🔴 Не авторизован"

    text = (
        "🏠 <b>Панель Управления Юзерботом</b>\n\n"
        "Аккаунт: <code>" + str(user_data['nick']) + "</code>\n"
        "Статус юзербота: <b>" + status_ub + "</b>\n"
        "Тариф: <b>" + str(TIERS[sub['tier']]['name']) + "</b>\n"
        "Доступен до: " + str(sub['expires'][:10])
    )
    keyboard = [
        [InlineKeyboardButton("👤 Профиль", callback_data="menu_profile"), InlineKeyboardButton("⚙️ Модули", callback_data="menu_modules")],
        [InlineKeyboardButton("❌ Отключить юзербота", callback_data="reset_api") if session_exists else InlineKeyboardButton("🚀 Авторизовать / Запустить", callback_data="start_ub_auth")],
        [InlineKeyboardButton("❌ Выйти из панели", callback_data="menu_logout")]
    ]
    if is_callback: update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else: update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ===== ОБРАБОТКА НАЖАТИЙ КНОПОК =====

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    tg_id = query.from_user.id
    data = query.data
    phone, user_data = get_user_by_tg_id(tg_id)
    
    if data == "auth_reg":
        user_states[tg_id] = {"state": "REG_NICK", "data": {}}
        query.edit_message_text("📝 <b>Регистрация</b>\n\nПридумай публичный ник:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="to_welcome")]]), parse_mode="HTML")
    elif data == "auth_login":
        user_states[tg_id] = {"state": "LOGIN_PHONE", "data": {}}
        query.edit_message_text("🔑 <b>Вход</b>\n\nВведи номер телефона (+79123456789):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="to_welcome")]]), parse_mode="HTML")
    elif data == "to_welcome":
        if tg_id in user_states: del user_states[tg_id]
        query.edit_message_text("👋 Добро пожаловать!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 Регистрация", callback_data="auth_reg")], [InlineKeyboardButton("🔑 Вход", callback_data="auth_login")]]))
    elif data == "to_main_menu":
        if tg_id in user_states: del user_states[tg_id]
        if user_data: show_main_menu(update, context, user_data, is_callback=True)
    elif data == "menu_profile":
        if not user_data: return
        sub = get_sub(tg_id)
        has_session = "✅ Активна" if os.path.exists(os.path.join(get_user_modules_dir(tg_id), str(phone) + ".session")) else "❌ Отсутствует"
        text = "👤 <b>Личный кабинет</b>\n\n<b>Ник:</b> " + str(user_data['nick']) + "\n<b>Телефон:</b> " + str(phone) + "\n<b>Сессия на сервере:</b> " + has_session
        query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="to_main_menu")]]), parse_mode="HTML")
    elif data == "menu_modules":
        query.edit_message_text("⚙️ <b>Управление модулями</b>\n\nВ данный момент нет доступных модулей для установки.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="to_main_menu")]]), parse_mode="HTML")
    elif data == "menu_logout":
        if phone:
            users = load_file(USERS_FILE)
            if phone in users:
                users[phone]["telegram_id"] = None
                save_file(USERS_FILE, users)
        query.edit_message_text("❌ Вы вышли из панели.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ На главную", callback_data="to_welcome")]]))
    
    elif data == "start_ub_auth":
        user_states[tg_id] = {"state": "REG_API_ID", "data": {"phone": phone, "nick": user_data["nick"], "password": user_data["password"]}}
        query.edit_message_text("⚙️ <b>Настройка сессии Telethon</b>\n\nВведите ваш <b>api_id</b> с сайта my.telegram.org (или 'пропустить'):", parse_mode="HTML")

    elif data == "reset_api":
        if phone:
            u_dir = get_user_modules_dir(tg_id)
            sess_path = os.path.join(u_dir, str(phone) + ".session")
            if os.path.exists(sess_path): 
                try: os.remove(sess_path)
                except: pass
            users = load_file(USERS_FILE)
            if phone in users:
                users[phone]["api_id"] = None
                users[phone]["api_hash"] = None
                save_file(USERS_FILE, users)
        query.edit_message_text("🛑 Юзербот остановлен, сессия удалена с сервера.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ В меню", callback_data="to_main_menu")]]))

    # --- ИНЛАЙН КНОПКИ ДЛЯ ВВОДА КОДА ---
    elif data.startswith("num_"):
        if tg_id not in user_states or user_states[tg_id].get("state") != "INPUT_TG_CODE":
            return
            
        if "code_buffer" not in user_states[tg_id]:
            user_states[tg_id]["code_buffer"] = ""
            
        action = data.split("_")[1]
        
        if action == "clear":
            user_states[tg_id]["code_buffer"] = ""
            text, reply_markup = get_number_keyboard(user_states[tg_id]["code_buffer"])
            query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
            
        elif action == "submit":
            code = user_states[tg_id]["code_buffer"]
            if len(code) != 5:
                text, reply_markup = get_number_keyboard(code)
                query.edit_message_text(text + "\n\n⚠️ <i>Код должен состоять из 5 цифр!</i>", reply_markup=reply_markup, parse_mode="HTML")
                return
                
            query.edit_message_text("⏳ Проверяю введенный код...")
            process_tg_code(query.message, context, tg_id, code)
            
        else:
            if len(user_states[tg_id]["code_buffer"]) < 5:
                user_states[tg_id]["code_buffer"] += action
            text, reply_markup = get_number_keyboard(user_states[tg_id]["code_buffer"])
            query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")

# ===== ОБРАБОТКА ВВОДА ТЕКСТА =====

def handle_text(update: Update, context: CallbackContext):
    if not update.message: return
    tg_id = update.effective_user.id
    text = update.message.text.strip()
    
    if tg_id not in user_states: 
        return

    state = user_states[tg_id].get("state")
    is_skip = text.lower() in ["/skip", "skip", "пропустить"]

    try:
        if state == "REG_NICK":
            if 3 <= len(text) <= 32:
                # ПРОВЕРКА: занят ли никнейм
                if is_nick_taken(text):
                    update.message.reply_text("❌ Данный никнейм уже занят! Придумайте другой:")
                    return
                
                user_states[tg_id]["data"]["nick"] = text
                user_states[tg_id]["state"] = "REG_PHONE"
                update.message.reply_text("Введи номер телефона аккаунта Telegram (+79123456789):")
            else:
                update.message.reply_text("❌ Ник должен быть от 3 до 32 символов!")
                
        elif state == "REG_PHONE":
            if not text.startswith("+") or not text[1:].isdigit():
                update.message.reply_text("❌ Номер должен быть в международном формате, например: +79123456789")
                return
                
            # ПРОВЕРКА: зарегистрирован ли номер телефона
            users = load_file(USERS_FILE)
            if text in users:
                update.message.reply_text("❌ Данный номер телефона уже зарегистрирован в системе! Введите другой номер:")
                return
                
            user_states[tg_id]["data"]["phone"] = text
            user_states[tg_id]["state"] = "REG_PASS"
            update.message.reply_text("Придумай пароль для входа в панель бота:")
            
        elif state == "REG_PASS":
            user_states[tg_id]["data"]["password"] = text
            user_states[tg_id]["state"] = "REG_API_ID"
            update.message.reply_text("⚙️ <b>Регистрация профиля успешна!</b>\n\nТеперь настроим юзербота.\nВведите ваш <b>api_id</b> (или напишите 'пропустить'):", parse_mode="HTML")
            
        elif state == "REG_API_ID":
            if is_skip:
                finalize_registration(update, context, skip_ub=True)
            else:
                if not text.isdigit():
                    update.message.reply_text("❌ api_id должен состоять только из цифр:")
                    return
                user_states[tg_id]["data"]["api_id"] = text
                user_states[tg_id]["state"] = "REG_API_HASH"
                update.message.reply_text("✅ api_id принят. Теперь введите ваш <b>api_hash</b>:", parse_mode="HTML")
                
        elif state == "REG_API_HASH":
            user_states[tg_id]["data"]["api_hash"] = text
            u_phone = user_states[tg_id]["data"]["phone"]
            u_dir = get_user_modules_dir(tg_id)
            sess_path = os.path.join(u_dir, u_phone)
            
            update.message.reply_text("⏳ Подключаюсь к серверам Telegram для отправки СМС-кода...")
            
            try:
                asyncio.set_event_loop(global_loop)
                
                client = TelegramClient(sess_path, int(user_states[tg_id]["data"]["api_id"]), user_states[tg_id]["data"]["api_hash"], loop=global_loop)
                global_loop.run_until_complete(client.connect())
                
                send_code_obj = global_loop.run_until_complete(client.send_code_request(u_phone))
                
                user_states[tg_id]["client"] = client
                user_states[tg_id]["phone_code_hash"] = send_code_obj.phone_code_hash
                user_states[tg_id]["state"] = "INPUT_TG_CODE"
                user_states[tg_id]["code_buffer"] = ""
                
                text_kb, markup_kb = get_number_keyboard()
                update.message.reply_text(text_kb, reply_markup=markup_kb, parse_mode="HTML")
                
            except Exception as e:
                update.message.reply_text("❌ Ошибка Telethon: " + str(e) + "\nРегистрация завершена без юзербота.")
                finalize_registration(update, context, skip_ub=True)

        elif state == "INPUT_TG_2FA":
            client = user_states[tg_id]["client"]
            asyncio.set_event_loop(global_loop)
            try:
                if not client.is_connected():
                    global_loop.run_until_complete(client.connect())
                
                global_loop.run_until_complete(client.sign_in(password=text))
                
                update.message.reply_text("✅ Двухфакторный пароль принят! Юзербот успешно запущен.")
                try: global_loop.run_until_complete(client.disconnect())
                except: pass
                
                finalize_registration(update, context, skip_ub=False)
            except PasswordHashInvalidError:
                update.message.reply_text("❌ Неверный облачный пароль! Попробуйте еще раз:")
            except Exception as e:
                update.message.reply_text("❌ Ошибка 2FA: " + str(e))
                try: global_loop.run_until_complete(client.disconnect())
                except: pass
                if tg_id in user_states: del user_states[tg_id]

        elif state == "LOGIN_PHONE":
            users = load_file(USERS_FILE)
            if text not in users:
                update.message.reply_text("❌ Пользователь с таким номером не найден.")
                return
            user_states[tg_id]["data"]["phone"] = text
            user_states[tg_id]["state"] = "LOGIN_PASS"
            update.message.reply_text("🔒 Введи пароль от панели:")
            
        elif state == "LOGIN_PASS":
            p = user_states[tg_id]["data"]["phone"]
            users = load_file(USERS_FILE)
            if p in users and users[p]["password"] == text:
                users[p]["telegram_id"] = tg_id
                save_file(USERS_FILE, users)
                del user_states[tg_id]
                update.message.reply_text("✅ Вход выполнен успешно!")
                show_main_menu(update, context, users[p], is_callback=False)
            else:
                update.message.reply_text("❌ Неверный пароль!")
                
    except Exception as main_err:
        update.message.reply_text("💥 Ошибка: " + str(main_err))

# ===== ПРОВЕРКА КОДА ИЗ КНОПОК =====
def process_tg_code(message, context, tg_id, code):
    client = user_states[tg_id]["client"]
    asyncio.set_event_loop(global_loop)
    
    phone_code_hash = user_states[tg_id]["phone_code_hash"]
    u_phone = user_states[tg_id]["data"]["phone"]
    
    try:
        if not client.is_connected():
            global_loop.run_until_complete(client.connect())
            
        global_loop.run_until_complete(client.sign_in(phone=u_phone, code=code, phone_code_hash=phone_code_hash))
        message.reply_text("✅ Авторизация успешна! Сессия сохранена на сервере.")
        try: global_loop.run_until_complete(client.disconnect())
        except: pass
        
        finalize_registration_by_msg(message, context, tg_id, skip_ub=False)
        
    except SessionPasswordNeededError:
        user_states[tg_id]["state"] = "INPUT_TG_2FA"
        message.reply_text("🔒 Аккаунт защищен двухфакторной аутентификацией.\n\n<b>Введите ваш Облачный Пароль (2FA) обычным текстом в чат:</b>", parse_mode="HTML")
    except PhoneCodeInvalidError:
        user_states[tg_id]["code_buffer"] = "" 
        text_kb, markup_kb = get_number_keyboard()
        message.reply_text("❌ Неверный код! Заново:\n\n" + text_kb, reply_markup=markup_kb, parse_mode="HTML")
    except Exception as e:
        message.reply_text("❌ Ошибка: " + str(e))
        try: global_loop.run_until_complete(client.disconnect())
        except: pass
        if tg_id in user_states: del user_states[tg_id]

# ===== СОХРАНЕНИЕ ДАННЫХ =====
def finalize_registration_by_msg(message, context, tg_id, skip_ub=False):
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
    
    user_data = users[phone]
    del user_states[tg_id]
    message.reply_text("🎉 Профиль сохранен в базе данных хостинга!")
    
    sub = get_sub(tg_id)
    u_dir = get_user_modules_dir(tg_id)
    session_exists = os.path.exists(os.path.join(u_dir, str(phone) + ".session"))
    status_ub = "🟢 Запущен" if session_exists else "🔴 Не авторизован"

    text = (
        "🏠 <b>Панель Управления Юзерботом</b>\n\n"
        "Аккаунт: <code>" + str(user_data['nick']) + "</code>\n"
        "Статус юзербота: <b>" + status_ub + "</b>\n"
        "Тариф: <b>" + str(TIERS[sub['tier']]['name']) + "</b>\n"
        "Доступен до: " + str(sub['expires'][:10])
    )
    keyboard = [
        [InlineKeyboardButton("👤 Профиль", callback_data="menu_profile"), InlineKeyboardButton("⚙️ Модули", callback_data="menu_modules")],
        [InlineKeyboardButton("❌ Отключить юзербота", callback_data="reset_api") if session_exists else InlineKeyboardButton("🚀 Авторизовать / Запустить", callback_data="start_ub_auth")],
        [InlineKeyboardButton("❌ Выйти из панели", callback_data="menu_logout")]
    ]
    message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

def finalize_registration(update: Update, context: CallbackContext, skip_ub=False):
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
    
    user_data = users[phone]
    del user_states[tg_id]
    update.message.reply_text("🎉 Профиль сохранен в базе данных хостинга!")
    
    sub = get_sub(tg_id)
    u_dir = get_user_modules_dir(tg_id)
    session_exists = os.path.exists(os.path.join(u_dir, str(phone) + ".session"))
    status_ub = "🟢 Запущен" if session_exists else "🔴 Не авторизован"

    text = (
        "🏠 <b>Панель Управления Юзерботом</b>\n\n"
        "Аккаунт: <code>" + str(user_data['nick']) + "</code>\n"
        "Статус юзербота: <b>" + status_ub + "</b>\n"
        "Тариф: <b>" + str(TIERS[sub['tier']]['name']) + "</b>\n"
        "Доступен до: " + str(sub['expires'][:10])
    )
    keyboard = [
        [InlineKeyboardButton("👤 Профиль", callback_data="menu_profile"), InlineKeyboardButton("⚙️ Модули", callback_data="menu_modules")],
        [InlineKeyboardButton("❌ Отключить юзербота", callback_data="reset_api") if session_exists else InlineKeyboardButton("🚀 Авторизовать / Запустить", callback_data="start_ub_auth")],
        [InlineKeyboardButton("❌ Выйти из панели", callback_data="menu_logout")]
    ]
    update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

def main():
    os.makedirs(MODULES_DIR, exist_ok=True)
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    
    print("🚀 Бот с валидацией уникальности запущен!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
