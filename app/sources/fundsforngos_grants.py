"""Конектор для тегу "Ukraine" на fundsforngos.org (fundsforNGOs).

fundsforNGOs — один з найбільших міжнародних медіа про гранти для НУО,
тег /tag/ukraine/ агрегує всі публікації (гранти, конкурси, фонди), що
стосуються України. Пряме HTML-скрапінг сторінки тегу НЕ працює: сайт
захищений анти-бот сервісом ShopShield/Cloudflare — перевірено вручну
(curl з User-Agent браузера):

    GET https://www2.fundsforngos.org/tag/ukraine/

повертає HTTP 200, але тілом відповіді є проміжна сторінка-заглушка
("Please Wait" / meta http-equiv="refresh" на ту саму URL через 5.5 сек,
SVG-лого "ShopShield") — це JS-виклик, який curl/httpx пройти не можуть.

Натомість перевірено вручну (curl), що офіційний публічний WordPress
REST API сайту доступний і не заблокований:

    GET https://www2.fundsforngos.org/wp-json/wp/v2/posts?tags=638&per_page=N&page=M

(tag id=638 відповідає тегу "ukraine" — отримано з
`GET /wp-json/wp/v2/tags/638`, поле description="View the latest grants
and resources for NGOs, companies, startups and individuals in Ukraine.").
Відповідь — валідний JSON зі списком постів (id, date, link, title.rendered,
excerpt.rendered), заголовки відповіді містять X-WP-TotalPages для
пагінації. Тому цей конектор не використовує регекс на HTML, а звертається
напряму до JSON REST API — це стабільніший, офіційно підтримуваний спосіб
доступу до того самого контенту, який показує сторінка тегу. Якщо WP REST
API колись стане недоступним, зламається тільки цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

API_URL = "https://www2.fundsforngos.org/wp-json/wp/v2/posts"
UKRAINE_TAG_ID = 638
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}


class FundsForNgosConnector(SourceConnector):
    name = "fundsforngos_org"

    def __init__(self, max_pages: int = 2, per_page: int = 20) -> None:
        self.max_pages = max_pages
        self.per_page = per_page

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                for page in range(1, self.max_pages + 1):
                    response = client.get(
                        API_URL,
                        params={
                            "tags": UKRAINE_TAG_ID,
                            "per_page": self.per_page,
                            "page": page,
                            "_fields": "id,date,link,title,excerpt",
                        },
                    )
                    if response.status_code == 400:
                        # WP REST API повертає 400 rest_post_invalid_page_number
                        # коли page перевищує X-WP-TotalPages.
                        break
                    response.raise_for_status()
                    posts = response.json()
                    if not posts:
                        break
                    items.extend(self._to_raw_item(post) for post in posts)
        except httpx.HTTPError as exc:
            logger.warning("fundsforngos.org request failed: %s", exc)
            return items
        except ValueError as exc:
            logger.warning("fundsforngos.org returned invalid JSON: %s", exc)
            return items

        logger.info("fundsforngos.org: fetched %d grant items", len(items))
        return items

    @staticmethod
    def _to_raw_item(post: dict) -> RawItem:
        post_id = str(post.get("id", ""))
        url = post.get("link", "")
        title = html.unescape(post.get("title", {}).get("rendered", "").strip())
        excerpt_html = post.get("excerpt", {}).get("rendered", "")
        excerpt_text = re.sub(r"<[^>]+>", " ", excerpt_html)
        excerpt_text = html.unescape(re.sub(r"\s+", " ", excerpt_text).strip())
        date_raw = post.get("date", "")

        raw_text_parts = [
            title,
            f"Дата публікації: {date_raw}",
            excerpt_text,
            f"Повний текст: {url}",
        ]
        return RawItem(
            source="fundsforngos_org",
            external_id=post_id,
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"published_raw": date_raw},
        )
