"""
Tracking bot (Задачи 4–5): детерминированный user stitching через deep-link Telegram.

Как это работает:
  1. Каждому размещению в реестре выдаётся уникальная ссылка  https://t.me/<bot>?start=<placement_id>
     (payload ≤ 64 символов, [A-Za-z0-9_-]). Ссылка вставляется в рекламный пост / пост своего канала.
  2. Пользователь нажимает → Telegram открывает бота и передаёт payload в /start.
  3. Бот пишет в fact_touch: user_hash = sha256(telegram_user_id + SALT), placement_id, ts, raw_payload
     (персональные данные не сохраняются; username_hash — второй ключ, чтобы стыковаться с student_id из base.xlsx,
      который «формируется из Telegram username и хешируется»).
  4. Бот показывает кнопки курсов (логируем интерес) и кнопку «Написать менеджеру» — ссылку t.me/m/<...>
     c pre-filled текстом «#<placement_id> хочу на <курс>» → менеджер видит источник даже без бота.
  5. Оплата: менеджер (или платёжная система) фиксирует user_hash → fact_order; дальше attribution.py/romi.py.

Если детерминированный стичинг невозможен (пользователь пришёл не по ссылке, а через поиск/репост):
  a) промокод креатива (promo_code_used) — второй детерминированный ключ;
  b) self-reported: кнопки «Откуда узнали?» у бота/менеджера (match_quality = self_reported);
  c) probabilistic: совпадение по времени «вступил в канал по инвайт-ссылке размещения → написал менеджеру»
     в пределах 48 ч (match_quality = probabilistic, вес в атрибуции понижен).

Запуск:
  python src/tracking_bot.py --simulate            # демо без Telegram: пишет 5 событий в pmm.sqlite
  python src/tracking_bot.py --make-links          # печатает deep-link для каждого размещения из реестра
  BOT_TOKEN=... MANAGER_CHAT_ID=... python src/tracking_bot.py   # реальный бот (aiogram 3.x)
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sqlite3
from datetime import datetime

import pandas as pd

from common import PROCESSED, SYNTHETIC

DB = PROCESSED / "pmm.sqlite"
SALT = os.environ.get("PMM_SALT", "postupashki-hackathon-demo-salt")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "PostupashkiTrackBot")
MANAGER_LINK = os.environ.get("MANAGER_LINK", "https://t.me/m/p94YcePXNjcy")  # реальная ссылка из постов канала
PAYLOAD_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
COURSES = ["Аналитика ПРО", "ML ПРО", "AI агенты ПРО", "Backend ПРО", "Алгоритмы ПРО", "СТАРТ (любой)"]

"""
BOT_USERNAME='SQLoutsideindustrybot' \
BOT_TOKEN='8897074854:AAE7Rjlj5rRTc8Wie2FkNhnu_lHMc7qDRAs' \
MANAGER_LINK='https://t.me/kornelikkk' \
MANAGER_CHAT_ID='878623702' \
uv run python src/tracking_bot.py

export BOT_TOKEN='8897074854:AAE7Rjlj5rRTc8Wie2FkNhnu_lHMc7qDRAs'

curl --silent \
  "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates" |
jq '.result[] | {
  username: .message.from.username,
  user_id: .message.from.id,
  chat_id: .message.chat.id,
  text: .message.text
}'

"""

def hash_id(value: str | int) -> str:
    return hashlib.sha256(f"{value}:{SALT}".encode()).hexdigest()[:16]


def parse_start_payload(text: str) -> str | None:
    """'/start p_ext_ds_memes_0904' -> 'p_ext_ds_memes_0904'; невалидный payload -> None."""
    parts = (text or "").split(maxsplit=1)
    if len(parts) < 2:
        return None
    payload = parts[1].strip()
    return payload if PAYLOAD_RE.match(payload) else None


def deep_link(placement_id: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start={placement_id}"


def log_touch(con: sqlite3.Connection, user_hash: str, placement_id: str | None, touch_type: str, raw_payload: str,
              match_quality: str = "deterministic", ts: datetime | None = None) -> None:
    known = con.execute("SELECT 1 FROM dim_placement WHERE placement_id=?", (placement_id,)).fetchone() if placement_id else None
    con.execute(
        "INSERT INTO fact_touch(user_hash, placement_id, touch_type, ts, raw_payload, match_quality, data_origin) VALUES (?,?,?,?,?,?,?)",
        (user_hash, placement_id if known else None, touch_type, (ts or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"), raw_payload, match_quality, "real"),
    )
    con.execute("INSERT OR IGNORE INTO dim_user(user_hash, first_seen_at, first_placement_id, data_origin) VALUES (?,?,?,?)",
                (user_hash, (ts or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"), placement_id if known else None, "real"))
    con.commit()


def log_lead(con: sqlite3.Connection, user_hash: str, placement_id: str | None, interest: str, self_reported: str | None = None) -> None:
    con.execute("INSERT INTO fact_lead(user_hash, ts, source_placement_id, source_self_reported, interest_course, status, data_origin) VALUES (?,?,?,?,?,?,?)",
                (user_hash, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), placement_id, self_reported, interest, "new", "real"))
    con.commit()


def prefilled_manager_link(placement_id: str | None, course: str) -> str:
    # Telegram Business «ссылка на чат» поддерживает несколько ссылок с разным заранее заполненным текстом.
    # В MVP используем одну ссылку + текст, который пользователь отправит менеджеру; код размещения = источник.
    code = placement_id or "organic"
    return f"{MANAGER_LINK}?text=%23{code}%20хочу%20на%20{course}"


# ----------------------------------------------------------------------------- режимы запуска
def simulate() -> None:
    con = sqlite3.connect(DB)
    events = [
        ("111222333", "/start p_own_1880", "bot_start"),
        ("111222333", "interest:Аналитика ПРО", "interest"),
        ("444555666", "/start p_ext_ds_memes_0904", "bot_start"),
        ("777888999", "/start", "bot_start"),               # без payload → источник неизвестен
        ("777888999", "self_reported:YouTube", "self_reported"),
    ]
    last_placement: dict[str, str | None] = {}
    for tg_user_id, text, kind in events:
        uh = hash_id(tg_user_id)
        if kind == "bot_start":
            pid = parse_start_payload(text)
            last_placement[uh] = pid
            log_touch(con, uh, pid, "bot_start", text, "deterministic" if pid else "self_reported")
            print(f"[touch] user={uh} placement={pid} link_for_manager={prefilled_manager_link(pid, 'курс')}")
        elif kind == "interest":
            log_lead(con, uh, last_placement.get(uh), text.split(':', 1)[1])
            print(f"[lead]  user={uh} interest={text.split(':', 1)[1]} source={last_placement.get(uh)}")
        elif kind == "self_reported":
            log_lead(con, uh, None, "unknown", self_reported=text.split(':', 1)[1])
            print(f"[lead]  user={uh} self_reported_source={text.split(':', 1)[1]} (match_quality=self_reported)")
    n = con.execute("SELECT COUNT(*) FROM fact_touch WHERE data_origin='real'").fetchone()[0]
    print(f"real touches in mart now: {n}")
    con.close()


def make_links() -> None:
    reg = pd.read_csv(SYNTHETIC / "ad_registry.csv")
    for r in reg.itertuples(index=False):
        print(f"{r.placement_id:26s} {r.channel_id:22s} {deep_link(r.placement_id)}")


def run_bot() -> None:  # pragma: no cover — требует токен и сеть
    import asyncio

    from aiogram import Bot, Dispatcher, F
    from aiogram.filters import CommandStart
    from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

    token = os.environ["BOT_TOKEN"]
    manager_chat = os.environ.get("MANAGER_CHAT_ID")
    con = sqlite3.connect(DB)
    bot, dp = Bot(token), Dispatcher()
    last_placement: dict[str, str | None] = {}

    def kb(pid: str | None) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text=c, callback_data=f"course:{c}")] for c in COURSES]
        rows.append([InlineKeyboardButton(text="Написать менеджеру", url=prefilled_manager_link(pid, "курс"))])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    @dp.message(CommandStart())
    async def on_start(m: Message) -> None:
        pid = parse_start_payload(m.text or "")
        uh = hash_id(m.from_user.id)
        last_placement[uh] = pid
        log_touch(con, uh, pid, "bot_start", m.text or "", "deterministic" if pid else "self_reported")
        await m.answer("Привет! Какой курс интересует? Выберите — и менеджер ответит на вопросы.", reply_markup=kb(pid))
        if not pid:
            src_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=s, callback_data=f"src:{s}")]
                                                           for s in ["Наш канал", "Другой Telegram-канал", "YouTube", "Друзья", "Поиск"]])
            await m.answer("Откуда вы о нас узнали?", reply_markup=src_kb)

    @dp.callback_query(F.data.startswith("course:"))
    async def on_course(cq: CallbackQuery) -> None:
        uh = hash_id(cq.from_user.id)
        course = cq.data.split(":", 1)[1]
        pid = last_placement.get(uh)
        log_lead(con, uh, pid, course)
        if manager_chat:
            await bot.send_message(manager_chat, f"Лид #{uh} · интерес: {course} · источник: {pid or 'неизвестен'}")
        await cq.message.answer(f"Записал интерес к «{course}». Нажмите «Написать менеджеру» — код источника подставится автоматически.",
                                reply_markup=kb(pid))
        await cq.answer()

    @dp.callback_query(F.data.startswith("src:"))
    async def on_src(cq: CallbackQuery) -> None:
        uh = hash_id(cq.from_user.id)
        log_lead(con, uh, None, "unknown", self_reported=cq.data.split(":", 1)[1])
        await cq.answer("Спасибо!")

    asyncio.run(dp.start_polling(bot))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument("--make-links", action="store_true")
    args = ap.parse_args()
    if args.simulate:
        simulate()
    elif args.make_links:
        make_links()
    else:
        run_bot()


if __name__ == "__main__":
    main()
