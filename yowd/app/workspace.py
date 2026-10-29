"""Workspace: where the running system keeps its documents.

The facade asks a Workspace for every piece of storage it needs, so the
same system runs from a folder on disk (console), entirely in memory
(unit tests) or in the browser (web UI) without any change to the
application or domain code.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from yowd.domain.ports import TextStorage
from yowd.services.storage import FileTextStorage, MemoryTextStorage


class Workspace(ABC):
    """Abstract source of named text documents."""

    @abstractmethod
    def config(self) -> TextStorage:
        """The business settings document (config.json)."""

    @abstractmethod
    def records(self) -> TextStorage:
        """All saved records (yowd_data.json)."""

    @abstractmethod
    def outbox(self) -> TextStorage:
        """Log of SMS/email messages sent (outbox.log)."""

    @abstractmethod
    def device_queue(self, staff_id: str) -> TextStorage:
        """One driver's offline queue (stands in for the phone)."""

    @abstractmethod
    def export(self, file_name: str) -> TextStorage:
        """Where an exported report is written."""

    def reset(self) -> None:
        """Forget records, messages and queues (keeps the settings)."""
        self.records().delete()
        self.outbox().delete()


class FolderWorkspace(Workspace):
    """Documents as files in a data folder (console application)."""

    __slots__ = ("__folder",)

    def __init__(self, folder: Path) -> None:
        self.__folder = Path(folder)

    @property
    def folder(self) -> Path:
        """The data folder."""
        return self.__folder

    def config(self) -> TextStorage:
        """data/config.json"""
        return FileTextStorage(self.__folder / "config.json")

    def records(self) -> TextStorage:
        """data/yowd_data.json"""
        return FileTextStorage(self.__folder / "yowd_data.json")

    def outbox(self) -> TextStorage:
        """data/outbox.log"""
        return FileTextStorage(self.__folder / "outbox.log")

    def device_queue(self, staff_id: str) -> TextStorage:
        """data/device/<staff>_queue.json"""
        return FileTextStorage(self.__folder / "device"
                               / f"{staff_id}_queue.json")

    def export(self, file_name: str) -> TextStorage:
        """data/exports/<file_name>"""
        return FileTextStorage(self.__folder / "exports" / file_name)

    def reset(self) -> None:
        """Delete records, messages and every device queue."""
        super().reset()
        device = self.__folder / "device"
        if device.is_dir():
            for queue in device.glob("*_queue.json"):
                queue.unlink()


class MemoryWorkspace(Workspace):
    """Documents held in memory (tests, and the browser front end)."""

    __slots__ = ("__documents",)

    def __init__(self, config_text: str) -> None:
        self.__documents: dict[str, MemoryTextStorage] = {
            "config.json": MemoryTextStorage(config_text)}

    def document(self, name: str) -> MemoryTextStorage:
        """The named document, created empty on first use."""
        return self.__documents.setdefault(name, MemoryTextStorage())

    def names(self) -> list[str]:
        """Names of every document that holds text."""
        return [name for name, doc in self.__documents.items()
                if doc.exists()]

    def config(self) -> TextStorage:
        """config.json"""
        return self.document("config.json")

    def records(self) -> TextStorage:
        """yowd_data.json"""
        return self.document("yowd_data.json")

    def outbox(self) -> TextStorage:
        """outbox.log"""
        return self.document("outbox.log")

    def device_queue(self, staff_id: str) -> TextStorage:
        """device/<staff>_queue.json"""
        return self.document(f"device/{staff_id}_queue.json")

    def export(self, file_name: str) -> TextStorage:
        """exports/<file_name>"""
        return self.document(f"exports/{file_name}")

    def reset(self) -> None:
        """Forget everything except the settings."""
        for name, doc in self.__documents.items():
            if name != "config.json":
                doc.delete()
