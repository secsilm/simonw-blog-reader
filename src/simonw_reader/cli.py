"""Command-line entry point: ``simonw-read <url>``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict

from dotenv import load_dotenv

from . import __all__ as _  # noqa: F401  ensure package import works
from .analyzer import AnalyzerError
from .fetcher import FetchError
from .pipeline import run


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="simonw-read",
        description=(
            "Fetch a Simon Willison blog post, follow its references one "
            "level deep, and print a Markdown analysis."
        ),
    )
    p.add_argument("url", help="URL of the blog post to read")
    p.add_argument(
        "--max-refs",
        type=int,
        default=None,
        help="Maximum number of references to analyse (default: 8 / SIMONW_MAX_REFERENCES)",
    )
    p.add_argument(
        "--lang",
        choices=["zh", "en"],
        default=None,
        help="Output language (default: zh / SIMONW_OUTPUT_LANG)",
    )
    p.add_argument("--model", default=None, help="Override the OpenAI model")
    p.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit a structured JSON payload instead of Markdown",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose logging to stderr"
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
        result = run(
            args.url,
            max_references=args.max_refs,
            lang=args.lang,
            model=args.model,
            progress=progress,
        )
    except FetchError as exc:
        print(f"ERROR: failed to fetch the post: {exc}", file=sys.stderr)
        return 2
    except AnalyzerError as exc:
        print(f"ERROR: analysis failed: {exc}", file=sys.stderr)
        return 3

    if args.as_json:
        payload = {
            "post": {
                "url": result.post.url,
                "title": result.post.title,
                "text": result.post.text,
            },
            "body_analysis": result.body_analysis,
            "references": [
                {
                    "url": r.reference.url,
                    "anchor_text": r.reference.anchor_text,
                    "context": r.reference.context,
                    "analysis": r.analysis,
                    "error": r.error,
                }
                for r in result.references
            ],
            "fetch_warnings": result.fetch_warnings,
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(result.to_markdown())

    if result.fetch_warnings:
        # Non-fatal but reported on stderr so callers can notice in scripts.
        print(
            f"\nNote: {len(result.fetch_warnings)} reference(s) could not be analysed.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
