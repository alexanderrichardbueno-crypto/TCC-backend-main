from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.inmet_sync import sync_inmet_warnings
from app.integrations.inmet import InmetClient, InmetError, parse_warning_feed
from app.integrations.open_meteo import OpenMeteoClient, OpenMeteoError
from app.models import AlertReview, AuditEvent, Role, User, WeatherAlert
from app.open_meteo_sync import get_open_meteo_or_fallback, refresh_open_meteo_forecast
from app.security import hash_password
from tests.conftest import csrf_headers


def add_user(db, *, email: str, role_code: str, public_code: str) -> User:
    role = db.scalar(select(Role).where(Role.code == role_code))
    user = User(
        public_code=public_code,
        name=f"Conta {role_code}",
        email=email,
        password_hash=hash_password("Senha123!"),
        role_id=role.id,
        email_verified_at=datetime.now(UTC),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_mobile_login_accepts_only_regular_users(registered_client: TestClient, db):
    add_user(
        db,
        email="meteorologista-mobile@exemplo.com",
        role_code="METEOROLOGIST",
        public_code="TEST-MOBILE-METEO",
    )
    denied = registered_client.post(
        "/api/v1/auth/login-mobile",
        json={"email": "meteorologista-mobile@exemplo.com", "password": "Senha123!"},
    )
    assert denied.status_code == 403
    allowed = registered_client.post(
        "/api/v1/auth/login-mobile",
        json={"email": "maria@exemplo.com", "password": "Senha123!"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["user"]["role"] == "USER"
    assert registered_client.get("/api/v1/auth/mobile-session").status_code == 200


def test_meteorologist_review_is_audited_and_hides_flagged_alert(client: TestClient, db):
    add_user(
        db,
        email="revisor@exemplo.com",
        role_code="METEOROLOGIST",
        public_code="TEST-REVIEWER",
    )
    assert (
        client.post(
            "/api/v1/auth/login-professional",
            json={"email": "revisor@exemplo.com", "password": "Senha123!"},
        ).status_code
        == 200
    )
    alert_id = client.get("/api/v1/alerts").json()[0]["id"]
    response = client.post(
        f"/api/v1/alerts/{alert_id}/review",
        headers=csrf_headers(client),
        json={
            "validation_status": "FALSE_ALARM",
            "reason": "O aviso foi conferido e nao corresponde ao evento observado.",
        },
    )
    assert response.status_code == 200
    assert response.json()["validation_status"] == "FALSE_ALARM"
    assert client.get("/api/v1/alerts").json() == []
    review_queue = client.get("/api/v1/alerts/review-queue")
    assert review_queue.status_code == 200
    assert review_queue.json()[0]["validation_status"] == "FALSE_ALARM"
    assert db.scalar(select(func.count(AlertReview.id))) == 1
    assert (
        db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.action == "ALERT_REVIEWED"))
        == 1
    )


def inmet_xml() -> bytes:
    now = datetime.now(UTC)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2"><channel><item>
      <guid>INMET-AVISO-123</guid><title>Aviso de tempestade</title>
      <cap:headline>Aviso detalhado de tempestade</cap:headline>
      <description>Chuva intensa e rajadas de vento.</description>
      <link>https://avisos.inmet.gov.br/123</link>
      <cap:event>Tempestade</cap:event><cap:severity>Severe</cap:severity>
      <cap:effective>{(now - timedelta(minutes=10)).isoformat()}</cap:effective>
      <cap:expires>{(now + timedelta(hours=2)).isoformat()}</cap:expires>
      <cap:areaDesc>Litoral de Sao Paulo</cap:areaDesc>
      <cap:polygon>-24.0,-46.8 -24.0,-46.2 -24.5,-46.2 -24.0,-46.8</cap:polygon>
      <cap:instruction>Procure abrigo seguro.</cap:instruction>
    </item></channel></rss>""".encode()


def test_inmet_parser_and_sync_are_safe_attributed_and_idempotent(db):
    parsed = parse_warning_feed(
        inmet_xml(), source_url="https://apiprevmet3.inmet.gov.br/avisos/rss"
    )
    assert parsed[0].severity == "HIGH"
    assert parsed[0].title == "Aviso detalhado de tempestade"
    assert parsed[0].polygon["type"] == "Polygon"

    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=inmet_xml()))
    settings = Settings(inmet_enabled=True)
    client = InmetClient(settings, transport=transport)
    assert sync_inmet_warnings(db, actor=None, client=client) == (1, 0)
    assert sync_inmet_warnings(db, actor=None, client=client) == (0, 1)
    warning = db.scalar(select(WeatherAlert).where(WeatherAlert.origin == "INMET"))
    assert warning.source_name == "Instituto Nacional de Meteorologia (INMET)"
    assert warning.source_url == "https://avisos.inmet.gov.br/123"
    assert warning.validation_status == "ACTIVE"

    cancellation = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2"><channel><item>
      <guid>INMET-CANCEL-456</guid>
      <cap:msgType>Cancel</cap:msgType>
      <cap:references>inmet.gov.br,INMET-AVISO-123,2026-09-21T10:00:00Z</cap:references>
    </item></channel></rss>"""
    cancel_transport = httpx.MockTransport(lambda _: httpx.Response(200, content=cancellation))
    cancel_client = InmetClient(settings, transport=cancel_transport)
    assert sync_inmet_warnings(db, actor=None, client=cancel_client) == (0, 1)
    db.refresh(warning)
    assert warning.validation_status == "FALSE_ALARM"


def test_inmet_update_only_supersedes_after_replacement_is_importable(db):
    settings = Settings(inmet_enabled=True)
    original_client = InmetClient(
        settings,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=inmet_xml())),
    )
    assert sync_inmet_warnings(db, actor=None, client=original_client) == (1, 0)
    original = db.scalar(select(WeatherAlert).where(WeatherAlert.origin == "INMET"))

    now = datetime.now(UTC)

    def update_xml(*, complete: bool) -> bytes:
        severity_node = "<cap:severity>Severe</cap:severity>" if complete else ""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2"><channel><item>
          <guid>INMET-AVISO-ATUALIZADO-456</guid>
          <title>Aviso atualizado</title><description>Área atualizada pelo INMET.</description>
          <cap:msgType>Update</cap:msgType>
          <cap:references>inmet.gov.br,INMET-AVISO-123,2026-09-21T10:00:00Z</cap:references>
          <cap:event>Tempestade</cap:event>{severity_node}
          <cap:effective>{now.isoformat()}</cap:effective>
          <cap:expires>{(now + timedelta(hours=3)).isoformat()}</cap:expires>
          <cap:areaDesc>Litoral atualizado</cap:areaDesc>
        </item></channel></rss>""".encode()

    incomplete_client = InmetClient(
        settings,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=update_xml(complete=False))
        ),
    )
    with pytest.raises(InmetError):
        sync_inmet_warnings(db, actor=None, client=incomplete_client)
    db.refresh(original)
    assert original.validation_status == "ACTIVE"

    # A valid official UPDATE can omit geometry; it remains a text-only alert.
    complete_client = InmetClient(
        settings,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=update_xml(complete=True))
        ),
    )
    assert sync_inmet_warnings(db, actor=None, client=complete_client) == (1, 0)
    db.refresh(original)
    assert original.validation_status == "NEEDS_CORRECTION"
    active = db.scalar(
        select(WeatherAlert).where(
            WeatherAlert.source_key != original.source_key,
            WeatherAlert.origin == "INMET",
            WeatherAlert.validation_status == "ACTIVE",
        )
    )
    assert active is not None
    assert active.polygon is None
    assert active.latitude is None and active.longitude is None
    assert sync_inmet_warnings(db, actor=None, client=complete_client) == (0, 1)


def test_inmet_client_rejects_malformed_xml_and_untrusted_url():
    malformed = httpx.MockTransport(lambda _: httpx.Response(200, content=b"<rss>"))
    with pytest.raises(InmetError):
        InmetClient(Settings(inmet_enabled=True), transport=malformed).fetch_warnings()
    with pytest.raises(InmetError):
        InmetClient(
            Settings(inmet_enabled=True, inmet_warning_rss_url="https://exemplo.com/rss")
        ).fetch_warnings()
    oversized = httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 64))
    with pytest.raises(InmetError):
        InmetClient(
            Settings(inmet_enabled=True, inmet_max_response_bytes=32),
            transport=oversized,
        ).fetch_warnings()
    unavailable = httpx.MockTransport(lambda _: httpx.Response(429))
    with pytest.raises(InmetError):
        InmetClient(Settings(inmet_enabled=True), transport=unavailable).fetch_warnings()


def open_meteo_payload(now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    return {
        "current": {
            "time": int(now.timestamp()),
            "temperature_2m": 24.2,
            "relative_humidity_2m": 71,
            "weather_code": 95,
            "wind_speed_10m": 18.4,
        },
        "daily": {
            "temperature_2m_min": [19.1, 18.8],
            "temperature_2m_max": [27.3, 26.0],
            "precipitation_probability_max": [86, 62],
            "wind_gusts_10m_max": [74.0, 52.0],
        },
    }


def test_open_meteo_geocodes_persists_and_reuses_fresh_cache(db):
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.host)
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "country_code": "BR",
                            "admin1": "São Paulo",
                            "latitude": -24.10,
                            "longitude": -46.62,
                        }
                    ]
                },
            )
        return httpx.Response(200, json=open_meteo_payload())

    settings = Settings(open_meteo_enabled=True, open_meteo_cache_minutes=15)
    client = OpenMeteoClient(settings, transport=httpx.MockTransport(handler))
    forecast = refresh_open_meteo_forecast(
        db,
        city="Mongaguá",
        state="SP",
        client=client,
    )
    assert forecast.source_name == "Open-Meteo"
    assert forecast.source_url == "https://open-meteo.com/"
    assert forecast.condition == "Tempestade"
    assert forecast.rain_probability == 86
    assert forecast.severity == "HIGH"
    assert requests == ["geocoding-api.open-meteo.com", "api.open-meteo.com"]

    cached, is_stale = get_open_meteo_or_fallback(
        db,
        city="Mongaguá",
        state="SP",
        settings=settings,
        client=client,
    )
    assert cached.id == forecast.id
    assert is_stale is False
    assert requests == ["geocoding-api.open-meteo.com", "api.open-meteo.com"]


def test_open_meteo_uses_recent_saved_data_when_provider_fails(db):
    settings = Settings(open_meteo_enabled=True, open_meteo_cache_minutes=15)
    good_client = OpenMeteoClient(
        settings,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=open_meteo_payload())),
    )
    forecast = refresh_open_meteo_forecast(
        db,
        city="Santos",
        state="SP",
        latitude=-23.96,
        longitude=-46.33,
        client=good_client,
    )
    forecast.issued_at = datetime.now(UTC) - timedelta(minutes=15)
    forecast.valid_until = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    unavailable = OpenMeteoClient(
        settings,
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
    )
    cached, is_stale = get_open_meteo_or_fallback(
        db,
        city="Santos",
        state="SP",
        latitude=-23.96,
        longitude=-46.33,
        settings=settings,
        client=unavailable,
    )
    assert cached.id == forecast.id
    assert is_stale is True


def test_open_meteo_rejects_untrusted_url_and_invalid_payload():
    with pytest.raises(OpenMeteoError, match="não é permitida"):
        OpenMeteoClient(
            Settings(
                open_meteo_enabled=True,
                open_meteo_api_url="https://exemplo.com/forecast",
            ),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=open_meteo_payload())),
        ).fetch_forecast(-23.55, -46.63)

    malformed = OpenMeteoClient(
        Settings(open_meteo_enabled=True),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"current": {}})),
    )
    with pytest.raises(OpenMeteoError, match="previsão incompleta"):
        malformed.fetch_forecast(-23.55, -46.63)


def test_native_app_uses_bearer_token_without_cookies(registered_client: TestClient):
    login = registered_client.post(
        "/api/v1/auth/login-mobile",
        json={"email": "maria@exemplo.com", "password": "Senha123!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert token
    registered_client.cookies.clear()
    headers = {"Authorization": f"Bearer {token}"}
    assert registered_client.get("/api/v1/auth/mobile-session", headers=headers).status_code == 200
    updated = registered_client.patch(
        "/api/v1/users/me", json={"dark_theme": False}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["dark_theme"] is False
    # O login do site continua sem expor o token no corpo da resposta.
    web = registered_client.post(
        "/api/v1/auth/login",
        json={"email": "maria@exemplo.com", "password": "Senha123!"},
    )
    assert web.json()["access_token"] is None


def test_mobile_pages_exist_and_mobile_login_blocks_admin(client: TestClient, db):
    admin = add_user(
        db,
        email="admin-mobile@exemplo.com",
        role_code="METEOROLOGIST",
        public_code="TEST-METEO-MOBILE",
    )
    assert admin.role.code == "METEOROLOGIST"
    assert client.get("/mobile/").status_code == 200
    assert client.get("/mobile/inicio.html").status_code == 200
    denied = client.post(
        "/api/v1/auth/login-mobile",
        json={"email": "admin-mobile@exemplo.com", "password": "Senha123!"},
    )
    assert denied.status_code == 403
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "admin-mobile@exemplo.com", "password": "Senha123!"},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/mobile-session").status_code == 403
