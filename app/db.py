import sqlite3
from app.config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            description TEXT,
            speaker TEXT,
            stored_audio_path TEXT NOT NULL,
            stored_text_path TEXT NOT NULL,
            transcribed_text TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL,
            duration_seconds REAL,
            processing_seconds REAL NOT NULL,
            status TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_history(
    created_at: str,
    original_filename: str,
    description: str,
    speaker: str,
    stored_audio_path: str,
    stored_text_path: str,
    transcribed_text: str,
    file_size_bytes: int,
    duration_seconds: float | None,
    processing_seconds: float,
    status: str,
):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transcriptions (
            created_at,
            original_filename,
            description,
            speaker,
            stored_audio_path,
            stored_text_path,
            transcribed_text,
            file_size_bytes,
            duration_seconds,
            processing_seconds,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        created_at,
        original_filename,
        description,
        speaker,
        stored_audio_path,
        stored_text_path,
        transcribed_text,
        file_size_bytes,
        duration_seconds,
        processing_seconds,
        status
    ))
    conn.commit()
    conn.close()


def get_history_rows(limit: int = 100):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            id,
            created_at,
            original_filename,
            description,
            speaker,
            stored_audio_path,
            stored_text_path,
            file_size_bytes,
            duration_seconds,
            processing_seconds,
            status
        FROM transcriptions
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_text_record(record_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT original_filename, stored_text_path
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