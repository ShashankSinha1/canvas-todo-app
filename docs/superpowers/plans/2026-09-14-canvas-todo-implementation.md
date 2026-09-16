# Canvas Weekly To-Do & Reminder App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Canvas weekly to-do app that auto-tracks graded assignment completion via Canvas submission status, infers ungraded to-dos from Canvas announcements, shows everything in a local web app, and sends daily Telegram reminders.

**Architecture:** A Python package (`canvas_todo`) provides a SQLite-backed data layer, a Canvas REST API client, and small CLI scripts (ingest, upsert-ungraded, digest, telegram-send) that a scheduled Claude agent orchestrates once daily. A Flask app reads/writes the same SQLite file for the browsable weekly view.

**Tech Stack:** Python 3, stdlib `sqlite3`, `requests`, `flask`, `python-dotenv`, `pytest`. No ORM, no frontend framework, no build step.

---

## Reference: Design Spec

This plan implements `docs/superpowers/specs/2026-09-14-canvas-todo-design.md`. Read that file first if anything here is ambiguous — it has the full rationale.

## File Structure

```
canvas-todo-app/
├── .env.template
├── .gitignore
├── requirements.txt
├── conftest.py
├── canvas_todo/
│   ├── __init__.py
│   ├── dateutils.py        # utc_now(), week_of() — shared by every other module
│   ├── db.py                # schema + all SQLite read/write functions
│   ├── canvas_client.py     # Canvas REST API wrapper (paginated GETs)
│   ├── ingest.py             # CLI: pulls Canvas data, upserts graded items, emits announcements JSON
│   ├── upsert_ungraded.py    # CLI: upserts LLM-extracted ungraded items with dedup
│   ├── digest.py              # CLI: builds Telegram digest + urgent-alert text
│   ├── telegram_client.py     # CLI: sends a message via Telegram Bot API
│   └── web.py                  # Flask app: GET /, POST /items/<id>/toggle
├── templates/
│   └── index.html
├── tests/
│   ├── fixtures/
│   │   ├── sample_courses.json
│   │   ├── sample_assignments.json
│   │   └── sample_announcements.json
│   ├── test_dateutils.py
│   ├── test_db.py
│   ├── test_canvas_client.py
│   ├── test_ingest.py
│   ├── test_upsert_ungraded.py
│   ├── test_digest.py
│   ├── test_telegram_client.py
│   └── test_web.py
└── README.md
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `canvas-todo-app/.gitignore`
- Create: `canvas-todo-app/requirements.txt`
- Create: `canvas-todo-app/.env.template`
- Create: `canvas-todo-app/conftest.py`
- Create: `canvas-todo-app/canvas_todo/__init__.py`

- [ ] **Step 1: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
*.db
venv/
.pytest_cache/
```

- [ ] **Step 2: Create `requirements.txt`**

```
flask==3.0.3
requests==2.32.3
python-dotenv==1.0.1
pytest==8.3.2
```

- [ ] **Step 3: Create `.env.template`**

```
# Canvas API
CANVAS_API_URL=https://YOUR_INSTITUTION.instructure.com
CANVAS_API_TOKEN=your_canvas_token_here

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# App
CANVAS_TODO_DB=canvas_todo.db
```

- [ ] **Step 4: Create `conftest.py`** (guarantees `canvas_todo` is importable by pytest regardless of how it's invoked)

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
```

- [ ] **Step 5: Create empty package init**

`canvas_todo/__init__.py`:

```python
```

- [ ] **Step 6: Create virtualenv and install dependencies**

Run:
```bash
cd ~/canvas-todo-app
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```
Expected: dependencies install without errors.

- [ ] **Step 7: Verify the environment**

Run: `venv/bin/python -c "import flask, requests, dotenv; print('ok')"`
Expected: `ok`

- [ ] **Step 8: Commit**

```bash
git add .gitignore requirements.txt .env.template conftest.py canvas_todo/__init__.py
git commit -m "chore: scaffold project structure and dependencies"
```

---

### Task 2: Date Utilities

**Files:**
- Create: `canvas_todo/dateutils.py`
- Test: `tests/test_dateutils.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_dateutils.py`:

```python
from datetime import datetime, timezone

from canvas_todo.dateutils import week_of


def test_week_of_returns_monday_for_midweek_date():
    dt = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)  # Thursday
    assert week_of(dt) == "2026-09-14"


def test_week_of_on_monday_itself():
    dt = datetime(2026, 9, 14, 0, 30, tzinfo=timezone.utc)  # Monday
    assert week_of(dt) == "2026-09-14"


def test_week_of_on_sunday_belongs_to_previous_monday():
    dt = datetime(2026, 9, 20, 23, 0, tzinfo=timezone.utc)  # Sunday
    assert week_of(dt) == "2026-09-14"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_dateutils.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'canvas_todo.dateutils'`

- [ ] **Step 3: Implement `canvas_todo/dateutils.py`**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def week_of(dt: datetime) -> str:
    """Return the ISO date (YYYY-MM-DD) of the Monday starting dt's week."""
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_dateutils.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add canvas_todo/dateutils.py tests/test_dateutils.py
git commit -m "feat: add week-of date utility shared across ingestion, digest, and web"
```

---

### Task 3: SQLite Data Layer

**Files:**
- Create: `canvas_todo/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_db.py`:

```python
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


def test_upsert_graded_item_rejects_invalid_status(conn):
    with pytest.raises(ValueError):
        db.upsert_graded_item(
            conn, course_name="CS101", title="Homework 1", due_at="2026-09-18T23:59:00Z",
            status="bogus", canvas_assignment_id=555, created_week="2026-09-14",
        )


def test_get_items_for_week_includes_unresolved_items_from_prior_weeks(conn):
    # Overdue item created in a prior week must still show up now (the bug this fix addresses)
    overdue_id = db.upsert_graded_item(
        conn, course_name="CS101", title="Late Homework", due_at="2026-09-10T23:59:00Z",
        status="overdue", canvas_assignment_id=111, created_week="2026-09-07",
    )
    # Pending ungraded item created in a prior week, never checked off, must still show up now
    pending_ungraded_id, _ = db.upsert_ungraded_item(
        conn, course_name="CS101", title="Watch Lecture 2", due_at=None,
        created_week="2026-09-07",
    )
    # A done item from a prior week should NOT show up in the current week's view
    db.upsert_graded_item(
        conn, course_name="CS101", title="Old Finished Homework", due_at="2026-09-05T23:59:00Z",
        status="done", canvas_assignment_id=222, created_week="2026-08-31",
    )

    rows = db.get_items_for_week(conn, "2026-09-14")
    ids = {row["id"] for row in rows}

    assert overdue_id in ids
    assert pending_ungraded_id in ids
    assert len(rows) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'canvas_todo.db'`

- [ ] **Step 3: Implement `canvas_todo/db.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_db.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add canvas_todo/db.py tests/test_db.py
git commit -m "feat: add SQLite data layer with graded/ungraded upsert and toggle logic"
```

---

### Task 4: Canvas API Client

> **SUPERSEDED (2026-09-16) — see `docs/superpowers/specs/2026-09-14-canvas-todo-design.md`, "Amendment 2."** Georgia Tech blocks student API tokens, and the follow-up session-cookie and token-free-feed approaches were each abandoned in turn (see Amendments 1 and 2). The module built by this task was removed in Task 16 and replaced by manually-triggered Chrome-extension ingestion + `canvas_todo/manual_ingest.py`. Left below as a historical record of what was originally built, reviewed, and later retired — do not re-implement from this section.

**Files:**
- Create: `canvas_todo/canvas_client.py`
- Test: `tests/test_canvas_client.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_canvas_client.py`:

```python
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("CANVAS_API_URL", "https://example.instructure.com")
os.environ.setdefault("CANVAS_API_TOKEN", "test-token")

from canvas_todo import canvas_client


def _fake_response(json_data, link_header=None, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.headers = {"Link": link_header} if link_header else {}
    response.text = ""
    return response


@patch("canvas_todo.canvas_client.requests.get")
def test_get_active_courses_single_page(mock_get):
    mock_get.return_value = _fake_response([{"id": 1, "name": "Intro to CS"}])
    courses = canvas_client.get_active_courses()
    assert courses == [{"id": 1, "name": "Intro to CS"}]
    mock_get.assert_called_once()


@patch("canvas_todo.canvas_client.requests.get")
def test_get_paginated_follows_next_link(mock_get):
    page1 = _fake_response(
        [{"id": 1}],
        link_header='<https://example.instructure.com/api/v1/courses?page=2>; rel="next"',
    )
    page2 = _fake_response([{"id": 2}])
    mock_get.side_effect = [page1, page2]

    courses = canvas_client.get_active_courses()
    assert courses == [{"id": 1}, {"id": 2}]
    assert mock_get.call_count == 2


@patch("canvas_todo.canvas_client.requests.get")
def test_get_paginated_handles_realistic_multi_link_header(mock_get):
    multi_link_header = (
        '<https://example.instructure.com/api/v1/courses?page=1>; rel="current", '
        '<https://example.instructure.com/api/v1/courses?page=2>; rel="next", '
        '<https://example.instructure.com/api/v1/courses?page=5>; rel="last"'
    )
    page1 = _fake_response([{"id": 1}], link_header=multi_link_header)
    page2 = _fake_response([{"id": 2}])  # last page, no Link header
    mock_get.side_effect = [page1, page2]

    courses = canvas_client.get_active_courses()
    assert courses == [{"id": 1}, {"id": 2}]
    assert mock_get.call_count == 2


def test_get_active_courses_raises_clear_error_when_token_missing(monkeypatch):
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    with pytest.raises(canvas_client.CanvasAPIError, match="CANVAS_API_TOKEN"):
        canvas_client.get_active_courses()


@patch("canvas_todo.canvas_client.requests.get")
def test_get_active_courses_raises_on_error(mock_get):
    mock_get.return_value = _fake_response({"errors": "bad token"}, status_code=401)
    with pytest.raises(canvas_client.CanvasAPIError):
        canvas_client.get_active_courses()


@patch("canvas_todo.canvas_client.requests.get")
def test_get_announcements_returns_empty_for_no_courses(mock_get):
    result = canvas_client.get_announcements([], since_days=7)
    assert result == []
    mock_get.assert_not_called()


@patch("canvas_todo.canvas_client.requests.get")
def test_get_assignments_with_submissions_passes_include_param(mock_get):
    mock_get.return_value = _fake_response([{"id": 10, "name": "HW1", "submission": {}}])
    assignments = canvas_client.get_assignments_with_submissions(123)
    assert assignments[0]["name"] == "HW1"
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["include[]"] == "submission"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_canvas_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'canvas_todo.canvas_client'`

- [ ] **Step 3: Implement `canvas_todo/canvas_client.py`**

```python
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

import requests


class CanvasAPIError(Exception):
    pass


def _base_url() -> str:
    try:
        url = os.environ["CANVAS_API_URL"]
    except KeyError as exc:
        raise CanvasAPIError("CANVAS_API_URL is not set (check your .env file)") from exc
    return f"{url.rstrip('/')}/api/v1"


def _headers() -> dict:
    try:
        token = os.environ["CANVAS_API_TOKEN"]
    except KeyError as exc:
        raise CanvasAPIError("CANVAS_API_TOKEN is not set (check your .env file)") from exc
    return {"Authorization": f"Bearer {token}"}


def _parse_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        segment = part.strip()
        match = re.match(r'<([^>]+)>;\s*rel="([^"]+)"', segment)
        if match and match.group(2) == "next":
            return match.group(1)
    return None


def _get_paginated(url: str, params: dict | None = None) -> list[dict]:
    results: list[dict] = []
    next_url = url
    next_params = params
    while next_url:
        response = requests.get(next_url, headers=_headers(), params=next_params, timeout=30)
        if response.status_code != 200:
            raise CanvasAPIError(
                f"GET {next_url} failed: {response.status_code} {response.text[:200]}"
            )
        results.extend(response.json())
        next_url = _parse_next_link(response.headers.get("Link"))
        next_params = None  # the next_url already has query params baked in
    return results


def get_active_courses() -> list[dict]:
    return _get_paginated(
        f"{_base_url()}/courses",
        params={"enrollment_state": "active", "per_page": 100},
    )


def get_assignments_with_submissions(course_id: int) -> list[dict]:
    return _get_paginated(
        f"{_base_url()}/courses/{course_id}/assignments",
        params={"include[]": "submission", "per_page": 100},
    )


def get_announcements(course_ids: list[int], since_days: int = 7) -> list[dict]:
    if not course_ids:
        return []
    start_date = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")
    return _get_paginated(
        f"{_base_url()}/announcements",
        params={
            "context_codes[]": [f"course_{cid}" for cid in course_ids],
            "start_date": start_date,
            "per_page": 50,
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_canvas_client.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add canvas_todo/canvas_client.py tests/test_canvas_client.py
git commit -m "feat: add Canvas REST API client with pagination"
```

---

### Task 5: Ingestion CLI

> **SUPERSEDED (2026-09-16) — see `docs/superpowers/specs/2026-09-14-canvas-todo-design.md`, "Amendment 2."** This module depended on Task 4's retired `canvas_client.py`. Removed in Task 16 and replaced by `canvas_todo/manual_ingest.py`, which persists data Claude reads live via the Chrome extension rather than fetching it itself. Left below as historical record — do not re-implement from this section.

**Files:**
- Create: `canvas_todo/ingest.py`
- Create: `tests/fixtures/sample_courses.json`
- Create: `tests/fixtures/sample_assignments.json`
- Create: `tests/fixtures/sample_announcements.json`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Create fixture files**

`tests/fixtures/sample_courses.json`:

```json
[
  {"id": 111, "name": "Introduction to Computer Science", "course_code": "CS101"}
]
```

`tests/fixtures/sample_assignments.json`:

```json
[
  {
    "id": 9001,
    "name": "Homework 1",
    "due_at": "2026-09-18T23:59:00Z",
    "submission": {"submitted_at": null}
  },
  {
    "id": 9002,
    "name": "Quiz 2",
    "due_at": "2026-09-10T23:59:00Z",
    "submission": {"submitted_at": null}
  },
  {
    "id": 9003,
    "name": "Project Proposal",
    "due_at": "2026-09-15T23:59:00Z",
    "submission": {"submitted_at": "2026-09-13T18:00:00Z"}
  }
]
```

`tests/fixtures/sample_announcements.json`:

```json
[
  {
    "context_code": "course_111",
    "title": "Week 5 Overview",
    "message": "This week, please watch Lecture 4 before Friday and read Chapter 5 before class on Wednesday.",
    "posted_at": "2026-09-14T09:00:00Z"
  }
]
```

- [ ] **Step 2: Write the failing tests**

`tests/test_ingest.py`:

```python
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


def test_run_ingest_falls_back_to_unknown_course_for_unrecognized_context_code(conn, sample_courses):
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    weird_announcement = [
        {
            "context_code": "group_999",
            "title": "Study Group Reminder",
            "message": "Don't forget the study group meets Friday.",
            "posted_at": "2026-09-14T09:00:00Z",
        }
    ]
    with patch("canvas_todo.ingest.canvas_client.get_active_courses", return_value=sample_courses), \
         patch("canvas_todo.ingest.canvas_client.get_assignments_with_submissions", return_value=[]), \
         patch("canvas_todo.ingest.canvas_client.get_announcements", return_value=weird_announcement):
        result = ingest.run_ingest(conn, now=now)

    assert result["announcements"][0]["course_name"] == "Unknown"


def test_main_prints_clean_json_error_on_unexpected_exception(tmp_path, monkeypatch, capsys):
    import sys as sys_module

    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(sys_module, "argv", ["ingest.py", "--db", db_path])

    def _boom(conn, now=None):
        raise ValueError("simulated unexpected failure")

    with patch("canvas_todo.ingest.run_ingest", side_effect=_boom):
        with pytest.raises(SystemExit) as exc_info:
            ingest.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert printed == {"error": "simulated unexpected failure"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'canvas_todo.ingest'`

- [ ] **Step 4: Implement `canvas_todo/ingest.py`**

```python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from canvas_todo import canvas_client, db
from canvas_todo.dateutils import utc_now, week_of


def compute_status(assignment: dict, now: datetime) -> str:
    submission = assignment.get("submission") or {}
    if submission.get("submitted_at"):
        return "done"
    due_at = assignment.get("due_at")
    if due_at:
        due_dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        if due_dt < now:
            return "overdue"
    return "pending"


def run_ingest(conn, now: datetime | None = None) -> dict:
    now = now or utc_now()
    wk = week_of(now)
    courses = canvas_client.get_active_courses()
    course_by_id = {c["id"]: (c.get("course_code") or c.get("name", "Unknown")) for c in courses}

    for course in courses:
        assignments = canvas_client.get_assignments_with_submissions(course["id"])
        for assignment in assignments:
            due_at = assignment.get("due_at")
            if due_at is None:
                continue  # undated assignments aren't part of a "this week" view
            db.upsert_graded_item(
                conn,
                course_name=course_by_id[course["id"]],
                title=assignment["name"],
                due_at=due_at,
                status=compute_status(assignment, now),
                canvas_assignment_id=assignment["id"],
                created_week=wk,
            )

    announcements = canvas_client.get_announcements(list(course_by_id.keys()), since_days=7)
    enriched_announcements = []
    for ann in announcements:
        context_code = ann.get("context_code", "")
        course_id = (
            int(context_code.replace("course_", "")) if context_code.startswith("course_") else None
        )
        enriched_announcements.append(
            {
                "course_name": course_by_id.get(course_id, "Unknown"),
                "title": ann.get("title", ""),
                "message": ann.get("message", ""),
                "posted_at": ann.get("posted_at"),
            }
        )

    db.insert_weekly_run(
        conn,
        run_at=now.isoformat(),
        week_of=wk,
        raw_announcement_snapshot=json.dumps(enriched_announcements),
    )
    return {"week_of": wk, "announcements": enriched_announcements}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Canvas assignments + announcements")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    args = parser.parse_args()

    conn = db.get_connection(args.db)
    db.init_db(conn)
    try:
        result = run_ingest(conn)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_ingest.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add canvas_todo/ingest.py tests/test_ingest.py tests/fixtures/
git commit -m "feat: add Canvas ingestion CLI with graded-status derivation"
```

---

### Task 6: Ungraded Item Upsert CLI

**Files:**
- Create: `canvas_todo/upsert_ungraded.py`
- Test: `tests/test_upsert_ungraded.py`

- [ ] **Step 1: Write the failing test**

`tests/test_upsert_ungraded.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_upsert_ungraded.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'canvas_todo.upsert_ungraded'`

- [ ] **Step 3: Implement `canvas_todo/upsert_ungraded.py`**

```python
from __future__ import annotations

import argparse
import json
import sys

from canvas_todo import db
from canvas_todo.dateutils import utc_now, week_of


def upsert_items(conn, items: list[dict], wk: str) -> dict:
    created = []
    skipped = []
    for item in items:
        item_id, was_created = db.upsert_ungraded_item(
            conn,
            course_name=item["course_name"],
            title=item["title"],
            due_at=item.get("due_at"),
            created_week=wk,
        )
        (created if was_created else skipped).append({"id": item_id, "title": item["title"]})
    return {"created": created, "skipped_duplicates": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upsert ungraded to-do items extracted from Canvas announcements"
    )
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument(
        "--items-json",
        required=True,
        help='JSON array, e.g. \'[{"course_name": "CS101", "title": "Watch Lecture 4", "due_at": null}]\'',
    )
    args = parser.parse_args()

    conn = db.get_connection(args.db)
    db.init_db(conn)
    wk = week_of(utc_now())
    try:
        items = json.loads(args.items_json)
        result = upsert_items(conn, items, wk)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

This CLI's only input (`--items-json`) is populated by an LLM (the Task 11 scheduled agent
extracting to-do items from Canvas announcement text), which is inherently probabilistic.
`main()` therefore wraps JSON parsing and the upsert loop in a broad `try/except` so that
malformed JSON or an item missing a required key (`course_name`/`title`) produces a clean
`{"error": ...}` JSON line on stdout and exits 1, instead of an uncaught traceback with no
output — matching the pattern established in Task 5's `ingest.py::main()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_upsert_ungraded.py -v`
Expected: 1 passed

- [ ] **Step 5: Add error-handling tests**

Append to `tests/test_upsert_ungraded.py` (requires adding `import json` at the top,
alongside the existing `sqlite3`, `pytest`, and `upsert_ungraded` imports):

```python
def test_main_prints_clean_json_error_on_malformed_json(tmp_path, monkeypatch, capsys):
    import sys as sys_module

    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(
        sys_module, "argv", ["upsert_ungraded.py", "--db", db_path, "--items-json", "not valid json{"]
    )

    with pytest.raises(SystemExit) as exc_info:
        upsert_ungraded.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert "error" in printed


def test_main_prints_clean_json_error_on_missing_required_key(tmp_path, monkeypatch, capsys):
    import sys as sys_module

    db_path = str(tmp_path / "test.db")
    bad_items_json = json.dumps([{"course_name": "CS101"}])  # missing "title"
    monkeypatch.setattr(
        sys_module, "argv", ["upsert_ungraded.py", "--db", db_path, "--items-json", bad_items_json]
    )

    with pytest.raises(SystemExit) as exc_info:
        upsert_ungraded.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert "error" in printed
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_upsert_ungraded.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add canvas_todo/upsert_ungraded.py tests/test_upsert_ungraded.py
git commit -m "feat: add CLI to upsert LLM-extracted ungraded to-do items"
```

---

### Task 7: Digest Builder CLI

**Files:**
- Create: `canvas_todo/digest.py`
- Test: `tests/test_digest.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_digest.py`:

```python
import sqlite3
from datetime import datetime, timezone

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
    assert printed == {"error": "simulated unexpected failure"}


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
```

Note: this test needs `import json` and `from unittest.mock import patch` added to this file's imports (alongside the existing `sqlite3`, `datetime`, `pytest` imports) — this follows the same `try/except Exception` error-handling pattern established in `ingest.py::main()` (Task 5) and `upsert_ungraded.py::main()` (Task 6), applied here proactively for consistency rather than waiting for a review cycle to flag the same gap a third time. The three additional tests above (overdue routing, marker clearing after `mark_reminded`, and `done`-item omission) were added during code review to close coverage gaps and lock in the Step 3 fix for dangling empty course headers.

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_digest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'canvas_todo.digest'`

- [ ] **Step 3: Implement `canvas_todo/digest.py`**

```python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

from canvas_todo import db
from canvas_todo.dateutils import utc_now, week_of

URGENT_WINDOW_HOURS = 24


def build_digest(conn, wk: str, now: datetime) -> dict:
    items = db.get_items_for_week(conn, wk)

    by_course: dict[str, dict[str, list]] = {}
    urgent_lines = []
    reminded_ids = []

    for item in items:
        if item["status"] == "done":
            continue

        course = item["course_name"]
        by_course.setdefault(course, {"due": [], "overdue": [], "not_checked": []})
        reminded_ids.append(item["id"])

        is_new = item["last_reminded_at"] is None
        marker = " 🆕" if is_new else ""

        if item["status"] == "overdue":
            by_course[course]["overdue"].append(f"- {item['title']}{marker}")
        elif item["type"] == "ungraded" and item["status"] == "pending":
            by_course[course]["not_checked"].append(f"- {item['title']}{marker}")
        elif item["status"] == "pending":
            by_course[course]["due"].append(f"- {item['title']} (due {item['due_at']}){marker}")

        if item["type"] == "graded" and item["status"] == "pending" and item["due_at"]:
            due_dt = datetime.fromisoformat(item["due_at"].replace("Z", "+00:00"))
            if now <= due_dt <= now + timedelta(hours=URGENT_WINDOW_HOURS):
                urgent_lines.append(
                    f"⚠️ {course}: {item['title']} is due within 24 hours and not submitted!"
                )

    digest_parts = [f"📋 Weekly Canvas Digest ({wk})\n"]
    for course, sections in by_course.items():
        digest_parts.append(f"\n**{course}**")
        if sections["due"]:
            digest_parts.append("Due this week:\n" + "\n".join(sections["due"]))
        if sections["overdue"]:
            digest_parts.append("Overdue:\n" + "\n".join(sections["overdue"]))
        if sections["not_checked"]:
            digest_parts.append("Not yet checked off:\n" + "\n".join(sections["not_checked"]))

    digest_text = "\n".join(digest_parts)
    urgent_text = "\n".join(urgent_lines) if urgent_lines else None

    return {"digest_text": digest_text, "urgent_text": urgent_text, "reminded_ids": reminded_ids}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the weekly Telegram digest from current DB state")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    args = parser.parse_args()

    conn = db.get_connection(args.db)
    db.init_db(conn)
    try:
        now = utc_now()
        wk = week_of(now)
        result = build_digest(conn, wk, now)
        # Marked as "reminded" here, before Telegram delivery is attempted (Task 8).
        # Accepted tradeoff for this POC: if the send fails, these items won't show
        # the 🆕 marker on a retry, but they still reappear in every future digest
        # until resolved (get_items_for_week never drops unresolved items). Moving
        # this to fire only after confirmed delivery would require passing ids
        # through the scheduled agent's orchestration across two separate CLI
        # invocations (digest.py then telegram_client.py) — not worth the added
        # complexity for a single-user POC.
        db.mark_reminded(conn, result["reminded_ids"], now.isoformat())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
    print(json.dumps({"digest_text": result["digest_text"], "urgent_text": result["urgent_text"]}))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_digest.py -v`
Expected: 7 passed (3 core tests + 1 error-handling test, added proactively per the Task 5/6 `main()` error-handling precedent, + 3 code-review tests covering overdue routing, marker clearing after `mark_reminded`, and `done`-item omission)

- [ ] **Step 5: Commit**

```bash
git add canvas_todo/digest.py tests/test_digest.py
git commit -m "feat: add digest builder with course grouping and 24h urgent-alert logic"
```

---

### Task 8: Telegram Client CLI

**Files:**
- Create: `canvas_todo/telegram_client.py`
- Test: `tests/test_telegram_client.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_telegram_client.py`:

```python
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-bot-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")

from canvas_todo import telegram_client


@patch("canvas_todo.telegram_client.requests.post")
def test_send_message_posts_to_telegram_api(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    telegram_client.send_message("hello")
    args, kwargs = mock_post.call_args
    assert "test-bot-token" in args[0]
    assert kwargs["data"]["chat_id"] == "12345"
    assert kwargs["data"]["text"] == "hello"


@patch("canvas_todo.telegram_client.requests.post")
def test_send_message_raises_on_failure(mock_post):
    mock_post.return_value = MagicMock(status_code=400, text="bad request")
    with pytest.raises(telegram_client.TelegramError):
        telegram_client.send_message("hello")


def test_main_prints_clean_json_error_on_send_failure(monkeypatch, capsys):
    import sys as sys_module

    monkeypatch.setattr(sys_module, "argv", ["telegram_client.py", "--message", "hello"])

    def _boom(text):
        raise telegram_client.TelegramError("Telegram send failed: 400 bad request")

    with patch("canvas_todo.telegram_client.send_message", side_effect=_boom):
        with pytest.raises(SystemExit) as exc_info:
            telegram_client.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert printed == {"error": "Telegram send failed: 400 bad request"}


def test_send_message_raises_clear_error_when_token_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(telegram_client.TelegramError, match="TELEGRAM_BOT_TOKEN"):
        telegram_client.send_message("hello")


def test_send_message_sanitizes_connection_error():
    import requests as requests_module

    with patch(
        "canvas_todo.telegram_client.requests.post",
        side_effect=requests_module.exceptions.ConnectionError(
            "Max retries exceeded with url: /botREALSECRETTOKEN12345/sendMessage (Caused by ...)"
        ),
    ):
        with pytest.raises(telegram_client.TelegramError) as exc_info:
            telegram_client.send_message("hello")

    assert "REALSECRETTOKEN12345" not in str(exc_info.value)
    assert "ConnectionError" in str(exc_info.value)
```

Note: this test file needs `import json` added at the top alongside the other imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_telegram_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'canvas_todo.telegram_client'`

- [ ] **Step 3: Implement `canvas_todo/telegram_client.py`**

```python
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramError(Exception):
    pass


def send_message(text: str) -> None:
    try:
        bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
        chat_id = os.environ["TELEGRAM_CHAT_ID"]
    except KeyError as exc:
        raise TelegramError(f"{exc.args[0]} is not set (check your .env file)") from exc

    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
    try:
        response = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=15)
    except requests.exceptions.RequestException as exc:
        raise TelegramError(f"Telegram request failed: {type(exc).__name__}") from exc

    if response.status_code != 200:
        raise TelegramError(f"Telegram send failed: {response.status_code} {response.text[:200]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a Telegram message")
    parser.add_argument("--message", required=True, help="Message text to send")
    args = parser.parse_args()
    try:
        send_message(args.message)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
```

Note: `main()` applies the same `try/except Exception` → clean JSON error → `sys.exit(1)` pattern established in Tasks 5–7, for consistency across all the project's CLIs even though nothing downstream currently parses this particular CLI's output.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_telegram_client.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add canvas_todo/telegram_client.py tests/test_telegram_client.py
git commit -m "feat: add Telegram message-sending CLI with clean error handling"
```

---

### Task 9: Flask Web App

**Files:**
- Create: `canvas_todo/web.py`
- Create: `templates/index.html`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_web.py`:

```python
import os
import tempfile

import pytest

from canvas_todo import db
from canvas_todo.dateutils import utc_now, week_of
from canvas_todo.web import create_app


@pytest.fixture
def app_and_ids():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = db.get_connection(path)
    db.init_db(conn)
    wk = week_of(utc_now())
    graded_id = db.upsert_graded_item(
        conn, course_name="CS101", title="Homework 1", due_at="2026-09-20T23:59:00Z",
        status="done", canvas_assignment_id=1, created_week=wk,
    )
    ungraded_id, _ = db.upsert_ungraded_item(
        conn, course_name="CS101", title="Watch Lecture 4", due_at=None, created_week=wk,
    )
    conn.close()

    app = create_app(path)
    app.config["TESTING"] = True
    yield app, graded_id, ungraded_id
    os.remove(path)


def test_index_shows_items_grouped_by_course(app_and_ids):
    app, _, _ = app_and_ids
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"CS101" in response.data
    assert b"Homework 1" in response.data
    assert b"Watch Lecture 4" in response.data


def test_toggle_ungraded_item_flips_status(app_and_ids):
    app, _, ungraded_id = app_and_ids
    client = app.test_client()
    response = client.post(f"/items/{ungraded_id}/toggle")
    assert response.status_code == 200
    assert response.get_json()["status"] == "done"


def test_toggle_graded_item_returns_400(app_and_ids):
    app, graded_id, _ = app_and_ids
    client = app.test_client()
    response = client.post(f"/items/{graded_id}/toggle")
    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_web.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'canvas_todo.web'`

- [ ] **Step 3: Implement `templates/index.html`**

```html
<!DOCTYPE html>
<html>
<head>
  <title>Canvas Weekly To-Do</title>
  <style>
    body { font-family: sans-serif; max-width: 700px; margin: 2rem auto; }
    .course { margin-bottom: 1.5rem; }
    .course h2 { border-bottom: 1px solid #ccc; }
    .item { padding: 0.25rem 0; }
    .item.auto-tracked { color: #888; }
    .item .due { color: #555; font-size: 0.85em; margin-left: 0.5rem; }
  </style>
</head>
<body>
  <h1>This Week</h1>
  {% for course_name, items in by_course.items() %}
  <div class="course">
    <h2>{{ course_name }}</h2>
    {% for item in items %}
    <div class="item {% if item['auto_tracked'] %}auto-tracked{% endif %}">
      <input
        type="checkbox"
        {% if item['status'] == 'done' %}checked{% endif %}
        {% if item['auto_tracked'] %}disabled{% endif %}
        data-item-id="{{ item['id'] }}"
        onclick="toggleItem({{ item['id'] }})"
      >
      <span>{{ item['title'] }}</span>
      {% if item['due_at'] %}<span class="due">due {{ item['due_at'] }}</span>{% endif %}
    </div>
    {% endfor %}
  </div>
  {% endfor %}

  <script>
    async function toggleItem(itemId) {
      const response = await fetch(`/items/${itemId}/toggle`, { method: "POST" });
      if (!response.ok) {
        alert("Couldn't update that item.");
        location.reload();
      }
    }
  </script>
</body>
</html>
```

- [ ] **Step 4: Implement `canvas_todo/web.py`**

```python
from __future__ import annotations

import os

from flask import Flask, jsonify, render_template

from canvas_todo import db
from canvas_todo.dateutils import utc_now, week_of

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_TEMPLATE_DIR = os.path.join(os.path.dirname(_PACKAGE_DIR), "templates")


def create_app(db_path: str) -> Flask:
    app = Flask(__name__, template_folder=_TEMPLATE_DIR)
    app.config["DB_PATH"] = db_path

    @app.route("/")
    def index():
        conn = db.get_connection(app.config["DB_PATH"])
        db.init_db(conn)
        wk = week_of(utc_now())
        items = db.get_items_for_week(conn, wk)

        by_course: dict[str, list] = {}
        for item in items:
            by_course.setdefault(item["course_name"], []).append(item)

        return render_template("index.html", by_course=by_course)

    @app.route("/items/<int:item_id>/toggle", methods=["POST"])
    def toggle(item_id: int):
        conn = db.get_connection(app.config["DB_PATH"])
        db.init_db(conn)
        try:
            new_status = db.toggle_item(conn, item_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"id": item_id, "status": new_status})

    return app


if __name__ == "__main__":
    app = create_app(os.environ.get("CANVAS_TODO_DB", "canvas_todo.db"))
    app.run(debug=True)
```

Note: `Flask(__name__, template_folder=_TEMPLATE_DIR)` is required here, not `Flask(__name__)`. Since `web.py` lives inside the `canvas_todo` package, Flask's default template-folder resolution looks for `canvas_todo/templates/`, not the top-level `templates/` directory this task creates — verified empirically during implementation (`Flask('canvas_todo.web').root_path` resolves to the `canvas_todo/` directory itself). `_TEMPLATE_DIR` is computed as the `templates/` directory one level up from the package, keeping the top-level layout the plan specifies while making `render_template` actually find the file.

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_web.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add canvas_todo/web.py templates/index.html tests/test_web.py
git commit -m "feat: add Flask web app for browsing and toggling the weekly list"
```

---

### Task 10: README with Setup Instructions

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Canvas Weekly To-Do & Reminder App (Personal POC)

Tracks graded Canvas assignments (auto-checked off via submission status) and
ungraded to-dos inferred from Canvas announcements, shown in a local web app,
with daily Telegram reminders.

## One-time setup

1. **Canvas API token**: Canvas → Account → Settings → "New Access Token".
   Also note your Canvas instance base URL (e.g. `https://illinois.instructure.com`).
2. **Telegram bot**:
   - Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`,
     follow the prompts. You'll get a bot token.
   - Send any message to your new bot, then visit
     `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser —
     your `chat.id` is in the JSON response. That's your `TELEGRAM_CHAT_ID`.
3. Copy `.env.template` to `.env` and fill in all four values plus
   `CANVAS_TODO_DB` (default `canvas_todo.db` is fine).
4. Install dependencies:
   ```bash
   python3 -m venv venv
   venv/bin/pip install -r requirements.txt
   ```
5. Run the test suite to confirm everything's wired up:
   ```bash
   venv/bin/pytest
   ```

## Running the web app

```bash
set -a && source .env && set +a
venv/bin/python -m canvas_todo.web
```

Open `http://localhost:5000`.

## Running the daily check manually (without waiting for the schedule)

```bash
set -a && source .env && set +a
venv/bin/python -m canvas_todo.ingest --db canvas_todo.db
```

This prints JSON with the week's announcements. The scheduled Claude agent
(see below) reads that output, decides which announcements describe concrete
ungraded to-dos, and calls `upsert_ungraded`, `digest`, and `telegram_client`
in turn. Running `ingest` alone will not send a Telegram message or extract
ungraded items — it only updates graded-assignment status from Canvas.

## Scheduled daily agent

Registered via this platform's scheduled-task feature (see
`docs/superpowers/plans/2026-09-14-canvas-todo-implementation.md`, Task 11,
for the exact registration call and prompt). Runs once daily while the
Claude Code app is open; if closed at run time, it fires on next launch.

## Known limitations (accepted for this POC)

- Announcement → to-do extraction is LLM-based and not perfectly precise;
  occasional missed/duplicate items are expected (see design spec).
- No EdStem lecture-watch-progress integration yet (phase 2, see design spec's
  Future Enhancements section).
- Single user, `localhost`-only web app, no auth, no deployment.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add setup and usage README"
```

---

### Task 11: Register the Scheduled Agent

> **NOT EXECUTED — superseded (2026-09-16) by `docs/superpowers/specs/2026-09-14-canvas-todo-design.md`, "Amendment 2."** Canvas access is now manually-triggered only (via the Chrome extension in a live conversation) — there is deliberately no scheduled/unattended automation, since that was the specific pattern rejected on security-control-circumvention grounds for the two prior Canvas-access approaches. This task is never executed. See Task 16 for what replaced it.

This step registers the daily automation using this platform's built-in scheduled-task tool. It must run **after** Tasks 1–10 are complete (the prompt below assumes the venv, `.env`, and all CLI modules already exist and work).

- [ ] **Step 1: Confirm prerequisites**

Run: `ls ~/canvas-todo-app/venv/bin/python ~/canvas-todo-app/.env ~/canvas-todo-app/courses.json`
Expected: all three paths exist. If `.env` doesn't exist yet, copy it from `.env.template` and fill in your Canvas Calendar Feed URL and Telegram credentials. If `courses.json` doesn't exist yet, create it listing each active course's name and Announcements feed URL (see the README and Task 12 below) — the scheduled agent will fail every run without both.

- [ ] **Step 2: Call `create_scheduled_task`**

Call the `create_scheduled_task` tool with exactly these arguments:

- `taskId`: `canvas-weekly-checkin`
- `cronExpression`: `30 7 * * *`
- `description`: `Daily Canvas ingest + Telegram digest for weekly to-do tracking`
- `notifyOnCompletion`: `false`
- `prompt`:

```
You are running the daily Canvas weekly check-in for shashank.wmr@gmail.com. Work entirely inside ~/canvas-todo-app. A Python virtualenv already exists at ~/canvas-todo-app/venv; use ~/canvas-todo-app/venv/bin/python for every script invocation below. The SQLite database is at ~/canvas-todo-app/canvas_todo.db. Environment variables (Canvas + Telegram credentials) live in ~/canvas-todo-app/.env and must be loaded in the SAME bash call as each script invocation, since exported variables don't persist between separate tool calls. The `canvas_todo` package is also only importable when the shell's current directory is the project root (running it via `python -m` resolves the package relative to the working directory, not the venv's location) — for both reasons, prefix EVERY command below with `cd ~/canvas-todo-app && set -a && source .env && set +a &&`, never skip the `cd` even if a previous command in the same run already did it, since each tool call may start a fresh shell.

Step 1 — Ingest Canvas data:
Run: cd ~/canvas-todo-app && set -a && source .env && set +a && venv/bin/python -m canvas_todo.ingest --db canvas_todo.db

This pulls active courses, upserts graded assignment status (submitted/overdue/pending) directly into the database, and prints JSON to stdout shaped like: {"week_of": "YYYY-MM-DD", "announcements": [{"course_name": ..., "title": ..., "message": ..., "posted_at": ...}, ...]}.

If this command's JSON output includes `"session_expired": true`, skip directly to Step 5 and send exactly one Telegram message: "🔒 Your Canvas session has expired. Please run: cd ~/canvas-todo-app && venv/bin/python -m canvas_todo.canvas_login_setup — to log in again." Do not attempt Steps 2-4 in that case.

If this command exits non-zero for any OTHER reason (and the output does not have `"session_expired": true`), skip directly to Step 5 and send exactly one Telegram message: "⚠️ Couldn't reach Canvas today — didn't update your to-do list. Will retry tomorrow." Do not attempt Steps 2-4 in that case.

Step 2 — Extract ungraded to-do items from announcements:
Read the "announcements" array from Step 1's output. For each announcement, read its "message" field (ignore any HTML markup) and decide whether it describes a concrete action the student needs to take that is NOT already a graded Canvas assignment — for example "watch Lecture 4 before Friday," "read Chapter 5 before class," "complete the practice problems (ungraded) by Monday." For each such action, build an object: {"course_name": <the announcement's course_name>, "title": <a short imperative phrase, e.g. "Watch Lecture 4">, "due_at": <an ISO 8601 date if the announcement states or clearly implies one, otherwise null>}.

Skip announcements that are purely informational (e.g. "class is cancelled Monday," "grades are posted," "welcome to the course") — only extract items that require the student to actually do something ungraded. If an announcement describes something that sounds like a graded assignment, skip it too (Step 1 already captured graded assignments directly from Canvas).

If you extract zero items, skip Step 3 entirely and go to Step 4.

Step 3 — Save the extracted items:
Run the following, substituting a valid single-quoted JSON array for ITEMS_JSON containing every object you built in Step 2:
cd ~/canvas-todo-app && set -a && source .env && set +a && venv/bin/python -m canvas_todo.upsert_ungraded --db canvas_todo.db --items-json 'ITEMS_JSON'

Step 4 — Build the digest:
Run: cd ~/canvas-todo-app && set -a && source .env && set +a && venv/bin/python -m canvas_todo.digest --db canvas_todo.db

This prints JSON shaped like: {"digest_text": "...", "urgent_text": "..." or null}.

Step 5 — Send Telegram message(s):
Always send one message with the digest_text from Step 4 (or the Canvas-unreachable message from Step 1's failure branch), using:
cd ~/canvas-todo-app && set -a && source .env && set +a && venv/bin/python -m canvas_todo.telegram_client --message "TEXT_HERE"

If Step 4's urgent_text is not null, send it as a second, separate call to the same command with the urgent_text as the message.

This task runs unattended — do not ask the user any questions and do not narrate these steps back to them. Just execute the steps in order and stop once the Telegram message(s) have been sent successfully.
```

- [ ] **Step 3: Verify registration**

Call `list_scheduled_tasks` and confirm `canvas-weekly-checkin` appears, `enabled` is true, and `nextRunAt` is tomorrow at 7:30am local time.

- [ ] **Step 4: Manual smoke test**

Since the cron won't fire for up to 24 hours, manually verify the full chain once by running Steps 1, 4, and 5 of the prompt above by hand from a terminal (skip Step 2/3 unless you want to test extraction too), confirming a real Telegram message arrives on your phone.

- [ ] **Step 5: Commit the plan/task registration note**

No code changes in this task — nothing to commit. If you want a record, add a line to `README.md`'s "Scheduled daily agent" section noting the task was registered on today's date, then:

```bash
git add README.md
git commit -m "docs: note scheduled task registration"
```

---

## Amendment 2 (2026-09-16): Manually-Triggered Ingestion via Chrome Extension

Supersedes Tasks 4, 5, and 11 above (left in place as historical record, each marked SUPERSEDED/NOT EXECUTED). See `docs/superpowers/specs/2026-09-14-canvas-todo-design.md`, "Amendment 2," for full rationale: Georgia Tech blocks student API tokens; a session-cookie approach and a token-free-feed approach were each considered and abandoned; the resolution is that Claude reads Canvas live via the Chrome extension **only when the user actively asks in conversation**, never on an unattended schedule.

### Task 16: Retire REST Canvas Client, Add Manual Ingestion CLI

**Files:**
- Delete: `canvas_todo/canvas_client.py`
- Delete: `canvas_todo/ingest.py`
- Delete: `tests/test_canvas_client.py`
- Delete: `tests/test_ingest.py`
- Delete: `tests/fixtures/sample_courses.json`
- Delete: `tests/fixtures/sample_assignments.json`
- Delete: `tests/fixtures/sample_announcements.json`
- Create: `canvas_todo/manual_ingest.py`
- Test: `tests/test_manual_ingest.py`
- Modify: `.env.template`
- Modify: `README.md`

- [ ] **Step 1: Delete the retired REST-API modules and their tests/fixtures**

```bash
git rm canvas_todo/canvas_client.py canvas_todo/ingest.py tests/test_canvas_client.py tests/test_ingest.py
git rm -r tests/fixtures
```

- [ ] **Step 2: Run the full suite to confirm nothing else depends on the removed modules**

Run: `venv/bin/pytest -q`
Expected: passes with a reduced count (removing ~20 tests between the two deleted test files — confirm the actual number rather than assuming), zero import errors from any remaining module.

- [ ] **Step 3: Write the failing tests**

`tests/test_manual_ingest.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_manual_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'canvas_todo.manual_ingest'`

- [ ] **Step 5: Implement `canvas_todo/manual_ingest.py`**

```python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from canvas_todo import db
from canvas_todo.dateutils import utc_now, week_of


def compute_status(assignment: dict, now: datetime) -> str:
    if assignment.get("submitted"):
        return "done"
    due_at = assignment.get("due_at")
    if due_at:
        due_dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        if due_dt < now:
            return "overdue"
    return "pending"


def run_manual_ingest(conn, data: dict, now: datetime | None = None) -> dict:
    now = now or utc_now()
    wk = week_of(now)

    for course in data.get("courses", []):
        course_name = course["course_name"]
        for assignment in course.get("assignments", []):
            due_at = assignment.get("due_at")
            if due_at is None:
                continue  # undated assignments aren't part of a "this week" view
            db.upsert_graded_item(
                conn,
                course_name=course_name,
                title=assignment["title"],
                due_at=due_at,
                status=compute_status(assignment, now),
                canvas_assignment_id=assignment["canvas_assignment_id"],
                created_week=wk,
            )

    announcements = data.get("announcements", [])
    db.insert_weekly_run(
        conn,
        run_at=now.isoformat(),
        week_of=wk,
        raw_announcement_snapshot=json.dumps(announcements),
    )
    return {"week_of": wk, "announcements": announcements}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Persist Canvas data Claude read live via the Chrome extension"
    )
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument(
        "--data-json",
        required=True,
        help='JSON object: {"courses": [{"course_name": ..., "assignments": [{"canvas_assignment_id": ..., "title": ..., "due_at": ..., "submitted": ...}]}], "announcements": [{"course_name": ..., "title": ..., "message": ..., "posted_at": ...}]}',
    )
    args = parser.parse_args()

    conn = db.get_connection(args.db)
    db.init_db(conn)
    try:
        data = json.loads(args.data_json)
        result = run_manual_ingest(conn, data)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

Note this module has NO dependency on `canvas_client.py` (deleted in Step 1) — it only depends on `db.py` and `dateutils.py`, both unchanged from Tasks 2-3. `compute_status` is intentionally similar to the old `ingest.py`'s version but reads a flat `submitted: bool` field instead of a nested `submission.submitted_at` structure, since Claude reports what it directly observes on the Canvas UI (a "Submitted"/"Not Submitted" indicator) rather than a raw API payload shape.

- [ ] **Step 6: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_manual_ingest.py -v`
Expected: 9 passed

- [ ] **Step 7: Run the full suite**

Run: `venv/bin/pytest -q`
Expected: all tests pass, no import errors, no leftover references to the deleted modules anywhere in the test suite.

- [ ] **Step 8: Update `.env.template`**

Replace the "Canvas API" section (which previously had `CANVAS_API_URL`/`CANVAS_API_TOKEN`) — remove it entirely, since no Canvas credentials of any kind are needed anymore. New contents:

```
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# App
CANVAS_TODO_DB=canvas_todo.db
```

- [ ] **Step 9: Rewrite the relevant `README.md` sections**

Replace the "One-time setup" step 1 (Canvas API token) and the entire "Scheduled daily agent" section. New content for "One-time setup":

```markdown
## One-time setup

1. **Canvas access**: none needed! This app doesn't use a Canvas API token,
   login, or session — Georgia Tech blocks student-generated tokens, so
   instead you ask Claude (with the Chrome extension connected) to read
   Canvas live through your own already-logged-in browser tab. See "Checking
   your Canvas" below.
2. **Telegram bot**:
   - Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`,
     follow the prompts. You'll get a bot token.
   - Send any message to your new bot, then visit
     `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser —
     your `chat.id` is in the JSON response. That's your `TELEGRAM_CHAT_ID`.
3. Copy `.env.template` to `.env` and fill in both Telegram values plus
   `CANVAS_TODO_DB` (default `canvas_todo.db` is fine).
4. Install dependencies:
   ```bash
   python3 -m venv venv
   venv/bin/pip install -r requirements.txt
   ```
5. Run the test suite to confirm everything's wired up:
   ```bash
   venv/bin/pytest
   ```
```

Replace "Running the daily check manually (without waiting for the schedule)" and "Scheduled daily agent" with:

```markdown
## Checking your Canvas

There is no automatic daily check — ask Claude directly, in an active
conversation, something like "check my Canvas" or "what's due this week."
Claude uses the Chrome extension to read your courses, assignments, and
announcements from your already-logged-in Canvas tab, then:

1. Calls `canvas_todo.manual_ingest` to save graded-assignment status into
   the database.
2. Reads announcement text and calls `canvas_todo.upsert_ungraded` for any
   ungraded to-dos it finds (readings, lectures to watch, etc.).
3. Calls `canvas_todo.digest` to build a summary and `canvas_todo.telegram_client`
   to send it to you.

This is deliberately not automated — see the design spec's "Amendment 2"
for why (Georgia Tech blocks the kind of unattended automated access this
would otherwise require).
```

- [ ] **Step 10: Update the "Known limitations" section**

Replace the existing bullet about "No EdStem..." list to also note:

```markdown
- No automatic/scheduled checks — you must ask Claude to check Canvas each
  time; nothing runs in the background. This is a deliberate tradeoff, not
  a bug (see design spec Amendment 2).
```

- [ ] **Step 11: Commit**

```bash
git add canvas_todo/manual_ingest.py tests/test_manual_ingest.py .env.template README.md
git commit -m "feat: replace REST/token Canvas access with manually-triggered Chrome-extension ingestion"
```

---

## Definition of Done

- [ ] `venv/bin/pytest` passes with 0 failures across all test files.
- [ ] `venv/bin/python -m canvas_todo.web` serves a page at `localhost:5000` showing at least one real course after a manual Canvas check has been run once.
- [ ] Asking Claude to "check my Canvas" in a live conversation results in `manual_ingest` → (optionally `upsert_ungraded`) → `digest` → `telegram_client` running in sequence and a real Telegram message arriving.
- [ ] No scheduled task is registered for this project — confirm `list_scheduled_tasks` does not include `canvas-weekly-checkin` (or any Canvas-related task).
- [ ] Toggling any item's checkbox in the web app (graded or ungraded — both are user-toggled now) persists across a page reload.
- [ ] No file in the repository references `CANVAS_API_TOKEN`, `CANVAS_API_URL`, `canvas_session_profile`, or `courses.json` (grep to confirm) — all now-inapplicable artifacts from the abandoned approaches are fully removed.
