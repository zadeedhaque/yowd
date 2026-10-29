"""Start the YOWD Delivery Management System (console front end).

Usage:
    python main.py                 # uses ./data
    python main.py --data DIR      # use another data folder
    python main.py --reset         # delete saved records, re-seed

All behaviour lives in classes; this file only locates the program's
folder (also when packaged as yowd_dms.pyz) and starts the application.
"""

import sys
from pathlib import Path

from yowd.ui.console_application import ConsoleApplication

if __name__ == "__main__":
    HOME = Path(__file__).resolve().parent
    if HOME.is_file():          # running from the packaged yowd_dms.pyz
        HOME = HOME.parent
    sys.exit(ConsoleApplication(HOME).run(sys.argv[1:]))
