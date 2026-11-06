import io
import os
import re
import uuid
import logging
from datetime import datetime

import requests
import qrcode
from cryptography.fernet import Fernet

from config import CRM_API_URL, CRM_API_KEY, FERNET_KEY

logger = logging.getLogger(__name__)

# Файл с ключом (используется, если FERNET_KEY не задан в .env)
_KEY_FILE = "secret.key"


# ============================================================
# Шифрование email / телефона
# ============================================================
def _load_fernet() -> Fernet:
    """Возвращает Fernet с одним и тем же ключом для бота и админки."""
    if FERNET_KEY:
        key = FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY
    elif os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(_KEY_FILE, "wb") as f:
            f.write(key)
        logger.info("Сгенерирован ключ шифрования в %s", _KEY_FILE)
    return Fernet(key)


_fernet = _load_fernet()


def encrypt_text(value: str | None) -> str | None:
    """Шифрует строку для хранения в БД. None / '' остаются как есть."""
    if not value:
        return value
    try:
        return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error("encrypt_text error: %s", e)
        return value


def decrypt_text(token: str | None) -> str | None:
    """Расшифровывает. Если данные не зашифрованы (старые) — возвращает как есть."""
    if not token:
        return token
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return token


# ============================================================
# Валидаторы
# ============================================================
def validate_email(email: str) -> bool:
    return re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email) is not None


def validate_phone(phone: str) -> bool:
    cleaned = re.sub(r"[^\d+]", "", phone)
    return 10 <= len(cleaned) <= 15


# ============================================================
# QR-код
# ============================================================
def generate_qr(data: str) -> io.BytesIO:
    print(f"⏳ [helpers] Начинаю генерацию QR для данных: {data}")
    qr = qrcode.make(data)
    buf = io.BytesIO()
    qr.save(buf)
    buf.name = "qr.png"
    buf.seek(0)
    print("✅ [helpers] QR успешно сгенерирован в памяти")
    return buf


# ============================================================
# .ics-экспорт
# ============================================================
def build_ics(sessions: list[dict], date_str: str = "20261105") -> io.BytesIO:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//VK Forum Bot//RU"]
    for s in sessions:
        start = datetime.strptime(f"{date_str} {s['start']}", "%Y%m%d %H:%M")
        end = datetime.strptime(f"{date_str} {s['end']}", "%Y%m%d %H:%M")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid4()}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{s['title']}",
            f"LOCATION:{s['hall']}",
            f"DESCRIPTION:Спикер: {s.get('speaker', '')}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    buf = io.BytesIO("\r\n".join(lines).encode("utf-8"))
    buf.name = "my_schedule.ics"
    return buf


# ============================================================
# CRM (заглушка)
# ============================================================
def crm_register(data: dict) -> str | None:
    try:
        try:
            requests.post(
                f"{CRM_API_URL}/register",
                json=data,
                headers={"X-API-Key": CRM_API_KEY},
                timeout=10,
            )
        except Exception:
            print("Ошибка при CRM")

        logger.info("CRM stub: %s", data)
        return "demo-crm-" + uuid.uuid4().hex[:8]
    except Exception as exc:
        logger.error("CRM error: %s", exc)
        return None