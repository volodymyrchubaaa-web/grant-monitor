from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Grant(Base):
    __tablename__ = "grants"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    # Походження
    source: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(256))
    url: Mapped[str] = mapped_column(String(1024))

    # Витягнуті LLM поля
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")
    sector: Mapped[str] = mapped_column(String(256), default="")
    location_raw: Mapped[str] = mapped_column(String(512), default="")
    applicant_type_raw: Mapped[str] = mapped_column(String(512), default="")
    amount_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(16), default="")
    deadline: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    # Результати матчингу (pipeline/match.py)
    is_lviv_relevant: Mapped[bool] = mapped_column(Boolean, default=False)
    is_oms_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_partner_org: Mapped[bool] = mapped_column(Boolean, default=False)
    partner_org_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    partner_org_contact: Mapped[str | None] = mapped_column(String(512), nullable=True)
    partner_org_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Скоринг (pipeline/score.py) — заглушка, доопрацьовується пізніше
    success_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability_rationale: Mapped[str] = mapped_column(Text, default="")

    # Методологія заявки (pipeline/methodology.py)
    application_tips: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reframing_bad: Mapped[str | None] = mapped_column(Text, nullable=True)
    reframing_good: Mapped[str | None] = mapped_column(Text, nullable=True)
    reframing_soft_components: Mapped[list | None] = mapped_column(JSON, nullable=True)
    theory_of_change: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    logframe_indicator: Mapped[str | None] = mapped_column(Text, nullable=True)
    logframe_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Службові поля
    raw_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="new")  # new | reviewed | archived
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
