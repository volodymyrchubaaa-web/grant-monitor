"""Конектор для головної сторінки nefco.int (NEFCO, Nordic Environment
Finance Corporation / "Nordic Green Bank").

Перевірено вручну (curl):

    GET https://www.nefco.int/

Це загальна маркетингова головна сторінка організації (hero-блоки "A true
Nordic first", "Scaling up green solutions", плитки розділів на кшталт
"Green recovery in Ukraine", "Procurement opportunities", блок "Key
figures", блок "Latest updates", блок "Events"). Жодного стабільного
повторюваного блоку "картка гранту/конкурсу з дедлайном" у серверному HTML
немає — усі знайдені `<h2>`/`<article>`-елементи це заголовки секцій
лендінгу, а не список окремих оголошень. Присвячена Україні плитка
("Green recovery in Ukraine") веде на окрему тематичну сторінку, а не
містить перелік грантів сама по собі.

Тому цей конектор працює у fallback-режимі "знімок сторінки": завантажує
головну сторінку NEFCO, знімає HTML-теги регексом, згортає пробіли,
обрізає до ~4000 символів і повертає ОДИН RawItem з
external_id="snapshot". Рішення про наявність у знімку актуальної
інформації про грант/конкурс (наприклад анонсу нового вікна фінансування
для України) приймає LLM-екстракція нижче за пайплайном, а не цей
конектор.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

PAGE_URL = "https://www.nefco.int/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}
SNAPSHOT_MAX_CHARS = 4000

TITLE_RE = re.compile(r"<title[^>]*>(?P<title>.*?)</title>", re.S)


class NefcoConnector(SourceConnector):
    name = "nefco_int"

    def fetch(self) -> list[RawItem]:
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(PAGE_URL)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("nefco.int request failed: %s", exc)
            return []

        item = self._to_snapshot_item(response.text, str(response.url))
        logger.info("nefco.int: fetched snapshot")
        return [item]

    def _to_snapshot_item(self, page_html: str, final_url: str) -> RawItem:
        title_match = TITLE_RE.search(page_html)
        title = html.unescape(title_match.group("title").strip()) if title_match else "NEFCO"

        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page_html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()[:SNAPSHOT_MAX_CHARS]

        raw_text_parts = [
            title,
            text,
            f"Повний текст: {final_url}",
        ]
        return RawItem(
            source=self.name,
            external_id="snapshot",
            url=final_url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"mode": "snapshot", "requested_url": PAGE_URL},
        )
