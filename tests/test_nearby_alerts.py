"""A seção de alertas mostra apenas o que cobre a região do usuário."""

from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from app.models import SevereForecast, WeatherAlert

from .test_backend_workflow import open_meteo_payload
from .test_map_integration import mocked_map_provider


def square(west: float, south: float) -> dict:
    east, north = west + 1, south + 1
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


NEAR = square(-47, -25)  # Contém Mongaguá (-24.1, -46.62).
FAR = square(-40, -6)


def add_alert(db, title: str, origin: str, polygon: dict | None) -> WeatherAlert:
    now = datetime.now(UTC)
    alert = WeatherAlert(
        origin=origin,
        source_name="Teste",
        validation_status="ACTIVE",
        title=title,
        message="Descrição do alerta",
        event_type="SEVERE_STORM",
        severity="HIGH",
        area_name="Área",
        polygon=polygon,
        recommendations=[],
        issued_at=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
    )
    db.add(alert)
    return alert


def add_forecast(db, level: int, polygon: dict) -> SevereForecast:
    now = datetime.now(UTC)
    item = SevereForecast(
        level=level,
        description="Previsão da equipe",
        polygon=polygon,
        issued_at=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
    )
    db.add(item)
    return item


def geocoding(request: httpx.Request) -> httpx.Response:
    if request.url.host == "geocoding-api.open-meteo.com":
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "country_code": "BR",
                        "admin1": "São Paulo",
                        "latitude": -24.1,
                        "longitude": -46.62,
                    }
                ]
            },
        )
    return httpx.Response(200, json=open_meteo_payload())


def test_nearby_lists_only_alerts_and_forecasts_covering_the_region(
    client: TestClient, db, monkeypatch
):
    mocked_map_provider(monkeypatch, geocoding)
    team_near = add_alert(db, "Equipe perto", "MANUAL", NEAR)
    inmet_near = add_alert(db, "INMET perto", "INMET", NEAR)
    team_far = add_alert(db, "Equipe longe", "MANUAL", FAR)
    without_area = add_alert(db, "INMET sem área", "INMET", None)
    forecast_near = add_forecast(db, 2, NEAR)
    forecast_far = add_forecast(db, 3, FAR)
    db.commit()

    response = client.get("/api/v1/alerts/nearby")

    assert response.status_code == 200
    data = response.json()
    assert data["location"] is not None
    ids = [item["id"] for item in data["alerts"]]
    assert team_near.id in ids and inmet_near.id in ids
    assert ids.index(team_near.id) < ids.index(inmet_near.id)
    assert team_far.id not in ids and without_area.id not in ids
    forecast_ids = [item["id"] for item in data["forecasts"]]
    assert forecast_near.id in forecast_ids and forecast_far.id not in forecast_ids
    listed = next(item for item in data["forecasts"] if item["id"] == forecast_near.id)
    assert listed["level_name"] == "Nível 2"
    assert listed["severity"] == "MODERATE"
    assert listed["description"] == "Previsão da equipe"


def test_nearby_prefers_device_coordinates_without_saving_them(
    client: TestClient, db, monkeypatch
):
    def must_not_run(_db, **_kwargs):
        raise AssertionError("Com coordenadas do aparelho não há busca pela cidade")

    monkeypatch.setattr("app.routers.weather.get_open_meteo_or_fallback", must_not_run)
    near = add_alert(db, "Equipe perto", "MANUAL", NEAR)
    far = add_alert(db, "Equipe longe", "MANUAL", FAR)
    db.commit()

    response = client.get("/api/v1/alerts/nearby", params={"latitude": -5.5, "longitude": -39.5})

    assert response.status_code == 200
    data = response.json()
    assert data["location"] == "Sua localização atual"
    ids = [item["id"] for item in data["alerts"]]
    assert far.id in ids and near.id not in ids


def test_nearby_requires_both_coordinates(client: TestClient):
    assert client.get("/api/v1/alerts/nearby", params={"latitude": -5.5}).status_code == 422


def test_nearby_returns_nothing_when_the_region_is_unknown(client: TestClient, db, monkeypatch):
    def unavailable(_db, **_kwargs):
        return None, False

    monkeypatch.setattr("app.routers.weather.get_open_meteo_or_fallback", unavailable)
    add_alert(db, "Equipe perto", "MANUAL", NEAR)
    db.commit()

    assert client.get("/api/v1/alerts/nearby").json() == {
        "location": None,
        "alerts": [],
        "forecasts": [],
    }
