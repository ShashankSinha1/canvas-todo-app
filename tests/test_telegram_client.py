import json
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
    with pytest.raises(RuntimeError):
        telegram_client.send_message("hello")


def test_main_prints_clean_json_error_on_send_failure(monkeypatch, capsys):
    import sys as sys_module

    monkeypatch.setattr(sys_module, "argv", ["telegram_client.py", "--message", "hello"])

    def _boom(text):
        raise RuntimeError("Telegram send failed: 400 bad request")

    with patch("canvas_todo.telegram_client.send_message", side_effect=_boom):
        with pytest.raises(SystemExit) as exc_info:
            telegram_client.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert printed == {"error": "Telegram send failed: 400 bad request"}
