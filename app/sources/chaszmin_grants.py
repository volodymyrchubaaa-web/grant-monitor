"""Конектор для сторінки "ГРАНТИ 2026" на chaszmin.com.ua (Центр розвитку "Час Змін").

Сторінка /granty-2026/ — постійно оновлюваний каталог актуальних грантових
можливостей (донори, конкурси, стипендії) для громадського сектору й бізнесу.
Публічно доступна без авторизації, офіційного JSON API немає — перевірено
вручну (curl):

    GET https://chaszmin.com.ua/granty-2026/

Усі оголошення (у перевіреній версії — ~300 карток) рендеряться на одній
сторінці (WordPress/Elementor-подібна тема, без /page/N/ пагінації — перевірено
curl-ом, /granty-2026/page/2/ не існує), тому пагінація тут по суті
не потрібна, але параметр max_pages лишений для сумісності з рештою конекторів
і про всяк випадок, якщо сайт додасть пагінацію.

Кожна картка — блок `<div class="col post-item">` із заголовком у
`<a href="..." class="post-title is-large ">`, і коротким описом (з дедлайном
на початку) у `<p class="from_the_blog_excerpt ">...</p>`. Парсинг
регекс-базований і крихкий до змін верстки — якщо структура зміниться,
зламається тільки цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://chaszmin.com.ua/granty-2026/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

BLOCK_RE = re.compile(
    r'<a href="(?P<href>[^"]+)" class="post-title is-large "[^>]*>\s*(?P<title>.*?)\s*</a>.*?'
    r'class="from_the_blog_excerpt ">(?P<desc>.*?)</p>',
    re.S,
)


class ChaszminGrantsConnector(SourceConnector):
    name = "chaszmin_com_ua"

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
                    matches = list(BLOCK_RE.finditer(response.text))
                    if not matches:
                        break
                    items.extend(self._to_raw_item(m) for m in matches)
                    # Сторінка не має пагінації — усі картки вже на першій.
                    if page == 1:
                        break
        except httpx.HTTPError as exc:
            logger.warning("chaszmin.com.ua request failed: %s", exc)
            return items

        logger.info("chaszmin.com.ua: fetched %d grant items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem:
        url = m.group("href")
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
