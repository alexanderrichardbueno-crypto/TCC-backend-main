"""INMET JSON and BDMEP adapters. No credentials or legacy browser drivers required."""

import csv
import io
import json
import re
import unicodedata
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.config import get_settings
from app.integrations.inmet import InmetError

UNAVAILABLE = "INMET indisponível ou resposta inválida; dados salvos preservados"


def number(value, low=-999, high=9999):
    if value is None or str(value).strip().lower() in {"", "null", "nan", "-9999", "-9999.0"}:
        return None
    try:
        result = Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation:
        return None
    return result if result.is_finite() and low <= result <= high else None


def normalized(row):
    return {
        re.sub(
            r"[^a-z0-9]",
            "",
            unicodedata.normalize("NFKD", str(k)).encode("ascii", "ignore").decode().lower(),
        ): v
        for k, v in row.items()
        if k is not None
    }


def station(row):
    r = normalized(row)
    code = str(r.get("cdestacao") or r.get("codigoomm") or r.get("estacao") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{3,16}", code):
        raise ValueError("Código de estação inválido")
    # O identificador WIGOS do INMET traz o código IBGE do município: 0-76-0-<IBGE><sufixo>.
    wigos = re.fullmatch(r"0-76-0-(\d{7})\d*", str(r.get("cdwsi") or "").strip())
    return {
        "code": code.upper(),
        "geocode": wigos.group(1) if wigos else None,
        "name": str(r.get("dcnome") or r.get("nomeestacao") or code)[:120],
        "state": str(r.get("sgestado") or r.get("estado") or "").upper()[:2] or None,
        "kind": "AUTOMATIC" if code[0].isalpha() else "CONVENTIONAL",
        "latitude": number(r.get("vllatitude", r.get("latitude")), -90, 90),
        "longitude": number(r.get("vllongitude", r.get("longitude")), -180, 180),
    }


def observation(row, *, source="INMET", period="HOURLY"):
    r = normalized(row)
    meta = station(row)
    raw_date = str(r.get("dtmedicao") or r.get("data") or "").strip()
    parsed = None
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(raw_date[:10], pattern)
            break
        except ValueError:
            pass
    if parsed is None:
        raise ValueError("Data de observação inválida")
    raw_hour = str(r.get("hrmedicao") or r.get("hora") or "0000").strip().replace(":", "").zfill(4)
    if not re.fullmatch(r"\d{4}", raw_hour):
        raise ValueError("Hora de observação inválida")
    parsed = parsed.replace(hour=int(raw_hour[:2]), minute=int(raw_hour[2:]), tzinfo=UTC)
    if parsed > datetime.now(UTC):
        raise ValueError("Observação no futuro")

    def pick(*keys, low=-100, high=100):
        return number(next((r[k] for k in keys if r.get(k) not in (None, "")), None), low, high)

    return meta, {
        "station_code": meta["code"],
        "observed_at": parsed,
        "period": period,
        "source": source,
        "temperature_c": pick("temins", "tempbulboseco", "tempcompmedia", "tempcompensadamedia"),
        "minimum_c": pick("temmin", "tempminima", "tempminimamedia"),
        "maximum_c": pick("temmax", "tempmaxima", "tempmaximamedia"),
        "humidity": pick("umdins", "umidaderelativa", "umidaderelativamedia", low=0),
        "precipitation_mm": pick("chuva", "precipitacao", "precipitacaototal", low=0, high=999999),
        "wind_ms": pick(
            "venvel", "velocidadeventomedia", "velocidadedoventomedia", low=0, high=500
        ),
    }


def parse_import(content: str, format: str, period: str):
    """Accept get_dados() JSON from Felipe and semicolon CSV from Fabio."""
    try:
        rows = (
            json.loads(content)
            if format == "rest-json"
            else list(csv.DictReader(io.StringIO(content.lstrip("\ufeff")), delimiter=";"))
        )
    except (ValueError, csv.Error) as error:
        raise ValueError("Arquivo inválido") from error
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError("Informe uma lista com até 10.000 observações")
    parsed, skipped = [], 0
    for row in rows:
        try:
            if not isinstance(row, dict):
                raise ValueError("Linha inválida")
            parsed.append(observation(row, source="BDMEP", period=period))
        except (ValueError, TypeError, OverflowError):
            skipped += 1
    return parsed, skipped


def fetch_body(url):
    """Download a fixed INMET URL. Never pass a URL supplied by a user or a station record."""
    settings = get_settings()
    if not settings.inmet_observations_enabled:
        raise InmetError("Observações INMET desabilitadas na configuração")
    try:
        with httpx.Client(timeout=settings.inmet_timeout_seconds, follow_redirects=False) as client:
            with client.stream(
                "GET", url, headers={"User-Agent": settings.inmet_user_agent}
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > settings.inmet_max_response_bytes:
                        raise InmetError("Resposta INMET excede o limite configurado")
        return bytes(body)
    except httpx.HTTPError as error:
        raise InmetError(UNAVAILABLE) from error


def fetch_json(path):
    body = fetch_body("https://apitempo.inmet.gov.br/" + path)
    if not body:  # 204: o INMET respondeu, mas não há registros para a consulta
        return []
    try:
        result = json.loads(body)
    except ValueError as error:
        raise InmetError(UNAVAILABLE) from error
    if not isinstance(result, list):
        raise InmetError(UNAVAILABLE)
    return result


def fetch_latest(geocode: str):
    """Latest measurement of the station INMET considers nearest to an IBGE municipality."""
    if not re.fullmatch(r"\d{7}", geocode):
        raise ValueError("Código IBGE inválido")
    body = fetch_body(f"https://apiprevmet3.inmet.gov.br/estacao/proxima/{geocode}")
    try:
        result = json.loads(body)
    except ValueError as error:
        raise InmetError(UNAVAILABLE) from error
    data = result.get("dados") if isinstance(result, dict) else None
    return data if isinstance(data, dict) else None


def fetch_observations(code: str, start: date, end: date):
    if not re.fullmatch(r"[A-Z0-9]{3,16}", code):
        raise ValueError("Código de estação inválido")
    return fetch_json(f"estacao/{start.isoformat()}/{end.isoformat()}/{code}")
