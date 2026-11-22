"""Entry point:  python -m inside_voice  [--minimized] [--selftest [--out FILE]]"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="inside-voice", description="Inside Voice - Shh... they can hear you.")
    parser.add_argument("--minimized", action="store_true", help="start in the tray without opening the window")
    parser.add_argument("--selftest", action="store_true", help="run built-in checks and exit")
    parser.add_argument("--out", default=None, help="write selftest output to this file")
    args = parser.parse_args(argv)

    if args.selftest:
        from .selftest import run

        return run(args.out)

    from .main import run_app

    return run_app(minimized=args.minimized)


if __name__ == "__main__":
    sys.exit(main())
