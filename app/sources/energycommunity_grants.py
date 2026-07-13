"""Конектор для Energy Community (енергетичне співтовариство ЄС + сусіди).

Головна сторінка https://www.energy-community.org/ — публічно доступна без
авторизації, офіційного JSON API немає — перевірено вручну (curl):

    GET https://www.energy-community.org/

На сторінці є календар подій, зверстаний як плаский список `<div>`-віджетів
без вкладеності — кожна подія це один самозакривний тег:

    <div class="added-event" data-date="2026-11-30" data-icon="..."
         data-display-date="30 November" data-weekday="Monday"
         data-date-range="" data-date-range-label=""
         data-title="24th Ministerial Council"
         data-link="/events/2026/12/MC.html" data-link-text="..."
         ... data-info="Participation upon invitation only" ...></div>

Перевірено вручну (curl) — станом на момент розробки 140 таких блоків на
головній сторінці. Порядок і набір data-атрибутів варіюється між подіями
(деякі мають data-info/data-countryInfo, деякі ні), тому парсинг
двоетапний: спершу regex виділяє кожен `<div class="added-event" ...>
</div>` блок цілком (нежадібно до першого закриття), потім усередині нього
окремими regex шукаються конкретні data-* атрибути незалежно від порядку.
Це дає ~118-140 валідних подій (частина блоків не проходить через дрібні
відмінності верстки — прийнятно, не критично).

Це календар заходів Energy Community (засідання, форуми, воркшопи), а не
прямий реєстр грантів — але серед подій трапляються анонси програм
підтримки/фінансування для країн-учасниць (включно з Україною). Downstream
LLM-екстракція вирішує, чи є в конкретному записі щось релевантне для
моніторингу. Розмітка кастомна (AEM-подібна CMS), парсинг регекс-базований
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

LIST_URL = "https://www.energy-community.org/"
BASE_URL = "https://www.energy-community.org"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

TAG_RE = re.compile(r'<div class="added-event"\s+(?P<attrs>.*?)>\s*</div>', re.S)
MAX_ITEMS = 60  # обмеження, щоб не тягнути весь дворічний календар подій


def _attr(attrs: str, name: str) -> str:
    m = re.search(name + r'="([^"]*)"', attrs)
    return html.unescape(re.sub(r"\s+", " ", m.group(1)).strip()) if m else ""


class EnergyCommunityConnector(SourceConnector):
    name = "energy_community"

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(LIST_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Energy Community request failed: %s", exc)
            return items

        for m in TAG_RE.finditer(response.text):
            item = self._to_raw_item(m.group("attrs"))
            if item is not None:
                items.append(item)
            if len(items) >= MAX_ITEMS:
                break

        logger.info("Energy Community: fetched %d event items", len(items))
        return items

    def _to_raw_item(self, attrs: str) -> RawItem | None:
        title = _attr(attrs, "data-title")
        link = _attr(attrs, "data-link")
        if not title or not link:
            return None

        date = _attr(attrs, "data-date")
        display_date = _attr(attrs, "data-display-date")
        info = _attr(attrs, "data-info")
        country_info = _attr(attrs, "data-countryInfo")
        url = link if link.startswith("http") else f"{BASE_URL}{link}"
        external_id = url.rstrip("/").rsplit("/", 1)[-1]

        raw_text_parts = [
            title,
            f"Дата: {display_date or date}",
            f"Локація: {country_info}" if country_info else "",
            info,
            f"Повний текст: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"date": date, "display_date": display_date},
        )
