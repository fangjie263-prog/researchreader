from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from ..pipeline import PipelineContext, PipelineResult, PipelineStatus
from .base import DocumentAdapter, TranslationAdapter


@dataclass(frozen=True)
class EPUBDocument:
    source_path: Path
    translated_path: Path | None = None


class EPUBAdapter(DocumentAdapter, TranslationAdapter):
    document_type = "epub"

    def load(self, source_path: Path) -> EPUBDocument:
        path = Path(source_path)
        self._validate_source_path(path)
        return EPUBDocument(source_path=path.resolve())

    def save(self, document: Any, output_path: Path) -> None:
        if not isinstance(document, EPUBDocument):
            raise ValueError("EPUBAdapter.save expects an EPUBDocument")
        target_path = Path(output_path)
        self._validate_epub_extension(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if document.translated_path is None:
            if target_path.exists():
                return
            raise ValueError("EPUBDocument does not contain a translated output path")
        shutil.copyfile(document.translated_path, target_path)

    def detect(self, source_path: Path) -> bool:
        return Path(source_path).suffix.lower() == ".epub"

    def metadata(self, document: Any) -> dict[str, Any]:
        if not isinstance(document, EPUBDocument):
            raise ValueError("EPUBAdapter.metadata expects an EPUBDocument")
        return {
            "document_type": self.document_type,
            "source_path": str(document.source_path),
        }

    def translate(self, context: PipelineContext) -> PipelineResult:
        try:
            source_path, output_path = self._paths_from_context(context)
            self._validate_source_path(source_path)
            self._validate_epub_extension(output_path)

            target_language = context.target_language
            if not target_language:
                raise ValueError("target_language is required for EPUB translation")

            backend = _load_epub_backend()
            llm = self._llm_from_context(context, backend.LLM)
            submit = context.runtime_options.get("submit", backend.SubmitKind.APPEND_BLOCK)
            if isinstance(submit, str):
                submit = backend.SubmitKind[submit]

            try:
                backend.translate(
                    source_path=source_path,
                    target_path=output_path,
                    target_language=target_language,
                    submit=submit,
                    llm=llm,
                )
            finally:
                self._close_llm(llm)

            return PipelineResult(
                status=PipelineStatus.SUCCESS,
                task=context.task,
                artifacts=(output_path,),
                metadata={
                    "adapter": self.document_type,
                    "provider": context.provider,
                    "model": context.model,
                    "target_language": target_language,
                },
            )
        except Exception as error:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                task=context.task,
                errors=(f"EPUB translation failed: {error}",),
            )

    def _paths_from_context(self, context: PipelineContext) -> tuple[Path, Path]:
        if context.source_path is None:
            raise ValueError("source_path is required")
        if context.output_path is None:
            raise ValueError("output_path is required")
        return Path(context.source_path), Path(context.output_path)

    def _llm_from_context(self, context: PipelineContext, llm_class: Any) -> Any:
        resolved_provider = context.resolved_provider
        api_key = getattr(resolved_provider, "api_key", None) or context.runtime_options.get("api_key")
        base_url = getattr(resolved_provider, "base_url", None) or context.runtime_options.get("base_url")
        model = getattr(resolved_provider, "model", None) or context.model
        token_encoding = context.runtime_options.get("token_encoding", "o200k_base")
        if not api_key:
            raise ValueError("provider API key is required")
        if not base_url:
            raise ValueError("provider base_url is required")
        return llm_class(
            key=str(api_key),
            url=str(base_url),
            model=str(model),
            token_encoding=str(token_encoding),
            cache_path=context.runtime_options.get("cache_path"),
            log_dir_path=context.runtime_options.get("log_dir_path"),
        )

    def _close_llm(self, llm: Any) -> None:
        close = getattr(llm, "close", None)
        if callable(close):
            close()
            return

        executor = getattr(llm, "_executor", None)
        executor_close = getattr(executor, "close", None)
        if callable(executor_close):
            executor_close()
            return

        client = getattr(executor, "_client", None)
        client_close = getattr(client, "close", None)
        if callable(client_close):
            client_close()

    def _validate_source_path(self, source_path: Path) -> None:
        self._validate_epub_extension(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"EPUB source file does not exist: {source_path}")
        if not source_path.is_file():
            raise ValueError(f"EPUB source path is not a file: {source_path}")

    def _validate_epub_extension(self, path: Path) -> None:
        if path.suffix.lower() != ".epub":
            raise ValueError(f"expected an .epub file: {path}")


def _load_epub_backend() -> Any:
    return import_module("epub_translator")
