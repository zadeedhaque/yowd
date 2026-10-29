"""ConsoleApplication: command-line start-up of the console front end.

Bootstrap step 1: it reads the command-line options, chooses the data
folder (a FolderWorkspace), creates the DeliveryManagementSystem - which
creates every other long-lived object - and hands over to the MainMenu.
"""

import argparse
import sys
from pathlib import Path

from yowd.app.system import DeliveryManagementSystem
from yowd.app.workspace import FolderWorkspace
from yowd.domain.errors import DmsError
from yowd.ui.console import Console
from yowd.ui.main_menu import MainMenu


class ConsoleApplication:
    """Parses options and runs the console user interface."""

    __slots__ = ("__home", "__console")

    def __init__(self, home: Path, console: Console | None = None) -> None:
        self.__home = Path(home)
        self.__console = console

    def run(self, argv: list[str]) -> int:
        """Start the program; return the process exit code."""
        options = self.__parser().parse_args(argv)
        workspace = FolderWorkspace(options.data)
        if not workspace.config().exists():
            print(f"config.json not found in {options.data}",
                  file=sys.stderr)
            return 2
        if options.reset:
            workspace.reset()
        try:
            system = DeliveryManagementSystem(workspace)
        except (DmsError, OSError, ValueError, KeyError) as error:
            print(f"The system could not start: {error}", file=sys.stderr)
            return 1
        MainMenu(self.__console or Console(), system).run()
        return 0

    def __parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description="YOWD Delivery Management System (console)")
        parser.add_argument("--data", type=Path, default=self.__home / "data",
                            help="folder holding config.json and the "
                                 "records")
        parser.add_argument("--reset", action="store_true",
                            help="delete saved records and start from the "
                                 "sample data")
        return parser
