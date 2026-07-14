from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..providers import ProviderCapabilities


@dataclass(frozen=True)
class ModelInfo:
    name: str
    provider: str
    context_length: int
    supports_stream: bool
    supports_image: bool
    supports_reasoning: bool
    supports_embedding: bool
    supports_tool_call: bool
    pricing: dict[str, float] | None = None

    def to_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_stream=self.supports_stream,
            supports_image=self.supports_image,
            supports_embedding=self.supports_embedding,
            supports_reasoning=self.supports_reasoning,
            supports_tool_call=self.supports_tool_call,
            supports_cache=False,
        )


class ModelRegistry:
    def __init__(self, models: Iterable[ModelInfo]) -> None:
        self._models_by_name = {model.name: model for model in models}

    def list_models(self) -> list[ModelInfo]:
        return sorted(self._models_by_name.values(), key=lambda model: (model.provider, model.name))

    def get_model(self, name: str) -> ModelInfo:
        model = self._models_by_name.get(name)
        if model is None:
            raise KeyError(f"unknown model: {name}")
        return model

    def list_models_by_provider(self, provider: str) -> list[ModelInfo]:
        return [
            model
            for model in self.list_models()
            if model.provider == provider
        ]
