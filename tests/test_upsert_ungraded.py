import json
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


def test_main_reads_from_items_file(tmp_path, monkeypatch, capsys):
    import sys as sys_module

    db_path = str(tmp_path / "test.db")
    items_file = tmp_path / "items.json"
    items = [{"course_name": "CS101", "title": "Watch Lecture 4", "due_at": None}]
    items_file.write_text(json.dumps(items))
    monkeypatch.setattr(
        sys_module, "argv", ["upsert_ungraded.py", "--db", db_path, "--items-file", str(items_file)]
    )
    upsert_ungraded.main()
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert len(printed["created"]) == 1


def test_main_requires_exactly_one_of_items_json_or_items_file(tmp_path, monkeypatch):
    import sys as sys_module

    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(sys_module, "argv", ["upsert_ungraded.py", "--db", db_path])
    with pytest.raises(SystemExit) as exc_info:
        upsert_ungraded.main()
    assert exc_info.value.code == 2


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
