"""LLM-екстракція структурованих полів гранту з сирого тексту оголошення.

Використовує Claude (Anthropic API) через tool-use, щоб отримати надійний
JSON замість парсингу вільного тексту відповіді.
"""
from __future__ import annotations

import datetime as dt
import logging

from anthropic import Anthropic
from pydantic import BaseModel

from app.config import settings
from app.sources.base import RawItem

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

EXTRACT_TOOL = {
    "name": "record_grant_fields",
    "description": "Зберегти структуровані поля, витягнуті з оголошення про грант.",
    "input_schema": {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Стислий опис гранту українською, 2-4 речення: що фінансує, для кого.",
            },
            "sector": {
                "type": "string",
                "description": "Найближчий сектор/напрямок зі списку стратегічних напрямків громади, або 'інше'.",
            },
            "location_raw": {
                "type": "string",
                "description": "Географічна прийнятність гранту як вказано в джерелі (країна/регіон/зона).",
            },
            "applicant_type_raw": {
                "type": "string",
                "description": "Типи заявників, які прийнятні, як вказано в джерелі.",
            },
            "applicant_category": {
                "type": "string",
                "enum": [
                    "local_authority_eligible",
                    "local_authority_not_eligible",
                    "unclear",
                ],
                "description": (
                    "local_authority_eligible - орган місцевого самоврядування (ОМС) "
                    "може подати заявку самостійно або як партнер; "
                    "local_authority_not_eligible - заявником може бути лише "
                    "неурядова/недержавна організація (ГО, БФ, приватна компанія тощо), "
                    "ОМС не є прийнятним заявником; unclear - з тексту не зрозуміло."
                ),
            },
            "amount_min": {"type": ["number", "null"]},
            "amount_max": {"type": ["number", "null"]},
            "currency": {"type": "string"},
            "deadline": {
                "type": ["string", "null"],
                "description": "Дедлайн подачі заявки у форматі YYYY-MM-DD, якщо вказаний.",
            },
        },
        "required": [
            "description",
            "sector",
            "location_raw",
            "applicant_type_raw",
            "applicant_category",
            "currency",
        ],
    },
}


class GrantDraft(BaseModel):
    title: str
    description: str = ""
    sector: str = "інше"
    location_raw: str = ""
    applicant_type_raw: str = ""
    applicant_category: str = "unclear"
    amount_min: float | None = None
    amount_max: float | None = None
    currency: str = ""
    deadline: dt.datetime | None = None


def extract(item: RawItem) -> GrantDraft:
    """Викликає Claude для перетворення RawItem у структурований GrantDraft.

    При помилці API повертає мінімальний GrantDraft із заголовком, щоб
    пайплайн не падав повністю через збій одного оголошення.
    """
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY не задано — пропускаю LLM-екстракцію для %s", item.external_id)
        return GrantDraft(title=item.title)

    client = Anthropic(api_key=settings.anthropic_api_key)
    sectors_list = "\n".join(f"- {s}" for s in settings.strategic_sectors)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=[EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "record_grant_fields"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Проаналізуй оголошення про грант нижче і виклич "
                        "record_grant_fields з витягнутими полями.\n\n"
                        f"Стратегічні напрямки громади (для поля sector):\n{sectors_list}\n\n"
                        f"Заголовок: {item.title}\n"
                        f"Джерело: {item.source}\n"
                        f"URL: {item.url}\n\n"
                        f"Текст оголошення:\n{item.raw_text}"
                    ),
                }
            ],
        )
    except Exception:  # noqa: BLE001 — не даємо збою одного запису зупинити весь fetch
        logger.exception("LLM-екстракція не вдалася для %s", item.external_id)
        return GrantDraft(title=item.title)

    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        logger.warning("Claude не повернув tool_use для %s", item.external_id)
        return GrantDraft(title=item.title)

    data = dict(tool_use.input)
    data["title"] = item.title

    deadline_raw = data.get("deadline")
    if deadline_raw:
        try:
            data["deadline"] = dt.datetime.fromisoformat(deadline_raw)
        except ValueError:
            data["deadline"] = None

    return GrantDraft(**data)
