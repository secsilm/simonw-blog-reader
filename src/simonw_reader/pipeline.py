"""End-to-end pipeline: fetch a Simon Willison post, follow its references
one level deep, and produce a Markdown analysis report.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from . import analyzer, fetcher
from .fetcher import BlogPost, FetchError, Reference

logger = logging.getLogger(__name__)


@dataclass
class ReferenceResult:
    reference: Reference
    analysis: str | None = None  # Markdown
    error: str | None = None


@dataclass
class AnalysisResult:
    post: BlogPost
    body_analysis: str  # Markdown
    references: list[ReferenceResult] = field(default_factory=list)
    fetch_warnings: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append(f"# {self.post.title}")
        lines.append("")
        lines.append(f"Source: {self.post.url}")
        lines.append("")
        lines.append(self.body_analysis.strip())
        lines.append("")
        if self.fetch_warnings:
            lines.append("## Fetch warnings")
            for w in self.fetch_warnings:
                lines.append(f"- {w}")
            lines.append("")
        if self.references:
            lines.append("## References")
            lines.append("")
            for i, r in enumerate(self.references, 1):
                anchor = r.reference.anchor_text or "(link)"
                lines.append(f"### [{i}] {anchor}")
                lines.append(f"<{r.reference.url}>")
                lines.append("")
                if r.error:
                    lines.append(f"> ⚠ Could not analyse this reference: {r.error}")
                else:
                    lines.append((r.analysis or "").strip())
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def _default_max_refs() -> int:
    try:
        return max(0, int(os.getenv("SIMONW_MAX_REFERENCES", "8")))
    except ValueError:
        return 8


def _default_lang() -> str:
    return os.getenv("SIMONW_OUTPUT_LANG", "zh").lower()


def run(
    url: str,
    *,
    max_references: int | None = None,
    lang: str | None = None,
    model: str | None = None,
    progress=None,
) -> AnalysisResult:
    """Run the full pipeline.

    ``progress`` is an optional callable receiving short status strings,
    useful for the Telegram bot to report progress to the user.
    """

    def report(msg: str) -> None:
        logger.info(msg)
        if progress is not None:
            try:
                progress(msg)
            except Exception:  # noqa: BLE001 - progress callback must not break the run
                logger.exception("progress callback raised")

    max_refs = _default_max_refs() if max_references is None else max_references
    lang = (lang or _default_lang()).lower()

    report(f"Fetching {url} ...")
    post = fetcher.fetch_and_parse(url)  # FetchError propagates to caller.
    report(f"Got post '{post.title}' with {len(post.references)} link(s).")

    report("Analysing the article body...")
    body_md = analyzer.analyze_post_body(post, lang=lang, model=model)

    chosen = fetcher.select_top_references(post.references, max_refs) if max_refs else []
    ref_results: list[ReferenceResult] = []
    warnings: list[str] = []

    if chosen:
        report(f"Following {len(chosen)} reference(s) one level deep...")
        # Fetch references concurrently; analyse sequentially to keep token usage tidy.
        fetched: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=min(8, len(chosen))) as pool:
            futures = {pool.submit(fetcher.fetch_readable, r.url): r for r in chosen}
            for fut in as_completed(futures):
                ref = futures[fut]
                try:
                    fetched[ref.url] = fut.result()
                except FetchError as exc:
                    msg = f"{ref.url}: {exc}"
                    warnings.append(msg)
                    ref_results.append(ReferenceResult(reference=ref, error=str(exc)))
                    report(f"⚠ Failed to fetch reference: {msg}")
                except Exception as exc:  # noqa: BLE001
                    msg = f"{ref.url}: unexpected error: {exc}"
                    warnings.append(msg)
                    ref_results.append(ReferenceResult(reference=ref, error=str(exc)))
                    report(f"⚠ Failed to fetch reference: {msg}")

        # Now analyse each successfully-fetched reference, preserving original order.
        for ref in chosen:
            if ref.url not in fetched:
                continue  # Already recorded as an error above.
            report(f"Analysing reference: {ref.url}")
            try:
                md = analyzer.analyze_reference(
                    post, ref, fetched[ref.url], lang=lang, model=model
                )
            except analyzer.AnalyzerError as exc:
                ref_results.append(ReferenceResult(reference=ref, error=str(exc)))
                warnings.append(f"{ref.url}: analysis failed: {exc}")
                continue
            ref_results.append(ReferenceResult(reference=ref, analysis=md))

    return AnalysisResult(
        post=post,
        body_analysis=body_md,
        references=ref_results,
        fetch_warnings=warnings,
    )
