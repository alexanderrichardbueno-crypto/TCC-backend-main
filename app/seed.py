from datetime import UTC, datetime

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import EducationalContent, Role, User
from app.security import hash_password

ROLES = {
    "USER": "Usuário",
    "METEOROLOGIST": "Meteorologista",
}
PREVOTS = "https://prevots.org/tempo-severo/"
DEFESA_CIVIL = "https://www.gov.br/mdr/pt-br/assuntos/protecao-e-defesa-civil"
EDUCATION = [
    (
        "EDU-TEMPO-SEVERO",
        "O que é tempo severo",
        "Tempo severo é o conjunto de fenômenos ligados a tempestades convectivas capazes de "
        "causar danos: rajadas de vento acima de 80 km/h, granizo maior que 2 cm ou acumulado, "
        "tornados e chuvas intensas que provocam alagamentos. O Sul, o Sudeste e o Centro-Oeste "
        "do Brasil estão entre as regiões do mundo mais propensas a esses eventos.",
        "/assets/img/edu-tempestade.svg",
        PREVOTS,
    ),
    (
        "EDU-TEMPESTADE",
        "Tempestades: como se proteger",
        "Permaneça em local coberto e afaste-se de janelas. Não procure abrigo sob árvores, "
        "evite campos abertos e desligue aparelhos da tomada antes da chegada dos raios. "
        "Acompanhe os avisos oficiais e as orientações da Defesa Civil (199).",
        "/assets/img/edu-tempestade.svg",
        DEFESA_CIVIL,
    ),
    (
        "EDU-GRANIZO",
        "Granizo: reduza os danos",
        "O granizo pode quebrar vidros e telhas, ferir pessoas e destruir plantações. Abrigue-se "
        "em local fechado, fique longe de janelas e claraboias e, se possível, guarde o veículo "
        "em local coberto antes da tempestade. Nunca saia para proteger bens durante a queda.",
        "/assets/img/edu-granizo.svg",
        PREVOTS,
    ),
    (
        "EDU-RAJADAS",
        "Rajadas de vento: o que fazer",
        "Rajadas fortes derrubam árvores, postes e estruturas leves. Antes da tempestade, prenda "
        "objetos soltos. Durante o evento, fique longe de árvores, muros, placas e fios caídos. "
        "Ao dirigir, reduza a velocidade e não pare sob árvores ou viadutos.",
        "/assets/img/edu-vento.svg",
        DEFESA_CIVIL,
    ),
    (
        "EDU-TORNADO",
        "Tornados: onde se abrigar",
        "Ao receber um alerta de tornado, vá imediatamente para o cômodo mais interno e baixo da "
        "construção, longe de portas e janelas, e proteja a cabeça e o pescoço. Não fique em "
        "veículos ou estruturas leves e nunca tente filmar ou seguir o fenômeno.",
        "/assets/img/edu-tornado.svg",
        PREVOTS,
    ),
    (
        "EDU-ALAGAMENTO",
        "Chuva intensa e alagamentos",
        "Nunca atravesse uma via alagada a pé ou de veículo: a água esconde buracos, correnteza "
        "e redes elétricas. Procure locais altos, desligue a energia se a água entrar em casa e "
        "ligue 199 (Defesa Civil) ou 193 (Bombeiros) em caso de risco.",
        "/assets/img/edu-alagamento.svg",
        DEFESA_CIVIL,
    ),
]


def ensure_roles(db) -> dict[str, Role]:
    roles = {}
    for code, display_name in ROLES.items():
        role = db.scalar(select(Role).where(Role.code == code))
        if not role:
            role = Role(code=code, display_name=display_name)
            db.add(role)
            db.flush()
        elif role.display_name != display_name:
            role.display_name = display_name
        roles[code] = role
    return roles


def ensure_owner(db, roles, settings) -> None:
    """RF03: a conta do dono já entra no banco com o acesso de meteorologista."""
    if not settings.owner_email or not settings.owner_password:
        return
    email = settings.owner_email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        return
    db.add(
        User(
            public_code="PVC-DONO0001",
            name=settings.owner_name,
            email=email,
            password_hash=hash_password(settings.owner_password),
            role_id=roles["METEOROLOGIST"].id,
            email_verified_at=datetime.now(UTC),
        )
    )


def ensure_education(db) -> None:
    published_at = datetime.now(UTC)
    for source_key, title, body, media_url, reference_url in EDUCATION:
        item = db.scalar(
            select(EducationalContent).where(EducationalContent.source_key == source_key)
        )
        if item:
            item.title, item.body = title, body
            item.media_url, item.reference_url = media_url, reference_url
            continue
        db.add(
            EducationalContent(
                source_key=source_key,
                title=title,
                body=body,
                media_url=media_url,
                reference_url=reference_url,
                published_at=published_at,
            )
        )


def main():
    with SessionLocal() as db:
        roles = ensure_roles(db)
        ensure_owner(db, roles, get_settings())
        ensure_education(db)
        db.commit()


if __name__ == "__main__":
    main()
