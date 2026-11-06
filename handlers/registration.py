from vkbottle.bot import Message, BotLabeler
from vkbottle import (
    BaseStateGroup, PhotoMessageUploader,
    GroupEventType, GroupTypes,
)

from bot_instance import bot
from database import db
from helpers import (
    validate_email,
    validate_phone,
    generate_qr,
    crm_register,
    encrypt_text,
)

router = BotLabeler()
router.vbml_ignore_case = True


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
            "Добро пожаловать на форум! 👋\n"
            "Я помогу с регистрацией, программой, вопросами спикерам и поддержкой.\n"
            "Начните с /register или /start."
        ),
        random_id=0,
    )


@router.message(text=["/start", "начать"])
async def cmd_start(message: Message):
    await message.answer(
        "Команды:\n"
        "/register — регистрация\n"
        "/program — программа\n"
        "/search — поиск докладов\n"
        "/my_schedule — экспорт в календарь\n"
        "/map — карта площадки\n"
        "/speaker — профиль спикера\n"
        "/ask — вопрос спикеру\n"
        "/find — поиск участников\n"
        "/poll — оценка доклада\n"
        "/my_qr — получить QR-код бейджа\n"
        "/support — написать в чат с поддержкой\n"
        "/edit_reg — изменить данные"
    )


@router.message(text="/register")
async def reg_start(message: Message):
    # Сбросим прошлую заявку, если была — начинаем с чистого листа
    existing = db.get_user(message.peer_id)
    if existing and existing.get("registration_status") == "confirmed":
        await message.answer(
            "Вы уже зарегистрированы. Чтобы получить QR-код — /my_qr.\n"
            "Для изменения данных — /edit_reg."
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
        f"👤 {data['full_name']}\n🏢 {data['organization']}\n🌍 {data['region']}\n"
        f"💼 {data['position']}\n📧 {data['email']}\n📞 {data['phone']}\n\n"
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

    data = message.state_peer.payload
    await bot.state_dispenser.delete(message.peer_id)

    # В CRM уходит plaintext
    crm_id = crm_register(data)
    if not crm_id:
        await message.answer("⚠️ Не удалось связаться с CRM.")
        return

    qr_data = f"BADGE:{crm_id}:{data['full_name']}"

    # Заявка сохраняется со статусом pending — ждёт одобрения админа.
    # QR-код пока не отправляем, только сохраняем в qr_code_data.
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
        "📝 Заявка на регистрацию отправлена!\n\n"
        "Она поступила на рассмотрение администратора. "
        "После одобрения вы получите уведомление в этом чате.\n\n"
        "Чтобы получить QR-код бейджа после одобрения, отправьте /my_qr.\n"
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
            "⏳ Ваша заявка ещё на рассмотрении администратора.\n"
            "Мы уведомим вас, когда она будет одобрена."
        )
        return

    if status == "cancelled":
        await message.answer(
            "❌ Ваша заявка отклонена.\n"
            "Вы можете пройти регистрацию заново: /register"
        )
        return

    if status == "confirmed":
        qr_data = user.get("qr_code_data")
        if not qr_data:
            await message.answer(
                "⚠️ QR-код не найден. Обратитесь к администратору."
            )
            return

        try:
            qr_buf = generate_qr(qr_data)
            uploader = PhotoMessageUploader(bot.api)
            photo = await uploader.upload(qr_buf, peer_id=message.peer_id)
            await message.answer(
                message="🎫 Ваш QR-код для бейджа:",
                attachment=photo,
            )
        except Exception as e:
            await message.answer(f"⚠️ Не удалось сформировать QR: {e}")
        return

    await message.answer(
        "Не удалось определить статус регистрации. Обратитесь к администратору."
    )


@router.message(text="/cancel_reg")
async def cancel_reg(message: Message):
    await bot.state_dispenser.delete(message.peer_id)
    user = db.get_user(message.peer_id)
    if user:
        db.update("users", {"registration_status": "cancelled"}, {"id": user["id"]})
    await message.answer("Регистрация отменена.")


@router.message(text="/edit_reg")
async def edit_reg(message: Message):
    await bot.state_dispenser.delete(message.peer_id)
    user = db.get_user(message.peer_id)
    if user and user.get("registration_status") == "confirmed":
        await message.answer(
            "Вы уже подтверждены. Изменение данных потребует повторного одобрения.\n"
            "Введите новые ФИО (или /cancel_reg для отмены):"
        )
    else:
        await message.answer("Введите новые ФИО:")
    await bot.state_dispenser.set(message.peer_id, RegForm.full_name)