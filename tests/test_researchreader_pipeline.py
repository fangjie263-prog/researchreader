import tempfile
import unittest
from pathlib import Path

from researchreader.researchreader.pipeline import Pipeline, PipelineContext, PipelineResult, PipelineStatus


class TestPipelineContext(unittest.TestCase):
    def test_context_carries_core_pipeline_inputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = PipelineContext(
                task="translation",
                provider="openai",
                model="gpt-4o-mini",
                target_language="Chinese",
                working_directory=Path(temp_dir),
                runtime_options={"concurrency": 2},
                adapter="epub",
                source_path=Path("source.epub"),
                output_path=Path("translated.epub"),
            )

        self.assertEqual(context.task, "translation")
        self.assertEqual(context.provider, "openai")
        self.assertEqual(context.model, "gpt-4o-mini")
        self.assertEqual(context.target_language, "Chinese")
        self.assertEqual(context.runtime_options["concurrency"], 2)
        self.assertEqual(context.adapter, "epub")


class TestPipelineResult(unittest.TestCase):
    def test_success_result_has_ok_property(self):
        result = PipelineResult(
            status=PipelineStatus.SUCCESS,
            task="summary",
            artifacts=(Path("summary.md"),),
            metadata={"sections": 3},
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.artifacts, (Path("summary.md"),))
        self.assertEqual(result.metadata["sections"], 3)

    def test_failed_result_has_errors(self):
        result = PipelineResult(
            status=PipelineStatus.FAILED,
            task="chat",
            errors=("missing index",),
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.errors, ("missing index",))


class TestPipelineInterface(unittest.TestCase):
    def test_pipeline_subclass_runs_with_context(self):
        pipeline = _NoopPipeline()
        context = PipelineContext(task="research", provider="openai", model="gpt-4o-mini")

        result = pipeline.run(context)

        self.assertTrue(result.ok)
        self.assertEqual(result.task, "research")


class _NoopPipeline(Pipeline):
    def run(self, context: PipelineContext) -> PipelineResult:
        return PipelineResult(status=PipelineStatus.SUCCESS, task=context.task)
