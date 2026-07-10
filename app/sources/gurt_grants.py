"""Конектор для розділу "Гроші" (гранти) на gurt.org.ua (ГУРТ).

Ресурсний центр ГУРТ веде агрегований дайджест-стрічку можливостей для
третього сектору — розділ /news/grants/ змішує в одній стрічці гранти,
вакансії, тендери та власні дайджести ГУРТа, кожен запис позначений
кольоровим бейджем-міткою. Публічно доступний без авторизації, офіційного
JSON API немає — перевірено вручну (curl):

    GET https://gurt.org.ua/news/grants/[?page=N]

Розмітка — стара табличну верстка (WordPress-тема без семантичних класів),
кожен запис — блок `<h2><a href="/news/grants/ID/">...</a></h2>` з
опціональним бейджем-`<span title="...">` перед заголовком ("Грант",
"Вакансія", "Тендер" або "Матеріал ГУРТа" для зведених дайджестів), датою
в сусідньому `<span>` і описом у `<div class="newstxt">`. Оскільки стрічка
змішує різні типи матеріалів, беремо лише записи з бейджем "ГРАНТ" —
вакансії, тендери та дайджести-огляди відфільтровуються. Парсинг
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

LIST_URL = "https://gurt.org.ua/news/grants/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

BLOCK_RE = re.compile(
    r'<h2>\s*<a href="(?P<href>/news/grants/\d+/)">\s*'
    r'(?:<span[^>]*title="[^"]*">\s*(?P<badge>[^<]*)</span>\s*)?'
    r'(?P<title_html>.*?)</a>\s*</h2>.*?'
    r'<span[^>]*>(?P<date>[\d.]+)</span>.*?'
    r'<div class="newstxt"[^>]*>(?P<desc>.*?)<a class="readnext"',
    re.S,
)

ACCEPTED_BADGES = {"ГРАНТ"}


class GurtGrantsConnector(SourceConnector):
    name = "gurt_org_ua"

    def __init__(self, max_pages: int = 2) -> None:
        self.max_pages = max_pages

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                for page in range(1, self.max_pages + 1):
                    url = LIST_URL if page == 1 else f"{LIST_URL}?page={page}"
                    response = client.get(url)
                    if response.status_code == 404:
                        break
                    response.raise_for_status()
                    matches = list(BLOCK_RE.finditer(response.text))
                    if not matches:
                        break
                    for m in matches:
                        badge = (m.group("badge") or "").strip()
                        if badge not in ACCEPTED_BADGES:
                            continue
                        items.append(self._to_raw_item(m))
        except httpx.HTTPError as exc:
            logger.warning("gurt.org.ua request failed: %s", exc)
            return items

        logger.info("gurt.org.ua: fetched %d grant items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem:
        url = "https://gurt.org.ua" + m.group("href")
        external_id = m.group("href").strip("/").rsplit("/", 1)[-1]
        title_raw = re.sub(r"<[^>]+>", " ", m.group("title_html"))
        title = html.unescape(re.sub(r"\s+", " ", title_raw).strip())
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
