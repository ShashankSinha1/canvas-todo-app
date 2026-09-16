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
