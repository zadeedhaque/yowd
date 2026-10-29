"""MessageOutbox adapters: where 'sent' SMS and email messages go."""

from datetime import datetime

from yowd.domain.ports import MessageOutbox, TextStorage


class StorageOutbox(MessageOutbox):
    """Appends each message as a line to a TextStorage document."""

    __slots__ = ("__storage",)

    def __init__(self, storage: TextStorage) -> None:
        self.__storage = storage

    def post(self, stamp: datetime, line: str) -> None:
        """Add one line: '<timestamp> <message>'."""
        previous = self.__storage.read() if self.__storage.exists() else ""
        self.__storage.write(previous + f"{stamp.isoformat()} {line}\n")


class MemoryOutbox(MessageOutbox):
    """Keeps messages in a list (tests)."""

    __slots__ = ("__lines",)

    def __init__(self) -> None:
        self.__lines: list[str] = []

    @property
    def lines(self) -> tuple[str, ...]:
        """Messages posted so far."""
        return tuple(self.__lines)

    def post(self, stamp: datetime, line: str) -> None:
        """Remember the message."""
        self.__lines.append(line)
