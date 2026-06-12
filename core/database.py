import sqlite3
import json
import os
from datetime import datetime

from core.config import DATA_DIR

# Caminho do banco de dados na raiz do projeto
DB_DIR = DATA_DIR
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "sage.db")

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tabela de Sessões
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            current_stage TEXT DEFAULT 'v0_setup',
            state_data TEXT DEFAULT '{}',
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    # Tabela de Fila (Jobs)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            task_type TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING',
            created_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            error_message TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def create_session(session_id: str, name: str):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO sessions (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (session_id, name, now, now)
    )
    conn.commit()
    conn.close()

def get_all_sessions():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_session(session_id: str):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_session_state(session_id: str, current_stage: str, state_data: dict):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    state_str = json.dumps(state_data)
    cursor.execute(
        "UPDATE sessions SET current_stage = ?, state_data = ?, updated_at = ? WHERE id = ?",
        (current_stage, state_str, now, session_id)
    )
    conn.commit()
    conn.close()

def enqueue_job(session_id: str, task_type: str):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO jobs_queue (session_id, task_type, created_at) VALUES (?, ?, ?)",
        (session_id, task_type, now)
    )
    conn.commit()
    conn.close()

def get_queue():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs_queue ORDER BY created_at ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_pending_job():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs_queue WHERE status = 'PENDING' ORDER BY created_at ASC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_job_status(job_id: int, status: str, error_message: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    if status == 'RUNNING':
        cursor.execute("UPDATE jobs_queue SET status = ?, started_at = ? WHERE id = ?", (status, now, job_id))
    elif status in ['COMPLETED', 'FAILED']:
        cursor.execute("UPDATE jobs_queue SET status = ?, completed_at = ?, error_message = ? WHERE id = ?", (status, now, error_message, job_id))
    else:
        cursor.execute("UPDATE jobs_queue SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()
    conn.close()

def get_session_active_job(session_id: str):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs_queue WHERE session_id = ? AND status IN ('PENDING', 'RUNNING') ORDER BY created_at ASC LIMIT 1", (session_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# Initialize db file on import
init_db()
