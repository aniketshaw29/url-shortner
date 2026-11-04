from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.timeutils import utc_now_ts


class Owner(Base):
    __tablename__ = "owners"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=utc_now_ts)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("owners.id", ondelete="CASCADE"), nullable=False
    )
    key_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=utc_now_ts)
    last_used_at: Mapped[int | None] = mapped_column(Integer)
    revoked_at: Mapped[int | None] = mapped_column(Integer)


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (
        CheckConstraint("length(code) BETWEEN 3 AND 30", name="ck_links_code_len"),
        CheckConstraint("code NOT GLOB '*[^0-9A-Za-z_-]*'", name="ck_links_code_chars"),
        CheckConstraint("length(long_url) BETWEEN 1 AND 2048", name="ck_links_long_url_len"),
        CheckConstraint("status IN ('active', 'blocked', 'deleted')", name="ck_links_status"),
        Index("links_owner_created_idx", "owner_id", "created_at"),
        Index(
            "links_expiry_idx",
            "expires_at",
            sqlite_where=text("status = 'active' AND expires_at IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    long_url: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("owners.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=utc_now_ts)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=utc_now_ts)
    expires_at: Mapped[int | None] = mapped_column(Integer)
    deleted_at: Mapped[int | None] = mapped_column(Integer)


class Click(Base):
    __tablename__ = "clicks"
    __table_args__ = (
        Index("clicks_link_time_idx", "link_id", "clicked_at"),
        Index("clicks_time_idx", "clicked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id", ondelete="CASCADE"), nullable=False)
    clicked_at: Mapped[int] = mapped_column(Integer, nullable=False)
    ip_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    user_agent: Mapped[str | None] = mapped_column(Text)
    referrer: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(2))


class LinkDailyStat(Base):
    __tablename__ = "link_daily_stats"

    link_id: Mapped[int] = mapped_column(
        ForeignKey("links.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_hll: Mapped[bytes | None] = mapped_column(LargeBinary)


class LinkReferrerDailyStat(Base):
    __tablename__ = "link_referrer_daily_stats"

    link_id: Mapped[int] = mapped_column(
        ForeignKey("links.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    referrer: Mapped[str] = mapped_column(Text, primary_key=True)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
