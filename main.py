# UserBot | Ru — Системный модуль: Автоответчик
# Канал: @userbotcbet

import asyncio
import json
import os
from telethon import events
from telethon.tl.types import User

# ── Тексты ответов по стилю ────────────────────────────────────────

TEXTS = {
    "official": [
        "Здравствуйте! В данный момент я недоступен. Ваше сообщение будет рассмотрено при первой возможности.",
        "Благодарю за обращение. Сейчас я не могу ответить — свяжусь с вами позднее.",
        "Добрый день. Я временно недоступен, отвечу при первой возможности.",
    ],
    "normal": [
        "Привет! Сейчас не могу ответить, напишу позже 👋",
        "Занят, отвечу чуть позже!",
        "Сейчас не у телефона, отпишу как освобожусь 🙂",
    ],
    "bold": [
        "Отстань, занят 😤",
        "Не мешай, потом отвечу если захочу",
        "Занят. Не трогай.",
    ],
}

# ── Загрузка/сохранение настроек ───────────────────────────────────

def _cfg_path(tg_id: str) -> str:
    data_dir = os.path.join("/app", "data")
    return os.path.join(data_dir, f"autoreply_{tg_id}.json")

def load_cfg(tg_id: str) -> dict:
    path = _cfg_path(tg_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "enabled": False,
        "mode": "all",       # all / contacts / non_contacts
        "style": "normal",   # official / normal / bold
    }

def save_cfg(tg_id: str, cfg: dict):
    path = _cfg_path(tg_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ── Уже отвеченные (чтобы не спамить) ─────────────────────────────
_replied: dict = {}  # {tg_id: set(chat_id)}

def init_telethon(client):

    async def get_tg_id():
        me = await client.get_me()
        return str(me.id)

    @client.on(events.NewMessage(incoming=True))
    async def on_message(event):
        try:
            tg_id = await get_tg_id()
            cfg   = load_cfg(tg_id)

            if not cfg.get("enabled"):
                return

            # Только личные сообщения (не группы/каналы)
            if not event.is_private:
                return

            sender = await event.get_sender()
            if not isinstance(sender, User):
                return
            if sender.bot:
                return

            # Режим: contacts / non_contacts / all
            mode = cfg.get("mode", "all")
            if mode == "contacts" and not sender.contact:
                return
            if mode == "non_contacts" and sender.contact:
                return

            # Не отвечаем дважды одному и тому же в одном чате
            chat_id = event.chat_id
            if tg_id not in _replied:
                _replied[tg_id] = set()
            if chat_id in _replied[tg_id]:
                return
            _replied[tg_id].add(chat_id)

            # Выбираем текст по стилю
            import random
            style   = cfg.get("style", "normal")
            texts   = TEXTS.get(style, TEXTS["normal"])
            reply   = random.choice(texts)

            await event.respond(reply)

        except Exception:
            pass
