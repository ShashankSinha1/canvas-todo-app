from __future__ import annotations

import argparse
import json
import os
import sys

import requests

TELEGRAM_API_BASE = "https://api.telegram.org"


def send_message(text: str) -> None:
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
    response = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=15)
    if response.status_code != 200:
        raise RuntimeError(f"Telegram send failed: {response.status_code} {response.text[:200]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a Telegram message")
    parser.add_argument("--message", required=True, help="Message text to send")
    args = parser.parse_args()
    try:
        send_message(args.message)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
