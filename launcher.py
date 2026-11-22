"""PyInstaller entry point (keeps package-relative imports working in the frozen app)."""
import sys

from inside_voice.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
