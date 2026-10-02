"""Canonical PostgreSQL memory facts; LangMem owns no Store."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, Personal


class Memory(Personal, Base):
    __tablename__ = "memories"
    __table_args__ = (
        UniqueConstraint("id", "owner_id"),
        CheckConstraint("version > 0"),
        CheckConstraint("status IN ('active','needs_review','stopped','deleted')"),
        CheckConstraint(
            "claim_type IN ('user_statement','user_feeling',"
            "'system_inference','confirmed_preference')"
        ),
    )
    content: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="active")
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scope: Mapped[str] = mapped_column(String(40), default="personal_memory")
    correction_id: Mapped[str | None] = mapped_column(String(36))
    supersedes_id: Mapped[str | None] = mapped_column(String(36))
    source_snapshot: Mapped[list[dict[str, str | int]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )


class MemoryCandidate(Personal, Base):
    __tablename__ = "memory_candidates"
    __table_args__ = (
        UniqueConstraint("id", "owner_id"),
        UniqueConstraint("job_id", "ordinal"),
        ForeignKeyConstraint(
            ["job_id", "owner_id"], ["background_jobs.id", "background_jobs.owner_id"]
        ),
        ForeignKeyConstraint(["memory_id", "owner_id"], ["memories.id", "memories.owner_id"]),
        CheckConstraint("operation = 'insert'"),
        CheckConstraint("status IN ('saved','invalidated','deleted')"),
    )
    job_id: Mapped[str] = mapped_column(String(36))
    ordinal: Mapped[int] = mapped_column(Integer)
    memory_id: Mapped[str | None] = mapped_column(String(36))
    proposed_content: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(30))
    operation: Mapped[str] = mapped_column(String(20), default="insert")
    status: Mapped[str] = mapped_column(String(20), default="saved")
    generator_version: Mapped[str] = mapped_column(String(100))


class ArtifactSource(Base):
    __tablename__ = "artifact_sources"
    __table_args__ = (
        ForeignKeyConstraint(["memory_id", "owner_id"], ["memories.id", "memories.owner_id"]),
        ForeignKeyConstraint(
            ["grant_id", "owner_id"], ["context_grants.id", "context_grants.owner_id"]
        ),
    )
    memory_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    grant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    grant_version: Mapped[int] = mapped_column(Integer)


class MemorySuppression(Personal, Base):
    __tablename__ = "memory_suppressions"
    __table_args__ = (UniqueConstraint("owner_id", "source_key"),)
    source_key: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(30))
