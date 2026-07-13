"""Конектор для порталу реєстру відновлення DREAM (dream.gov.ua) — fallback
snapshot mode.

Перевірено вручну (curl):

    GET https://dream.gov.ua/

Сервер віддає лише HTML-каркас Next.js-застосунку
(`<div id="__next"><div>Loading DREAM...</div></div>`, скрипти з
`/_next/static/chunks/...`) без жодного серверно-рендереного контенту —
увесь список проєктів/конкурсів довантажується клієнтським JavaScript через
внутрішнє API вже в браузері. У відповіді curl немає жодного стабільного
"картка проєкту" блоку, який можна було б регекс-парсити без ризику
постійних хибних спрацювань.

Тому для цього джерела реалізовано fallback "знімок сторінки": весь HTML
очищується від тегів, пробіли згортаються, текст обрізається до ~4000
символів і повертається ОДИН `RawItem` з `external_id="snapshot"`. Заголовок
береться з `<title>` (якщо є) або з назви сайту. Чи є на
серверно-відданій сторінці щось релевантне грантам/відновленню — вирішує
подальша LLM-екстракція в пайплайні, а не цей конектор. Якщо в майбутньому
буде знайдено стабільний публічний API DREAM для списку проєктів — його
варто підключити тут замість snapshot-режиму.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

PAGE_URL = "https://dream.gov.ua/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}
SNAPSHOT_MAX_CHARS = 4000

TITLE_RE = re.compile(r"<title[^>]*>(?P<title>.*?)</title>", re.S | re.I)


class DreamGrantsConnector(SourceConnector):
    name = "dream_gov_ua"

    def fetch(self) -> list[RawItem]:
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(PAGE_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("dream.gov.ua request failed: %s", exc)
            return []

        item = self._to_snapshot_item(response.text)
        logger.info("dream.gov.ua: fetched 1 snapshot item (fallback mode)")
        return [item]

    def _to_snapshot_item(self, page_html: str) -> RawItem:
        title_m = TITLE_RE.search(page_html)
        title = html.unescape(title_m.group("title").strip()) if title_m else "DREAM — реєстр відновлення"

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
