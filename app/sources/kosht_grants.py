"""Конектор для головної сторінки практичного медіа про гроші kosht.media.

Українське медіа про особисті фінанси й економіку, час від часу публікує
новини про гранти, державні виплати та програми підтримки бізнесу поряд із
загальними фінансовими новинами. Публічно доступний без авторизації,
офіційного JSON API немає — перевірено вручну (curl):

    GET https://kosht.media/

Розмітка сучасна (Tailwind-класи), кожен запис у блоках "Вибір редакції по
категоріях" — `<li class="rounded-xl border border-koshtGrey ...">
<a href="..." class="p-5 w-full h-full block ...">` з заголовком у
`<h2 class="font-unbounded text-[18px] ...">...</h2>` і датою публікації у
`<time datetime="ISO" ...>DD.MM.YYYY</time>`.

Пагінація: `/page/2/` віддає 200 OK, але перевірено вручну — повертається
той самий шаблон головної сторінки з тим самим набором посилань, що й на
`/page/1/` (це кастомний Next-подібний домашній шаблон, а не WP-архів із
реальною пагінацією). Тому `fetch()` завжди читає лише головну сторінку і
не йде по неіснуючих "наступних" сторінках.

Парсинг регекс-базований (двоетапний: спершу блок `<li>`, потім поля
всередині) і крихкий до змін верстки — якщо структура зміниться, зламається
тільки цей файл. Матеріал видає загальні фінансові новини головної
сторінки; чи є серед них актуальна грантова пропозиція, вирішує подальша
LLM-екстракція, а не цей конектор.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://kosht.media/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

CARD_RE = re.compile(
    r'<li class="rounded-xl border border-koshtGrey[^"]*">\s*'
    r'<a href="(?P<href>[^"]+)" class="p-5[^"]*">(?P<body>.*?)</a>\s*</li>',
    re.S,
)
TITLE_RE = re.compile(r'<h2[^>]*>\s*(?P<title>.*?)\s*</h2>', re.S)
TIME_RE = re.compile(r'<time datetime="(?P<dt>[^"]+)"[^>]*>\s*(?P<dtxt>[^<]*?)\s*</time>')


class KoshtGrantsConnector(SourceConnector):
    name = "kosht_media"

    def __init__(self, max_pages: int = 2) -> None:
        # Сайт не має реальної пагінації для головної сторінки (перевірено
        # вручну), параметр залишено для сумісності інтерфейсу з іншими
        # конекторами, але fetch() завжди читає лише сторінку 1.
        self.max_pages = max_pages

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(LIST_URL)
                response.raise_for_status()
                matches = list(CARD_RE.finditer(response.text))
                seen_urls: set[str] = set()
                for m in matches:
                    if m.group("href") in seen_urls:
                        continue
                    seen_urls.add(m.group("href"))
                    item = self._to_raw_item(m)
                    if item is not None:
                        items.append(item)
        except httpx.HTTPError as exc:
            logger.warning("kosht.media request failed: %s", exc)
            return items

        logger.info("kosht.media: fetched %d items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem | None:
        url = m.group("href")
        body = m.group("body")
        title_m = TITLE_RE.search(body)
        if not title_m:
            return None
        title = html.unescape(title_m.group("title").strip())
        title = re.sub(r"\s+", " ", title)

        time_m = TIME_RE.search(body)
        published = time_m.group("dtxt").strip() if time_m else ""

        external_id = url.rstrip("/").rsplit("/", 1)[-1]

        raw_text_parts = [
            title,
            f"Дата публікації: {published}" if published else "",
            f"Повний текст: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"published_raw": published},
        )
