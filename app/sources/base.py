from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawItem:
    """Необроблений запис, отриманий з джерела, перед LLM-екстракцією."""

    source: str
    external_id: str
    url: str
    title: str
    raw_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class SourceConnector(ABC):
    """Спільний інтерфейс для всіх конекторів джерел грантів.

    Кожне нове джерело (DREAM, Дія.Бізнес, донори, TG/FB-групи тощо) має
    реалізувати цей клас в окремому файлі всередині app/sources/, не
    торкаючись інших конекторів чи пайплайну.
    """

    name: str

    @abstractmethod
    def fetch(self) -> list[RawItem]:
        """Повертає список нових/актуальних оголошень з джерела."""
        raise NotImplementedError
