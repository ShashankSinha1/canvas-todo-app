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
    assert kwargs["data"]["parse_mode"] == "Markdown"


@patch("canvas_todo.telegram_client.requests.post")
def test_send_message_raises_on_failure(mock_post):
    mock_post.return_value = MagicMock(status_code=400, text="bad request")
    with pytest.raises(telegram_client.TelegramError):
        telegram_client.send_message("hello")


def test_main_prints_clean_json_error_on_send_failure(monkeypatch, capsys):
    import sys as sys_module

    monkeypatch.setattr(sys_module, "argv", ["telegram_client.py", "--message", "hello"])

    def _boom(text):
        raise telegram_client.TelegramError("Telegram send failed: 400 bad request")

    with patch("canvas_todo.telegram_client.send_message", side_effect=_boom):
        with pytest.raises(SystemExit) as exc_info:
            telegram_client.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert printed == {"error": "Telegram send failed: 400 bad request"}


def test_send_message_raises_clear_error_when_token_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(telegram_client.TelegramError, match="TELEGRAM_BOT_TOKEN"):
        telegram_client.send_message("hello")


def test_send_message_sanitizes_connection_error():
    import requests as requests_module

    with patch(
        "canvas_todo.telegram_client.requests.post",
        side_effect=requests_module.exceptions.ConnectionError(
            "Max retries exceeded with url: /botREALSECRETTOKEN12345/sendMessage (Caused by ...)"
        ),
    ):
        with pytest.raises(telegram_client.TelegramError) as exc_info:
            telegram_client.send_message("hello")

    assert "REALSECRETTOKEN12345" not in str(exc_info.value)
    assert "ConnectionError" in str(exc_info.value)
