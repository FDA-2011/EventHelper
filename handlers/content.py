from vkbottle.bot import Bot, Message, BotLabeler
from vkbottle import (
    BaseStateGroup, Keyboard, Callback, DocMessagesUploader,
)

from config import VENUE_POIS
from database import db
from helpers import build_ics

router = BotLabeler()
router.vbml_ignore_case = True


class AskForm(BaseStateGroup):
    speaker = "speaker"
    question = "question"
    anonymity = "anonymity"


# ---------- Программа ----------
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
            start = s["start_time"].split(" ")[1][:5]
            end = s["end_time"].split(" ")[1][:5]
            lines.append(f"  {start}–{end} — {s['title']} ({s['speaker']})")
        lines.append("")
    await message.answer("\n".join(lines))


# ---------- Поиск докладов ----------
@router.message(func=lambda m: m.text and m.text.lower().startswith("/search "))
async def search(message: Message):
    query = message.text[len("/search "):].strip()
    if not query:
        await message.answer("Использование: /search <слово>")
        return
    q = f"%{query.lower()}%"
    rows = db.con.execute(
        "SELECT s.title, s.start_time, sp.full_name AS speaker, l.name AS hall "
        "FROM sessions s "
        "LEFT JOIN speakers sp ON s.speaker_id = sp.id "
        "LEFT JOIN locations l ON s.location_id = l.id "
        "WHERE LOWER(s.title) LIKE ? OR LOWER(sp.full_name) LIKE ?",
        (q, q),
    ).fetchall()
    if not rows:
        await message.answer("Ничего не найдено.")
        return
    await message.answer(
        "🔍 Результаты:\n" + "\n".join(
            f"• {r['title']} — {r['speaker']} "
            f"({r['start_time'].split(' ')[1][:5]}, {r['hall']})"
            for r in rows
        )
    )


@router.message(text="/search")
async def search_usage(message: Message):
    await message.answer("Использование: /search <слово>")


# ---------- Экспорт расписания ----------
@router.message(text="/my_schedule")
async def my_schedule(message: Message, bot: Bot):
    try:
        user = db.get_user(message.peer_id)
        if user:
            sessions = db.con.execute(
                "SELECT s.title, s.start_time, s.end_time, "
                "       sp.full_name AS speaker, l.name AS hall "
                "FROM user_schedule us "
                "JOIN sessions s ON us.session_id = s.id "
                "LEFT JOIN speakers sp ON s.speaker_id = sp.id "
                "LEFT JOIN locations l ON s.location_id = l.id "
                "ORDER BY s.start_time",
            ).fetchall()
            selected = [dict(r) for r in sessions]
        else:
            selected = []

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
                "start": s["start_time"][11:16],
                "end": s["end_time"][11:16],
            }
            for s in selected
        ]
        buf = build_ics(payload)
        uploader = DocMessagesUploader(bot.api)
        doc = await uploader.upload(buf, peer_id=message.peer_id, title="my_schedule.ics")
        await message.answer(
            message="Ваше расписание (.ics)",
            attachment=[str(doc)],
        )
    except Exception as e:
        await message.answer(f"⚠️ Не удалось сформировать .ics: {e}")


# ---------- Карта площадки ----------
@router.message(text="/map")
async def show_map(message: Message):
    pts = "~".join(f"{lon},{lat},pm2rdm" for lon, lat in VENUE_POIS.values())
    url = (
        f"https://static-maps.yandex.ru/1.x/?"
        f"ll=37.617,55.755&z=17&size=650,450&l=map&pt={pts}"
    )
    await message.answer(
        message="🗺️ Карта площадки. Маршрут: /route <откуда> <куда>\n"
                "Доступно: " + ", ".join(VENUE_POIS.keys()),
        attachment=url,
    )


@router.message(func=lambda m: m.text and m.text.lower().startswith("/route "))
async def route(message: Message):
    body = message.text[len("/route "):].strip()
    parts = body.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Использование: /route <откуда> <куда>\n"
            "Доступно: " + ", ".join(VENUE_POIS.keys())
        )
        return

    origin, dest = parts[0].lower(), parts[1].lower()
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
    await message.answer(
        message=f"🧭 Маршрут: {origin} → {dest}",
        attachment=url,
    )


@router.message(text="/route")
async def route_usage(message: Message):
    await message.answer(
        "Использование: /route <откуда> <куда>\n"
        "Доступно: " + ", ".join(VENUE_POIS.keys())
    )


# ---------- Спикеры ----------
@router.message(func=lambda m: m.text and m.text.lower().startswith("/speaker "))
async def speaker_profile(message: Message):
    name = message.text[len("/speaker "):].strip()
    if not name:
        await message.answer("Использование: /speaker <ФИО спикера>")
        return
    rows = db.select("speakers", {"full_name": name})
    if not rows:
        await message.answer(f"Спикер «{name}» не найден.")
        return
    s = rows[0]
    await message.answer(
        f"👤 {s['full_name']}\n\n📖 {s.get('bio') or '—'}\n\n"
        f"🔗 Соцсети: {s.get('social_links') or '—'}"
    )


@router.message(text="/speaker")
async def speaker_usage(message: Message):
    rows = db.select("speakers")
    names = ", ".join(r["full_name"] for r in rows) if rows else "—"
    await message.answer(f"Использование: /speaker <ФИО>\nДоступные спикеры: {names}")


# ---------- Вопрос спикеру ----------
@router.message(text="/ask")
async def ask_start(message: Message, bot: Bot):
    await bot.state_dispenser.set(message.peer_id, AskForm.speaker)
    await message.answer("Введите ФИО спикера:")


@router.message(state=AskForm.speaker)
async def ask_speaker(message: Message, bot: Bot):
    await bot.state_dispenser.set(
        message.peer_id, AskForm.question, speaker=message.text.strip()
    )
    await message.answer("Введите текст вопроса:")


@router.message(state=AskForm.question)
async def ask_question(message: Message, bot: Bot):
    p = message.state_peer.payload
    await bot.state_dispenser.set(
        message.peer_id, AskForm.anonymity,
        speaker=p["speaker"], question=message.text.strip(),
    )
    kb = (
        Keyboard(inline=True)
        .add(Callback("Анонимно", payload={"anon": "yes"}))
        .row()
        .add(Callback("С автором", payload={"anon": "no"}))
    )
    await message.answer("Как отправить?", keyboard=kb.get_json())


@router.message(state=AskForm.anonymity)
async def ask_anonymity(message: Message, bot: Bot):
    p = message.state_peer.payload
    is_anon = (message.payload or {}).get("anon") == "yes"
    await bot.state_dispenser.delete(message.peer_id)

    speaker_rows = db.select("speakers", {"full_name": p["speaker"]})
    if not speaker_rows:
        await message.answer("Спикер не найден — вопрос не сохранён.")
        return

    session_row = db.con.execute(
        "SELECT id FROM sessions WHERE speaker_id = ? LIMIT 1",
        (speaker_rows[0]["id"],),
    ).fetchone()
    if not session_row:
        await message.answer("У спикера нет докладов в программе.")
        return

    user = db.get_user(message.peer_id)
    db.insert("questions", {
        "user_id": user["id"] if user else None,
        "session_id": session_row["id"],
        "question_text": p["question"],
        "is_anonymous": int(is_anon),
        "status": "pending",
    })
    await message.answer(
        "✅ Вопрос отправлен на модерацию" + (" анонимно." if is_anon else ".")
    )