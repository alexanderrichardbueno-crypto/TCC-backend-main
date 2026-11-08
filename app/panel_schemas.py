"""Contratos da API da central meteorológica (/painel.html)."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator

from app.schemas import check_password, utc_iso

AlertType = Literal["SEVERE_STORM", "TORNADO"]


def _squash(value: object) -> object:
    return " ".join(value.split()) if isinstance(value, str) else value


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("informe data e hora com fuso horário")
    return value.astimezone(UTC)


class PanelAlertIn(BaseModel):
    """UC008: validade, tipo, descrição e área; as instruções são pré-definidas."""

    model_config = ConfigDict(extra="forbid")

    event_type: AlertType
    valid_until: datetime
    message: str = Field(min_length=1, max_length=500)
    points: list[list[float]] = Field(min_length=3, max_length=2000)

    @field_validator("message", mode="before")
    @classmethod
    def squash_message(cls, value: object) -> object:
        return _squash(value)

    @field_validator("valid_until")
    @classmethod
    def aware_valid_until(cls, value: datetime) -> datetime:
        return _aware(value)


class PanelAlertOut(BaseModel):
    id: int
    title: str
    event_type: str
    severity: str
    area_name: str
    message: str
    recommendations: list[str]
    polygon: dict | None
    issued_at: datetime
    valid_until: datetime
    closed_at: datetime | None
    created_by_name: str | None

    @field_serializer("issued_at", "valid_until", "closed_at")
    def serialize_datetimes(self, value: datetime | None) -> str | None:
        return utc_iso(value) if value else None


class ForecastIn(BaseModel):
    """UC005 e UC006: nível, emissão, vencimento, descrição e área."""

    model_config = ConfigDict(extra="forbid")

    level: int = Field(ge=0, le=4)
    issued_at: datetime
    valid_until: datetime
    description: str = Field(min_length=1, max_length=500)
    points: list[list[float]] = Field(min_length=3, max_length=2000)

    @field_validator("description", mode="before")
    @classmethod
    def squash_description(cls, value: object) -> object:
        return _squash(value)

    @field_validator("issued_at", "valid_until")
    @classmethod
    def aware_dates(cls, value: datetime) -> datetime:
        return _aware(value)


class ForecastOut(BaseModel):
    id: int
    level: int
    description: str
    points: list[list[float]]
    issued_at: datetime
    valid_until: datetime
    created_at: datetime
    created_by_name: str | None
    editable_until: datetime

    @field_serializer("issued_at", "valid_until", "created_at", "editable_until")
    def serialize_datetimes(self, value: datetime) -> str:
        return utc_iso(value)


class ActivityOut(BaseModel):
    text: str
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return utc_iso(value)


class AccountOut(BaseModel):
    id: int
    public_code: str
    name: str
    email: str
    role: str
    city: str | None
    state: str | None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return utc_iso(value)


class AccountUpdate(BaseModel):
    """UC003: edita uma ou mais informações, inclusive o nível de acesso."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    role: Literal["USER", "METEOROLOGIST"] | None = None

    @field_validator("name", mode="before")
    @classmethod
    def squash_name(cls, value: object) -> object:
        return _squash(value)


class MeteorologistIn(BaseModel):
    """Credenciamento: nome completo, e-mail e senha temporária."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("name", mode="before")
    @classmethod
    def squash_name(cls, value: object) -> object:
        return _squash(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return check_password(value)


class MeOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    role_name: str
    dark_theme: bool


class PanelStateOut(BaseModel):
    me: MeOut
    alerts: list[PanelAlertOut]
    forecasts: list[ForecastOut]
    activity: list[ActivityOut]
    stations_total: int
    today: str
    generated_at: datetime

    @field_serializer("generated_at")
    def serialize_generated_at(self, value: datetime) -> str:
        return utc_iso(value)
