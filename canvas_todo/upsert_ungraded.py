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
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--items-json",
        help='JSON array inline (only safe for data with no quotes/apostrophes — prefer --items-file), '
        'e.g. \'[{"course_name": "CS101", "title": "Watch Lecture 4", "due_at": null}]\'',
    )
    group.add_argument(
        "--items-file",
        help="Path to a file containing the JSON array (recommended: avoids shell quoting issues "
        "with apostrophes/quotes in real announcement-derived titles)",
    )
    args = parser.parse_args()

    conn = db.get_connection(args.db)
    db.init_db(conn)
    wk = week_of(utc_now())
    try:
        if args.items_file:
            with open(args.items_file, "r", encoding="utf-8") as f:
                raw = f.read()
        else:
            raw = args.items_json
        items = json.loads(raw)
        result = upsert_items(conn, items, wk)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
