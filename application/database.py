import os
import sqlite3
from typing import Any
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

    try:
        cur = conn.cursor()
        cur.execute(""" CREATE TABLE IF NOT EXISTS error_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        date        TEXT,
                        time        TEXT,
                        nodetype      TEXT,
                        module      TEXT,
                        errorcode   TEXT,
                        moreinfo    TEXT,
                        sampleID    TEXT,
                        carrierID   TEXT,
                        offline     TEXT,
                        full_string TEXT,
                        
                        UNIQUE ( date, time, nodetype, module, errorcode, moreinfo, sampleID, carrierID ) ) """)

        #indexes for fast filtering
        cur.execute("CREATE INDEX IF NOT EXISTS idx_date_time ON error_log(date, time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_module ON error_log(module)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_errorcode ON error_log(errorcode)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sampleID ON error_log(sampleID)")
        conn.commit()
    finally:
        conn.close()

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
                        date, time, nodetype, module, errorcode,
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
                            date, time, nodetype, module, errorcode,
                            moreinfo, sampleID, carrierID, offline, full_string)

                            VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
                            RETURNING id """, entry)
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

def fetch_entries_page(limit: int = 500, offset: int = 0) -> list[tuple[int | str | None, ...]]:
    conn = get_connection()

    try:
        cur = conn.cursor()
        cur.execute( """    SELECT id, date, time, nodetype, module, errorcode,
                            moreinfo, sampleID, carrierID, offline 
                            FROM error_log 
                            ORDER BY date DESC, time DESC
                            LIMIT ? OFFSET ?""",    (limit, offset))

        rows = cur.fetchall()
        return rows
    finally:
        conn.close()

def fetch_filtered_page(filters: dict[str, Any], limit: int = 500, offset: int = 0) -> list[tuple[str | None, ...]]:
    conn = get_connection()

    try:
        cur = conn.cursor()
        base_query = """    SELECT id, date, time, nodetype, module, errorcode,
                            moreinfo, sampleID, carrierID, offline 
                            FROM error_log 
                            WHERE 1=1 """

        query_parts = [base_query]
        params = []

        _add_filter(query_parts, params, filters, "date_from", ">=")
        _add_filter(query_parts, params, filters, "date_to", "<=")
        _add_filter(query_parts, params, filters, "time_from", ">=")
        _add_filter(query_parts, params, filters, "time_to", "<=")

        _add_filter(query_parts, params, filters, "nodetype", "=")
        _add_filter(query_parts, params, filters, "module", "=")

        _add_filter(query_parts, params, filters, "errorcode", "LIKE")
        _add_filter(query_parts, params, filters, "sampleID", "LIKE")

        query = " ".join(query_parts)
        query += " ORDER BY date DESC, time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        print(query)
        print(params)
        cur.execute(query, params)
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()

def _add_filter(query_parts: list[str], params: list, filters: dict, key: str, sql_operator: str) -> None:
    val = filters.get(key)
    if val is not None and val != "":
        if sql_operator == "LIKE":
            val = f"{val}%"
        if "_from" in key:
            db_column = key.removesuffix("_from")
        elif "_to" in key:
            db_column = key.removesuffix("_to")
        else:
            db_column = key
        query_parts.append(f" AND {db_column} {sql_operator} ?")
        params.append(val)

def get_values_for_filter(column: str) -> list[str]:
    if column not in { "date", "time", "nodetype", "module", "errorcode", "moreinfo", "sampleID" } :
        raise ValueError(f"Invalid column: {column}") #not really needed. check again later

    conn = get_connection()

    try:
        cur = conn.cursor()
        cur.execute(f"""    SELECT DISTINCT {column}
                            FROM error_log
                            WHERE {column} IS NOT NULL
                            ORDER BY {column}           """)

        values = [row[0] for row in cur.fetchall()]
        return values
    finally:
        conn.close()

def fetch_full_string_by_id(row_id: int) -> str | None:
    conn = get_connection()

    try:
        cur = conn.cursor()
        cur.execute(""" SELECT fullString
                        FROM error_log
                        WHERE id = ?    """, (row_id,))
        row = cur.fetchone()    # returns a tuple
                                # (12.02.25 14:30 ... ... BE12 "Device turned to an autonomous killing machine" ,)
    finally:
        conn.close()

    return row[0] if row else None





