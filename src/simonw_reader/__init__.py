"""Simon Willison blog reading assistant."""

from .fetcher import BlogPost, FetchError, Reference, fetch_and_parse, fetch_readable
from .pipeline import (
    AnalysisResult,
    FetchedReference,
    FetchResult,
    fetch_with_references,
    run,
)

__all__ = [
    "BlogPost",
    "Reference",
    "FetchError",
    "AnalysisResult",
    "FetchResult",
    "FetchedReference",
    "fetch_and_parse",
    "fetch_readable",
    "fetch_with_references",
    "run",
]
