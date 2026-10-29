"""Build the static web site for GitHub Pages into ./site.

Usage (from the repository root):
    python tools/build_web.py                 # site loads Pyodide from CDN
    python tools/build_web.py --pyodide       # also vendor Pyodide into site
    python tools/build_web.py --pyodide-archive core.tar.bz2

The site is plain static files: the page (web/), the yowd Python package
and config.json zipped as app.zip, and optionally a copy of Pyodide so
the site does not depend on a CDN.
"""

import argparse
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path


class WebSiteBuilder:
    """Assembles the static site from the sources."""

    PYODIDE_VERSION = "0.27.7"
    PYODIDE_URL = ("https://github.com/pyodide/pyodide/releases/download/"
                   "{v}/pyodide-core-{v}.tar.bz2")
    __slots__ = ("__root", "__site")

    def __init__(self, root: Path, site: Path) -> None:
        self.__root = Path(root)
        self.__site = Path(site)

    def build(self, vendor: bool = False,
              archive: Path | None = None) -> Path:
        """Create the site folder; return its path."""
        if self.__site.exists():
            shutil.rmtree(self.__site)
        shutil.copytree(self.__root / "web", self.__site)
        (self.__site / ".nojekyll").write_text("", encoding="utf-8")
        self.__bundle_python()
        if vendor or archive:
            self.__vendor_pyodide(archive)
        return self.__site

    def __bundle_python(self) -> None:
        """Zip the yowd package (minus the console UI) and config.json."""
        target = self.__site / "app.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted((self.__root / "yowd").rglob("*.py")):
                relative = path.relative_to(self.__root)
                if relative.parts[1] == "ui":
                    continue
                bundle.write(path, relative.as_posix())
            bundle.write(self.__root / "data" / "config.json", "config.json")

    def __vendor_pyodide(self, archive: Path | None) -> None:
        """Unpack the Pyodide core runtime into site/pyodide."""
        with tempfile.TemporaryDirectory() as temp:
            if archive is None:
                archive = Path(temp) / "pyodide.tar.bz2"
                url = self.PYODIDE_URL.format(v=self.PYODIDE_VERSION)
                with urllib.request.urlopen(url) as reply, \
                        archive.open("wb") as handle:
                    shutil.copyfileobj(reply, handle)
            with tarfile.open(archive, "r:bz2") as tar:
                tar.extractall(temp, filter="data")
            shutil.copytree(Path(temp) / "pyodide",
                            self.__site / "pyodide")


class BuildCommand:
    """Command-line wrapper around WebSiteBuilder."""

    def run(self, argv: list[str]) -> int:
        """Parse options and build."""
        parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
        parser.add_argument("--pyodide", action="store_true",
                            help="download Pyodide and include it")
        parser.add_argument("--pyodide-archive", type=Path,
                            help="use a downloaded pyodide-core tar.bz2")
        options = parser.parse_args(argv)
        root = Path(__file__).resolve().parent.parent
        site = WebSiteBuilder(root, root / "site").build(
            options.pyodide, options.pyodide_archive)
        print(f"Built {site}")
        return 0


if __name__ == "__main__":
    sys.exit(BuildCommand().run(sys.argv[1:]))
