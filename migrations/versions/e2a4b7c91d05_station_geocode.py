"""IBGE municipality code of each station, used to fetch its latest measurement.

Revision ID: e2a4b7c91d05
Revises: c7d3f1a90e22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2a4b7c91d05"
down_revision: str | None = "c7d3f1a90e22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("weather_stations", sa.Column("geocode", sa.String(length=7), nullable=True))


def downgrade() -> None:
    op.drop_column("weather_stations", "geocode")
