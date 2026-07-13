"""Конектор для сторінки країни "Ukraine" на giz.de (Deutsche Gesellschaft
für Internationale Zusammenarbeit, GIZ).

Перевірено вручну (curl):

    GET https://www.giz.de/en/worldwide/302.html

Сторінка коректно віддає country-профіль GIZ в Україні (hero-блок з назвою
країни, кількістю комісій — "46 commissions", список PDF-документів для
завантаження). Однак сам перелік проєктів/комісій GIZ в Україні
рендериться на клієнті через React-острівець:
`<div class="js-react-island-project-list" data-country="248"></div>` —
у серверному HTML немає жодного проєкту, тільки порожній контейнер з
data-атрибутом, дані підвантажуються окремим JS/XHR-запитом, URL і формат
якого не задокументовано і не стабільний для регекс-парсингу без
рендерингу браузером. Отже, стабільної повторюваної розмітки "картка
проєкту/гранту" для витягування регексом тут немає.

Тому цей конектор працює у fallback-режимі "знімок сторінки": завантажує
country-сторінку GIZ Ukraine, знімає HTML-теги регексом, згортає пробіли,
обрізає до ~4000 символів і повертає ОДИН RawItem з
external_id="snapshot". Знімок міститиме серверно відрендерений текст
(назву країни, заголовки розділів, назви завантажуваних документів) —
рішення про наявність там актуального гранту/конкурсу приймає
LLM-екстракція нижче за пайплайном, а не цей конектор.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

PAGE_URL = "https://www.giz.de/en/worldwide/302.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}
SNAPSHOT_MAX_CHARS = 4000

TITLE_RE = re.compile(r"<title[^>]*>(?P<title>.*?)</title>", re.S)


class GizUkraineConnector(SourceConnector):
    name = "giz_ukraine"

    def fetch(self) -> list[RawItem]:
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(PAGE_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("giz.de request failed: %s", exc)
            return []

        item = self._to_snapshot_item(response.text, str(response.url))
        logger.info("giz.de: fetched snapshot for Ukraine country page")
        return [item]

    def _to_snapshot_item(self, page_html: str, final_url: str) -> RawItem:
        title_match = TITLE_RE.search(page_html)
        title = html.unescape(title_match.group("title").strip()) if title_match else "GIZ Ukraine"

        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page_html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()[:SNAPSHOT_MAX_CHARS]

        raw_text_parts = [
            title,
            text,
            f"Повний текст: {final_url}",
        ]
        return RawItem(
            source=self.name,
            external_id="snapshot",
            url=final_url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"mode": "snapshot", "requested_url": PAGE_URL},
        )
