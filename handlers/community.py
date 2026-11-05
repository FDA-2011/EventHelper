import logging

from vkbottle.bot import Bot, Message, BotLabeler
from vkbottle import BaseStateGroup, Keyboard, Callback

from config import ADMIN_IDS, OPERATOR_PEER_ID
from database import db

logger = logging.getLogger(__name__)
router = BotLabeler()
router.vbml_ignore_case = True


class Feedback(BaseStateGroup):
    rating = "rating"
    comment = "comment"


class Support(BaseStateGroup):
    waiting = "waiting"


# ---------- Нетворкинг ----------
@router.message(func=lambda m: m.text and m.text.lower().startswith("/find "))
async def find(message: Message):
    query = message.text[len("/find "):].strip()
    if not query:
        await message.answer("Использование: /find <регион/компания>")
        return
    q = f"%{query.lower()}%"
    rows = db.con.execute(
        "SELECT full_name, organization, region FROM users "
        "WHERE registration_status = 'confirmed' "
        "AND (LOWER(organization) LIKE ? OR LOWER(region) LIKE ?)",
        (q, q),
    ).fetchall()
    if not rows:
        await message.answer("Никого не найдено.")
        return
    await message.answer(
        f"Найдено: {len(rows)}\n" + "\n".join(
            f"• {r['full_name']} — {r['organization']}, {r['region']}"
            for r in rows
        )
    )


@router.message(text="/find")
async def find_usage(message: Message):
    await message.answer("Использование: /find <регион/компания>")


# ---------- Опрос ----------
@router.message(text="/poll")
async def poll_start(message: Message, bot: Bot):
    session = db.get_first_session()
    if not session:
        await message.answer("Программа ещё не загружена.")
        return
    await bot.state_dispenser.set(
        message.peer_id, Feedback.rating, session_id=session["id"]
    )
    kb = Keyboard(inline=True)
    for s in range(1, 6):
        kb.add(Callback(f"{s} ⭐", payload={"rate": s}))
        if s != 5:
            kb.row()
    await message.answer(
        f"Оцените доклад «{session['title']}» от 1 до 5:",
        keyboard=kb.get_json(),
    )


@router.message(state=Feedback.rating)
async def poll_rate(message: Message, bot: Bot):
    payload = message.payload or {}
    if "rate" not in payload:
        await message.answer("Нажмите на кнопку с оценкой.")
        return
    score = payload["rate"]
    p = message.state_peer.payload
    await bot.state_dispenser.set(
        message.peer_id, Feedback.comment,
        session_id=p.get("session_id"), rating=score,
    )
    await message.answer(f"Оценка: {score}\nКомментарий (или «-» для пропуска):")


@router.message(state=Feedback.comment)
async def poll_comment(message: Message, bot: Bot):
    text = message.text.strip()
    p = message.state_peer.payload
    await bot.state_dispenser.delete(message.peer_id)

    user = db.get_user(message.peer_id)
    if user:
        db.insert("feedback", {
            "user_id": user["id"],
            "target_type": "session",
            "target_id": p.get("session_id"),
            "rating": p.get("rating"),
            "comment": "" if text == "-" else text,
        })
    await message.answer("✅ Спасибо за обратную связь!")


# ---------- Админ: рассылка ----------
@router.message(func=lambda m: m.text and m.text.lower().startswith("/broadcast"))
async def broadcast(message: Message, bot: Bot):
    if message.peer_id not in ADMIN_IDS:
        await message.answer("⛔ Недостаточно прав.")
        return
    text = message.text[len("/broadcast"):].strip()
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


@router.message(func=lambda m: m.text and m.text.lower().startswith("/emergency"))
async def emergency(message: Message, bot: Bot):
    if message.peer_id not in ADMIN_IDS:
        await message.answer("⛔ Недостаточно прав.")
        return
    text = message.text[len("/emergency"):].strip()
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


# ---------- FAQ ----------
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


# ---------- Поддержка ----------
@router.message(text="/support")
async def support_cmd(message: Message, bot: Bot):
    await bot.state_dispenser.set(message.peer_id, Support.waiting)
    await message.answer(
        "Вы подключены к линии поддержки. Опишите вопрос — оператор ответит.\n"
        "Для выхода: /end_support"
    )


@router.message(state=Support.waiting)
async def forward_support(message: Message, bot: Bot):
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
async def end_support(message: Message, bot: Bot):
    await bot.state_dispenser.delete(message.peer_id)
    await message.answer("Вы вышли из режима поддержки.")