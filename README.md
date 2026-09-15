# Canvas Weekly To-Do & Reminder App (Personal POC)

Tracks graded Canvas assignments (auto-checked off via submission status) and
ungraded to-dos inferred from Canvas announcements, shown in a local web app,
with daily Telegram reminders.

## One-time setup

1. **Canvas API token**: Canvas → Account → Settings → "New Access Token".
   Also note your Canvas instance base URL (e.g. `https://illinois.instructure.com`).
2. **Telegram bot**:
   - Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`,
     follow the prompts. You'll get a bot token.
   - Send any message to your new bot, then visit
     `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser —
     your `chat.id` is in the JSON response. That's your `TELEGRAM_CHAT_ID`.
3. Copy `.env.template` to `.env` and fill in all four values plus
   `CANVAS_TODO_DB` (default `canvas_todo.db` is fine).
4. Install dependencies:
   ```bash
   python3 -m venv venv
   venv/bin/pip install -r requirements.txt
   ```
5. Run the test suite to confirm everything's wired up:
   ```bash
   venv/bin/pytest
   ```

## Running the web app

```bash
set -a && source .env && set +a
venv/bin/python -m canvas_todo.web
```

Open `http://localhost:5000`.

## Running the daily check manually (without waiting for the schedule)

```bash
set -a && source .env && set +a
venv/bin/python -m canvas_todo.ingest --db canvas_todo.db
```

This prints JSON with the week's announcements. The scheduled Claude agent
(see below) reads that output, decides which announcements describe concrete
ungraded to-dos, and calls `upsert_ungraded`, `digest`, and `telegram_client`
in turn. Running `ingest` alone will not send a Telegram message or extract
ungraded items — it only updates graded-assignment status from Canvas.

## Scheduled daily agent

Registered via this platform's scheduled-task feature (see
`docs/superpowers/plans/2026-09-14-canvas-todo-implementation.md`, Task 11,
for the exact registration call and prompt). Runs once daily while the
Claude Code app is open; if closed at run time, it fires on next launch.

## Known limitations (accepted for this POC)

- Announcement → to-do extraction is LLM-based and not perfectly precise;
  occasional missed/duplicate items are expected (see design spec).
- No EdStem lecture-watch-progress integration yet (phase 2, see design spec's
  Future Enhancements section).
- Single user, `localhost`-only web app, no auth, no deployment.
