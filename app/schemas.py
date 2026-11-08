import re
from datetime import UTC, datetime
from decimal import Decimal
from math import isfinite
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

# RNF01: pelo menos 6 caracteres, com uma letra maiúscula e um caractere especial.
PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{6,128}$")
PASSWORD_MESSAGE = "a senha precisa de 6 caracteres, uma letra maiúscula e um caractere especial"


def check_password(value: str) -> str:
    if not PASSWORD_PATTERN.match(value):
        raise ValueError(PASSWORD_MESSAGE)
    return value


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def validate_geojson_polygon(value: dict) -> dict:
    if value.get("type") != "Polygon" or set(value) - {"type", "coordinates"}:
        raise ValueError("o polígono deve ser uma geometria GeoJSON do tipo Polygon")
    rings = value.get("coordinates")
    if not isinstance(rings, list) or not rings:
        raise ValueError("o polígono deve conter pelo menos um anel")
    point_count = 0
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("cada anel deve ser fechado e conter pelo menos quatro pontos")
        for point in ring:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("os pontos devem ser pares [longitude, latitude]")
            longitude, latitude = point
            if (
                isinstance(longitude, bool)
                or isinstance(latitude, bool)
                or not isinstance(longitude, (int, float))
                or not isinstance(latitude, (int, float))
                or not isfinite(longitude)
                or not isfinite(latitude)
                or not -180 <= longitude <= 180
                or not -90 <= latitude <= 90
            ):
                raise ValueError("as coordenadas do polígono estão fora dos limites válidos")
            point_count += 1
            if point_count > 10_000:
                raise ValueError("o polígono não pode conter mais de 10000 pontos")
    return value


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("name", "city")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else value

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return check_password(value)

    @model_validator(mode="after")
    def location_pair(self):
        if bool(self.city) != bool(self.state):
            raise ValueError("cidade e UF devem ser informadas juntas")
        return self


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RegisterOut(BaseModel):
    message: str
    email: EmailStr


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class VerifyEmailRequest(EmailRequest):
    code: str = Field(pattern=r"^\d{6}$")


class ResetPasswordRequest(VerifyEmailRequest):
    password: str = Field(min_length=1, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return check_password(value)


class UserOut(BaseModel):
    id: int
    public_code: str
    name: str
    email: EmailStr
    role: str
    role_name: str
    city: str | None
    state: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    weather_notifications: bool
    alert_sound: bool
    dark_theme: bool
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return utc_iso(value)


class AuthResponse(BaseModel):
    user: UserOut
    csrf_token: str
    # Preenchido apenas no login do aplicativo nativo (React Native), que usa
    # o cabeçalho Authorization: Bearer em vez de cookies.
    access_token: str | None = None


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=120)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    weather_notifications: bool | None = None
    alert_sound: bool | None = None
    dark_theme: bool | None = None

    @field_validator("name", "city")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else value

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @model_validator(mode="after")
    def validate_pairs(self):
        supplied = self.model_fields_set
        if "name" in supplied and self.name is None:
            raise ValueError("o nome não pode ser nulo")
        if "city" in supplied or "state" in supplied:
            if not {"city", "state"}.issubset(supplied) or bool(self.city) != bool(self.state):
                raise ValueError("cidade e UF devem ser informadas juntas ou ambas removidas")
        if "latitude" in supplied or "longitude" in supplied:
            if not {"latitude", "longitude"}.issubset(supplied) or (
                (self.latitude is None) != (self.longitude is None)
            ):
                raise ValueError(
                    "latitude e longitude devem ser informadas juntas ou ambas removidas"
                )
        for field in ("weather_notifications", "alert_sound", "dark_theme"):
            if field in supplied and getattr(self, field) is None:
                raise ValueError(f"{field} não pode ser nulo")
        return self


class ForecastOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    city: str
    state: str
    condition: str
    temperature_c: Decimal
    minimum_c: Decimal
    maximum_c: Decimal
    humidity: int
    wind_kmh: Decimal
    rain_probability: int
    severity: str
    description: str | None
    source_name: str
    source_url: str | None = None
    is_stale: bool = False
    issued_at: datetime
    valid_until: datetime

    @field_serializer("issued_at", "valid_until")
    def serialize_datetimes(self, value: datetime) -> str:
        return utc_iso(value)


class AlertOut(BaseModel):
    id: int
    title: str
    message: str
    event_type: str
    severity: str
    area_name: str
    recommendations: list[str]
    origin: str
    source_name: str
    source_url: str | None
    validation_status: str
    status_reason: str | None
    status_changed_at: datetime | None
    issued_at: datetime
    valid_until: datetime
    is_read: bool = False

    @field_serializer("issued_at", "valid_until", "status_changed_at")
    def serialize_datetimes(self, value: datetime | None) -> str | None:
        return utc_iso(value) if value else None


class AlertCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=140)
    message: str = Field(min_length=10, max_length=5000)
    event_type: Literal["SEVERE_STORM", "TORNADO"]
    severity: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]
    area_name: str = Field(min_length=2, max_length=160)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    radius_km: Decimal | None = Field(default=None, gt=0, le=1000)
    polygon: dict | None = None
    recommendations: list[str] = Field(min_length=1, max_length=12)
    issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    valid_until: datetime

    @field_validator("title", "message", "area_name", mode="before")
    @classmethod
    def clean_required_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("issued_at", "valid_until")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("informe data e hora com fuso horário")
        return value.astimezone(UTC)

    @field_validator("recommendations")
    @classmethod
    def validate_recommendations(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(value.split()) for value in values if value.strip()]
        if not cleaned or any(len(value) > 300 for value in cleaned):
            raise ValueError("as recomendações devem conter textos de até 300 caracteres")
        return cleaned

    @model_validator(mode="after")
    def validate_area_and_time(self):
        if self.valid_until <= self.issued_at:
            raise ValueError("a validade deve ser posterior à emissão")
        has_circle = all(
            value is not None for value in (self.latitude, self.longitude, self.radius_km)
        )
        if self.polygon:
            self.polygon = validate_geojson_polygon(self.polygon)
        elif not has_circle:
            raise ValueError("informe um polígono ou latitude, longitude e raio em km")
        return self


class AlertReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validation_status: Literal["ACTIVE", "FALSE_ALARM", "NEEDS_CORRECTION"]
    reason: str = Field(min_length=10, max_length=2000)

    @field_validator("reason", mode="before")
    @classmethod
    def clean_reason(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value


class AlertReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_id: int
    reviewer_id: int
    previous_status: str
    new_status: str
    reason: str
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return utc_iso(value)


class WarningFeedOut(BaseModel):
    status: Literal["current", "stale", "unavailable", "pending", "disabled"]
    last_success_at: datetime | None = None

    @field_serializer("last_success_at")
    def serialize_last_success(self, value: datetime | None) -> str | None:
        return utc_iso(value) if value else None


class HomeOut(BaseModel):
    forecast: ForecastOut | None
    active_alerts: list[AlertOut]
    unread_alert_count: int
    warning_feed: WarningFeedOut


class NearbyForecastOut(BaseModel):
    id: int
    level: int
    level_name: str
    severity: str
    description: str
    issued_at: datetime
    valid_until: datetime

    @field_serializer("issued_at", "valid_until")
    def serialize_datetimes(self, value: datetime) -> str:
        return utc_iso(value)


class NearbyAlertsOut(BaseModel):
    location: str | None
    alerts: list[AlertOut]
    forecasts: list[NearbyForecastOut]


class MapAlertOut(BaseModel):
    id: int
    title: str
    message: str
    event_type: str
    severity: str
    area_name: str
    latitude: Decimal | None
    longitude: Decimal | None
    radius_km: Decimal | None
    polygon: dict | None
    origin: str
    source_name: str
    source_url: str | None
    validation_status: str
    issued_at: datetime
    valid_until: datetime

    @field_serializer("issued_at", "valid_until")
    def serialize_datetimes(self, value: datetime) -> str:
        return utc_iso(value)


class MapForecastOut(BaseModel):
    id: int
    city: str
    state: str
    severity: str
    polygon: dict
    source_name: str
    valid_until: datetime

    @field_serializer("valid_until")
    def serialize_valid_until(self, value: datetime) -> str:
        return utc_iso(value)


class MapForecastPointOut(BaseModel):
    id: int
    city: str
    state: str
    latitude: Decimal
    longitude: Decimal
    condition: str
    temperature_c: Decimal
    rain_probability: int
    source_name: str
    source_url: str | None
    issued_at: datetime
    valid_until: datetime
    is_stale: bool = False

    @field_serializer("issued_at", "valid_until")
    def serialize_datetimes(self, value: datetime) -> str:
        return utc_iso(value)


class MapDataOut(BaseModel):
    warning_feed: WarningFeedOut
    alerts: list[MapAlertOut]
    # Avisos oficiais que ainda vão começar ("próximos dias" no mapa).
    upcoming_alerts: list[MapAlertOut] = Field(default_factory=list)
    forecast_areas: list[MapForecastOut]
    forecast_points: list[MapForecastPointOut] = Field(default_factory=list)
    # Áreas de previsão e de alerta publicadas pelo painel dos meteorologistas (GeoJSON).
    published_areas: list[dict] = Field(default_factory=list)
    published_areas_at: datetime | None = None
    generated_at: datetime

    @field_serializer("generated_at")
    def serialize_generated_at(self, value: datetime) -> str:
        return utc_iso(value)

    @field_serializer("published_areas_at")
    def serialize_published_at(self, value: datetime | None) -> str | None:
        return utc_iso(value) if value else None


class EducationalContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    media_url: str | None
    reference_url: str
    published_at: datetime

    @field_serializer("published_at")
    def serialize_published_at(self, value: datetime) -> str:
        return utc_iso(value)


class MessageOut(BaseModel):
    message: str


class InmetWarningSyncOut(BaseModel):
    synced: bool
    using_stored_data: bool
    message: str
    imported: int
    skipped: int
    stored_active_alerts: int
