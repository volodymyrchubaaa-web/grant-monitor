"""Smoke-тест живого конектора decentralization.gov.ua (тег «грант»).

Робить реальний HTTP-запит до зовнішнього сайту (без моків), щоб перевірити,
що сторінка досі доступна і повертає новини у відомій формі. Якщо тест падає
через мережеву помилку — це може бути тимчасова недоступність сайту або зміна
розмітки, а не обов'язково баг конектора.
"""
from app.sources.decentralization_grants import DecentralizationGrantsConnector


def test_fetch_returns_grant_news_with_expected_fields():
    connector = DecentralizationGrantsConnector(max_pages=1)
    items = connector.fetch()

    assert isinstance(items, list)
    assert len(items) > 0, "Конектор не повернув жодного запису — перевірте сторінку вручну"

    first = items[0]
    assert first.source == "decentralization_gov_ua_grants"
    assert first.external_id
    assert first.url.startswith("https://decentralization.gov.ua/news/")
    assert first.title
