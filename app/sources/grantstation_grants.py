"""Конектор для сторінки grantstation.com/ukraine-funding (GrantStation).

Перевірено вручну (curl -I): запит на цільову сторінку повертає HTTP 302
редирект на форму входу:

    GET https://grantstation.com/ukraine-funding
    -> 302 Location: https://grantstation.com/user/login?destination=/ukraine-funding

Тобто сторінка з переліком грантів для України на GrantStation закрита
платною реєстрацією/авторизацією (Drupal-based paywall) — публічного
контенту з переліком грантів без логіну немає. Стабільної розмітки
"картки гранту" для регекс-парсингу отримати неможливо, оскільки без
авторизації сайт завжди віддає сторінку логіну.

Тому цей конектор працює у fallback-режимі "знімок сторінки": завантажує
URL (httpx автоматично проходить редирект), знімає HTML-теги регексом,
згортає пробіли, обрізає до ~4000 символів і повертає ОДИН RawItem з
external_id="snapshot". На практиці це буде знімок сторінки логіну (заголовок
"Log in | GrantStation") — подальше рішення про наявність там актуального
гранту приймає LLM-екстракція нижче за пайплайном, а не цей конектор;
якщо GrantStation колись відкриє публічний доступ до /ukraine-funding,
знімок автоматично почне містити реальний контент сторінки.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

PAGE_URL = "https://grantstation.com/ukraine-funding"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}
SNAPSHOT_MAX_CHARS = 4000

TITLE_RE = re.compile(r"<title[^>]*>(?P<title>.*?)</title>", re.S)


class GrantStationConnector(SourceConnector):
    name = "grantstation_com"

    def fetch(self) -> list[RawItem]:
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(PAGE_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("grantstation.com request failed: %s", exc)
            return []

        item = self._to_snapshot_item(response.text, str(response.url))
        logger.info("grantstation.com: fetched snapshot (final url: %s)", response.url)
        return [item]

    def _to_snapshot_item(self, page_html: str, final_url: str) -> RawItem:
        title_match = TITLE_RE.search(page_html)
        title = html.unescape(title_match.group("title").strip()) if title_match else "GrantStation"

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
