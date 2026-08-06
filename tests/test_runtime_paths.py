import os
from pathlib import Path
import tempfile
import unittest

from max_agent.runtime_paths import configure_hf_modules_cache


class RuntimePathTests(unittest.TestCase):
    def test_hf_modules_cache_uses_writable_ignored_artifact_directory(self) -> None:
        previous = os.environ.get("HF_MODULES_CACHE")
        try:
            with tempfile.TemporaryDirectory() as directory:
                cache_dir = configure_hf_modules_cache(Path(directory))

                self.assertEqual(cache_dir, Path(directory) / "hf_modules")
                self.assertTrue(cache_dir.is_dir())
                self.assertEqual(os.environ["HF_MODULES_CACHE"], str(cache_dir))
        finally:
            if previous is None:
                os.environ.pop("HF_MODULES_CACHE", None)
            else:
                os.environ["HF_MODULES_CACHE"] = previous
