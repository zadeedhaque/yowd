"""Console input/output helpers shared by every screen.

``Console`` wraps ``input``/``print`` so the screens can be driven by a
script in tests.  ``ask`` re-asks until a validator accepts the value,
which gives every field immediate validation with a helpful message
(SRS P2, QU7).
"""

import sys
from typing import Callable, Iterable, TypeVar

from yowd.domain.errors import DmsError

T = TypeVar("T")
WIDTH = 78


class EndOfInput(Exception):
    """Raised when the input stream ends (e.g. a scripted demo)."""


class Console:
    """Reads lines and prints text; echoes input when not a terminal."""

    def __init__(self, stream_in=None, stream_out=None) -> None:
        self.__in = stream_in or sys.stdin
        self.__out = stream_out or sys.stdout
        self.__echo = not self.__in.isatty()

    def say(self, text: str = "") -> None:
        """Print a line."""
        print(text.rstrip(), file=self.__out)

    def read(self, prompt: str) -> str:
        """Read one line after a prompt."""
        self.__out.write(prompt)
        self.__out.flush()
        line = self.__in.readline()
        if not line:
            raise EndOfInput()
        line = line.rstrip("\n")
        if self.__echo:
            self.__out.write(line + "\n")
        return line

    # --------------------------------------------------------- layout
    def header(self, title: str, subtitle: str = "") -> None:
        """Screen title bar."""
        self.say()
        self.say("=" * WIDTH)
        left = f"  {title}"
        self.say(left + subtitle.rjust(WIDTH - len(left) - 2))
        self.say("=" * WIDTH)

    def section(self, title: str) -> None:
        """Sub-heading inside a screen."""
        self.say(f"-- {title} " + "-" * max(0, WIDTH - len(title) - 4))

    def ok(self, text: str) -> None:
        """Success message."""
        self.say(f"  [OK] {text}")

    def error(self, text: str) -> None:
        """Validation or business-rule message."""
        self.say(f"  [!] {text}")

    def info(self, text: str) -> None:
        """Neutral message."""
        self.say(f"  {text}")

    def notices(self, lines: Iterable[str]) -> None:
        """Show notifications that the system just sent."""
        lines = list(lines)
        if lines:
            self.section("Notifications sent")
            for line in lines:
                self.say(f"  {line}")

    def table(self, headings: list[str], rows: list[list[str]]) -> None:
        """Simple fixed-width table."""
        if not rows:
            self.info("(none)")
            return
        widths = [max(len(str(h)), *(len(str(r[i])) for r in rows))
                  for i, h in enumerate(headings)]
        self.say("  " + "  ".join(str(h).ljust(w)
                                  for h, w in zip(headings, widths)))
        self.say("  " + "  ".join("-" * w for w in widths))
        for row in rows:
            self.say("  " + "  ".join(str(c).ljust(w)
                                      for c, w in zip(row, widths)))

    # ---------------------------------------------------------- input
    def ask(self, label: str, convert: Callable[[str], T],
            hint: str = "") -> T:
        """Ask until ``convert`` accepts the answer."""
        prompt = f"  {label}" + (f" [{hint}]" if hint else "") + ": "
        while True:
            raw = self.read(prompt)
            try:
                return convert(raw)
            except DmsError as error:
                self.error(str(error))

    def text(self, label: str, required: bool = True,
             hint: str = "") -> str:
        """Free text; blank is refused when required."""
        def check(raw: str) -> str:
            if required and not raw.strip():
                raise _Blank(f"{label} cannot be blank.")
            return raw.strip()
        return self.ask(label, check, hint)

    def choose(self, label: str, options: list[str]) -> str:
        """Choose one option key (case-insensitive)."""
        keys = [o.upper() for o in options]

        def check(raw: str) -> str:
            value = raw.strip().upper()
            if value not in keys:
                raise _Blank("Please enter one of: "
                             + ", ".join(options) + ".")
            return value
        return self.ask(label, check)

    def yes_no(self, label: str) -> bool:
        """Y or N."""
        return self.choose(label + " (Y/N)", ["Y", "N"]) == "Y"

    def menu(self, items: list[tuple[str, str]]) -> str:
        """Show numbered items and return the chosen key."""
        for key, text in items:
            self.say(f"  {key:>2}  {text}")
        self.say()
        return self.choose("Choose an option", [k for k, _ in items])

    def pause(self) -> None:
        """Wait for Enter."""
        self.read("  Press Enter to continue...")


class _Blank(DmsError):
    """Internal: blank or unknown menu input."""
