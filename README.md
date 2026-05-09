# simonw-blog-reader

Reading assistant for [Simon Willison's blog](https://simonwillison.net/).

Give it a URL → it fetches the post, extracts every outbound link in the
body, follows each one *one level deep*, and asks an LLM to explain how
each reference supports the original article. The result is a single
Markdown report.

It ships in three forms that share the same fetch/parse core:

1. **`simonw-read <url>`** — CLI that does fetch + LLM analysis end-to-end (needs `OPENAI_API_KEY`).
2. **`simonw-fetch <url>`** — fetch-only CLI emitting JSON (no LLM, no API key). Used by the skill.
3. **Telegram bot** (long polling) — `simonw-read-bot` (needs `OPENAI_API_KEY` + `TELEGRAM_BOT_TOKEN`).
4. **Claude Code skill** — `skills/simonw-reader/SKILL.md`. Calls `simonw-fetch` and lets the host model (Claude) write the analysis itself, so it requires **no OpenAI key**.

## Install

```bash
pip install -e .
cp .env.example .env   # then fill in OPENAI_API_KEY (and optional bot token)
```

Python 3.10+ is required.

## Configuration

| Variable                    | Default        | Purpose                                              |
| --------------------------- | -------------- | ---------------------------------------------------- |
| `OPENAI_API_KEY`            | *(required)*   | OpenAI credential                                    |
| `OPENAI_BASE_URL`           | OpenAI default | Optional custom base URL                             |
| `SIMONW_OPENAI_MODEL`       | `gpt-4o-mini`  | Model used for both body and reference analysis      |
| `SIMONW_OUTPUT_LANG`        | `zh`           | `zh` or `en`                                         |
| `SIMONW_MAX_REFERENCES`     | `8`            | Maximum references analysed per post                 |
| `TELEGRAM_BOT_TOKEN`        | —              | Required only for the Telegram bot                   |
| `TELEGRAM_ALLOWED_USER_IDS` | —              | Comma-separated allowlist; empty = open to everyone  |

## CLIs

### `simonw-read` — full analysis (uses OpenAI)

```bash
simonw-read https://simonwillison.net/2024/Aug/13/quoting-paul-graham/
simonw-read <url> --lang en --max-refs 5
simonw-read <url> --json | jq .
```

Exit codes: `0` success, `2` fetch failure, `3` analysis (LLM) failure.

Stdout is a Markdown report; stderr contains progress (with `-v`) and any
warnings about references that could not be fetched. Failed references are
also listed in a `## Fetch warnings` section of the report itself — the
tool never invents content for a page it could not load.

### `simonw-fetch` — fetch only (no LLM)

```bash
simonw-fetch <url> --max-refs 8 --ref-chars 6000 | jq .
```

Emits JSON: `{post:{url,title,text}, references:[{url, anchor_text,
context, fetched_text, error}, ...], fetch_warnings:[...]}`. No API key
required. Used by the Claude Code skill, but also handy as a building
block for any agent or pipeline.

Exit codes: `0` success, `2` fetch failure (a JSON error payload is still
written to stdout: `{"error":"fetch_failed","url":...,"message":...}`).

## Telegram bot

```bash
simonw-read-bot
```

Send a URL in DM. The bot edits a status message while it works, then
posts the Markdown report (split into chunks if needed). The bot uses long
polling, so no public HTTPS endpoint is required.

Set `TELEGRAM_ALLOWED_USER_IDS` to lock the bot to specific accounts.

## Claude Code skill

The skill (`skills/simonw-reader/SKILL.md` + `scripts/read.sh`) is
**fetch-only**. Claude Code invokes `simonw-fetch` to get JSON for the
post + each cited page, then writes the analysis itself. No OpenAI key,
no second LLM. Copy or symlink `skills/simonw-reader/` into your skills
directory.

## How references are picked

The body of the post is parsed with BeautifulSoup; each `<a href>` inside
the article container is collected together with its anchor text and the
text of its enclosing paragraph (used as "context" for the LLM). Anchors
that are weak ("here", "this", a bare domain) are deprioritised, fragments
and binary files (`.pdf`, images, archives) are skipped. The top
`SIMONW_MAX_REFERENCES` survivors are fetched in parallel and analysed one
by one.
