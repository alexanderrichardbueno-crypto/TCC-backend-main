"""Cenários unitários documentados em docs/testes-unitarios-tcc.md."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.integrations.stations import number, observation, parse_import, station
from app.routers.weather import distance_km, point_in_polygon


def test_numero_de_medicao_reconhece_decimal_e_descarta_valores_invalidos():
    assert number("23,5", low=-100, high=100) == Decimal("23.5")
    assert number("-9999", low=-100, high=100) is None
    assert number("NaN", low=-100, high=100) is None
    assert number("101", low=-100, high=100) is None
    assert number("0", low=0, high=100) == Decimal("0")


def test_estacao_normaliza_codigo_e_rejeita_coordenada_invalida():
    result = station(
        {"CD_ESTACAO": "a001", "DC_NOME": "Brasília", "SG_ESTADO": "df", "VL_LATITUDE": "-91"}
    )
    assert result["code"] == "A001"
    assert result["name"] == "Brasília"
    assert result["state"] == "DF"
    assert result["kind"] == "AUTOMATIC"
    assert result["latitude"] is None
    with pytest.raises(ValueError, match="Código de estação inválido"):
        station({"CD_ESTACAO": "../A001"})


def test_observacao_converte_data_hora_utc_e_preserva_chuva_zero():
    metadata, result = observation(
        {
            "CD_ESTACAO": "A001",
            "DT_MEDICAO": "2024-05-01",
            "HR_MEDICAO": "1300",
            "TEM_INS": "23,5",
            "CHUVA": "0",
        }
    )
    assert metadata["code"] == result["station_code"] == "A001"
    assert result["observed_at"] == datetime(2024, 5, 1, 13, tzinfo=UTC)
    assert result["temperature_c"] == Decimal("23.5")
    assert result["precipitation_mm"] == Decimal("0")


def test_importacao_csv_conta_linha_invalida_sem_descartar_linha_valida():
    content = "ESTACAO;DATA;HORA;PRECIPITACAO\nA001;01/05/2024;1300;0\nA001;data-invalida;1300;15\n"
    rows, skipped = parse_import(content, "temperature-csv", "HOURLY")
    assert len(rows) == 1
    assert skipped == 1
    assert rows[0][1]["precipitation_mm"] == Decimal("0")
    assert rows[0][1]["source"] == "BDMEP"


def test_poligono_considera_borda_e_exclui_interior_de_buraco():
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            [[3, 3], [7, 3], [7, 7], [3, 7], [3, 3]],
        ],
    }
    assert point_in_polygon(1, 1, geometry) is True
    assert point_in_polygon(0, 5, geometry) is True
    assert point_in_polygon(5, 5, geometry) is False
    assert point_in_polygon(11, 5, geometry) is False


def test_distancia_geografica_e_zero_na_mesma_posicao_e_simetrica():
    brasilia = (-15.7939, -47.8828)
    sao_paulo = (-23.5505, -46.6333)
    assert distance_km(*brasilia, *brasilia) == 0
    forward = distance_km(*brasilia, *sao_paulo)
    assert forward == pytest.approx(870, abs=10)
    assert distance_km(*sao_paulo, *brasilia) == pytest.approx(forward)
