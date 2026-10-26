"""Stable ingestion boundary for authorized future data providers."""
from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass(frozen=True)
class ExternalRecord:
    source_system: str
    source_id: str
    payload: dict


class IngestionAdapter(Protocol):
    name: str

    def validate_configuration(self, configuration: dict) -> list[str]: ...
    def fetch(self, cursor: str | None = None) -> Iterable[ExternalRecord]: ...


class AdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, IngestionAdapter] = {}

    def register(self, adapter: IngestionAdapter):
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> IngestionAdapter:
        if name not in self._adapters:
            raise KeyError(f"Integration adapter '{name}' is not configured")
        return self._adapters[name]


registry = AdapterRegistry()

