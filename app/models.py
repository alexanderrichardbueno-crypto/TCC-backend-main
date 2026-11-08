from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="ck_user_lat"),
        CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="ck_user_lon"),
        CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL)",
            name="ck_user_coordinates_pair",
        ),
        Index("ix_users_name", "name"),
        Index("ix_users_role_id", "role_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    weather_notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alert_sound: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    dark_theme: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    role: Mapped[Role] = relationship(lazy="joined")


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        CheckConstraint("valid_until > issued_at", name="ck_forecast_validity"),
        CheckConstraint("humidity BETWEEN 0 AND 100", name="ck_forecast_humidity"),
        CheckConstraint("rain_probability BETWEEN 0 AND 100", name="ck_forecast_rain"),
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="ck_forecast_lat"),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180", name="ck_forecast_lon"
        ),
        CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL)",
            name="ck_forecast_coordinates_pair",
        ),
        Index("ix_forecasts_location_valid", "city", "state", "valid_until"),
        Index("ix_forecasts_coords_valid", "latitude", "longitude", "valid_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    condition: Mapped[str] = mapped_column(String(120), nullable=False)
    temperature_c: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    minimum_c: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    maximum_c: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    humidity: Mapped[int] = mapped_column(Integer, nullable=False)
    wind_kmh: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    rain_probability: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default="LOW", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    polygon: Mapped[dict | None] = mapped_column(JSON)
    source_name: Mapped[str] = mapped_column(String(120), default="PrevClima", nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class WeatherAlert(Base):
    __tablename__ = "weather_alerts"
    __table_args__ = (
        CheckConstraint("valid_until > issued_at", name="ck_alert_validity"),
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="ck_alert_lat"),
        CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="ck_alert_lon"),
        CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL)",
            name="ck_alert_coordinates_pair",
        ),
        CheckConstraint("radius_km IS NULL OR radius_km > 0", name="ck_alert_radius"),
        CheckConstraint(
            "origin = 'INMET' OR polygon IS NOT NULL OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL AND radius_km IS NOT NULL)",
            name="ck_alert_has_area",
        ),
        CheckConstraint(
            "severity IN ('LOW', 'MODERATE', 'HIGH', 'CRITICAL')",
            name="ck_alert_severity",
        ),
        CheckConstraint(
            "validation_status IN ('ACTIVE', 'FALSE_ALARM', 'NEEDS_CORRECTION')",
            name="ck_alert_validation_status",
        ),
        CheckConstraint(
            "origin IN ('MANUAL', 'INMET')",
            name="ck_alert_origin",
        ),
        Index("ix_alerts_active", "valid_until", "severity"),
        Index("ix_alerts_validation", "validation_status", "valid_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    origin: Mapped[str] = mapped_column(String(16), default="MANUAL", nullable=False)
    source_name: Mapped[str] = mapped_column(String(120), default="PrevClima", nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    validation_status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False)
    status_reason: Mapped[str | None] = mapped_column(Text)
    status_changed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    area_name: Mapped[str] = mapped_column(String(160), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    radius_km: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    polygon: Mapped[dict | None] = mapped_column(JSON)
    recommendations: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Encerramento manual pelo painel: o aviso deixa de valer antes do prazo.
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Exclusão pelo painel: some das consultas, mas o registro e a auditoria permanecem.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AlertReview(Base):
    __tablename__ = "alert_reviews"
    __table_args__ = (
        CheckConstraint(
            "previous_status IN ('ACTIVE', 'FALSE_ALARM', 'NEEDS_CORRECTION')",
            name="ck_alert_review_previous_status",
        ),
        CheckConstraint(
            "new_status IN ('ACTIVE', 'FALSE_ALARM', 'NEEDS_CORRECTION')",
            name="ck_alert_review_new_status",
        ),
        Index("ix_alert_reviews_alert_created", "alert_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("weather_alerts.id", ondelete="RESTRICT"), nullable=False
    )
    reviewer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    previous_status: Mapped[str] = mapped_column(String(24), nullable=False)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_target_created", "target_type", "target_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AlertRead(Base):
    __tablename__ = "alert_reads"
    __table_args__ = (UniqueConstraint("user_id", "alert_id", name="uq_alert_read_user_alert"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("weather_alerts.id", ondelete="CASCADE"), nullable=False
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class News(Base):
    __tablename__ = "news"
    __table_args__ = (Index("ix_news_published", "published_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EducationalContent(Base):
    __tablename__ = "educational_contents"
    __table_args__ = (Index("ix_education_published", "published_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    media_url: Mapped[str | None] = mapped_column(String(500))
    reference_url: Mapped[str] = mapped_column(String(500), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SevereForecast(Base):
    """Previsão de tempo severo emitida por um meteorologista (UC005 a UC007)."""

    __tablename__ = "severe_forecasts"
    __table_args__ = (
        CheckConstraint("level BETWEEN 0 AND 4", name="ck_severe_forecast_level"),
        CheckConstraint("valid_until > issued_at", name="ck_severe_forecast_validity"),
        Index("ix_severe_forecasts_valid", "valid_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    polygon: Mapped[dict] = mapped_column(JSON, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Início da janela de 30 minutos para editar ou excluir: o momento real da emissão no sistema.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class AccountCode(Base):
    """Código enviado por e-mail para confirmar o cadastro ou redefinir a senha."""

    __tablename__ = "account_codes"
    __table_args__ = (
        CheckConstraint("purpose IN ('VERIFY_EMAIL', 'RESET_PASSWORD')", name="ck_code_purpose"),
        Index("ix_account_codes_user_purpose", "user_id", "purpose"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
