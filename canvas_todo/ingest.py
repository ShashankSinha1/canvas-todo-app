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
