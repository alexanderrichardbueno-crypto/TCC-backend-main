"""Contract tests for the map's distinct forecast-point and warning-area layers."""

from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.inmet_sync import cached_active_inmet_count, sync_inmet_warnings
from app.integrations.inmet import InmetClient
from app.integrations.open_meteo import OpenMeteoClient
from app.models import Forecast, User, WeatherAlert
from app.open_meteo_sync import forecast_cache_key, get_open_meteo_or_fallback
from app.routers import weather

from .test_backend_workflow import inmet_xml, open_meteo_payload


def mocked_map_provider(monkeypatch, handler, *, enabled=True):
    settings = Settings(open_meteo_enabled=enabled)
    provider = OpenMeteoClient(settings, transport=httpx.MockTransport(handler))

    def resolve(db, **kwargs):
        return get_open_meteo_or_fallback(db, settings=settings, client=provider, **kwargs)

    monkeypatch.setattr(weather, "get_open_meteo_or_fallback", resolve)


def test_map_geocodes_city_then_renders_open_meteo_point_not_invented_polygon(
    client: TestClient, db, monkeypatch
):
    requests = []

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
                            "latitude": -24.101,
                            "longitude": -46.620,
                        }
                    ]
                },
            )
        return httpx.Response(200, json=open_meteo_payload())

    mocked_map_provider(monkeypatch, handler)
    response = client.get("/api/v1/map-data", params={"city": "Mongaguá", "state": "SP"})
    assert response.status_code == 200
    data = response.json()
    assert requests == ["geocoding-api.open-meteo.com", "api.open-meteo.com"]
    assert len(data["forecast_points"]) == 1
    point = data["forecast_points"][0]
    assert point["city"] == "Mongaguá"
    assert point["source_name"] == "Open-Meteo"
    assert point["source_url"] == "https://open-meteo.com/"
    assert float(point["latitude"]) == -24.101
    assert float(point["longitude"]) == -46.62
    assert point["temperature_c"] is not None
    assert point["is_stale"] is False
    assert "polygon" not in point
    assert [area["source_name"] for area in data["forecast_areas"]] == ["TEST DATA"]
    saved = db.scalar(select(Forecast).where(Forecast.source_name == "Open-Meteo"))
    assert saved.polygon is None
    assert saved.latitude is not None and saved.longitude is not None

    # A second request uses the persisted forecast rather than hitting either provider.
    cached = client.get("/api/v1/map-data", params={"city": "Mongaguá", "state": "SP"})
    assert cached.status_code == 200
    assert cached.json()["forecast_points"][0]["id"] == point["id"]
    assert requests == ["geocoding-api.open-meteo.com", "api.open-meteo.com"]


def test_map_coordinates_require_login_and_skip_geocoding(
    client: TestClient, registered_client: TestClient, monkeypatch
):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.host)
        assert request.url.params.get("latitude") == "-23.96"
        assert request.url.params.get("longitude") == "-46.33"
        return httpx.Response(200, json=open_meteo_payload())

    mocked_map_provider(monkeypatch, handler)
    coordinates = {
        "city": "Santos",
        "state": "SP",
        "latitude": -23.9637,
        "longitude": -46.3342,
    }
    with TestClient(client.app) as anonymous:
        assert anonymous.get("/api/v1/map-data", params=coordinates).status_code == 401
    result = registered_client.get(
        "/api/v1/map-data",
        params=coordinates,
    )
    assert result.status_code == 200
    assert float(result.json()["forecast_points"][0]["latitude"]) == -23.96
    assert requests == ["api.open-meteo.com"]

    for params in (
        {"latitude": -23.96},
        {"longitude": -46.33},
        {"latitude": 91, "longitude": -46.33},
        {"latitude": -23.96, "longitude": -181},
        {"city": "Santos"},
        {"state": "SP"},
    ):
        assert registered_client.get("/api/v1/map-data", params=params).status_code == 422
    assert requests == ["api.open-meteo.com"]


def test_map_uses_signed_in_city_when_saved_coordinates_are_missing(
    registered_client: TestClient, db, monkeypatch
):
    user = db.scalar(select(User).where(User.email == "maria@exemplo.com"))
    user.city = "Santos"
    user.state = "SP"
    user.latitude = None
    user.longitude = None
    db.commit()
    requested_city = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "geocoding-api.open-meteo.com":
            requested_city.append(request.url.params.get("name"))
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "country_code": "BR",
                            "admin1": "São Paulo",
                            "latitude": -23.96,
                            "longitude": -46.33,
                        }
                    ]
                },
            )
        return httpx.Response(200, json=open_meteo_payload())

    mocked_map_provider(monkeypatch, handler)
    result = registered_client.get("/api/v1/map-data")
    assert result.status_code == 200
    assert requested_city == ["Santos"]
    assert result.json()["forecast_points"][0]["city"] == "Santos"


def test_map_stale_forecast_is_marked_and_never_rendered_as_polygon(
    client: TestClient, db, monkeypatch
):
    mocked_map_provider(
        monkeypatch,
        lambda _: httpx.Response(503),
    )
    now = datetime.now(UTC)
    db.add(
        Forecast(
            source_key=forecast_cache_key("Santos", "SP"),
            city="Santos",
            state="SP",
            latitude=-23.96,
            longitude=-46.33,
            condition="Nublado",
            temperature_c=25,
            minimum_c=20,
            maximum_c=27,
            humidity=70,
            wind_kmh=10,
            rain_probability=40,
            severity="LOW",
            polygon=None,
            source_name="Open-Meteo",
            source_url="https://open-meteo.com/",
            issued_at=now - timedelta(minutes=20),
            valid_until=now - timedelta(minutes=1),
        )
    )
    db.commit()
    result = client.get("/api/v1/map-data", params={"city": "Santos", "state": "SP"})
    assert result.status_code == 200
    point = result.json()["forecast_points"][0]
    assert point["is_stale"] is True
    assert point["source_name"] == "Open-Meteo"
    assert all(area["source_name"] != "Open-Meteo" for area in result.json()["forecast_areas"])


def test_map_omits_historic_point_without_coordinates_if_provider_unavailable(
    client: TestClient, monkeypatch
):
    mocked_map_provider(monkeypatch, lambda _: httpx.Response(503))
    result = client.get("/api/v1/map-data", params={"city": "Mongagua", "state": "SP"})
    assert result.status_code == 200
    assert result.json()["forecast_points"] == []
    assert result.json()["forecast_areas"][0]["source_name"] == "TEST DATA"


def test_map_excludes_future_and_expired_warnings(client: TestClient, db, monkeypatch):
    mocked_map_provider(monkeypatch, lambda _: httpx.Response(503), enabled=False)
    now = datetime.now(UTC)
    for source_key, start, end in (
        ("TEST-FUTURE-ALERT", now + timedelta(hours=1), now + timedelta(hours=3)),
        ("TEST-EXPIRED-ALERT", now - timedelta(hours=3), now - timedelta(hours=1)),
    ):
        db.add(
            WeatherAlert(
                source_key=source_key,
                title=source_key,
                message="Aviso de teste sem atividade",
                event_type="SEVERE_STORM",
                severity="HIGH",
                area_name="Santos",
                latitude=-23.96,
                longitude=-46.33,
                radius_km=10,
                recommendations=[],
                issued_at=start,
                valid_until=end,
            )
        )
    db.commit()
    titles = [item["title"] for item in client.get("/api/v1/map-data").json()["alerts"]]
    assert "TEST-FUTURE-ALERT" not in titles
    assert "TEST-EXPIRED-ALERT" not in titles


def test_map_inmet_warning_uses_its_real_polygon_and_source(client: TestClient, db, monkeypatch):
    mocked_map_provider(monkeypatch, lambda _: httpx.Response(503), enabled=False)
    feed = InmetClient(
        Settings(inmet_enabled=True),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=inmet_xml())),
    )
    assert sync_inmet_warnings(db, actor=None, client=feed) == (1, 0)
    warning = db.scalar(select(WeatherAlert).where(WeatherAlert.origin == "INMET"))
    assert warning is not None
    map_result = client.get("/api/v1/map-data")
    assert map_result.status_code == 200
    item = next(alert for alert in map_result.json()["alerts"] if alert["origin"] == "INMET")
    assert item["polygon"]["type"] == "Polygon"
    assert item["source_url"] == "https://avisos.inmet.gov.br/123"
    assert item["radius_km"] is None

    # A reviewed false alarm disappears from the public map without deleting provenance.
    warning.validation_status = "FALSE_ALARM"
    db.commit()
    active = client.get("/api/v1/map-data").json()["alerts"]
    assert not any(alert["origin"] == "INMET" for alert in active)


def test_geometryless_inmet_warning_is_listed_without_inventing_a_map_area(
    client: TestClient, db, monkeypatch
):
    mocked_map_provider(monkeypatch, lambda _: httpx.Response(503), enabled=False)
    # INMET can describe an affected area in words without supplying a CAP polygon.
    feed_xml = inmet_xml().replace(
        b"<cap:polygon>-24.0,-46.8 -24.0,-46.2 -24.5,-46.2 -24.0,-46.8</cap:polygon>",
        b"",
    )
    assert b"<cap:polygon>" not in feed_xml
    feed = InmetClient(
        Settings(inmet_enabled=True),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=feed_xml)),
    )
    assert sync_inmet_warnings(db, actor=None, client=feed) == (1, 0)
    assert sync_inmet_warnings(db, actor=None, client=feed) == (0, 1)
    assert cached_active_inmet_count(db) == 1

    map_result = client.get("/api/v1/map-data")
    assert map_result.status_code == 200
    map_data = map_result.json()
    official = [item for item in map_data["alerts"] if item["origin"] == "INMET"]
    assert len(official) == 1
    warning = official[0]
    assert warning["title"] == "Aviso detalhado de tempestade"
    assert warning["area_name"] == "Litoral de Sao Paulo"
    assert warning["polygon"] is None
    assert warning["latitude"] is None
    assert warning["longitude"] is None
    assert warning["radius_km"] is None
    assert warning["source_url"] == "https://avisos.inmet.gov.br/123"
    assert all(area["source_name"] != "INMET" for area in map_data["forecast_areas"])

    listed = client.get("/api/v1/alerts")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json() if item["origin"] == "INMET"] == [warning["id"]]
