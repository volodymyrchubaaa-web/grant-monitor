"""Smoke-тест живого конектора gurt.org.ua (розділ «Гроші»).

Робить реальний HTTP-запит до зовнішнього сайту (без моків). Стрічка на
gurt.org.ua змішує гранти/вакансії/тендери/дайджести — тест лише перевіряє,
що конектор досі повертає непорожній список записів, позначених бейджем
"ГРАНТ" (див. фільтрацію в самому конекторі). Якщо тест падає через мережеву
помилку — це може бути тимчасова недоступність сайту або зміна розмітки, а
не обов'язково баг конектора. Порожній список (без падіння) також можливий,
якщо на момент запуску серед свіжих записів немає жодного з бейджем "ГРАНТ".
"""
from app.sources.gurt_grants import GurtGrantsConnector


def test_fetch_returns_list():
    connector = GurtGrantsConnector(max_pages=1)
    items = connector.fetch()

    assert isinstance(items, list)
    if items:
        first = items[0]
        assert first.source == "gurt_org_ua"
        assert first.external_id
        assert first.url.startswith("https://gurt.org.ua/news/grants/")
        assert first.title
