"""Конектор для GEF Small Grants Programme (UNDP) — проєкти в Україні.

Сторінка https://sgp.undp.org/spacial-itemid-projects-landing-page/
spacial-itemid-project-search.html?view=allprojects&countryId=178 —
Joomla-сайт (компонент com_sgpprojects). Перевірено вручну (curl), що
переданий у URL GET-параметр `countryId=178` НЕ фільтрує таблицю проєктів
на сервері (перший рядок віддає проєкти з Танзанії) — фільтр застосовується
лише через JS/POST-форму `adminForm`, яка реально відправляється на:

    POST https://sgp.undp.org/index.php?option=com_sgpprojects&view=allprojects&Itemid=279
         CountryID[]=UKR&submt=GO&limitstart=<N>

Перевірено вручну (curl -X POST) — цей ендпоінт коректно повертає таблицю
проєктів, відфільтровану саме по Україні (20 проєктів на сторінку,
`limitstart` — пагінація по 20). Кожен проєкт — блок з рядків `<tr>`:
назва й посилання у `<a class="item_title" href="...">`, країна/тематика/
рік/сума в наступних `<td class="yellow_light_bg">`, номер проєкту в
окремому `<td class="project_number_line">`, опис у
`<span class='statement_into'>...</span>`. Деякі короткі назви НЕ мають
truncation-спана `<span id="more_title...">` — це врахо­вано в regex
(non-greedy title зупиняється на першому з двох можливих маркерів:
початок truncation-спана або `</a>`), інакше заголовок "з'їдає" сусідні
рядки таблиці.

Розмітка стара (Joomla template, без семантичних data-атрибутів на
контентних полях), парсинг регекс-базований і крихкий до змін верстки —
якщо структура зміниться, зламається тільки цей файл.
"""
from __future__ import annotations

import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

SEARCH_URL = "https://sgp.undp.org/index.php?option=com_sgpprojects&view=allprojects&Itemid=279"
DETAIL_BASE_URL = "https://sgp.undp.org"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

ROW_RE = re.compile(
    r'<a class="item_title" href="(?P<href>[^"]+)"\s*'
    r'title="[^"]*"\s*>\s*(?P<title>.*?)(?=<span id="more_title|</a>).*?</a>\s*</div>\s*</td>\s*'
    r'<td class="yellow_light_bg">\s*<div>\s*(?P<country>.*?)\s*</div>\s*</td>\s*'
    r'<td class="yellow_light_bg">\s*<div>\s*(?P<area>.*?)\s*</div>\s*</td>\s*'
    r'<td class="yellow_light_bg" align="left"[^>]*>\s*<div>\s*(?P<year>.*?)\s*</div>\s*</td>\s*'
    r'<td class="yellow_light_bg" align="center">\s*<div>\s*(?P<amount>.*?)\s*</div>\s*</td>.*?'
    r'Project Number:\s*&nbsp;&nbsp;(?P<pnum>[^\s<]+)\s*</td>.*?'
    r"<span class='statement_into'>(?P<desc>.*?)</span>",
    re.S,
)


class GefSgpUndpConnector(SourceConnector):
    name = "gef_sgp_undp"

    def __init__(self, max_pages: int = 2) -> None:
        self.max_pages = max_pages

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                for page in range(self.max_pages):
                    data = {
                        "submt": "GO",
                        "CountryID[]": "UKR",
                        "limitstart": str(page * 20),
                    }
                    response = client.post(SEARCH_URL, data=data)
                    response.raise_for_status()
                    matches = list(ROW_RE.finditer(response.text))
                    if not matches:
                        break
                    items.extend(self._to_raw_item(m) for m in matches)
        except httpx.HTTPError as exc:
            logger.warning("GEF SGP UNDP request failed: %s", exc)
            return items

        logger.info("GEF SGP UNDP: fetched %d Ukraine project items", len(items))
        return items

    def _to_raw_item(self, m: re.Match) -> RawItem:
        href = html.unescape(m.group("href"))
        url = href if href.startswith("http") else f"{DETAIL_BASE_URL}{href}"
        pid_match = re.search(r"id=(\d+)", url)
        external_id = pid_match.group(1) if pid_match else url

        title = html.unescape(re.sub(r"\s+", " ", m.group("title")).strip())
        country = html.unescape(m.group("country").strip())
        area = html.unescape(re.sub(r"<BR\s*/?>", "; ", m.group("area")).strip())
        year = m.group("year").strip()
        amount = m.group("amount").strip()
        pnum = m.group("pnum").strip()
        desc = html.unescape(re.sub(r"\s+", " ", m.group("desc")).strip())

        raw_text_parts = [
            title,
            f"Країна: {country}",
            f"Тематика: {area}",
            f"Рік початку: {year}",
            f"Сума гранту (USD): {amount}",
            f"Номер проєкту: {pnum}",
            desc,
            f"Повний текст: {url}",
        ]
        return RawItem(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            raw_text="\n".join(p for p in raw_text_parts if p),
            metadata={
                "country": country,
                "area": area,
                "year": year,
                "amount_usd": amount,
                "project_number": pnum,
            },
        )
