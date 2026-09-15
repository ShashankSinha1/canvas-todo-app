from __future__ import annotations

import sqlite3
from difflib import SequenceMatcher
from typing import Optional

SIMILARITY_THRESHOLD = 0.8

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_name TEXT NOT NULL,
    title TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('graded', 'ungraded')),
    due_at TEXT,
    source TEXT NOT NULL CHECK(source IN ('canvas_assignment', 'announcement')),
    status TEXT NOT NULL CHECK(status IN ('pending', 'done', 'overdue')),
    auto_tracked INTEGER NOT NULL CHECK(auto_tracked IN (0, 1)),
    last_reminded_at TEXT,
    canvas_assignment_id INTEGER UNIQUE,
    created_week TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    week_of TEXT NOT NULL,
    raw_announcement_snapshot TEXT NOT NULL
);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_graded_item(
    conn: sqlite3.Connection,
    *,
    course_name: str,
    title: str,
    due_at: Optional[str],
    status: str,
    canvas_assignment_id: int,
    created_week: str,
) -> int:
    if status not in ("pending", "done", "overdue"):
        raise ValueError(f"invalid status: {status}")

    existing = conn.execute(
        "SELECT id FROM items WHERE canvas_assignment_id = ?",
        (canvas_assignment_id,),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE items
               SET course_name = ?, title = ?, due_at = ?, status = ?
               WHERE id = ?""",
            (course_name, title, due_at, status, existing["id"]),
        )
        conn.commit()
        return existing["id"]

    cursor = conn.execute(
        """INSERT INTO items
           (course_name, title, type, due_at, source, status, auto_tracked,
            canvas_assignment_id, created_week)
           VALUES (?, ?, 'graded', ?, 'canvas_assignment', ?, 1, ?, ?)""",
        (course_name, title, due_at, status, canvas_assignment_id, created_week),
    )
    conn.commit()
    return cursor.lastrowid


def upsert_ungraded_item(
    conn: sqlite3.Connection,
    *,
    course_name: str,
    title: str,
    due_at: Optional[str],
    created_week: str,
) -> tuple[int, bool]:
    """Insert an ungraded item unless a similar one already exists this week
    for this course. Returns (item_id, created); created is False when an
    existing item was matched instead of a new one being inserted."""
    candidates = conn.execute(
        """SELECT id, title FROM items
           WHERE course_name = ? AND created_week = ? AND type = 'ungraded'""",
        (course_name, created_week),
    ).fetchall()

    for row in candidates:
        similarity = SequenceMatcher(None, row["title"].lower(), title.lower()).ratio()
        if similarity >= SIMILARITY_THRESHOLD:
            return row["id"], False

    cursor = conn.execute(
        """INSERT INTO items
           (course_name, title, type, due_at, source, status, auto_tracked, created_week)
           VALUES (?, ?, 'ungraded', ?, 'announcement', 'pending', 0, ?)""",
        (course_name, title, due_at, created_week),
    )
    conn.commit()
    return cursor.lastrowid, True


def toggle_item(conn: sqlite3.Connection, item_id: int) -> str:
    """Flip an ungraded item's status between pending and done. Raises
    ValueError if the item doesn't exist or is auto_tracked (graded)."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise ValueError(f"no item with id {item_id}")
    if row["auto_tracked"]:
        raise ValueError("cannot manually toggle an auto-tracked (graded) item")

    new_status = "done" if row["status"] == "pending" else "pending"
    conn.execute("UPDATE items SET status = ? WHERE id = ?", (new_status, item_id))
    conn.commit()
    return new_status


def get_items_for_week(conn: sqlite3.Connection, week_of: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT * FROM items
           WHERE created_week = ? OR status != 'done'
           ORDER BY course_name, due_at IS NULL, due_at""",
        (week_of,),
    ).fetchall()


def mark_reminded(conn: sqlite3.Connection, item_ids: list[int], reminded_at: str) -> None:
    if not item_ids:
        return
    conn.executemany(
        "UPDATE items SET last_reminded_at = ? WHERE id = ?",
        [(reminded_at, item_id) for item_id in item_ids],
    )
    conn.commit()


def insert_weekly_run(
    conn: sqlite3.Connection, *, run_at: str, week_of: str, raw_announcement_snapshot: str
) -> int:
    cursor = conn.execute(
        """INSERT INTO weekly_runs (run_at, week_of, raw_announcement_snapshot)
           VALUES (?, ?, ?)""",
        (run_at, week_of, raw_announcement_snapshot),
    )
    conn.commit()
    return cursor.lastrowid
