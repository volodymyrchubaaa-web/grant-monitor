"""Конектор для порталу gov.pl/web/polishaid (Polish Aid / Polska Pomoc, MSZ).

Перевірено вручну (curl):

    GET https://www.gov.pl/web/polishaid

Це офіційна головна сторінка програми польської допомоги розвитку
(Ministerstwo Spraw Zagranicznych), а не окрема сторінка з переліком
конкурсів/грантів. У розмітці (типовий gov.pl/Drupal шаблон) немає
стабільного блоку "картка гранту з дедлайном" — є лише навігаційне меню
(`unit-list-item` — пункти "News", "About Polish Aid", "Partners",
"Where we assist" тощо) і кілька випадкових `<h3 class="title">` блоків
(наприклад "Framework documents", "Annual reports"), які не є переліком
конкурсів. Регекс-парсинг конкретних "оголошень про грант" тут був би
чистим вгадуванням і крихким без реальної повторюваної структури.

Тому цей конектор працює у fallback-режимі "знімок сторінки": завантажує
головну сторінку Polish Aid, знімає HTML-теги регексом, згортає пробіли,
обрізає до ~4000 символів і повертає ОДИН RawItem з
external_id="snapshot". Рішення про наявність у знімку актуального
оголошення про грант/конкурс приймає LLM-екстракція нижче за пайплайном,
а не цей конектор.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

PAGE_URL = "https://www.gov.pl/web/polishaid"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}
SNAPSHOT_MAX_CHARS = 4000

TITLE_RE = re.compile(r"<title[^>]*>(?P<title>.*?)</title>", re.S)


class PolishAidConnector(SourceConnector):
    name = "polishaid_gov_pl"

    def fetch(self) -> list[RawItem]:
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(PAGE_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("gov.pl/web/polishaid request failed: %s", exc)
            return []

        item = self._to_snapshot_item(response.text, str(response.url))
        logger.info("gov.pl/web/polishaid: fetched snapshot")
        return [item]

    def _to_snapshot_item(self, page_html: str, final_url: str) -> RawItem:
        title_match = TITLE_RE.search(page_html)
        title = html.unescape(title_match.group("title").strip()) if title_match else "Polish Aid"

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
