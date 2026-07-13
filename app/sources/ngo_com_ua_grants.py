"""Конектор для рубрики "Фонди та гранти" на ngo.com.ua.

Головна сторінка ngo.com.ua змішує загальні статті про НГО (поради, факти,
історії успіху) з оголошеннями про гранти в одній верстці (`vl-post-item`),
що ненадійно для точкового парсингу саме грантів. У навігації знайдено й
вручну перевірено (curl) окрему рубрику, що містить власне грантові
оголошення:

    GET https://ngo.com.ua/category/fondy-ta-granty/[page/N/]

Ця сторінка на WordPress використовує іншу (архівну) верстку теми: кожен
запис — `<article>` із блоком `<div class="ht-post-wrapper">`, датою у
`<div class="ht-post-date"><div class="ht-month">...</div><div class="ht-day">
...</div><div class="ht-year">...</div></div>`, заголовком у
`<h3 class="entry-title"><a href="..." rel="bookmark">...</a></h3>` і
анонсом у `<div class="entry-content">...</div><!-- .entry-content -->`.
Пагінація підтверджена curl-ом (`/page/2/`, `/page/5/` існують і повертають
HTTP 200). Парсинг регекс-базований і крихкий до змін верстки — якщо
структура зміниться, зламається тільки цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://ngo.com.ua/category/fondy-ta-granty/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

BLOCK_RE = re.compile(
    r'<div class="ht-post-date">\s*<div class="ht-month">(?P<month>[^<]+)</div>\s*'
    r'<div class="ht-day">(?P<day>[^<]+)</div>\s*<div class="ht-year">(?P<year>[^<]+)</div>\s*</div>.*?'
    r'<h3 class="entry-title"><a href="(?P<href>[^"]+)" rel="bookmark">(?P<title>.*?)</a></h3>.*?'
    r'<div class="entry-content">\s*(?P<desc>.*?)\s*</div><!-- .entry-content -->',
    re.S,
)


class NgoComUaGrantsConnector(SourceConnector):
    name = "ngo_com_ua"

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
            logger.warning("ngo.com.ua request failed: %s", exc)
            return items

        logger.info("ngo.com.ua: fetched %d grant items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem:
        url = m.group("href")
        external_id = url.rstrip("/").rsplit("/", 1)[-1]
        title = html.unescape(re.sub(r"\s+", " ", m.group("title").strip()))
        desc = html.unescape(m.group("desc").strip())
        desc = re.sub(r"\s+", " ", desc)
        date = f"{m.group('day').strip()} {m.group('month').strip()} {m.group('year').strip()}"

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
