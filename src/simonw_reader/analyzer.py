"""LLM-powered analysis of a blog post and its references (OpenAI)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from openai import OpenAI, OpenAIError

from .fetcher import BlogPost, Reference

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("SIMONW_OPENAI_MODEL", "gpt-4o-mini")


class AnalyzerError(RuntimeError):
    """Raised when the LLM call fails."""


@dataclass
class RefAnalysis:
    reference: Reference
    role: str  # How this reference supports / extends the original article.
    summary: str  # One-paragraph summary of the referenced page.
    fetch_error: str | None = None


@dataclass
class PostAnalysis:
    overview: str  # High-level summary of the article.
    key_points: list[str]
    references: list[RefAnalysis]


# ---------------------------------------------------------------------------
# Prompts


_LANG_INSTRUCTIONS = {
    "zh": "请使用简体中文回答。",
    "en": "Respond in English.",
}


def _lang_instruction(lang: str) -> str:
    return _LANG_INSTRUCTIONS.get(lang, _LANG_INSTRUCTIONS["zh"])


def _post_prompt(post: BlogPost, lang: str) -> list[dict]:
    system = (
        "You are a careful technical reading assistant. "
        "You summarise blog posts faithfully, never inventing facts that "
        "are not in the source. " + _lang_instruction(lang)
    )
    user = (
        f"Below is a blog post from {post.url}.\n\n"
        f"Title: {post.title}\n\n"
        f"Body:\n\"\"\"\n{post.text}\n\"\"\"\n\n"
        "Produce:\n"
        "1) A 3-5 sentence overview of what this post is about.\n"
        "2) A bullet list (3-7 items) of the key points or takeaways.\n\n"
        "Format your answer in Markdown with two sections: "
        "`## Overview` and `## Key points`."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _ref_prompt(post: BlogPost, ref: Reference, ref_text: str, lang: str) -> list[dict]:
    system = (
        "You are a careful reading assistant analysing how a blog post uses "
        "an external reference. Be concrete, cite specifics, and never invent "
        "facts. " + _lang_instruction(lang)
    )
    user = (
        f"ORIGINAL POST: {post.title} ({post.url})\n"
        "Excerpt of the original post where this reference appears:\n"
        f"\"\"\"\n{ref.context}\n\"\"\"\n\n"
        f"Anchor text used in the original: {ref.anchor_text!r}\n"
        f"Reference URL: {ref.url}\n\n"
        "Content fetched from the reference URL:\n"
        f"\"\"\"\n{ref_text}\n\"\"\"\n\n"
        "Answer two questions, each in 2-4 sentences, using these exact headers:\n"
        "### Summary\n"
        "What is the referenced page about?\n"
        "### Role in the original post\n"
        "How does this reference support or extend the original article? "
        "Be specific about what the original would lose without it "
        "(evidence, definition, example, counter-point, further reading, etc.)."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# OpenAI plumbing


def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AnalyzerError(
            "OPENAI_API_KEY is not set; cannot call the analysis model."
        )
    base_url = os.getenv("OPENAI_BASE_URL")
    return OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)


def _chat(messages: list[dict], *, model: str | None = None) -> str:
    client = _client()
    model = model or DEFAULT_MODEL
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
        )
    except OpenAIError as exc:
        raise AnalyzerError(f"OpenAI request failed: {exc}") from exc
    if not resp.choices:
        raise AnalyzerError("OpenAI returned no choices")
    return (resp.choices[0].message.content or "").strip()


def analyze_post_body(post: BlogPost, *, lang: str = "zh", model: str | None = None) -> str:
    """Return Markdown with `## Overview` and `## Key points` sections."""
    return _chat(_post_prompt(post, lang), model=model)


def analyze_reference(
    post: BlogPost,
    ref: Reference,
    ref_text: str,
    *,
    lang: str = "zh",
    model: str | None = None,
) -> str:
    """Return Markdown with `### Summary` and `### Role in the original post`."""
    return _chat(_ref_prompt(post, ref, ref_text, lang), model=model)


# Convenience: a single, opinionated entry point used by the pipeline.
def analyze(messages: list[dict], *, model: str | None = None) -> str:
    return _chat(messages, model=model)
