"""TextStorage adapters: a file on disk, or memory (tests, browser)."""

import os
from pathlib import Path

from yowd.domain.ports import TextStorage


class FileTextStorage(TextStorage):
    """A text file, written atomically (temp file + rename, QR4)."""

    __slots__ = ("__path",)

    def __init__(self, path: Path) -> None:
        self.__path = Path(path)

    @property
    def path(self) -> Path:
        """Location of the file."""
        return self.__path

    def exists(self) -> bool:
        """True if the file is there."""
        return self.__path.exists()

    def read(self) -> str:
        """Whole file as text."""
        return self.__path.read_text(encoding="utf-8")

    def write(self, text: str) -> None:
        """Replace the file without ever leaving it half-written."""
        self.__path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.__path.with_name(self.__path.name + ".tmp")
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, self.__path)

    def delete(self) -> None:
        """Remove the file if present."""
        self.__path.unlink(missing_ok=True)


class MemoryTextStorage(TextStorage):
    """Keeps the document in memory (tests, or a browser that syncs it)."""

    __slots__ = ("__text",)

    def __init__(self, text: str | None = None) -> None:
        self.__text = text

    def exists(self) -> bool:
        """True once something has been written."""
        return self.__text is not None

    def read(self) -> str:
        """The stored text ("" if none)."""
        return self.__text or ""

    def write(self, text: str) -> None:
        """Replace the stored text."""
        self.__text = text

    def delete(self) -> None:
        """Forget the stored text."""
        self.__text = None
