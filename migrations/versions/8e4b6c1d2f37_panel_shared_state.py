"""Shared state for the meteorologists' panel (replaces the browser localStorage).

Revision ID: 8e4b6c1d2f37
Revises: 3b6f82078bcf
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e4b6c1d2f37"
down_revision: str | None = "3b6f82078bcf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("professional_registry", sa.String(40), nullable=True))

    with op.batch_alter_table("weather_alerts") as batch:
        batch.add_column(sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("weather_reports") as batch:
        batch.add_column(sa.Column("report_type", sa.String(24), nullable=True))
        batch.add_column(sa.Column("location_name", sa.String(160), nullable=True))

    op.create_table(
        "map_areas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("alert_type", sa.String(40), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("polygon", sa.JSON(), nullable=False),
        sa.Column(
            "alert_id",
            sa.Integer(),
            sa.ForeignKey("weather_alerts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('FORECAST', 'ALERT')", name="ck_map_area_kind"),
        sa.CheckConstraint(
            "(kind = 'FORECAST' AND level BETWEEN 0 AND 4 AND alert_type IS NULL) OR "
            "(kind = 'ALERT' AND level IS NULL AND alert_type IN ('SEVERE_STORM', 'TORNADO'))",
            name="ck_map_area_details",
        ),
    )

    op.create_table(
        "map_publications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "published_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_map_publications_published", "map_publications", ["published_at"])

    op.create_table(
        "city_risk_overrides",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("levels", sa.JSON(), nullable=False),
        sa.Column("valid_on", sa.String(10), nullable=False),
        sa.Column(
            "updated_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("city", name="uq_city_risk_override_city"),
    )

    op.create_table(
        "panel_notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("message", sa.String(200), nullable=False),
        sa.Column("target", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("reach", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "alert_id",
            sa.Integer(),
            sa.ForeignKey("weather_alerts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('INFO', 'WARNING', 'EMERGENCY')", name="ck_panel_notification_kind"
        ),
    )
    op.create_index("ix_panel_notifications_created", "panel_notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_panel_notifications_created", table_name="panel_notifications")
    op.drop_table("panel_notifications")
    op.drop_table("city_risk_overrides")
    op.drop_index("ix_map_publications_published", table_name="map_publications")
    op.drop_table("map_publications")
    op.drop_table("map_areas")
    with op.batch_alter_table("weather_reports") as batch:
        batch.drop_column("location_name")
        batch.drop_column("report_type")
    with op.batch_alter_table("weather_alerts") as batch:
        batch.drop_column("deleted_at")
        batch.drop_column("closed_at")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("professional_registry")
