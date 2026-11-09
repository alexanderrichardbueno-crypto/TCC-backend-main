"""Station metadata and measured weather, separate from forecast products."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models import utcnow


class WeatherStation(Base):
    __tablename__ = "weather_stations"
    __table_args__ = (
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="ck_station_lat"),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180", name="ck_station_lon"
        ),
        Index("ix_stations_state_name", "state", "name"),
    )
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str | None] = mapped_column(String(2))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    geocode: Mapped[str | None] = mapped_column(String(7))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class StationObservation(Base):
    __tablename__ = "station_observations"
    __table_args__ = (
        UniqueConstraint("station_code", "observed_at", "period", name="uq_station_observation"),
        CheckConstraint(
            "humidity IS NULL OR humidity BETWEEN 0 AND 100", name="ck_observation_humidity"
        ),
        CheckConstraint(
            "precipitation_mm IS NULL OR precipitation_mm >= 0", name="ck_observation_rain"
        ),
        CheckConstraint("wind_ms IS NULL OR wind_ms >= 0", name="ck_observation_wind"),
        CheckConstraint("period IN ('HOURLY', 'DAILY', 'MONTHLY')", name="ck_observation_period"),
        Index("ix_observations_time", "observed_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_code: Mapped[str] = mapped_column(
        ForeignKey("weather_stations.code", ondelete="RESTRICT")
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period: Mapped[str] = mapped_column(String(10), nullable=False)
    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    minimum_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    maximum_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    humidity: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    precipitation_mm: Mapped[Decimal | None] = mapped_column(Numeric(9, 2))
    wind_ms: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
