from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import EducationalContent, Forecast, Role, WeatherAlert


@pytest.fixture()
def db(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "open_meteo_enabled", False)
    monkeypatch.setattr(get_settings(), "inmet_enabled", False)
    monkeypatch.setattr(get_settings(), "inmet_observations_enabled", False)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        session.add_all(
            [
                Role(code="USER", display_name="Usuário"),
                Role(code="METEOROLOGIST", display_name="Meteorologista"),
            ]
        )
        now = datetime.now(UTC)
        session.add(
            Forecast(
                source_key="TEST-FORECAST",
                city="Mongagua",
                state="SP",
                condition="Parcialmente nublado",
                temperature_c=Decimal("23"),
                minimum_c=Decimal("18"),
                maximum_c=Decimal("26"),
                humidity=68,
                wind_kmh=Decimal("14"),
                rain_probability=73,
                severity="HIGH",
                polygon={
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-47.0, -24.5],
                            [-46.0, -24.5],
                            [-46.0, -23.5],
                            [-47.0, -23.5],
                            [-47.0, -24.5],
                        ]
                    ],
                },
                source_name="TEST DATA",
                issued_at=now - timedelta(minutes=10),
                valid_until=now + timedelta(hours=6),
            )
        )
        session.add(
            WeatherAlert(
                source_key="TEST-ALERT",
                title="Tempestade severa",
                message="Ventos fortes nas proximas horas.",
                event_type="SEVERE_STORM",
                severity="CRITICAL",
                area_name="Baixada Santista",
                latitude=Decimal("-24.1008"),
                longitude=Decimal("-46.6200"),
                radius_km=Decimal("30"),
                recommendations=["Procure abrigo"],
                issued_at=now - timedelta(minutes=15),
                valid_until=now + timedelta(hours=3),
            )
        )
        session.add_all(
            [
                EducationalContent(
                    source_key="TEST-EDU-PUBLISHED",
                    title="Seguranca em tempestades",
                    body="Procure abrigo seguro e acompanhe os alertas oficiais.",
                    reference_url="https://exemplo.com/seguranca",
                    published_at=now - timedelta(hours=1),
                ),
                EducationalContent(
                    source_key="TEST-EDU-FUTURE",
                    title="Conteudo agendado",
                    body="Este conteudo ainda nao deve aparecer na pagina publica.",
                    reference_url="https://exemplo.com/futuro",
                    published_at=now + timedelta(days=1),
                ),
            ]
        )
        session.commit()

        def override_db():
            yield session

        app.dependency_overrides[get_db] = override_db
        yield session
        app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def client(db: Session):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def registered_client(client: TestClient, monkeypatch):
    sent = capture_mail(monkeypatch)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Maria Teste",
            "email": "maria@exemplo.com",
            "password": "Senha123!",
            "city": "Mongagua",
            "state": "SP",
        },
    )
    assert response.status_code == 201
    verify_email(client, sent)
    return client


def capture_mail(monkeypatch) -> list[tuple[str, str]]:
    from app import account_codes

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        account_codes, "deliver", lambda to, _subject, body: sent.append((to, body))
    )
    return sent


def verify_email(client: TestClient, sent: list[tuple[str, str]]) -> None:
    email, body = sent[-1]
    code = body.split("é ")[1].split(".")[0]
    response = client.post("/api/v1/auth/verify-email", json={"email": email, "code": code})
    assert response.status_code == 200


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("prevclima_csrf")}
