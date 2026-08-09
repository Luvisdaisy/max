from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPOSITORY_ROOT / "requirements.txt"
LEGACY_MANIFESTS = (
    REPOSITORY_ROOT / "requirements" / "base.txt",
    REPOSITORY_ROOT / "requirements" / "constraints.txt",
    REPOSITORY_ROOT / "requirements" / "torch-cu130.txt",
)


def _normalized_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        name, separator, version = stripped.partition("==")
        if separator:
            pins[name.lower().replace("_", "-")] = version
    return pins


class RequirementsManifestTests(unittest.TestCase):
    def test_root_manifest_is_the_complete_install_entry_point(self) -> None:
        content = MANIFEST.read_text(encoding="utf-8")
        self.assertIn(
            "--extra-index-url https://download.pytorch.org/whl/cu130", content
        )
        self.assertIn("\n-e .\n", f"\n{content.rstrip()}\n")
        self.assertEqual(
            {
                "langchain": "1.3.14",
                "langgraph": "1.2.10",
                "modelscope": "1.39.1",
                "textual": "8.1.1",
                "transformers": "5.14.1",
                "ruff": "0.16.2",
                "torch": "2.13.0+cu130",
                "torchvision": "0.28.0+cu130",
                "pillow": "11.3.0",
                "numpy": "2.3.5",
                "opencv-contrib-python": "4.10.0.84",
                "mss": "10.2.0",
                "pyautogui": "0.9.54",
                "pynput": "1.8.2",
                "pywinauto": "0.6.9",
                "paddlepaddle": "3.3.1",
                "paddleocr": "3.7.0",
                "pydantic": "2.13.4",
            },
            _normalized_pins(),
        )

    def test_package_metadata_dependencies_are_pinned_in_root_manifest(self) -> None:
        project = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        manifest_pins = _normalized_pins()
        for requirement in project["dependencies"]:
            name, separator, version = requirement.partition("==")
            self.assertEqual("==", separator)
            self.assertEqual(version, manifest_pins[name.lower().replace("_", "-")])

    def test_split_requirements_manifests_are_removed(self) -> None:
        self.assertFalse(
            [
                str(path.relative_to(REPOSITORY_ROOT))
                for path in LEGACY_MANIFESTS
                if path.exists()
            ]
        )


if __name__ == "__main__":
    unittest.main()
