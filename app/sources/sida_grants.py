"""Конектор для SIDA (Swedish International Development Cooperation Agency).

Головна сторінка https://www.sida.se/en — перевірено вручну (curl):

    GET https://www.sida.se/en

Це загальна головна сторінка організації (Nuxt.js SPA з серверним
рендерингом), а НЕ виділена сторінка з переліком грантів/тендерів. Вміст —
меню, блоки "Our partners" (`class="info-card"`) з посиланнями на статичні
розділи типу "Civil society organisations" / "Multilateral organisations",
новинний слайдер тощо — жодного стабільного повторюваного блоку типу
"call for proposals" з датою/дедлайном не знайдено. Спроба регекс-парсингу
карток `info-card` дає лише навігаційні посилання на розділи сайту, а не
конкретні оголошення, тому змушений regex-парсинг був би крихким і
малокорисним.

Тому цей конектор працює у fallback-режимі "знімок сторінки": завантажує
головну сторінку, знімає HTML-теги, згортає пробіли, обрізає до ~4000
символів і повертає ОДИН `RawItem` з `external_id="snapshot"`. Чи є на
сторінці на момент конкретного опитування щось релевантне (наприклад,
анонс нової програми для України) — вирішує downstream LLM-екстракція,
а не цей конектор.
"""
from __future__ import annotations

import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

PAGE_URL = "https://www.sida.se/en"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}
MAX_TEXT_LEN = 4000

TITLE_RE = re.compile(r"<title>(?P<title>.*?)</title>", re.S)


class SidaConnector(SourceConnector):
    name = "sida_ukraine"

    def fetch(self) -> list[RawItem]:
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(PAGE_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("SIDA request failed: %s", exc)
            return []

        html_text = response.text
        title_m = TITLE_RE.search(html_text)
        title = title_m.group("title").strip() if title_m else "Sida"

        text = re.sub(r"<[^>]+>", " ", html_text)
        text = re.sub(r"\s+", " ", text).strip()[:MAX_TEXT_LEN]

        item = RawItem(
            source=self.name,
            external_id="snapshot",
            url=PAGE_URL,
            title=title,
            raw_text=f"{title}\n\n{text}\n\nПовний текст: {PAGE_URL}",
            metadata={"mode": "page_snapshot"},
        )
        logger.info("SIDA: fetched 1 page snapshot item")
        return [item]
