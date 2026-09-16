# Canvas Weekly To-Do & Reminder App (Personal POC)

Tracks graded Canvas assignments (auto-checked off via submission status) and
ungraded to-dos inferred from Canvas announcements, shown in a local web app,
with daily Telegram reminders.

## One-time setup

1. **Canvas access**: none needed! This app doesn't use a Canvas API token,
   login, or session — Georgia Tech blocks student-generated tokens, so
   instead you ask Claude (with the Chrome extension connected) to read
   Canvas live through your own already-logged-in browser tab. See "Checking
   your Canvas" below.
2. **Telegram bot**:
   - Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`,
     follow the prompts. You'll get a bot token.
   - Send any message to your new bot, then visit
     `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser —
     your `chat.id` is in the JSON response. That's your `TELEGRAM_CHAT_ID`.
3. Copy `.env.template` to `.env` and fill in both Telegram values plus
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

## Checking your Canvas

There is no automatic daily check — ask Claude directly, in an active
conversation, something like "check my Canvas" or "what's due this week."
Claude uses the Chrome extension to read your courses, assignments, and
announcements from your already-logged-in Canvas tab, then:

1. Calls `canvas_todo.manual_ingest` to save graded-assignment status into
   the database.
2. Reads announcement text and calls `canvas_todo.upsert_ungraded` for any
   ungraded to-dos it finds (readings, lectures to watch, etc.).
3. Calls `canvas_todo.digest` to build a summary and `canvas_todo.telegram_client`
   to send it to you.

This is deliberately not automated — see the design spec's "Amendment 2"
for why (Georgia Tech blocks the kind of unattended automated access this
would otherwise require).

## Known limitations (accepted for this POC)

- Announcement → to-do extraction is LLM-based and not perfectly precise;
  occasional missed/duplicate items are expected (see design spec).
- No EdStem lecture-watch-progress integration yet (phase 2, see design spec's
  Future Enhancements section).
- Single user, `localhost`-only web app, no auth, no deployment.
- No automatic/scheduled checks — you must ask Claude to check Canvas each
  time; nothing runs in the background. This is a deliberate tradeoff, not
  a bug (see design spec Amendment 2).
