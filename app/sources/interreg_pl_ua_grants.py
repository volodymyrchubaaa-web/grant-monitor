"""Конектор для розділу новин програми Interreg NEXT Poland–Ukraine 2021-2027.

Головна сторінка pl-ua.eu/en/ — це посадкова сторінка з навігаційними
картками (не список публікацій), тож перевірено вручну (curl), що реальний
потік новин і оголошень (включно з "Calls open for Small Projects Funds"
тощо) знаходиться на окремій сторінці:

    GET https://pl-ua.eu/en/news/[page/N/]

Розмітка сучасна (WordPress-тема), кожен запис — блок
`<li class="news-list-wrapper__list__item"><a href="...">` з датою
публікації у `<small class="card-success-story__date">DD.MM.YYYY</small>`
і заголовком у `<h3 id="cardTitlePlc1">...</h3>`. Пагінація стандартна —
`/en/news/page/N/` (перевірено, сторінка 2 повертає ще 20 записів з тим
самим блоком). Парсинг регекс-базований і крихкий до змін верстки — якщо
структура зміниться, зламається тільки цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://pl-ua.eu/en/news/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

ITEM_RE = re.compile(
    r'<li class="news-list-wrapper__list__item">\s*'
    r'<a href="(?P<href>[^"]+)"[^>]*>.*?'
    r'<small class="card-success-story__date">(?P<date>[^<]*)</small>.*?'
    r'<h3[^>]*>\s*(?P<title>.*?)\s*</h3>',
    re.S,
)


class InterregPlUaConnector(SourceConnector):
    name = "interreg_pl_ua"

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
            logger.warning("pl-ua.eu request failed: %s", exc)
            return items

        logger.info("pl-ua.eu: fetched %d news/call items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem:
        url = m.group("href")
        external_id = url.rstrip("/").rsplit("/", 1)[-1]
        title = html.unescape(re.sub(r"\s+", " ", m.group("title")).strip())
        date = m.group("date").strip()

        raw_text_parts = [
            title,
            f"Дата публікації: {date}",
            f"Повний текст: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"published_raw": date},
        )
