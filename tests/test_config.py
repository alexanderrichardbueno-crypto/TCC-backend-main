import pytest

from app.config import Settings


def test_cors_environment_accepts_example_and_json(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:18080,http://127.0.0.1:18080")
    assert Settings(_env_file=None).cors_origins == [
        "http://localhost:18080",
        "http://127.0.0.1:18080",
    ]
    monkeypatch.setenv("CORS_ORIGINS", '["https://prevclima.example"]')
    assert Settings(_env_file=None).cors_origins == ["https://prevclima.example"]


def test_production_rejects_development_defaults():
    settings = Settings(
        app_env="production",
        database_url="mysql+pymysql://user:pass@db/prevclima",
        cookie_secure=True,
        smtp_host="smtp.example",
        smtp_from="prevclima@example.com",
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.validate_production()


def test_production_accepts_explicit_safe_settings():
    settings = Settings(
        app_env="production",
        database_url="mysql+pymysql://user:pass@db/prevclima",
        jwt_secret="a-unique-production-secret-that-is-long-enough",
        cookie_secure=True,
        smtp_host="smtp.example",
        smtp_from="prevclima@example.com",
        cors_origins=["https://prevclima.example"],
    )
    settings.validate_production()


def test_production_rejects_example_secret():
    settings = Settings(
        app_env="production",
        database_url="mysql+pymysql://user:pass@db/prevclima",
        cookie_secure=True,
        smtp_host="smtp.example",
        smtp_from="prevclima@example.com",
        jwt_secret="replace-with-at-least-32-random-characters",
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.validate_production()
