import os
import logging
from vkbottle.bot import Message, BotLabeler
from vkbottle import (
    BaseStateGroup, PhotoMessageUploader,
    GroupEventType, GroupTypes,
)

from bot_instance import bot
from database import db
from helpers import validate_email, validate_phone, generate_qr, crm_register

logger = logging.getLogger(__name__)
router = BotLabeler()
router.vbml_ignore_case = True

QR_DIR = "qr_codes"
os.makedirs(QR_DIR, exist_ok=True)

class RegForm(BaseStateGroup):
    full_name = "full_name"
    organization = "organization"
    region = "region"
    position = "position"
    email = "email"
    phone = "phone"
    confirm = "confirm"

@router.message(text=["/start", "начать"])
async def cmd_start(message: Message):
    await bot.state_dispenser.delete(message.peer_id)
    await message.answer(
        "Команды:\n"
        "/register — регистрация\n"
        "/cancel — отменить действие\n"
        "/program — программа\n"
        "/search — поиск докладов\n"
        "/my_schedule — экспорт в календарь\n"
        "/map — карта площадки\n"
        "/route — маршрут\n"
        "/speaker — профиль спикера\n"
        "/ask — вопрос спикеру\n"
        "/find — поиск участников\n"
        "/poll — оценка доклада\n"
        "/my_qr — получить QR-код\n"
        "/edit_reg — изменить данные"
    )

@router.message(text="/cancel")
async def cancel_state(message: Message):
    await bot.state_dispenser.delete(message.peer_id)
    await message.answer("Действие отменено. /start")

@router.message(text="/register")
async def reg_start(message: Message):
    user = db.get_user(message.peer_id)
    if user and user.get("registration_status") == "confirmed":
        await message.answer("Вы уже зарегистрированы! ✅\nQR-код: /my_qr")
        return
    elif user and user.get("registration_status") == "pending":
        await message.answer("Ваша заявка на модерации. Пожалуйста, подождите.")
        return

    await bot.state_dispenser.set(message.peer_id, RegForm.full_name)
    await message.answer("Введите ваше ФИО:")

@router.message(state=RegForm.full_name, func=lambda m: m.text and not m.text.startswith("/"))
async def reg_name(message: Message):
    text = message.text.strip()
    if len(text.split()) < 2:
        await message.answer("Укажите минимум фамилию и имя.")
        return
    await bot.state_dispenser.set(message.peer_id, RegForm.organization, full_name=text)
    await message.answer("Организация:")

@router.message(state=RegForm.organization, func=lambda m: m.text and not m.text.startswith("/"))
async def reg_org(message: Message):
    p = message.state_peer.payload
    await bot.state_dispenser.set(message.peer_id, RegForm.region, full_name=p["full_name"], organization=message.text.strip())
    await message.answer("Регион:")

@router.message(state=RegForm.region, func=lambda m: m.text and not m.text.startswith("/"))
async def reg_region(message: Message):
    p = message.state_peer.payload
    await bot.state_dispenser.set(message.peer_id, RegForm.position, full_name=p["full_name"], organization=p["organization"], region=message.text.strip())
    await message.answer("Должность:")

@router.message(state=RegForm.position, func=lambda m: m.text and not m.text.startswith("/"))
async def reg_position(message: Message):
    p = message.state_peer.payload
    await bot.state_dispenser.set(message.peer_id, RegForm.email, full_name=p["full_name"], organization=p["organization"], region=p["region"], position=message.text.strip())
    await message.answer("E‑mail:")

@router.message(state=RegForm.email, func=lambda m: m.text and not m.text.startswith("/"))
async def reg_email(message: Message):
    email = message.text.strip()
    if not validate_email(email):
        await message.answer("Некорректный e‑mail, попробуйте снова:")
        return
    p = message.state_peer.payload
    await bot.state_dispenser.set(message.peer_id, RegForm.phone, full_name=p["full_name"], organization=p["organization"], region=p["region"], position=p["position"], email=email)
    await message.answer("Телефон (+7 999 123-45-67):")

@router.message(state=RegForm.phone, func=lambda m: m.text and not m.text.startswith("/"))
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
        "Всё верно? Отправьте «да» или /cancel."
    )

@router.message(state=RegForm.confirm, func=lambda m: m.text and not m.text.startswith("/"))
async def reg_confirm(message: Message):
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

    db.upsert_user(message.peer_id, {
        "full_name": data["full_name"],
        "organization": data["organization"],
        "region": data["region"],
        "position": data["position"],
        "email": data["email"],
        "phone": data["phone"],
        "qr_code_data": qr_data,
        "registration_status": "pending",
    })

    await message.answer(
        "✅ Заявка отправлена!\n"
        "Ожидайте подтверждения от администратора. Как только вас одобрят, вы сможете получить QR-код командой /my_qr."
    )

@router.message(text="/my_qr")
async def my_qr(message: Message):
    user = db.get_user(message.peer_id)
    if not user or not user.get("qr_code_data"):
        await message.answer("Вы ещё не зарегистрированы. Используйте /register.")
        return
    if user.get("registration_status") != "confirmed":
        await message.answer("⏳ Ваша заявка ещё не одобрена администратором. Пожалуйста, подождите.")
        return

    try:
        qr_buf = generate_qr(user["qr_code_data"])
        uploader = PhotoMessageUploader(bot.api)
        photo = await uploader.upload(qr_buf, peer_id=message.peer_id)
        await message.answer(message="Ваш QR-код для прохода:", attachment=photo)
    except Exception as e:
        logger.error("Ошибка при получении /my_qr: %s", e, exc_info=True)
        await message.answer("⚠️ Не удалось отправить QR-код. Попробуйте позже.")

@router.message(text="/edit_reg")
async def edit_reg(message: Message):
    user = db.get_user(message.peer_id)
    if not user or user.get("registration_status") != "confirmed":
        await message.answer("Вы ещё не зарегистрированы или не одобрены.")
        return
    await bot.state_dispenser.delete(message.peer_id)
    await bot.state_dispenser.set(message.peer_id, RegForm.full_name)
    await message.answer("Введите новые ФИО:")