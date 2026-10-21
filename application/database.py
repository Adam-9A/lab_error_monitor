import os
import sqlite3
from utils import app_dir

DB_NAME = os.path.join(app_dir(), "error_log.db")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA journal_mode=WAL;") #graphical_ui reads while rt_monitor writes without blocking each other
    conn.execute("PRAGMA synchronous=NORMAL;") #how quickly SQLite flushes data to disk after every write
    conn.execute("PRAGMA temp_store=MEMORY;") #stores temporary tables/indexes in RAM instead of disk
    return conn

def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(""" CREATE TABLE IF NOT EXISTS error_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    date        TEXT,
                    time        TEXT,
                    nodeID      TEXT,
                    module      TEXT,
                    errorcode   TEXT,
                    moreinfo    TEXT,
                    sampleID    TEXT,
                    carrierID   TEXT,
                    offline     TEXT,
                    full_string TEXT,
                    
                    UNIQUE ( date, time, nodeID, module, errorcode, moreinfo, sampleID, carrierID ) ) """)

def ensure_db() -> None:
    if not os.path.exists(DB_NAME):
        init_db()

def insert_log_entries(entries: list[tuple[str | None, ...]]) -> None:
    if not entries:
        return

    ensure_db()
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("BEGIN")
    cur.executemany(""" INSERT OR IGNORE INTO error_log (
                        date, time, nodeID, module, errorcode,
                        moreinfo, sampleID, carrierID, offline, full_string)
                        
                        VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) """, entries)
    conn.commit()
    conn.close()

def insert_live_log_entries(entries: list[tuple[str | None, ...]]) -> list[int | None]:
    if not entries:
        return []

    ensure_db()
    conn = get_connection()
    cur = conn.cursor()
    row_ids = []

    try:
        cur.execute("BEGIN")
        for entry in entries:
            cur.execute(""" INSERT OR IGNORE INTO error_log (
                            date, time, nodeID, module, errorcode,
                            moreinfo, sampleID, carrierID, offline, full_string)

                            VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) """, entry)
            row = cur.fetchone()
            new_id = row[0] if row else None
            row_ids.append(new_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return row_ids

