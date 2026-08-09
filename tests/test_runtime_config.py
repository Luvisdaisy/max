import unittest
from pathlib import Path

from max_agent.config import ModelConfig, assert_project_model_dir


class RuntimeConfigTests(unittest.TestCase):
    def test_model_directory_rejects_path_outside_project_model_tree(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the repository"):
            assert_project_model_dir(Path("C:/repo"), Path("F:/AI/models"))

    def test_model_directory_accepts_path_below_project_model_tree(self) -> None:
        assert_project_model_dir(
            Path("C:/repo"), Path("C:/repo/model/ZhipuAI/glm-4v-9b")
        )

    def test_model_config_requires_non_empty_revision(self) -> None:
        with self.assertRaisesRegex(ValueError, "revision"):
            ModelConfig(
                model_id="ZhipuAI/glm-4v-9b",
                revision="",
                model_dir=Path("C:/repo/model/ZhipuAI/glm-4v-9b"),
            )
