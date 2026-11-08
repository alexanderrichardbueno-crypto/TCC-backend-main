"""API da central meteorológica (/painel.html).

Implementa os casos de uso UC002 a UC008 do documento do projeto. Existe um único nível de
acesso profissional, o de meteorologista.
"""

import json
import re
import time
from datetime import UTC, datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.audit import record_audit
from app.config import get_settings
from app.dependencies import DbSession, require_roles
from app.models import AuditEvent, Role, SevereForecast, User, WeatherAlert, utcnow
from app.panel_schemas import (
    AccountOut,
    AccountUpdate,
    ActivityOut,
    ForecastIn,
    ForecastOut,
    MeOut,
    MeteorologistIn,
    PanelAlertIn,
    PanelAlertOut,
    PanelStateOut,
)
from app.routers.auth import new_public_code, normalized_email
from app.schemas import MessageOut, validate_geojson_polygon
from app.security import hash_password
from app.station_models import WeatherStation

router = APIRouter(prefix="/panel", tags=["central meteorológica"])

Meteorologist = Annotated[User, Depends(require_roles("METEOROLOGIST"))]

EDIT_WINDOW = timedelta(minutes=30)
EDIT_EXPIRED = "Já se passou 30 minutos desde a emissão da previsão, você não pode mais editá-la."
DELETE_EXPIRED = (
    "Já se passou 30 minutos desde a emissão da previsão, você não pode mais excluí-la."
)
ALERT_TYPES = {
    "SEVERE_STORM": {
        "name": "Alerta de tempestade severa",
        "severity": "HIGH",
        "recommendations": [
            "Procure abrigo em local coberto imediatamente",
            "Evite áreas abertas e não se abrigue sob árvores",
            "Mantenha-se longe de janelas",
            "Emergências: Bombeiros 193 e Defesa Civil 199",
        ],
    },
    "TORNADO": {
        "name": "Alerta de tornado",
        "severity": "CRITICAL",
        "recommendations": [
            "Vá imediatamente para o cômodo mais interno e baixo da construção",
            "Afaste-se de portas e janelas e proteja a cabeça e o pescoço",
            "Não permaneça em veículos ou estruturas leves",
            "Emergências: Bombeiros 193 e Defesa Civil 199",
        ],
    },
}
REGION_MAX_KM = 150
# Referências usadas só para dar um nome legível à área desenhada no mapa.
REGIONS = {
    "Norte de São Paulo": (-21.18, -47.81),
    "Grande São Paulo": (-23.55, -46.63),
    "Campinas e região": (-22.90, -47.06),
    "Baixada Santista": (-24.00, -46.40),
    "Litoral Sul de São Paulo": (-24.71, -47.56),
    "Litoral Norte de São Paulo": (-23.62, -45.41),
    "Vale do Ribeira": (-24.50, -47.85),
    "Curitiba e região": (-25.43, -49.27),
    "Litoral do Paraná": (-25.52, -48.51),
    "Norte do Paraná": (-23.31, -51.16),
    "Oeste do Paraná": (-24.96, -53.46),
    "Grande Florianópolis": (-27.60, -48.55),
    "Norte de Santa Catarina": (-26.30, -48.85),
    "Oeste de Santa Catarina": (-27.10, -52.62),
    "Porto Alegre e região": (-30.03, -51.23),
    "Serra Gaúcha": (-29.17, -51.18),
    "Campo Grande e região": (-20.47, -54.62),
    "Cuiabá e região": (-15.60, -56.10),
    "Goiânia e região": (-16.69, -49.26),
    "Distrito Federal": (-15.79, -47.88),
    "Belo Horizonte e região": (-19.92, -43.94),
    "Rio de Janeiro e região": (-22.91, -43.20),
}


def now_utc() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def today_br() -> str:
    """Data atual no horário de Brasília (UTC-3, sem horário de verão desde 2019)."""
    return (now_utc() - timedelta(hours=3)).date().isoformat()


def closed_polygon(points: list[list[float]]) -> dict:
    if any(len(point) != 2 for point in points):
        raise HTTPException(status_code=422, detail="Área inválida no mapa")
    ring = [[round(float(p[0]), 5), round(float(p[1]), 5)] for p in points]
    if len(ring) < 3:
        raise HTTPException(status_code=422, detail="A área precisa de pelo menos 3 pontos")
    if ring[0] != ring[-1]:
        ring.append(list(ring[0]))
    try:
        return validate_geojson_polygon({"type": "Polygon", "coordinates": [ring]})
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    value = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(value))


def area_name_for(polygon: dict) -> str:
    ring = polygon["coordinates"][0][:-1]
    longitude = sum(point[0] for point in ring) / len(ring)
    latitude = sum(point[1] for point in ring) / len(ring)
    name, center = min(REGIONS.items(), key=lambda item: distance_km(latitude, longitude, *item[1]))
    if distance_km(latitude, longitude, *center) > REGION_MAX_KM:
        return "Área desenhada no mapa"
    return name


# ----------------------------------------------------------------------------- alertas


def names_by_id(db: DbSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.name).where(User.id.in_(ids))).all())


def alert_out(alert: WeatherAlert, names: dict[int, str]) -> PanelAlertOut:
    return PanelAlertOut(
        id=alert.id,
        title=alert.title,
        event_type=alert.event_type,
        severity=alert.severity,
        area_name=alert.area_name,
        message=alert.message,
        recommendations=alert.recommendations,
        polygon=alert.polygon,
        issued_at=alert.issued_at,
        valid_until=alert.valid_until,
        closed_at=alert.closed_at,
        created_by_name=names.get(alert.created_by) if alert.created_by else None,
    )


def list_panel_alerts(db: DbSession) -> list[PanelAlertOut]:
    since = now_utc() - timedelta(days=30)
    alerts = list(
        db.scalars(
            select(WeatherAlert)
            .where(
                WeatherAlert.origin == "MANUAL",
                WeatherAlert.deleted_at.is_(None),
                or_(WeatherAlert.issued_at >= since, WeatherAlert.valid_until > now_utc()),
            )
            .order_by(desc(WeatherAlert.issued_at))
            .limit(300)
        )
    )
    names = names_by_id(db, {alert.created_by for alert in alerts if alert.created_by})
    return [alert_out(alert, names) for alert in alerts]


@router.post("/alerts", response_model=PanelAlertOut, status_code=status.HTTP_201_CREATED)
def create_alert(payload: PanelAlertIn, db: DbSession, user: Meteorologist):
    issued = now_utc()
    if payload.valid_until <= issued:
        raise HTTPException(status_code=422, detail="A validade deve ser uma data futura")
    polygon = closed_polygon(payload.points)
    kind = ALERT_TYPES[payload.event_type]
    area_name = area_name_for(polygon)
    alert = WeatherAlert(
        created_by=user.id,
        origin="MANUAL",
        source_name="PrevClima - central meteorológica",
        validation_status="ACTIVE",
        title=f"{kind['name']} – {area_name}"[:140],
        message=payload.message,
        event_type=payload.event_type,
        severity=kind["severity"],
        area_name=area_name,
        polygon=polygon,
        recommendations=kind["recommendations"],
        issued_at=issued,
        valid_until=payload.valid_until,
    )
    db.add(alert)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="PANEL_ALERT_CREATED",
        target_type="weather_alert",
        target_id=alert.id,
        details={"event_type": alert.event_type, "area_name": alert.area_name},
    )
    db.commit()
    db.refresh(alert)
    return alert_out(alert, {user.id: user.name})


# ----------------------------------------------------------------------------- previsões


def forecast_out(item: SevereForecast, names: dict[int, str]) -> ForecastOut:
    return ForecastOut(
        id=item.id,
        level=item.level,
        description=item.description,
        points=[list(point) for point in item.polygon["coordinates"][0][:-1]],
        issued_at=item.issued_at,
        valid_until=item.valid_until,
        created_at=item.created_at,
        created_by_name=names.get(item.created_by) if item.created_by else None,
        editable_until=as_utc(item.created_at) + EDIT_WINDOW,
    )


def list_forecasts(db: DbSession) -> list[ForecastOut]:
    items = list(
        db.scalars(
            select(SevereForecast)
            .where(SevereForecast.valid_until > now_utc())
            .order_by(SevereForecast.level, SevereForecast.id)
        )
    )
    names = names_by_id(db, {item.created_by for item in items if item.created_by})
    return [forecast_out(item, names) for item in items]


def check_forecast_dates(payload: ForecastIn) -> None:
    if payload.valid_until <= payload.issued_at:
        raise HTTPException(status_code=422, detail="O vencimento deve ser posterior à emissão")
    if payload.valid_until <= now_utc():
        raise HTTPException(status_code=422, detail="O vencimento deve ser uma data futura")


def editable_forecast(db: DbSession, forecast_id: int, expired_message: str) -> SevereForecast:
    item = db.get(SevereForecast, forecast_id)
    if not item:
        raise HTTPException(status_code=404, detail="Previsão não encontrada")
    if now_utc() > as_utc(item.created_at) + EDIT_WINDOW:
        raise HTTPException(status_code=409, detail=expired_message)
    return item


@router.post("/forecasts", response_model=ForecastOut, status_code=status.HTTP_201_CREATED)
def create_forecast(payload: ForecastIn, db: DbSession, user: Meteorologist):
    check_forecast_dates(payload)
    item = SevereForecast(
        level=payload.level,
        description=payload.description,
        polygon=closed_polygon(payload.points),
        issued_at=payload.issued_at,
        valid_until=payload.valid_until,
        created_by=user.id,
        created_at=utcnow(),
    )
    db.add(item)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="PANEL_FORECAST_CREATED",
        target_type="severe_forecast",
        target_id=item.id,
        details={"level": item.level},
    )
    db.commit()
    db.refresh(item)
    return forecast_out(item, {user.id: user.name})


@router.patch("/forecasts/{forecast_id}", response_model=ForecastOut)
def update_forecast(forecast_id: int, payload: ForecastIn, db: DbSession, user: Meteorologist):
    item = editable_forecast(db, forecast_id, EDIT_EXPIRED)
    check_forecast_dates(payload)
    item.level = payload.level
    item.description = payload.description
    item.polygon = closed_polygon(payload.points)
    item.issued_at = payload.issued_at
    item.valid_until = payload.valid_until
    record_audit(
        db,
        actor=user,
        action="PANEL_FORECAST_UPDATED",
        target_type="severe_forecast",
        target_id=item.id,
        details={"level": item.level},
    )
    db.commit()
    db.refresh(item)
    author = names_by_id(db, {item.created_by} if item.created_by else set())
    return forecast_out(item, author)


@router.delete("/forecasts/{forecast_id}", response_model=MessageOut)
def delete_forecast(forecast_id: int, db: DbSession, user: Meteorologist):
    item = editable_forecast(db, forecast_id, DELETE_EXPIRED)
    level = item.level
    db.delete(item)
    record_audit(
        db,
        actor=user,
        action="PANEL_FORECAST_DELETED",
        target_type="severe_forecast",
        target_id=forecast_id,
        details={"level": level},
    )
    db.commit()
    return MessageOut(message="Previsão excluída")


# ----------------------------------------------------------------------------- contas


def account_out(user: User) -> AccountOut:
    return AccountOut(
        id=user.id,
        public_code=user.public_code,
        name=user.name,
        email=user.email,
        role=user.role.code,
        city=user.city,
        state=user.state,
        created_at=user.created_at,
    )


def get_account(db: DbSession, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user


def get_role(db: DbSession, code: str) -> Role:
    role = db.scalar(select(Role).where(Role.code == code))
    if not role:
        raise HTTPException(status_code=503, detail="As funções de acesso não foram inicializadas")
    return role


@router.get("/accounts", response_model=list[AccountOut])
def search_accounts(
    db: DbSession,
    _: Meteorologist,
    search: str | None = Query(default=None, max_length=150),
    limit: int = Query(default=100, ge=1, le=200),
):
    query = select(User).where(User.is_active.is_(True)).order_by(User.name, User.id).limit(limit)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(User.name.ilike(term), User.email.ilike(term), User.public_code.ilike(term))
        )
    return [account_out(user) for user in db.scalars(query)]


@router.patch("/accounts/{user_id}", response_model=AccountOut)
def update_account(user_id: int, payload: AccountUpdate, db: DbSession, actor: Meteorologist):
    user = get_account(db, user_id)
    fields = payload.model_fields_set
    if any(getattr(payload, field) is None for field in fields):
        raise HTTPException(status_code=422, detail="Um ou mais campos em branco")
    if "role" in fields and payload.role != user.role.code:
        if user.id == actor.id:
            raise HTTPException(status_code=409, detail="Você não pode alterar a própria função")
        previous = user.role.code
        user.role_id = get_role(db, payload.role).id
        user.token_version += 1
        record_audit(
            db,
            actor=actor,
            action="USER_ROLE_CHANGED",
            target_type="user",
            target_id=user.id,
            details={"name": user.name, "previous_role": previous, "new_role": payload.role},
        )
    if "name" in fields:
        user.name = payload.name
    if "email" in fields:
        email = normalized_email(str(payload.email))
        if email != user.email and db.scalar(select(User.id).where(User.email == email)):
            db.rollback()
            raise HTTPException(
                status_code=409, detail="Uma ou mais informações congruentes a de outro usuário"
            )
        user.email = email
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Uma ou mais informações congruentes a de outro usuário"
        ) from error
    db.refresh(user)
    return account_out(user)


@router.delete("/accounts/{user_id}", response_model=MessageOut)
def deactivate_account(user_id: int, db: DbSession, actor: Meteorologist):
    user = get_account(db, user_id)
    if user.id == actor.id:
        raise HTTPException(status_code=409, detail="Você não pode desativar a própria conta")
    user.is_active = False
    user.token_version += 1
    record_audit(
        db,
        actor=actor,
        action="USER_DEACTIVATED",
        target_type="user",
        target_id=user.id,
        details={"name": user.name},
    )
    db.commit()
    return MessageOut(message="Conta desativada")


@router.post("/meteorologists", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def credential_meteorologist(payload: MeteorologistIn, db: DbSession, actor: Meteorologist):
    email = normalized_email(str(payload.email))
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado")
    user = User(
        public_code=new_public_code(db),
        name=payload.name,
        email=email,
        password_hash=hash_password(payload.password),
        role_id=get_role(db, "METEOROLOGIST").id,
        email_verified_at=utcnow(),
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="METEOROLOGIST_CREATED",
        target_type="user",
        target_id=user.id,
        details={"name": user.name},
    )
    db.commit()
    db.refresh(user)
    return account_out(user)


# ----------------------------------------------------------------------------- atividade


def describe(event: AuditEvent, actor: str) -> str:
    d = event.details or {}
    alert_name = ALERT_TYPES.get(d.get("event_type"), {}).get("name", "Alerta").lower()
    level = d.get("level")
    forecast = "tempestades não severas" if level == 0 else f"nível {level}"
    texts = {
        "PANEL_ALERT_CREATED": f"{actor} emitiu {alert_name} em {d.get('area_name', '')}",
        "PANEL_FORECAST_CREATED": f"{actor} emitiu previsão de {forecast}",
        "PANEL_FORECAST_UPDATED": f"{actor} editou uma previsão de {forecast}",
        "PANEL_FORECAST_DELETED": f"{actor} excluiu uma previsão de {forecast}",
        "METEOROLOGIST_CREATED": f"{actor} credenciou {d.get('name', 'um meteorologista')}",
        "USER_DEACTIVATED": f"{actor} desativou a conta de {d.get('name', 'um usuário')}",
        "USER_ROLE_CHANGED": f"{actor} alterou a função de {d.get('name', 'uma conta')}",
        "INMET_WARNINGS_SYNCED": "Avisos do INMET sincronizados",
        "INMET_WARNINGS_FAILED": "Consulta ao INMET indisponível",
        "INMET_STATIONS_SYNCED": "Catálogo de estações do INMET atualizado",
        "INMET_OBSERVATIONS_SYNCED": "Medições do INMET atualizadas",
        "BDMEP_IMPORTED": f"{actor} importou histórico BDMEP",
        "OWNER_CREATED": "Conta principal criada",
    }
    return texts.get(event.action, f"{actor}: {event.action.replace('_', ' ').lower()}")


def list_activity(db: DbSession) -> list[ActivityOut]:
    rows = db.execute(
        select(AuditEvent, User.name)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .order_by(desc(AuditEvent.created_at), desc(AuditEvent.id))
        .limit(30)
    )
    return [
        ActivityOut(text=describe(event, name or "Sistema"), created_at=event.created_at)
        for event, name in rows
    ]


# ----------------------------------------------------------------------------- estado completo


@router.get("/state", response_model=PanelStateOut)
def panel_state(db: DbSession, user: Meteorologist):
    return PanelStateOut(
        me=MeOut(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role.code,
            role_name=user.role.display_name,
            dark_theme=user.dark_theme,
        ),
        alerts=list_panel_alerts(db),
        forecasts=list_forecasts(db),
        activity=list_activity(db),
        stations_total=int(db.scalar(select(func.count()).select_from(WeatherStation)) or 0),
        today=today_br(),
        generated_at=now_utc(),
    )


# ----------------------------------------------------------------------------- INMET (cópia)

INMET_PREVMET = "https://apiprevmet3.inmet.gov.br/"
INMET_PATHS = re.compile(r"^(avisos/ativos|previsao/\d{7}|estacao/proxima/\d{7})$")
INMET_CACHE_SECONDS = 30 * 60
_inmet_cache: dict[str, tuple[float, bytes]] = {}


def fetch_prevmet(path: str) -> bytes:
    settings = get_settings()
    # Origem fixa e caminho validado: nunca repassa uma URL enviada pelo navegador.
    with httpx.Client(timeout=settings.inmet_timeout_seconds, follow_redirects=False) as client:
        with client.stream(
            "GET", INMET_PREVMET + path, headers={"User-Agent": settings.inmet_user_agent}
        ) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > settings.inmet_max_response_bytes:
                    raise ValueError("Resposta do INMET excede o limite configurado")
    json.loads(body)  # só repassa JSON válido
    return bytes(body)


@router.get("/inmet/{path:path}")
def inmet_copy(path: str, user: Meteorologist):
    """Cópia dos dados do INMET buscada pelo servidor.

    O navegador também consulta o INMET direto; esta rota cobre quando ele não consegue
    (bloqueio de CORS, rede da instituição etc.). O INMET recusa acessos de fora do Brasil,
    então ela só funciona com o servidor hospedado no país.
    """
    if not INMET_PATHS.fullmatch(path):
        raise HTTPException(status_code=404, detail="Recurso do INMET não permitido")
    cached = _inmet_cache.get(path)
    if cached and time.monotonic() - cached[0] < INMET_CACHE_SECONDS:
        body = cached[1]
    else:
        try:
            body = fetch_prevmet(path)
            _inmet_cache[path] = (time.monotonic(), body)
        except (httpx.HTTPError, ValueError) as error:
            if cached:
                body = cached[1]
            else:
                raise HTTPException(
                    status_code=502, detail="O INMET não respondeu ao servidor"
                ) from error
    return Response(content=body, media_type="application/json")
