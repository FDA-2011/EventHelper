from vkbottle.bot import Bot, Message, BotLabeler
from vkbottle import BaseStateGroup, Keyboard, Callback, DocMessagesUploader

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
        "SELECT s.id, s.title, s.start_time, s.end_time, "
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
            lines.append(f"  ID {s['id']}: {start}–{end} — {s['title']} ({s['speaker'] or 'спикер не указан'})")
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
    user = db.get_user(message.from_id or message.peer_id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /register")
        return
    selected = db.get_user_schedule(user["id"])
    if not selected:
        await message.answer("Личное расписание пусто. Добавьте доклады командой /schedule_add <ID>. Программа: /program")
        return
    buf = build_ics(selected)
    try:
        uploader = DocMessagesUploader(bot.api)
        doc = await uploader.upload(buf, peer_id=message.peer_id, title="my_schedule.ics")
        await message.answer(message="Ваше личное расписание (.ics)", attachment=[str(doc)])
    except Exception as e:
        await message.answer("Не удалось отправить календарь. Ваше расписание:\n" + "\n".join(
            f"{r['start_time']} — {r['title']} ({r['hall'] or '—'})" for r in selected
        ))


@router.message(func=lambda m: m.text and m.text.lower().startswith("/schedule_add "))
async def schedule_add(message: Message):
    try:
        session_id = int(message.text.split(maxsplit=1)[1])
    except (ValueError, IndexError):
        await message.answer("Использование: /schedule_add <ID доклада>. ID можно увидеть в /program")
        return
    user = db.get_user(message.from_id or message.peer_id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /register")
        return
    if not db.select("sessions", {"id": session_id}):
        await message.answer("Доклад с таким ID не найден. Посмотрите /program")
        return
    added = db.add_to_schedule(user["id"], session_id)
    await message.answer("Доклад добавлен в ваше расписание." if added else "Этот доклад уже есть в расписании.")


@router.message(func=lambda m: m.text and m.text.lower().startswith("/schedule_remove "))
async def schedule_remove(message: Message):
    try:
        session_id = int(message.text.split(maxsplit=1)[1])
    except (ValueError, IndexError):
        await message.answer("Использование: /schedule_remove <ID доклада>")
        return
    user = db.get_user(message.from_id or message.peer_id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /register")
        return
    removed = db.delete("user_schedule", {"user_id": user["id"], "session_id": session_id})
    await message.answer("Доклад удалён из расписания." if removed else "Такого доклада нет в вашем расписании.")


@router.message(text=["/schedule_add", "/schedule_remove"])
async def schedule_usage(message: Message):
    await message.answer("Укажите ID доклада. Список: /program")


# ---------- Карта площадки ----------
@router.message(text="/map")
async def show_map(message: Message):
    lon, lat = next(iter(VENUE_POIS.values()))
    url = f"https://yandex.ru/maps/?ll={lon}%2C{lat}&z=17"
    await message.answer(
        "🗺️ Карта площадки: " + url + "\nМаршрут: /route <откуда> <куда>\n"
        "Доступные точки: " + ", ".join(VENUE_POIS.keys())
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
    url = f"https://yandex.ru/maps/?rtext={oy}%2C{ox}~{dy}%2C{dx}&rtt=pd"
    await message.answer(f"🧭 Маршрут: {origin} → {dest}\n{url}")


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

    user = db.get_user(message.from_id or message.peer_id)
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