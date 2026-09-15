import json
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from canvas_todo import db, ingest


def test_compute_status_submitted_is_done():
    assignment = {"submission": {"submitted_at": "2026-09-10T10:00:00Z"}, "due_at": "2026-09-18T23:59:00Z"}
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert ingest.compute_status(assignment, now) == "done"


def test_compute_status_overdue_when_unsubmitted_past_due():
    assignment = {"submission": {"submitted_at": None}, "due_at": "2026-09-10T23:59:00Z"}
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert ingest.compute_status(assignment, now) == "overdue"


def test_compute_status_pending_when_unsubmitted_and_upcoming():
    assignment = {"submission": {"submitted_at": None}, "due_at": "2026-09-20T23:59:00Z"}
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert ingest.compute_status(assignment, now) == "pending"


def test_compute_status_pending_when_no_due_date():
    assignment = {"submission": None, "due_at": None}
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    assert ingest.compute_status(assignment, now) == "pending"


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    db.init_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def sample_courses():
    with open("tests/fixtures/sample_courses.json") as f:
        return json.load(f)


@pytest.fixture
def sample_assignments():
    with open("tests/fixtures/sample_assignments.json") as f:
        return json.load(f)


@pytest.fixture
def sample_announcements():
    with open("tests/fixtures/sample_announcements.json") as f:
        return json.load(f)


def test_run_ingest_upserts_graded_items_and_returns_announcements(
    conn, sample_courses, sample_assignments, sample_announcements
):
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    with patch("canvas_todo.ingest.canvas_client.get_active_courses", return_value=sample_courses), \
         patch("canvas_todo.ingest.canvas_client.get_assignments_with_submissions", return_value=sample_assignments), \
         patch("canvas_todo.ingest.canvas_client.get_announcements", return_value=sample_announcements):
        result = ingest.run_ingest(conn, now=now)

    rows = conn.execute("SELECT * FROM items WHERE type = 'graded'").fetchall()
    assert len(rows) == len(sample_assignments)
    assert result["week_of"] == "2026-09-14"
    assert len(result["announcements"]) == len(sample_announcements)
    assert result["announcements"][0]["course_name"] == sample_courses[0]["course_code"]

    run_row = conn.execute("SELECT * FROM weekly_runs").fetchone()
    assert run_row is not None
    assert json.loads(run_row["raw_announcement_snapshot"]) == result["announcements"]
