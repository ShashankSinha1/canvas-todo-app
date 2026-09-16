import json
import sqlite3
from datetime import datetime, timezone

import pytest

from canvas_todo import db, manual_ingest


def test_compute_status_submitted_is_done():
    assignment = {"submitted": True, "due_at": "2026-09-18T23:59:00Z"}
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert manual_ingest.compute_status(assignment, now) == "done"


def test_compute_status_overdue_when_unsubmitted_past_due():
    assignment = {"submitted": False, "due_at": "2026-09-10T23:59:00Z"}
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert manual_ingest.compute_status(assignment, now) == "overdue"


def test_compute_status_pending_when_unsubmitted_and_upcoming():
    assignment = {"submitted": False, "due_at": "2026-09-20T23:59:00Z"}
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert manual_ingest.compute_status(assignment, now) == "pending"


def test_compute_status_pending_when_no_due_date():
    assignment = {"submitted": False, "due_at": None}
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert manual_ingest.compute_status(assignment, now) == "pending"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    db.init_db(connection)
    yield connection
    connection.close()


def test_run_manual_ingest_upserts_graded_items_and_records_announcements(conn):
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    data = {
        "courses": [
            {
                "course_name": "CS101",
                "assignments": [
                    {"canvas_assignment_id": 1, "title": "Homework 1", "due_at": "2026-09-18T23:59:00Z", "submitted": False},
                    {"canvas_assignment_id": 2, "title": "Quiz 2", "due_at": "2026-09-10T23:59:00Z", "submitted": False},
                    {"canvas_assignment_id": 3, "title": "Project Proposal", "due_at": "2026-09-15T23:59:00Z", "submitted": True},
                ],
            }
        ],
        "announcements": [
            {"course_name": "CS101", "title": "Week 5", "message": "Watch Lecture 4", "posted_at": "2026-09-14T09:00:00Z"}
        ],
    }

    result = manual_ingest.run_manual_ingest(conn, data, now=now)

    rows = conn.execute("SELECT * FROM items WHERE type = 'graded'").fetchall()
    assert len(rows) == 3
    statuses = {row["title"]: row["status"] for row in rows}
    assert statuses["Homework 1"] == "pending"
    assert statuses["Quiz 2"] == "overdue"
    assert statuses["Project Proposal"] == "done"

    assert result["week_of"] == "2026-09-14"
    assert result["announcements"] == data["announcements"]

    run_row = conn.execute("SELECT * FROM weekly_runs").fetchone()
    assert run_row is not None
    assert json.loads(run_row["raw_announcement_snapshot"]) == data["announcements"]


def test_run_manual_ingest_skips_assignments_without_due_date(conn):
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    data = {
        "courses": [
            {
                "course_name": "CS101",
                "assignments": [
                    {"canvas_assignment_id": 1, "title": "Undated Assignment", "due_at": None, "submitted": False},
                ],
            }
        ],
        "announcements": [],
    }
    manual_ingest.run_manual_ingest(conn, data, now=now)
    rows = conn.execute("SELECT * FROM items").fetchall()
    assert len(rows) == 0


def test_run_manual_ingest_re_upserts_existing_assignment_by_id(conn):
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    data = {
        "courses": [{"course_name": "CS101", "assignments": [
            {"canvas_assignment_id": 1, "title": "Homework 1", "due_at": "2026-09-18T23:59:00Z", "submitted": False},
        ]}],
        "announcements": [],
    }
    manual_ingest.run_manual_ingest(conn, data, now=now)
    data["courses"][0]["assignments"][0]["submitted"] = True
    manual_ingest.run_manual_ingest(conn, data, now=now)

    rows = conn.execute("SELECT * FROM items").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "done"


def test_main_prints_clean_json_error_on_malformed_input(tmp_path, monkeypatch, capsys):
    import sys as sys_module

    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(
        sys_module, "argv", ["manual_ingest.py", "--db", db_path, "--data-json", "not valid json{"]
    )
    with pytest.raises(SystemExit) as exc_info:
        manual_ingest.main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert "error" in printed


def test_main_upserts_and_prints_result(tmp_path, monkeypatch, capsys):
    import sys as sys_module

    db_path = str(tmp_path / "test.db")
    data = {
        "courses": [{"course_name": "CS101", "assignments": [
            {"canvas_assignment_id": 1, "title": "Homework 1", "due_at": "2026-09-18T23:59:00Z", "submitted": False},
        ]}],
        "announcements": [],
    }
    monkeypatch.setattr(
        sys_module, "argv", ["manual_ingest.py", "--db", db_path, "--data-json", json.dumps(data)]
    )
    manual_ingest.main()
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert "week_of" in printed
