"""验证离线模型与图像预检拒绝不完整、越界或不可读输入。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from max_agent.model_runtime import (
    load_qwen35_model,
    require_complete_local_model,
    require_readable_image,
)


class ModelRuntimeTests(unittest.TestCase):
    def _complete_model(self, repository: Path) -> Path:
        target = repository / "model" / "Qwen" / "Qwen3.5-4B"
        target.mkdir(parents=True)
        for name in ("config.json", "preprocessor_config.json", "tokenizer.json"):
            (target / name).write_text("{}", encoding="utf-8")
        (target / "model.safetensors").write_bytes(b"weights")
        (target / "model.safetensors.index.json").write_text(
            '{"weight_map": {"layer": "model.safetensors"}}', encoding="utf-8"
        )
        return target

    def test_qwen35_loader_uses_native_offline_bf16_transformers_loader(self) -> None:
        loaded_model = Mock()
        loaded_model.to.return_value = loaded_model
        loaded_model.eval.return_value = loaded_model

        with (
            patch("torch.cuda.is_available", return_value=False),
            patch("torch.cuda.reset_peak_memory_stats") as reset_peak_memory,
            patch(
                "transformers.AutoModelForMultimodalLM.from_pretrained",
                return_value=loaded_model,
            ) as loader,
        ):
            result = load_qwen35_model(Path("C:/repo/model/Qwen/Qwen3.5-4B"))

        self.assertIs(result, loaded_model)
        self.assertIn("dtype", loader.call_args.kwargs)
        self.assertNotIn("torch_dtype", loader.call_args.kwargs)
        self.assertEqual(loader.call_args.kwargs["local_files_only"], True)
        self.assertNotIn("trust_remote_code", loader.call_args.kwargs)
        reset_peak_memory.assert_not_called()

    def test_offline_model_loader_rejects_missing_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            target = repository / "model" / "Qwen" / "Qwen3.5-4B"
            target.mkdir(parents=True)
            with self.assertRaisesRegex(
                FileNotFoundError, "offline benchmark requires"
            ):
                require_complete_local_model(repository, target)

    def test_offline_model_loader_accepts_complete_local_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            target = self._complete_model(repository)

            self.assertTrue(
                require_complete_local_model(repository, target).samefile(target)
            )

    def test_offline_model_loader_rejects_another_project_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            self._complete_model(repository)
            other_model = repository / "model" / "Qwen" / "another-model"
            other_model.mkdir(parents=True)

            with self.assertRaisesRegex(ValueError, "supported local Qwen3.5-4B"):
                require_complete_local_model(repository, other_model)

    def test_offline_model_loader_rejects_missing_weight_shard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            target = self._complete_model(repository)
            (target / "model.safetensors").unlink()

            with self.assertRaisesRegex(
                FileNotFoundError, "complete local Qwen3.5-4B weights"
            ):
                require_complete_local_model(repository, target)

    def test_image_preflight_accepts_readable_image_and_rejects_invalid_input(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.ppm"
            image.write_bytes(b"P6\n1 1\n255\n\x00\x00\x00")
            self.assertEqual(require_readable_image(image), image.resolve())
            invalid = Path(directory) / "invalid-image"
            invalid.write_text("not an image", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "readable local image"):
                require_readable_image(invalid)
