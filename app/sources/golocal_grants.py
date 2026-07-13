"""Конектор для каталогу "Програми" на hranty-dlya-hromad.golocal-ukraine.com
(GoLocal — гранти для громад).

Каталог грантових програм для територіальних громад. Публічно доступний без
авторизації, офіційного JSON API немає — перевірено вручну (curl):

    GET https://hranty-dlya-hromad.golocal-ukraine.com/programy/

Список побудований на JetEngine/Elementor listing-grid: кожна програма — блок
`<div class="jet-listing-grid__item jet-listing-dynamic-post-{id}"
data-post-id="{id}">` з посиланням у вкладеному
`data-url="..."`, назвою у `<h2 class="elementor-heading-title
elementor-size-default">...</h2>` і кількома короткими текстовими віджетами
(статус, категорія, регіон) одразу після заголовка. Розмітка Elementor-важка
й без стабільних класів для полів метаданих, тому для опису беремо весь
текстовий вміст блоку (з обрізаними тегами) замість точкового парсингу
окремих полів.

Перевірено curl-ом: `/programy/page/2/` повертає HTTP 200, але з ІДЕНТИЧНИМ
набором `data-post-id` (список рендериться повністю на першій сторінці,
пагінація на сайті — клієнтський JetSmartFilters AJAX, а не серверний
`?page=`). Тому конектор дедуплікує записи за `external_id` між "сторінками"
і не повертає одні й ті самі оголошення двічі.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://hranty-dlya-hromad.golocal-ukraine.com/programy/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

ITEM_SPLIT_RE = re.compile(
    r'(?=<div class="jet-listing-grid__item jet-listing-dynamic-post-\d+" data-post-id="\d+" >)'
)
HEADER_RE = re.compile(
    r'data-post-id="(?P<id>\d+)"[^>]*><div class="jet-engine-listing-overlay-wrap" '
    r'data-url="(?P<url>[^"]+)"'
)
TITLE_RE = re.compile(
    r'<h2 class="elementor-heading-title elementor-size-default">(?P<title>.*?)</h2>',
    re.S,
)
TAG_RE = re.compile(r"<[^>]+>")


class GoLocalGrantsConnector(SourceConnector):
    name = "golocal_ukraine"

    def __init__(self, max_pages: int = 2) -> None:
        self.max_pages = max_pages

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        seen_ids: set[str] = set()
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                for page in range(1, self.max_pages + 1):
                    url = LIST_URL if page == 1 else f"{LIST_URL}page/{page}/"
                    response = client.get(url)
                    if response.status_code == 404:
                        break
                    response.raise_for_status()
                    chunks = ITEM_SPLIT_RE.split(response.text)[1:]
                    if not chunks:
                        break
                    new_count = 0
                    for chunk in chunks:
                        item = self._to_raw_item(chunk)
                        if item is None or item.external_id in seen_ids:
                            continue
                        seen_ids.add(item.external_id)
                        items.append(item)
                        new_count += 1
                    if new_count == 0:
                        # Сайт віддає ту саму сторінку на будь-який page/N/.
                        break
        except httpx.HTTPError as exc:
            logger.warning("golocal-ukraine.com request failed: %s", exc)
            return items

        logger.info("golocal-ukraine.com: fetched %d grant items", len(items))
        return items

    def _to_raw_item(self, chunk: str) -> RawItem | None:
        header = HEADER_RE.search(chunk)
        title_m = TITLE_RE.search(chunk)
        if not header or not title_m:
            return None

        external_id = header.group("id")
        url = header.group("url")
        title = html.unescape(re.sub(r"\s+", " ", title_m.group("title").strip()))

        # Опис/статус/категорія — беремо весь текст блоку (без тегів, без
        # <style>) як компактний контекст для подальшої LLM-екстракції.
        chunk_no_style = re.sub(r"<style>.*?</style>", " ", chunk, flags=re.S)
        text = TAG_RE.sub(" ", chunk_no_style)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        text = text[:2000]

        raw_text_parts = [
            title,
            text,
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
