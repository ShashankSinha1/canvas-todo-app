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
