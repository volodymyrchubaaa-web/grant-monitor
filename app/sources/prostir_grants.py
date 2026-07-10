"""Конектор для розділу "Гранти" на prostir.ua (Громадський Простір).

Найбільший український агрегатор оголошень для громадського сектору —
розділ /category/grants/ курує гранти, стипендії та конкурси для ГО, громад
і активістів. Публічно доступний без авторизації, офіційного JSON API немає —
перевірено вручну (curl):

    GET https://www.prostir.ua/category/grants/[page/N/]

Кожне оголошення — блок `<div class="newsblock">` з посиланням, заголовком,
періодом подачі (дата початку - дедлайн) і коротким описом. Розмітка
стара (WordPress-тема без семантичних класів на елементах title/desc), тому
парсинг регекс-базований і крихкий до змін верстки — якщо структура зміниться,
зламається тільки цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://www.prostir.ua/category/grants/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

BLOCK_RE = re.compile(
    r'<div class="newsblock">.*?'
    r'<div class="date_cloud_news">\s*<p>\s*(?P<start>[\d.]+)\s*-\s*(?P<deadline>[\d.]+)\s*</p>.*?'
    r'<h3>\s*<a href="(?P<href>[^"]+)"\s*title="(?P<title>[^"]*)">.*?'
    r'<p>\s*<p>(?P<desc>.*?)</p>',
    re.S,
)


class ProstirGrantsConnector(SourceConnector):
    name = "prostir_ua_grants"

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
            logger.warning("prostir.ua request failed: %s", exc)
            return items

        logger.info("prostir.ua: fetched %d grant items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem:
        url = m.group("href")
        external_id = url.split("grants=", 1)[-1] if "grants=" in url else url
        title = html.unescape(m.group("title").strip())
        desc = html.unescape(m.group("desc").strip())
        desc = re.sub(r"\s+", " ", desc)
        start = m.group("start").strip()
        deadline = m.group("deadline").strip()

        raw_text_parts = [
            title,
            f"Період подачі: {start} - {deadline}",
            desc,
            f"Повний текст: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"start_raw": start, "deadline_raw": deadline},
        )
