from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import desc, select

from app.dependencies import DbSession
from app.models import EducationalContent
from app.schemas import EducationalContentOut

router = APIRouter(tags=["conteudo"])


@router.get("/education", response_model=list[EducationalContentOut])
def list_educational_content(
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
):
    return list(
        db.scalars(
            select(EducationalContent)
            .where(EducationalContent.published_at <= datetime.now(UTC))
            .order_by(desc(EducationalContent.published_at), EducationalContent.id)
            .offset(offset)
            .limit(limit)
        )
    )
