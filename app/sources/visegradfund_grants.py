"""Конектор для сторінки apply/grants/ на visegradfund.org (International Visegrad Fund).

Сторінка публікує перелік грантових програм Фонду (Visegrad Grants,
Visegrad+ Grants, Strategic Grants, V4 Gen Mini Grants тощо), кожна — з
датою відкриття наступного конкурсу і коротким описом. Публічно доступний
без авторизації, офіційного JSON API немає — перевірено вручну (curl):

    GET https://www.visegradfund.org/apply/grants/

Розмітка сучасна (React/Tailwind, серверний рендер): кожна програма — блок
`<article class="... rounded-lg ...">` з назвою у `<h3 ...><span
class="block ...">Частина 1</span><span class="block ...">Частина 2</span>
</h3>`, статусом дедлайну у сусідньому `<span ...>Opens/Deadline ...</span>`,
описом у `<p ...>...</p>` і посиланням "Learn more" `<a ... href="...">`.
Кількість програм невелика (фіксований набір, без пагінації) — сторінка
одна. Парсинг регекс-базований і крихкий до змін верстки — якщо структура
зміниться, зламається тільки цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

PAGE_URL = "https://www.visegradfund.org/apply/grants/"
BASE_URL = "https://www.visegradfund.org"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

ITEM_RE = re.compile(
    r'<article class="[^"]*rounded-lg[^"]*">.*?'
    r'<h3[^>]*>(?P<title_html>.*?)</h3>\s*'
    r'<div[^>]*>\s*<span[^>]*>(?P<status>[^<]*)</span>\s*</div>.*?'
    r'<p[^>]*>(?P<desc>.*?)</p>\s*'
    r'<a[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<cta>[^<]*)',
    re.S,
)


class VisegradFundConnector(SourceConnector):
    name = "visegradfund_org"

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(PAGE_URL)
                response.raise_for_status()
                matches = list(ITEM_RE.finditer(response.text))
                items.extend(self._to_raw_item(m) for m in matches)
        except httpx.HTTPError as exc:
            logger.warning("visegradfund.org request failed: %s", exc)
            return items

        logger.info("visegradfund.org: fetched %d grant programme items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem:
        href = m.group("href")
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        external_id = url.rstrip("/").rsplit("/", 1)[-1]

        title_raw = re.sub(r"<[^>]+>", " ", m.group("title_html"))
        title = html.unescape(re.sub(r"\s+", " ", title_raw).strip())
        status = html.unescape(m.group("status").strip())
        desc = html.unescape(re.sub(r"\s+", " ", m.group("desc")).strip())

        raw_text_parts = [
            title,
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
            metadata={"status_raw": status},
        )
