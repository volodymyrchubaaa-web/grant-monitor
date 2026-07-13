"""Конектор для EBRD (Європейський банк реконструкції та розвитку) — сторінка Україна.

Сторінка https://www.ebrd.com/ukraine.html — країнова сторінка EBRD по
Україні. Публічно доступна без авторизації, офіційного JSON API немає —
перевірено вручну (curl):

    GET https://www.ebrd.com/ukraine.html

На сторінці кілька блоків "related content" (кейс-стаді, новини, посилання
на розділи сайту): кожен запис — `<article class="related-content__single
-card-wrapper ..." ...>...</article>` з заголовком у
`<h3 class="related-content__title">`, описом у
`<div class="related-content__text ...">`, і посиланням у
`<a href="..." ... class="related-content__btn-wrapper ...">`. Перевірено
вручну (curl) — станом на момент розробки 12 таких карток на сторінці
(більшість — кейс-стаді про вплив EBRD в Україні, кілька — навігаційні
посилання на розділи "Donor Partnerships" / "Project financing enquiries"
тощо). Парсинг двоетапний: спершу regex виділяє кожен `<article>...
</article>` блок повністю, потім усередині нього окремими regex шукаються
title/desc/href — це надійніше за один великий regex, бо порядок і
наявність підблоків (label, дата) варіюється між картками.

Це не прямий реєстр "відкритих грантів", а огляд діяльності EBRD в
Україні — downstream LLM-екстракція вирішує, чи є в конкретному записі
щось релевантне (наприклад, нова кредитна лінія чи донорська програма).
Розмітка сучасна (Adobe AEM / кастомний EBRD DXP), парсинг регекс-базований
і крихкий до змін верстки — якщо структура зміниться, зламається тільки
цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://www.ebrd.com/ukraine.html"
BASE_URL = "https://www.ebrd.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

ARTICLE_RE = re.compile(
    r'<article class="related-content__single-card-wrapper[^"]*"[^>]*>(?P<body>.*?)</article>',
    re.S,
)
TITLE_RE = re.compile(r'<h3 class="related-content__title">(?P<title>.*?)</h3>', re.S)
DESC_RE = re.compile(
    r'<div class="related-content__text(?:\s[^"]*)?"[^>]*>(?P<desc>.*?)</div>', re.S
)
HREF_RE = re.compile(
    r'<a href="(?P<href>[^"]+)"[^>]*class="related-content__btn-wrapper', re.S
)
LABEL_RE = re.compile(
    r'<p class="related-content__text-label"[^>]*>(?P<label>[^<]*)</p>', re.S
)


class EbrdConnector(SourceConnector):
    name = "ebrd_ukraine"

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(LIST_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("EBRD Ukraine request failed: %s", exc)
            return items

        seen_urls: set[str] = set()
        for m in ARTICLE_RE.finditer(response.text):
            item = self._to_raw_item(m.group("body"))
            if item is not None and item.url not in seen_urls:
                seen_urls.add(item.url)
                items.append(item)

        logger.info("EBRD Ukraine: fetched %d content cards", len(items))
        return items

    def _to_raw_item(self, body: str) -> RawItem | None:
        title_m = TITLE_RE.search(body)
        href_m = HREF_RE.search(body)
        if not title_m or not href_m:
            return None
        desc_m = DESC_RE.search(body)
        label_m = LABEL_RE.search(body)

        title = html.unescape(re.sub(r"\s+", " ", title_m.group("title")).strip())
        desc = (
            html.unescape(re.sub(r"\s+", " ", desc_m.group("desc")).strip()) if desc_m else ""
        )
        label = html.unescape(label_m.group("label").strip()) if label_m else ""
        href = href_m.group("href")
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        external_id = url.rstrip("/").rsplit("/", 1)[-1]

        raw_text_parts = [
            title,
            f"Категорія: {label}" if label else "",
            desc,
            f"Повний текст: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"label": label},
        )
