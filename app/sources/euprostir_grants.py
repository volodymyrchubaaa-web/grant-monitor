"""Конектор для порталу можливостей euprostir.org.ua (fallback snapshot mode).

Перевірено вручну (curl):

    GET https://euprostir.org.ua/

Сервер віддає лише порожній HTML-каркас (~11 КБ) — це Ember.js SPA
(видно з `<meta name="euprostir/config/environment" ...>`, що містить
конфіг для клієнтського рендерингу через API `livarava.com/api/v2`).
Увесь реальний контент (розділ "Можливості"/opportunities з грантами)
довантажується JavaScript'ом у браузері вже ПІСЛЯ завантаження сторінки —
у відповіді curl немає жодного заголовка, опису чи посилання на конкретну
грантову пропозицію, які можна було б стабільно регекс-парсити.

Тому для цього джерела реалізовано fallback "знімок сторінки": весь HTML
очищується від тегів, пробіли згортаються, текст обрізається до ~4000
символів і повертається ОДИН `RawItem` з `external_id="snapshot"`. Заголовок
береться з `<title>`. Чи є на сторінці (чи в її SSR-заглушці) щось
релевантне грантам — вирішує подальша LLM-екстракція в пайплайні, а не цей
конектор.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

PAGE_URL = "https://euprostir.org.ua/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}
SNAPSHOT_MAX_CHARS = 4000

TITLE_RE = re.compile(r"<title[^>]*>(?P<title>.*?)</title>", re.S | re.I)


class EuProstirGrantsConnector(SourceConnector):
    name = "euprostir_org_ua"

    def fetch(self) -> list[RawItem]:
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(PAGE_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("euprostir.org.ua request failed: %s", exc)
            return []

        item = self._to_snapshot_item(response.text)
        logger.info("euprostir.org.ua: fetched 1 snapshot item (fallback mode)")
        return [item]

    def _to_snapshot_item(self, page_html: str) -> RawItem:
        title_m = TITLE_RE.search(page_html)
        title = html.unescape(title_m.group("title").strip()) if title_m else "ЄвроПростір"

        text = re.sub(r"<script.*?</script>", " ", page_html, flags=re.S | re.I)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()[:SNAPSHOT_MAX_CHARS]

        raw_text_parts = [
            title,
            text,
            f"Повний текст: {PAGE_URL}",
        ]
        return RawItem(
            source=self.name,
            external_id="snapshot",
            url=PAGE_URL,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"mode": "snapshot"},
        )
