"""Конектор для розділу "Добірка конкурсів та грантів" на hromady.org
(Всеукраїнська Асоціація ОТГ).

Головна сторінка hromady.org — загальна новинна стрічка Асоціації (новини
законодавства, освіта, децентралізація тощо), яка НЕ підходить для
надійного регекс-парсингу грантів. Але вручну (curl) знайдено й перевірено
окрему рубрику, присвячену саме грантам:

    GET https://hromady.org/category/dobirka-konkursiv-ta-grantiv/[page/N/]

Кожен запис — блок `<article class="list post-{id} ...">` із датою у
`<div class="time_ago"><span>...</span></div>`, заголовком у
`<a href="..."><h2>...</h2></a>` і коротким описом у `<p>...</p>` секції
`<section class="post-content">`. Розмітка WordPress-подібна із
семантичними класами, але без офіційного API — перевірено вручну.
Пагінація підтверджена curl-ом (page/2/ повертає HTTP 200 з новими
записами). Парсинг регекс-базований і крихкий до змін верстки — якщо
структура зміниться, зламається тільки цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://hromady.org/category/dobirka-konkursiv-ta-grantiv/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

BLOCK_RE = re.compile(
    r'<article class="list post-\d+[^"]*"[^>]*id="post-(?P<id>\d+)">.*?'
    r'<div class="time_ago"><span>(?P<date>[^<]+)</span></div>\s*'
    r'<a href="(?P<href>[^"]+)"[^>]*><h2>(?P<title>.*?)</h2></a>\s*'
    r'<p>(?P<desc>.*?)</p>',
    re.S,
)


class HromadyGrantsConnector(SourceConnector):
    name = "hromady_org"

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
        except httpx.HTTPError as exc:
            logger.warning("hromady.org request failed: %s", exc)
            return items

        logger.info("hromady.org: fetched %d grant items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem:
        url = m.group("href")
        external_id = m.group("id")
        title = html.unescape(re.sub(r"\s+", " ", m.group("title").strip()))
        desc = html.unescape(m.group("desc").strip())
        desc = re.sub(r"\s+", " ", desc)
        date = m.group("date").strip()

        raw_text_parts = [
            title,
            f"Дата публікації: {date}",
            desc,
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
