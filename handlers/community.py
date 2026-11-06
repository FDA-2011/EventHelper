import logging

from vkbottle.bot import Message, BotLabeler, MessageEvent
from vkbottle import BaseStateGroup, Keyboard, Callback, GroupEventType

from bot_instance import bot
from config import ADMIN_IDS, OPERATOR_PEER_ID
from database import db

logger = logging.getLogger(__name__)
router = BotLabeler()
router.vbml_ignore_case = True
PENDING_POLLS: dict[int, dict] = {}
LAST_SUPPORT_FROM: dict[int, int] = {}


class Feedback(BaseStateGroup):
    comment = "comment"


class Support(BaseStateGroup):
    waiting = "waiting"
@router.message(text=["/find", "/find <query>"])
async def find(message: Message, query: str = None):
    if not query:
        await message.answer("Использование: /find <регион/компания/ФИО>")
        return

    all_users = db.con.execute(
        "SELECT full_name, organization, region FROM users "
        "WHERE registration_status = 'confirmed'"
    ).fetchall()

    if not all_users:
        await message.answer(
            "В базе пока нет подтверждённых участников. "
            "Пройдите /register, чтобы вас могли найти."
        )
        return

    q = query.lower().strip()
    rows = [
        r for r in all_users
        if q in (r["full_name"] or "").lower()
        or q in (r["organization"] or "").lower()
        or q in (r["region"] or "").lower()
    ]

    if not rows:
        await message.answer(
            f"По запросу «{query}» никого не найдено. "
            f"Всего в базе: {len(all_users)}."
        )
        return

    await message.answer(
        f"Найдено: {len(rows)}\n" + "\n".join(
            f"• {r['full_name']} — {r['organization'] or '—'}, {r['region'] or '—'}"
            for r in rows
        )
    )
@router.message(text="/poll")
async def poll_start(message: Message):
    sessions = db.con.execute(
        "SELECT id, title FROM sessions ORDER BY start_time"
    ).fetchall()
    if not sessions:
        await message.answer("Программа ещё не загружена.")
        return

    kb = Keyboard(inline=True)
    for s in sessions:
        title = s["title"] if len(s["title"]) <= 30 else s["title"][:27] + "..."
        kb.add(Callback(
            title,
            payload={"action": "poll_select", "session_id": s["id"]},
        ))
        kb.row()

    await message.answer("Выберите доклад для оценки:", keyboard=kb.get_json())


@router.raw_event(
    GroupEventType.MESSAGE_EVENT,
    dataclass=MessageEvent,
    blocking=False,
)
async def poll_callback(event: MessageEvent):
    payload = event.payload or {}
    action = payload.get("action")

    if action not in ("poll_select", "poll_rate") and "rate" not in payload:
        return

    if action == "poll_select":
        session_id = payload.get("session_id")
        if not session_id:
            await event.show_snackbar("Ошибка: доклад не найден")
            return

        session = db.con.execute(
            "SELECT title FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            await event.show_snackbar("Доклад не найден")
            return

        PENDING_POLLS[event.peer_id] = {"session_id": session_id}

        kb = Keyboard(inline=True)
        for i in range(1, 6):
            kb.add(Callback(
                f"{i} ",
                payload={"action": "poll_rate", "rate": i},
            ))
            kb.row()

        await event.show_snackbar("Выберите оценку")
        await event.send_message(
            f"Оцените доклад «{session['title']}» от 1 до 5:",
            keyboard=kb.get_json(),
        )
        return

    score = payload.get("rate")
    poll_data = PENDING_POLLS.get(event.peer_id)
    if not poll_data:
        await event.show_snackbar("Сессия истекла")
        await event.send_message("Ошибка: сессия истекла. Начните заново /poll")
        return

    user = db.get_user(event.peer_id)
    if not user:
        await event.show_snackbar("Сначала /register")
        await event.send_message(
            "Чтобы оценивать доклады, сначала пройдите /register"
        )
        return

    session_id = poll_data["session_id"]
    existing = db.con.execute(
        "SELECT id FROM feedback "
        "WHERE user_id = ? AND target_type = 'session' AND target_id = ?",
        (user["id"], session_id),
    ).fetchone()

    if existing:
        db.update(
            "feedback",
            {"rating": score, "comment": None},
            {"id": existing["id"]},
        )
    else:
        db.insert("feedback", {
            "user_id": user["id"],
            "target_type": "session",
            "target_id": session_id,
            "rating": score,
        })

    PENDING_POLLS[event.peer_id]["rating"] = score
    await bot.state_dispenser.set(event.peer_id, Feedback.comment)

    await event.show_snackbar(f"Оценка {score} сохранена")
    await event.send_message(
        f"Оценка: {score}  сохранена.\n"
        f"Комментарий (или «-» для пропуска):"
    )


@router.message(
    state=Feedback.comment,
    func=lambda m: m.text and not m.text.startswith("/"),
)
async def poll_comment(message: Message):
    text = message.text.strip()
    await bot.state_dispenser.delete(message.peer_id)

    poll_data = PENDING_POLLS.pop(message.peer_id, None)
    if not poll_data:
        await message.answer("Ошибка: данные об оценке не найдены.")
        return

    user = db.get_user(message.peer_id)
    if not user:
        await message.answer("Вы не зарегистрированы, оценка не сохранена.")
        return

    comment = "" if text == "-" else text
    session_id = poll_data.get("session_id")
    rating = poll_data.get("rating")

    existing = db.con.execute(
        "SELECT id FROM feedback "
        "WHERE user_id = ? AND target_type = 'session' AND target_id = ?",
        (user["id"], session_id),
    ).fetchone()

    if existing:
        db.update("feedback", {"comment": comment}, {"id": existing["id"]})
    else:
        db.insert("feedback", {
            "user_id": user["id"],
            "target_type": "session",
            "target_id": session_id,
            "rating": rating,
            "comment": comment,
        })

    await message.answer(" Спасибо за обратную связь!")
@router.message(text=["/broadcast <text>"])
async def broadcast(message: Message, text: str = None):
    if message.peer_id not in ADMIN_IDS:
        await message.answer(" Недостаточно прав.")
        return
    if not text:
        await message.answer("Использование: /broadcast <текст>")
        return

    users = db.get_confirmed_users()
    sent = 0
    for u in users:
        try:
            await bot.api.messages.send(
                peer_id=u["vk_user_id"], message=text, random_id=0
            )
            sent += 1
        except Exception as e:
            logger.error("Broadcast %s: %s", u["vk_user_id"], e)

    db.insert("broadcasts", {"text_content": text, "status": "sent"})
    await message.answer(f"Отправлено {sent} из {len(users)}.")


@router.message(text=["/emergency <text>"])
async def emergency(message: Message, text: str = None):
    if message.peer_id not in ADMIN_IDS:
        await message.answer(" Недостаточно прав.")
        return
    if not text:
        await message.answer("Использование: /emergency <текст>")
        return

    users = db.get_confirmed_users()
    for u in users:
        try:
            await bot.api.messages.send(
                peer_id=u["vk_user_id"], message=text, random_id=0
            )
        except Exception:
            pass
    await message.answer("Оповещение разослано.")


@router.message(text="/admin_help")
async def admin_help(message: Message):
    if message.peer_id not in ADMIN_IDS:
        return
    await message.answer(
        " Админ-команды:\n\n"
        "Поддержка:\n"
        "/support_list — активные обращения\n"
        "/reply <текст> — ответить последнему\n"
        "/answer <peer_id> <текст> — ответить конкретному\n\n"
        "Рассылка:\n"
        "/broadcast <текст> — всем участникам\n"
        "/emergency <текст> — экстренное оповещение\n\n"
        "Управление — через Streamlit-админку:\n"
        "• Пользователи, программа, спикеры\n"
        "• Вопросы на модерации\n"
        "• Карта площадки"
    )
@router.message(text="/faq")
async def faq_list(message: Message):
    rows = db.select("faq")
    if not rows:
        await message.answer("FAQ пока не заполнен.")
        return
    text = " Частые вопросы:\n\n" + "\n\n".join(
        f"• {r['question']}: {r['answer']}" for r in rows
    )
    text += "\n\n🆘 Поддержка: /support"
    await message.answer(text)


@router.message(text="/support")
async def support_cmd(message: Message):
    if message.peer_id in ADMIN_IDS:
        await message.answer(
            "Вы администратор. Команды поддержки:\n"
            "/support_list — все обращения\n"
            "/reply <текст> — ответить последнему обратившемуся\n"
            "/answer <peer_id> <текст> — ответить конкретному\n"
            "/admin_help — все админ-команды"
        )
        return

    await bot.state_dispenser.set(message.peer_id, Support.waiting)
    await message.answer(
        "Вы подключены к линии поддержки. Опишите вопрос — оператор ответит.\n"
        "Для выхода: /end_support"
    )


@router.message(
    state=Support.waiting,
    func=lambda m: m.text and not m.text.startswith("/"),
)
async def forward_support(message: Message):
    user = db.get_user(message.peer_id)
    if user:
        db.insert("support_messages", {
            "user_id": user["id"],
            "sender_type": "user",
            "message_text": message.text,
        })

    try:
        await bot.api.messages.send(
            peer_id=OPERATOR_PEER_ID,
            message=(
                f"🆘 Сообщение от участника {message.peer_id}:\n\n"
                f"{message.text}\n\n"
                f"─────\n"
                f"/reply <текст> — ответить\n"
                f"/answer {message.peer_id} <текст> — ответить явно\n"
                f"/support_list — все обращения"
            ),
            random_id=0,
        )
        LAST_SUPPORT_FROM[OPERATOR_PEER_ID] = message.peer_id
    except Exception as e:
        logger.error("Support forward: %s", e)

    await message.answer("Сообщение передано оператору. Ожидайте ответа.")


@router.message(text="/end_support")
async def end_support(message: Message):
    await bot.state_dispenser.delete(message.peer_id)
    await message.answer("Вы вышли из режима поддержки.")
async def _send_reply_to_user(admin_message: Message, target: int, text: str):
    if not text:
        await admin_message.answer("Пустой текст ответа.")
        return

    try:
        await bot.api.messages.send(
            peer_id=target,
            message=f" Ответ поддержки:\n\n{text}",
            random_id=0,
        )
    except Exception as e:
        await admin_message.answer(f" Не удалось отправить: {e}")
        return

    user = db.get_user(target)
    if user:
        db.insert("support_messages", {
            "user_id": user["id"],
            "sender_type": "operator",
            "message_text": text,
        })
        db.con.execute(
            "UPDATE support_messages SET is_read_by_operator = 1 "
            "WHERE user_id = ? AND sender_type = 'user'",
            (user["id"],),
        )
        db.con.commit()

    await admin_message.answer(f" Ответ отправлен участнику {target}.")


@router.message(func=lambda m: m.text and m.text.lower().startswith("/reply "))
async def admin_reply(message: Message):
    if message.peer_id not in ADMIN_IDS:
        return

    text = message.text[len("/reply "):].strip()
    target = LAST_SUPPORT_FROM.get(OPERATOR_PEER_ID)
    if not target:
        await message.answer(
            "Нет активного диалога. Используйте /support_list, "
            "а затем /answer <peer_id> <текст>."
        )
        return

    await _send_reply_to_user(message, target, text)


@router.message(func=lambda m: m.text and m.text.lower().startswith("/answer "))
async def admin_answer(message: Message):
    if message.peer_id not in ADMIN_IDS:
        return

    body = message.text[len("/answer "):].strip()
    parts = body.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /answer <peer_id> <текст>")
        return

    try:
        target = int(parts[0])
    except ValueError:
        await message.answer(
            "peer_id должен быть числом. Пример: /answer 638787485 Привет"
        )
        return

    await _send_reply_to_user(message, target, parts[1])


@router.message(text="/support_list")
async def admin_support_list(message: Message):
    if message.peer_id not in ADMIN_IDS:
        await message.answer(" Недостаточно прав.")
        return

    rows = db.con.execute(
        "SELECT u.vk_user_id, u.full_name, "
        "       COUNT(sm.id) AS unread, "
        "       MAX(sm.message_text) AS last_msg, "
        "       MAX(sm.created_at) AS last_time "
        "FROM support_messages sm "
        "JOIN users u ON sm.user_id = u.id "
        "WHERE sm.sender_type = 'user' AND sm.is_read_by_operator = 0 "
        "GROUP BY u.id "
        "ORDER BY last_time DESC"
    ).fetchall()

    if not rows:
        await message.answer("Нет новых сообщений от участников.")
        return

    text = " Активные обращения:\n\n" + "\n\n".join(
        f" {r['full_name']} (peer_id={r['vk_user_id']}) — {r['unread']} сообщ.\n"
        f"   Последнее: {r['last_msg'][:80]}"
        for r in rows
    )
    text += "\n\nОтветить: /answer <peer_id> <текст>"
    await message.answer(text)