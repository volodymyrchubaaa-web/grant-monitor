"""Конектор для розділу "Конкурси та гранти" на irf.ua (Міжнародний фонд
"Відродження").

Розділ /grants/contests/ публікує всі відкриті й нещодавно завершені
конкурси/тендери фонду. Публічно доступний без авторизації, офіційного
JSON API немає — перевірено вручну (curl):

    GET https://www.irf.ua/grants/contests/[page/N/]

Кожен запис — блок `<div class="grid-2 grant-excerpt ...">` (клас
`finished` додається до завершених конкурсів) із посиланням у обгортці
`<a href="...">`, дедлайном у `<time class="date">ЗАВЕРШЕННЯ КОНКУРСУ:
DD.MM, YYYY</time>`, заголовком у `<h2 class="title">`, статусом
(«триває» / «закінчився») у `<div class="grant-meta"><strong>...</strong>`
і коротким описом у `<p>...</p>`. Розмітка сучасна (WordPress, семантичні
класи), пагінація підтверджена curl-ом (`/contests/page/2/` → HTTP 200).
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

LIST_URL = "https://www.irf.ua/grants/contests/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

BLOCK_RE = re.compile(
    r'<div class="grid-2 grant-excerpt[^"]*">\s*'
    r'<a href="(?P<href>[^"]+)">\s*'
    r'<div class="grant-excerpt--top">\s*'
    r'<time class="date">(?P<date>[^<]*)</time>\s*'
    r'<h2 class="title">(?P<title>.*?)</h2>\s*'
    r'</div>\s*'
    r'<div class="grant-excerpt--bottom">\s*'
    r'<div class="grant-meta">\s*(?P<meta_label>[^<]*)\s*<strong>(?P<status>[^<]*)</strong>\s*</div>\s*'
    r'<p>\s*(?P<desc>.*?)\s*</p>',
    re.S,
)


class IRFGrantsConnector(SourceConnector):
    name = "irf_ua"

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
            logger.warning("irf.ua request failed: %s", exc)
            return items

        logger.info("irf.ua: fetched %d grant items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem:
        url = m.group("href")
        external_id = url.rstrip("/").rsplit("/", 1)[-1]
        title = html.unescape(re.sub(r"\s+", " ", m.group("title").strip()))
        desc = html.unescape(m.group("desc").strip())
        desc = re.sub(r"\s+", " ", desc)
        deadline = m.group("date").strip()
        status = m.group("status").strip()

        raw_text_parts = [
            title,
            deadline,
            f"Статус конкурсу: {status}",
            desc,
            f"Повний текст: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"deadline_raw": deadline, "status": status},
        )
