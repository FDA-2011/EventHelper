import streamlit as st
import sqlite3
import pandas as pd
import requests
import os
from dotenv import load_dotenv

load_dotenv()
st.set_page_config(page_title="Админ-панель Бота", page_icon="🛠️", layout="wide")

VK_TOKEN = os.getenv("VK_BOT_TOKEN", "")
DB_PATH = "bot.db"


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def send_vk_message(user_id: int, text: str):
    if not VK_TOKEN: return False, "Токен не найден"
    url = "https://api.vk.com/method/messages.send"
    payload = {"user_id": user_id, "message": text, "random_id": 0, "access_token": VK_TOKEN, "v": "5.199"}
    try:
        r = requests.post(url, data=payload, timeout=3)
        res = r.json()
        if "error" in res: return False, res["error"].get("error_msg", "Ошибка VK API")
        return True, "OK"
    except Exception as e:
        return False, str(e)


ADMIN_PASS = os.getenv("WEB_ADMIN_PASS", "admin")

with st.sidebar:
    st.title("🛠️ Админ-панель")
    pwd = st.text_input("Введите пароль", type="password")
    if pwd != ADMIN_PASS:
        st.warning("Доступ запрещен.")
        st.stop()

    if st.button("🔄 Обновить данные", use_container_width=True):
        st.rerun()

menu = st.sidebar.radio(
    "Выберите раздел:",
    ["📊 Дашборд", "👥 Пользователи", "❓ Вопросы", "📅 Программа", "🎤 Спикеры", "📍 Локации", "⭐ Отзывы", "💬 FAQ",
     "📢 Рассылка"]
)

conn = get_db()

if menu == "📊 Дашборд":
    st.header("Общая статистика")
    total_users = conn.execute("SELECT COUNT(*) FROM users WHERE registration_status = 'confirmed'").fetchone()[0]
    pending_users = conn.execute("SELECT COUNT(*) FROM users WHERE registration_status = 'pending'").fetchone()[0]
    total_questions = conn.execute("SELECT COUNT(*) FROM questions WHERE status = 'pending'").fetchone()[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("✅ Подтвержденные участники", total_users)
    col2.metric("⏳ Ожидают одобрения", pending_users)
    col3.metric("❓ Вопросов на модерации", total_questions)

elif menu == "👥 Пользователи":
    st.header("Управление пользователями")
    tab1, tab2 = st.tabs(["⏳ На модерации", "✅ Все участники"])

    with tab1:
        pending = conn.execute("SELECT * FROM users WHERE registration_status = 'pending'").fetchall()
        if not pending:
            st.info("Нет пользователей, ожидающих одобрения.")
        else:
            for user in pending:
                with st.container():
                    st.write(f"**{user['full_name']}** ({user['organization']})")
                    st.write(f"Email: {user['email']} | Тел: {user['phone']}")
                    col1, col2 = st.columns([1, 10])
                    if col1.button("Одобрить", key=f"app_{user['id']}"):
                        conn.execute("UPDATE users SET registration_status = 'confirmed' WHERE id = ?", (user["id"],))
                        conn.commit()
                        send_vk_message(user["vk_user_id"], "🎉 Ваша регистрация одобрена! Получите QR-код: /my_qr")
                        st.rerun()
                    if col2.button("Отклонить", key=f"rej_{user['id']}", type="primary"):
                        conn.execute("UPDATE users SET registration_status = 'cancelled' WHERE id = ?", (user["id"],))
                        conn.commit()
                        st.rerun()
                    st.divider()

    with tab2:
        users = pd.read_sql_query(
            "SELECT id, vk_user_id, full_name, organization, registration_status FROM users ORDER BY full_name", conn)
        st.dataframe(users, width="stretch")

elif menu == "❓ Вопросы":
    st.header("Модерация и ответы на вопросы")
    questions = conn.execute(
        "SELECT q.id, q.question_text, q.is_anonymous, q.user_id, sp.full_name AS speaker "
        "FROM questions q LEFT JOIN sessions s ON q.session_id = s.id LEFT JOIN speakers sp ON s.speaker_id = sp.id "
        "WHERE q.status = 'pending'"
    ).fetchall()

    if not questions:
        st.success("Все вопросы обработаны!")
    else:
        for q in questions:
            with st.container():
                anon = "🕵️ Анонимно" if q["is_anonymous"] else "👤 Открыто"
                st.write(f"**Спикер:** {q['speaker']} | **Режим:** {anon}")
                st.info(q["question_text"])

                with st.expander("✍️ Ответить пользователю"):
                    answer = st.text_area("Текст ответа", key=f"ans_{q['id']}")
                    if st.button("Отправить", key=f"btn_ans_{q['id']}"):
                        if answer:
                            user_row = conn.execute("SELECT vk_user_id FROM users WHERE id = ?",
                                                    (q['user_id'],)).fetchone()
                            if user_row:
                                send_vk_message(user_row["vk_user_id"],
                                                f"Ответ на ваш вопрос спикеру {q['speaker']}:\n\n{answer}")
                                conn.execute("UPDATE questions SET status = 'answered', answer_text = ? WHERE id = ?",
                                             (answer, q["id"]))
                                conn.commit()
                                st.success("Ответ отправлен!")
                                st.rerun()

                if st.button("❌ Отклонить / Скрыть вопрос", key=f"rq_{q['id']}"):
                    conn.execute("UPDATE questions SET status = 'rejected' WHERE id = ?", (q["id"],))
                    conn.commit()
                    st.rerun()
                st.divider()

elif menu == "🎤 Спикеры":
    st.header("Управление спикерами")
    with st.form("add_speaker"):
        full_name = st.text_input("ФИО спикера")
        bio = st.text_area("Биография (необязательно)")
        social = st.text_input("Соцсети (необязательно)")
        if st.form_submit_button("Добавить спикера"):
            if full_name:
                conn.execute("INSERT INTO speakers (full_name, bio, social_links) VALUES (?, ?, ?)",
                             (full_name, bio, social))
                conn.commit()
                st.success(f"Спикер {full_name} добавлен!")
                st.rerun()

    speakers = pd.read_sql_query("SELECT id, full_name, bio FROM speakers", conn)
    st.dataframe(speakers, width="stretch")

elif menu == "📍 Локации":
    st.header("Управление локациями (залами)")
    with st.form("add_location"):
        loc_name = st.text_input("Название зала (например, 'Зал А' или 'Коворкинг')")
        if st.form_submit_button("Добавить"):
            if loc_name:
                conn.execute("INSERT INTO locations (name, type) VALUES (?, 'hall')", (loc_name,))
                conn.commit()
                st.success(f"Локация {loc_name} добавлена!")
                st.rerun()

    locations = pd.read_sql_query("SELECT id, name, type FROM locations", conn)
    st.dataframe(locations, width="stretch")
    if not locations.empty:
        del_loc = st.selectbox("Удалить локацию по ID", locations["id"].tolist())
        if st.button("🗑️ Удалить локацию"):
            conn.execute("DELETE FROM locations WHERE id = ?", (del_loc,))
            conn.commit()
            st.rerun()

elif menu == "⭐ Отзывы":
    st.header("Оценки докладов")
    feedbacks = pd.read_sql_query(
        "SELECT f.id, s.title AS session, u.full_name AS user, f.rating, f.comment "
        "FROM feedback f "
        "LEFT JOIN sessions s ON f.target_id = s.id "
        "LEFT JOIN users u ON f.user_id = u.id "
        "ORDER BY f.created_at DESC", conn
    )
    st.dataframe(feedbacks, width="stretch")

elif menu == "📅 Программа":
    st.header("Управление расписанием")
    with st.expander("➕ Добавить новый доклад", expanded=False):
        speakers = conn.execute("SELECT id, full_name FROM speakers").fetchall()
        speaker_options = {f"{s['full_name']}": s['id'] for s in speakers}

        locations = conn.execute("SELECT id, name FROM locations").fetchall()
        loc_options = {f"{l['name']}": l['id'] for l in locations}

        with st.form("add_session"):
            title = st.text_input("Название доклада")
            speaker_name = st.selectbox("Спикер", options=["Без спикера"] + list(speaker_options.keys()))
            loc_name = st.selectbox("Локация (зал)", options=["Без локации"] + list(loc_options.keys()))
            col1, col2 = st.columns(2)
            start_t = col1.text_input("Начало (ГГГГ-ММ-ДД ЧЧ:ММ)", value="2026-11-05 10:00")
            end_t = col2.text_input("Конец (ГГГГ-ММ-ДД ЧЧ:ММ)", value="2026-11-05 11:00")

            if st.form_submit_button("Сохранить"):
                sp_id = speaker_options.get(speaker_name) if speaker_name != "Без спикера" else None
                loc_id = loc_options.get(loc_name) if loc_name != "Без локации" else None
                conn.execute(
                    "INSERT INTO sessions (title, start_time, end_time, speaker_id, location_id) VALUES (?, ?, ?, ?, ?)",
                    (title, start_t, end_t, sp_id, loc_id)
                )
                conn.commit()
                st.success("Доклад добавлен!")
                st.rerun()

    sessions = pd.read_sql_query(
        "SELECT s.id, s.title, sp.full_name as speaker, l.name as hall, s.start_time, s.end_time "
        "FROM sessions s "
        "LEFT JOIN speakers sp ON s.speaker_id = sp.id "
        "LEFT JOIN locations l ON s.location_id = l.id "
        "ORDER BY s.start_time", conn
    )
    if not sessions.empty:
        st.dataframe(sessions, width="stretch")
        delete_id = st.selectbox("Выберите ID доклада для удаления", sessions["id"].tolist())
        if st.button("🗑️ Удалить доклад"):
            conn.execute("DELETE FROM sessions WHERE id = ?", (delete_id,))
            conn.commit()
            st.rerun()

elif menu == "💬 FAQ":
    st.header("Частые вопросы")
    with st.form("add_faq"):
        q = st.text_input("Вопрос")
        a = st.text_area("Ответ")
        if st.form_submit_button("Добавить"):
            if q and a:
                conn.execute("INSERT INTO faq (question, answer) VALUES (?, ?)", (q, a))
                conn.commit()
                st.rerun()
    faqs = pd.read_sql_query("SELECT id, question, answer FROM faq", conn)
    st.dataframe(faqs, width="stretch")
    if not faqs.empty:
        del_id = st.selectbox("Удалить по ID", faqs["id"].tolist())
        if st.button("🗑️ Удалить FAQ"):
            conn.execute("DELETE FROM faq WHERE id = ?", (del_id,))
            conn.commit()
            st.rerun()

elif menu == "📢 Рассылка":
    st.header("Массовая рассылка")
    text = st.text_area("Текст сообщения", height=150)
    if st.button("🚀 Отправить всем", type="primary"):
        if text:
            users = conn.execute("SELECT vk_user_id FROM users WHERE registration_status = 'confirmed'").fetchall()
            with st.spinner(f"Отправляем {len(users)} чел..."):
                progress = st.progress(0)
                success = 0
                for i, u in enumerate(users):
                    ok, _ = send_vk_message(u["vk_user_id"], text)
                    if ok: success += 1
                    progress.progress((i + 1) / len(users))
                st.success(f"✅ Отправлено {success} из {len(users)}")

conn.close()