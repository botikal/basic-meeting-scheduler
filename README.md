# basic-meeting-scheduler

A simple web app that lets outside clients book meetings with your team, in the
style of Calendly. Clients pick an open slot and enter their name + email - no
account required. Each booking gets a private, unguessable link for rescheduling
or cancelling.

## Stack

- **FastAPI** + **Uvicorn** - web framework and server
- **SQLModel** on **SQLite** - database (a single `scheduler.db` file)
- **Jinja2** - server-rendered pages
- Config via environment / `.env` (see `.env.example`)

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
# source .venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt          # runtime only
pip install -r requirements-dev.txt      # + test/lint tools

# 3. Configure
copy .env.example .env          # then edit .env
```

## Run

```bash
uvicorn app.main:app --reload
```

Then open:

| URL | What it is |
|-----|------------|
| http://localhost:8000/ | Client booking page |
| http://localhost:8000/b/<token> | Manage a booking (from the confirmation email) |
| http://localhost:8000/admin | Staff view of all bookings (HTTP Basic auth) |
| http://localhost:8000/docs | Interactive API documentation |

With no `SMTP_HOST` set, confirmation emails are printed to the console instead
of being sent.

## Tests

```bash
pytest          # run the suite
ruff check .    # lint
ruff format .   # auto-format
```

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/slots?day=YYYY-MM-DD` | Open slots on a day |
| POST | `/api/bookings` | Create a booking |
| GET | `/api/bookings/{token}` | Look up a booking |
| POST | `/api/bookings/{token}/reschedule` | Move a booking |
| POST | `/api/bookings/{token}/cancel` | Cancel a booking |
| GET | `/api/admin/bookings` | All bookings (admin auth) |

## Known limitations (v1)

- Double-booking is prevented by an application-level check, not a database
  constraint - a true simultaneous race could still slip through. Fine for low
  volume; revisit if traffic grows.
- Availability rules are global (one set of business hours). No per-person
  calendars or holiday handling yet.
- No Google Calendar / Outlook sync yet.
- Schema changes require recreating the database (no migrations - add Alembic
  when the schema stabilizes).
