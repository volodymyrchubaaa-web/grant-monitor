"""Матчинг гранту проти критеріїв громади.

MVP-логіка навмисно проста та детермінована (без додаткового LLM-виклику,
щоб не подвоювати вартість/латентність на кожен запис) — базується на
`applicant_category`, який вже визначив Claude у pipeline/extract.py, та на
пошуку ключових слів локації. Пошук організації-партнера (ГО/БФ) для
needs_partner_org=True записів — наступна ітерація (поле поки заповнюється
як None, тільки прапорець виставляється).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.pipeline.extract import GrantDraft
from app.sources.base import RawItem

LOCATION_KEYWORDS = ("ukraine", "україна", "lviv", "львів", "львівськ")


@dataclass
class MatchResult:
    is_lviv_relevant: bool
    is_oms_eligible: bool
    needs_partner_org: bool
    status: str  # "new" | "needs_review" | "closed"


def match(item: RawItem, draft: GrantDraft) -> MatchResult:
    haystack = " ".join(
        [draft.location_raw or "", item.raw_text or "", item.title or ""]
    ).lower()
    is_lviv_relevant = any(keyword in haystack for keyword in LOCATION_KEYWORDS)

    if draft.applicant_category == "local_authority_eligible":
        is_oms_eligible = True
        needs_partner_org = False
        status = "new"
    elif draft.applicant_category == "local_authority_not_eligible":
        is_oms_eligible = False
        needs_partner_org = True
        status = "new"
    else:  # "unclear"
        is_oms_eligible = False
        needs_partner_org = False
        status = "needs_review"

    # Джерела (напр. EU Funding Portal) можуть повертати вже прострочені
    # виклики через особливості їх пошукового API (див. докстрінг
    # eu_funding_portal.py) — позначаємо це окремим статусом, а не
    # відкидаємо запис, щоб дашборд міг показати/приховати за фільтром.
    if _is_deadline_passed(draft):
        status = "closed"

    return MatchResult(
        is_lviv_relevant=is_lviv_relevant,
        is_oms_eligible=is_oms_eligible,
        needs_partner_org=needs_partner_org,
        status=status,
    )


def _is_deadline_passed(draft: GrantDraft) -> bool:
    if draft.deadline is None:
        return False
    now = dt.datetime.now(draft.deadline.tzinfo) if draft.deadline.tzinfo else dt.datetime.utcnow()
    return draft.deadline < now
