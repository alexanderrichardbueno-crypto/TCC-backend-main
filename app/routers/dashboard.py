from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.dependencies import DbSession, require_roles
from app.models import AuditEvent, User, WeatherAlert
from app.schemas import utc_iso
from app.station_models import StationObservation, WeatherStation

router = APIRouter(tags=["painel"])


@router.get("/dashboard")
def dashboard(db: DbSession, user: Annotated[User, Depends(require_roles("METEOROLOGIST"))]):
    now = datetime.now(UTC)
    active = (
        WeatherAlert.issued_at <= now,
        WeatherAlert.valid_until > now,
        WeatherAlert.validation_status == "ACTIVE",
        WeatherAlert.closed_at.is_(None),
        WeatherAlert.deleted_at.is_(None),
    )
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(8))
    latest = db.scalar(select(func.max(StationObservation.observed_at)))
    return {
        "active_alerts": db.scalar(select(func.count()).select_from(WeatherAlert).where(*active)),
        "official_alerts": db.scalar(
            select(func.count())
            .select_from(WeatherAlert)
            .where(*active, WeatherAlert.origin == "INMET")
        ),
        "stations": db.scalar(select(func.count()).select_from(WeatherStation)),
        "latest_observation_at": utc_iso(latest) if latest else None,
        "activity": [{"action": e.action, "created_at": utc_iso(e.created_at)} for e in events],
        "generated_at": utc_iso(now),
    }
