"""Entry point for the PyInstaller build.

PyInstaller starts a script rather than a module, and ``processfreezer/app.py``
uses relative imports, so the bundle goes through this wrapper.
"""

import sys

from processfreezer.app import main

if __name__ == "__main__":
    sys.exit(main())
