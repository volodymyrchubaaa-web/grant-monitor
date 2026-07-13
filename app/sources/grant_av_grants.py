"""Конектор для каталогу "Гранти" на grant-av.com.ua.

Український агрегатор грантових програм на базі 1С-Бітрікс (видно з класів
`FrmBuyItem`, `CntField`, `ItemBlock_<id>` — типового каталогу товарів
Бітрікса, тут переналаштованого під картки грантів). Публічно доступний без
авторизації, офіційного JSON API немає — перевірено вручну (curl):

    GET https://grant-av.com.ua/grants/

Кожне оголошення — блок `<div class="cat_item ItemBlock_<id>">...</form>`,
що містить посилання/заголовок у `<div class="pt"><a href="..." title="...">`,
дедлайн у `<div class="date">До&nbsp;DD.MM.YYYY</div>`, категорію(ї) у
`<div class="cat_tags"><div class="tag_item"># ...</div></div>` і суму
гранту у `<div class="price_new"><span>...</span> <span class="currency">
грн</span></div>`.

Пагінація: параметр `?PAGEN_1=N` приймається сервером (200 OK), але
перевірено вручну — на сторінці 2 віддаються ті самі 22 ItemBlock_id, що й
на сторінці 1 (сайт ігнорує параметр для цього розділу). Реальної
пагінації не знайдено, тому `fetch()` завжди читає лише список зі сторінки 1
і зупиняється, якщо повторна сторінка не додає нових id (захист від
нескінченного дублювання, а не активна пагінація).

Парсинг регекс-базований (двоетапний: спершу блок картки, потім поля
всередині) і крихкий до змін верстки — якщо структура зміниться, зламається
тільки цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

LIST_URL = "https://grant-av.com.ua/grants/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

BLOCK_RE = re.compile(
    r'<div class="cat_item ItemBlock_(?P<id>\d+)\s*">(?P<body>.*?)</form>',
    re.S,
)
TITLE_RE = re.compile(
    r'<div class="pt">\s*<a href="(?P<href>[^"]+)"[^>]*>\s*(?P<title>.*?)\s*</a>',
    re.S,
)
DATE_RE = re.compile(r'<div class="date">(?P<date>[^<]*)</div>')
TAG_RE = re.compile(r'<div class="tag_item">\s*#\s*(?P<tag>[^<]+)</div>')
PRICE_RE = re.compile(
    r'<div class="price_new"><span>(?P<price>[^<]+)</span>\s*'
    r'<span class="currency">(?P<currency>[^<]+)</span>',
)


class GrantAvGrantsConnector(SourceConnector):
    name = "grant_av_com_ua"

    def __init__(self, max_pages: int = 2) -> None:
        self.max_pages = max_pages

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        seen_ids: set[str] = set()
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                for page in range(1, self.max_pages + 1):
                    url = LIST_URL if page == 1 else f"{LIST_URL}?PAGEN_1={page}"
                    response = client.get(url)
                    if response.status_code == 404:
                        break
                    response.raise_for_status()
                    matches = list(BLOCK_RE.finditer(response.text))
                    if not matches:
                        break
                    new_matches = [m for m in matches if m.group("id") not in seen_ids]
                    if not new_matches:
                        # Сервер ігнорує параметр пагінації і повертає ту саму
                        # сторінку — далі йти немає сенсу.
                        break
                    for m in new_matches:
                        seen_ids.add(m.group("id"))
                        item = self._to_raw_item(m)
                        if item is not None:
                            items.append(item)
        except httpx.HTTPError as exc:
            logger.warning("grant-av.com.ua request failed: %s", exc)
            return items

        logger.info("grant-av.com.ua: fetched %d grant items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem | None:
        body = m.group("body")
        title_m = TITLE_RE.search(body)
        if not title_m:
            return None
        url = title_m.group("href")
        title = html.unescape(title_m.group("title").strip())
        title = re.sub(r"\s+", " ", title)

        date_m = DATE_RE.search(body)
        deadline = html.unescape(date_m.group("date").strip()) if date_m else ""

        tags = [html.unescape(t.strip()) for t in TAG_RE.findall(body)]
        category = ", ".join(tags)

        price_m = PRICE_RE.search(body)
        amount = ""
        if price_m:
            amount_num = html.unescape(price_m.group("price").strip())
            currency = html.unescape(price_m.group("currency").strip())
            amount = f"{amount_num} {currency}"

        raw_text_parts = [
            title,
            f"Категорія: {category}" if category else "",
            f"Дедлайн: {deadline}" if deadline else "",
            f"Сума гранту: {amount}" if amount else "",
            f"Повний текст: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id=m.group("id"),
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={"deadline_raw": deadline, "category": category, "amount_raw": amount},
        )
