from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from max_agent.model_runtime import load_qwen35_model, require_complete_local_model


class ModelRuntimeTests(unittest.TestCase):
    def test_qwen35_loader_uses_native_offline_bf16_transformers_loader(self) -> None:
        loaded_model = Mock()
        loaded_model.to.return_value = loaded_model
        loaded_model.eval.return_value = loaded_model

        with patch("transformers.AutoModelForMultimodalLM.from_pretrained", return_value=loaded_model) as loader:
            result = load_qwen35_model(Path("C:/repo/model/Qwen/Qwen3.5-4B"))

        self.assertIs(result, loaded_model)
        self.assertIn("dtype", loader.call_args.kwargs)
        self.assertNotIn("torch_dtype", loader.call_args.kwargs)
        self.assertEqual(loader.call_args.kwargs["local_files_only"], True)
        self.assertNotIn("trust_remote_code", loader.call_args.kwargs)

    def test_offline_model_loader_rejects_missing_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            target = repository / "model" / "Qwen" / "Qwen3.5-4B"
            target.mkdir(parents=True)
            with self.assertRaisesRegex(FileNotFoundError, "offline benchmark requires"):
                require_complete_local_model(repository, target)

    def test_offline_model_loader_accepts_local_model_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model_dir = Path(directory)
            (model_dir / "config.json").write_text("{}", encoding="utf-8")

            repository = model_dir / "repository"
            target = repository / "model" / "Qwen" / "Qwen3.5-4B"
            target.mkdir(parents=True)
            (target / "config.json").write_text("{}", encoding="utf-8")

            self.assertEqual(require_complete_local_model(repository, target), target)
