import sqlite3
import threading


class DataBase:
    def __init__(self, path: str = "bot.db"):
        self.con = sqlite3.connect(path, check_same_thread=False, timeout=15)
        self.lock = threading.RLock()
        self.con.execute("PRAGMA journal_mode=WAL;")
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.cur = self.con.cursor()

        schema = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vk_user_id INTEGER UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    organization TEXT,
    region TEXT,
    position TEXT,
    email TEXT,
    phone TEXT,
    qr_code_data TEXT,
    registration_status TEXT DEFAULT 'pending',
    privacy_settings TEXT DEFAULT '{}',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    tag_name TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'hall',
    map_description TEXT
);
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT
);
CREATE TABLE IF NOT EXISTS speakers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    bio TEXT,
    photo_url TEXT,
    social_links TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    speaker_id INTEGER,
    track_id INTEGER,
    location_id INTEGER,
    presentation_url TEXT,
    FOREIGN KEY (speaker_id) REFERENCES speakers(id) ON DELETE SET NULL,
    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE SET NULL,
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS user_schedule (
    user_id INTEGER NOT NULL,
    session_id INTEGER NOT NULL,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, session_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    session_id INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    answer_text TEXT,
    is_anonymous BOOLEAN DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS polls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1
);
CREATE TABLE IF NOT EXISTS poll_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id INTEGER NOT NULL,
    option_text TEXT NOT NULL,
    FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS poll_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id INTEGER NOT NULL,
    option_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE,
    FOREIGN KEY (option_id) REFERENCES poll_options(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    rating INTEGER CHECK(rating BETWEEN 1 AND 5),
    comment TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text_content TEXT,
    media_url TEXT,
    target_tag TEXT,
    scheduled_time DATETIME,
    status TEXT DEFAULT 'draft',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS faq (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    keywords TEXT
);
CREATE TABLE IF NOT EXISTS support_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sender_type TEXT NOT NULL,
    message_text TEXT NOT NULL,
    is_read_by_operator BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""
        self.con.executescript(schema)
        self.con.commit()

    def insert(self, table, data):
        with self.lock:
            keys = ", ".join(data.keys())
            placeholders = ", ".join(["?"] * len(data))
            sql = f"INSERT INTO {table} ({keys}) VALUES ({placeholders})"
            cur = self.con.execute(sql, tuple(data.values()))
            self.con.commit()
            return cur.lastrowid

    def select(self, table, conditions=None, columns="*"):
        with self.lock:
            sql = f"SELECT {columns} FROM {table}"
            params = []
            if conditions:
                sql += " WHERE " + " AND ".join(f"{k} = ?" for k in conditions)
                params = list(conditions.values())
            self.cur.execute(sql, tuple(params))
            return [dict(row) for row in self.cur.fetchall()]

    def update(self, table, data, conditions):
        with self.lock:
            set_clause = ", ".join(f"{k} = ?" for k in data)
            where_clause = " AND ".join(f"{k} = ?" for k in conditions)
            sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
            self.con.execute(sql, tuple(data.values()) + tuple(conditions.values()))
            self.con.commit()

    def delete(self, table, conditions) -> int:
        with self.lock:
            where_clause = " AND ".join(f"{k} = ?" for k in conditions)
            sql = f"DELETE FROM {table} WHERE {where_clause}"
            cur = self.con.execute(sql, tuple(conditions.values()))
            self.con.commit()
            return cur.rowcount

    def get_user(self, vk_user_id: int) -> dict | None:
        with self.lock:
            rows = self.select("users", {"vk_user_id": vk_user_id})
            return rows[0] if rows else None

    def upsert_user(self, vk_user_id: int, data: dict) -> int:
        with self.lock:
            existing = self.get_user(vk_user_id)
            data = {**data, "vk_user_id": vk_user_id, "updated_at": "CURRENT_TIMESTAMP"}
            if existing:
                sets = ", ".join(f"{k} = ?" for k in data if k != "updated_at")
                self.con.execute(
                    f"UPDATE users SET {sets}, updated_at = CURRENT_TIMESTAMP "
                    f"WHERE vk_user_id = ?",
                    tuple(data[k] for k in data if k != "updated_at") + (vk_user_id,),
                )
                self.con.commit()
                return existing["id"]
            data.pop("updated_at", None)
            return self.insert("users", data)

    def get_confirmed_users(self) -> list[dict]:
        with self.lock:
            return self.select("users", {"registration_status": "confirmed"})


db = DataBase()
