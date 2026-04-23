from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.db.base import Base


class Master(Base):
    __tablename__ = "masters"
    __table_args__ = (
        Index(
            "ix_masters_catalog",
            "is_public",
            "blocked_at",
            postgresql_where=text("blocked_at IS NULL AND is_public = true"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="Asia/Yerevan")
    work_hours: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    breaks: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    slot_step_min: Mapped[int] = mapped_column(Integer, nullable=False, server_default="20")
    auto_confirm: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="ru")
    decision_timeout_min: Mapped[int] = mapped_column(Integer, nullable=False, server_default="120")
    slug: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        default=lambda: f"master-{uuid4().hex[:6]}",
    )
    specialty_text: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    blocked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    salon_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("salons.id", ondelete="SET NULL"),
        nullable=True,
    )
    past_slugs: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    slug_changed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("duration_min > 0", name="ck_services_duration_positive"),
        Index(
            "ix_services_master_active",
            "master_id",
            postgresql_where=text("active = true"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    master_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("masters.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    price_amd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("master_id", "phone", name="uq_clients_master_phone"),
        Index(
            "ix_clients_master_tg",
            "master_id",
            "tg_id",
            postgresql_where=text("tg_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    master_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("masters.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    tg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


APPT_STATUSES = ("pending", "confirmed", "rejected", "cancelled", "completed", "no_show")
APPT_SOURCES = ("client_request", "master_manual")
APPT_CANCELLERS = ("client", "master", "system")


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("status IN " + str(APPT_STATUSES), name="ck_appointments_status"),
        CheckConstraint("source IN " + str(APPT_SOURCES), name="ck_appointments_source"),
        CheckConstraint(
            "cancelled_by IS NULL OR cancelled_by IN " + str(APPT_CANCELLERS),
            name="ck_appointments_cancelled_by",
        ),
        Index("ix_appointments_master_start", "master_id", "start_at"),
        Index(
            "ix_appointments_pending_deadline",
            "status",
            "decision_deadline",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "uq_appointment_slot",
            "master_id",
            "start_at",
            unique=True,
            postgresql_where=text("status IN ('pending', 'confirmed')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    master_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("masters.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    service_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("services.id"), nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    decision_deadline: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(Text, nullable=True)


REMINDER_KINDS = ("day_before", "two_hours", "master_before")
REMINDER_CHANNELS = ("telegram", "sms")


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint("kind IN " + str(REMINDER_KINDS), name="ck_reminders_kind"),
        CheckConstraint("channel IN " + str(REMINDER_CHANNELS), name="ck_reminders_channel"),
        UniqueConstraint("appointment_id", "kind", name="uq_reminders_appointment_kind"),
        Index(
            "ix_reminders_pending_send_at",
            "send_at",
            postgresql_where=text("sent = false"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    appointment_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
    )
    send_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False, server_default="telegram")
    sent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint(
            "(used_by_tg_id IS NULL) = (used_at IS NULL) "
            "AND (used_at IS NULL) = (used_for_master_id IS NULL)",
            name="ck_invites_usage_tuple",
        ),
        CheckConstraint(
            "kind IN ('master', 'salon_owner')",
            name="ck_invites_kind",
        ),
        Index("ix_invites_code", "code"),
        Index("ix_invites_creator", "created_by_tg_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    created_by_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used_by_tg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    used_for_master_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("masters.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'master'"))
    salon_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("salons.id", ondelete="CASCADE"),
        nullable=True,
    )


class Salon(Base):
    __tablename__ = "salons"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    owner_tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    logo_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    blocked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
