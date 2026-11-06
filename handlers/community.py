import logging
from vkbottle.bot import Message, BotLabeler
from vkbottle import BaseStateGroup, Keyboard, Callback, GroupEventType
from vkbottle.bot import MessageEvent

from bot_instance import bot
from config import ADMIN_IDS, OPERATOR_PEER_ID
from database import db

logger = logging.getLogger(__name__)
router = BotLabeler()
router.vbml_ignore_case = True

PENDING_POLLS = {}


class Feedback(BaseStateGroup):
    comment = "comment"


class Support(BaseStateGroup):
    waiting = "waiting"


@router.message(text=["/find", "/find <query>"])
async def find(message: Message, query: str = None):
    if not query:
        await message.answer("Использование: /find <регион/компания/ФИО>")
        return

    q = f"%{query.lower().strip()}%"
    rows = db.con.execute(
        "SELECT full_name, organization, region FROM users "
        "WHERE registration_status = 'confirmed' "
        "AND (LOWER(organization) LIKE ? OR LOWER(region) LIKE ? OR LOWER(full_name) LIKE ?)",
        (q, q, q),
    ).fetchall()
    if not rows:
        await message.answer("Никого не найдено. Убедитесь, что пользователи одобрены в админке.")
        return
    await message.answer(
        f"Найдено: {len(rows)}\n" + "\n".join(
            f"• {r['full_name']} — {r['organization']}, {r['region']}"
            for r in rows
        )
    )


@router.message(text="/poll")
async def poll_start(message: Message):
    sessions = db.con.execute("SELECT id, title FROM sessions ORDER BY start_time").fetchall()
    if not sessions:
        await message.answer("Программа ещё не загружена.")
        return

    kb = Keyboard(inline=True)
    for s in sessions:
        title = s["title"] if len(s["title"]) <= 30 else s["title"][:27] + "..."
        kb.add(Callback(title, payload={"action": "poll_select", "session_id": s["id"]}))
        kb.row()

    await message.answer("Выберите доклад для оценки:", keyboard=kb.get_json())


@router.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=MessageEvent)
async def poll_callback(event: MessageEvent):
    payload = event.payload or {}
    uid = event.user_id

    if payload.get("action") == "poll_select":
        try:
            await event.show_snackbar("Доклад выбран!")
        except:
            pass
        session_id = payload["session_id"]

        PENDING_POLLS[uid] = {"session_id": session_id}

        kb = Keyboard(inline=True)
        for i in range(1, 6):
            kb.add(Callback(f"{i} ⭐", payload={"rate": i}))
            if i != 5: kb.row()

        await event.send_message("Оцените доклад от 1 до 5:", keyboard=kb.get_json())

    elif "rate" in payload:
        try:
            await event.show_snackbar("Оценка принята!")
        except:
            pass
        score = payload["rate"]

        poll_data = PENDING_POLLS.get(uid)
        if not poll_data:
            await event.send_message("Ошибка: сессия истекла. Начните заново /poll")
            return

        PENDING_POLLS[uid]["rating"] = score
        await bot.state_dispenser.set(event.peer_id, Feedback.comment)

        await event.send_message(f"Оценка: {score}\nКомментарий (или «-» для пропуска):")


@router.message(state=Feedback.comment, func=lambda m: m.text and not m.text.startswith("/"))
async def poll_comment(message: Message):
    text = message.text.strip()
    await bot.state_dispenser.delete(message.peer_id)

    uid = message.from_id
    poll_data = PENDING_POLLS.pop(uid, None) or PENDING_POLLS.pop(message.peer_id, None)

    if not poll_data:
        await message.answer("Ошибка: данные об оценке не найдены.")
        return

    user = db.get_user(message.peer_id)
    if user:
        db.insert("feedback", {
            "user_id": user["id"],
            "target_type": "session",
            "target_id": poll_data.get("session_id"),
            "rating": poll_data.get("rating"),
            "comment": "" if text == "-" else text,
        })
        await message.answer("✅ Спасибо за обратную связь!")
    else:
        await message.answer("Вы не зарегистрированы, оценка не сохранена.")


@router.message(text=["/broadcast <text>"])
async def broadcast(message: Message, text: str = None):
    if message.peer_id not in ADMIN_IDS:
        await message.answer("⛔ Недостаточно прав.")
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
        await message.answer("⛔ Недостаточно прав.")
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


@router.message(text="/faq")
async def faq_list(message: Message):
    rows = db.select("faq")
    if not rows:
        await message.answer("FAQ пока не заполнен.")
        return
    text = "📚 Частые вопросы:\n\n" + "\n\n".join(
        f"• {r['question']}: {r['answer']}" for r in rows
    )
    text += "\n\n🆘 Поддержка: /support"
    await message.answer(text)


@router.message(text="/support")
async def support_cmd(message: Message):
    await bot.state_dispenser.set(message.peer_id, Support.waiting)
    await message.answer(
        "Вы подключены к линии поддержки. Опишите вопрос — оператор ответит.\n"
        "Для выхода: /end_support"
    )


@router.message(state=Support.waiting, func=lambda m: m.text and not m.text.startswith("/"))
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
            message=f"🆘 {message.peer_id}:\n{message.text}",
            random_id=0,
        )
    except Exception as e:
        logger.error("Support forward: %s", e)
    await message.answer("Сообщение передано оператору.")


@router.message(text="/end_support")
async def end_support(message: Message):
    await bot.state_dispenser.delete(message.peer_id)
    await message.answer("Вы вышли из режима поддержки.")