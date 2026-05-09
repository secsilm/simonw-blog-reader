---
name: simonw-reader
description: Read and analyse a Simon Willison blog post (or any blog post with citations). Fetches the article and the readable text of every link it cites, one level deep, then YOU produce a structured Markdown analysis explaining how each reference supports the original. Trigger when the user gives a URL on simonwillison.net, or any blog URL and asks for a "reference-aware" / "with citations" reading.
---

# Simon Willison Blog Reader

This skill is a **fetch-only data source**. The Python script does *no*
LLM work — it just downloads the post, extracts every cited link, fetches
each linked page's readable text, and emits JSON. **You** (the agent
calling the skill) do the actual analysis using that JSON.

That means: no `OPENAI_API_KEY` needed, no extra LLM round-trips, no
double-summarisation.

## When to use

- The user gives you a URL from `simonwillison.net` and asks for a summary
  or reading help.
- The user pastes a blog URL and asks for a reference-aware reading
  ("帮我读一下这篇并分析它引用的链接", "summarise this and its citations").

Do **not** use it for one-line summaries, homepages, tag indexes, or
anything that's clearly not an article.

## Prerequisites

- Python 3.10+
- The package importable: either `pip install -e .` from the repo root,
  or run from the source tree (the wrapper script handles `PYTHONPATH`).
- No API keys required.

## How to invoke

```bash
bash skills/simonw-reader/scripts/read.sh <url> [--max-refs N] [--ref-chars N]
```

Or directly:

```bash
simonw-fetch <url> [--max-refs N] [--ref-chars N]
# or, from a source checkout without install:
PYTHONPATH=src python -m simonw_reader.fetch_cli <url> ...
```

Defaults: up to 8 references, 6000 chars of extracted text per reference.

## Output (JSON on stdout)

```json
{
  "post": {
    "url": "...",
    "title": "...",
    "text": "<plain-text article body, paragraphs separated by blank lines>"
  },
  "references": [
    {
      "url": "...",
      "anchor_text": "<the link text used in the original>",
      "context": "<the paragraph the link sits in>",
      "fetched_text": "<plain-text body of the referenced page, truncated>",
      "error": null
    },
    {
      "url": "...",
      "anchor_text": "...",
      "context": "...",
      "fetched_text": null,
      "error": "Failed to fetch ...: 404 Not Found"
    }
  ],
  "fetch_warnings": ["<url>: <reason>", "..."]
}
```

Exit code `0` on success, `2` on post-fetch failure (stdout will be a
single JSON object: `{"error":"fetch_failed","url":...,"message":...}`).

## What you should do with it

1. Parse the JSON. If the top-level `error` field is set, **stop** and
   tell the user the fetch failed — do not invent content.
2. From `post.text`, write a Markdown report with these sections:
   - `# <post title>` and `Source: <post.url>`
   - `## Overview` — 3-5 sentences of what the post is about.
   - `## Key points` — 3-7 bullets.
3. For each item in `references`:
   - If `error` is set, list it under `## Fetch warnings` and emit a
     `### [N] <anchor>` entry that says "⚠ Could not fetch: <error>".
     **Never** invent what the page would have said.
   - Otherwise, read `fetched_text` and write:
     - `### [N] <anchor_text>` plus the URL on its own line
     - `### Summary` — 2-4 sentences on what the referenced page is about.
     - `### Role in the original post` — 2-4 sentences explaining how
       this reference supports the original. Be specific: is it evidence,
       a definition, an example, a counter-point, further reading? Use
       the `context` field to ground your answer in *where* the link
       appears in the original.
4. Match the user's language (default: respond in the language they wrote
   in). Don't translate the post title or URLs.

## Failure handling

- Top-level fetch failure → exit code 2, JSON `{"error":"fetch_failed",...}`.
  Surface the message to the user. Do not retry blindly.
- Per-reference failure → entry has `"error": "..."` and `"fetched_text":
  null`. Include it under `## Fetch warnings` and the per-reference
  section, but keep the rest of the report.
- Empty `references` array → just produce the body analysis; mention that
  the post doesn't cite external sources.
