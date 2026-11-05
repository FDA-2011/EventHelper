from vkbottle.bot import Bot, Message, BotLabeler
from vkbottle import (
    BaseStateGroup, PhotoMessageUploader,
    GroupEventType, GroupTypes,
)

from database import db
from helpers import validate_email, validate_phone, generate_qr, crm_register

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
async def on_group_join(event: GroupTypes.GroupJoin, bot: Bot):
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
        "/search (название доклада) — поиск докладов\n"
        "/schedule_add ID — добавить доклад в расписание\n"
        "/schedule_remove ID — убрать доклад\n"
        "/my_schedule — экспорт личного расписания в календарь\n"
        "/map — карта площадки\n"
        "/route — маршрут\n"
        "/speaker — профиль спикера\n"
        "/ask — вопрос спикеру\n"
        "/find — поиск участников\n"
        "/poll — оценка доклада\n"
        "/broadcast — рассылка (админ)\n"
        "/faq — частые вопросы\n"
        "/support — оператор"
    )


# ---------- Пошаговая регистрация (FSM) ----------
@router.message(text="/register")
async def reg_start(message: Message, bot: Bot):
    await bot.state_dispenser.set(message.peer_id, RegForm.full_name)
    await message.answer("Введите ваше ФИО:")


@router.message(state=RegForm.full_name)
async def reg_name(message: Message, bot: Bot):
    text = message.text.strip()
    if len(text.split()) < 2:
        await message.answer("Укажите минимум фамилию и имя.")
        return
    await bot.state_dispenser.set(
        message.peer_id, RegForm.organization, full_name=text
    )
    await message.answer("Организация:")


@router.message(state=RegForm.organization)
async def reg_org(message: Message, bot: Bot):
    p = message.state_peer.payload
    await bot.state_dispenser.set(
        message.peer_id, RegForm.region,
        full_name=p["full_name"], organization=message.text.strip(),
    )
    await message.answer("Регион:")


@router.message(state=RegForm.region)
async def reg_region(message: Message, bot: Bot):
    p = message.state_peer.payload
    await bot.state_dispenser.set(
        message.peer_id, RegForm.position,
        full_name=p["full_name"], organization=p["organization"],
        region=message.text.strip(),
    )
    await message.answer("Должность:")


@router.message(state=RegForm.position)
async def reg_position(message: Message, bot: Bot):
    p = message.state_peer.payload
    await bot.state_dispenser.set(
        message.peer_id, RegForm.email,
        full_name=p["full_name"], organization=p["organization"],
        region=p["region"], position=message.text.strip(),
    )
    await message.answer("E‑mail:")


@router.message(state=RegForm.email)
async def reg_email(message: Message, bot: Bot):
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


@router.message(state=RegForm.phone)
async def reg_phone(message: Message, bot: Bot):
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


@router.message(state=RegForm.confirm)
async def reg_confirm(message: Message, bot: Bot):
    if message.text.strip().lower() not in ("да", "yes", "подтверждаю"):
        await bot.state_dispenser.delete(message.peer_id)
        await message.answer("Регистрация отменена. /register — начать заново.")
        return

    data = message.state_peer.payload
    await bot.state_dispenser.delete(message.peer_id)

    crm_id = crm_register(data)
    if not crm_id:
        await message.answer("⚠️ Не удалось связаться с CRM.")
        return

    qr_data = f"BADGE:{crm_id}:{data['full_name']}"

    db.upsert_user(message.from_id or message.peer_id, {
        "full_name": data["full_name"],
        "organization": data["organization"],
        "region": data["region"],
        "position": data["position"],
        "email": data["email"],
        "phone": data["phone"],
        "qr_code_data": qr_data,
        "registration_status": "confirmed",
    })

    qr_buf = generate_qr(qr_data)
    uploader = PhotoMessageUploader(bot.api)
    photo = await uploader.upload(qr_buf, peer_id=message.peer_id)
    await message.answer(
        message=f"✅ Регистрация подтверждена!\nQR-код бейджа во вложении.\nID: {crm_id}",
        attachment=photo,
    )


@router.message(text="/cancel_reg")
async def cancel_reg(message: Message, bot: Bot):
    await bot.state_dispenser.delete(message.peer_id)
    user = db.get_user(message.from_id or message.peer_id)
    if user:
        db.update("users", {"registration_status": "cancelled"}, {"id": user["id"]})
    await message.answer("Регистрация отменена.")


@router.message(text="/edit_reg")
async def edit_reg(message: Message, bot: Bot):
    await bot.state_dispenser.delete(message.peer_id)
    await bot.state_dispenser.set(message.peer_id, RegForm.full_name)
    await message.answer("Введите новые ФИО:")