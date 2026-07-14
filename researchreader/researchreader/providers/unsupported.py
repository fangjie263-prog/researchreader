from __future__ import annotations

from ..config import ProviderConfig
from .base import ProviderError, ProviderTestResult


class UnsupportedProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def list_models(self) -> list[str]:
        raise ProviderError(f"unsupported provider kind: {self.config.kind}")

    def measure_first_token_latency(self) -> float:
        raise ProviderError(f"unsupported provider kind: {self.config.kind}")

    def test(self) -> ProviderTestResult:
        return ProviderTestResult(
            provider_name=self.config.name,
            display_name=self.config.display_name,
            model=self.config.model,
            ok=False,
            configuration_ok=False,
            errors=(f"unsupported provider kind: {self.config.kind}",),
        )
