"""Add persistent asynchronous plan generation jobs.

Revision ID: 0002_plan_generations
Revises: 0001_initial
Create Date: 2026-09-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0002_plan_generations"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plan_generations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("trip_id", sa.String(), nullable=False),
        sa.Column("itinerary_id", sa.String(), nullable=True),
        sa.Column("input_message_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_plan_generations_status",
        ),
        sa.ForeignKeyConstraint(
            ["itinerary_id"],
            ["itineraries.id"],
            name="fk_plan_generations_itinerary_id_itineraries",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name="fk_plan_generations_trip_id_trips",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trip_id",
            "input_message_ts",
            name="uq_plan_generations_trip_input",
        ),
    )
    op.create_index(
        "ix_plan_generations_status",
        "plan_generations",
        ["status"],
    )
    op.create_index(
        "ix_plan_generations_trip_id",
        "plan_generations",
        ["trip_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_plan_generations_trip_id", table_name="plan_generations")
    op.drop_index("ix_plan_generations_status", table_name="plan_generations")
    op.drop_table("plan_generations")
