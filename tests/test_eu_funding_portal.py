"""Smoke-тест живого конектора EU Funding & Tenders Portal.

Робить реальний HTTP-запит до зовнішнього API (без моків), щоб перевірити,
що ендпоінт досі доступний і повертає дані у відомій формі. Якщо тест падає
через мережеву помилку — це може бути тимчасова недоступність порталу, а не
обов'язково баг конектора.
"""
from app.sources.eu_funding_portal import EUFundingPortalConnector


def test_fetch_returns_topics_with_expected_fields():
    connector = EUFundingPortalConnector(page_size=20)
    items = connector.fetch()

    assert isinstance(items, list)
    assert len(items) > 0, "Конектор не повернув жодного запису — перевірте ендпоінт вручну"

    first = items[0]
    assert first.source == "eu_funding_tenders_portal"
    assert first.external_id
    assert first.url.startswith("http")
    assert first.title
    assert "Deadline:" in first.raw_text
