"""Align the data model with the project document.

Single professional role, no reports, no push records, no demonstration data, severe
forecasts with a 30-minute edit window and e-mail codes.

Revision ID: c7d3f1a90e22
Revises: 8e4b6c1d2f37
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d3f1a90e22"
down_revision: str | None = "8e4b6c1d2f37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def remove_demonstration_data() -> None:
    bind = op.get_bind()
    demo_alerts = "SELECT id FROM weather_alerts WHERE origin = 'DEMO' OR is_demo = :yes"
    demo_users = "SELECT id FROM users WHERE public_code LIKE 'DEMO-%'"
    for statement in (
        f"DELETE FROM alert_reads WHERE alert_id IN ({demo_alerts})",
        f"DELETE FROM alert_reviews WHERE alert_id IN ({demo_alerts})",
        f"DELETE FROM map_areas WHERE alert_id IN ({demo_alerts})",
        f"DELETE FROM panel_notifications WHERE alert_id IN ({demo_alerts})",
        # Sem subconsulta: o MySQL não aceita selecionar da tabela que está apagando.
        "DELETE FROM weather_alerts WHERE origin = 'DEMO' OR is_demo = :yes",
    ):
        bind.execute(sa.text(statement), {"yes": True})
    bind.execute(sa.text("DELETE FROM forecasts WHERE source_key LIKE 'DEMO-%'"))
    bind.execute(sa.text("DELETE FROM educational_contents WHERE source_key LIKE 'DEMO-%'"))
    bind.execute(
        sa.text(f"UPDATE audit_events SET actor_id = NULL WHERE actor_id IN ({demo_users})")
    )
    bind.execute(
        sa.text(f"UPDATE forecasts SET created_by = NULL WHERE created_by IN ({demo_users})")
    )
    bind.execute(sa.text(f"UPDATE news SET author_id = NULL WHERE author_id IN ({demo_users})"))
    bind.execute(sa.text(f"DELETE FROM alert_reads WHERE user_id IN ({demo_users})"))
    bind.execute(sa.text("DELETE FROM users WHERE public_code LIKE 'DEMO-%'"))


def merge_admin_role() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE users SET role_id = (SELECT id FROM roles WHERE code = 'METEOROLOGIST'), "
            "token_version = token_version + 1 "
            "WHERE role_id = (SELECT id FROM roles WHERE code = 'ADMIN')"
        )
    )
    bind.execute(sa.text("DELETE FROM roles WHERE code = 'ADMIN'"))


def upgrade() -> None:
    remove_demonstration_data()
    merge_admin_role()

    op.drop_table("panel_notifications")
    op.drop_table("map_publications")
    op.drop_table("map_areas")
    op.drop_table("city_risk_overrides")
    op.drop_table("weather_reports")

    with op.batch_alter_table("weather_alerts") as batch:
        batch.drop_constraint("ck_alert_origin", type_="check")
        batch.drop_column("is_demo")
        batch.create_check_constraint("ck_alert_origin", "origin IN ('MANUAL', 'INMET')")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("professional_registry")

    op.create_table(
        "severe_forecasts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("polygon", sa.JSON(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("level BETWEEN 0 AND 4", name="ck_severe_forecast_level"),
        sa.CheckConstraint("valid_until > issued_at", name="ck_severe_forecast_validity"),
    )
    op.create_index("ix_severe_forecasts_valid", "severe_forecasts", ["valid_until"])
    op.create_table(
        "account_codes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("purpose IN ('VERIFY_EMAIL', 'RESET_PASSWORD')", name="ck_code_purpose"),
    )
    op.create_index("ix_account_codes_user_purpose", "account_codes", ["user_id", "purpose"])


def downgrade() -> None:
    raise NotImplementedError("Esta migração remove dados e não pode ser revertida.")
