import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.database import engine
from app.routers import auth, content, dashboard, inmet, panel, stations, users, weather

settings = get_settings()
public_dir = Path(__file__).resolve().parent.parent / "public"
site_template = Path(__file__).resolve().parent.parent.parent / "site.tpl.html"

DEFAULT_CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline' https://unpkg.com "
    "https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; "
    "script-src 'self' https://unpkg.com; connect-src 'self'"
)
# O painel usa o MapLibre GL (unpkg, com reserva no jsdelivr), o mapa base do MapTiler ou
# do OpenFreeMap, as fontes do Google e consulta o INMET direto do navegador.
PANEL_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://unpkg.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net "
    "https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "img-src 'self' data: blob: https:; "
    "worker-src 'self' blob:; child-src blob:; "
    "connect-src 'self' https://apiprevmet3.inmet.gov.br https://api.maptiler.com "
    "https://*.maptiler.com https://tiles.openfreemap.org https://unpkg.com "
    "https://cdn.jsdelivr.net"
)
# site.tpl.html traz os scripts dentro da própria página.
SITE_CSP = PANEL_CSP.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'")
SITE_PAGES = {"/painel.html", "/profissional.html"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_production()
    yield


app = FastAPI(
    title="PrevClima API",
    version="0.1.0",
    description="API do prototipo conectado de avisos meteorologicos severos.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if (
        request.url.path.startswith("/api/")
        and request.method in {"POST", "PATCH", "PUT", "DELETE"}
        and request.cookies.get("prevclima_access")
        and request.url.path
        not in {
            "/api/v1/auth/login",
            "/api/v1/auth/login-mobile",
            "/api/v1/auth/login-app",
            "/api/v1/auth/login-professional",
            "/api/v1/auth/login-token",
            "/api/v1/auth/register",
        }
    ):
        cookie_token = request.cookies.get("prevclima_csrf", "")
        header_token = request.headers.get("X-CSRF-Token", "")
        if not cookie_token or not secrets.compare_digest(cookie_token, header_token):
            return JSONResponse(status_code=403, content={"detail": "Token CSRF inválido"})

    response = await call_next(request)
    # Faz o navegador conferir se as páginas e scripts mudaram antes de usar a cópia salva.
    if not request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        SITE_CSP
        if request.url.path in SITE_PAGES
        else PANEL_CSP
        if request.url.path == "/mapa.html"
        else DEFAULT_CSP
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    translations = {
        "missing": "Campo obrigatório",
        "string_too_short": "Texto menor que o permitido",
        "string_too_long": "Texto maior que o permitido",
        "literal_error": "Valor inválido",
        "greater_than": "Valor abaixo do limite permitido",
        "less_than_equal": "Valor acima do limite permitido",
    }
    errors = []
    for error in exc.errors():
        message = translations.get(error["type"], error["msg"])
        if error["type"] == "value_error":
            message = str(error.get("ctx", {}).get("error", message))
        errors.append({"loc": error["loc"], "msg": message, "type": error["type"]})
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException):
    translated = {
        "Not Found": "Recurso não encontrado",
        "Method Not Allowed": "Método não permitido",
    }.get(exc.detail, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": translated})


@app.get("/api/health", tags=["operações"])
def health():
    return {"status": "ok"}


@app.get("/api/ready", tags=["operações"])
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "indisponível"})
    return {"status": "pronto"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(weather.router, prefix="/api/v1")
app.include_router(content.router, prefix="/api/v1")
app.include_router(inmet.router, prefix="/api/v1")
app.include_router(stations.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(panel.router, prefix="/api/v1")


LOGO_BIG = ("logo.png", "logo.svg", "logo.jpg", "logo.webp")
LOGO_SMALL = ("logo-small.png", "logo-small.svg", "logo.png", "logo.svg")


def logo_file(names: tuple[str, ...]) -> str | None:
    return next((n for n in names if (public_dir / "assets" / "img" / n).is_file()), None)


@app.get("/marca/logo", include_in_schema=False)
def big_logo():
    return RedirectResponse(f"/assets/img/{logo_file(LOGO_BIG) or 'logo-reserva.svg'}")


@app.get("/marca/logo-small", include_in_schema=False)
def small_logo():
    return RedirectResponse(f"/assets/img/{logo_file(LOGO_SMALL) or 'logo-reserva.svg'}")


@app.get("/mapa.html", include_in_schema=False)
def map_page():
    html = (public_dir / "mapa.html").read_text(encoding="utf-8")
    key = re.sub(r"[^A-Za-z0-9_-]", "", settings.maptiler_key or "")
    return HTMLResponse(html.replace("__MAPTILER_KEY__", key))


def site_html(request: Request) -> str:
    """site.tpl.html com o endereço da API, a chave do MapTiler e a logo preenchidos."""
    # No Docker só a pasta do backend é copiada; ali vale a central de public/.
    source = site_template if site_template.is_file() else public_dir / "painel.html"
    html = source.read_text(encoding="utf-8")
    html = html.replace("__API_BASE__", str(request.base_url).rstrip("/"))
    html = html.replace("__INMET_DATA__", "{}")
    key = re.sub(r"[^A-Za-z0-9_-]", "", settings.maptiler_key or "")
    if key:
        html = html.replace("__MAPTILER_KEY__", key)
    for marker, names in (("__LOGO_BIG__", LOGO_BIG), ("__LOGO_SMALL__", LOGO_SMALL)):
        found = logo_file(names)
        if found:
            html = html.replace(marker, f"/assets/img/{found}")
    return html


@app.get("/painel.html", include_in_schema=False)
@app.get("/profissional.html", include_in_schema=False)
def site_page(request: Request):
    return HTMLResponse(site_html(request), headers={"Cache-Control": "no-store"})


@app.get("/meteorologista.html", include_in_schema=False)
def professional_login():
    # O painel novo tem a própria tela de entrada.
    return RedirectResponse("/painel.html", status_code=307)


app.mount("/", StaticFiles(directory=public_dir, html=True), name="public")
