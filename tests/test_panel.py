"""Regras do documento do projeto: casos de uso UC001 a UC008 e nível de acesso único."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import account_codes
from app.main import app
from app.models import AccountCode, Role, SevereForecast, User, WeatherAlert
from app.security import hash_password

PASSWORD = "Senha@1"
AREA = [[-46.8, -24.3], [-46.2, -24.3], [-46.2, -23.8]]


@pytest.fixture
def mail(monkeypatch):
    sent = []
    monkeypatch.setattr(
        account_codes, "deliver", lambda to, subject, body: sent.append((to, subject, body))
    )
    return sent


def code_from(mail):
    return mail[-1][2].split("é ")[1].split(".")[0]


def make_user(db, email, role="METEOROLOGIST", name="Conta Teste"):
    role_id = db.scalar(select(Role.id).where(Role.code == role))
    user = User(
        public_code=f"PVC-{abs(hash(email)) % 10**8:08d}",
        name=name,
        email=email,
        password_hash=hash_password(PASSWORD),
        role_id=role_id,
        email_verified_at=datetime.now(UTC),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(db, email="meteo@teste.com"):
    make_user(db, email)
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login-professional", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies["prevclima_csrf"]
    return client


def future(hours=3):
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def forecast_body(**changes):
    body = {
        "level": 2,
        "issued_at": datetime.now(UTC).isoformat(),
        "valid_until": future(),
        "description": "Risco de tempestades severas no litoral.",
        "points": AREA,
    }
    return {**body, **changes}


def test_only_two_access_levels(db):
    assert set(db.scalars(select(Role.code))) == {"USER", "METEOROLOGIST"}


def test_register_requires_email_confirmation(db, mail):
    client = TestClient(app)
    data = {"name": "Maria", "email": "maria@teste.com", "password": PASSWORD}
    response = client.post("/api/v1/auth/register", json=data)
    assert response.status_code == 201
    assert "prevclima_access" not in client.cookies
    credentials = {"email": data["email"], "password": PASSWORD}
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 403
    verified = client.post(
        "/api/v1/auth/verify-email", json={"email": data["email"], "code": code_from(mail)}
    )
    assert verified.status_code == 200
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 200


def test_wrong_code_is_rejected_and_attempts_are_limited(db, mail):
    client = TestClient(app)
    email = "tentativas@teste.com"
    client.post("/api/v1/auth/register", json={"name": "Ana", "email": email, "password": PASSWORD})
    right = code_from(mail)
    wrong = "000000" if right != "000000" else "111111"
    for _ in range(5):
        response = client.post("/api/v1/auth/verify-email", json={"email": email, "code": wrong})
        assert response.status_code == 400
    response = client.post("/api/v1/auth/verify-email", json={"email": email, "code": right})
    assert response.status_code == 400


@pytest.mark.parametrize("password", ["Ab@1", "semmaiuscula@1", "SemEspecial1"])
def test_password_policy(db, mail, password):
    response = TestClient(app).post(
        "/api/v1/auth/register", json={"name": "Ana", "email": "a@teste.com", "password": password}
    )
    assert response.status_code == 422


def test_forgot_password_flow(db, mail):
    make_user(db, "esqueci@teste.com", role="USER")
    client = TestClient(app)
    assert (
        client.post("/api/v1/auth/forgot-password", json={"email": "esqueci@teste.com"}).status_code
        == 200
    )
    response = client.post(
        "/api/v1/auth/reset-password",
        json={"email": "esqueci@teste.com", "code": code_from(mail), "password": "Nova#1"},
    )
    assert response.status_code == 200
    login_data = {"email": "esqueci@teste.com", "password": "Nova#1"}
    assert client.post("/api/v1/auth/login", json=login_data).status_code == 200
    assert db.scalar(select(AccountCode)) is None


def test_forgot_password_does_not_reveal_accounts(db, mail):
    response = TestClient(app).post(
        "/api/v1/auth/forgot-password", json={"email": "ninguem@teste.com"}
    )
    assert response.status_code == 200
    assert mail == []


def test_common_user_cannot_use_the_panel(db):
    make_user(db, "comum@teste.com", role="USER")
    client = TestClient(app)
    client.post("/api/v1/auth/login", json={"email": "comum@teste.com", "password": PASSWORD})
    client.headers["X-CSRF-Token"] = client.cookies["prevclima_csrf"]
    assert client.get("/api/v1/panel/state").status_code == 403
    assert client.post("/api/v1/panel/forecasts", json=forecast_body()).status_code == 403


def test_forecast_is_public_and_editable_for_30_minutes(db):
    client = login(db)
    created = client.post("/api/v1/panel/forecasts", json=forecast_body())
    assert created.status_code == 201
    forecast_id = created.json()["id"]
    areas = TestClient(app).get("/api/v1/map-data").json()["published_areas"]
    assert areas[0]["properties"]["descricao"] == "Risco de tempestades severas no litoral."
    assert areas[0]["properties"]["nivel"] == 2
    updated = client.patch(f"/api/v1/panel/forecasts/{forecast_id}", json=forecast_body(level=3))
    assert updated.status_code == 200
    assert updated.json()["level"] == 3


def test_forecast_locks_after_30_minutes(db):
    client = login(db)
    forecast_id = client.post("/api/v1/panel/forecasts", json=forecast_body()).json()["id"]
    item = db.get(SevereForecast, forecast_id)
    item.created_at = datetime.now(UTC) - timedelta(minutes=31)
    db.commit()
    response = client.patch(f"/api/v1/panel/forecasts/{forecast_id}", json=forecast_body())
    assert response.status_code == 409
    assert response.json()["detail"].startswith("Já se passou 30 minutos")
    assert client.delete(f"/api/v1/panel/forecasts/{forecast_id}").status_code == 409


def test_forecast_can_be_deleted_inside_the_window(db):
    client = login(db)
    forecast_id = client.post("/api/v1/panel/forecasts", json=forecast_body()).json()["id"]
    assert client.delete(f"/api/v1/panel/forecasts/{forecast_id}").status_code == 200
    assert TestClient(app).get("/api/v1/map-data").json()["published_areas"] == []


def test_forecast_requires_all_fields(db):
    client = login(db)
    body = forecast_body()
    del body["description"]
    assert client.post("/api/v1/panel/forecasts", json=body).status_code == 422
    blank = forecast_body(description="   ")
    assert client.post("/api/v1/panel/forecasts", json=blank).status_code == 422


@pytest.mark.parametrize(
    ("event_type", "severity"), [("SEVERE_STORM", "HIGH"), ("TORNADO", "CRITICAL")]
)
def test_alert_uses_predefined_instructions(db, event_type, severity):
    client = login(db)
    response = client.post(
        "/api/v1/panel/alerts",
        json={
            "event_type": event_type,
            "valid_until": future(),
            "message": "Tempestade com sinais de severidade.",
            "points": AREA,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["severity"] == severity
    assert data["area_name"] == "Baixada Santista"
    assert len(data["recommendations"]) == 4
    assert data["id"] in [a["id"] for a in TestClient(app).get("/api/v1/alerts").json()]


def test_alert_only_accepts_the_two_document_types(db):
    client = login(db)
    response = client.post(
        "/api/v1/panel/alerts",
        json={"event_type": "HAIL", "valid_until": future(), "message": "x", "points": AREA},
    )
    assert response.status_code == 422


def test_alert_cannot_be_edited_or_deleted(db):
    client = login(db)
    alert_id = client.post(
        "/api/v1/panel/alerts",
        json={"event_type": "TORNADO", "valid_until": future(), "message": "Risco", "points": AREA},
    ).json()["id"]
    assert client.patch(f"/api/v1/panel/alerts/{alert_id}", json={}).status_code == 405
    assert client.delete(f"/api/v1/panel/alerts/{alert_id}").status_code == 405


def test_any_meteorologist_manages_accounts(db):
    client = login(db)
    other = make_user(db, "busca@teste.com", role="USER", name="Fulana Busca")
    found = client.get("/api/v1/panel/accounts", params={"search": other.public_code}).json()
    assert [item["id"] for item in found] == [other.id]
    assert client.get("/api/v1/panel/accounts", params={"search": "inexistente"}).json() == []
    promoted = client.patch(f"/api/v1/panel/accounts/{other.id}", json={"role": "METEOROLOGIST"})
    assert promoted.json()["role"] == "METEOROLOGIST"
    demoted = client.patch(f"/api/v1/panel/accounts/{other.id}", json={"role": "USER"})
    assert demoted.json()["role"] == "USER"
    assert client.delete(f"/api/v1/panel/accounts/{other.id}").status_code == 200
    assert client.get("/api/v1/panel/accounts", params={"search": "busca@"}).json() == []


def test_account_edit_rejects_duplicates_and_self_changes(db):
    client = login(db)
    me = db.scalar(select(User).where(User.email == "meteo@teste.com"))
    other = make_user(db, "outro@teste.com", role="USER")
    response = client.patch(f"/api/v1/panel/accounts/{other.id}", json={"email": "meteo@teste.com"})
    assert response.status_code == 409
    assert client.patch(f"/api/v1/panel/accounts/{me.id}", json={"role": "USER"}).status_code == 409
    assert client.delete(f"/api/v1/panel/accounts/{me.id}").status_code == 409


def test_meteorologist_is_credentialed_with_temporary_password(db):
    client = login(db)
    response = client.post(
        "/api/v1/panel/meteorologists",
        json={"name": "Nova Meteo", "email": "nova@teste.com", "password": "Temp@1"},
    )
    assert response.status_code == 201
    new_client = TestClient(app)
    entered = new_client.post(
        "/api/v1/auth/login-professional", json={"email": "nova@teste.com", "password": "Temp@1"}
    )
    assert entered.status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/reports"),
        ("get", "/api/v1/reports/me"),
        ("post", "/api/v1/panel/notifications"),
        ("get", "/api/v1/admin/users"),
    ],
)
def test_removed_features_do_not_exist(db, method, path):
    client = login(db)
    assert getattr(client, method)(path).status_code in {404, 405}


def test_panel_state_has_no_reports_or_push(db):
    state = login(db).get("/api/v1/panel/state").json()
    assert "reports" not in state
    assert "notifications" not in state
    assert state["me"]["role_name"] == "Meteorologista"


def test_token_login_is_only_for_meteorologists(db):
    make_user(db, "token@teste.com")
    make_user(db, "comum2@teste.com", role="USER")
    client = TestClient(app)
    data = {"email": "token@teste.com", "password": PASSWORD}
    token = client.post("/api/v1/auth/login-token", json=data).json()["access_token"]
    assert "prevclima_access" not in client.cookies
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/panel/state", headers=headers).status_code == 200
    data = {"email": "comum2@teste.com", "password": PASSWORD}
    assert client.post("/api/v1/auth/login-token", json=data).status_code == 403


def test_single_login_identifies_the_access_level(db):
    client = TestClient(app)
    home = client.get("/")
    assert 'id="login-form"' in home.text
    assert "role-switch" not in home.text
    assert "login-token" in client.get("/painel.html").text
    make_user(db, "auto@teste.com")
    user = client.post("/api/v1/auth/login", json={"email": "auto@teste.com", "password": PASSWORD})
    assert user.json()["user"]["role"] == "METEOROLOGIST"
    headers = {"X-CSRF-Token": client.cookies["prevclima_csrf"]}
    session = client.post("/api/v1/auth/session-token", headers=headers)
    assert session.status_code == 200
    bearer = TestClient(app)
    auth = {"Authorization": f"Bearer {session.json()['access_token']}"}
    assert bearer.get("/api/v1/panel/state", headers=auth).status_code == 200


def test_common_user_gets_no_panel_token(db):
    make_user(db, "auto2@teste.com", role="USER")
    client = TestClient(app)
    client.post("/api/v1/auth/login", json={"email": "auto2@teste.com", "password": PASSWORD})
    headers = {"X-CSRF-Token": client.cookies["prevclima_csrf"]}
    assert client.post("/api/v1/auth/session-token", headers=headers).status_code == 403


def test_expo_app_accepts_users_and_meteorologists(db):
    make_user(db, "app.meteo@teste.com")
    make_user(db, "app.user@teste.com", role="USER")
    client = TestClient(app)
    for email, role in (("app.meteo@teste.com", "METEOROLOGIST"), ("app.user@teste.com", "USER")):
        response = client.post(
            "/api/v1/auth/login-app", json={"email": email, "password": PASSWORD}
        )
        assert response.status_code == 200
        assert response.json()["user"]["role"] == role
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
        assert client.get("/api/v1/home", headers=headers).status_code == 200
    assert "prevclima_access" not in client.cookies
    # O aplicativo web instalável continua exclusivo para contas de usuário.
    data = {"email": "app.meteo@teste.com", "password": PASSWORD}
    assert client.post("/api/v1/auth/login-mobile", json=data).status_code == 403


def test_map_sends_upcoming_inmet_warnings_separately(db):
    now = datetime.now(UTC)
    polygon = {"type": "Polygon", "coordinates": [AREA + [AREA[0]]]}
    db.add(
        WeatherAlert(
            source_key="INMET-FUTURO",
            origin="INMET",
            source_name="INMET",
            title="Aviso futuro",
            message="Aviso para amanhã.",
            event_type="HEAVY_RAIN",
            severity="HIGH",
            area_name="Litoral",
            polygon=polygon,
            recommendations=["Atenção"],
            issued_at=now + timedelta(days=1),
            valid_until=now + timedelta(days=2),
        )
    )
    db.commit()
    data = TestClient(app).get("/api/v1/map-data").json()
    assert [item["title"] for item in data["upcoming_alerts"]] == ["Aviso futuro"]
    assert "Aviso futuro" not in [item["title"] for item in data["alerts"]]
