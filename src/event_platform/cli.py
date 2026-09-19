"""Reviewer-facing command line entry points."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from event_platform.search.rebuild import main as rebuild_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="event_platform")
    subparsers = parser.add_subparsers(dest="domain", required=True)
    search = subparsers.add_parser("search")
    search_subparsers = search.add_subparsers(dest="command", required=True)
    rebuild = search_subparsers.add_parser("rebuild")
    rebuild.add_argument("--confirm", action="store_true")
    status = search_subparsers.add_parser("rebuild-status")
    status.add_argument("--rebuild-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "rebuild":
        rebuild_args = ["run"] + (["--confirm"] if args.confirm else [])
    else:
        rebuild_args = ["status"]
        if args.rebuild_id:
            rebuild_args.extend(["--rebuild-id", args.rebuild_id])
    return rebuild_main(rebuild_args)


if __name__ == "__main__":
    raise SystemExit(main())
