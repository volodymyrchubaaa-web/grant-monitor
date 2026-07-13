"""Конектор для розділу "Opportunities" на euneighbourseast.eu (EU NEIGHBOURS east).

EU NEIGHBOURS east — офіційний інформаційний портал програми Східного
партнерства ЄС, розділ /opportunities/ публікує вакансії, гранти, конкурси
та стажування для країн-партнерів (включно з Україною). Публічно доступний
без авторизації, офіційного JSON API немає — перевірено вручну (curl):

    GET https://euneighbourseast.eu/opportunities/[page/N/]

Розмітка сучасна (WordPress + YOOtheme), кожен запис — блок
`<a class="el-item uk-card ..." href="...">` з дедлайном у
`<div class="el-meta uk-text-meta uk-margin-top">CLOSING DATE: ...</div>`,
заголовком у `<h3 class="el-title ...">...</h3>` і коротким описом у
`<div class="el-content ...">...</div>`. Пагінація стандартна —
`/opportunities/page/N/` (посилання на сторінки 2-6+ присутні в розмітці).
Парсинг регекс-базований і крихкий до змін верстки — якщо структура
зміниться, зламається тільки цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://euneighbourseast.eu/opportunities/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

ITEM_RE = re.compile(
    r'<a class="el-item uk-card[^"]*" href="(?P<href>[^"]+)">.*?'
    r'<div class="el-meta uk-text-meta uk-margin-top">(?P<meta>[^<]*)</div>'
    r'<h3 class="el-title[^"]*">\s*(?P<title>.*?)</h3>'
    r'<div class="el-content[^"]*">(?P<desc>.*?)</div>',
    re.S,
)


class EuNeighboursEastConnector(SourceConnector):
    name = "euneighbourseast_eu"

    def __init__(self, max_pages: int = 2) -> None:
        self.max_pages = max_pages

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                for page in range(1, self.max_pages + 1):
                    url = LIST_URL if page == 1 else f"{LIST_URL}page/{page}/"
                    response = client.get(url)
                    if response.status_code == 404:
                        break
                    response.raise_for_status()
                    matches = list(ITEM_RE.finditer(response.text))
                    if not matches:
                        break
                    items.extend(self._to_raw_item(m) for m in matches)
        except httpx.HTTPError as exc:
            logger.warning("euneighbourseast.eu request failed: %s", exc)
            return items

        logger.info("euneighbourseast.eu: fetched %d opportunity items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem:
        url = m.group("href")
        external_id = url.rstrip("/").rsplit("/", 1)[-1]
        title = html.unescape(re.sub(r"\s+", " ", m.group("title")).strip())
        meta = html.unescape(m.group("meta").strip())
        desc = re.sub(r"<[^>]+>", " ", m.group("desc"))
        desc = html.unescape(re.sub(r"\s+", " ", desc).strip())

        raw_text_parts = [
            title,
            meta,
            desc,
            f"Повний текст: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"closing_date_raw": meta},
        )
