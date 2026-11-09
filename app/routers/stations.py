import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from app.audit import record_audit
from app.dependencies import DbSession, require_roles
from app.integrations.inmet import InmetError
from app.integrations.stations import (
    fetch_json,
    fetch_observations,
    observation,
    parse_import,
    station,
)
from app.models import User
from app.schemas import utc_iso
from app.station_models import StationObservation, WeatherStation
from app.station_sync import save_latest, save_observations, save_station

router = APIRouter(prefix="/stations", tags=["estações INMET"])
Operator = Annotated[User, Depends(require_roles("METEOROLOGIST"))]

# Evita repetir consultas ao INMET a cada abertura de tela, inclusive quando ele falha.
RETRY_SECONDS = 15 * 60
_last_attempt: dict[str, float] = {}


def attempt_allowed(key: str) -> bool:
    now = time.monotonic()
    if now - _last_attempt.get(key, -RETRY_SECONDS) < RETRY_SECONDS:
        return False
    _last_attempt[key] = now
    return True


def load_catalog_if_empty(db) -> None:
    """Fill an empty catalog so visitors do not depend on a meteorologist's first sync."""
    if db.scalar(select(WeatherStation.code).limit(1)) is not None:
        return
    if not attempt_allowed("catalog"):
        return
    try:
        for row in fetch_json("estacoes/T"):
            try:
                db.add(WeatherStation(**station(row)))
            except (ValueError, TypeError, AttributeError):
                continue
        db.commit()
    except (InmetError, IntegrityError):
        db.rollback()


def refresh_latest(db, item: WeatherStation) -> None:
    if not item.geocode or not attempt_allowed(item.code):
        return
    try:
        save_latest(db, item)
        db.commit()
    except (InmetError, IntegrityError):
        db.rollback()


class StationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    state: str | None
    kind: str
    latitude: Decimal | None
    longitude: Decimal | None


class ObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    station_code: str
    observed_at: datetime
    period: str
    source: str
    temperature_c: Decimal | None
    minimum_c: Decimal | None
    maximum_c: Decimal | None
    humidity: Decimal | None
    precipitation_mm: Decimal | None
    wind_ms: Decimal | None
    imported_at: datetime

    @field_serializer("observed_at", "imported_at")
    def serialize_time(self, value):
        return utc_iso(value)


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: date = Field(default_factory=lambda: datetime.now(UTC).date() - timedelta(days=1))
    end: date = Field(default_factory=lambda: datetime.now(UTC).date())

    @model_validator(mode="after")
    def bounded_range(self):
        if not 0 <= (self.end - self.start).days <= 31 or self.end > datetime.now(UTC).date():
            raise ValueError("Selecione até 31 dias, sem datas futuras")
        return self


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["rest-json", "temperature-csv"]
    period: Literal["HOURLY", "DAILY", "MONTHLY"]
    content: str = Field(min_length=1, max_length=2_000_000)


@router.get("", response_model=list[StationOut])
def list_stations(
    db: DbSession,
    state: str | None = Query(None, pattern="^[A-Z]{2}$"),
    search: str = Query("", max_length=120),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    load_catalog_if_empty(db)
    query = select(WeatherStation).order_by(WeatherStation.name, WeatherStation.code)
    if state:
        query = query.where(WeatherStation.state == state)
    if search:
        query = query.where(WeatherStation.name.icontains(search, autoescape=True))
    return list(db.scalars(query.limit(limit).offset(offset)))


@router.post("/sync-catalog")
def sync_catalog(db: DbSession, user: Operator):
    try:
        rows = fetch_json("estacoes/T")
        imported = skipped = 0
        for row in rows:
            try:
                values = station(row)
            except (ValueError, TypeError, AttributeError):
                skipped += 1
                continue
            save_station(db, values)
            imported += 1
        record_audit(
            db,
            actor=user,
            action="INMET_STATIONS_SYNCED",
            target_type="station",
            target_id="catalog",
            details={"imported": imported},
        )
        db.commit()
        return {"synced": True, "imported": imported, "skipped": skipped}
    except InmetError as error:
        db.rollback()
        raise HTTPException(503, str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            409, "Outra sincronização está em andamento; tente novamente"
        ) from error


@router.post("/import")
def import_history(payload: ImportRequest, db: DbSession, user: Operator):
    try:
        rows, skipped = parse_import(payload.content, payload.format, payload.period)
        if not rows:
            raise ValueError("Nenhuma observação válida encontrada")
        inserted, updated = save_observations(db, rows)
        record_audit(
            db,
            actor=user,
            action="BDMEP_IMPORTED",
            target_type="station",
            target_id="import",
            details={"inserted": inserted, "updated": updated, "skipped": skipped},
        )
        db.commit()
        return {"inserted": inserted, "updated": updated, "skipped": skipped}
    except ValueError as error:
        db.rollback()
        raise HTTPException(422, str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Importação concorrente; tente novamente") from error


@router.get("/{code}/observations", response_model=list[ObservationOut])
def observations(
    code: str,
    db: DbSession,
    start: date | None = None,
    end: date | None = None,
    period: Literal["HOURLY", "DAILY", "MONTHLY"] | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    item = db.get(WeatherStation, code)
    if not item:
        raise HTTPException(404, "Estação não encontrada")
    if start and end and start > end:
        raise HTTPException(422, "Intervalo de datas inválido")
    refresh_latest(db, item)
    query = select(StationObservation).where(StationObservation.station_code == code)
    if start:
        query = query.where(
            StationObservation.observed_at >= datetime.combine(start, datetime.min.time(), UTC)
        )
    if end:
        query = query.where(
            StationObservation.observed_at
            < datetime.combine(end, datetime.min.time(), UTC) + timedelta(days=1)
        )
    if period:
        query = query.where(StationObservation.period == period)
    return list(
        db.scalars(
            query.order_by(desc(StationObservation.observed_at), StationObservation.id)
            .limit(limit)
            .offset(offset)
        )
    )


@router.post("/{code}/sync")
def sync_station(code: str, payload: SyncRequest, db: DbSession, user: Operator):
    item = db.get(WeatherStation, code)
    if not item:
        raise HTTPException(404, "Estação não encontrada; sincronize o catálogo")
    try:
        records = fetch_observations(code, payload.start, payload.end)
        rows, skipped = [], 0
        for row in records:
            try:
                meta, values = observation(row)
                if (
                    meta["code"] != code
                    or not payload.start <= values["observed_at"].date() <= payload.end
                ):
                    raise ValueError("Registro fora da consulta")
                rows.append((meta, values))
            except (ValueError, TypeError, AttributeError):
                skipped += 1
        inserted, updated = save_observations(db, rows)
        if not records:  # o INMET não entrega mais o período; resta a medição mais recente
            inserted, updated = save_latest(db, item)
        record_audit(
            db,
            actor=user,
            action="INMET_OBSERVATIONS_SYNCED",
            target_type="station",
            target_id=code,
            details={"inserted": inserted, "updated": updated},
        )
        db.commit()
        return {"synced": True, "inserted": inserted, "updated": updated, "skipped": skipped}
    except InmetError as error:
        db.rollback()
        raise HTTPException(503, str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Sincronização concorrente; tente novamente") from error
