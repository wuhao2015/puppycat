"""Add Planner Agent job status fields to plan generations.

Revision ID: 0003_plan_generation_status
Revises: 0002_plan_generations
Create Date: 2026-09-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003_plan_generation_status"
down_revision: Union[str, None] = "0002_plan_generations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_plan_generations_status",
        "plan_generations",
        type_="check",
    )
    op.add_column(
        "plan_generations",
        sa.Column(
            "stage",
            sa.String(),
            server_default=sa.text("'understanding'"),
            nullable=False,
        ),
    )
    op.add_column(
        "plan_generations",
        sa.Column(
            "step_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "plan_generations",
        sa.Column(
            "tool_call_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "plan_generations",
        sa.Column("clarification_question", sa.String(), nullable=True),
    )
    op.create_check_constraint(
        "ck_plan_generations_status",
        "plan_generations",
        "status IN ('queued', 'running', 'needs_input', 'succeeded', 'failed')",
    )
    op.create_check_constraint(
        "ck_plan_generations_stage",
        "plan_generations",
        "stage IN ('understanding', 'resolving_destination', "
        "'searching_places', 'drafting', 'verifying')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE plan_generations SET status = 'failed', "
        "error_code = 'plan_generation_failed', "
        "error_message = 'Plan generation requires more information' "
        "WHERE status = 'needs_input'"
    )
    op.drop_constraint(
        "ck_plan_generations_stage",
        "plan_generations",
        type_="check",
    )
    op.drop_constraint(
        "ck_plan_generations_status",
        "plan_generations",
        type_="check",
    )
    op.drop_column("plan_generations", "clarification_question")
    op.drop_column("plan_generations", "tool_call_count")
    op.drop_column("plan_generations", "step_count")
    op.drop_column("plan_generations", "stage")
    op.create_check_constraint(
        "ck_plan_generations_status",
        "plan_generations",
        "status IN ('queued', 'running', 'succeeded', 'failed')",
    )
