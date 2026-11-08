"""Cria a conta principal do dono (RF03), com o nível de acesso de meteorologista."""

from getpass import getpass
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.database import SessionLocal
from app.models import User, utcnow
from app.schemas import RegisterRequest
from app.security import hash_password
from app.seed import ensure_roles


def create_owner(db: Session, payload: RegisterRequest) -> User:
    email = str(payload.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise ValueError("Este e-mail já está cadastrado; nenhuma conta foi alterada.")
    roles = ensure_roles(db)
    user = User(
        public_code=f"PVC-{uuid4().hex[:8].upper()}",
        name=payload.name,
        email=email,
        password_hash=hash_password(payload.password),
        role_id=roles["METEOROLOGIST"].id,
        email_verified_at=utcnow(),
    )
    db.add(user)
    db.flush()
    record_audit(db, actor=user, action="OWNER_CREATED", target_type="user", target_id=user.id)
    db.commit()
    return user


def main() -> None:
    name = input("Nome: ").strip()
    email = input("E-mail: ").strip()
    password = getpass("Senha (mínimo 6, com maiúscula e caractere especial): ")
    if password != getpass("Confirme a senha: "):
        raise SystemExit("As senhas não coincidem; nenhuma conta foi criada.")
    try:
        payload = RegisterRequest(name=name, email=email, password=password)
    except ValidationError:
        # Nunca imprime a validação: ela contém a senha.
        raise SystemExit("Nome, e-mail ou senha inválidos; nenhuma conta foi criada.") from None
    try:
        with SessionLocal() as db:
            create_owner(db, payload)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print("Conta criada. Entre pela aba Profissional do site.")


if __name__ == "__main__":
    main()
