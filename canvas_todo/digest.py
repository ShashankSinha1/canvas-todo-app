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
