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
    """)
    conn.commit()

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
# Build aiohttp app
# ---------------------------------------------------------------------------

def build_web_app() -> web.Application:
    app = web.Application()

    app.router.add_get("/health", handle_health)
    app.router.add_get("/tg/config", handle_config)
    app.router.add_get("/pets", handle_pets)
    app.router.add_get("/pets/{id}", handle_pet_by_id)
    app.router.add_get("/tg/favorites", handle_get_favorites)
    app.router.add_post("/tg/favorites", handle_add_favorite)
    app.router.add_delete("/tg/favorites/{pet_id}", handle_delete_favorite)

    # CORS preflight OPTIONS routes
    for path in ("/health", "/tg/config", "/pets", "/tg/favorites"):
        app.router.add_route("OPTIONS", path, handle_options)
    app.router.add_route("OPTIONS", "/pets/{id}", handle_options)
    app.router.add_route("OPTIONS", "/tg/favorites/{pet_id}", handle_options)

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
