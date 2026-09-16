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
