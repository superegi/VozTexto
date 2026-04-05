import hashlib
import sqlite3
from typing import Optional

from app.config import DB_PATH, ADMIN_USER, ADMIN_PASSWORD


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cur = conn.cursor()
    cur.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
    """, (table_name,))
    return cur.fetchone() is not None


def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    columns = cur.fetchall()
    return any(col["name"] == column_name for col in columns)


def create_users_table(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def create_transcriptions_table(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            exam_date TEXT,
            modality TEXT,
            hospital TEXT,
            description TEXT,
            speaker TEXT,
            stored_audio_path TEXT NOT NULL,
            stored_text_path TEXT NOT NULL,
            transcribed_text TEXT NOT NULL,
            final_text TEXT,
            user_id INTEGER,
            file_size_bytes INTEGER NOT NULL,
            duration_seconds REAL,
            processing_seconds REAL NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()


def migrate_transcriptions_table(conn: sqlite3.Connection):
    cur = conn.cursor()

    if not column_exists(conn, "transcriptions", "final_text"):
        cur.execute("ALTER TABLE transcriptions ADD COLUMN final_text TEXT")
        conn.commit()

    if not column_exists(conn, "transcriptions", "user_id"):
        cur.execute("ALTER TABLE transcriptions ADD COLUMN user_id INTEGER")
        conn.commit()

    if not column_exists(conn, "transcriptions", "exam_date"):
        cur.execute("ALTER TABLE transcriptions ADD COLUMN exam_date TEXT")
        conn.commit()

    if not column_exists(conn, "transcriptions", "modality"):
        cur.execute("ALTER TABLE transcriptions ADD COLUMN modality TEXT")
        conn.commit()

    if not column_exists(conn, "transcriptions", "hospital"):
        cur.execute("ALTER TABLE transcriptions ADD COLUMN hospital TEXT")
        conn.commit()

def migrate_users_table(conn: sqlite3.Connection):
    cur = conn.cursor()

    if not column_exists(conn, "users", "email"):
        cur.execute("ALTER TABLE users ADD COLUMN email TEXT")
        conn.commit()

def ensure_admin_user(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, username, is_admin, password_hash, email
        FROM users
        WHERE username = ?
    """, (ADMIN_USER,))
    row = cur.fetchone()

    password_hash = hash_password(ADMIN_PASSWORD)

    default_email = f"{ADMIN_USER}@saluddeadentro.cl"

    if row is None:
        cur.execute("""
            INSERT INTO users (username, email, password_hash, is_admin)
            VALUES (?, ?, ?, 1)
        """, (ADMIN_USER, default_email, password_hash))
        conn.commit()
        return

    needs_update = False

    if row["is_admin"] != 1:
        needs_update = True

    if row["password_hash"] != password_hash:
        needs_update = True

    if not row["email"]:
        needs_update = True

    if needs_update:
        cur.execute("""
            UPDATE users
            SET password_hash = ?, is_admin = 1, email = ?
            WHERE id = ?
        """, (password_hash, default_email, row["id"]))
        conn.commit()



def init_db():
    conn = get_connection()
    try:
        create_users_table(conn)
        migrate_users_table(conn)

        create_transcriptions_table(conn)
        migrate_transcriptions_table(conn)

        ensure_admin_user(conn)
    finally:
        conn.close()


def save_history(
    created_at: str,
    original_filename: str,
    exam_date: str,
    modality: str,
    hospital: str,
    description: str,
    speaker: str,
    stored_audio_path: str,
    stored_text_path: str,
    transcribed_text: str,
    file_size_bytes: int,
    duration_seconds: float | None,
    processing_seconds: float,
    status: str,
    user_id: Optional[int] = None,
    final_text: Optional[str] = None,
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transcriptions (
            created_at,
            original_filename,
            exam_date,
            modality,
            hospital,
            description,
            speaker,
            stored_audio_path,
            stored_text_path,
            transcribed_text,
            final_text,
            user_id,
            file_size_bytes,
            duration_seconds,
            processing_seconds,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        created_at,
        original_filename,
        exam_date,
        modality,
        hospital,
        description,
        speaker,
        stored_audio_path,
        stored_text_path,
        transcribed_text,
        final_text,
        user_id,
        file_size_bytes,
        duration_seconds,
        processing_seconds,
        status
    ))
    conn.commit()
    record_id = cur.lastrowid
    conn.close()
    return record_id


def get_history_rows(limit: int = 100):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            t.id,
            t.created_at,
            t.original_filename,
            t.exam_date,
            t.modality,
            t.hospital,
            t.description,
            t.speaker,
            t.stored_audio_path,
            t.stored_text_path,
            t.transcribed_text,
            t.final_text,
            t.user_id,
            u.username,
            t.file_size_bytes,
            t.duration_seconds,
            t.processing_seconds,
            t.status
        FROM transcriptions t
        LEFT JOIN users u ON t.user_id = u.id
        ORDER BY t.id DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_history_rows_by_user(user_id: int, limit: int = 100):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            t.id,
            t.created_at,
            t.original_filename,
            t.exam_date,
            t.modality,
            t.hospital,
            t.description,
            t.speaker,
            t.stored_audio_path,
            t.stored_text_path,
            t.transcribed_text,
            t.final_text,
            t.user_id,
            u.username,
            t.file_size_bytes,
            t.duration_seconds,
            t.processing_seconds,
            t.status
        FROM transcriptions t
        LEFT JOIN users u ON t.user_id = u.id
        WHERE t.user_id = ?
        ORDER BY t.id DESC
        LIMIT ?
    """, (user_id, limit))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_text_record(record_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT original_filename, final_text, transcribed_text
        FROM transcriptions
        WHERE id = ?
    """, (record_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_audio_record(record_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT original_filename, stored_audio_path
        FROM transcriptions
        WHERE id = ?
    """, (record_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_user_by_username(username: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, username, password_hash, is_admin, created_at
        FROM users
        WHERE username = ?
    """, (username,))
    row = cur.fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, username, password_hash, is_admin, created_at
        FROM users
        WHERE id = ?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def verify_user_credentials(username: str, password: str):
    user = get_user_by_username(username)
    if not user:
        return None

    if user["password_hash"] != hash_password(password):
        return None

    return user


def create_user(username: str, email: str, password: str, is_admin: int = 0):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (username, email, password_hash, is_admin)
        VALUES (?, ?, ?, ?)
    """, (username, email, hash_password(password), is_admin))
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def update_final_text(record_id: int, final_text: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE transcriptions
        SET final_text = ?
        WHERE id = ?
    """, (final_text, record_id))
    conn.commit()
    conn.close()

def get_transcription_owner(record_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            t.id,
            t.user_id,
            u.username
        FROM transcriptions t
        LEFT JOIN users u ON t.user_id = u.id
        WHERE t.id = ?
    """, (record_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_transcription_by_id(record_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            t.id,
            t.created_at,
            t.original_filename,
            t.exam_date,
            t.modality,
            t.hospital,
            t.description,
            t.speaker,
            t.stored_audio_path,
            t.stored_text_path,
            t.transcribed_text,
            t.final_text,
            t.user_id,
            u.username,
            t.file_size_bytes,
            t.duration_seconds,
            t.processing_seconds,
            t.status
        FROM transcriptions t
        LEFT JOIN users u ON t.user_id = u.id
        WHERE t.id = ?
    """, (record_id,))
    row = cur.fetchone()
    conn.close()
    return row


def update_transcription_edit(record_id: int, final_text: str, exam_date: str, hospital: str, modality: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE transcriptions
        SET final_text = ?, exam_date = ?, hospital = ?, modality = ?
        WHERE id = ?
    """, (final_text, exam_date, hospital, modality, record_id))
    conn.commit()
    conn.close()


def get_audio_path_by_record_id(record_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT stored_audio_path
        FROM transcriptions
        WHERE id = ?
    """, (record_id,))
    row = cur.fetchone()
    conn.close()
    return row