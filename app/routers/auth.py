import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.account_codes import PURPOSE_RESET, PURPOSE_VERIFY, check_code, send_code
from app.config import get_settings
from app.dependencies import CurrentUser, DbSession, MobileUser
from app.models import Role, User
from app.schemas import (
    AuthResponse,
    EmailRequest,
    LoginRequest,
    MessageOut,
    RegisterOut,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from app.security import create_access_token, create_csrf_token, hash_password, verify_password
from app.services import user_out

router = APIRouter(prefix="/auth", tags=["autenticacao"])
DUMMY_PASSWORD_HASH = hash_password("NotARealPassword123!")


def normalized_email(value: str) -> str:
    return value.strip().lower()


def new_public_code(db: DbSession) -> str:
    while True:
        code = f"PVC-{secrets.token_hex(4).upper()}"
        if not db.scalar(select(User.id).where(User.public_code == code)):
            return code


def set_auth_cookies(
    response: Response,
    user: User,
    *,
    audience: str = "prevclima-web",
) -> str:
    csrf, _ = set_auth_cookies_with_token(response, user, audience=audience)
    return csrf


def set_auth_cookies_with_token(
    response: Response,
    user: User,
    *,
    audience: str = "prevclima-web",
) -> tuple[str, str]:
    settings = get_settings()
    csrf = create_csrf_token()
    access_token = create_access_token(user.id, user.token_version, audience=audience)
    response.set_cookie(
        "prevclima_access",
        access_token,
        max_age=settings.jwt_ttl_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "prevclima_csrf",
        csrf,
        max_age=settings.jwt_ttl_minutes * 60,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return csrf, access_token


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: DbSession):
    email = normalized_email(str(payload.email))
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado")

    role = db.scalar(select(Role).where(Role.code == "USER"))
    if not role:
        raise HTTPException(status_code=503, detail="As funções de acesso não foram inicializadas")

    user = User(
        public_code=new_public_code(db),
        name=payload.name,
        email=email,
        password_hash=hash_password(payload.password),
        role_id=role.id,
        city=payload.city,
        state=payload.state,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado"
        ) from error
    send_code(db, user, PURPOSE_VERIFY)
    db.commit()
    return RegisterOut(message="Enviamos um código de confirmação para o seu e-mail.", email=email)


def user_by_email(db: DbSession, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalized_email(email)))


@router.post("/verify-email", response_model=AuthResponse)
def verify_email(payload: VerifyEmailRequest, response: Response, db: DbSession):
    user = user_by_email(db, str(payload.email))
    if not user or not user.is_active or not check_code(db, user, PURPOSE_VERIFY, payload.code):
        db.commit()  # guarda a contagem de tentativas
        raise HTTPException(status_code=400, detail="Código inválido ou expirado")
    user.email_verified_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    csrf = set_auth_cookies(response, user)
    return AuthResponse(user=user_out(user), csrf_token=csrf)


@router.post("/resend-verification", response_model=MessageOut)
def resend_verification(payload: EmailRequest, db: DbSession):
    user = user_by_email(db, str(payload.email))
    if user and user.is_active and user.email_verified_at is None:
        send_code(db, user, PURPOSE_VERIFY)
        db.commit()
    return MessageOut(message="Se o cadastro estiver pendente, enviamos um novo código.")


@router.post("/forgot-password", response_model=MessageOut)
def forgot_password(payload: EmailRequest, db: DbSession):
    user = user_by_email(db, str(payload.email))
    if user and user.is_active:
        send_code(db, user, PURPOSE_RESET)
        db.commit()
    return MessageOut(message="Se o e-mail estiver cadastrado, enviamos um código de redefinição.")


@router.post("/reset-password", response_model=MessageOut)
def reset_password(payload: ResetPasswordRequest, db: DbSession):
    user = user_by_email(db, str(payload.email))
    if not user or not user.is_active or not check_code(db, user, PURPOSE_RESET, payload.code):
        db.commit()
        raise HTTPException(status_code=400, detail="Código inválido ou expirado")
    user.password_hash = hash_password(payload.password)
    user.token_version += 1
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)  # o código provou o acesso ao e-mail
    db.commit()
    return MessageOut(message="Senha redefinida. Entre com a nova senha.")


@router.get("/mobile-session", response_model=AuthResponse)
def mobile_session(user: MobileUser):
    return AuthResponse(user=user_out(user), csrf_token="")


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: DbSession):
    user = authenticate(payload, db)
    csrf = set_auth_cookies(response, user)
    return AuthResponse(user=user_out(user), csrf_token=csrf)


@router.post("/login-app", response_model=AuthResponse)
def login_app(payload: LoginRequest, db: DbSession):
    """Entrada do aplicativo Expo: aceita usuários e meteorologistas, sempre por token."""
    user = authenticate(payload, db)
    token = create_access_token(user.id, user.token_version, audience="prevclima-mobile")
    return AuthResponse(user=user_out(user), csrf_token="", access_token=token)


@router.post("/login-mobile", response_model=AuthResponse)
def login_mobile(payload: LoginRequest, response: Response, db: DbSession):
    user = authenticate(payload, db)
    if user.role.code != "USER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este acesso é exclusivo para contas de usuário",
        )
    csrf, access_token = set_auth_cookies_with_token(response, user, audience="prevclima-mobile")
    return AuthResponse(user=user_out(user), csrf_token=csrf, access_token=access_token)


def authenticate(payload: LoginRequest, db: DbSession) -> User:
    user = db.scalar(select(User).where(User.email == normalized_email(str(payload.email))))
    encoded = user.password_hash if user else DUMMY_PASSWORD_HASH
    password_is_valid = verify_password(payload.password, encoded)
    if not user or not user.is_active or not password_is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha inválidos"
        )
    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Confirme seu e-mail antes de entrar",
        )
    return user


@router.post("/login-professional", response_model=AuthResponse)
def login_professional(payload: LoginRequest, response: Response, db: DbSession):
    user = authenticate(payload, db)
    if user.role.code != "METEOROLOGIST":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Acesso profissional necessário"
        )
    csrf = set_auth_cookies(response, user)
    return AuthResponse(user=user_out(user), csrf_token=csrf)


@router.post("/login-token", response_model=AuthResponse)
def login_token(payload: LoginRequest, db: DbSession):
    """Entrada da central embutida no Streamlit, que usa Authorization: Bearer."""
    user = authenticate(payload, db)
    if user.role.code != "METEOROLOGIST":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Acesso profissional necessário"
        )
    token = create_access_token(user.id, user.token_version)
    return AuthResponse(user=user_out(user), csrf_token="", access_token=token)


@router.post("/session-token", response_model=AuthResponse)
def session_token(user: CurrentUser):
    """Entrega à central (site.tpl.html) o token da sessão aberta na tela de login."""
    if user.role.code != "METEOROLOGIST":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Acesso profissional necessário"
        )
    token = create_access_token(user.id, user.token_version)
    return AuthResponse(user=user_out(user), csrf_token="", access_token=token)


@router.post("/logout", response_model=MessageOut)
def logout(response: Response, user: CurrentUser, db: DbSession):
    user.token_version += 1
    db.commit()
    response.delete_cookie("prevclima_access", path="/")
    response.delete_cookie("prevclima_csrf", path="/")
    return MessageOut(message="Sessão encerrada")


@router.get("/me", response_model=AuthResponse)
def me(user: CurrentUser):
    return AuthResponse(user=user_out(user), csrf_token="")
