"""Заглушка евристичної оцінки ймовірності успіху заявки.

Це навмисно спрощена версія для MVP — просто зважує кілька відомих на
момент матчингу факторів. Модель має бути переглянута в наступній
ітерації (наприклад, з урахуванням історичних даних про подані заявки,
конкуренції за програмою тощо).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.pipeline.extract import GrantDraft
from app.pipeline.match import MatchResult


@dataclass
class ScoreResult:
    success_probability: float
    rationale: str


def score(draft: GrantDraft, match_result: MatchResult) -> ScoreResult:
    reasons: list[str] = []
    value = 0.5  # база

    if match_result.is_lviv_relevant:
        value += 0.15
        reasons.append("географічно релевантний (+0.15)")
    else:
        value -= 0.2
        reasons.append("географічна релевантність не підтверджена (-0.2)")

    if match_result.is_oms_eligible:
        value += 0.15
        reasons.append("ОМС є прийнятним заявником (+0.15)")
    elif match_result.needs_partner_org:
        value -= 0.1
        reasons.append("потрібен організація-партнер для подачі (-0.1)")

    if draft.sector != "інше":
        value += 0.1
        reasons.append(f"відповідає стратегічному напрямку «{draft.sector}» (+0.1)")

    value = max(0.0, min(1.0, value))
    rationale = "MVP-евристика (потребує доопрацювання): " + "; ".join(reasons)
    return ScoreResult(success_probability=round(value, 2), rationale=rationale)
