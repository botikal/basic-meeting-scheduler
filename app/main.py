"""FastAPI application: booking API + minimal server-rendered pages."""

import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .availability import available_slots, is_slot_available, slot_length
from .config import Settings, get_settings
from .database import get_session, init_db
from .emailer import send_booking_cancellation, send_booking_confirmation
from .models import Booking, BookingCreate, BookingRead, BookingReschedule, BookingStatus
from .timeutils import to_utc_naive

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

UTC = ZoneInfo("UTC")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Meeting Scheduler", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

_basic_auth = HTTPBasic()


# --- shared helpers ----------------------------------------------------------


def require_admin(
    credentials: HTTPBasicCredentials = Depends(_basic_auth),
    settings: Settings = Depends(get_settings),
) -> str:
    user_ok = secrets.compare_digest(credentials.username, settings.admin_username)
    pass_ok = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def _manage_url(settings: Settings, token: str) -> str:
    return f"{settings.base_url.rstrip('/')}/b/{token}"


def _to_read(booking: Booking, settings: Settings) -> BookingRead:
    return BookingRead(
        client_name=booking.client_name,
        client_email=booking.client_email,
        start_at=booking.start_at,
        end_at=booking.end_at,
        note=booking.note,
        status=booking.status,
        manage_token=booking.manage_token,
        manage_url=_manage_url(settings, booking.manage_token),
    )


def _get_booking_or_404(session: Session, token: str) -> Booking:
    booking = session.exec(select(Booking).where(Booking.manage_token == token)).first()
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def _create_booking(session: Session, data: BookingCreate, settings: Settings) -> Booking:
    start_at = to_utc_naive(data.start_at)
    if not is_slot_available(session, start_at, settings):
        raise HTTPException(status_code=409, detail="That time is no longer available.")
    booking = Booking(
        client_name=data.client_name.strip(),
        client_email=str(data.client_email),
        start_at=start_at,
        end_at=start_at + slot_length(settings),
        note=data.note.strip(),
    )
    session.add(booking)
    session.commit()
    session.refresh(booking)
    send_booking_confirmation(booking, settings)
    return booking


def _reschedule_booking(
    session: Session, booking: Booking, new_start: datetime, settings: Settings
) -> Booking:
    if booking.status is not BookingStatus.confirmed:
        raise HTTPException(status_code=409, detail="Only confirmed bookings can be rescheduled.")
    new_start = to_utc_naive(new_start)
    if not is_slot_available(session, new_start, settings, ignore_start=booking.start_at):
        raise HTTPException(status_code=409, detail="That time is no longer available.")
    booking.start_at = new_start
    booking.end_at = new_start + slot_length(settings)
    session.add(booking)
    session.commit()
    session.refresh(booking)
    send_booking_confirmation(booking, settings)
    return booking


def _cancel_booking(session: Session, booking: Booking, settings: Settings) -> Booking:
    if booking.status is BookingStatus.cancelled:
        return booking
    booking.status = BookingStatus.cancelled
    session.add(booking)
    session.commit()
    session.refresh(booking)
    send_booking_cancellation(booking, settings)
    return booking


def _fmt_slot(dt: datetime, settings: Settings) -> str:
    local = dt.replace(tzinfo=UTC).astimezone(ZoneInfo(settings.timezone))
    return local.strftime("%a %d %b %Y, %H:%M")


def _slot_choices(
    session: Session, day: date, settings: Settings, *, ignore_start: datetime | None = None
) -> list[dict[str, str]]:
    slots = available_slots(session, day, settings, ignore_start=ignore_start)
    return [{"value": s.isoformat(), "label": _fmt_slot(s, settings)} for s in slots]


# --- JSON API --------------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/slots")
def api_slots(
    day: date,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    slots = available_slots(session, day, settings)
    return {"day": day.isoformat(), "slots": [s.isoformat() for s in slots]}


@app.post("/api/bookings", response_model=BookingRead, status_code=201)
def api_create_booking(
    data: BookingCreate,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BookingRead:
    booking = _create_booking(session, data, settings)
    return _to_read(booking, settings)


@app.get("/api/bookings/{token}", response_model=BookingRead)
def api_get_booking(
    token: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BookingRead:
    return _to_read(_get_booking_or_404(session, token), settings)


@app.post("/api/bookings/{token}/reschedule", response_model=BookingRead)
def api_reschedule_booking(
    token: str,
    data: BookingReschedule,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BookingRead:
    booking = _get_booking_or_404(session, token)
    booking = _reschedule_booking(session, booking, data.start_at, settings)
    return _to_read(booking, settings)


@app.post("/api/bookings/{token}/cancel", response_model=BookingRead)
def api_cancel_booking(
    token: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> BookingRead:
    booking = _get_booking_or_404(session, token)
    booking = _cancel_booking(session, booking, settings)
    return _to_read(booking, settings)


@app.get("/api/admin/bookings")
def api_admin_bookings(
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[BookingRead]:
    bookings = session.exec(select(Booking).order_by(Booking.start_at)).all()
    return [_to_read(b, settings) for b in bookings]


# --- Server-rendered pages ------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def page_index(
    request: Request,
    day: date | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    choices = _slot_choices(session, day, settings) if day else []
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "settings": settings,
            "day": day.isoformat() if day else "",
            "slots": choices,
        },
    )


@app.post("/book")
def page_book(
    request: Request,
    client_name: str = Form(...),
    client_email: str = Form(...),
    start_at: datetime = Form(...),
    note: str = Form(""),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    data = BookingCreate(
        client_name=client_name, client_email=client_email, start_at=start_at, note=note
    )
    booking = _create_booking(session, data, settings)
    return RedirectResponse(url=f"/b/{booking.manage_token}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/b/{token}", response_class=HTMLResponse)
def page_manage(
    request: Request,
    token: str,
    day: date | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    booking = _get_booking_or_404(session, token)
    choices = _slot_choices(session, day, settings, ignore_start=booking.start_at) if day else []
    return templates.TemplateResponse(
        request,
        "manage.html",
        {
            "settings": settings,
            "booking": booking,
            "when": _fmt_slot(booking.start_at, settings),
            "day": day.isoformat() if day else "",
            "slots": choices,
        },
    )


@app.post("/b/{token}/reschedule")
def page_reschedule(
    token: str,
    start_at: datetime = Form(...),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    booking = _get_booking_or_404(session, token)
    _reschedule_booking(session, booking, start_at, settings)
    return RedirectResponse(url=f"/b/{token}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/b/{token}/cancel")
def page_cancel(
    token: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    booking = _get_booking_or_404(session, token)
    _cancel_booking(session, booking, settings)
    return RedirectResponse(url=f"/b/{token}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin", response_class=HTMLResponse)
def page_admin(
    request: Request,
    _: str = Depends(require_admin),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    bookings = session.exec(select(Booking).order_by(Booking.start_at)).all()
    rows = [
        {
            "booking": b,
            "when": _fmt_slot(b.start_at, settings),
            "manage_url": _manage_url(settings, b.manage_token),
        }
        for b in bookings
    ]
    return templates.TemplateResponse(request, "admin.html", {"settings": settings, "rows": rows})
