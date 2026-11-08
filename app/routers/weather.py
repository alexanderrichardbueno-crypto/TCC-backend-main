from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, select, update
from sqlalchemy.exc import IntegrityError

from app.audit import record_audit
from app.dependencies import CurrentUser, DbSession, optional_current_user, require_roles
from app.inmet_sync import warning_feed_status
from app.models import AlertRead, AlertReview, Forecast, SevereForecast, User, WeatherAlert
from app.open_meteo_sync import get_open_meteo_or_fallback
from app.schemas import (
    AlertCreateRequest,
    AlertOut,
    AlertReviewOut,
    AlertReviewRequest,
    ForecastOut,
    HomeOut,
    MapAlertOut,
    MapDataOut,
    MapForecastOut,
    MapForecastPointOut,
    MessageOut,
    NearbyAlertsOut,
    NearbyForecastOut,
    utc_iso,
)

router = APIRouter(tags=["meteorologia"])

SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1}
FORECAST_LEVEL_SEVERITY = {0: "LOW", 1: "LOW", 2: "MODERATE", 3: "HIGH", 4: "CRITICAL"}


def now_utc() -> datetime:
    return datetime.now(UTC)


def alert_out(alert: WeatherAlert, read_ids: set[int] | None = None) -> AlertOut:
    return AlertOut(
        id=alert.id,
        title=alert.title,
        message=alert.message,
        event_type=alert.event_type,
        severity=alert.severity,
        area_name=alert.area_name,
        recommendations=alert.recommendations,
        origin=alert.origin,
        source_name=alert.source_name,
        source_url=alert.source_url,
        validation_status=alert.validation_status,
        status_reason=alert.status_reason,
        status_changed_at=alert.status_changed_at,
        issued_at=alert.issued_at,
        valid_until=alert.valid_until,
        is_read=bool(read_ids and alert.id in read_ids),
    )


def forecast_out(forecast: Forecast, *, is_stale: bool = False) -> ForecastOut:
    return ForecastOut.model_validate(forecast).model_copy(update={"is_stale": is_stale})


def not_deleted_filter():
    return WeatherAlert.deleted_at.is_(None)


def in_force_filter():
    """Avisos válidos agora: dentro do prazo, não encerrados e não excluídos no painel."""
    now = now_utc()
    return and_(
        WeatherAlert.issued_at <= now,
        WeatherAlert.valid_until > now,
        WeatherAlert.closed_at.is_(None),
        WeatherAlert.deleted_at.is_(None),
    )


def active_alerts(db: DbSession) -> list[WeatherAlert]:
    return list(
        db.scalars(
            select(WeatherAlert)
            .where(
                and_(
                    in_force_filter(),
                    WeatherAlert.validation_status == "ACTIVE",
                )
            )
            .order_by(desc(WeatherAlert.issued_at))
        )
    )


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(radians, (lat1, lon1, lat2, lon2))
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    value = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(value))


def ring_state(longitude: float, latitude: float, ring: list[list[float]]) -> int:
    inside = False
    for index in range(len(ring) - 1):
        x1, y1 = ring[index][:2]
        x2, y2 = ring[index + 1][:2]
        cross = (longitude - x1) * (y2 - y1) - (latitude - y1) * (x2 - x1)
        if (
            abs(cross) <= 1e-9
            and min(x1, x2) - 1e-9 <= longitude <= max(x1, x2) + 1e-9
            and min(y1, y2) - 1e-9 <= latitude <= max(y1, y2) + 1e-9
        ):
            return 2
        if (y1 > latitude) != (y2 > latitude):
            intersection = (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
            if longitude < intersection:
                inside = not inside
    return 1 if inside else 0


def point_in_polygon(longitude: float, latitude: float, geometry: dict) -> bool:
    if geometry.get("type") != "Polygon":
        return False
    rings = geometry.get("coordinates")
    if not isinstance(rings, list) or not rings or len(rings[0]) < 4:
        return False
    outer = ring_state(longitude, latitude, rings[0])
    if outer == 0:
        return False
    if outer == 2:
        return True
    for hole in rings[1:]:
        state = ring_state(longitude, latitude, hole)
        if state == 2:
            return True
        if state == 1:
            return False
    return True


def alerts_for_location(
    alerts: list[WeatherAlert], latitude: float | None, longitude: float | None
) -> list[WeatherAlert]:
    if latitude is None or longitude is None:
        return alerts
    selected = []
    for alert in alerts:
        if alert.polygon:
            if point_in_polygon(longitude, latitude, alert.polygon):
                selected.append(alert)
            continue
        if alert.latitude is None or alert.longitude is None or alert.radius_km is None:
            selected.append(alert)
            continue
        if distance_km(latitude, longitude, float(alert.latitude), float(alert.longitude)) <= float(
            alert.radius_km
        ):
            selected.append(alert)
    return selected


def user_read_ids(db: DbSession, user: User | None, alert_ids: list[int]) -> set[int]:
    if not user or not alert_ids:
        return set()
    return set(
        db.scalars(
            select(AlertRead.alert_id).where(
                AlertRead.user_id == user.id, AlertRead.alert_id.in_(alert_ids)
            )
        )
    )


def map_alert_out(alert: WeatherAlert) -> MapAlertOut:
    return MapAlertOut(
        id=alert.id,
        title=alert.title,
        message=alert.message,
        event_type=alert.event_type,
        severity=alert.severity,
        area_name=alert.area_name,
        latitude=alert.latitude,
        longitude=alert.longitude,
        radius_km=alert.radius_km,
        polygon=alert.polygon,
        origin=alert.origin,
        source_name=alert.source_name,
        source_url=alert.source_url,
        validation_status=alert.validation_status,
        issued_at=alert.issued_at,
        valid_until=alert.valid_until,
    )


def severe_forecast_name(level: int) -> str:
    return "Tempestades não severas" if level == 0 else f"Nível {level}"


def severe_forecast_feature(item: SevereForecast) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "id": item.id,
            "tipo": "previsao",
            "nivel": "T" if item.level == 0 else item.level,
            "nome": severe_forecast_name(item.level),
            "descricao": item.description,
            "validade": utc_iso(item.valid_until),
        },
        "geometry": item.polygon,
    }


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    db: DbSession,
    user: Annotated[User | None, Depends(optional_current_user)],
    active: bool = Query(default=True),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
):
    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=422, detail="Latitude e longitude devem ser informadas juntas"
        )
    query = select(WeatherAlert)
    query = query.where(WeatherAlert.validation_status == "ACTIVE", not_deleted_filter())
    if active:
        query = query.where(in_force_filter())
    alerts = list(db.scalars(query.order_by(desc(WeatherAlert.issued_at))))
    if user and latitude is None and user.latitude is not None and user.longitude is not None:
        latitude, longitude = float(user.latitude), float(user.longitude)
    alerts = alerts_for_location(alerts, latitude, longitude)
    read_ids = user_read_ids(db, user, [alert.id for alert in alerts])
    return [alert_out(alert, read_ids) for alert in alerts]


@router.get("/alerts/nearby", response_model=NearbyAlertsOut)
def nearby_alerts(
    db: DbSession,
    user: Annotated[User | None, Depends(optional_current_user)],
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
):
    """Alertas e previsões de tempo severo que cobrem a região do usuário.

    As coordenadas do aparelho só são usadas nesta consulta; nada é salvo no perfil.
    """
    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=422, detail="Latitude e longitude devem ser informadas juntas"
        )
    city = user.city if user and user.city else "Mongagua"
    state = user.state if user and user.state else "SP"
    location = f"{city}, {state}"
    if latitude is not None:
        location = "Sua localização atual"
    elif user and user.latitude is not None and user.longitude is not None:
        latitude, longitude = float(user.latitude), float(user.longitude)
    else:
        forecast, _ = get_open_meteo_or_fallback(
            db, city=city, state=state, latitude=None, longitude=None, require_coordinates=True
        )
        if forecast and forecast.latitude is not None and forecast.longitude is not None:
            latitude, longitude = float(forecast.latitude), float(forecast.longitude)
            location = f"{forecast.city}, {forecast.state}"
    if latitude is None or longitude is None:
        return NearbyAlertsOut(location=None, alerts=[], forecasts=[])

    # Aqui só entra o que comprovadamente cobre a região; aviso sem área não dá para confirmar.
    delimited = [
        alert
        for alert in active_alerts(db)
        if alert.polygon or (alert.latitude is not None and alert.radius_km is not None)
    ]
    alerts = alerts_for_location(delimited, latitude, longitude)
    alerts.sort(key=lambda alert: (alert.origin != "MANUAL", -SEVERITY_RANK.get(alert.severity, 0)))
    read_ids = user_read_ids(db, user, [alert.id for alert in alerts])

    severe = db.scalars(
        select(SevereForecast)
        .where(SevereForecast.issued_at <= now_utc(), SevereForecast.valid_until > now_utc())
        .order_by(desc(SevereForecast.level), SevereForecast.id)
    )
    forecasts = [
        NearbyForecastOut(
            id=item.id,
            level=item.level,
            level_name=severe_forecast_name(item.level),
            severity=FORECAST_LEVEL_SEVERITY.get(item.level, "LOW"),
            description=item.description,
            issued_at=item.issued_at,
            valid_until=item.valid_until,
        )
        for item in severe
        if point_in_polygon(longitude, latitude, item.polygon)
    ]
    return NearbyAlertsOut(
        location=location,
        alerts=[alert_out(alert, read_ids) for alert in alerts],
        forecasts=forecasts,
    )


@router.get("/alerts/review-queue", response_model=list[AlertOut])
def alert_review_queue(
    db: DbSession,
    _: Annotated[User, Depends(require_roles("METEOROLOGIST"))],
    limit: int = Query(default=100, ge=1, le=200),
):
    alerts = db.scalars(
        select(WeatherAlert)
        .where(not_deleted_filter())
        .order_by(desc(WeatherAlert.issued_at))
        .limit(limit)
    )
    return [alert_out(alert) for alert in alerts]


@router.post("/alerts", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
def create_alert(
    payload: AlertCreateRequest,
    db: DbSession,
    user: Annotated[User, Depends(require_roles("METEOROLOGIST"))],
):
    alert = WeatherAlert(
        created_by=user.id,
        origin="MANUAL",
        source_name="PrevClima - inserção manual",
        validation_status="ACTIVE",
        title=payload.title,
        message=payload.message,
        event_type=payload.event_type,
        severity=payload.severity,
        area_name=payload.area_name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_km=payload.radius_km,
        polygon=payload.polygon,
        recommendations=payload.recommendations,
        issued_at=payload.issued_at,
        valid_until=payload.valid_until,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert_out(alert)


@router.post("/alerts/{alert_id}/review", response_model=AlertOut)
def review_alert(
    alert_id: int,
    payload: AlertReviewRequest,
    db: DbSession,
    user: Annotated[User, Depends(require_roles("METEOROLOGIST"))],
):
    alert = db.get(WeatherAlert, alert_id)
    if not alert or alert.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aviso não encontrado")
    previous_status = alert.validation_status
    if previous_status == payload.validation_status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O aviso já possui essa situação de validação",
        )
    changed_at = now_utc()
    result = db.execute(
        update(WeatherAlert)
        .where(
            WeatherAlert.id == alert_id,
            WeatherAlert.validation_status == previous_status,
        )
        .values(
            validation_status=payload.validation_status,
            status_reason=payload.reason,
            status_changed_by=user.id,
            status_changed_at=changed_at,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O aviso foi revisado por outra pessoa; atualize a página",
        )
    db.add(
        AlertReview(
            alert_id=alert_id,
            reviewer_id=user.id,
            previous_status=previous_status,
            new_status=payload.validation_status,
            reason=payload.reason,
            created_at=changed_at,
        )
    )
    record_audit(
        db,
        actor=user,
        action="ALERT_REVIEWED",
        target_type="weather_alert",
        target_id=alert_id,
        details={
            "previous_status": previous_status,
            "new_status": payload.validation_status,
            "reason": payload.reason,
        },
    )
    db.commit()
    return alert_out(db.get(WeatherAlert, alert_id))


@router.get("/alerts/{alert_id}/reviews", response_model=list[AlertReviewOut])
def alert_review_history(
    alert_id: int,
    db: DbSession,
    _: Annotated[User, Depends(require_roles("METEOROLOGIST"))],
):
    if not db.get(WeatherAlert, alert_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aviso não encontrado")
    return list(
        db.scalars(
            select(AlertReview)
            .where(AlertReview.alert_id == alert_id)
            .order_by(AlertReview.created_at, AlertReview.id)
        )
    )


@router.post("/alerts/{alert_id}/read", response_model=MessageOut)
def mark_alert_read(alert_id: int, user: CurrentUser, db: DbSession):
    alert = db.scalar(
        select(WeatherAlert).where(
            WeatherAlert.id == alert_id,
            WeatherAlert.validation_status == "ACTIVE",
            not_deleted_filter(),
        )
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aviso não encontrado")
    exists = db.scalar(
        select(AlertRead.id).where(AlertRead.user_id == user.id, AlertRead.alert_id == alert_id)
    )
    if not exists:
        db.add(AlertRead(user_id=user.id, alert_id=alert_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return MessageOut(message="Aviso marcado como lido")


@router.get("/forecasts/current", response_model=ForecastOut)
def current_forecast(
    db: DbSession,
    city: str = Query(default="Mongagua", min_length=2, max_length=100),
    state: str = Query(default="SP", min_length=2, max_length=2),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
):
    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=422, detail="Latitude e longitude devem ser informadas juntas"
        )
    forecast, is_stale = get_open_meteo_or_fallback(
        db,
        city=city,
        state=state,
        latitude=latitude,
        longitude=longitude,
    )
    if not forecast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Previsão atual indisponível"
        )
    return forecast_out(forecast, is_stale=is_stale)


@router.get("/home", response_model=HomeOut)
def home(
    db: DbSession,
    user: Annotated[User | None, Depends(optional_current_user)],
    city: str | None = Query(default=None, min_length=2, max_length=100),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
):
    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=422, detail="Latitude e longitude devem ser informadas juntas"
        )
    if (city is None) != (state is None):
        raise HTTPException(status_code=422, detail="Cidade e UF devem ser informadas juntas")
    explicit_location = city is not None or latitude is not None
    if city is None:
        city = user.city if user and user.city else "Mongagua"
        state = user.state if user and user.state else "SP"
    if not explicit_location and user and user.latitude is not None and user.longitude is not None:
        latitude, longitude = float(user.latitude), float(user.longitude)
    forecast, is_stale = get_open_meteo_or_fallback(
        db,
        city=city,
        state=state,
        latitude=latitude,
        longitude=longitude,
    )
    if not forecast and latitude is not None and longitude is not None:
        area_forecasts = db.scalars(
            select(Forecast)
            .where(
                Forecast.issued_at <= now_utc(),
                Forecast.valid_until > now_utc(),
                Forecast.polygon.is_not(None),
            )
            .order_by(desc(Forecast.issued_at))
        )
        forecast = next(
            (
                item
                for item in area_forecasts
                if item.polygon and point_in_polygon(longitude, latitude, item.polygon)
            ),
            None,
        )
    if (
        latitude is None
        and forecast
        and forecast.latitude is not None
        and forecast.longitude is not None
    ):
        latitude, longitude = float(forecast.latitude), float(forecast.longitude)
    alerts = alerts_for_location(active_alerts(db), latitude, longitude)
    # Highlight the most severe current warning, rather than the newest mild one.
    alerts.sort(key=lambda alert: SEVERITY_RANK.get(alert.severity, 0), reverse=True)
    read_ids = user_read_ids(db, user, [alert.id for alert in alerts])
    rendered = [alert_out(alert, read_ids) for alert in alerts]
    return HomeOut(
        warning_feed=warning_feed_status(db),
        forecast=forecast_out(forecast, is_stale=is_stale) if forecast else None,
        active_alerts=rendered,
        unread_alert_count=(
            sum(1 for alert in rendered if not alert.is_read)
            if not user or user.weather_notifications
            else 0
        ),
    )


@router.get("/map-data", response_model=MapDataOut)
def map_data(
    db: DbSession,
    user: Annotated[User | None, Depends(optional_current_user)],
    city: str | None = Query(default=None, min_length=2, max_length=100),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
):
    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=422, detail="Latitude e longitude devem ser informadas juntas"
        )
    if (city is None) != (state is None):
        raise HTTPException(status_code=422, detail="Cidade e UF devem ser informadas juntas")
    if latitude is not None and user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Entre na sua conta para consultar sua localização no mapa",
        )
    explicit_location = city is not None or latitude is not None
    if city is None:
        if latitude is not None:
            city, state = "Minha localização", "BR"
        else:
            city = user.city if user and user.city else "Mongagua"
            state = user.state if user and user.state else "SP"
    if latitude is None and not explicit_location and user:
        if user.latitude is not None and user.longitude is not None:
            latitude, longitude = float(user.latitude), float(user.longitude)
    forecast, is_stale = get_open_meteo_or_fallback(
        db,
        city=city,
        state=state,
        latitude=latitude,
        longitude=longitude,
        require_coordinates=True,
    )
    forecast_points = []
    if forecast and forecast.latitude is not None and forecast.longitude is not None:
        forecast_points.append(
            MapForecastPointOut(
                id=forecast.id,
                city=forecast.city,
                state=forecast.state,
                latitude=forecast.latitude,
                longitude=forecast.longitude,
                condition=forecast.condition,
                temperature_c=forecast.temperature_c,
                rain_probability=forecast.rain_probability,
                source_name=forecast.source_name,
                source_url=forecast.source_url,
                issued_at=forecast.issued_at,
                valid_until=forecast.valid_until,
                is_stale=is_stale,
            )
        )
    alerts = [map_alert_out(alert) for alert in active_alerts(db)]
    upcoming = db.scalars(
        select(WeatherAlert)
        .where(
            WeatherAlert.origin == "INMET",
            WeatherAlert.issued_at > now_utc(),
            WeatherAlert.valid_until > now_utc(),
            WeatherAlert.validation_status == "ACTIVE",
            WeatherAlert.closed_at.is_(None),
            not_deleted_filter(),
        )
        .order_by(WeatherAlert.issued_at)
    )
    forecasts = db.scalars(
        select(Forecast)
        .where(
            Forecast.issued_at <= now_utc(),
            Forecast.valid_until > now_utc(),
            Forecast.polygon.is_not(None),
        )
        .order_by(desc(Forecast.issued_at))
    )
    forecast_areas = [
        MapForecastOut(
            id=forecast.id,
            city=forecast.city,
            state=forecast.state,
            severity=forecast.severity,
            polygon=forecast.polygon,
            source_name=forecast.source_name,
            valid_until=forecast.valid_until,
        )
        for forecast in forecasts
        if forecast.polygon
    ]
    severe = list(
        db.scalars(
            select(SevereForecast)
            .where(SevereForecast.issued_at <= now_utc(), SevereForecast.valid_until > now_utc())
            .order_by(SevereForecast.level, SevereForecast.id)
        )
    )
    return MapDataOut(
        warning_feed=warning_feed_status(db),
        alerts=alerts,
        upcoming_alerts=[map_alert_out(alert) for alert in upcoming],
        forecast_areas=forecast_areas,
        forecast_points=forecast_points,
        published_areas=[severe_forecast_feature(item) for item in severe],
        published_areas_at=max((item.created_at for item in severe), default=None),
        generated_at=now_utc(),
    )
