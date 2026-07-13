"""Конектор для головної сторінки медіа про бізнес vlasnasprava.ua.

Українське медіа про малий і середній бізнес, регулярно публікує новини про
грантові програми та державну підтримку підприємців поряд із загальними
новинами законодавства й економіки. Публічно доступний без авторизації,
офіційного JSON API немає — перевірено вручну (curl):

    GET https://vlasnasprava.ua/[page/N/]

Розмітка — WordPress-тема Ceris: у секції `role="main"` головної сторінки
кожен запис — блок `<article class="post ...">...</article>` із заголовком
у `<h2>`/`<h3 class="post__title ..."><a href="...">...</a></h3>`, датою
публікації у `<time datetime="ISO" ...>DD.MM.YYYY</time>` (перед текстом
дати іноді стоїть іконка `<i class="mdicon mdicon-schedule"></i>`, яку
потрібно пропускати) і категорією у `<a class="... post__cat ..."
href="...">Назва</a>`. Не всі картки мають дату/категорію (деякі варіанти
верстки "great-post" їх не показують) — ці поля опціональні, обов'язкові
лише заголовок і посилання. Пагінація стандартна WordPress
(`/page/N/`) — перевірено, `page/2/` повертає 200 з іншим набором статей.

Парсинг регекс-базований (двоетапний: спершу блок `<article>`, потім поля
всередині) і крихкий до змін верстки — якщо структура зміниться, зламається
тільки цей файл. Матеріал видає всі новини головної сторінки; чи є серед
них актуальна грантова пропозиція, вирішує подальша LLM-екстракція, а не
цей конектор.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://vlasnasprava.ua/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

MAIN_RE = re.compile(r'role="main"', re.S)
ARTICLE_RE = re.compile(r'<article class="post[^"]*"[^>]*>(?P<body>.*?)</article>', re.S)
TITLE_RE = re.compile(
    r'<h[23][^>]*>\s*<a href="(?P<href>[^"]+)">(?P<title>.*?)</a>\s*</h[23]>',
    re.S,
)
TIME_RE = re.compile(
    r'<time[^>]*datetime="(?P<dt>[^"]+)"[^>]*>(?:<i[^>]*></i>)?(?P<dtxt>[^<]*)</time>',
)
CAT_RE = re.compile(r'class="[^"]*post__cat[^"]*"\s+href="(?P<churl>[^"]+)">(?P<cname>[^<]+)</a>')


class VlasnaSpravaGrantsConnector(SourceConnector):
    name = "vlasnasprava_ua"

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
                    main_m = MAIN_RE.search(response.text)
                    scope = response.text[main_m.start():] if main_m else response.text
                    matches = list(ARTICLE_RE.finditer(scope))
                    if not matches:
                        break
                    for m in matches:
                        item = self._to_raw_item(m)
                        if item is not None:
                            items.append(item)
        except httpx.HTTPError as exc:
            logger.warning("vlasnasprava.ua request failed: %s", exc)
            return items

        logger.info("vlasnasprava.ua: fetched %d items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem | None:
        body = m.group("body")
        title_m = TITLE_RE.search(body)
        if not title_m:
            return None
        url = title_m.group("href")
        title = html.unescape(title_m.group("title").strip())
        title = re.sub(r"\s+", " ", title)

        time_m = TIME_RE.search(body)
        published = time_m.group("dtxt").strip() if time_m else ""

        cat_m = CAT_RE.search(body)
        category = html.unescape(cat_m.group("cname").strip()) if cat_m else ""

        external_id = url.rstrip("/").rsplit("/", 1)[-1]

        raw_text_parts = [
            title,
            f"Категорія: {category}" if category else "",
            f"Дата публікації: {published}" if published else "",
            f"Повний текст: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"published_raw": published, "category": category},
        )
