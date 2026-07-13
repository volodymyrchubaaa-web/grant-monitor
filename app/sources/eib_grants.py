"""Конектор для EIB (Європейський інвестиційний банк) — країнова сторінка Україна.

Сторінка https://www.eib.org/en/projects/regions/eastern-neighbours/ukraine/index.htm
— це оглядова країнова сторінка EIB по Україні (EIB фінансує переважно через
кредити/гарантії/техдопомогу, окремого реєстру "call for proposals" на ній
немає). Публічно доступна без авторизації, офіційного JSON API немає —
перевірено вручну (curl):

    GET https://www.eib.org/en/projects/regions/eastern-neighbours/ukraine/index.htm

На сторінці є карусель новин/історій про діяльність EIB в Україні: кожен
запис — блок `<div class="eib-card ..." data-type="media" data-subType="stories"
...>`, що містить дату у `<span class='eib-card-date'>`, заголовок і
посилання у `<h3 class="eib-card-title..."><a class="eib-card-title__link"
href="...">`, короткий опис у `<div class="eib-card-text"><p>...</p></div>`
і закривається `</footer>` (тег-теги за секторами/країнами). Перевірено
вручну (curl) — станом на момент розробки 6 таких карток на сторінці.

Це новини/кейси EIB про Україну, а не пряме "оголошення про грант" — але
серед них трапляються анонси нових інвестиційних програм і трастових
фондів (наприклад EU for Ukraine Fund), тому downstream LLM-екстракція
вирішує, чи є в конкретному записі щось релевантне для моніторингу.
Розмітка сучасна (кастомна EIB CMS), парсинг регекс-базований і крихкий до
змін верстки — якщо структура зміниться, зламається тільки цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://www.eib.org/en/projects/regions/eastern-neighbours/ukraine/index.htm"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

BLOCK_RE = re.compile(
    r'<div class="eib-card [^"]*" data-type="media" data-subType="stories"[^>]*>'
    r"(?P<body>.*?)</footer>",
    re.S,
)
DATE_RE = re.compile(r"<span class='eib-card-date'>(?P<date>[^<]*)</span>", re.S)
TITLE_RE = re.compile(
    r'<a class="eib-card-title__link" href="(?P<href>[^"]+)"\s*>(?P<title>.*?)</a>', re.S
)
DESC_RE = re.compile(r'<div class="eib-card-text">\s*<p>\s*(?P<desc>.*?)\s*</p>', re.S)


class EibConnector(SourceConnector):
    name = "eib_ukraine"

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(LIST_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("EIB Ukraine request failed: %s", exc)
            return items

        for m in BLOCK_RE.finditer(response.text):
            item = self._to_raw_item(m.group("body"))
            if item is not None:
                items.append(item)

        logger.info("EIB Ukraine: fetched %d story/news items", len(items))
        return items

    def _to_raw_item(self, body: str) -> RawItem | None:
        title_m = TITLE_RE.search(body)
        if not title_m:
            return None
        date_m = DATE_RE.search(body)
        desc_m = DESC_RE.search(body)

        url = title_m.group("href")
        title = html.unescape(re.sub(r"\s+", " ", title_m.group("title")).strip())
        date = html.unescape(date_m.group("date").strip()) if date_m else ""
        desc = (
            html.unescape(re.sub(r"\s+", " ", desc_m.group("desc")).strip()) if desc_m else ""
        )
        external_id = url.rstrip("/").rsplit("/", 1)[-1]

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
