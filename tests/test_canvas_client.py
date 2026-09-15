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
