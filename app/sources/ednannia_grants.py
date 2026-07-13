"""Конектор для розділу "Грантові конкурси" на ednannia.ua (Єднання).

Головна сторінка ednannia.ua — загальна новинна стрічка (заголовок сторінки
<title>Новини — Єднання</title>), що НЕ підходить для надійного
per-item регекс-парсингу грантів. Але в навігації знайдено й вручну
перевірено (curl) окрему сторінку зі списком поточних грантових конкурсів:

    GET https://ednannia.ua/tryvaiut-hrantovi-konkursy[?start=N]

Сайт на Joomla (без офіційного API): кожен запис — блок
`<div class="item column-1">` з посиланням-заголовком у `<h2><a href="...">
...</a></h2>` і (не завжди присутнім) коротким описом одразу після заголовка,
до коментаря `<!-- <a class="mod-articles-readmore" ... -->`. Посилання
відносні (`/tryvaiut-hrantovi-konkursy/...`) — конектор доклеює домен.

Пагінація в Joomla реалізована через `?start=N` (перевірено curl-ом:
`?start=12` повертає HTTP 200, хоч на момент перевірки сторінка з 12
записами була останньою — далі йде порожній список). Розмітка не має
явних /page/2/ посилань у HTML, тому параметр зсуву обчислюється за
кількістю записів на сторінці (12). Парсинг регекс-базований і крихкий
до змін верстки — якщо структура зміниться, зламається тільки цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

BASE_URL = "https://ednannia.ua"
LIST_URL = "https://ednannia.ua/tryvaiut-hrantovi-konkursy"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}
ITEMS_PER_PAGE = 12

BLOCK_RE = re.compile(
    r'<div class="item column-1">\s*<h2>\s*<a href="(?P<href>[^"]+)">\s*'
    r'(?P<title>.*?)</a>\s*</h2>\s*'
    r'(?P<desc>.*?)<!-- <a class="mod-articles-readmore"',
    re.S,
)


class EdnanniaGrantsConnector(SourceConnector):
    name = "ednannia_ua"

    def __init__(self, max_pages: int = 2) -> None:
        self.max_pages = max_pages

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                for page in range(1, self.max_pages + 1):
                    start = (page - 1) * ITEMS_PER_PAGE
                    url = LIST_URL if start == 0 else f"{LIST_URL}?start={start}"
                    response = client.get(url)
                    if response.status_code == 404:
                        break
                    response.raise_for_status()
                    matches = list(BLOCK_RE.finditer(response.text))
                    if not matches:
                        break
                    items.extend(self._to_raw_item(m) for m in matches)
        except httpx.HTTPError as exc:
            logger.warning("ednannia.ua request failed: %s", exc)
            return items

        logger.info("ednannia.ua: fetched %d grant items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem:
        href = m.group("href")
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        external_id = url.rstrip("/").rsplit("/", 1)[-1]
        title = html.unescape(re.sub(r"\s+", " ", m.group("title").strip()))
        desc = html.unescape(m.group("desc").strip())
        desc = re.sub(r"\s+", " ", desc)

        raw_text_parts = [
            title,
            desc,
            f"Повний текст: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={},
        )
