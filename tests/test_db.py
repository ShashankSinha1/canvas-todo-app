import sqlite3

import pytest

from canvas_todo import db


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    db.init_db(connection)
    yield connection
    connection.close()


def test_upsert_graded_item_creates_new_row(conn):
    item_id = db.upsert_graded_item(
        conn,
        course_name="CS101",
        title="Homework 1",
        due_at="2026-09-18T23:59:00Z",
        status="pending",
        canvas_assignment_id=555,
        created_week="2026-09-14",
    )
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    assert row["title"] == "Homework 1"
    assert row["status"] == "pending"
    assert row["auto_tracked"] == 1
    assert row["type"] == "graded"


def test_upsert_graded_item_updates_existing_row_by_assignment_id(conn):
    item_id = db.upsert_graded_item(
        conn, course_name="CS101", title="Homework 1", due_at="2026-09-18T23:59:00Z",
        status="pending", canvas_assignment_id=555, created_week="2026-09-14",
    )
    updated_id = db.upsert_graded_item(
        conn, course_name="CS101", title="Homework 1", due_at="2026-09-18T23:59:00Z",
        status="done", canvas_assignment_id=555, created_week="2026-09-14",
    )
    assert updated_id == item_id
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    assert row["status"] == "done"
    assert conn.execute("SELECT COUNT(*) as c FROM items").fetchone()["c"] == 1


def test_upsert_ungraded_item_creates_new_row(conn):
    item_id, created = db.upsert_ungraded_item(
        conn, course_name="CS101", title="Watch Lecture 4", due_at=None,
        created_week="2026-09-14",
    )
    assert created is True
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    assert row["type"] == "ungraded"
    assert row["auto_tracked"] == 0
    assert row["status"] == "pending"


def test_upsert_ungraded_item_dedupes_similar_title_same_week(conn):
    first_id, _ = db.upsert_ungraded_item(
        conn, course_name="CS101", title="Watch Lecture 4", due_at=None,
        created_week="2026-09-14",
    )
    second_id, created = db.upsert_ungraded_item(
        conn, course_name="CS101", title="watch lecture 4", due_at=None,
        created_week="2026-09-14",
    )
    assert created is False
    assert second_id == first_id
    assert conn.execute("SELECT COUNT(*) as c FROM items").fetchone()["c"] == 1


def test_upsert_ungraded_item_does_not_dedupe_different_week(conn):
    first_id, _ = db.upsert_ungraded_item(
        conn, course_name="CS101", title="Watch Lecture 4", due_at=None,
        created_week="2026-09-07",
    )
    second_id, created = db.upsert_ungraded_item(
        conn, course_name="CS101", title="Watch Lecture 4", due_at=None,
        created_week="2026-09-14",
    )
    assert created is True
    assert second_id != first_id


def test_toggle_item_flips_ungraded_status(conn):
    item_id, _ = db.upsert_ungraded_item(
        conn, course_name="CS101", title="Read Ch 5", due_at=None, created_week="2026-09-14",
    )
    assert db.toggle_item(conn, item_id) == "done"
    assert db.toggle_item(conn, item_id) == "pending"


def test_toggle_item_rejects_graded_item(conn):
    item_id = db.upsert_graded_item(
        conn, course_name="CS101", title="Homework 1", due_at="2026-09-18T23:59:00Z",
        status="pending", canvas_assignment_id=555, created_week="2026-09-14",
    )
    with pytest.raises(ValueError):
        db.toggle_item(conn, item_id)


def test_toggle_item_missing_id_raises(conn):
    with pytest.raises(ValueError):
        db.toggle_item(conn, 9999)


def test_mark_reminded_sets_timestamp(conn):
    item_id, _ = db.upsert_ungraded_item(
        conn, course_name="CS101", title="Read Ch 5", due_at=None, created_week="2026-09-14",
    )
    db.mark_reminded(conn, [item_id], "2026-09-14T07:30:00+00:00")
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    assert row["last_reminded_at"] == "2026-09-14T07:30:00+00:00"


def test_insert_weekly_run(conn):
    run_id = db.insert_weekly_run(
        conn, run_at="2026-09-14T07:30:00+00:00", week_of="2026-09-14",
        raw_announcement_snapshot="[]",
    )
    row = conn.execute("SELECT * FROM weekly_runs WHERE id = ?", (run_id,)).fetchone()
    assert row["week_of"] == "2026-09-14"


def test_get_items_for_week_returns_rows(conn):
    db.upsert_graded_item(
        conn, course_name="CS101", title="Homework 1", due_at="2026-09-18T23:59:00Z",
        status="pending", canvas_assignment_id=555, created_week="2026-09-14",
    )
    rows = db.get_items_for_week(conn, "2026-09-14")
    assert len(rows) == 1
    assert rows[0]["title"] == "Homework 1"
