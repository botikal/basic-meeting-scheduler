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
  availability.py  slot generation + availability checks
  services.py      create / reschedule / cancel (shared by pages and API)
  emails.py        confirmation + cancellation emails
  forms.py         booking + reschedule forms
  views.py         server-rendered pages
  api.py           DRF JSON endpoints
  serializers.py   DRF serializers
  admin.py         staff admin
  templates/scheduling/
tests/             pytest suite (test_api.py, test_pages.py)
```

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/slots/?day=YYYY-MM-DD` | Open slots on a day |
| POST | `/api/bookings/` | Create a booking |
| GET | `/api/bookings/{token}/` | Look up a booking |
| POST | `/api/bookings/{token}/reschedule/` | Move a booking |
| POST | `/api/bookings/{token}/cancel/` | Cancel a booking |

## Notes & limitations (v1)

- Double-booking is prevented both by an app-level check and a database
  constraint (`unique_confirmed_start` - a partial unique index on confirmed
  bookings), so even a race loses cleanly with a 409.
- Availability rules are global (one set of business hours). No per-person
  calendars or holiday handling yet.
- No Google Calendar / Outlook sync yet.
- The client-facing pages are deliberately plain - the next step is a real
  calendar-style slot picker.
