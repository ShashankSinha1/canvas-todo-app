# Canvas Weekly To-Do & Reminder App — Design

**Status:** Approved (POC scope)
**Date:** 2026-09-14
**Owner:** shashank.wmr@gmail.com

## Purpose

A personal Canvas assistant that: (1) shows a weekly view of everything due — graded assignments and ungraded lecture/reading catch-up items inferred from Canvas announcements; (2) sends Telegram reminders proactively so the user doesn't have to remember to check; (3) automatically checks off graded assignments the moment they're submitted on Canvas, so manual bookkeeping is limited to the items Canvas genuinely cannot verify on its own.

This is an explicit POC for a single user (shashank.wmr@gmail.com). Deployment, multi-user support, and hosting hardening are out of scope for this iteration but the design avoids choices that would make them harder later.

## Non-Goals (this iteration)

- EdStem lecture-watch-progress integration (see Future Enhancements) — deferred to phase 2.
- Multi-device sync, user accounts, authentication on the web app.
- Production hosting/deployment (runs locally only).
- Perfect precision on announcement-derived to-do extraction — occasional missed or duplicate items are an accepted tradeoff (see "Canvas Ingestion & Announcement Parsing").

## Architecture

Three components sharing one local SQLite database (`canvas_todo.db`):

1. **Canvas ingestion module** (Python) — calls the Canvas REST API directly (same underlying API canvas-mcp wraps) to pull active courses, assignments + submission status, and the last 7 days of announcements.
2. **Scheduled agent** — a task registered via this platform's scheduled-task feature (`~/.claude/scheduled-tasks/`), running on a daily cron (while the Claude Code app is open). Each run: ingests Canvas data, reasons over announcement text to extract ungraded to-do items, upserts everything into SQLite, and sends Telegram messages (daily digest + conditional urgent alert).
3. **Local web app** — a single-page Flask app (`localhost` only) reading/writing the same SQLite file, showing the current week's items with checkboxes. Graded items are read-only/auto-checked; ungraded items have a live toggle.

Rationale for one shared SQLite file: the scheduled agent and the web app must agree on reminder state and manual-checkoff state, or the user gets repeat texts for things already marked done.

**Known constraint:** scheduled tasks on this platform only fire while the Claude Code app is open; if closed at run time, the run fires on next launch (may be late that day). Acceptable for a personal POC.

## Data Model

**`items`** — one row per to-do item for the current week:

| column | type | notes |
|---|---|---|
| `id` | integer PK | |
| `course_name` | text | |
| `title` | text | |
| `type` | enum(`graded`, `ungraded`) | |
| `due_at` | datetime, nullable | null allowed for ungraded items |
| `source` | enum(`canvas_assignment`, `announcement`) | |
| `status` | enum(`pending`, `done`, `overdue`) | |
| `auto_tracked` | bool | true = graded (status derived from Canvas, not user-editable) |
| `last_reminded_at` | datetime, nullable | drives "new vs already-seen" flagging in the digest |

**`weekly_runs`** — one row per scheduled-agent run: `id`, `run_at`, `week_of`, `raw_announcement_snapshot` (JSON blob of what was read, for debugging LLM extraction).

Upsert key: Canvas assignment ID for graded items; fuzzy match (course + normalized title similarity, scoped to current week) for announcement-derived items, to avoid re-creating (and re-texting about) the same ungraded item on every run.

Graded item `status` is fully re-derived from Canvas submission data on every run (no manual override). Ungraded item `status` changes only via the web app checkbox; the scheduled agent only adds new ones and reads current status — it never overwrites a user's manual "done."

## Canvas Ingestion & Announcement Parsing

Each run:

1. `GET /courses` (active enrollments).
2. Per course: `GET /assignments?include[]=submission` → upsert `items` rows with `type=graded`, `source=canvas_assignment`, `status` derived from `submission.submitted_at` (submitted → `done`; unsubmitted + past due → `overdue`; unsubmitted + upcoming → `pending`).
3. Per course: `GET /announcements` (last 7 days) → the agent reads each announcement body and extracts zero or more concrete action items with a best-guess implied due date, upserting as `type=ungraded`, `source=announcement`, `status=pending`, `auto_tracked=false`.
4. Fuzzy-dedup against existing pending/done ungraded items for the same course/week before creating a new row.

This step is inherently probabilistic. Precision is not a target for the POC — the `raw_announcement_snapshot` field lets the user audit why an item was created if it looks wrong, and incorrect items are trivially deletable/toggleable in the web app.

## Reminder Logic & Telegram Delivery

- **Daily digest** (always sent, ~7:30am local, configurable): grouped by course into "Due this week," "Overdue," "Not yet checked off" — with newly-added or newly-urgent items visually flagged (e.g. 🆕/⚠️) so repeat-day items don't clutter attention.
- **Urgent alert** (conditional): sent as a separate message only when a graded item is due within 24 hours and still unsubmitted per Canvas.
- `last_reminded_at` is updated whenever an item is mentioned, to drive the "new vs seen" flagging — items are never silently dropped from the digest, just de-emphasized once already seen.
- Delivery: plain HTTPS POST to the Telegram Bot API (no SDK dependency). Bot created via @BotFather; bot token + chat ID stored in local `.env` (gitignored).

## Web App

- Single Flask app, `localhost` only, no auth (POC scope).
- `GET /` — renders current week's items grouped by course, sorted by due date. Graded items: greyed-out, pre-checked, non-interactive checkbox. Ungraded items: live checkbox.
- `POST /items/<id>/toggle` — flips `pending`/`done` for an ungraded item only; writes directly to the shared SQLite file. Graded items reject toggle attempts.
- No frontend framework/build step — vanilla HTML/JS `fetch` on checkbox click. Run via `flask run`; no production WSGI server for this iteration.

## Setup & Credentials Required

1. Canvas API token (Canvas → Account → Settings → New Access Token) + Canvas instance base URL.
2. Telegram bot token (via @BotFather) + chat ID (captured once bot exists).
3. canvas-mcp installed and configured locally for ad hoc/on-demand queries via Claude ("what's due this week") — separate from the scheduled agent's direct-REST-API ingestion path, which doesn't route through the MCP layer.

All secrets in a local `.env`, gitignored, never hardcoded.

## Error Handling & Edge Cases

- **Canvas API failure**: run logs the error, does not update `items` for that run, and still sends a Telegram message noting Canvas was unreachable rather than going silent or sending stale data as if current.
- **LLM misreads an announcement**: worst case is a spurious/missed to-do item, recoverable via the web app; `raw_announcement_snapshot` provides an audit trail.
- **Claude Code app closed at scheduled run time**: run fires on next app launch instead (platform behavior, not fixable at this layer) — digest may arrive late.
- **Duplicate Telegram sends**: prevented by the `last_reminded_at`-driven upsert logic, not by time-based dedup — a manual re-run of the agent does not double-send.

## Testing Approach

Pragmatic, not exhaustive, given POC/single-user scope:

- Unit tests for ingestion/upsert/dedup logic against saved fixture JSON (anonymized real Canvas payloads) — this is the highest-bug-risk area.
- Integration tests for the Flask toggle endpoint against a temp SQLite file (toggle persists; graded items reject toggle).
- Telegram sending and LLM announcement-parsing are verified manually (external API / non-deterministic reasoning), consistent with the accepted precision tradeoff above. No CI pipeline for this iteration.

## Amendment (2026-09-16): Canvas Auth Pivot — Session Cookie via Persistent Browser Profile

**Problem discovered during implementation:** Georgia Tech (the user's institution) disables student-generated Canvas API access tokens as institutional policy — this is not a bug or a missing setting, it's a deliberate FERPA/security-driven restriction confirmed across multiple peer institutions (GT, UW-Madison, UW, Texas A&M). The original design's assumption of a long-lived `CANVAS_API_TOKEN` (Bearer auth) is not viable for this user.

**Options considered:** (1) request token access via GT's help desk — untried/uncertain turnaround; (2) fall back to token-free public feeds (iCal for due dates, RSS for announcements) — rejected because it loses submission-status data entirely, eliminating auto-checkoff for graded work, the single most-wanted feature; (3) pause the project; (4) authenticate via a real, persistent, cookie-based browser session instead of a token — **chosen**.

**Decision:** Replace Bearer-token auth with session-cookie auth sourced from a **persistent Playwright browser profile**:

- **One-time (and occasional re-run) manual setup**: the user runs a new interactive script (`canvas_todo/canvas_login_setup.py`) that opens a real, visible Chromium window via Playwright. The user logs into Canvas themselves — typing their GT password and completing Duo 2FA directly in that browser window; this script never sees or handles the password. On success, Playwright's persistent profile (cookies, local storage) is saved to disk at a fixed, gitignored path.
- **Daily ingestion**: `canvas_client.py` loads cookies from that persistent profile into a `requests.Session` and calls the same public Canvas REST API endpoints as before — no change to which endpoints are called or how pagination/response parsing works, only how the request is authenticated.
- **Session expiry is expected, not exceptional**: unlike an API token, this session will eventually expire (exact GT-specific duration unknown — dependent on Duo/SSO "remember this device" configuration, which is admin-set and undocumented for GT). When ingestion detects an expired/invalid session (HTTP 401, or a redirect to a login/SSO page instead of a JSON API response), it must raise a distinguishable error so the scheduled agent can send a specific "please log in again" Telegram alert rather than a generic failure message — the user should never have to notice via silence that something broke.

**Accepted risks, explicitly surfaced to and approved by the user:**
- A live session cookie is at least as sensitive as a password/token — arguably more directly so, since it *is* an active authenticated session. It is stored only in the local, gitignored Playwright profile directory, never committed, never logged.
- This access pattern (automated use of a personal browser session against Canvas) is not an officially sanctioned integration path the way a Developer Key/OAuth flow would be — it sits in a gray area relative to Canvas's terms, mitigated by being read-only, single-user, and never sharing/redistributing the session.
- "Persistent" is relative: this is expected to survive materially longer than a single manually-copied cookie snapshot (which could die same-day), but will still eventually require the user to re-run the login script — cadence unknown, could be days to weeks.

**New dependency:** Playwright (plus a downloaded Chromium binary via `playwright install chromium`) — a materially heavier addition than the project's prior pure-`requests` stack. Accepted as a necessary cost for this user's institutional constraint.

## Future Enhancements (Explicitly Deferred)

- **EdStem lecture-progress integration**: user wants percent-watched-per-lecture, not just Ed's binary checkmark. Deferred because Ed has no documented public API for this — would require inspecting Ed's internal (undocumented) endpoints via an authenticated session to confirm percentage data is even exposed (vs. only a binary completion flag), before committing to a scraping approach. Schema extension sketch: a `lecture_progress` table (`lecture_id`, `course_name`, `percent_watched`, `last_synced_at`) joined to `items` by lecture reference. Not built in this iteration.
- Deploying the web app off-Mac; multi-device/multi-user support — noted as a possible future direction but not designed for here.
