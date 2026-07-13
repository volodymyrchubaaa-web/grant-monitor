"""Конектор для публічних Telegram-каналів через веб-preview (t.me/s/<handle>).

Telegram віддає останні ~20 постів публічного каналу у вигляді
серверно-рендереного HTML без будь-якої авторизації, бот-токена чи API-ключа
— достатньо звичайного GET-запиту на `https://t.me/s/<handle>`. Це той самий
трюк, що вже був підтверджений робочим у Node.js-прототипі `grantbot`
(парсинг через cheerio за класом `.tgme_widget_message_text`).

Розмітку перевірено вручну (curl) на реальному каналі `grantsua` станом на
момент написання файлу:

    GET https://t.me/s/grantsua

Кожен пост — блок, що починається з
`<div class="tgme_widget_message_wrap js-widget_message_wrap">` і містить
всередині:
  - `data-post="grantsua/1557"` — атрибут з handle каналу та номером поста
    (використовується як зовнішній ID та для побудови permalink-у
    `https://t.me/<handle>/<id>`);
  - `<div class="tgme_widget_message_text js-message_text" dir="auto">...</div>`
    — текст поста (inline-теги `<b>`, `<i>`, `<a>`, `<br/>`, emoji-спани,
    без вкладених `<div>`, тому пошук до першого `</div>` безпечний у межах
    одного поста);
  - `<a class="tgme_widget_message_date" href="https://t.me/<handle>/<id>">
    <time datetime="...">` — дата публікації (ISO 8601 у `datetime`).

Оскільки в межах одного HTML-документу однакові класи (`tgme_widget_message_text`
тощо) повторюються у КОЖНОМУ пості, регекс не можна застосовувати до всього
документу одразу (нежадібний `.*?` перескочить у сусідній пост, якщо в
поточному чогось бракує). Тому документ спершу ріжеться на шматки-пости за
маркером `tgme_widget_message_wrap js-widget_message_wrap">` (`str.split`), і
вже всередині кожного шматка застосовуються прицільні регекси — так само
регекс-базований і крихкий до змін верстки підхід, як і в інших конекторах
цього проєкту (`gurt_grants.py`, `getgrant_grants.py`). Якщо Telegram змінить
розмітку прев'ю — зламається лише цей файл.

Канали (як і Facebook-групи чи інші агрегатори) змішують в одній стрічці
пости про гранти з новинами, привітаннями, оголошеннями про конкурси
непов'язаної тематики тощо. Тому застосовується ключовий фільтр (довжина
тексту > 50 символів + наявність одного з ключових слів: "грант", "конкурс",
"дедлайн", "фінансуван", "підтримк", "grant", "funding", "call for") —
логіка й пороги перенесені 1-в-1 з grantbot-прототипу (JS, cheerio), лише
портовані на Python/regex.
"""
from __future__ import annotations

import hashlib
import html
import logging
import re

import httpx

from app.sources.base import RawItem, SourceConnector

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; grant-monitor/1.0)"}

MESSAGE_SPLIT_MARKER = 'tgme_widget_message_wrap js-widget_message_wrap">'

DATA_POST_RE = re.compile(r'data-post="(?P<handle>[^/"]+)/(?P<post_id>\d+)"')
TEXT_RE = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(?P<text_html>.*?)</div>',
    re.S,
)
DATE_RE = re.compile(r'<time datetime="(?P<date>[^"]+)"')
LINK_RE = re.compile(r'<a[^>]+href="(?P<href>[^"]+)"')

KEYWORDS = (
    "грант",
    "конкурс",
    "дедлайн",
    "фінансуван",
    "підтримк",
    "grant",
    "funding",
    "call for",
)

MAX_ITEMS_PER_CHANNEL = 10
MAX_RAW_TEXT_LEN = 1500
MAX_TITLE_LEN = 150


def _html_to_text(text_html: str) -> str:
    """Прибирає HTML-теги з тексту поста, зберігаючи переноси рядків з <br/>."""
    text_html = re.sub(r"<br\s*/?>", "\n", text_html)
    text_html = re.sub(r"<[^>]+>", "", text_html)
    text = html.unescape(text_html)
    # Нормалізуємо пробіли всередині рядків, але зберігаємо самі переноси.
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


class TelegramChannelConnector(SourceConnector):
    """Конектор одного публічного Telegram-каналу через t.me/s/<handle>."""

    def __init__(self, handle: str, display_name: str) -> None:
        self.handle = handle
        self.display_name = display_name
        self.name = f"telegram_{handle}"

    def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        url = f"https://t.me/s/{self.handle}"
        try:
            with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("telegram %s (%s) request failed: %s", self.handle, self.display_name, exc)
            return items

        try:
            chunks = response.text.split(MESSAGE_SPLIT_MARKER)[1:]
            for chunk in chunks:
                if len(items) >= MAX_ITEMS_PER_CHANNEL:
                    break
                item = self._parse_chunk(chunk)
                if item is not None:
                    items.append(item)
        except Exception as exc:  # noqa: BLE001 — парсинг не має валити пайплайн
            logger.warning("telegram %s (%s) parsing failed: %s", self.handle, self.display_name, exc)

        logger.info("telegram %s (%s): fetched %d grant items", self.handle, self.display_name, len(items))
        return items

    def _parse_chunk(self, chunk: str) -> RawItem | None:
        text_match = TEXT_RE.search(chunk)
        if not text_match:
            return None

        text = _html_to_text(text_match.group("text_html"))
        if len(text) <= 50:
            return None

        lowered = text.lower()
        if not any(keyword in lowered for keyword in KEYWORDS):
            return None

        post_match = DATA_POST_RE.search(chunk)
        channel_url = f"https://t.me/s/{self.handle}"
        permalink = channel_url
        external_id = None
        if post_match:
            handle, post_id = post_match.group("handle"), post_match.group("post_id")
            permalink = f"https://t.me/{handle}/{post_id}"
            external_id = post_id
        if not external_id:
            external_id = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]

        external_link = None
        for link_match in LINK_RE.finditer(text_match.group("text_html")):
            href = link_match.group("href")
            if "t.me" in href or href.startswith("?q="):
                continue
            external_link = href
            break

        item_url = external_link or permalink

        first_line = text.split("\n", 1)[0].strip()
        title = first_line[:MAX_TITLE_LEN]

        date_match = DATE_RE.search(chunk)
        metadata = {}
        if date_match:
            metadata["published_raw"] = date_match.group("date")

        return RawItem(
            source=self.name,
            external_id=external_id,
            url=item_url,
            title=title,
            raw_text=text[:MAX_RAW_TEXT_LEN],
            metadata=metadata,
        )


TELEGRAM_CONNECTORS: list[SourceConnector] = [
    TelegramChannelConnector(handle="grantsua", display_name="Гранти UA"),
    TelegramChannelConnector(handle="grantovyphishky", display_name="Грантові фішки"),
    TelegramChannelConnector(handle="grants_here", display_name="Гранти та можливості"),
    TelegramChannelConnector(handle="gaborets", display_name="Ресурсний центр ГУРТ"),
    TelegramChannelConnector(handle="aotgnews", display_name="Асоціація ОТГ"),
    TelegramChannelConnector(handle="democracy_ua", display_name="Демократія поруч"),
    TelegramChannelConnector(handle="EUDelegationUA", display_name="EU Delegation UA"),
    TelegramChannelConnector(handle="UNDPUkraine", display_name="ПРООН Україна"),
    TelegramChannelConnector(handle="decentralization_ua", display_name="Децентралізація"),
    TelegramChannelConnector(handle="getgrant_ua", display_name="GetGrant"),
]
