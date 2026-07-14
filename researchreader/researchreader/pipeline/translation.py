from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from ..adapters import AdapterFactory, TranslationAdapter
from ..config.resolver import ProviderResolver
from ..config.settings import Settings, load_settings
from .base import Pipeline
from .context import PipelineContext
from .result import PipelineResult, PipelineStatus


class TranslationPipeline(Pipeline):
    def __init__(
        self,
        adapter_factory: AdapterFactory | None = None,
        provider_resolver: ProviderResolver | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._adapter_factory = adapter_factory or AdapterFactory()
        self._settings = settings or load_settings()
        self._provider_resolver = provider_resolver or ProviderResolver(settings=self._settings)

    def run(self, context: PipelineContext) -> PipelineResult:
        return self.execute(context)

    def execute(self, context: PipelineContext) -> PipelineResult:
        start_time = datetime.now(UTC)
        try:
            context = self._resolve_context(context)
            self._validate_context(context)
            assert context.source_path is not None
            assert context.output_path is not None

            adapter = self._adapter_factory.create_for_path(context.source_path)
            document = adapter.load(context.source_path)
            if not isinstance(adapter, TranslationAdapter):
                raise TypeError(f"adapter does not support translation: {adapter.document_type}")

            result = adapter.translate(context)
            if result.ok:
                adapter.save(document, context.output_path)

            return self._with_metrics(
                result=result,
                context=context,
                document_type=adapter.document_type,
                start_time=start_time,
            )
        except Exception as error:
            return self._with_metrics(
                result=PipelineResult(
                    status=PipelineStatus.FAILED,
                    task=context.task,
                    errors=(f"Translation pipeline failed: {error}",),
                ),
                context=context,
                document_type=None,
                start_time=start_time,
            )

    def _validate_context(self, context: PipelineContext) -> None:
        if context.task != "translation":
            raise ValueError(f"unsupported task for TranslationPipeline: {context.task}")
        if context.source_path is None:
            raise ValueError("source_path is required")
        if context.output_path is None:
            raise ValueError("output_path is required")
        if not context.target_language:
            raise ValueError("target_language is required")
        if context.resolved_provider is None:
            raise ValueError("resolved_provider is required")

    def _resolve_context(self, context: PipelineContext) -> PipelineContext:
        resolved_provider = self._provider_resolver.resolve(
            provider=context.provider or None,
            model=context.model or None,
        )
        runtime_options = dict(context.runtime_options)
        runtime_options.setdefault("concurrency", self._settings.concurrency)
        runtime_options.setdefault("retry_count", self._settings.retry_count)
        runtime_options.setdefault("timeout", self._settings.timeout)
        runtime_options.setdefault("enable_cache", self._settings.enable_cache)
        runtime_options.setdefault("log_level", self._settings.log_level)
        runtime_options.setdefault("output_directory", str(self._settings.output_directory))

        if context.output_path is not None:
            context.output_path.parent.mkdir(parents=True, exist_ok=True)

        return replace(
            context,
            provider=resolved_provider.id,
            model=resolved_provider.model,
            target_language=context.target_language or self._settings.target_language,
            runtime_options=runtime_options,
            resolved_provider=resolved_provider,
        )

    def _with_metrics(
        self,
        result: PipelineResult,
        context: PipelineContext,
        document_type: str | None,
        start_time: datetime,
    ) -> PipelineResult:
        end_time = datetime.now(UTC)
        metadata = dict(result.metadata)
        metadata.setdefault("document_type", document_type)
        metadata.setdefault("provider", context.provider)
        metadata.setdefault("model", context.model)
        return replace(
            result,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=(end_time - start_time).total_seconds(),
            metadata=metadata,
        )
