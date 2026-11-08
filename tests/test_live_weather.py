"""Regression checks for real-data mode, location precedence and feed health."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.config import Settings, get_settings
from app.inmet_sync import sync_inmet_warnings, warning_feed_status
from app.integrations.inmet import InmetClient, InmetError
from app.integrations.open_meteo import OpenMeteoError, parse_forecast_payload
from app.models import AuditEvent, Forecast, User
from app.routers import weather

from .test_backend_workflow import inmet_xml, open_meteo_payload


def test_home_explicit_city_overrides_saved_city_and_gps(registered_client, db, monkeypatch):
    user = db.scalar(select(User).where(User.email == "maria@exemplo.com"))
    user.latitude, user.longitude = -24.1, -46.62
    db.commit()
    calls = []

    def resolve(_db, **kwargs):
        calls.append(kwargs)
        return None, False

    monkeypatch.setattr(weather, "get_open_meteo_or_fallback", resolve)
    assert registered_client.get("/api/v1/home?city=Recife&state=PE").status_code == 200
    assert calls[-1] == {"city": "Recife", "state": "PE", "latitude": None, "longitude": None}
    assert registered_client.get("/api/v1/home").status_code == 200
    assert calls[-1]["latitude"] == -24.1
    assert registered_client.get("/api/v1/home?city=Recife").status_code == 422


def test_home_city_forecast_filters_unrelated_warning_geometry(client, db, monkeypatch):
    forecast = db.scalar(select(Forecast))
    forecast.latitude, forecast.longitude = -8.05, -34.88
    monkeypatch.setattr(weather, "get_open_meteo_or_fallback", lambda *_a, **_kw: (forecast, False))
    result = client.get("/api/v1/home?city=Recife&state=PE").json()
    assert result["active_alerts"] == []  # Fixture warning is in São Paulo.


def test_inmet_status_tracks_success_failure_and_delayed_worker(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "inmet_enabled", True)
    assert warning_feed_status(db)["status"] == "pending"
    success = InmetClient(
        Settings(inmet_enabled=True),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=inmet_xml())),
    )
    sync_inmet_warnings(db, actor=None, client=success)
    assert warning_feed_status(db)["status"] == "current"
    first_success = warning_feed_status(db)["last_success_at"]
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "INMET_WARNINGS_SYNCED"))
    event.created_at = datetime.now(UTC) - timedelta(hours=3)
    db.commit()
    assert warning_feed_status(db)["status"] == "stale"
    failing = InmetClient(
        Settings(inmet_enabled=True), transport=httpx.MockTransport(lambda _: httpx.Response(503))
    )
    with pytest.raises(InmetError):
        sync_inmet_warnings(db, actor=None, client=failing)
    assert warning_feed_status(db)["status"] == "unavailable"
    assert warning_feed_status(db)["last_success_at"] < first_success
    response = client.get("/api/v1/map-data").json()
    assert response["warning_feed"]["status"] == "unavailable"
    assert response["warning_feed"]["last_success_at"].endswith("Z")
    assert any(a["origin"] == "INMET" for a in response["alerts"])
    monkeypatch.setattr(get_settings(), "inmet_enabled", False)
    assert warning_feed_status(db)["status"] == "disabled"


@pytest.mark.parametrize("offset", [-10801, 3600, 10**20])
def test_forecast_rejects_stale_future_and_out_of_range_provider_times(offset):
    payload = open_meteo_payload()
    payload["current"]["time"] = int(datetime.now(UTC).timestamp()) + offset
    with pytest.raises(OpenMeteoError):
        parse_forecast_payload(payload, cache_minutes=15)
