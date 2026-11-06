from io import BytesIO
import requests
from vkbottle.bot import Message, BotLabeler
from vkbottle import BaseStateGroup, Keyboard, Callback, DocMessagesUploader, PhotoMessageUploader
from vkbottle import GroupEventType
from vkbottle.bot import MessageEvent

from bot_instance import bot
from config import VENUE_POIS
from database import db
from helpers import build_ics

router = BotLabeler()
router.vbml_ignore_case = True

PENDING_QUESTIONS = {}


class AskForm(BaseStateGroup):
    speaker = "speaker"
    question = "question"


@router.message(text="/program")
async def show_program(message: Message):
    rows = db.con.execute(
        "SELECT s.title, s.start_time, s.end_time, "
        "       sp.full_name AS speaker, l.name AS hall "
        "FROM sessions s "
        "LEFT JOIN speakers sp ON s.speaker_id = sp.id "
        "LEFT JOIN locations l ON s.location_id = l.id "
        "ORDER BY s.start_time"
    ).fetchall()
    if not rows:
        await message.answer("Программа пока пуста.")
        return

    halls: dict[str, list] = {}
    for r in rows:
        halls.setdefault(r["hall"] or "—", []).append(dict(r))

    lines = ["📅 Программа форума\n"]
    for hall, sessions in halls.items():
        lines.append(f"🏛️ {hall}")
        for s in sessions:
            start = s["start_time"].split(" ")[1][:5] if " " in s["start_time"] else s["start_time"]
            end = s["end_time"].split(" ")[1][:5] if " " in s["end_time"] else s["end_time"]
            lines.append(f"  {start}–{end} — {s['title']} ({s['speaker'] or 'Нет спикера'})")
        lines.append("")
    await message.answer("\n".join(lines))


@router.message(text=["/search", "/search <query>"])
async def search(message: Message, query: str = None):
    if not query:
        await message.answer("Использование: /search <слово>")
        return

    q = f"%{query.lower().strip()}%"

    try:
        rows = db.con.execute(
            "SELECT s.title, s.start_time, sp.full_name AS speaker, l.name AS hall "
            "FROM sessions s "
            "LEFT JOIN speakers sp ON s.speaker_id = sp.id "
            "LEFT JOIN locations l ON s.location_id = l.id "
            "LEFT JOIN tracks t ON s.track_id = t.id "
            "WHERE LOWER(s.title) LIKE ? OR LOWER(sp.full_name) LIKE ? OR LOWER(t.name) LIKE ? OR LOWER(l.name) LIKE ?",
            (q, q, q, q),
        ).fetchall()

        if not rows:
            await message.answer("Ничего не найдено.")
            return

        await message.answer(
            "🔍 Результаты:\n" + "\n".join(
                f"• {r['title']} — {r['speaker'] or 'Нет спикера'} "
                f"({r['start_time'].split(' ')[1][:5] if ' ' in r['start_time'] else r['start_time']}, {r['hall'] or 'Зал не указан'})"
                for r in rows
            )
        )
    except Exception as e:
        print(f"Ошибка поиска: {e}")
        await message.answer("⚠️ Ошибка при поиске докладов.")


@router.message(text="/my_schedule")
async def my_schedule(message: Message):
    try:
        user = db.get_user(message.peer_id)
        selected = []

        if user:
            sessions = db.con.execute(
                "SELECT s.title, s.start_time, s.end_time, "
                "       sp.full_name AS speaker, l.name AS hall "
                "FROM user_schedule us "
                "JOIN sessions s ON us.session_id = s.id "
                "LEFT JOIN speakers sp ON s.speaker_id = sp.id "
                "LEFT JOIN locations l ON s.location_id = l.id "
                "WHERE us.user_id = ? "
                "ORDER BY s.start_time",
                (user["id"],)
            ).fetchall()
            selected = [dict(r) for r in sessions]

        if not selected:
            rows = db.con.execute(
                "SELECT s.title, s.start_time, s.end_time, "
                "       sp.full_name AS speaker, l.name AS hall "
                "FROM sessions s "
                "LEFT JOIN speakers sp ON s.speaker_id = sp.id "
                "LEFT JOIN locations l ON s.location_id = l.id "
                "ORDER BY s.start_time"
            ).fetchall()
            selected = [dict(r) for r in rows]

        if not selected:
            await message.answer("Расписание пока пусто.")
            return

        payload = [
            {
                "title": s["title"],
                "hall": s["hall"] or "—",
                "speaker": s["speaker"] or "",
                "start": s["start_time"][11:16] if len(s["start_time"]) > 16 else "00:00",
                "end": s["end_time"][11:16] if len(s["end_time"]) > 16 else "00:00",
            }
            for s in selected
        ]
        buf = build_ics(payload)
        uploader = DocMessagesUploader(bot.api)
        doc = await uploader.upload(buf, peer_id=message.peer_id, title="my_schedule.ics")
        await message.answer(message="Ваше расписание (.ics)", attachment=doc)
    except Exception as e:
        await message.answer(f"⚠️ Не удалось сформировать .ics: {e}")


async def _send_map_image(message: Message, url: str, caption: str):
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        buf = BytesIO(resp.content)
        buf.name = "map.png"
        uploader = PhotoMessageUploader(bot.api)
        photo = await uploader.upload(buf, peer_id=message.peer_id)
        await message.answer(message=caption, attachment=photo)
    except Exception:
        await message.answer(f"{caption}\n\n{url}")


@router.message(text="/map")
async def show_map(message: Message):
    pts = "~".join(f"{lon},{lat},pm2rdm" for lon, lat in VENUE_POIS.values())
    url = (
        f"https://static-maps.yandex.ru/1.x/?"
        f"ll=37.617,55.755&z=17&size=650,450&l=map&pt={pts}"
    )
    await _send_map_image(
        message, url,
        "🗺️ Карта площадки. Маршрут: /route <откуда> <куда>\n"
        "Доступно: " + ", ".join(VENUE_POIS.keys()),
    )


@router.message(text=["/route", "/route <origin> <dest>"])
async def route(message: Message, origin: str = None, dest: str = None):
    if not origin or not dest:
        await message.answer(
            "Использование: /route <откуда> <куда>\n"
            "Доступно: " + ", ".join(VENUE_POIS.keys())
        )
        return

    origin, dest = origin.lower(), dest.lower()
    if origin not in VENUE_POIS or dest not in VENUE_POIS:
        await message.answer(
            f"Точка не найдена. Доступно: {', '.join(VENUE_POIS.keys())}"
        )
        return

    ox, oy = VENUE_POIS[origin]
    dx, dy = VENUE_POIS[dest]
    pl = f"{ox},{oy},{dx},{dy}"
    url = (
        f"https://static-maps.yandex.ru/1.x/?"
        f"ll=37.617,55.755&z=17&size=650,450&l=map"
        f"&pl={pl}"
        f"&pt={ox},{oy},pm2gnm~{dx},{dy},pm2rdm"
    )
    await _send_map_image(message, url, f"🧭 Маршрут: {origin} → {dest}")


@router.message(text=["/speaker", "/speaker <query>"])
async def speaker_profile(message: Message, query: str = None):
    if not query:
        rows = db.select("speakers")
        names = ", ".join(r["full_name"] for r in rows) if rows else "—"
        await message.answer(f"Использование: /speaker <ФИО>\nДоступные спикеры: {names}")
        return

    name = query.strip()
    rows = db.select("speakers", {"full_name": name})
    if not rows:
        await message.answer(f"Спикер «{name}» не найден.")
        return
    s = rows[0]
    await message.answer(
        f"👤 {s['full_name']}\n\n📖 {s.get('bio') or '—'}\n\n"
        f"🔗 Соцсети: {s.get('social_links') or '—'}"
    )


@router.message(text="/ask")
async def ask_start(message: Message):
    await bot.state_dispenser.set(message.peer_id, AskForm.speaker)
    await message.answer("Введите ФИО спикера:")


@router.message(state=AskForm.speaker, func=lambda m: m.text and not m.text.startswith("/"))
async def ask_speaker(message: Message):
    await bot.state_dispenser.set(
        message.peer_id, AskForm.question, speaker=message.text.strip()
    )
    await message.answer("Введите текст вопроса:")


@router.message(state=AskForm.question, func=lambda m: m.text and not m.text.startswith("/"))
async def ask_question(message: Message):
    p = message.state_peer.payload
    PENDING_QUESTIONS[message.peer_id] = {
        "speaker": p["speaker"],
        "question": message.text.strip()
    }
    await bot.state_dispenser.delete(message.peer_id)
    kb = (
        Keyboard(inline=True)
        .add(Callback("Анонимно", payload={"anon": "yes"}))
        .row()
        .add(Callback("С автором", payload={"anon": "no"}))
    )
    await message.answer("Как отправить?", keyboard=kb.get_json())


@router.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=MessageEvent)
async def handle_anonymity_callback(event: MessageEvent):
    try:
        await event.show_snackbar("Ваш выбор принят!")
    except Exception:
        pass

    if "anon" not in (event.payload or {}):
        return

    p = PENDING_QUESTIONS.pop(event.peer_id, None)
    if not p:
        await event.send_message("Ошибка: сессия истекла. Начните заново /ask")
        return

    is_anon = event.payload.get("anon") == "yes"
    speaker_name = p.get("speaker")
    question_text = p.get("question")

    speaker_rows = db.select("speakers", {"full_name": speaker_name})
    if not speaker_rows:
        await event.send_message("Спикер не найден — вопрос не сохранён.")
        return

    session_row = db.con.execute(
        "SELECT id FROM sessions WHERE speaker_id = ? LIMIT 1",
        (speaker_rows[0]["id"],),
    ).fetchone()
    if not session_row:
        await event.send_message("У спикера нет докладов в программе.")
        return

    user = db.get_user(event.user_id)
    db.insert("questions", {
        "user_id": user["id"] if user else None,
        "session_id": session_row["id"],
        "question_text": question_text,
        "is_anonymous": int(is_anon),
        "status": "pending",
    })

    confirm_text = "✅ Вопрос отправлен на модерацию" + (" анонимно." if is_anon else ".")
    await event.send_message(confirm_text)