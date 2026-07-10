"""Smoke-тест живого конектора getgrant.ua (розділ «Гранти та фінансування»).

Робить реальний HTTP-запит до зовнішнього сайту (без моків), щоб перевірити,
що сторінка досі доступна і повертає записи у відомій формі. Якщо тест падає
через мережеву помилку — це може бути тимчасова недоступність сайту або зміна
розмітки, а не обов'язково баг конектора.
"""
from app.sources.getgrant_grants import GetGrantConnector


def test_fetch_returns_grant_items_with_expected_fields():
    connector = GetGrantConnector(max_pages=1)
    items = connector.fetch()

    assert isinstance(items, list)
    assert len(items) > 0, "Конектор не повернув жодного запису — перевірте сторінку вручну"

    first = items[0]
    assert first.source == "getgrant_ua"
    assert first.external_id
    assert first.url.startswith("https://getgrant.ua/")
    assert first.title
