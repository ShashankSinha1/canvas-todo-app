import json
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from canvas_todo import db, digest


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    db.init_db(connection)
    yield connection
    connection.close()


def test_build_digest_groups_by_course_and_section(conn):
    db.upsert_graded_item(
        conn, course_name="CS101", title="Homework 1", due_at="2026-09-20T23:59:00Z",
        status="pending", canvas_assignment_id=1, created_week="2026-09-14",
    )
    db.upsert_graded_item(
        conn, course_name="CS101", title="Quiz 2", due_at="2026-09-10T23:59:00Z",
        status="overdue", canvas_assignment_id=2, created_week="2026-09-14",
    )
    db.upsert_ungraded_item(
        conn, course_name="CS101", title="Watch Lecture 4", due_at=None, created_week="2026-09-14",
    )

    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    result = digest.build_digest(conn, "2026-09-14", now)

    assert "CS101" in result["digest_text"]
    assert "Homework 1" in result["digest_text"]
    assert "Quiz 2" in result["digest_text"]
    assert "Watch Lecture 4" in result["digest_text"]
    assert result["urgent_text"] is None
    assert len(result["reminded_ids"]) == 3


def test_build_digest_flags_urgent_when_graded_due_within_24h(conn):
    db.upsert_graded_item(
        conn, course_name="CS101", title="Homework 1", due_at="2026-09-14T18:00:00Z",
        status="pending", canvas_assignment_id=1, created_week="2026-09-14",
    )
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    result = digest.build_digest(conn, "2026-09-14", now)
    assert result["urgent_text"] is not None
    assert "Homework 1" in result["urgent_text"]


def test_build_digest_marks_new_items_with_marker(conn):
    db.upsert_ungraded_item(
        conn, course_name="CS101", title="Watch Lecture 4", due_at=None, created_week="2026-09-14",
    )
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    result = digest.build_digest(conn, "2026-09-14", now)
    assert "🆕" in result["digest_text"]


def test_main_prints_clean_json_error_on_unexpected_exception(tmp_path, monkeypatch, capsys):
    import sys as sys_module

    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(sys_module, "argv", ["digest.py", "--db", db_path])

    def _boom(conn, wk, now):
        raise ValueError("simulated unexpected failure")

    with patch("canvas_todo.digest.build_digest", side_effect=_boom):
        with pytest.raises(SystemExit) as exc_info:
            digest.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert "error" in printed


def test_build_digest_routes_overdue_graded_item_to_overdue_section_only(conn):
    db.upsert_graded_item(
        conn, course_name="CS101", title="Late Quiz", due_at="2026-09-10T23:59:00Z",
        status="overdue", canvas_assignment_id=1, created_week="2026-09-07",
    )
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    result = digest.build_digest(conn, "2026-09-14", now)

    assert "Overdue:" in result["digest_text"]
    overdue_section = result["digest_text"].split("Overdue:")[1]
    assert "Late Quiz" in overdue_section
    due_section_present = "Due this week:" in result["digest_text"]
    if due_section_present:
        due_section = result["digest_text"].split("Due this week:")[1].split("Overdue:")[0]
        assert "Late Quiz" not in due_section


def test_new_marker_disappears_after_mark_reminded(conn):
    item_id, _ = db.upsert_ungraded_item(
        conn, course_name="CS101", title="Watch Lecture 4", due_at=None, created_week="2026-09-14",
    )
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)

    first_result = digest.build_digest(conn, "2026-09-14", now)
    assert "🆕" in first_result["digest_text"]

    db.mark_reminded(conn, first_result["reminded_ids"], now.isoformat())

    second_result = digest.build_digest(conn, "2026-09-14", now)
    assert "🆕" not in second_result["digest_text"]
    assert "Watch Lecture 4" in second_result["digest_text"]


def test_build_digest_omits_done_items_and_their_course_header(conn):
    db.upsert_graded_item(
        conn, course_name="CS101", title="Finished Homework", due_at="2026-09-12T23:59:00Z",
        status="done", canvas_assignment_id=1, created_week="2026-09-14",
    )
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    result = digest.build_digest(conn, "2026-09-14", now)

    assert "CS101" not in result["digest_text"]
    assert "Finished Homework" not in result["digest_text"]
    assert result["reminded_ids"] == []
