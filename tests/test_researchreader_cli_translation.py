import io
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from enum import Enum
from pathlib import Path
from unittest.mock import patch

from researchreader.researchreader.cli.main import main
from researchreader.researchreader.config.settings import Settings


class TestCLITranslation(unittest.TestCase):
    def test_translate_command_runs_end_to_end_with_mock_epub_backend(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "book.epub"
            output_path = temp_path / "translated.epub"
            source_path.write_bytes(b"fake epub")

            result_code, output = self._run_translate(
                ["translate", str(source_path), str(output_path)],
                temp_path,
                backend=_FakeEPUBBackend(),
            )

            self.assertEqual(result_code, 0)
            self.assertIn("Translation completed successfully.", output)
            self.assertIn("Provider: deepseek", output)
            self.assertIn("Model: deepseek-chat", output)
            self.assertIn("Target language: Chinese", output)
            self.assertTrue(output_path.exists())

    def test_translate_command_generates_default_output_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "paper.epub"
            expected_output = temp_path / "output" / "paper_translated.epub"
            source_path.write_bytes(b"fake epub")

            result_code, output = self._run_translate(
                ["translate", str(source_path)],
                temp_path,
                backend=_FakeEPUBBackend(),
            )

            self.assertEqual(result_code, 0)
            self.assertIn(str(expected_output), output)
            self.assertTrue(expected_output.exists())

    def test_translate_command_reports_missing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            missing_path = temp_path / "missing.epub"

            result_code, output = self._run_translate(
                ["translate", str(missing_path)],
                temp_path,
                backend=_FakeEPUBBackend(),
            )

        self.assertEqual(result_code, 1)
        self.assertIn("Translation failed.", output)
        self.assertIn("does not exist", output)

    def test_translate_command_reports_invalid_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "paper.pdf"
            source_path.write_bytes(b"fake pdf")

            result_code, output = self._run_translate(
                ["translate", str(source_path)],
                temp_path,
                backend=_FakeEPUBBackend(),
            )

        self.assertEqual(result_code, 1)
        self.assertIn("Translation failed.", output)
        self.assertIn("unknown document adapter", output)

    def test_translate_command_reports_translation_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "book.epub"
            source_path.write_bytes(b"fake epub")

            result_code, output = self._run_translate(
                ["translate", str(source_path)],
                temp_path,
                backend=_FailingEPUBBackend(),
            )

        self.assertEqual(result_code, 1)
        self.assertIn("Translation failed.", output)
        self.assertIn("backend failed", output)

    def test_translate_process_exits_after_successful_translation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "book.epub"
            output_path = temp_path / "translated.epub"
            source_path.write_bytes(b"fake epub")
            sitecustomize_path = temp_path / "sitecustomize.py"
            sitecustomize_path.write_text(_FAKE_EPUB_TRANSLATOR_MODULE, encoding="utf-8")

            env = dict(os.environ)
            env["DEEPSEEK_API_KEY"] = "test-key"
            env["PYTHONPATH"] = str(temp_path) + os.pathsep + env.get("PYTHONPATH", "")

            completed = subprocess.run(
                [
                    sys.executable,
                    "run.py",
                    "translate",
                    str(source_path),
                    str(output_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("Translation completed successfully.", completed.stdout)
            self.assertTrue(output_path.exists())

    def _run_translate(self, argv: list[str], temp_path: Path, backend: object) -> tuple[int, str]:
        settings = Settings(output_directory=temp_path / "output")
        stdout = io.StringIO()
        with (
            patch("researchreader.researchreader.cli.main.load_settings", return_value=settings),
            patch("researchreader.researchreader.adapters.epub._load_epub_backend", return_value=backend),
            patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"}, clear=False),
            redirect_stdout(stdout),
        ):
            result_code = main(argv)
        return result_code, stdout.getvalue()


class _FakeSubmitKind(Enum):
    APPEND_BLOCK = 1


class _FakeEPUBBackend:
    SubmitKind = _FakeSubmitKind

    def LLM(self, **kwargs):
        return {"llm": kwargs}

    def translate(self, **kwargs):
        Path(kwargs["target_path"]).write_bytes(b"translated epub")


class _FailingEPUBBackend(_FakeEPUBBackend):
    def translate(self, **kwargs):
        raise RuntimeError("backend failed")


_FAKE_EPUB_TRANSLATOR_MODULE = textwrap.dedent(
    """
    import sys
    import threading
    import time
    import types
    from enum import Enum
    from pathlib import Path

    class SubmitKind(Enum):
        APPEND_BLOCK = 1

    class LLM:
        def __init__(self, **kwargs):
            self._stop = threading.Event()
            self._thread = threading.Thread(target=self._run)
            self._thread.start()

        def _run(self):
            while not self._stop.wait(0.05):
                pass

        def close(self):
            self._stop.set()
            self._thread.join(timeout=2)

    def translate(**kwargs):
        Path(kwargs["target_path"]).write_bytes(b"translated epub")

    module = types.ModuleType("epub_translator")
    module.LLM = LLM
    module.SubmitKind = SubmitKind
    module.translate = translate
    sys.modules["epub_translator"] = module
    """
)
