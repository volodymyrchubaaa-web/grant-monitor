"""Тягне сирі записи (RawItem) з усіх джерел і друкує їх як JSON у stdout.

Без жодних LLM-викликів і без API-ключів — тільки HTTP-запити до джерел.
Призначення: Claude (у запланованій задачі) читає вивід цього скрипта і сам
робить структуровану екстракцію/фільтрацію/оцінку замість pipeline/extract.py
(що вимагає ANTHROPIC_API_KEY). Використання:

    python scripts/fetch_raw.py
"""
from __future__ import annotations

import dataclasses
import json
import sys

from app.pipeline.run import SOURCES


def main() -> None:
    all_items = []
    for connector in SOURCES:
        try:
            items = connector.fetch()
        except Exception as exc:  # джерело не повинно валити весь fetch
            print(f"[{connector.name}] fetch failed: {exc}", file=sys.stderr)
            continue
        all_items.extend(dataclasses.asdict(item) for item in items)

    json.dump(all_items, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
