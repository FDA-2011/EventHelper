import os
from dotenv import load_dotenv

load_dotenv()

VK_BOT_TOKEN = os.getenv("VK_BOT_TOKEN", "")
OPERATOR_PEER_ID = int(os.getenv("OPERATOR_PEER_ID", "0"))
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

CRM_API_URL = os.getenv("CRM_API_URL", "")
CRM_API_KEY = os.getenv("CRM_API_KEY", "")
CRM_ENABLED = os.getenv("CRM_ENABLED", "0").lower() in ("1", "true", "yes")

# ---------- Точки площадки (для /map и /route) ----------
# Координаты — lon,lat. Замените на реальные координаты вашей площадки.
VENUE_POIS = {
    "вход": tuple(map(float, os.getenv("VENUE_ENTRY", "37.6160,55.7545").split(","))),
    "гардероб": tuple(map(float, os.getenv("VENUE_WARDROBE", "37.6165,55.7550").split(","))),
    "зал а": tuple(map(float, os.getenv("VENUE_HALL_A", "37.6175,55.7555").split(","))),
    "зал б": tuple(map(float, os.getenv("VENUE_HALL_B", "37.6185,55.7560").split(","))),
    "парковка": tuple(map(float, os.getenv("VENUE_PARKING", "37.6155,55.7540").split(","))),
    "выход": tuple(map(float, os.getenv("VENUE_EXIT", "37.6160,55.7545").split(","))),
}

# ---------- Seed-данные: используются только при первом запуске ----------
SEED_SPEAKERS = [
    {"full_name": "Иванов И.И.", "bio": "Эксперт в области AI, 10 лет опыта.",
     "social_links": "@ivanov_ai"},
    {"full_name": "Петрова А.С.", "bio": "Руководитель EdTech-проекта.",
     "social_links": "@petrova_ed"},
]

SEED_SCHEDULE = [
    {"title": "Открытие форума", "hall": "Зал А", "track": "Пленарные",
     "speaker": "Иванов И.И.",
     "start": "2026-11-05 10:00", "end": "2026-11-05 11:00"},
    {"title": "AI в образовании", "hall": "Зал Б", "track": "Технологии",
     "speaker": "Петрова А.С.",
     "start": "2026-11-05 11:30", "end": "2026-11-05 12:30"},
]

SEED_FAQ = [
    {"question": "парковка",
     "answer": "Парковка на уровне −1, въезд с ул. Примерной.",
     "keywords": "парковка,машина"},
    {"question": "дресс-код", "answer": "Деловой стиль.",
     "keywords": "дресс,одежда"},
    {"question": "wi-fi", "answer": "Сеть FORUM, пароль 12345678.",
     "keywords": "wifi,wi-fi,интернет"},
]