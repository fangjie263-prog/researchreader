from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import ProviderConfig


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_stream: bool = False
    supports_image: bool = False
    supports_embedding: bool = False
    supports_reasoning: bool = False
    supports_tool_call: bool = False
    supports_cache: bool = False


@dataclass(frozen=True)
class ProviderTestResult:
    provider_name: str
    display_name: str
    model: str
    ok: bool
    configuration_ok: bool = False
    connectivity_ok: bool = False
    model_available: bool = False
    capabilities: ProviderCapabilities = ProviderCapabilities()
    first_token_latency_ms: float | None = None
    total_response_time_ms: float | None = None
    errors: tuple[str, ...] = ()


class Provider(Protocol):
    config: ProviderConfig

    def list_models(self) -> list[str]:
        ...

    def measure_first_token_latency(self) -> float:
        ...

    def test(self) -> ProviderTestResult:
        ...


class ProviderError(Exception):
    pass
