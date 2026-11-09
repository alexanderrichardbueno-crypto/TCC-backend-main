import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.integrations import stations
from app.integrations.inmet import InmetError
from app.station_models import StationObservation, WeatherStation
from tests.conftest import csrf_headers
from tests.test_backend_workflow import add_user

CSV = (
    "CodigoOMM;NomeEstacao;Estado;Latitude;Longitude;Estacao;Data;Hora;TempBulboSeco;"
    "TempMaxima;TempMinima;UmidadeRelativa;Precipitacao;Velocidade do Vento Media\n"
    "82989;AGUA BRANCA;AL;-9.28;-37.9;82989;01/01/2018;0000;26,1;30;22;72;0;4.1\n"
)


@pytest.fixture()
def operator(client, db):
    add_user(db, email="station@exemplo.com", role_code="METEOROLOGIST", public_code="STATION-OP")
    response = client.post(
        "/api/v1/auth/login-professional",
        json={
            "email": "station@exemplo.com",
            "password": "Senha123!",
        },
    )
    assert response.status_code == 200
    return client


def test_import_csv_idempotency_periods_and_utc(operator, db):
    payload = {"format": "temperature-csv", "period": "HOURLY", "content": CSV}
    response = operator.post(
        "/api/v1/stations/import", json=payload, headers=csrf_headers(operator)
    )
    assert response.status_code == 200
    assert response.json() == {"inserted": 1, "updated": 0, "skipped": 0}
    second = operator.post("/api/v1/stations/import", json=payload, headers=csrf_headers(operator))
    assert second.json()["updated"] == 1
    assert db.scalar(select(func.count()).select_from(StationObservation)) == 1
    assert operator.get("/api/v1/stations?state=AL").json()[0]["code"] == "82989"
    measurement = operator.get("/api/v1/stations/82989/observations").json()[0]
    assert measurement["observed_at"] == "2018-01-01T00:00:00Z"
    assert measurement["source"] == "BDMEP"
    assert Decimal(measurement["temperature_c"]) == Decimal("26.1")
    payload["period"] = "MONTHLY"
    assert (
        operator.post(
            "/api/v1/stations/import", json=payload, headers=csrf_headers(operator)
        ).status_code
        == 200
    )
    assert db.scalar(select(func.count()).select_from(StationObservation)) == 2
    assert len(operator.get("/api/v1/stations/82989/observations?period=MONTHLY").json()) == 1


def test_rest_json_and_missing_measurements():
    data = [
        {
            "Estacao": "82989",
            "Data": "01/01/2018",
            "Hora": "1200",
            "TempMinima": "-9999",
            "UmidadeRelativa": "120",
            "Precipitacao": "0",
        },
        {"Data": "bad"},
    ]
    rows, skipped = stations.parse_import(json.dumps(data), "rest-json", "DAILY")
    assert skipped == 1
    assert rows[0][1]["minimum_c"] is None
    assert rows[0][1]["humidity"] is None
    assert rows[0][1]["precipitation_mm"] == 0
    assert rows[0][0]["latitude"] is None


def test_live_normalization_and_malformed_time():
    row = {
        "CD_ESTACAO": "A001",
        "DT_MEDICAO": "2025-01-01",
        "HR_MEDICAO": "1200",
        "TEM_INS": "27.4",
        "UMD_INS": "54",
        "VEN_VEL": "2.3",
    }
    _, data = stations.observation(row)
    assert data["temperature_c"] == Decimal("27.4")
    assert data["humidity"] == 54
    assert data["wind_ms"] == Decimal("2.3")
    with pytest.raises(ValueError):
        stations.observation({**row, "HR_MEDICAO": "2560"})
    for value in ("NaN", "Infinity", "-9999", ""):
        assert stations.number(value) is None


def test_permissions_and_invalid_import(registered_client, client, operator):
    # The operator fixture changes this shared client's session; explicitly log out.
    client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert client.post("/api/v1/stations/sync-catalog").status_code == 401
    client.post("/api/v1/auth/login", json={"email": "maria@exemplo.com", "password": "Senha123!"})
    assert (
        client.post("/api/v1/stations/sync-catalog", headers=csrf_headers(client)).status_code
        == 403
    )
    assert client.get("/api/v1/dashboard").status_code == 403


def test_catalog_sync_and_outage_preserves_data(operator, db, monkeypatch):
    monkeypatch.setattr(
        "app.routers.stations.fetch_json",
        lambda _: [
            {
                "CD_ESTACAO": "A001",
                "DC_NOME": "BRASILIA",
                "SG_ESTADO": "DF",
                "VL_LATITUDE": "-15.7",
                "VL_LONGITUDE": "-47.9",
            }
        ],
    )
    response = operator.post("/api/v1/stations/sync-catalog", headers=csrf_headers(operator))
    assert response.json()["imported"] == 1

    def unavailable(*args):
        raise InmetError("INMET indisponível")

    monkeypatch.setattr("app.routers.stations.fetch_observations", unavailable)
    response = operator.post("/api/v1/stations/A001/sync", json={}, headers=csrf_headers(operator))
    assert response.status_code == 503
    assert db.get(WeatherStation, "A001").name == "BRASILIA"
    invalid = operator.post(
        "/api/v1/stations/A001/sync",
        json={"start": "2020-01-01", "end": "2025-01-01"},
        headers=csrf_headers(operator),
    )
    assert invalid.status_code == 422
    invalid = operator.post(
        "/api/v1/stations/import",
        json={"format": "rest-json", "period": "DAILY", "content": "{}"},
        headers=csrf_headers(operator),
    )
    assert invalid.status_code == 422
    assert operator.get("/api/v1/dashboard").json()["stations"] == 1


def test_json_client_limits_redirects_and_bad_responses(monkeypatch):
    settings = Settings(inmet_observations_enabled=True, inmet_max_response_bytes=1024)
    monkeypatch.setattr(stations, "get_settings", lambda: settings)
    real_client = httpx.Client
    for response in (
        httpx.Response(302, headers={"location": "https://example.com"}),
        httpx.Response(200, text="x" * 1025),
        httpx.Response(200, json={"error": "bad"}),
    ):
        monkeypatch.setattr(
            stations.httpx,
            "Client",
            lambda **kwargs: real_client(
                transport=httpx.MockTransport(lambda request: response), **kwargs
            ),
        )
        with pytest.raises(InmetError):
            stations.fetch_json("estacoes/T")


CATALOG_ROW = {
    "CD_ESTACAO": "A771",
    "DC_NOME": "INTERLAGOS",
    "SG_ESTADO": "SP",
    "CD_WSI": "0-76-0-3550308000000001",
}


def latest_row(code="A771"):
    day = datetime.now(UTC).date().isoformat()
    return {"CD_ESTACAO": code, "DT_MEDICAO": day, "HR_MEDICAO": "0000", "TEM_INS": "21.5"}


@pytest.fixture()
def fresh_attempts(monkeypatch):
    monkeypatch.setattr("app.routers.stations._last_attempt", {})


def test_empty_catalog_loads_for_visitors_and_keeps_geocode(
    client, db, monkeypatch, fresh_attempts
):
    monkeypatch.setattr("app.routers.stations.fetch_json", lambda _: [CATALOG_ROW, {"bad": 1}])
    response = client.get("/api/v1/stations")
    assert [item["code"] for item in response.json()] == ["A771"]
    assert db.get(WeatherStation, "A771").geocode == "3550308"


def test_empty_catalog_survives_inmet_outage(client, db, monkeypatch, fresh_attempts):
    def unavailable(_):
        raise InmetError("INMET indisponível")

    monkeypatch.setattr("app.routers.stations.fetch_json", unavailable)
    response = client.get("/api/v1/stations")
    assert response.status_code == 200
    assert response.json() == []


def test_opening_station_fetches_latest_once(client, db, monkeypatch, fresh_attempts):
    db.add(WeatherStation(code="A771", name="Interlagos", kind="AUTOMATIC", geocode="3550308"))
    db.commit()
    calls = []

    def latest(geocode):
        calls.append(geocode)
        return latest_row()

    monkeypatch.setattr("app.station_sync.fetch_latest", latest)
    first = client.get("/api/v1/stations/A771/observations").json()
    client.get("/api/v1/stations/A771/observations")
    assert Decimal(first[0]["temperature_c"]) == Decimal("21.5")
    assert first[0]["source"] == "INMET"
    assert calls == ["3550308"]


def test_latest_from_another_station_is_not_attributed(client, db, monkeypatch, fresh_attempts):
    db.add(WeatherStation(code="A771", name="Interlagos", kind="AUTOMATIC", geocode="3550308"))
    db.commit()
    monkeypatch.setattr("app.station_sync.fetch_latest", lambda _: latest_row("A999"))
    assert client.get("/api/v1/stations/A771/observations").json() == []
    assert db.get(WeatherStation, "A999") is None


def test_empty_answer_is_not_an_outage(monkeypatch):
    settings = Settings(inmet_observations_enabled=True)
    monkeypatch.setattr(stations, "get_settings", lambda: settings)
    real_client = httpx.Client
    monkeypatch.setattr(
        stations.httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(204)), **kwargs
        ),
    )
    assert stations.fetch_json("estacao/2026-01-01/2026-01-01/A001") == []


def test_observation_sync_skips_wrong_station(operator, db, monkeypatch):
    db.add(WeatherStation(code="A001", name="Brasília", kind="AUTOMATIC"))
    db.commit()
    day = datetime.now(UTC).date().isoformat()
    monkeypatch.setattr(
        "app.routers.stations.fetch_observations",
        lambda *args: [
            {"CD_ESTACAO": "A002", "DT_MEDICAO": day, "HR_MEDICAO": "0000", "TEM_INS": 22}
        ],
    )
    result = operator.post("/api/v1/stations/A001/sync", json={}, headers=csrf_headers(operator))
    assert result.status_code == 200
    assert result.json()["skipped"] == 1
    assert db.scalar(select(func.count()).select_from(StationObservation)) == 0
