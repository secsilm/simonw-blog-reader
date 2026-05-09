"""``simonw-fetch`` — fetch-only CLI used by the Claude Code skill.

Emits a JSON document containing the post body and the readable text of
each top-N referenced page, *without* calling any LLM. The host agent
(Claude) is expected to do the analysis itself.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from dotenv import load_dotenv

from .fetcher import FetchError
from .pipeline import fetch_with_references


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="simonw-fetch",
        description=(
            "Fetch a Simon Willison blog post and the readable text of each "
            "of its top references (one level deep). Emits JSON on stdout. "
            "Does not call any LLM."
        ),
    )
    p.add_argument("url", help="URL of the blog post to read")
    p.add_argument(
        "--max-refs",
        type=int,
        default=None,
        help="Maximum number of references to fetch (default: 8 / SIMONW_MAX_REFERENCES)",
    )
    p.add_argument(
        "--ref-chars",
        type=int,
        default=6000,
        help="Per-reference character cap on extracted text (default: 6000)",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose progress on stderr"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    def progress(msg: str) -> None:
        if args.verbose:
            print(f"[progress] {msg}", file=sys.stderr)

    try:
        result = fetch_with_references(
            args.url,
            max_references=args.max_refs,
            ref_char_limit=args.ref_chars,
            progress=progress,
        )
    except FetchError as exc:
        # Emit a JSON error payload so the agent can read it programmatically,
        # *and* set a non-zero exit code.
        json.dump(
            {"error": "fetch_failed", "url": args.url, "message": str(exc)},
            sys.stdout,
            ensure_ascii=False,
        )
        sys.stdout.write("\n")
        print(f"ERROR: failed to fetch the post: {exc}", file=sys.stderr)
        return 2

    json.dump(result.to_dict(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")

    if result.fetch_warnings:
        print(
            f"\nNote: {len(result.fetch_warnings)} reference(s) could not be fetched "
            "(see fetch_warnings in the JSON output).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
