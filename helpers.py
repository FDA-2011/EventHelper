import io
import re
import uuid
import logging
from datetime import datetime

import qrcode

from config import CRM_API_URL, CRM_API_KEY, CRM_ENABLED

logger = logging.getLogger(__name__)


def validate_email(email: str) -> bool:
    return re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email) is not None


def validate_phone(phone: str) -> bool:
    cleaned = re.sub(r"[^\d+]", "", phone)
    return 10 <= len(cleaned) <= 15


def generate_qr(data: str) -> io.BytesIO:
    qr = qrcode.make(data)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return buf


def build_ics(sessions: list[dict], date_str: str | None = None) -> io.BytesIO:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//VK Forum Bot//RU"]
    for s in sessions:
        start_value = s.get("start_time")
        end_value = s.get("end_time")
        if start_value and end_value:
            start = datetime.fromisoformat(str(start_value))
            end = datetime.fromisoformat(str(end_value))
        else:
            day = date_str or datetime.now().strftime("%Y%m%d")
            start = datetime.strptime(f"{day} {s['start']}", "%Y%m%d %H:%M")
            end = datetime.strptime(f"{day} {s['end']}", "%Y%m%d %H:%M")
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


def crm_register(data: dict) -> str | None:
    if not CRM_ENABLED:
        return "local-" + uuid.uuid4().hex[:8]
    if not CRM_API_URL or not CRM_API_KEY:
        logger.error("CRM is enabled but CRM_API_URL / CRM_API_KEY are missing")
        return None
    try:
        import requests
        response = requests.post(
            f"{CRM_API_URL.rstrip('/')}/register", json=data,
            headers={"X-API-Key": CRM_API_KEY}, timeout=10
        )
        response.raise_for_status()
        result = response.json()
        return str(result.get("id") or result.get("crm_id") or "") or None
    except Exception as exc:
        logger.error("CRM error: %s", exc)
        return None