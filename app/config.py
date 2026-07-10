"""Конфігурація застосунку та критеріїв відбору грантів для Жовтанецької ТГ.

Критерії відбору (сектори/напрямки) взяті зі стратегічних цілей громади,
див. CLAUDE.md -> "Стратегічне бачення". Список призначений для передачі в
LLM-екстракцію/матчинг як контекст, а не для жорсткої фільтрації рядків.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = ""
    database_url: str = "sqlite:///./grants.db"
    fetch_interval_hours: int = 6

    # Критерії громади, використовуються в pipeline/match.py та pipeline/extract.py
    target_region: str = "Львівська область"
    community_name: str = "Жовтанецька територіальна громада"
    strategic_sectors: list[str] = [
        "інфраструктура (дороги, водопостачання, енергетика)",
        "агропромисловий розвиток",
        "підтримка підприємництва та МСП",
        "освіта та інклюзія",
        "охорона довкілля",
        "цифровізація адмінпослуг",
        "туризм та збереження культурної спадщини",
    ]


settings = Settings()

BASE_DIR = Path(__file__).resolve().parent.parent
