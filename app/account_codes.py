"""Códigos de uso único enviados por e-mail (confirmação de cadastro e nova senha)."""

import hashlib
import hmac
import logging
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AccountCode, User

PURPOSE_VERIFY = "VERIFY_EMAIL"
PURPOSE_RESET = "RESET_PASSWORD"
CODE_TTL = timedelta(minutes=30)
MAX_ATTEMPTS = 5
SUBJECTS = {
    PURPOSE_VERIFY: "PrevClima: confirme seu e-mail",
    PURPOSE_RESET: "PrevClima: redefinição de senha",
}
logger = logging.getLogger("uvicorn.error")


def _hash(user_id: int, purpose: str, code: str) -> str:
    message = f"{user_id}:{purpose}:{code}".encode()
    return hmac.new(get_settings().jwt_secret.encode(), message, hashlib.sha256).hexdigest()


def deliver(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        # Só ocorre fora de produção: validate_production exige o SMTP configurado.
        logger.warning("SMTP não configurado. E-mail para %s | %s | %s", to, subject, body)
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        if settings.smtp_starttls:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)


def send_code(db: Session, user: User, purpose: str) -> None:
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.execute(
        delete(AccountCode).where(AccountCode.user_id == user.id, AccountCode.purpose == purpose)
    )
    db.add(
        AccountCode(
            user_id=user.id,
            purpose=purpose,
            code_hash=_hash(user.id, purpose, code),
            expires_at=datetime.now(UTC) + CODE_TTL,
        )
    )
    db.flush()
    try:
        deliver(
            user.email, SUBJECTS[purpose], f"Seu código PrevClima é {code}. Vale por 30 minutos."
        )
    except (OSError, smtplib.SMTPException) as error:
        db.rollback()
        raise HTTPException(
            status_code=503, detail="Não foi possível enviar o e-mail. Tente novamente."
        ) from error


def check_code(db: Session, user: User, purpose: str, code: str) -> bool:
    item = db.scalar(
        select(AccountCode).where(AccountCode.user_id == user.id, AccountCode.purpose == purpose)
    )
    if not item:
        return False
    expires = item.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires <= datetime.now(UTC) or item.attempts >= MAX_ATTEMPTS:
        db.delete(item)
        return False
    if not hmac.compare_digest(item.code_hash, _hash(user.id, purpose, code)):
        item.attempts += 1
        return False
    db.delete(item)
    return True
