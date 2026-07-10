"""Оркестрація наскрізного пайплайну: fetch -> extract -> match -> score -> save.

Викликається і з APScheduler (фоново), і з POST /api/refresh (вручну).
Щоб додати нове джерело — достатньо додати його екземпляр у SOURCES.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import Grant
from app.pipeline.extract import extract
from app.pipeline.match import match
from app.pipeline.methodology import (
    generate_checklist,
    generate_logframe,
    generate_reframing,
    generate_theory_of_change,
    generate_tips,
)
from app.pipeline.partners import find_partner
from app.pipeline.score import score
from app.sources.base import SourceConnector
from app.sources.decentralization_grants import DecentralizationGrantsConnector
from app.sources.eu_funding_portal import EUFundingPortalConnector
from app.sources.getgrant_grants import GetGrantConnector
from app.sources.gurt_grants import GurtGrantsConnector
from app.sources.prostir_grants import ProstirGrantsConnector

logger = logging.getLogger(__name__)

# Друга ціль пошуку по EU Funding & Tenders Portal — прикордонне/донорське
# співробітництво (Interreg, EU Neighbourhood, відновлення), щоб розширити
# покриття європейських програм окрім загального запиту за замовчуванням.
EU_CROSS_BORDER_QUERY = (
    "cross-border cooperation Interreg Neighbourhood Ukraine recovery "
    "local government reconstruction municipality"
)

SOURCES: list[SourceConnector] = [
    EUFundingPortalConnector(),
    EUFundingPortalConnector(query=EU_CROSS_BORDER_QUERY),
    DecentralizationGrantsConnector(),
    ProstirGrantsConnector(),
    GurtGrantsConnector(),
    GetGrantConnector(),
]


def run_pipeline(db: Session) -> dict[str, int]:
    stats = {"fetched": 0, "saved": 0, "updated": 0, "skipped": 0}

    for connector in SOURCES:
        try:
            raw_items = connector.fetch()
        except Exception:  # noqa: BLE001 — збій одного джерела не має зупиняти інші
            logger.exception("Fetch failed for source %s", connector.name)
            continue

        stats["fetched"] += len(raw_items)

        for item in raw_items:
            try:
                draft = extract(item)
                match_result = match(item, draft)
                score_result = score(draft, match_result)

                existing = (
                    db.query(Grant)
                    .filter_by(source=item.source, external_id=item.external_id)
                    .first()
                )

                if existing:
                    _apply_fields(existing, item, draft, match_result, score_result)
                    stats["updated"] += 1
                else:
                    grant = Grant(source=item.source, external_id=item.external_id)
                    _apply_fields(grant, item, draft, match_result, score_result)
                    db.add(grant)
                    stats["saved"] += 1

                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.exception("Failed to process item %s/%s", item.source, item.external_id)
                stats["skipped"] += 1

    return stats


def _apply_fields(grant: Grant, item, draft, match_result, score_result) -> None:
    grant.url = item.url
    grant.title = draft.title
    grant.description = draft.description
    grant.sector = draft.sector
    grant.location_raw = draft.location_raw
    grant.applicant_type_raw = draft.applicant_type_raw
    grant.amount_min = draft.amount_min
    grant.amount_max = draft.amount_max
    grant.currency = draft.currency
    grant.deadline = draft.deadline
    grant.is_lviv_relevant = match_result.is_lviv_relevant
    grant.is_oms_eligible = match_result.is_oms_eligible
    grant.needs_partner_org = match_result.needs_partner_org
    if match_result.needs_partner_org:
        partner = find_partner(draft.sector, item.raw_text)
        if partner:
            grant.partner_org_name = partner.name
            grant.partner_org_contact = partner.contact
            grant.partner_org_url = partner.website
    grant.success_probability = score_result.success_probability
    grant.probability_rationale = score_result.rationale
    grant.raw_text = item.raw_text
    grant.status = match_result.status

    donor_hint = f"{item.source} {draft.title}"
    reframing = generate_reframing(draft.sector, item.raw_text)
    theory_of_change = generate_theory_of_change(draft.sector, draft.title)
    logframe = generate_logframe(draft.sector)
    grant.application_tips = generate_tips(donor_hint, draft.sector, item.raw_text)
    grant.reframing_bad = reframing.bad
    grant.reframing_good = reframing.good
    grant.reframing_soft_components = reframing.soft_components
    grant.theory_of_change = {
        "problem": theory_of_change.problem,
        "causes": theory_of_change.causes,
        "intervention": theory_of_change.intervention,
        "outputs": theory_of_change.outputs,
        "outcomes": theory_of_change.outcomes,
        "impact": theory_of_change.impact,
    }
    grant.logframe_indicator = logframe.indicator
    grant.logframe_source = logframe.source
    grant.checklist = generate_checklist(
        match_result.needs_partner_org, grant.partner_org_name, reframing
    )
