---
name: simonw-reader
description: Read and analyse a Simon Willison blog post. Fetches the article, follows its referenced links one level deep, and produces a structured Markdown analysis explaining what each reference is and how it supports the original post. Trigger when the user provides a URL on simonwillison.net (or asks to "read" / "analyse" / "summarise" a Simon Willison post), or when they paste any blog post URL and ask for a reference-aware reading.
---

# Simon Willison Blog Reader

This skill drives a small Python tool that:

1. Fetches the blog post at a URL.
2. Extracts the main article text and every outbound link in the body.
3. Fetches each referenced page (one level deep) and asks an LLM how that
   reference supports the original article (evidence, definition, example,
   counterpoint, further reading, ...).
4. Returns a single Markdown report.

## When to use

- The user gives you a URL from `simonwillison.net` and asks for a summary
  or reading help.
- The user pastes any blog post URL and explicitly asks for a
  "reference-aware" / "with citations" reading.
- The user says things like "帮我读一下这篇 Simon 的博客" / "analyse this post
  and its citations".

Do NOT use this skill if the user only wants a one-line summary, or if
the URL is clearly not an article (homepage, tag index, login page).

## Prerequisites

The host machine needs:

- Python 3.10+
- The package installed (`pip install -e .` from the repo root) **or** the
  source available so `python -m simonw_reader` resolves.
- `OPENAI_API_KEY` set in the environment. Optionally
  `SIMONW_OPENAI_MODEL` (default `gpt-4o-mini`),
  `SIMONW_OUTPUT_LANG` (`zh` or `en`, default `zh`),
  `SIMONW_MAX_REFERENCES` (default `8`).

If the key is missing the tool will exit with a clear error — surface that
error to the user and stop.

## How to invoke

Run the wrapper script and stream its stdout back to the user:

```bash
bash skills/simonw-reader/scripts/read.sh <url> [--lang zh|en] [--max-refs N] [--json]
```

Or call the Python module directly:

```bash
python -m simonw_reader <url> [--lang zh|en] [--max-refs N] [--json]
```

- Default output is Markdown on stdout — paste it back to the user verbatim
  (don't paraphrase; the LLM analysis is already done).
- Pass `--json` if you need to post-process structured fields
  (`post`, `body_analysis`, `references[]`, `fetch_warnings`).
- Exit code `0` = success; `2` = fetch failure; `3` = LLM/analysis failure.
  On non-zero exit, report the exact stderr message to the user — do not
  retry silently.

## Output shape (Markdown mode)

```
# <post title>
Source: <url>

## Overview
...

## Key points
- ...

## Fetch warnings   (only if some references could not be fetched)
- <url>: <reason>

## References
### [1] <anchor text>
<url>
### Summary
...
### Role in the original post
...
```

## Failure handling

- If the post URL itself fails to fetch, the tool exits with code 2 and
  prints the reason on stderr. Surface that error to the user.
- If individual references fail (404, paywall, timeouts), they appear in
  `## Fetch warnings` and as `⚠ Could not analyse this reference: ...` in
  the per-reference section. The rest of the report is still valid.
- Never invent content for a failed reference.
