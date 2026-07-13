"""Конектор для SDC (Swiss Agency for Development and Cooperation) — Україна.

Сторінка https://www.eda.admin.ch/deza/en/home/countries/ukraine.html —
перевірено вручну (curl):

    GET https://www.eda.admin.ch/deza/en/home/countries/ukraine.html

Сайт швейцарського МЗС (eda.admin.ch) захищений Akamai і повертає
"Access Denied" (HTTP 403) на будь-який запит без валідної browser-сесії —
перевірено вручну (curl, з різними User-Agent, включно з реалістичним
Chrome UA): результат стабільно 403, тіло відповіді — сторінка-заглушка
Akamai (~425 байт), жодного реального контенту сторінки отримати
неможливо. Тому регекс-парсинг реальної розмітки об'єктивно неможливий
навіть у fallback-режимі "знімок сторінки" — Akamai блокує ще до віддачі
HTML.

Конектор реалізований у тому самому fallback-режимі "знімок сторінки", що
і решта загальних org-сторінок у цьому пакеті (щоб легко почав працювати,
якщо блокування колись зніметься або пайплайн запуститься з іншої IP/
інфраструктури): завантажує сторінку, знімає HTML-теги, обрізає до ~4000
символів, повертає ОДИН `RawItem`. Якщо сайт повертає помилку (403/5xx/
timeout) — конектор логує попередження і повертає порожній список, це
очікувана поведінка для цього джерела на момент розробки.
"""
from __future__ import annotations

import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

PAGE_URL = "https://www.eda.admin.ch/deza/en/home/countries/ukraine.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}
MAX_TEXT_LEN = 4000

TITLE_RE = re.compile(r"<title>(?P<title>.*?)</title>", re.S)


class SdcConnector(SourceConnector):
    name = "sdc_ukraine"

    def fetch(self) -> list[RawItem]:
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(PAGE_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "SDC Ukraine request failed (сайт відомо блокує Akamai-захистом "
                "запити без браузерної сесії — стабільно 403): %s",
                exc,
            )
            return []

        html_text = response.text
        title_m = TITLE_RE.search(html_text)
        title = title_m.group("title").strip() if title_m else "SDC Ukraine"

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
        logger.info("SDC Ukraine: fetched 1 page snapshot item")
        return [item]
