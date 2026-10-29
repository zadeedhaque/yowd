"""Package the console program as one executable file: yowd_dms.pyz.

Usage (from the repository root):  python tools/build_executable.py
"""

import shutil
import sys
import tempfile
import zipapp
from pathlib import Path


class ExecutableBuilder:
    """Builds a Python zipapp containing the yowd package and main.py."""

    __slots__ = ("__root",)

    def __init__(self, root: Path) -> None:
        self.__root = Path(root)

    def build(self, target_name: str = "yowd_dms.pyz") -> Path:
        """Copy the sources to a temporary folder and zip them."""
        target = self.__root / target_name
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp)
            shutil.copytree(self.__root / "yowd", stage / "yowd",
                            ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy(self.__root / "main.py", stage / "__main__.py")
            zipapp.create_archive(stage, target,
                                  interpreter="/usr/bin/env python3",
                                  compressed=True)
        return target


if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parent.parent
    print(f"Built {ExecutableBuilder(ROOT).build()}")
    sys.exit(0)
