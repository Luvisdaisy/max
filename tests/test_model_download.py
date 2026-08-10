"""验证模型元数据与完整下载均使用受管目录和官方 CLI 参数。"""

import unittest
from pathlib import Path

from max_agent.config import ModelConfig
from max_agent.model_download import download_qwen35_model, validate_model_metadata


class ModelDownloadTests(unittest.TestCase):
    def test_metadata_validation_requests_only_config_file(self) -> None:
        received: dict[str, str] = {}

        def model_file_download(**kwargs: str) -> str:
            received.update(kwargs)
            return "F:/AI/models/modelscope/config.json"

        result = validate_model_metadata(
            ModelConfig(
                "ZhipuAI/glm-4v-9b",
                "revision-123",
                Path("C:/repo/model/ZhipuAI/glm-4v-9b"),
            ),
            Path("C:/repo"),
            model_file_download,
        )

        self.assertEqual(result.name, "config.json")
        self.assertEqual(received["file_path"], "config.json")
        self.assertEqual(received["revision"], "revision-123")

    def test_qwen35_download_uses_modelscope_cli_and_project_model_directory(
        self,
    ) -> None:
        received: list[str] = []

        def runner(command: list[str]) -> None:
            received.extend(command)

        target = download_qwen35_model(Path("C:/repo"), runner)

        self.assertEqual(target, Path("C:/repo/model/Qwen/Qwen3.5-4B"))
        self.assertEqual(
            received,
            [
                "modelscope",
                "download",
                "--model",
                "Qwen/Qwen3.5-4B",
                "--local_dir",
                "C:\\repo\\model\\Qwen\\Qwen3.5-4B",
            ],
        )
