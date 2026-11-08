from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.integrations.open_meteo import OpenMeteoClient, OpenMeteoError
from app.models import Forecast

OPEN_METEO_SOURCE_NAME = "Open-Meteo"
OPEN_METEO_SOURCE_URL = "https://open-meteo.com/"


def forecast_cache_key(
    city: str,
    state: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
) -> str:
    if latitude is not None and longitude is not None:
        # Coarse cells avoid keeping exact device coordinates and make nearby
        # requests share a cached forecast instead of creating one row per GPS fix.
        location = f"{latitude:.2f}|{longitude:.2f}"
    else:
        location = f"{city.strip().casefold()}|{state.strip().upper()}"
    digest = hashlib.sha256(location.encode("utf-8")).hexdigest()[:32].upper()
    return f"OPEN-METEO-{digest}"


def refresh_open_meteo_forecast(
    db: Session,
    *,
    city: str,
    state: str,
    latitude: float | None = None,
    longitude: float | None = None,
    client: OpenMeteoClient | None = None,
) -> Forecast:
    client = client or OpenMeteoClient()
    coordinates_supplied = latitude is not None and longitude is not None
    if coordinates_supplied:
        latitude, longitude = round(latitude, 2), round(longitude, 2)
    else:
        coordinates = client.geocode(city, state)
        latitude, longitude = coordinates.latitude, coordinates.longitude
    normalized = client.fetch_forecast(latitude, longitude)
    source_key = forecast_cache_key(
        city,
        state,
        latitude=latitude if latitude is not None else None,
        longitude=longitude if longitude is not None else None,
    )
    if not coordinates_supplied:
        # City-only requests retain a stable city key after geocoding so they can be reused.
        source_key = forecast_cache_key(city, state)

    forecast = db.scalar(select(Forecast).where(Forecast.source_key == source_key))
    if not forecast:
        forecast = Forecast(source_key=source_key)
        db.add(forecast)
    forecast.city = " ".join(city.split())
    forecast.state = state.strip().upper()
    forecast.latitude = Decimal(str(round(latitude, 6)))
    forecast.longitude = Decimal(str(round(longitude, 6)))
    forecast.condition = normalized.condition
    forecast.temperature_c = Decimal(str(round(normalized.temperature_c, 2)))
    forecast.minimum_c = Decimal(str(round(normalized.minimum_c, 2)))
    forecast.maximum_c = Decimal(str(round(normalized.maximum_c, 2)))
    forecast.humidity = normalized.humidity
    forecast.wind_kmh = Decimal(str(round(normalized.wind_kmh, 2)))
    forecast.rain_probability = normalized.rain_probability
    forecast.severity = normalized.severity
    forecast.description = normalized.description
    forecast.polygon = None
    forecast.source_name = OPEN_METEO_SOURCE_NAME
    forecast.source_url = OPEN_METEO_SOURCE_URL
    forecast.issued_at = normalized.issued_at
    forecast.valid_until = normalized.valid_until
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Forecast).where(Forecast.source_key == source_key))
        if not existing:
            raise
        return existing
    db.refresh(forecast)
    return forecast


def get_open_meteo_or_fallback(
    db: Session,
    *,
    city: str,
    state: str,
    latitude: float | None = None,
    longitude: float | None = None,
    settings: Settings | None = None,
    client: OpenMeteoClient | None = None,
    require_coordinates: bool = False,
) -> tuple[Forecast | None, bool]:
    settings = settings or get_settings()
    now = datetime.now(UTC)
    source_key = forecast_cache_key(city, state, latitude=latitude, longitude=longitude)
    fresh = db.scalar(
        select(Forecast).where(
            Forecast.source_key == source_key,
            Forecast.issued_at <= now,
            Forecast.valid_until > now,
        )
    )
    if fresh and (
        not require_coordinates or (fresh.latitude is not None and fresh.longitude is not None)
    ):
        return fresh, False

    if settings.open_meteo_enabled:
        try:
            return (
                refresh_open_meteo_forecast(
                    db,
                    city=city,
                    state=state,
                    latitude=latitude,
                    longitude=longitude,
                    client=client or OpenMeteoClient(settings),
                ),
                False,
            )
        except OpenMeteoError:
            pass

    # Existing records predating the coordinate migration remain valid forecasts,
    # even if a point cannot yet be drawn until a successful provider refresh.
    if fresh:
        return fresh, False

    stale_cutoff = now - timedelta(hours=settings.open_meteo_stale_hours)
    stale = db.scalar(
        select(Forecast)
        .where(
            Forecast.source_key == source_key,
            Forecast.source_name == OPEN_METEO_SOURCE_NAME,
            Forecast.issued_at >= stale_cutoff,
            Forecast.issued_at <= now,
        )
        .order_by(desc(Forecast.issued_at))
    )
    if stale:
        return stale, True

    if latitude is None or longitude is None:
        local = db.scalar(
            select(Forecast)
            .where(
                func.lower(Forecast.city) == city.strip().lower(),
                Forecast.state == state.strip().upper(),
                Forecast.issued_at <= now,
                Forecast.valid_until > now,
            )
            .order_by(desc(Forecast.issued_at))
        )
        if local:
            return local, False
    return None, False


__all__ = [
    "OPEN_METEO_SOURCE_NAME",
    "OPEN_METEO_SOURCE_URL",
    "forecast_cache_key",
    "get_open_meteo_or_fallback",
    "refresh_open_meteo_forecast",
]
