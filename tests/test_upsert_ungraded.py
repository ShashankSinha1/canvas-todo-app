import sqlite3

import pytest

from canvas_todo import db, upsert_ungraded


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    db.init_db(connection)
    yield connection
    connection.close()


def test_upsert_items_creates_new_and_skips_duplicate(conn):
    items = [
        {"course_name": "CS101", "title": "Watch Lecture 4", "due_at": None},
        {"course_name": "CS101", "title": "watch lecture 4", "due_at": None},
        {"course_name": "CS101", "title": "Read Chapter 5", "due_at": None},
    ]
    result = upsert_ungraded.upsert_items(conn, items, "2026-09-14")
    assert len(result["created"]) == 2
    assert len(result["skipped_duplicates"]) == 1
    assert conn.execute("SELECT COUNT(*) as c FROM items").fetchone()["c"] == 2
