"""Telegram bot front-end (long polling).

Send the bot a URL to a Simon Willison blog post and it will reply with a
Markdown analysis of the article and its referenced links.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Iterable

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .analyzer import AnalyzerError
from .fetcher import FetchError
from .pipeline import run as run_pipeline

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://\S+")

WELCOME = (
    "Hi! Send me a URL to a Simon Willison blog post (or any post that links "
    "to references) and I'll fetch it, follow its references one level deep, "
    "and reply with an analysis.\n\n"
    "Commands:\n"
    "/start - show this message\n"
    "/help - same"
)


def _allowed_user_ids() -> set[int]:
    raw = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def _is_allowed(user_id: int, allowed: set[int]) -> bool:
    return not allowed or user_id in allowed


def _chunks(text: str, max_len: int = 3500) -> Iterable[str]:
    """Telegram messages cap at 4096 chars; split on paragraph boundaries."""
    if len(text) <= max_len:
        yield text
        return
    buf: list[str] = []
    size = 0
    for para in text.split("\n\n"):
        piece = para + "\n\n"
        if size + len(piece) > max_len and buf:
            yield "".join(buf).rstrip()
            buf, size = [], 0
        if len(piece) > max_len:
            # Paragraph itself too long; hard-split.
            for i in range(0, len(piece), max_len):
                yield piece[i : i + max_len]
            buf, size = [], 0
            continue
        buf.append(piece)
        size += len(piece)
    if buf:
        yield "".join(buf).rstrip()


# ---------------------------------------------------------------------------
# Handlers


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if msg is None or msg.text is None:
        return

    user = update.effective_user
    allowed = context.bot_data.get("allowed_user_ids", set())
    if user is None or not _is_allowed(user.id, allowed):
        await msg.reply_text("Sorry, this bot is private.")
        return

    match = URL_RE.search(msg.text)
    if not match:
        await msg.reply_text("Please send a URL (e.g. https://simonwillison.net/...).")
        return
    url = match.group(0).rstrip(").,>")

    status = await msg.reply_text(f"Fetching {url} ...")
    chat_id = msg.chat_id
    bot = context.bot

    progress_queue: asyncio.Queue[str] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def progress(s: str) -> None:
        # Called from worker thread; hand off to the asyncio loop.
        asyncio.run_coroutine_threadsafe(progress_queue.put(s), loop)

    async def drain_progress() -> None:
        while True:
            s = await progress_queue.get()
            if s == "__done__":
                return
            try:
                await bot.send_chat_action(chat_id, ChatAction.TYPING)
                await status.edit_text(s[:4000])
            except Exception:  # noqa: BLE001 - status updates are best-effort
                logger.debug("status update failed", exc_info=True)

    drainer = asyncio.create_task(drain_progress())
    try:
        result = await asyncio.to_thread(run_pipeline, url, progress=progress)
    except FetchError as exc:
        await progress_queue.put("__done__")
        await drainer
        await status.edit_text(f"❌ Failed to fetch the post: {exc}")
        return
    except AnalyzerError as exc:
        await progress_queue.put("__done__")
        await drainer
        await status.edit_text(f"❌ Analysis failed: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        await progress_queue.put("__done__")
        await drainer
        logger.exception("pipeline crashed")
        await status.edit_text(f"❌ Unexpected error: {exc}")
        return
    finally:
        if not drainer.done():
            await progress_queue.put("__done__")
            await drainer

    md = result.to_markdown()
    try:
        await status.edit_text("✅ Done. Sending the report...")
    except Exception:  # noqa: BLE001
        pass
    for chunk in _chunks(md):
        try:
            await bot.send_message(chat_id, chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            # Markdown can fail on weird content; fall back to plain text.
            await bot.send_message(chat_id, chunk)


# ---------------------------------------------------------------------------
# Entry point


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set.")
        return 1

    application = Application.builder().token(token).build()
    application.bot_data["allowed_user_ids"] = _allowed_user_ids()

    application.add_handler(CommandHandler(["start", "help"], cmd_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    logger.info("simonw-read-bot starting (long polling)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
