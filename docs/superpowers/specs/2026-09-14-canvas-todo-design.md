# Canvas Weekly To-Do & Reminder App — Design

**Status:** Approved (POC scope)
**Date:** 2026-09-14
**Owner:** shashank.wmr@gmail.com

## Purpose

*(See "Amendment 2" below — the automation model changed from proactive/scheduled to manually-triggered. This section describes the original intent; treat Amendment 2 as authoritative for what's actually built.)*

A personal Canvas assistant that: (1) shows a weekly view of everything due — graded assignments and ungraded lecture/reading catch-up items inferred from Canvas announcements; (2) sends Telegram reminders proactively so the user doesn't have to remember to check; (3) automatically checks off graded assignments the moment they're submitted on Canvas, so manual bookkeeping is limited to the items Canvas genuinely cannot verify on its own.

This is an explicit POC for a single user (shashank.wmr@gmail.com). Deployment, multi-user support, and hosting hardening are out of scope for this iteration but the design avoids choices that would make them harder later.

## Non-Goals (this iteration)

- EdStem lecture-watch-progress integration (see Future Enhancements) — deferred to phase 2.
- Multi-device sync, user accounts, authentication on the web app.
- Production hosting/deployment (runs locally only).
- Perfect precision on announcement-derived to-do extraction — occasional missed or duplicate items are an accepted tradeoff (see "Canvas Ingestion & Announcement Parsing").

## Architecture

**⚠️ Items 1-2 below are superseded by "Amendment 2" (end of document) — the CURRENT architecture has no REST ingestion module and no scheduled agent; ingestion happens only when the user asks Claude to check Canvas in a live conversation, via the Chrome extension. Item 3 (web app) is still accurate. Read Amendment 2 before implementing anything from this section.**

Three components sharing one local SQLite database (`canvas_todo.db`):

1. **Canvas ingestion module** (Python) — calls the Canvas REST API directly (same underlying API canvas-mcp wraps) to pull active courses, assignments + submission status, and the last 7 days of announcements.
2. **Scheduled agent** — a task registered via this platform's scheduled-task feature (`~/.claude/scheduled-tasks/`), running on a daily cron (while the Claude Code app is open). Each run: ingests Canvas data, reasons over announcement text to extract ungraded to-do items, upserts everything into SQLite, and sends Telegram messages (daily digest + conditional urgent alert).
3. **Local web app** — a single-page Flask app (`localhost` only) reading/writing the same SQLite file, showing the current week's items with checkboxes. Graded items are read-only/auto-checked; ungraded items have a live toggle.

Rationale for one shared SQLite file: the scheduled agent and the web app must agree on reminder state and manual-checkoff state, or the user gets repeat texts for things already marked done.

**Known constraint:** scheduled tasks on this platform only fire while the Claude Code app is open; if closed at run time, the run fires on next launch (may be late that day). Acceptable for a personal POC. *(Moot under Amendment 2 — there is no scheduled task.)*

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

**⚠️ Superseded by Amendment 2 — there is no `GET /courses`/`GET /assignments`/`GET /announcements` REST access. Claude reads this data live via the Chrome extension instead, then calls `manual_ingest.py`/`upsert_ungraded.py`. The upsert/dedup mechanics described below (fuzzy-dedup, `raw_announcement_snapshot` audit trail) are still accurate — only the fetch mechanism changed.**

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

**⚠️ SUPERSEDED — this section describes Amendment 1 (token-free feeds), which was itself abandoned before implementation. Do not follow these steps.** The actually-implemented, current requirements are in **Amendment 2** below: no Canvas credentials of any kind (no token, no calendar feed URL, no `courses.json`) — only a Telegram bot token/chat ID and the Chrome extension being connected. This section is kept only as a historical record of an intermediate design that was never built.

<details>
<summary>Historical: Amendment 1's setup steps (never implemented)</summary>

1. **Canvas Calendar Feed URL** (Account → Settings → "Calendar Feed") — one-time copy into `.env`.
2. **Per-course Announcements Feed URLs** — one per active course, found on each course's Announcements page; collected into a gitignored `courses.json` config file. Must be refreshed each semester when enrolled courses change.
3. Telegram bot token (via @BotFather) + chat ID (captured once bot exists).
4. canvas-mcp installed and configured locally for ad hoc/on-demand queries via Claude ("what's due this week").

All secrets/feed URLs in local, gitignored files (`.env`, `courses.json`), never hardcoded, never committed.

</details>

## Error Handling & Edge Cases

**⚠️ The first and third bullets below are stale (reference feed fetching and a scheduled run, neither of which exist under Amendment 2). The second and fourth bullets are still accurate.**

- ~~**Canvas feed fetch failure**...~~ *(N/A under Amendment 2 — there's no feed to fetch. If Claude can't read a Canvas page via the Chrome extension, it says so directly in the conversation.)*
- **LLM misreads an announcement**: worst case is a spurious/missed to-do item, recoverable via the web app; `raw_announcement_snapshot` provides an audit trail. *(Still accurate.)*
- ~~**Claude Code app closed at scheduled run time**...~~ *(N/A under Amendment 2 — there's no scheduled run; ingestion only happens when the user is actively in a conversation.)*
- **Duplicate Telegram sends**: prevented by the `last_reminded_at`-driven upsert logic, not by time-based dedup — re-running the pipeline in the same conversation does not double-send. *(Still accurate.)*

## Testing Approach

Pragmatic, not exhaustive, given POC/single-user scope:

- Unit tests for ingestion/upsert/dedup logic against saved fixture JSON (anonymized real Canvas payloads) — this is the highest-bug-risk area.
- Integration tests for the Flask toggle endpoint against a temp SQLite file (toggle persists; graded items reject toggle).
- Telegram sending and LLM announcement-parsing are verified manually (external API / non-deterministic reasoning), consistent with the accepted precision tradeoff above. No CI pipeline for this iteration.

## Amendment (2026-09-16): Canvas Auth Pivot — Token-Free Public Feeds

**Problem discovered during implementation:** Georgia Tech (the user's institution) disables student-generated Canvas API access tokens as institutional policy — this is not a bug or a missing setting, it's a deliberate FERPA/security-driven restriction confirmed across multiple peer institutions (GT, UW-Madison, UW, Texas A&M). The original design's assumption of a long-lived `CANVAS_API_TOKEN` (Bearer auth) is not viable for this user.

**Options considered:** (1) request token access via GT's help desk — untried/uncertain turnaround, not pursued; (2) fall back to token-free public feeds (iCal for due dates, Atom for announcements) — **chosen**; (3) pause the project; (4) authenticate via a persistent, cookie-based browser session harvested from an interactive login — **attempted, then abandoned**. Option 4 got as far as a drafted implementation plan before the platform's own safety review flagged it as circumventing GT's deliberate institutional access control (harvesting and persisting a live authenticated session specifically to enable the unattended automated access GT chose to block via tokens) rather than a personal risk tradeoff the user could authorize alone. That implementation was never committed; this amendment supersedes it.

**Decision:** Replace all Canvas REST API access (courses, assignments+submissions, announcements) with two **officially-documented, publicly-supported Canvas feed features**, neither of which requires a token, login, or session of any kind — the feed URL itself, once obtained, is a Canvas-issued, revocable, scoped credential (analogous to a signed link), not something being reverse-engineered or bypassed:

- **Calendar Feed** (iCal/ICS) — a per-user URL of the form `https://<instance>/feeds/calendars/user_<token>.ics`, found in Canvas under Account → Settings → "Calendar Feed." Aggregates due dates for all courses. Canvas explicitly designs this for external calendar-app syndication; a public open-source tool (`canvas-planner`) already uses this exact pattern for the same purpose (a token-free Canvas due-date tracker).
- **Per-course Announcements Feed** (Atom) — a URL of the form `https://<instance>/feeds/announcements/course_<id>_<token>.atom`, found via an RSS icon/link on each course's Announcements page. One URL per active course. Also independently validated by an existing open-source tool (`canvas-announcements-to-discord-template`) polling exactly these feeds on a schedule.

**What this costs, explicitly accepted by the user:**
- **No submission status, ever** — meaning **no auto-checkoff for graded assignments**. This eliminates one of the app's three original core promises. Graded assignment items now behave exactly like ungraded items: they appear on the list with a real, live checkbox, and the user manually checks them off. The `auto_tracked` distinction in the data model is retired — every item the app tracks is now user-toggled.
- **No course discovery API** — without `/courses`, the app cannot enumerate the user's active courses on its own. The user must manually collect each active course's Announcements feed URL (and course display name) into a small local config file once per semester, when their course list changes. This is a low-frequency manual step, not an ongoing maintenance burden like the abandoned session-refresh approach would have been.
- **Feed URLs are still secrets** — Canvas explicitly warns these act like a password for the underlying content. They're stored only in local, gitignored config (the calendar URL in `.env`, course announcement URLs in a gitignored `courses.json`), never committed, never logged.

**What this preserves:** the daily Telegram digest/urgent-alert cadence, the LLM-driven announcement-to-to-do extraction, the local web app, and the SQLite data layer are all unchanged in spirit — only the ingestion source and the graded-item toggle behavior change. No new heavyweight dependency (no browser automation): parsing these feeds needs only the lightweight `icalendar` and `feedparser` libraries.

## Amendment 2 (2026-09-16): Manually-Triggered Ingestion via Chrome Extension — Supersedes Amendment 1

**This is the current, authoritative architecture.** Amendment 1 (token-free feeds) is superseded before implementation — while researching its announcement-feed piece, the user proposed an alternative: since they have the Claude-in-Chrome browser extension and keep Chrome running, Claude could read Canvas live through an already-authenticated browser tab instead of using feeds or tokens at all.

**Why this is different from the abandoned session-cookie approach (Amendment 1's option 4):** that approach was rejected for building an *unattended, scheduled* mechanism — harvesting and persisting a live session specifically so automated access could happen without the user present, recreating the exact capability GT's token policy blocks. The same concern was raised again here (the user's first proposal was to keep Chrome open and have the daily cron drive it, which has the identical shape) and rejected on the same grounds. **The resolution: ingestion is user-triggered only, never scheduled.** When the user is actively present, asking Claude in a live conversation to check Canvas, browsing their own already-logged-in session is materially the same as any other assistive use of the browser extension — not an automated background-access mechanism. This is the load-bearing distinction; it is why this design is acceptable where the two prior approaches were not.

**What changes from the original design:**

- **No scheduled task at all.** The `~/.claude/scheduled-tasks/` cron registration (originally Task 11) is dropped entirely. There is no daily-7:30am automation.
- **Trigger:** the user, in an active conversation, asks Claude to check Canvas (e.g., "check my Canvas" / "what's due this week"). Claude uses the Chrome extension to navigate the user's courses, assignments, and announcements pages (already authenticated via the user's normal browser login — Claude never handles credentials).
- **Ingestion becomes a persistence step, not a fetch step:** Claude compiles what it reads into structured JSON (courses, assignments with due dates and submission status, recent announcement text) and hands it to a new CLI, `canvas_todo/manual_ingest.py`, which upserts into the same `items`/`weekly_runs` tables via the existing, unchanged `db.py` functions.
- **Submission status is back.** Because Claude is reading the live, authenticated Canvas UI (the same thing a token or session would show), real submission status is available again — **auto-checkoff for graded assignments is restored**, reversing Amendment 1's biggest cost. The `auto_tracked` distinction in the data model stays exactly as originally designed (Data Model section above) — no schema change needed.
- **Announcement-to-to-do extraction is unchanged in spirit** — Claude reads announcement text directly from the page (instead of a fetched feed) and applies the same extraction judgment described in "Canvas Ingestion & Announcement Parsing" above, then calls the existing `upsert_ungraded.py`.
- **Digest and Telegram delivery are unchanged** — after `manual_ingest.py` runs, `digest.py` and `telegram_client.py` run exactly as originally built, so the user still gets a Telegram message and can still check the web app; they just now happen on-demand rather than every morning automatically.
- **`canvas_client.py` and the original `ingest.py` are retired** — no REST API, no feed parsing, no token, no session, no Playwright, no `icalendar`/`feedparser` dependency. This is a net simplification relative to both prior approaches.

**What this costs, explicitly accepted by the user:** the app is no longer proactive. Nothing happens unless the user remembers to ask — which is the exact problem ("I keep falling behind... I don't want to check things off myself") the project originally set out to solve. This is a real, acknowledged regression from the original vision, traded for staying clearly on the right side of GT's access-control policy. The user may partially mitigate this by simply getting in the habit of asking each morning, but the app itself cannot enforce that habit anymore.

**Setup, updated:** no Canvas credentials of any kind are needed — no token, no calendar feed URL, no `courses.json`, no login script. Only the Telegram bot token/chat ID (unchanged) and the Chrome extension being connected. This meaningfully simplifies onboarding versus both prior approaches.

## Future Enhancements (Explicitly Deferred)

- **EdStem lecture-progress integration**: user wants percent-watched-per-lecture, not just Ed's binary checkmark. Deferred because Ed has no documented public API for this — would require inspecting Ed's internal (undocumented) endpoints via an authenticated session to confirm percentage data is even exposed (vs. only a binary completion flag), before committing to a scraping approach. Schema extension sketch: a `lecture_progress` table (`lecture_id`, `course_name`, `percent_watched`, `last_synced_at`) joined to `items` by lecture reference. Not built in this iteration.
- Deploying the web app off-Mac; multi-device/multi-user support — noted as a possible future direction but not designed for here.
