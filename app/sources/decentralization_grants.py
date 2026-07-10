"""Конектор для розділу новин "грант" на decentralization.gov.ua.

Офіційний урядовий портал реформи децентралізації (підтримка U-LEAD/USAID),
розділ новин курований під тегом "hrant" — саме про гранти/донорські
конкурси для територіальних громад і ОМС. Публічно доступний без
авторизації, офіційного JSON API немає — перевірено вручну (curl):

    GET https://decentralization.gov.ua/news/tag/hrant[?page=N]

Повертає HTML зі списком новин у блоках `<div class='one-article'>`, кожен
з посиланням на новину (`/news/<id>`), заголовком, категорією-тегом і датою
публікації. Офіційно не задокументовано — якщо розробники сайту поміняють
розмітку, зламається тільки цей файл, решта пайплайну не залежить від
деталей парсингу.

Для кожної новини додатково запитується сторінка статті, щоб витягнути
`og:description` (короткий лід) — повний текст статті не парситься (немає
стабільного контейнера в розмітці на момент перевірки), тому LLM-екстракція
нижче за пайплайном працює з заголовком+лідом+URL, як і для інших джерел.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://decentralization.gov.ua/news/tag/hrant"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

ARTICLE_RE = re.compile(
    r"<div class='one-article'>.*?"
    r"<a class=\"one-article__tag\" href=\"[^\"]*\">\s*(?P<tag>[^<]*?)\s*</a>.*?"
    r"<a class=\"one-article__title\" href=\"(?P<href>/news/\d+)\">(?P<title>[^<]*)</a>.*?"
    r"<div class='one-article__date'>\s*(?P<date>[^<]*?)\s*</div>",
    re.S,
)
OG_DESCRIPTION_RE = re.compile(r'property="og:description"\s+content="(.*?)"\s*/>', re.S)


class DecentralizationGrantsConnector(SourceConnector):
    name = "decentralization_gov_ua_grants"

    def __init__(self, max_pages: int = 2) -> None:
        self.max_pages = max_pages

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                for page in range(1, self.max_pages + 1):
                    url = LIST_URL if page == 1 else f"{LIST_URL}?page={page}"
                    response = client.get(url)
                    response.raise_for_status()
                    matches = list(ARTICLE_RE.finditer(response.text))
                    if not matches:
                        break
                    for m in matches:
                        items.append(self._to_raw_item(m, client))
        except httpx.HTTPError as exc:
            logger.warning("decentralization.gov.ua request failed: %s", exc)
            return items

        logger.info("decentralization.gov.ua: fetched %d grant news items", len(items))
        return items

    def _to_raw_item(self, m: re.Match, client: httpx.Client) -> RawItem:
        news_id = m.group("href").rsplit("/", 1)[-1]
        title = html.unescape(m.group("title").strip())
        tag = html.unescape(m.group("tag").strip())
        date_raw = m.group("date").strip()
        url = f"https://decentralization.gov.ua{m.group('href')}"

        description = self._fetch_description(client, url)

        raw_text_parts = [
            title,
            f"Категорія/донор: {tag}",
            f"Дата публікації: {date_raw}",
            description or "",
            f"Повний текст новини: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id=news_id,
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"tag": tag, "published_raw": date_raw},
        )

    @staticmethod
    def _fetch_description(client: httpx.Client, url: str) -> str | None:
        try:
            response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        m = OG_DESCRIPTION_RE.search(response.text)
        if not m:
            return None
        text = html.unescape(m.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        return text or None
