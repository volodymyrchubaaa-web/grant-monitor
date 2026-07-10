"""Smoke-тест живого конектора prostir.ua (розділ «Гранти»).

Робить реальний HTTP-запит до зовнішнього сайту (без моків), щоб перевірити,
що сторінка досі доступна і повертає оголошення у відомій формі. Якщо тест
падає через мережеву помилку — це може бути тимчасова недоступність сайту
або зміна розмітки, а не обов'язково баг конектора.
"""
from app.sources.prostir_grants import ProstirGrantsConnector


def test_fetch_returns_grant_items_with_expected_fields():
    connector = ProstirGrantsConnector(max_pages=1)
    items = connector.fetch()

    assert isinstance(items, list)
    assert len(items) > 0, "Конектор не повернув жодного запису — перевірте сторінку вручну"

    first = items[0]
    assert first.source == "prostir_ua_grants"
    assert first.external_id
    assert first.url.startswith("https://www.prostir.ua/")
    assert first.title
