"""Конектор для сторінки грантів Львівської обласної ради — fallback
snapshot mode.

Перевірено вручну (curl):

    GET https://lvivoblrada.gov.ua/index.php/activity/granti   -> HTTP 404
    GET https://lvivoblrada.gov.ua/                              -> HTTP 200

Задана URL-адреса розділу "Гранти" (стара Joomla-структура
`index.php/activity/...`) на поточному сайті не існує — сайт вже
перебудований на WordPress (перевірено: `wp-json`, `wp-content` у
розмітці). У навігації головної сторінки (101 унікальне внутрішнє
посилання, перевірено вручну) НЕ знайдено жодного пункту меню чи URL, що
явно відповідає окремому стабільному розділу "гранти" (перевірені
кандидати на кшталт `/info/oblasni-prohramy/` не містять згадок слова
"грант"). Створювати регекс під випадковий чужий розділ (новини,
антикорупційна діяльність тощо) означало б вигадувати структуру, якої
немає — це заборонено методологією.

Тому для цього джерела реалізовано fallback "знімок сторінки": фактично
запитується головна сторінка (як найстабільніший актуальний вхідний пункт
сайту), весь HTML очищується від тегів, пробіли згортаються, текст
обрізається до ~4000 символів і повертається ОДИН `RawItem` з
`external_id="snapshot"`. Заголовок береться з `<title>`. Чи згадується на
головній сторінці (чи анонсах на ній) щось релевантне грантам — вирішує
подальша LLM-екстракція в пайплайні, а не цей конектор. Якщо адміністрація
ради опублікує окремий розділ "Гранти" з постійною адресою — варто
переписати цей конектор на повноцінний per-item парсинг.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

GRANTS_URL = "https://lvivoblrada.gov.ua/index.php/activity/granti"
FALLBACK_URL = "https://lvivoblrada.gov.ua/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}
SNAPSHOT_MAX_CHARS = 4000

TITLE_RE = re.compile(r"<title[^>]*>(?P<title>.*?)</title>", re.S | re.I)


class LvivOblradaGrantsConnector(SourceConnector):
    name = "lvivoblrada_gov_ua"

    def fetch(self) -> list[RawItem]:
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(GRANTS_URL)
                if response.status_code == 404:
                    # Стара Joomla-адреса більше не існує — читаємо головну
                    # сторінку як найстабільніший актуальний вхідний пункт
                    # (див. докстрінг файлу).
                    url = FALLBACK_URL
                    response = client.get(FALLBACK_URL)
                else:
                    url = GRANTS_URL
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("lvivoblrada.gov.ua request failed: %s", exc)
            return []

        item = self._to_snapshot_item(response.text, url)
        logger.info("lvivoblrada.gov.ua: fetched 1 snapshot item (fallback mode, url=%s)", url)
        return [item]

    def _to_snapshot_item(self, page_html: str, url: str) -> RawItem:
        title_m = TITLE_RE.search(page_html)
        title = html.unescape(title_m.group("title").strip()) if title_m else "Львівська обласна рада"

        text = re.sub(r"<script.*?</script>", " ", page_html, flags=re.S | re.I)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()[:SNAPSHOT_MAX_CHARS]

        raw_text_parts = [
            title,
            text,
            f"Повний текст: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id="snapshot",
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"mode": "snapshot", "requested_url": GRANTS_URL, "fetched_url": url},
        )
