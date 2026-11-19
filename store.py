# store.py
# Local SQLite store for administration records. Replaces Firestore.
import os
import sqlite3
import threading
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smartdrop.db")

_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


_conn = _connect()
with _lock:
    _conn.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            eye TEXT NOT NULL DEFAULT 'left',
            drop_count INTEGER NOT NULL,
            angle REAL,
            success INTEGER NOT NULL
        )
        """
    )
    _conn.commit()


def add_record(drop_count, angle, success, eye="left", timestamp=None):
    """Insert one dispense attempt and return it as a dict."""
    ts = int(timestamp if timestamp is not None else time.time())
    with _lock:
        cur = _conn.execute(
            "INSERT INTO records (timestamp, eye, drop_count, angle, success) VALUES (?, ?, ?, ?, ?)",
            (ts, eye, int(drop_count), angle, 1 if success else 0),
        )
        _conn.commit()
        row = _conn.execute("SELECT * FROM records WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_dict(row)


def list_records(limit=50):
    """Most recent records first."""
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM records ORDER BY timestamp DESC, id DESC LIMIT ?", (int(limit),)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row):
    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "eye": row["eye"],
        "drop_count": row["drop_count"],
        "angle": row["angle"],
        "success": bool(row["success"]),
    }
