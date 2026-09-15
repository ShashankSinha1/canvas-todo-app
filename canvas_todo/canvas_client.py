from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

import requests


class CanvasAPIError(Exception):
    pass


def _base_url() -> str:
    url = os.environ["CANVAS_API_URL"].rstrip("/")
    return f"{url}/api/v1"


def _headers() -> dict:
    return {"Authorization": f"Bearer {os.environ['CANVAS_API_TOKEN']}"}


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
