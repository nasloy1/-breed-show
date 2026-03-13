"""
Breed Show – Telegram Mini App backend
Runs TWO bots (cats + dogs) concurrently via python-telegram-bot + aiohttp.
Deploy to Railway. Frontend on GitHub Pages.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
import urllib.parse
from typing import Optional

from aiohttp import web
from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("breed_show")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MINI_APP_URL = os.getenv("MINI_APP_URL", "https://breed.show/tg")
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("DB_PATH", "breed_show.db")
PUBLIC_URL = os.getenv("PUBLIC_URL", "")
SKIP_INITDATA_CHECK = os.getenv("SKIP_INITDATA_CHECK", "false").lower() == "true"

BOT_TOKEN_CATS = os.getenv("BOT_TOKEN_CATS", "")
BOT_TOKEN_DOGS = os.getenv("BOT_TOKEN_DOGS", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_MODE = os.getenv("BOT_MODE", "cats")

BOT_USERNAME_CATS = os.getenv("BOT_USERNAME_CATS", "kittens_buy_bot")
BOT_USERNAME_DOGS = os.getenv("BOT_USERNAME_DOGS", "puppies_buy_bot")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_SESSIONS: dict[str, float] = {}  # token -> expires_at
SESSION_DURATION = 86400  # 24 hours

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-TG-InitData",
}

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

SEED_CATS = [
    {
        "id": "1", "name": "Барсик", "breed": "Британская короткошёрстная", "mode": "cats",
        "age_months": 3, "gender": "male", "price": 35000, "color": "голубой",
        "description": "Ласковый котёнок с отличной родословной. Привит, обработан от паразитов. Мама и папа — чемпионы выставок.",
        "image": "https://images.unsplash.com/photo-1571566882372-1598d88abd90?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/breeder_british",
        "phone": "+7 916 123-45-67", "email": "british@example.com",
        "is_promoted": 1, "has_kennel_landing": 1,
        "kennel_name": "Питомник «Серебряный Туман»", "kennel_id": "silver_mist",
    },
    {
        "id": "2", "name": "Луна", "breed": "Шотландская вислоухая", "mode": "cats",
        "age_months": 5, "gender": "female", "price": 45000, "color": "белый",
        "description": "Нежная кошечка с выразительными глазами. Документы, ветпаспорт, две прививки.",
        "image": "https://images.unsplash.com/photo-1503431153839-4c9b977c9f1a?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/scottish_fold_kennel",
        "phone": "+7 926 234-56-78", "email": "luna@example.com",
        "is_promoted": 0, "has_kennel_landing": 1,
        "kennel_name": "Питомник «Лунный Свет»", "kennel_id": "moonlight",
    },
    {
        "id": "3", "name": "Симба", "breed": "Мейн-кун", "mode": "cats",
        "age_months": 4, "gender": "male", "price": 60000, "color": "табби коричневый",
        "description": "Крупный котёнок породы мейн-кун. Отличный темперамент, игривый и ласковый. Родословная WCF.",
        "image": "https://images.unsplash.com/photo-1615789591457-74a63395c990?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/maincoon_rus",
        "phone": "+7 903 345-67-89", "email": "simba@example.com",
        "is_promoted": 1, "has_kennel_landing": 1,
        "kennel_name": "Питомник «Лесной Король»", "kennel_id": "forest_king",
    },
    {
        "id": "4", "name": "Снежинка", "breed": "Турецкая ангора", "mode": "cats",
        "age_months": 6, "gender": "female", "price": 28000, "color": "белый",
        "description": "Белоснежная красавица с голубыми глазами. Привита, стерилизована не будет до 1 года.",
        "image": "https://images.unsplash.com/photo-1596854407944-bf87f6fdd49e?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/angora_breeder",
        "phone": "+7 911 456-78-90", "email": "angora@example.com",
        "is_promoted": 0, "has_kennel_landing": 0,
        "kennel_name": "", "kennel_id": "",
    },
    {
        "id": "5", "name": "Рыжик", "breed": "Персидская", "mode": "cats",
        "age_months": 2, "gender": "male", "price": 40000, "color": "рыжий",
        "description": "Персидский котёнок с роскошной шерстью. Очень ласковый, любит объятия. Полный пакет документов.",
        "image": "https://images.unsplash.com/photo-1543852786-1cf6624b9987?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/persian_cats_msk",
        "phone": "+7 985 567-89-01", "email": "persian@example.com",
        "is_promoted": 0, "has_kennel_landing": 1,
        "kennel_name": "Питомник «Персия»", "kennel_id": "persia",
    },
    {
        "id": "6", "name": "Мурка", "breed": "Сибирская", "mode": "cats",
        "age_months": 8, "gender": "female", "price": 22000, "color": "чёрно-белый",
        "description": "Сибирская кошка с мощным телосложением. Гипоаллергенная порода. Готова к переезду.",
        "image": "https://images.unsplash.com/photo-1529778873920-4da4926a72c2?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/siberian_cats",
        "phone": "", "email": "siberian@example.com",
        "is_promoted": 0, "has_kennel_landing": 0,
        "kennel_name": "", "kennel_id": "",
    },
    {
        "id": "7", "name": "Граф", "breed": "Бенгальская", "mode": "cats",
        "age_months": 3, "gender": "male", "price": 75000, "color": "пятнистый",
        "description": "Экзотический бенгальский котёнок. Дикий окрас, ласковый характер. Документы TICA.",
        "image": "https://images.unsplash.com/photo-1548247416-ec66f4900b2e?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/bengal_pride",
        "phone": "+7 916 678-90-12", "email": "bengal@example.com",
        "is_promoted": 1, "has_kennel_landing": 1,
        "kennel_name": "Питомник «Бенгальский Тигр»", "kennel_id": "bengal_tiger",
    },
    {
        "id": "8", "name": "Дина", "breed": "Абиссинская", "mode": "cats",
        "age_months": 5, "gender": "female", "price": 38000, "color": "нутовый",
        "description": "Активная и игривая абиссинская кошечка. Любит высоту и приключения. Привита по возрасту.",
        "image": "https://images.unsplash.com/photo-1586183189334-1e3e85e63ebe?w=600&q=80",
        "available": 0, "telegram_url": "https://t.me/abyssinian_rus",
        "phone": "+7 926 789-01-23", "email": "",
        "is_promoted": 0, "has_kennel_landing": 0,
        "kennel_name": "", "kennel_id": "",
    },
    {
        "id": "9", "name": "Принц", "breed": "Регдолл", "mode": "cats",
        "age_months": 4, "gender": "male", "price": 55000, "color": "колорпойнт",
        "description": "Огромный ласковый регдолл. Обожает находиться на руках. Документы, прививки, чип.",
        "image": "https://images.unsplash.com/photo-1555685812-4b943f1cb0eb?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/ragdoll_moscou",
        "phone": "+7 903 890-12-34", "email": "ragdoll@example.com",
        "is_promoted": 0, "has_kennel_landing": 1,
        "kennel_name": "Питомник «Пушистый Принц»", "kennel_id": "fluffy_prince",
    },
    {
        "id": "10", "name": "Тося", "breed": "Норвежская лесная", "mode": "cats",
        "age_months": 7, "gender": "female", "price": 32000, "color": "табби",
        "description": "Пышная норвежская лесная кошечка. Выносливая, независимая, красивая. Документы NFF.",
        "image": "https://images.unsplash.com/photo-1601979031925-424e53b6caaa?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/norwegian_forest",
        "phone": "+7 911 901-23-45", "email": "norwegian@example.com",
        "is_promoted": 0, "has_kennel_landing": 0,
        "kennel_name": "", "kennel_id": "",
    },
    {
        "id": "11", "name": "Лео", "breed": "Экзотическая короткошёрстная", "mode": "cats",
        "age_months": 3, "gender": "male", "price": 48000, "color": "кремовый",
        "description": "Плюшевый экзот с плоской мордочкой. Спокойный и уравновешенный. Документы CFA.",
        "image": "https://images.unsplash.com/photo-1570824104453-508955ab713e?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/exotic_cats_spb",
        "phone": "+7 985 012-34-56", "email": "exotic@example.com",
        "is_promoted": 1, "has_kennel_landing": 0,
        "kennel_name": "", "kennel_id": "",
    },
    {
        "id": "12", "name": "Жемчуг", "breed": "Бирманская", "mode": "cats",
        "age_months": 6, "gender": "female", "price": 42000, "color": "сил-пойнт",
        "description": "Священная Бирма с изысканной внешностью. Шелковистая шерсть, голубые глаза. Полная документация.",
        "image": "https://images.unsplash.com/photo-1478098711619-5ab0b478d6e6?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/birman_sacred",
        "phone": "+7 916 123-45-00", "email": "birman@example.com",
        "is_promoted": 0, "has_kennel_landing": 1,
        "kennel_name": "Питомник «Священная Бирма»", "kennel_id": "sacred_birma",
    },
]

SEED_DOGS = [
    {
        "id": "101", "name": "Буря", "breed": "Хаски", "mode": "dogs",
        "age_months": 4, "gender": "male", "price": 50000, "color": "чёрно-белый",
        "description": "Энергичный щенок сибирского хаски. Голубые глаза, красивый окрас. Документы РКФ, прививки.",
        "image": "https://images.unsplash.com/photo-1605568427561-40dd23c2acea?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/husky_kennel_ru",
        "phone": "+7 916 111-22-33", "email": "husky@example.com",
        "is_promoted": 1, "has_kennel_landing": 1,
        "kennel_name": "Питомник «Северный Ветер»", "kennel_id": "north_wind",
    },
    {
        "id": "102", "name": "Кнопка", "breed": "Французский бульдог", "mode": "dogs",
        "age_months": 3, "gender": "female", "price": 65000, "color": "кремовый",
        "description": "Очаровательный щенок французского бульдога. Игривая, здоровая, привита. Документы РКФ.",
        "image": "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/french_bulldog_msk",
        "phone": "+7 926 222-33-44", "email": "bulldog@example.com",
        "is_promoted": 1, "has_kennel_landing": 1,
        "kennel_name": "Питомник «Пти Шарм»", "kennel_id": "petit_charme",
    },
    {
        "id": "103", "name": "Арес", "breed": "Немецкая овчарка", "mode": "dogs",
        "age_months": 5, "gender": "male", "price": 35000, "color": "чепрачный",
        "description": "Щенок немецкой овчарки из рабочей линии. Умный, обучаемый. Родословная FCI.",
        "image": "https://images.unsplash.com/photo-1589941013453-ec89f33b5e95?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/gsd_working",
        "phone": "+7 903 333-44-55", "email": "gsd@example.com",
        "is_promoted": 0, "has_kennel_landing": 1,
        "kennel_name": "Питомник «Арийский Страж»", "kennel_id": "aryan_guard",
    },
    {
        "id": "104", "name": "Нала", "breed": "Лабрадор-ретривер", "mode": "dogs",
        "age_months": 6, "gender": "female", "price": 30000, "color": "золотистый",
        "description": "Дружелюбная лабрадорша. Идеальный семейный питомец. Документы, прививки, здоровые родители.",
        "image": "https://images.unsplash.com/photo-1591160690555-5debfba289f0?w=600&q=80",
        "available": 1, "telegram_url": "https://t.me/labrador_family",
        "phone": "+7 911 444-55-66", "email": "labrador@example.com",
        "is_promoted": 0, "has_kennel_landing": 0,
        "kennel_name": "", "kennel_id": "",
    },
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS pets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            breed TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'cats',
            age_months INTEGER NOT NULL DEFAULT 0,
            gender TEXT NOT NULL DEFAULT 'male',
            price INTEGER NOT NULL DEFAULT 0,
            color TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            image TEXT NOT NULL DEFAULT '',
            available INTEGER NOT NULL DEFAULT 1,
            telegram_url TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            is_promoted INTEGER NOT NULL DEFAULT 0,
            has_kennel_landing INTEGER NOT NULL DEFAULT 0,
            kennel_name TEXT NOT NULL DEFAULT '',
            kennel_id TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS tg_favorites (
            tg_user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(tg_user_id, pet_id)
        );

        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            pet_id TEXT,
            kennel_id TEXT,
            tg_user_id TEXT,
            extra TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'cats',
            breed TEXT,
            label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS notification_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id TEXT NOT NULL,
            pet_id TEXT NOT NULL,
            sent_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(tg_user_id, pet_id)
        );
    """)
    conn.commit()

    # Migrations: add new columns if they don't exist yet
    for col, definition in [
        ("show_to_subscribers", "INTEGER NOT NULL DEFAULT 0"),
        ("created_at", "TEXT NOT NULL DEFAULT (datetime('now'))"),
    ]:
        try:
            conn.execute(f"ALTER TABLE pets ADD COLUMN {col} {definition}")
            conn.commit()
        except Exception:
            pass  # column already exists

    count = cur.execute("SELECT COUNT(*) FROM pets").fetchone()[0]
    if count == 0:
        all_pets = SEED_CATS + SEED_DOGS
        for pet in all_pets:
            cur.execute(
                """
                INSERT OR IGNORE INTO pets
                (id, name, breed, mode, age_months, gender, price, color, description,
                 image, available, telegram_url, phone, email,
                 is_promoted, has_kennel_landing, kennel_name, kennel_id)
                VALUES
                (:id, :name, :breed, :mode, :age_months, :gender, :price, :color, :description,
                 :image, :available, :telegram_url, :phone, :email,
                 :is_promoted, :has_kennel_landing, :kennel_name, :kennel_id)
                """,
                pet,
            )
        conn.commit()
        logger.info("Seeded %d pets", len(all_pets))

    conn.close()


def row_to_dict(row) -> dict:
    d = dict(row)
    d["available"] = bool(d.get("available", 1))
    d["is_promoted"] = bool(d.get("is_promoted", 0))
    d["has_kennel_landing"] = bool(d.get("has_kennel_landing", 0))
    d["show_to_subscribers"] = bool(d.get("show_to_subscribers", 0))
    return d


# ---------------------------------------------------------------------------
# initData validation
# ---------------------------------------------------------------------------

def validate_init_data(init_data_raw: str, bot_token: str) -> Optional[dict]:
    """
    Validate Telegram WebApp initData using HMAC-SHA256.
    Returns user dict {id, first_name, ...} or None if invalid.
    secret_key = HMAC-SHA256('WebAppData', bot_token)
    data_check_string = sorted key=value pairs joined by newlines (hash excluded)
    """
    if not init_data_raw or not bot_token:
        return None
    try:
        parsed = urllib.parse.parse_qs(init_data_raw, keep_blank_values=True)
        hash_from_data = parsed.get("hash", [None])[0]
        if not hash_from_data:
            return None

        pairs = []
        for key, values in parsed.items():
            if key == "hash":
                continue
            pairs.append(f"{key}={values[0]}")
        pairs.sort()
        data_check_string = "\n".join(pairs)

        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_hash, hash_from_data):
            return None

        if not SKIP_INITDATA_CHECK:
            auth_date_str = parsed.get("auth_date", [None])[0]
            if auth_date_str:
                auth_date = int(auth_date_str)
                if time.time() - auth_date > 86400:
                    logger.warning("initData expired (auth_date too old)")
                    return None

        user_str = parsed.get("user", [None])[0]
        if user_str:
            return json.loads(user_str)
        return {"id": 0}
    except Exception as exc:
        logger.warning("validate_init_data error: %s", exc)
        return None


def extract_user_id_from_init_data(init_data_raw: str) -> Optional[int]:
    """Extract user id from initData without cryptographic verification (dev mode)."""
    if not init_data_raw:
        return None
    try:
        parsed = urllib.parse.parse_qs(init_data_raw, keep_blank_values=True)
        user_str = parsed.get("user", [None])[0]
        if user_str:
            user = json.loads(user_str)
            return user.get("id")
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Auth middleware helper
# ---------------------------------------------------------------------------

async def get_tg_user_id(request: web.Request) -> Optional[int]:
    """
    Extract and validate tg_user_id from X-TG-InitData header.
    Returns user_id int or None (caller should return 401).
    """
    init_data_raw = request.headers.get("X-TG-InitData", "")

    if SKIP_INITDATA_CHECK:
        if not init_data_raw:
            return 0  # dev fallback: anonymous user
        uid = extract_user_id_from_init_data(init_data_raw)
        return uid if uid is not None else 0

    # Try all configured tokens
    tokens: list[str] = []
    if BOT_TOKEN_CATS:
        tokens.append(BOT_TOKEN_CATS)
    if BOT_TOKEN_DOGS:
        tokens.append(BOT_TOKEN_DOGS)
    if BOT_TOKEN:
        tokens.append(BOT_TOKEN)

    for token in tokens:
        user = validate_init_data(init_data_raw, token)
        if user is not None:
            return int(user.get("id", 0))

    return None


# ---------------------------------------------------------------------------
# HTTP response helper
# ---------------------------------------------------------------------------

def json_response(data, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        status=status,
        content_type="application/json",
        headers=CORS_HEADERS,
    )


# ---------------------------------------------------------------------------
# HTTP handlers
# ---------------------------------------------------------------------------

async def handle_health(request: web.Request) -> web.Response:
    return json_response({"ok": True})


async def handle_options(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=CORS_HEADERS)


async def handle_analytics_event(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return json_response({"ok": False, "error": "invalid json"}, status=400)

    event = str(body.get("event", ""))[:64]
    if not event:
        return json_response({"ok": False, "error": "event required"}, status=400)

    pet_id = str(body.get("pet_id", ""))[:64] or None
    kennel_id = str(body.get("kennel_id", ""))[:64] or None
    tg_user_id = str(body.get("tg_user_id", ""))[:64] or None
    extra = json.dumps(body.get("extra")) if body.get("extra") else None

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO analytics_events (event, pet_id, kennel_id, tg_user_id, extra) VALUES (?,?,?,?,?)",
        (event, pet_id, kennel_id, tg_user_id, extra),
    )
    conn.commit()
    conn.close()

    logger.info("analytics: %s pet=%s kennel=%s user=%s", event, pet_id, kennel_id, tg_user_id)
    return json_response({"ok": True})


async def handle_config(request: web.Request) -> web.Response:
    cats_username = BOT_USERNAME_CATS or "kittens_buy_bot"
    dogs_username = BOT_USERNAME_DOGS or "puppies_buy_bot"
    config = {
        "bots": {
            "kittens_bot_username": cats_username,
            "puppies_bot_username": dogs_username,
            "kittens_bot_url": f"https://t.me/{cats_username}",
            "puppies_bot_url": f"https://t.me/{dogs_username}",
        },
        "links": {
            "add_for_sale_url_template": (
                "https://breed.show/add"
                "?utm_source=telegram&utm_medium=miniapp&utm_campaign={mode}"
            ),
        },
    }
    return json_response(config)


async def handle_pets(request: web.Request) -> web.Response:
    q = request.rel_url.query

    mode = q.get("mode", "")
    breed = q.get("breed", "")
    gender = q.get("gender", "")
    available_only = q.get("available_only", "").lower() in ("1", "true", "yes")

    def safe_int(val: str, default: int = 0) -> int:
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    min_price = safe_int(q.get("min_price", "0"))
    max_price = safe_int(q.get("max_price", "0"))
    min_age = safe_int(q.get("min_age", "0"))
    max_age = safe_int(q.get("max_age", "0"))

    conditions: list[str] = []
    params: list = []

    if mode in ("cats", "dogs"):
        conditions.append("mode = ?")
        params.append(mode)

    if breed:
        conditions.append("LOWER(breed) LIKE ?")
        params.append(f"%{breed.lower()}%")

    if gender in ("male", "female"):
        conditions.append("gender = ?")
        params.append(gender)

    if available_only:
        conditions.append("available = 1")

    if min_price > 0:
        conditions.append("price >= ?")
        params.append(min_price)

    if max_price > 0:
        conditions.append("price <= ?")
        params.append(max_price)

    if min_age > 0:
        conditions.append("age_months >= ?")
        params.append(min_age)

    if max_age > 0:
        conditions.append("age_months <= ?")
        params.append(max_age)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"SELECT * FROM pets {where} ORDER BY is_promoted DESC, id ASC"

    conn = get_db()
    try:
        rows = conn.execute(sql, params).fetchall()
        pets = [row_to_dict(r) for r in rows]
    finally:
        conn.close()

    return json_response(pets)


async def handle_pet_by_id(request: web.Request) -> web.Response:
    pet_id = request.match_info["id"]
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM pets WHERE id = ?", (pet_id,)).fetchone()
    finally:
        conn.close()

    if row is None:
        return json_response({"error": "Not found"}, status=404)

    return json_response(row_to_dict(row))


async def handle_get_favorites(request: web.Request) -> web.Response:
    user_id = await get_tg_user_id(request)
    if user_id is None:
        return json_response({"error": "Unauthorized"}, status=401)

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT pet_id FROM tg_favorites WHERE tg_user_id = ? ORDER BY created_at DESC",
            (str(user_id),),
        ).fetchall()
        pet_ids = [r["pet_id"] for r in rows]
    finally:
        conn.close()

    return json_response({"pet_ids": pet_ids})


async def handle_add_favorite(request: web.Request) -> web.Response:
    user_id = await get_tg_user_id(request)
    if user_id is None:
        return json_response({"error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
        pet_id = str(body.get("pet_id", "")).strip()
    except Exception:
        return json_response({"error": "Invalid JSON body"}, status=400)

    if not pet_id:
        return json_response({"error": "pet_id is required"}, status=400)

    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO tg_favorites (tg_user_id, pet_id) VALUES (?, ?)",
            (str(user_id), pet_id),
        )
        conn.commit()
    finally:
        conn.close()

    return json_response({"ok": True})


async def handle_delete_favorite(request: web.Request) -> web.Response:
    user_id = await get_tg_user_id(request)
    if user_id is None:
        return json_response({"error": "Unauthorized"}, status=401)

    pet_id = request.match_info["pet_id"]

    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM tg_favorites WHERE tg_user_id = ? AND pet_id = ?",
            (str(user_id), pet_id),
        )
        conn.commit()
    finally:
        conn.close()

    return json_response({"ok": True})


# ---------------------------------------------------------------------------
# Telegram bot handlers
# ---------------------------------------------------------------------------

def make_start_handler(bot_mode: str):
    async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        first_name = (user.first_name or "") if user else ""

        args = context.args or []
        arg = args[0] if args else ""

        if arg.startswith("pet_"):
            pet_id = arg[4:]
            url = f"{MINI_APP_URL}?mode={bot_mode}&pet_id={pet_id}"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Открыть карточку →", web_app=WebAppInfo(url=url))]
            ])
            await update.message.reply_text(
                "Открыть карточку питомца:",
                reply_markup=keyboard,
            )
        else:
            url = f"{MINI_APP_URL}?mode={bot_mode}"
            btn_label = "🐱 Смотреть котят" if bot_mode == "cats" else "🐶 Смотреть щенков"

            greeting = f"Привет{', ' + first_name if first_name else ''}! 👋\n\n"
            if bot_mode == "cats":
                text = (
                    greeting
                    + "Добро пожаловать в Breed Show — маркетплейс котят от проверенных заводчиков.\n\n"
                    "Нажмите кнопку ниже, чтобы посмотреть котят:"
                )
            else:
                text = (
                    greeting
                    + "Добро пожаловать в Breed Show — маркетплейс щенков от проверенных заводчиков.\n\n"
                    "Нажмите кнопку ниже, чтобы посмотреть щенков:"
                )

            share_text = urllib.parse.quote("Смотрите питомцев на Breed Show!")
            share_url = f"https://t.me/share/url?url={urllib.parse.quote(url)}&text={share_text}"

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(btn_label, web_app=WebAppInfo(url=url))],
                [InlineKeyboardButton("📢 Поделиться", url=share_url)],
            ])
            await update.message.reply_text(text, reply_markup=keyboard)

    return start_handler


def make_unknown_handler(bot_mode: str):
    async def unknown_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "Я умею только открывать каталог 😊\n\n"
            "Используйте команду /start чтобы перейти в приложение.\n\n"
            "По вопросам пишите: @breed_show_support"
        )

    return unknown_handler


# ---------------------------------------------------------------------------
# Build Telegram Application
# ---------------------------------------------------------------------------

def build_application(token: str, bot_mode: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", make_start_handler(bot_mode)))
    app.add_handler(MessageHandler(filters.ALL, make_unknown_handler(bot_mode)))
    return app


# ---------------------------------------------------------------------------
# Subscription API handlers
# ---------------------------------------------------------------------------

async def handle_get_subscriptions(request: web.Request) -> web.Response:
    user_id = await get_tg_user_id(request)
    if user_id is None:
        return json_response({"error": "unauthorized"}, status=401)
    conn = get_db()
    rows = conn.execute(
        "SELECT id, mode, breed, label, created_at FROM subscriptions WHERE tg_user_id=? ORDER BY id DESC",
        (str(user_id),),
    ).fetchall()
    conn.close()
    return json_response([dict(r) for r in rows])


async def handle_create_subscription(request: web.Request) -> web.Response:
    user_id = await get_tg_user_id(request)
    if user_id is None:
        return json_response({"error": "unauthorized"}, status=401)
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "invalid json"}, status=400)

    mode = body.get("mode", "cats")
    breed = (body.get("breed") or "").strip() or None
    label = (body.get("label") or "").strip()[:128]
    if not label:
        label = f"Новые {'котята' if mode == 'cats' else 'щенки'}" + (f" · {breed}" if breed else "")

    conn = get_db()
    # Prevent duplicates for same user+mode+breed
    existing = conn.execute(
        "SELECT id FROM subscriptions WHERE tg_user_id=? AND mode=? AND (breed=? OR (breed IS NULL AND ? IS NULL))",
        (str(user_id), mode, breed, breed),
    ).fetchone()
    if existing:
        conn.close()
        return json_response({"id": existing["id"], "already_exists": True})

    cur = conn.execute(
        "INSERT INTO subscriptions (tg_user_id, mode, breed, label) VALUES (?,?,?,?)",
        (str(user_id), mode, breed, label),
    )
    conn.commit()
    sub_id = cur.lastrowid
    conn.close()
    return json_response({"id": sub_id, "label": label})


async def handle_delete_subscription(request: web.Request) -> web.Response:
    user_id = await get_tg_user_id(request)
    if user_id is None:
        return json_response({"error": "unauthorized"}, status=401)
    sub_id = request.match_info["id"]
    conn = get_db()
    conn.execute("DELETE FROM subscriptions WHERE id=? AND tg_user_id=?", (sub_id, str(user_id)))
    conn.commit()
    conn.close()
    return json_response({"ok": True})


async def handle_demand_breeds(request: web.Request) -> web.Response:
    mode = request.rel_url.query.get("mode", "")
    conn = get_db()
    if mode:
        rows = conn.execute(
            """SELECT breed, COUNT(*) as count FROM subscriptions
               WHERE mode=? AND breed IS NOT NULL
               GROUP BY breed ORDER BY count DESC LIMIT 50""",
            (mode,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT breed, mode, COUNT(*) as count FROM subscriptions
               WHERE breed IS NOT NULL
               GROUP BY breed, mode ORDER BY count DESC LIMIT 50"""
        ).fetchall()
    conn.close()
    return json_response([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------

async def send_pet_notification(bot, tg_user_id: str, pet: dict) -> None:
    mode = pet.get("mode", "cats")
    age = pet.get("age_months", 0)
    price = pet.get("price", 0)
    price_str = f"{price:,}".replace(",", "\u00a0") + "\u00a0₽" if price else ""

    text = (
        f"🔔 <b>Новый питомец по вашей подписке!</b>\n\n"
        f"<b>{pet.get('name', '')}</b> — {pet.get('breed', '')}\n"
        f"{age}\u00a0мес.{f'  ·  {price_str}' if price_str else ''}\n"
    )
    if pet.get("color"):
        text += f"Окрас: {pet['color']}\n"

    pet_id = pet.get("id", "")
    mini_app_url = MINI_APP_URL.rstrip("/")
    url = f"{mini_app_url}?mode={mode}&pet_id={pet_id}"

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Смотреть →", web_app=WebAppInfo(url=url))]
    ])

    if pet.get("image"):
        await bot.send_photo(
            chat_id=int(tg_user_id),
            photo=pet["image"],
            caption=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    else:
        await bot.send_message(
            chat_id=int(tg_user_id),
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )


async def notify_subscribers_for_pet(pet: dict, tg_apps: list) -> None:
    if not tg_apps:
        return
    pet_id = str(pet.get("id", ""))
    mode = pet.get("mode", "cats")
    breed = (pet.get("breed") or "").lower()

    # Pick the right bot for this mode
    bot = None
    for app in tg_apps:
        app_mode = "cats" if BOT_TOKEN_CATS and app.bot.token == BOT_TOKEN_CATS else "dogs"
        if app_mode == mode:
            bot = app.bot
            break
    if not bot:
        bot = tg_apps[0].bot  # fallback

    conn = get_db()
    subs = conn.execute(
        "SELECT id, tg_user_id, breed FROM subscriptions WHERE mode=?",
        (mode,),
    ).fetchall()

    for sub in subs:
        # Match breed filter
        sub_breed = (sub["breed"] or "").lower()
        if sub_breed and sub_breed not in breed and breed not in sub_breed:
            continue

        uid = sub["tg_user_id"]
        # Check dedup
        already = conn.execute(
            "SELECT 1 FROM notification_log WHERE tg_user_id=? AND pet_id=?",
            (uid, pet_id),
        ).fetchone()
        if already:
            continue

        try:
            await send_pet_notification(bot, uid, pet)
            conn.execute(
                "INSERT OR IGNORE INTO notification_log (tg_user_id, pet_id) VALUES (?,?)",
                (uid, pet_id),
            )
            conn.commit()
            logger.info("Notified user %s about pet %s", uid, pet_id)
        except Exception as e:
            logger.warning("Failed to notify user %s: %s", uid, e)

    conn.close()


# ---------------------------------------------------------------------------
# Admin panel helpers
# ---------------------------------------------------------------------------

def _admin_check(request: web.Request) -> bool:
    token = request.cookies.get("admin_session")
    if not token:
        return False
    expires = ADMIN_SESSIONS.get(token, 0)
    if time.time() > expires:
        ADMIN_SESSIONS.pop(token, None)
        return False
    return True


_ADMIN_CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f0f4fa;margin:0;color:#1a1d23}
.topbar{background:#1a5fa8;color:#fff;padding:12px 24px;display:flex;align-items:center;justify-content:space-between}
.topbar h1{margin:0;font-size:1.1rem}
.topbar a{color:#fff;opacity:.8;text-decoration:none;font-size:.9rem}
.topbar a:hover{opacity:1}
.container{max-width:1100px;margin:0 auto;padding:24px}
.card{background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(26,95,168,.09);padding:24px;margin-bottom:20px}
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 18px;border-radius:8px;font-size:.9rem;font-weight:600;border:none;cursor:pointer;text-decoration:none;transition:opacity .15s}
.btn:active{opacity:.8}
.btn-primary{background:#1a5fa8;color:#fff}
.btn-success{background:#1c8a4e;color:#fff}
.btn-danger{background:#c0392b;color:#fff}
.btn-outline{background:transparent;color:#1a5fa8;border:1.5px solid #1a5fa8}
.btn-sm{padding:5px 12px;font-size:.8rem}
table{width:100%;border-collapse:collapse}
th{text-align:left;padding:10px 12px;background:#f7f9fc;font-size:.78rem;text-transform:uppercase;letter-spacing:.05em;color:#5a6375;border-bottom:1.5px solid #dde4ee}
td{padding:10px 12px;border-bottom:1px solid #f0f4fa;font-size:.88rem;vertical-align:middle}
tr:hover td{background:#f7f9fc}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.72rem;font-weight:700}
.badge-cats{background:#e8f4fd;color:#1a5fa8}
.badge-dogs{background:#fef3e2;color:#e85c00}
.badge-on{background:#d4f0e1;color:#1c8a4e}
.badge-off{background:#fde8e8;color:#c0392b}
.badge-promo{background:rgba(232,92,0,.12);color:#e85c00}
.form-group{margin-bottom:16px}
label{display:block;font-size:.82rem;font-weight:600;color:#5a6375;margin-bottom:6px}
input[type=text],input[type=number],input[type=url],input[type=email],textarea,select{width:100%;padding:10px 12px;border:1.5px solid #dde4ee;border-radius:8px;font:inherit;font-size:.92rem;outline:none;box-sizing:border-box}
input:focus,textarea:focus,select:focus{border-color:#1a5fa8}
textarea{min-height:80px;resize:vertical}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.form-row-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}
.checkbox-row{display:flex;align-items:center;gap:10px}
.checkbox-row input{width:auto}
.img-preview{width:100%;max-height:200px;object-fit:cover;border-radius:8px;margin-top:8px;display:none}
.upload-btn{display:inline-flex;align-items:center;gap:6px;padding:8px 14px;background:#f0f4fb;border:1.5px solid #dde4ee;border-radius:8px;font-size:.85rem;font-weight:600;color:#1a5fa8;cursor:pointer;transition:background .15s}
.upload-btn:hover{background:#dde8f8}
.upload-btn input[type=file]{display:none}
.upload-status{font-size:.8rem;margin-top:4px;min-height:18px}
.filters{display:flex;gap:10px;margin-bottom:20px;align-items:center;flex-wrap:wrap}
.filters a{padding:7px 16px;border-radius:999px;font-size:.85rem;font-weight:600;text-decoration:none;border:1.5px solid #dde4ee;color:#5a6375}
.filters a.active{background:#1a5fa8;color:#fff;border-color:#1a5fa8}
.empty{text-align:center;padding:48px;color:#8a94a6}
"""


def _admin_layout(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Breed Show Admin</title>
<style>{_ADMIN_CSS}</style></head>
<body>
<div class="topbar">
  <h1>🐾 Breed Show Admin</h1>
  <div style="display:flex;gap:12px;align-items:center">
    <a href="/admin/pets">Питомцы</a>
    <a href="/admin/analytics">Аналитика</a>
    <a href="/admin/logout">Выйти</a>
  </div>
</div>
<div class="container">{body}</div>
</body></html>"""


def _pet_form_html(pet: dict | None = None, error: str = "") -> str:
    p = pet or {}
    is_edit = bool(p)
    action = f"/admin/pets/{p.get('id')}/edit" if is_edit else "/admin/pets/new"
    title = "Редактировать питомца" if is_edit else "Добавить питомца"

    def v(key, default=""):
        return str(p.get(key, default)) if p.get(key) is not None else default

    def sel(key, val):
        return "selected" if str(p.get(key, "")) == val else ""

    def chk(key):
        return "checked" if p.get(key) else ""

    err_html = f'<div style="background:#fde8e8;color:#c0392b;padding:10px 14px;border-radius:8px;margin-bottom:16px">{error}</div>' if error else ""

    body = f"""
<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
  <a href="/admin/pets" class="btn btn-outline btn-sm">← Назад</a>
  <h2 style="margin:0">{title}</h2>
</div>
{err_html}
<div class="card">
<form method="post" action="{action}">
  <div class="form-row">
    <div class="form-group">
      <label>Имя *</label>
      <input type="text" name="name" value="{v('name')}" required>
    </div>
    <div class="form-group">
      <label>Порода *</label>
      <input type="text" name="breed" value="{v('breed')}" required>
    </div>
  </div>
  <div class="form-row-3">
    <div class="form-group">
      <label>Категория</label>
      <select name="mode">
        <option value="cats" {sel('mode','cats')}>🐱 Котята</option>
        <option value="dogs" {sel('mode','dogs')}>🐶 Щенки</option>
      </select>
    </div>
    <div class="form-group">
      <label>Пол</label>
      <select name="gender">
        <option value="male" {sel('gender','male')}>Кот / Кобель</option>
        <option value="female" {sel('gender','female')}>Кошка / Сука</option>
      </select>
    </div>
    <div class="form-group">
      <label>Возраст (мес.)</label>
      <input type="number" name="age_months" value="{v('age_months','0')}" min="0">
    </div>
  </div>
  <div class="form-row">
    <div class="form-group">
      <label>Цена, ₽</label>
      <input type="number" name="price" value="{v('price','0')}" min="0">
    </div>
    <div class="form-group">
      <label>Окрас</label>
      <input type="text" name="color" value="{v('color')}">
    </div>
  </div>
  <div class="form-group">
    <label>Описание</label>
    <textarea name="description">{v('description')}</textarea>
  </div>
  <div class="form-group">
    <label>Фото</label>
    <div style="display:flex;gap:8px;align-items:flex-start;flex-wrap:wrap">
      <input type="url" name="image" value="{v('image')}" id="imgUrl" oninput="previewImg(this.value)" placeholder="https://..." style="flex:1;min-width:200px">
      <label class="upload-btn" title="Загрузить фото">
        📷 Загрузить
        <input type="file" accept="image/*" id="imgUpload" onchange="uploadPhoto(this)">
      </label>
    </div>
    <div class="upload-status" id="uploadStatus"></div>
    <img id="imgPreview" class="img-preview" src="{v('image')}" alt="">
  </div>
  <div class="form-row">
    <div class="form-group">
      <label>Telegram URL</label>
      <input type="text" name="telegram_url" value="{v('telegram_url')}" placeholder="https://t.me/username">
    </div>
    <div class="form-group">
      <label>Телефон</label>
      <input type="text" name="phone" value="{v('phone')}" placeholder="+7 000 000-00-00">
    </div>
  </div>
  <div class="form-group">
    <label>Email</label>
    <input type="email" name="email" value="{v('email')}">
  </div>
  <hr style="border:none;border-top:1px solid #dde4ee;margin:20px 0">
  <div class="form-row">
    <div class="form-group">
      <label>Питомник (название)</label>
      <input type="text" name="kennel_name" value="{v('kennel_name')}">
    </div>
    <div class="form-group">
      <label>Питомник (ID для ссылки)</label>
      <input type="text" name="kennel_id" value="{v('kennel_id')}" placeholder="my_kennel">
    </div>
  </div>
  <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:20px">
    <label class="checkbox-row"><input type="checkbox" name="available" {chk('available')}> Доступен</label>
    <label class="checkbox-row"><input type="checkbox" name="is_promoted" {chk('is_promoted')}> 🔥 ТОП</label>
    <label class="checkbox-row"><input type="checkbox" name="has_kennel_landing" {chk('has_kennel_landing')}> ⭐ Питомник</label>
    <label class="checkbox-row"><input type="checkbox" name="show_to_subscribers" {chk('show_to_subscribers')}> 🔔 Показывать подписчикам</label>
  </div>
  <div style="display:flex;gap:10px">
    <button type="submit" class="btn btn-primary">💾 Сохранить</button>
    <a href="/admin/pets" class="btn btn-outline">Отмена</a>
  </div>
</form>
</div>
<script>
function previewImg(url) {{
  var img = document.getElementById('imgPreview');
  if (url) {{ img.src = url; img.style.display = 'block'; }}
  else {{ img.style.display = 'none'; }}
}}
window.onload = function() {{
  var url = document.getElementById('imgUrl').value;
  if (url) previewImg(url);
}};
async function uploadPhoto(input) {{
  if (!input.files || !input.files[0]) return;
  var file = input.files[0];
  var status = document.getElementById('uploadStatus');
  status.textContent = '⏳ Загружаю...';
  status.style.color = '#5a6375';
  try {{
    var form = new FormData();
    form.append('file', file);
    var resp = await fetch('/admin/upload', {{ method: 'POST', body: form }});
    var data = await resp.json();
    if (data && data.url) {{
      document.getElementById('imgUrl').value = data.url;
      previewImg(data.url);
      status.textContent = '✅ Загружено';
      status.style.color = '#1c8a4e';
    }} else {{
      status.textContent = '❌ Ошибка: ' + (data.error || JSON.stringify(data));
      status.style.color = '#c0392b';
    }}
  }} catch(e) {{
    status.textContent = '❌ Ошибка загрузки';
    status.style.color = '#c0392b';
  }}
  input.value = '';
}}
</script>"""
    return _admin_layout(title, body)


# ---------------------------------------------------------------------------
# Admin HTTP handlers
# ---------------------------------------------------------------------------

async def handle_admin_upload(request: web.Request) -> web.Response:
    if not _admin_check(request):
        return web.Response(text='{"error":"unauthorized"}', status=401, content_type="application/json")
    try:
        reader = await request.multipart()
        field = await reader.next()
        if not field or field.name != "file":
            return web.Response(text='{"error":"no file"}', status=400, content_type="application/json")
        data = await field.read()
        filename = field.filename or "photo.jpg"
        content_type_header = field.headers.get("Content-Type", "image/jpeg")
    except Exception as e:
        return web.Response(text=json.dumps({"error": str(e)}), status=400, content_type="application/json")

    try:
        import uuid
        import asyncio
        import boto3
        s3_endpoint = os.environ.get("S3_URL", "https://s3.twcstorage.ru")
        s3_bucket = os.environ.get("S3_BUCKET", "")
        s3_access = os.environ.get("S3_ACCESS_KEY", "")
        s3_secret = os.environ.get("S3_SECRET_KEY", "")
        s3_region = os.environ.get("S3_REGION", "ru-1")
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
        key = f"pets/{uuid.uuid4().hex}.{ext}"

        def _upload():
            client = boto3.client(
                "s3",
                endpoint_url=s3_endpoint,
                aws_access_key_id=s3_access,
                aws_secret_access_key=s3_secret,
                region_name=s3_region,
            )
            client.put_object(
                Bucket=s3_bucket,
                Key=key,
                Body=data,
                ContentType=content_type_header,
            )
            return f"{s3_endpoint}/{s3_bucket}/{key}"

        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(None, _upload)
        return web.Response(text=json.dumps({"url": url}), content_type="application/json")
    except Exception as e:
        return web.Response(text=json.dumps({"error": str(e)}), status=502, content_type="application/json")


async def handle_admin_redirect(request: web.Request) -> web.Response:
    if _admin_check(request):
        raise web.HTTPFound("/admin/pets")
    raise web.HTTPFound("/admin/login")


async def handle_admin_login_get(request: web.Request) -> web.Response:
    if _admin_check(request):
        raise web.HTTPFound("/admin/pets")
    error = request.rel_url.query.get("error", "")
    err_html = f'<div style="background:#fde8e8;color:#c0392b;padding:10px 14px;border-radius:8px;margin-bottom:16px">{error}</div>' if error else ""
    html = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Вход — Breed Show Admin</title>
<style>{_ADMIN_CSS}
.login-wrap{{display:flex;align-items:center;justify-content:center;min-height:100vh;background:#f0f4fa}}
.login-card{{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(26,95,168,.12);padding:40px;width:100%;max-width:380px}}
.login-logo{{text-align:center;font-size:2.5rem;margin-bottom:8px}}
.login-title{{text-align:center;font-size:1.2rem;font-weight:800;margin-bottom:24px;color:#1a1d23}}
</style></head>
<body>
<div class="login-wrap">
  <div class="login-card">
    <div class="login-logo">🐾</div>
    <div class="login-title">Breed Show Admin</div>
    {err_html}
    <form method="post" action="/admin/login">
      <div class="form-group">
        <label>Пароль</label>
        <input type="password" name="password" autofocus required>
      </div>
      <button type="submit" class="btn btn-primary" style="width:100%">Войти</button>
    </form>
  </div>
</div>
</body></html>"""
    return web.Response(text=html, content_type="text/html")


async def handle_admin_login_post(request: web.Request) -> web.Response:
    data = await request.post()
    password = data.get("password", "")
    if password == ADMIN_PASSWORD:
        token = secrets.token_hex(32)
        ADMIN_SESSIONS[token] = time.time() + SESSION_DURATION
        response = web.HTTPFound("/admin/pets")
        response.set_cookie("admin_session", token, max_age=SESSION_DURATION, httponly=True)
        raise response
    raise web.HTTPFound("/admin/login?error=Неверный+пароль")


async def handle_admin_logout(request: web.Request) -> web.Response:
    token = request.cookies.get("admin_session")
    if token:
        ADMIN_SESSIONS.pop(token, None)
    response = web.HTTPFound("/admin/login")
    response.del_cookie("admin_session")
    raise response


async def handle_admin_pets(request: web.Request) -> web.Response:
    if not _admin_check(request):
        raise web.HTTPFound("/admin/login")

    mode = request.rel_url.query.get("mode", "")
    conn = get_db()
    try:
        if mode in ("cats", "dogs"):
            rows = conn.execute(
                "SELECT * FROM pets WHERE mode=? ORDER BY is_promoted DESC, id ASC", (mode,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pets ORDER BY mode, is_promoted DESC, id ASC"
            ).fetchall()
        pets = [row_to_dict(r) for r in rows]
        total = conn.execute("SELECT COUNT(*) FROM pets").fetchone()[0]
        cats_count = conn.execute("SELECT COUNT(*) FROM pets WHERE mode='cats'").fetchone()[0]
        dogs_count = conn.execute("SELECT COUNT(*) FROM pets WHERE mode='dogs'").fetchone()[0]
    finally:
        conn.close()

    active_all = "active" if not mode else ""
    active_cats = "active" if mode == "cats" else ""
    active_dogs = "active" if mode == "dogs" else ""

    rows_html = ""
    for p in pets:
        cat_badge = f'<span class="badge badge-{"cats" if p["mode"]=="cats" else "dogs"}">{"🐱 Котята" if p["mode"]=="cats" else "🐶 Щенки"}</span>'
        avail_badge = f'<span class="badge badge-{"on" if p["available"] else "off"}">{"Доступен" if p["available"] else "Недоступен"}</span>'
        promo = '<span class="badge badge-promo">🔥 ТОП</span>' if p["is_promoted"] else ""
        img = f'<img src="{p["image"]}" style="width:48px;height:36px;object-fit:cover;border-radius:6px">' if p["image"] else "—"
        toggle_label = "Скрыть" if p["available"] else "Показать"
        rows_html += f"""<tr>
          <td>{img}</td>
          <td><strong>{p['name']}</strong><br><span style="color:#8a94a6;font-size:.8rem">{p['breed']}</span></td>
          <td>{cat_badge}</td>
          <td>{p['age_months']} мес.</td>
          <td><strong>{p['price']:,} ₽</strong></td>
          <td>{avail_badge} {promo}</td>
          <td>
            <a href="/admin/pets/{p['id']}/edit" class="btn btn-outline btn-sm">✏️</a>
            <form method="post" action="/admin/pets/{p['id']}/toggle" style="display:inline">
              <button class="btn btn-sm" style="background:#e8f4fd;color:#1a5fa8;border:none">{toggle_label}</button>
            </form>
            <form method="post" action="/admin/pets/{p['id']}/delete" style="display:inline" onsubmit="return confirm('Удалить {p['name']}?')">
              <button class="btn btn-danger btn-sm">🗑</button>
            </form>
          </td>
        </tr>"""

    table_html = f"""<table>
      <thead><tr>
        <th>Фото</th><th>Питомец</th><th>Категория</th><th>Возраст</th><th>Цена</th><th>Статус</th><th>Действия</th>
      </tr></thead>
      <tbody>{rows_html if rows_html else f'<tr><td colspan="7" class="empty">Питомцы не найдены</td></tr>'}</tbody>
    </table>""" if pets else '<div class="empty">Питомцев пока нет</div>'

    body = f"""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:12px">
  <h2 style="margin:0">Питомцы <span style="color:#8a94a6;font-size:.9rem">({total} всего)</span></h2>
  <a href="/admin/pets/new" class="btn btn-primary">+ Добавить питомца</a>
</div>
<div class="filters">
  <a href="/admin/pets" class="{active_all}">Все ({total})</a>
  <a href="/admin/pets?mode=cats" class="{active_cats}">🐱 Котята ({cats_count})</a>
  <a href="/admin/pets?mode=dogs" class="{active_dogs}">🐶 Щенки ({dogs_count})</a>
</div>
<div class="card" style="padding:0;overflow:hidden">{table_html}</div>"""

    return web.Response(text=_admin_layout("Питомцы", body), content_type="text/html")


async def handle_admin_pet_new_get(request: web.Request) -> web.Response:
    if not _admin_check(request):
        raise web.HTTPFound("/admin/login")
    return web.Response(text=_pet_form_html(), content_type="text/html")


async def handle_admin_pet_new_post(request: web.Request) -> web.Response:
    if not _admin_check(request):
        raise web.HTTPFound("/admin/login")
    data = await request.post()
    if not data.get("name") or not data.get("breed"):
        return web.Response(text=_pet_form_html(dict(data), "Имя и порода обязательны"), content_type="text/html")

    pet_id = str(int(time.time() * 1000))
    show_to_subs = 1 if data.get("show_to_subscribers") else 0
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO pets (id,name,breed,mode,age_months,gender,price,color,description,
            image,available,telegram_url,phone,email,is_promoted,has_kennel_landing,kennel_name,kennel_id,
            show_to_subscribers,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
            (
                pet_id,
                data.get("name", "").strip(),
                data.get("breed", "").strip(),
                data.get("mode", "cats"),
                int(data.get("age_months") or 0),
                data.get("gender", "male"),
                int(data.get("price") or 0),
                data.get("color", "").strip(),
                data.get("description", "").strip(),
                data.get("image", "").strip(),
                1 if data.get("available") else 0,
                data.get("telegram_url", "").strip(),
                data.get("phone", "").strip(),
                data.get("email", "").strip(),
                1 if data.get("is_promoted") else 0,
                1 if data.get("has_kennel_landing") else 0,
                data.get("kennel_name", "").strip(),
                data.get("kennel_id", "").strip(),
                show_to_subs,
            ),
        )
        conn.commit()
        if show_to_subs:
            row = conn.execute("SELECT * FROM pets WHERE id=?", (pet_id,)).fetchone()
            pet_dict = row_to_dict(row) if row else {}
    finally:
        conn.close()

    if show_to_subs and pet_dict:
        from aiohttp.web import Application as WebApp
        tg_apps_ref = getattr(handle_admin_pet_new_post, "_tg_apps", [])
        asyncio.create_task(notify_subscribers_for_pet(pet_dict, tg_apps_ref))

    raise web.HTTPFound("/admin/pets")


async def handle_admin_pet_edit_get(request: web.Request) -> web.Response:
    if not _admin_check(request):
        raise web.HTTPFound("/admin/login")
    pet_id = request.match_info["id"]
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM pets WHERE id=?", (pet_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise web.HTTPFound("/admin/pets")
    return web.Response(text=_pet_form_html(row_to_dict(row)), content_type="text/html")


async def handle_admin_pet_edit_post(request: web.Request) -> web.Response:
    if not _admin_check(request):
        raise web.HTTPFound("/admin/login")
    pet_id = request.match_info["id"]
    data = await request.post()
    if not data.get("name") or not data.get("breed"):
        conn = get_db()
        try:
            row = conn.execute("SELECT * FROM pets WHERE id=?", (pet_id,)).fetchone()
        finally:
            conn.close()
        pet = row_to_dict(row) if row else {}
        pet.update(dict(data))
        return web.Response(text=_pet_form_html(pet, "Имя и порода обязательны"), content_type="text/html")

    conn = get_db()
    try:
        conn.execute(
            """UPDATE pets SET name=?,breed=?,mode=?,age_months=?,gender=?,price=?,color=?,
            description=?,image=?,available=?,telegram_url=?,phone=?,email=?,
            is_promoted=?,has_kennel_landing=?,kennel_name=?,kennel_id=?,
            show_to_subscribers=? WHERE id=?""",
            (
                data.get("name", "").strip(),
                data.get("breed", "").strip(),
                data.get("mode", "cats"),
                int(data.get("age_months") or 0),
                data.get("gender", "male"),
                int(data.get("price") or 0),
                data.get("color", "").strip(),
                data.get("description", "").strip(),
                data.get("image", "").strip(),
                1 if data.get("available") else 0,
                data.get("telegram_url", "").strip(),
                data.get("phone", "").strip(),
                data.get("email", "").strip(),
                1 if data.get("is_promoted") else 0,
                1 if data.get("has_kennel_landing") else 0,
                data.get("kennel_name", "").strip(),
                data.get("kennel_id", "").strip(),
                1 if data.get("show_to_subscribers") else 0,
                pet_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    raise web.HTTPFound("/admin/pets")


async def handle_admin_pet_delete(request: web.Request) -> web.Response:
    if not _admin_check(request):
        raise web.HTTPFound("/admin/login")
    pet_id = request.match_info["id"]
    conn = get_db()
    try:
        conn.execute("DELETE FROM pets WHERE id=?", (pet_id,))
        conn.commit()
    finally:
        conn.close()
    raise web.HTTPFound("/admin/pets")


async def handle_admin_pet_toggle(request: web.Request) -> web.Response:
    if not _admin_check(request):
        raise web.HTTPFound("/admin/login")
    pet_id = request.match_info["id"]
    conn = get_db()
    try:
        conn.execute("UPDATE pets SET available = 1 - available WHERE id=?", (pet_id,))
        conn.commit()
    finally:
        conn.close()
    raise web.HTTPFound(request.headers.get("Referer", "/admin/pets"))


async def handle_admin_analytics(request: web.Request) -> web.Response:
    if not _admin_check(request):
        raise web.HTTPFound("/admin/login")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Summary counts per event
    rows = conn.execute("""
        SELECT event, COUNT(*) as cnt,
               COUNT(DISTINCT tg_user_id) as uniq_users
        FROM analytics_events
        GROUP BY event
        ORDER BY cnt DESC
    """).fetchall()

    # Recent 50 events
    recent = conn.execute("""
        SELECT event, pet_id, kennel_id, tg_user_id, created_at
        FROM analytics_events
        ORDER BY id DESC
        LIMIT 50
    """).fetchall()
    conn.close()

    summary_rows = "".join(
        f"<tr><td>{r['event']}</td><td>{r['cnt']}</td><td>{r['uniq_users']}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='3' style='text-align:center;color:#8a94a6'>Нет данных</td></tr>"

    recent_rows = "".join(
        f"<tr><td>{r['event']}</td><td>{r['pet_id'] or '—'}</td>"
        f"<td>{r['kennel_id'] or '—'}</td><td>{r['tg_user_id'] or '—'}</td>"
        f"<td style='white-space:nowrap'>{r['created_at']}</td></tr>"
        for r in recent
    ) or "<tr><td colspan='5' style='text-align:center;color:#8a94a6'>Нет данных</td></tr>"

    body = f"""
    <h2 style="margin-bottom:20px">📊 Аналитика событий</h2>

    <h3 style="margin-bottom:12px">Сводка</h3>
    <table>
      <thead><tr><th>Событие</th><th>Всего</th><th>Уник. пользователей</th></tr></thead>
      <tbody>{summary_rows}</tbody>
    </table>

    <h3 style="margin:24px 0 12px">Последние 50 событий</h3>
    <table>
      <thead><tr><th>Событие</th><th>Pet ID</th><th>Kennel ID</th><th>User ID</th><th>Время</th></tr></thead>
      <tbody>{recent_rows}</tbody>
    </table>
    """
    return web.Response(text=_admin_layout("Аналитика", body), content_type="text/html")


# ---------------------------------------------------------------------------
# Build aiohttp app
# ---------------------------------------------------------------------------

def build_web_app() -> web.Application:
    app = web.Application()

    app.router.add_get("/health", handle_health)
    app.router.add_post("/analytics/event", handle_analytics_event)
    app.router.add_get("/tg/config", handle_config)
    app.router.add_get("/pets", handle_pets)
    app.router.add_get("/pets/{id}", handle_pet_by_id)
    app.router.add_get("/tg/favorites", handle_get_favorites)
    app.router.add_post("/tg/favorites", handle_add_favorite)
    app.router.add_delete("/tg/favorites/{pet_id}", handle_delete_favorite)
    app.router.add_get("/tg/subscriptions", handle_get_subscriptions)
    app.router.add_post("/tg/subscriptions", handle_create_subscription)
    app.router.add_delete("/tg/subscriptions/{id}", handle_delete_subscription)
    app.router.add_get("/demand/breeds", handle_demand_breeds)

    # CORS preflight OPTIONS routes
    for path in (
        "/health", "/analytics/event", "/tg/config", "/pets",
        "/tg/favorites", "/tg/subscriptions", "/demand/breeds",
    ):
        app.router.add_route("OPTIONS", path, handle_options)
    app.router.add_route("OPTIONS", "/pets/{id}", handle_options)
    app.router.add_route("OPTIONS", "/tg/favorites/{pet_id}", handle_options)
    app.router.add_route("OPTIONS", "/tg/subscriptions/{id}", handle_options)

    # Admin panel routes
    app.router.add_post("/admin/upload", handle_admin_upload)
    app.router.add_get("/admin", handle_admin_redirect)
    app.router.add_get("/admin/login", handle_admin_login_get)
    app.router.add_post("/admin/login", handle_admin_login_post)
    app.router.add_get("/admin/logout", handle_admin_logout)
    app.router.add_get("/admin/pets", handle_admin_pets)
    app.router.add_get("/admin/pets/new", handle_admin_pet_new_get)
    app.router.add_post("/admin/pets/new", handle_admin_pet_new_post)
    app.router.add_get("/admin/pets/{id}/edit", handle_admin_pet_edit_get)
    app.router.add_post("/admin/pets/{id}/edit", handle_admin_pet_edit_post)
    app.router.add_post("/admin/pets/{id}/delete", handle_admin_pet_delete)
    app.router.add_post("/admin/pets/{id}/toggle", handle_admin_pet_toggle)
    app.router.add_get("/admin/analytics", handle_admin_analytics)

    return app


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    init_db()

    # Determine bot configs
    bots_config: list[tuple[str, str]] = []  # [(token, mode), ...]
    if BOT_TOKEN_CATS:
        bots_config.append((BOT_TOKEN_CATS, "cats"))
    if BOT_TOKEN_DOGS:
        bots_config.append((BOT_TOKEN_DOGS, "dogs"))
    if not bots_config and BOT_TOKEN:
        bots_config.append((BOT_TOKEN, BOT_MODE))

    if not bots_config:
        logger.warning(
            "No bot tokens configured. "
            "Set BOT_TOKEN_CATS / BOT_TOKEN_DOGS or BOT_TOKEN + BOT_MODE."
        )

    tg_apps: list[Application] = []
    for token, mode in bots_config:
        tg_apps.append(build_application(token, mode))
        logger.info("Telegram bot configured: mode=%s", mode)

    # Start aiohttp HTTP server
    web_app = build_web_app()
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("HTTP server listening on port %d", PORT)

    # Start Telegram polling for all bots
    if tg_apps:
        await asyncio.gather(*[app.initialize() for app in tg_apps])
        await asyncio.gather(*[app.start() for app in tg_apps])
        await asyncio.gather(
            *[app.updater.start_polling(drop_pending_updates=True) for app in tg_apps]
        )
        logger.info("Telegram bots started (%d bot(s))", len(tg_apps))

    # Share tg_apps with admin handler for triggering notifications
    handle_admin_pet_new_post._tg_apps = tg_apps

    # Block forever
    try:
        await asyncio.Event().wait()
    finally:
        logger.info("Shutting down...")
        await runner.cleanup()
        for app in tg_apps:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
