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
| http://localhost:8000/ | Client booking page |
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
  templates/scheduling/
tests/             pytest suite (test_api.py, test_pages.py)
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

A booking can span 1-`MAX_CONSECUTIVE_SLOTS` back-to-back slots (default 2, i.e.
30 or 60 minutes). The client picks a start time, then a length - "1 hour" only
appears when the following slot is also free. `Booking.slot_count` records how
many slots a booking holds; `end_at` is derived from it.

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
- No Google Calendar / Outlook sync yet.
