from vkbottle.bot import Message, BotLabeler
from vkbottle import (
    BaseStateGroup, PhotoMessageUploader, Keyboard, Text,
    GroupEventType, GroupTypes,
)

from bot_instance import bot
from database import db
from config import ADMIN_IDS
from helpers import (
    validate_email,
    validate_phone,
    generate_qr,
    crm_register,
    encrypt_text,
)

router = BotLabeler()
router.vbml_ignore_case = True
FULL_ACCESS_STATUSES = {"confirmed"}
PENDING_ALLOWED = {
    "/my_qr", "/cancel_reg", "/help", "/start", "/register", "/cancel",
}
ADMIN_ALLOWED = {
    "/broadcast", "/emergency", "/support_list", "/reply", "/answer",
    "/admin_help", "/start", "/help", "/cancel",
}


def _is_admin(peer_id: int) -> bool:
    return peer_id in ADMIN_IDS


def _user_status(peer_id: int) -> str | None:
    user = db.get_user(peer_id)
    return user.get("registration_status") if user else None


def _block_matcher(m: Message) -> bool:
    """True  блокировать, False  пропустить."""
    peer_id = m.peer_id
    status = _user_status(peer_id)
    if status in FULL_ACCESS_STATUSES:
        return False

    text = (m.text or "").strip()
    text_lower = text.lower()
    cmd = text_lower.split(maxsplit=1)[0] if text_lower else ""
    if cmd == "/register" or text_lower == "/cancel":
        return False
    if _is_admin(peer_id) and cmd in ADMIN_ALLOWED:
        return False
    if status == "pending" and cmd in PENDING_ALLOWED:
        return False
    state_peer = getattr(m, "state_peer", None)
    if state_peer and getattr(state_peer, "state", None):
        if not text.startswith("/"):
            return False

    return True


@router.message(func=_block_matcher)
async def block_unregistered(message: Message):
    status = _user_status(message.peer_id)

    if status == "pending":
        kb = Keyboard(one_time=False)
        kb.add(Text("/my_qr")).add(Text("/cancel_reg"))
        await message.answer(
            "⏳ Ваша заявка на регистрацию ещё на рассмотрении.\n\n"
            "Доступные команды:\n"
            " /my_qr — статус заявки\n"
            " /cancel_reg — отменить заявку\n"
            " /help — помощь",
            keyboard=kb.get_json(),
        )
        return

    kb = Keyboard(one_time=False).add(Text("/register"))
    await message.answer(
        " Для использования бота пройдите регистрацию.\n\n"
        "Отправьте /register или нажмите кнопку ниже.",
        keyboard=kb.get_json(),
    )
HELP_TEXT = (
    " Все команды бота:\n\n"
    " /program — программа форума\n"
    " /my_schedule — расписание в календарь (.ics)\n"
    " /search <слово> — поиск докладов\n"
    " /speaker <ФИО> — профиль спикера\n"
    " /map — карта площадки\n"
    " /poll — оценить доклад\n"
    " /ask — задать вопрос спикеру\n"
    " /find <запрос> — поиск участников\n"
    " /my_qr — QR-код бейджа\n"
    " /support — связаться с оператором\n"
    " /edit_reg — изменить данные\n"
    " /cancel_reg — отменить заявку\n\n"
    "Команды с < > — введите аргумент через пробел.\n"
    "Или нажмите кнопку ниже — команда выполнится сама."
)

HELP_TEXT_PENDING = (
    " Ваша заявка на регистрацию на рассмотрении администратора.\n\n"
    "Доступные команды:\n"
    " /my_qr — статус заявки\n"
    " /cancel_reg — отменить заявку\n"
    " /help — это сообщение\n"
    " /start — главное меню\n\n"
    "Остальные команды откроются после одобрения."
)


def _help_keyboard() -> str:
    kb = Keyboard(one_time=False)
    kb.add(Text("/program")).add(Text("/my_schedule")).row()
    kb.add(Text("/search")).add(Text("/speaker")).row()
    kb.add(Text("/map")).add(Text("/poll")).row()
    kb.add(Text("/ask")).add(Text("/find")).row()
    kb.add(Text("/my_qr")).add(Text("/support")).row()
    kb.add(Text("/edit_reg")).add(Text("/cancel_reg"))
    return kb.get_json()


def _pending_keyboard() -> str:
    kb = Keyboard(one_time=False)
    kb.add(Text("/my_qr")).add(Text("/cancel_reg"))
    return kb.get_json()
@router.message(text=["/start", "начать"])
async def cmd_start(message: Message):
    status = _user_status(message.peer_id)

    if status == "pending":
        await message.answer(HELP_TEXT_PENDING, keyboard=_pending_keyboard())
        return

    if status == "confirmed":
        await message.answer(HELP_TEXT, keyboard=_help_keyboard())
        return
    kb = Keyboard(one_time=False).add(Text("/register"))
    await message.answer(
        " Для использования бота пройдите регистрацию.",
        keyboard=kb.get_json(),
    )


@router.message(text=["/help", "help", "помощь"])
async def cmd_help(message: Message):
    status = _user_status(message.peer_id)

    if status == "pending":
        await message.answer(HELP_TEXT_PENDING, keyboard=_pending_keyboard())
        return

    if status == "confirmed":
        await message.answer(HELP_TEXT, keyboard=_help_keyboard())
        return

    kb = Keyboard(one_time=False).add(Text("/register"))
    await message.answer(
        " Для использования бота пройдите регистрацию.",
        keyboard=kb.get_json(),
    )
@router.message(text="/cancel")
async def cancel_state(message: Message):
    await bot.state_dispenser.delete(message.peer_id)
    await message.answer("Действие отменено. Список команд: /help")
class RegForm(BaseStateGroup):
    full_name = "full_name"
    organization = "organization"
    region = "region"
    position = "position"
    email = "email"
    phone = "phone"
    confirm = "confirm"


@router.raw_event(GroupEventType.GROUP_JOIN, dataclass=GroupTypes.GroupJoin)
async def on_group_join(event: GroupTypes.GroupJoin):
    await bot.api.messages.send(
        peer_id=event.object.user_id,
        message=(
            "Добро пожаловать на форум! \n\n"
            " Для использования бота нужна регистрация.\n"
            "Пройдите её командой /register."
        ),
        random_id=0,
    )


@router.message(text="/register")
async def reg_start(message: Message):
    existing = db.get_user(message.peer_id)

    if existing:
        status = existing.get("registration_status")

        if status == "confirmed":
            await message.answer(
                " Вы уже зарегистрированы.\n\n"
                " Получить QR-код: /my_qr\n"
                " Изменить данные: /edit_reg"
            )
            return

        if status == "pending":
            await message.answer(
                "⏳ Ваша заявка уже на рассмотрении.\n\n"
                " Статус: /my_qr\n"
                " Отменить: /cancel_reg\n"
                " Изменить данные: /edit_reg"
            )
            return

    await bot.state_dispenser.set(message.peer_id, RegForm.full_name)
    await message.answer("Введите ваше ФИО:")


@router.message(
    state=RegForm.full_name,
    func=lambda m: m.text and not m.text.startswith("/"),
)
async def reg_name(message: Message):
    text = message.text.strip()
    if len(text.split()) < 2:
        await message.answer("Укажите минимум фамилию и имя.")
        return
    await bot.state_dispenser.set(
        message.peer_id, RegForm.organization, full_name=text
    )
    await message.answer("Организация:")


@router.message(
    state=RegForm.organization,
    func=lambda m: m.text and not m.text.startswith("/"),
)
async def reg_org(message: Message):
    p = message.state_peer.payload
    await bot.state_dispenser.set(
        message.peer_id, RegForm.region,
        full_name=p["full_name"], organization=message.text.strip(),
    )
    await message.answer("Регион:")


@router.message(
    state=RegForm.region,
    func=lambda m: m.text and not m.text.startswith("/"),
)
async def reg_region(message: Message):
    p = message.state_peer.payload
    await bot.state_dispenser.set(
        message.peer_id, RegForm.position,
        full_name=p["full_name"], organization=p["organization"],
        region=message.text.strip(),
    )
    await message.answer("Должность:")


@router.message(
    state=RegForm.position,
    func=lambda m: m.text and not m.text.startswith("/"),
)
async def reg_position(message: Message):
    p = message.state_peer.payload
    await bot.state_dispenser.set(
        message.peer_id, RegForm.email,
        full_name=p["full_name"], organization=p["organization"],
        region=p["region"], position=message.text.strip(),
    )
    await message.answer("E‑mail:")


@router.message(
    state=RegForm.email,
    func=lambda m: m.text and not m.text.startswith("/"),
)
async def reg_email(message: Message):
    email = message.text.strip()
    if not validate_email(email):
        await message.answer("Некорректный e‑mail, попробуйте снова:")
        return
    p = message.state_peer.payload
    await bot.state_dispenser.set(
        message.peer_id, RegForm.phone,
        full_name=p["full_name"], organization=p["organization"],
        region=p["region"], position=p["position"], email=email,
    )
    await message.answer("Телефон (+7 999 123-45-67):")


@router.message(
    state=RegForm.phone,
    func=lambda m: m.text and not m.text.startswith("/"),
)
async def reg_phone(message: Message):
    phone = message.text.strip()
    if not validate_phone(phone):
        await message.answer("Неверный формат телефона, попробуйте снова:")
        return
    p = message.state_peer.payload
    data = {
        "full_name": p["full_name"], "organization": p["organization"],
        "region": p["region"], "position": p["position"],
        "email": p["email"], "phone": phone,
    }
    await bot.state_dispenser.set(message.peer_id, RegForm.confirm, **data)
    await message.answer(
        "Проверьте данные:\n"
        f" {data['full_name']}\n {data['organization']}\n {data['region']}\n"
        f" {data['position']}\n {data['email']}\n {data['phone']}\n\n"
        "Всё верно? Отправьте «да» или /register для отмены."
    )


@router.message(
    state=RegForm.confirm,
    func=lambda m: m.text and not m.text.startswith("/"),
)
async def reg_confirm(message: Message):
    if message.text.strip().lower() not in ("да", "yes", "подтверждаю"):
        await bot.state_dispenser.delete(message.peer_id)
        await message.answer("Регистрация отменена. /register — начать заново.")
        return

    current = db.get_user(message.peer_id)
    if current:
        status = current.get("registration_status")
        if status == "confirmed":
            await bot.state_dispenser.delete(message.peer_id)
            await message.answer(
                "ℹ Ваша регистрация уже подтверждена ранее.\n\n"
                " Получить QR-код: /my_qr"
            )
            return
        if status == "pending":
            await bot.state_dispenser.delete(message.peer_id)
            await message.answer(
                "⏳ Заявка уже на рассмотрении.\n"
                "Дождитесь решения администратора."
            )
            return

    data = message.state_peer.payload
    await bot.state_dispenser.delete(message.peer_id)

    crm_id = crm_register(data)
    if not crm_id:
        await message.answer(" Не удалось связаться с CRM.")
        return

    qr_data = f"BADGE:{crm_id}:{data['full_name']}"

    db.upsert_user(message.peer_id, {
        "full_name": data["full_name"],
        "organization": data["organization"],
        "region": data["region"],
        "position": data["position"],
        "email": encrypt_text(data["email"]),
        "phone": encrypt_text(data["phone"]),
        "qr_code_data": qr_data,
        "registration_status": "pending",
    })

    await message.answer(
        " Заявка на регистрацию отправлена!\n\n"
        "Она поступила на рассмотрение администратора. "
        "После одобрения вам станут доступны все команды бота.\n\n"
        " Проверить статус: /my_qr\n"
        f"Номер заявки: {crm_id}"
    )
@router.message(text="/my_qr")
async def my_qr(message: Message):
    user = db.get_user(message.peer_id)
    if not user:
        await message.answer(
            "Вы ещё не регистрировались.\nПройдите регистрацию: /register"
        )
        return

    status = user.get("registration_status")

    if status == "pending":
        await message.answer(
            "⏳ Ваша заявка ещё на рассмотрении.\n"
            "Мы уведомим вас, когда её одобрят."
        )
        return

    if status == "cancelled":
        await message.answer(
            " Ваша заявка отменена или отклонена.\n"
            "Пройти регистрацию заново: /register"
        )
        return

    if status == "confirmed":
        qr_data = user.get("qr_code_data")
        if not qr_data:
            await message.answer(
                " QR-код не найден. Обратитесь к администратору."
            )
            return

        try:
            qr_buf = generate_qr(qr_data)
            uploader = PhotoMessageUploader(bot.api)
            photo = await uploader.upload(qr_buf, peer_id=message.peer_id)
            await message.answer(
                message=" Ваш QR-код для бейджа:",
                attachment=photo,
            )
        except Exception as e:
            await message.answer(f" Не удалось сформировать QR: {e}")
        return

    await message.answer(
        "Не удалось определить статус регистрации. Обратитесь к администратору."
    )
@router.message(text="/cancel_reg")
async def cancel_reg(message: Message):
    await bot.state_dispenser.delete(message.peer_id)

    user = db.get_user(message.peer_id)
    if not user:
        await message.answer("У вас нет активной заявки.")
        return

    status = user.get("registration_status")

    if status == "cancelled":
        await message.answer(
            "Заявка уже отменена.\nПройти регистрацию заново: /register"
        )
        return

    db.update("users", {"registration_status": "cancelled"}, {"id": user["id"]})
    await message.answer(" Заявка отменена.\n\nПройти заново: /register")
@router.message(text="/edit_reg")
async def edit_reg(message: Message):
    await bot.state_dispenser.delete(message.peer_id)

    user = db.get_user(message.peer_id)
    if not user:
        await message.answer(
            "Вы ещё не регистрировались.\nНачать: /register"
        )
        return

    status = user.get("registration_status")

    if status == "confirmed":
        await message.answer(
            " Изменение данных подтверждённой регистрации.\n"
            "После заполнения заявка снова уйдёт на модерацию.\n\n"
            "Введите новые ФИО:"
        )
    elif status == "pending":
        await message.answer(
            " Изменение заявки на модерации.\n\n"
            "Введите новые ФИО:"
        )
    else:
        await message.answer("Введите новые ФИО:")

    await bot.state_dispenser.set(message.peer_id, RegForm.full_name)