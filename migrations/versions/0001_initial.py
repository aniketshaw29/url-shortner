"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owners",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column(
            "created_at",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("(unixepoch())"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=32), nullable=False),
        sa.Column("key_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("(unixepoch())"),
        ),
        sa.Column("last_used_at", sa.Integer(), nullable=True),
        sa.Column("revoked_at", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )

    op.create_table(
        "links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("long_url", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("(unixepoch())"),
        ),
        sa.Column(
            "updated_at",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("(unixepoch())"),
        ),
        sa.Column("expires_at", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.Integer(), nullable=True),
        sa.CheckConstraint("length(code) BETWEEN 3 AND 30", name="ck_links_code_len"),
        sa.CheckConstraint("code NOT GLOB '*[^0-9A-Za-z_-]*'", name="ck_links_code_chars"),
        sa.CheckConstraint("length(long_url) BETWEEN 1 AND 2048", name="ck_links_long_url_len"),
        sa.CheckConstraint("status IN ('active', 'blocked', 'deleted')", name="ck_links_status"),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("links_owner_created_idx", "links", ["owner_id", "created_at"], unique=False)
    op.create_index(
        "links_expiry_idx",
        "links",
        ["expires_at"],
        unique=False,
        sqlite_where=sa.text("status = 'active' AND expires_at IS NOT NULL"),
    )

    op.create_table(
        "clicks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("clicked_at", sa.Integer(), nullable=False),
        sa.Column("ip_hash", sa.LargeBinary(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("clicks_link_time_idx", "clicks", ["link_id", "clicked_at"], unique=False)
    op.create_index("clicks_time_idx", "clicks", ["clicked_at"], unique=False)

    op.create_table(
        "link_daily_stats",
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_hll", sa.LargeBinary(), nullable=True),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("link_id", "day"),
    )

    op.create_table(
        "link_referrer_daily_stats",
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("referrer", sa.Text(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("link_id", "day", "referrer"),
    )


def downgrade() -> None:
    op.drop_table("link_referrer_daily_stats")
    op.drop_table("link_daily_stats")
    op.drop_index("clicks_time_idx", table_name="clicks")
    op.drop_index("clicks_link_time_idx", table_name="clicks")
    op.drop_table("clicks")
    op.drop_index("links_expiry_idx", table_name="links")
    op.drop_index("links_owner_created_idx", table_name="links")
    op.drop_table("links")
    op.drop_table("api_keys")
    op.drop_table("owners")
