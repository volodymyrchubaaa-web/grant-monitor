"""Конектор для EU Funding & Tenders Portal.

Використовує публічний пошуковий API порталу (не офіційно задокументований,
але стабільно застосовується сторонніми інтеграціями — Apify-скрапери,
EMDESK). Ендпоінт та форма відповіді перевірені вручну (curl) під час
планування:

    POST https://api.tech.ec.europa.eu/search-api/prod/rest/search
         ?apiKey=SEDIA&text=<query>&pageSize=<n>&pageNumber=<n>

Перевірено вручну (curl) під час планування та повторно під час імплементації:

1. Параметр `query` (bool/terms-фільтр за type/status) у тілі запиту API
   ІГНОРУЄ — офіційного способу відфільтрувати "тільки відкриті виклики"
   без публічної документації API знайти не вдалося.
2. Пошук працює як full-text relevance-search по ВСЬОМУ контенту порталу
   (включно з подіями, тендерами, архівом документів з 2016+ року), тому
   для вузьких ключових слів найрелевантнішими часто виявляються СТАРІ,
   вже закриті виклики (в них ключове слово згадується найчастіше).

Тому фільтрація на клієнті лишається такою:
- URL що містить "/topicDetails/" -> це грантова тема (topic), а не тендер/подія
- metadata.language[0] == "en" -> уникаємо дублікатів тієї ж теми іншими мовами

А ось "чи ще відкритий цей грант" — НЕ фільтрується тут (щоб не губити
записи через relevance-упередженість пошуку), а обчислюється нижче за
пайплайном у app/pipeline/match.py на основі поля deadline. Дашборд і API
дозволяють фільтрувати за статусом.

Якщо EC змінить поведінку ендпоінта — правити тільки цей файл, решта
пайплайну не залежить від деталей API.
"""
from __future__ import annotations

import datetime as dt
import json
import logging

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"

# Ключові слова для пошуку тем, релевантних територіальній громаді:
# місцеве самоврядування, інфраструктура, МСП, довкілля, цифровізація.
# MVP: один загальний запит; у наступних ітераціях можна розбити на кілька
# запитів по секторах зі config.strategic_sectors.
DEFAULT_QUERY = (
    "local authorities municipality Ukraine infrastructure environment "
    "SME digitalisation"
)


class EUFundingPortalConnector(SourceConnector):
    name = "eu_funding_tenders_portal"

    def __init__(self, query: str = DEFAULT_QUERY, page_size: int = 50) -> None:
        self.query = query
        self.page_size = page_size

    def fetch(self) -> list[RawItem]:
        try:
            payload = self._search()
        except httpx.HTTPError as exc:
            logger.warning("EU Funding Portal request failed: %s", exc)
            return []

        items: list[RawItem] = []
        seen_call_ids: set[str] = set()

        for result in payload.get("results", []):
            url = result.get("url", "")
            if "/topicDetails/" not in url:
                continue  # пропускаємо тендери/події/новини — лишаємо тільки грантові теми

            metadata = result.get("metadata", {})
            if _first(metadata.get("language")) != "en":
                continue  # уникаємо мовних дублікатів однієї теми

            call_id = _first(metadata.get("callIdentifier")) or _first(metadata.get("identifier"))
            if not call_id or call_id in seen_call_ids:
                continue
            seen_call_ids.add(call_id)

            items.append(self._to_raw_item(result, metadata, call_id))

        logger.info("EU Funding Portal: fetched %d relevant topics", len(items))
        return items

    def _search(self) -> dict:
        params = {
            "apiKey": "SEDIA",
            "text": self.query,
            "pageSize": self.page_size,
            "pageNumber": 1,
        }
        # Тіло надсилається для сумісності з API, хоча фільтр type/status
        # наразі клієнт ігнорує (див. докстрінг файлу).
        body = {"query": {"bool": {"must": [{"terms": {"type": ["1", "2"]}}]}}}
        with httpx.Client(timeout=20) as client:
            response = client.post(SEARCH_URL, params=params, json=body)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _latest_deadline(metadata: dict) -> str | None:
        """Багатоетапні виклики мають кілька дедлайнів у списку — беремо
        найпізніший як орієнтир "до коли грант ще актуальний"."""
        raw_values = metadata.get("deadlineDate") or []
        parsed: list[dt.datetime] = []
        for raw in raw_values:
            try:
                parsed.append(dt.datetime.fromisoformat(raw.replace("Z", "+00:00")))
            except (ValueError, AttributeError):
                continue
        if not parsed:
            return None
        return max(parsed).isoformat()

    @classmethod
    def _to_raw_item(cls, result: dict, metadata: dict, call_id: str) -> RawItem:
        title = _first(metadata.get("title")) or result.get("summary", "")
        deadline = cls._latest_deadline(metadata)
        raw_text_parts = [
            title,
            f"Budget: {_first(metadata.get('budget'))} {_first(metadata.get('currency'))}",
            f"Deadline: {deadline}",
            f"Framework programme: {_first(metadata.get('frameworkProgramme'))}",
            f"Beneficiary administration: {_first(metadata.get('beneficiaryAdministration'))}",
            f"Geographical zones: {_first(metadata.get('geographicalZones'))}",
        ]
        return RawItem(
            source=EUFundingPortalConnector.name,
            external_id=call_id,
            url=result.get("url", ""),
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={
                "budget": _first(metadata.get("budget")),
                "currency": _first(metadata.get("currency")),
                "deadlineDate": deadline,
                "geographicalZones": _first(metadata.get("geographicalZones")),
                "beneficiaryAdministration": metadata.get("beneficiaryAdministration", []),
                "frameworkProgramme": _first(metadata.get("frameworkProgramme")),
                "raw_metadata_json": json.dumps(metadata, ensure_ascii=False)[:4000],
            },
        )


def _first(value: list | None) -> str | None:
    if not value:
        return None
    return value[0]
