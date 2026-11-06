import os
from dotenv import load_dotenv

load_dotenv()

VK_BOT_TOKEN = os.getenv("VK_BOT_TOKEN", "")
OPERATOR_PEER_ID = int(os.getenv("OPERATOR_PEER_ID", "0"))
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

CRM_API_URL = os.getenv("CRM_API_URL", "")
CRM_API_KEY = os.getenv("CRM_API_KEY", "")
FERNET_KEY = os.getenv("FERNET_KEY", "")

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
