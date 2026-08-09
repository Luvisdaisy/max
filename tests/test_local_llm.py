import asyncio
import tempfile
import unittest
from pathlib import Path

from max_agent.console_core import OperationResult
from max_agent.console_frontends import create_textual_chat_app
from max_agent.local_llm import LocalChatRuntime, LocalRuntimeError, require_qwen35_2b


class LocalLlmTests(unittest.TestCase):
    def _model_dir(self, root: Path) -> Path:
        directory = root / "model" / "Qwen" / "Qwen3.5-2B"
        directory.mkdir(parents=True)
        for name in ("config.json", "tokenizer.json"):
            (directory / name).write_text("{}", encoding="utf-8")
        (directory / "model.safetensors").write_bytes(b"weights")
        (directory / "model.safetensors.index.json").write_text(
            '{"weight_map": {"weight": "model.safetensors"}}', encoding="utf-8"
        )
        return directory

    def test_runtime_loads_once_and_reuses_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._model_dir(root)
            loads: list[Path] = []
            runtime = LocalChatRuntime(
                root,
                loader=lambda path: (loads.append(path) or "model", "processor"),
                generator=lambda model, processor, history, message: f"reply:{message}",
            )

            self.assertEqual(runtime.reply("hello"), "reply:hello")
            self.assertEqual(runtime.reply("again"), "reply:again")
            self.assertEqual(len(loads), 1)
            self.assertEqual(runtime.state, "ready")

    def test_runtime_rejects_incomplete_local_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(LocalRuntimeError):
                require_qwen35_2b(Path(temporary))

    def test_generation_failure_keeps_runtime_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._model_dir(root)
            runtime = LocalChatRuntime(
                root,
                loader=lambda path: ("model", "processor"),
                generator=lambda *args: (_ for _ in ()).throw(
                    LocalRuntimeError("generation failed")
                ),
            )

            with self.assertRaisesRegex(LocalRuntimeError, "generation failed"):
                runtime.reply("hello")
            self.assertEqual(runtime.state, "failed")

    def test_textual_slash_commands_render_without_model_loading(self) -> None:
        async def exercise() -> None:
            calls: list[str] = []
            app = create_textual_chat_app(
                lambda value: (
                    calls.append(value) or OperationResult("doctor", ("doctor-result",))
                )
            )
            async with app.run_test() as pilot:
                await pilot.click("#chat-input")
                await pilot.press("/", "d", "o", "c", "t", "o", "r", "enter")
                self.assertEqual(calls, ["/doctor"])

        asyncio.run(exercise())
