from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class GrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    url: str
    title: str
    description: str
    sector: str
    location_raw: str
    applicant_type_raw: str
    amount_min: float | None
    amount_max: float | None
    currency: str
    deadline: dt.datetime | None
    is_lviv_relevant: bool
    is_oms_eligible: bool
    needs_partner_org: bool
    partner_org_name: str | None
    partner_org_contact: str | None
    partner_org_url: str | None
    success_probability: float | None
    probability_rationale: str
    status: str
    fetched_at: dt.datetime


class RefreshResult(BaseModel):
    fetched: int
    saved: int
    updated: int
    skipped: int
