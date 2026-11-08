"""Monta a central meteorológica do PrevClima (site.tpl.html) dentro do Streamlit.

A página usa os dados reais do backend PrevClima (FastAPI): login de meteorologista, previsões,
alertas, contas e estações. Configure em .streamlit/secrets.toml ou no ambiente:
    PREVCLIMA_API_URL = "https://endereco-do-backend"   # padrão: http://127.0.0.1:18080
e inclua o endereço do Streamlit em CORS_ORIGINS no .env do backend
(em desenvolvimento: http://localhost:8501).

Uso no app:
    from prevclima_site import render_site
    render_site(logo="assets/logo.png")            # ajuste o caminho da sua logo

Mapa (MapTiler OMT, o mesmo mapa vetorial do openstreetmap.org):
    Crie uma chave grátis em https://cloud.maptiler.com/account/keys/ e coloque em
    .streamlit/secrets.toml:   MAPTILER_KEY = "sua_chave"
    (ou na variável de ambiente MAPTILER_KEY). A chave vai para o navegador, então
    restrinja-a ao domínio do seu app no painel do MapTiler.
    Sem chave, o mapa usa o OpenFreeMap (mesmos dados do OSM, mesmo esquema OpenMapTiles).

O que este módulo resolve:
1. Logo: lê o arquivo de imagem e troca os marcadores __LOGO_BIG__ / __LOGO_SMALL__
   pelo base64 correto (str, sem quebras de linha, com o tipo certo: png, jpg, svg...).
   Erro comum que deixava a logo quebrada: usar base64.encodebytes() (põe quebras de linha)
   ou colar o resultado de b64encode() sem .decode() (vira "b'...'" dentro do HTML).
2. Dados do INMET: o próprio navegador do usuário consulta a API do INMET e atualiza sozinho.
   Este módulo também baixa uma cópia no servidor (cache de 1 hora, renovada todo dia) que a
   página usa como reserva se o navegador não conseguir falar com o INMET.
   Atenção: o INMET recusa conexões vindas de fora do Brasil. Se o app roda no Streamlit
   Community Cloud (servidores nos EUA), a cópia do servidor pode vir vazia; nesse caso vale só
   a busca feita pelo navegador, que funciona normalmente para quem acessa do Brasil.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
from datetime import date
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

BASE = Path(__file__).resolve().parent
TEMPLATE = BASE / "site.tpl.html"
INMET_API = "https://apiprevmet3.inmet.gov.br"
DEFAULT_API_URL = "http://127.0.0.1:18080"

# Código IBGE das cidades do "Resumo de risco de hoje"
GEOCODES = {
    "Mongaguá": "3531100",
    "Santos": "3548500",
    "São Paulo": "3550308",
    "Campinas": "3509502",
    "Curitiba": "4106902",
    "Florianópolis": "4205407",
}


def _data_uri(path: str | Path | None) -> str:
    """Converte uma imagem em data URI. Retorna "" se o arquivo não existir."""
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = BASE / p
    if not p.is_file():
        st.warning(f"Logo não encontrada em: {p}")
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")  # .decode() evita o "b'...'"
    return f"data:{mime};base64,{b64}"


@st.cache_data(ttl=3600, show_spinner=False)
def inmet_snapshot(dia: str) -> dict:
    """Cópia dos dados do INMET. O argumento `dia` força uma nova busca a cada dia."""
    out: dict = {"ts": int(time.time() * 1000), "dia": dia, "cidades": {}}
    s = requests.Session()
    s.headers["User-Agent"] = "PrevClima/1.0"
    try:
        r = s.get(f"{INMET_API}/avisos/ativos", timeout=20)
        r.raise_for_status()
        out["avisos"] = r.json()
    except Exception as e:  # sem conexão, fora do Brasil, INMET fora do ar...
        out["erro"] = str(e)
    for geo in GEOCODES.values():
        cidade = {}
        for chave, url in (
            ("previsao", f"{INMET_API}/previsao/{geo}"),
            ("estacao", f"{INMET_API}/estacao/proxima/{geo}"),
        ):
            try:
                r = s.get(url, timeout=15)
                r.raise_for_status()
                cidade[chave] = r.json()
            except Exception:
                pass
        if cidade:
            out["cidades"][geo] = cidade
    return out


def maptiler_key() -> str:
    try:
        k = st.secrets.get("MAPTILER_KEY", "")
    except Exception:  # sem secrets.toml
        k = ""
    return str(k or os.environ.get("MAPTILER_KEY", "")).strip()


def api_url() -> str:
    try:
        url = st.secrets.get("PREVCLIMA_API_URL", "")
    except Exception:  # sem secrets.toml
        url = ""
    url = str(url or os.environ.get("PREVCLIMA_API_URL", "") or DEFAULT_API_URL).strip().rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9.\-_:/]+", url):
        raise ValueError("PREVCLIMA_API_URL inválida")
    return url


def build_html(logo: str | Path | None = None, logo_small: str | Path | None = None,
               incluir_inmet: bool = True, maptiler: str | None = None) -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__API_BASE__", api_url())
    key = maptiler if maptiler is not None else maptiler_key()
    if key:
        html = html.replace("__MAPTILER_KEY__", key.replace("<", ""))

    big = _data_uri(logo)
    small = _data_uri(logo_small) or big
    if big:
        html = html.replace("data:image/png;base64,__LOGO_BIG__", big)
    if small:
        html = html.replace("data:image/png;base64,__LOGO_SMALL__", small)

    dados = inmet_snapshot(date.today().isoformat()) if incluir_inmet else {}
    # "</" escapado para o JSON não fechar a tag <script> por engano
    html = html.replace("__INMET_DATA__", json.dumps(dados, ensure_ascii=False).replace("</", "<\\/"))
    return html


def render_site(logo: str | Path | None = "assets/logo.png", logo_small: str | Path | None = None,
                height: int = 900) -> None:
    components.html(build_html(logo, logo_small), height=height, scrolling=True)


if __name__ == "__main__":
    # Teste rápido fora do Streamlit: gera site.html para abrir no navegador
    (BASE / "site.html").write_text(build_html("assets/logo.png", incluir_inmet=False), encoding="utf-8")
    print("site.html gerado")
