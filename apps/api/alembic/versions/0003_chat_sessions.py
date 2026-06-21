"""chat-first trips: profiles, trip sessions

Revision ID: 0003_chat_sessions
Revises: 0002_user_password
Create Date: 2026-06-19

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_chat_sessions"
down_revision: Union[str, None] = "0002_user_password"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Profile: nationalities for visa grounding.
    op.add_column(
        "users",
        sa.Column(
            "passport_countries",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("users", sa.Column("home_country", sa.String(), nullable=True))

    # Trip becomes a chat session: title + persisted messages, nullable trip facts.
    op.add_column("trips", sa.Column("title", sa.String(), nullable=True))
    op.add_column(
        "trips",
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "trips",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.alter_column("trips", "destination", existing_type=sa.String(), nullable=True)
    op.alter_column("trips", "start_date", existing_type=sa.String(), nullable=True)
    op.alter_column("trips", "end_date", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.alter_column("trips", "end_date", existing_type=sa.String(), nullable=False)
    op.alter_column("trips", "start_date", existing_type=sa.String(), nullable=False)
    op.alter_column("trips", "destination", existing_type=sa.String(), nullable=False)
    op.drop_column("trips", "updated_at")
    op.drop_column("trips", "messages")
    op.drop_column("trips", "title")
    op.drop_column("users", "home_country")
    op.drop_column("users", "passport_countries")
