# PRD-45 — The notice inbox: grouped by source, read in bulk, muted per source

**Status:** built 2026-11-23 (iOS + backend, one PR). Screen page deferred.

## Why

Jimmy, 2026-11-23, about the Actions tab: "we have too many notices and they
trace back to screen and strategies we set up before". He wanted users to be
able to (a) silence, read and avoid messages as they need, and (b) trace each
one back to the strategy or screen that sent it and make that choice there.
"The end goal is creating a simple, clear notice system that users can
identify important information quickly and take actions", built end to end:
data → backend → UI.

## What was there

Five jobs write notices into `notification_banner_entries`:

| Job | What happened | Kind | Level |
|---|---|---|---|
| `signal_cron` | a strategy's signal changed | strategy | changed |
| `saved_screen_cron` | a new name entered a screen | screen | fyi |
| `ticker_alert_cron` | a followed stock passes or fails a screen | stock_alert | fyi |
| `daily_position_jobs` | a stop or target was hit | position | act |
| `intraday_jobs` | the same, from the intraday feed | position | act |

Each row was a title, a sentence and `strategy_slug` (always a
`saved_strategies.id`; screens are rows whose `strategy_json.kind` is
"screen"). The app showed the newest 10 in one list with "Mark as read" one at
a time. Notices could not be muted at all; only emails had mute switches.

## Decisions (Jimmy, 2026-11-23)

- **Mute covers email too.** A muted strategy or screen sends no notices to the
  tab and no signal-change emails.
- **Screen page later.** A screen's notices get their own page with read and
  mute; an "Open screen" page is a separate step.
- Exits (stops and targets on held positions) are never muted. *(My proposal,
  accepted with the plan.)*

## As built

**Data.** `notification_banner_entries` gains `source_kind`, `symbol`, `level`
(nullable, isolated `ADD COLUMN` per dialect). New table `notice_mutes
(user_id, source_id)`. Old rows are classified on read
(`notice_inbox.classify`), not rewritten: a "⚡" title came from a strategy or
screen; "defines as an exit" in the body is a position exit.

**Backend** (`app/services/notice_inbox.py`, routes in `notifications.py`):

- `GET /api/me/notices` — unread notices grouped by source, ranked by the most
  important unread notice then the newest; exits left out (they are listed as
  decisions above); muted sources listed.
- `GET /api/me/notices/sources/{id}` — one source's history, read or not.
- `POST /api/me/notices/read` — by ids or by source.
- `PUT|DELETE /api/me/notices/mutes/{id}` — mute marks the source's unread
  notices read (exits excepted); later notices arrive read.
- Every writer passes `source_kind` / `level` / `symbol`.
  `dispatch_in_app_banner` and `dispatch_signal_change_email` check the mute.
- `GET /api/me/notifications/pending` (the website's banner) is unchanged.

**App.** The Actions tab's flat "Notices" list becomes **Updates**: one row
per strategy or screen with its name, the newest line, "N new · level", and
time; swipe to Read or Mute; a **Muted** row lists silenced sources with
Unmute. A source's page has Mark all read, Mute/Unmute, its history, and
**Open strategy** for strategies. The strategy page says "Muted: no updates or
emails" instead of "Email alerts are on" when muted.

## Not done / next

- An app page for a saved screen ("Open screen").
- The daily digest email still lists every strategy, muted or not.
- The tab badge still counts exits only.
