# basic-meeting-scheduler

A simple web app that lets outside clients book meetings with your team, in the
style of Calendly. Clients pick an open slot and enter their name + email - no
account required. Each booking gets a private, unguessable link for rescheduling
or cancelling. Staff manage everything through the Django admin.

## Stack

- **Django 6** - web framework, ORM, templates, and the staff admin
- **Django REST Framework** - the JSON API (`/api/...`)
- **SQLite** - database (a single `db.sqlite3` file)
- Config via environment / `.env` (see `.env.example`), read with `django-environ`

## Timezones

Business hours are set in `BUSINESS_TIMEZONE` (default `Asia/Seoul`, 09:00-18:00),
and clients see every time in `DISPLAY_TIMEZONE` (default `UTC`). So a Korean
09:00-18:00 workday shows to a client as 00:00-09:00 UTC. The staff calendar shows
times in `BUSINESS_TIMEZONE`.

`LUNCH_START_HOUR`/`LUNCH_END_HOUR` (also in `BUSINESS_TIMEZONE`) carve a daily
break with no bookable slots out of business hours - equal values (the
default) mean no break.

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
# source .venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements-dev.txt      # runtime + test/lint tools
# pip install -r requirements.txt        # runtime only

# 3. Configure
copy .env.example .env          # then edit .env

# 4. Set up the database and a staff login
python manage.py migrate
python manage.py createsuperuser
```

## Run

```bash
python manage.py runserver
```

| URL | What it is |
|-----|------------|
| http://localhost:8000/ | Landing page - pick a service (Headhunting / Japan services / Wanted Global) |
| http://localhost:8000/schedule/ | Client booking calendar |
| http://localhost:8000/b/&lt;token&gt;/ | Manage a booking (link is in the confirmation email) |
| http://localhost:8000/admin/ | Staff view of all bookings (login required) |
| http://localhost:8000/api/ | Browsable JSON API |

With no `EMAIL_HOST` set, confirmation emails are printed to the console.

## Tests

```bash
pytest          # run the suite
ruff check .    # lint
ruff format .   # auto-format
```

## Project layout

```
config/            Django project (settings, root urls, wsgi/asgi)
scheduling/        the app
  models.py        Booking
  rules.py         typed access to the booking rules in settings.SCHEDULER
  availability.py  slot generation + availability / capacity checks
  calendarview.py  month-grid builder for the calendar picker
  services.py      create / reschedule / cancel (shared by pages and API)
  emails.py        confirmation + cancellation emails
  forms.py         the client-details form
  views.py         server-rendered pages (htmx-enhanced)
  api.py           DRF JSON endpoints
  serializers.py   DRF serializers
  admin.py         staff admin
  googlecal.py     Google Calendar / Meet integration (optional)
  management/commands/google_oauth_setup.py   one-time OAuth authorization
  templates/scheduling/
  templates/scheduling/landing.html   the service-picker cover page
tests/             pytest suite (api, pages, staff, timezones, googlecal)
```

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/slots/?day=YYYY-MM-DD[&slot_count=N]` | Open slots on a day (that can fit N back-to-back slots) |
| POST | `/api/bookings/` | Create a booking (`slot_count` 1-`MAX_CONSECUTIVE_SLOTS`) |
| GET | `/api/bookings/{token}/` | Look up a booking |
| POST | `/api/bookings/{token}/reschedule/` | Move a booking |
| POST | `/api/bookings/{token}/cancel/` | Cancel a booking |

## Meeting length

Every meeting is `SLOT_MINUTES` long (default 30). Raising `MAX_CONSECUTIVE_SLOTS`
above 1 lets a client book several back-to-back slots as one meeting - a
"Meeting length" choice then appears on the booking form, offering a longer
option only when the following slots are free. `Booking.slot_count` records how
many slots a booking holds; `end_at` is derived from it.

## Service picker & per-service calendars

Before reaching the booking calendar, a client picks one of three services on
the landing page (`Booking.Service`: `headhunting`, `japan`, `global`). The
choice is carried through the calendar as a `?service=` query param / hidden
form field and saved on the booking (`Booking.service`) - it's purely
informational for Headhunting and Wanted Global (they share one calendar),
while Japan can be pointed at entirely different calendars, both explained
below.

**Reading (availability):** a slot busy on our own bookings is always
excluded; if Google Calendar is configured, two more checks layer on top:

- **`GOOGLE_CALENDAR_ID`'s own events count as busy, for every booking**
  (not just ones made through this app) - so a client can't book over
  something already on that calendar.
- **Japan services additionally check `GOOGLE_CALENDAR_ID_JAPAN`** (if set) -
  its free/busy is checked only for Japan bookings, on top of the main
  calendar check above. Leave it blank to skip; this calendar only needs to
  be *shared as readable* with whichever account `GOOGLE_TOKEN_FILE` is
  authorized as - it's never written to.

A slot busy on any calendar that applies to it is excluded (`availability.
extra_busy_for`, `googlecal.busy_intervals`/`main_calendar_id`/
`extra_calendar_for`). If Google Calendar isn't configured at all, this is
skipped entirely and only our own bookings are checked, same as before.

**Writing (where a confirmed booking's event actually gets created):**
defaults to `GOOGLE_CALENDAR_ID`, but can be split off with two more optional
settings - useful when the calendar you want read for conflicts (e.g. a
real staff member's own calendar) shouldn't also collect client invites:

- `GOOGLE_CALENDAR_WRITE_ID` - if set, headhunting/global bookings are
  created here instead of `GOOGLE_CALENDAR_ID`.
- `GOOGLE_CALENDAR_ID_JAPAN_WRITE` - if set, Japan bookings are created here
  instead. Falls back to `GOOGLE_CALENDAR_WRITE_ID`/`GOOGLE_CALENDAR_ID` if
  unset, matching the old one-calendar-for-everything behavior.

Whichever calendar ends up as a write target needs to be shared with
**"Make changes to events"** access, same as the main calendar in the Google
Meet setup below (`googlecal.write_calendar_for`).

## Google Meet

Optional. When configured, a confirmed booking gets a real Google Calendar
event with a Meet link, shown in the confirmation email, the manage page, and
the staff calendar. Leave it unconfigured and everything else works the same,
minus the Meet link.

Auth is OAuth2 as the calendar owner - not a service account - because a
service account needs the calendar explicitly *shared* with it, which some
Workspace organizations block for external (non-domain) accounts regardless of
which calendar it is. OAuth sidesteps that: the owner authorizes the app
directly, the same way they'd authorize any third-party app.

Setup:
1. Google Cloud Console -> a project -> enable the **Google Calendar API**
2. **APIs & Services -> OAuth consent screen**: set it up (Internal if your
   account is on Workspace and that's offered, External + add yourself as a
   test user otherwise), with scope `.../auth/calendar.events`
3. **APIs & Services -> Credentials -> Create Credentials -> OAuth client ID**,
   application type **Desktop app** -> download the JSON
4. `python manage.py google_oauth_setup path/to/that-file.json` - opens a
   browser, sign in and approve, and it writes `token.json`
5. In `.env`, set `GOOGLE_TOKEN_FILE=token.json` and `GOOGLE_CALENDAR_ID=...`
   (your email, or a secondary calendar's ID from its "Integrate calendar"
   settings - either works, since it's your own calendar now)
6. Optionally, set `GOOGLE_CALENDAR_ID_JAPAN=...` to a calendar shared as
   readable with that same account, and/or `GOOGLE_CALENDAR_WRITE_ID=...` /
   `GOOGLE_CALENDAR_ID_JAPAN_WRITE=...` to calendars shared with **"Make
   changes to events"** access - see "Service picker & per-service calendars"
   above

It also means the client can be added as a real calendar **attendee**
(`create_event` in `googlecal.py`, with `sendUpdates="all"`) - a plain service
account (no Workspace domain-wide delegation) is blocked from inviting
attendees at all, another reason OAuth-as-yourself is the simpler path here.
So the client gets both our own confirmation email *and* a real Google
Calendar invite with the Meet link attached; rescheduling and cancelling
notify them the same way, through Google.

## Notes & limitations (v1)

- Double-booking: the availability check and the insert run inside one
  `transaction.atomic()` block, and a partial unique index
  (`unique_confirmed_start`) hard-guarantees no two confirmed bookings share a
  start time. On SQLite the transaction's global write lock also serialises the
  multi-slot overlap check; on Postgres you'd add `select_for_update()`.
- Availability rules are global (one set of business hours). No per-person
  calendars or holiday handling yet.
- No cancel/reschedule cutoff - a client can change a booking that starts in a
  minute.
- No Outlook sync.
