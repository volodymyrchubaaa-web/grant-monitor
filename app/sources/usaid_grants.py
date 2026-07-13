"""Конектор для USAID Ukraine.

Сторінка https://www.usaid.gov/ukraine — перевірено вручну (curl):

    GET https://www.usaid.gov/ukraine

Станом на момент розробки запит стабільно повертає HTTP 404 (Content-Length:
10, тіло "Not found") — перевірено вручну (curl -L -w, з фіналним ефективним
URL таким самим, тобто це не редирект на іншу сторінку, а справжня
відсутня сторінка на боці usaid.gov). Ймовірна причина — реорганізація
структури сайту usaid.gov (сторінки окремих країнових місій неодноразово
переносились/перейменовувались). Оскільки жодного реального HTML для
парсингу немає, регекс-парсинг (як структурований, так і fallback-знімок)
об'єктивно неможливий по цьому URL.

Конектор реалізований у стандартному fallback-режимі "знімок сторінки" —
якщо URL колись знову стане валідним (USAID відновить/перенесе сторінку
на цю адресу), конектор автоматично почне повертати знімок вмісту без
додаткових змін коду. Поки що (404) — логує попередження і повертає
порожній список, це очікувана поведінка для цього джерела на момент
розробки.
"""
from __future__ import annotations

import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

PAGE_URL = "https://www.usaid.gov/ukraine"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}
MAX_TEXT_LEN = 4000

TITLE_RE = re.compile(r"<title>(?P<title>.*?)</title>", re.S)


class UsaidUkraineConnector(SourceConnector):
    name = "usaid_ukraine"

    def fetch(self) -> list[RawItem]:
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(PAGE_URL)
                if response.status_code == 404:
                    logger.warning(
                        "USAID Ukraine: сторінка %s повертає 404 (перевірено вручну, "
                        "не редирект) — сторінку, ймовірно, прибрали/перенесли",
                        PAGE_URL,
                    )
                    return []
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("USAID Ukraine request failed: %s", exc)
            return []

        html_text = response.text
        title_m = TITLE_RE.search(html_text)
        title = title_m.group("title").strip() if title_m else "USAID Ukraine"

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
        logger.info("USAID Ukraine: fetched 1 page snapshot item")
        return [item]
