"""
Brain processor for Second Brain.

Background service that handles:
- Daily digest generation and sending
- Inbox review notifications
- Processing orphaned corrections
"""
import asyncio
import logging
from datetime import datetime, timedelta

from telegram import Bot

from config import (
    TELEGRAM_TOKEN,
    CATEGORIES,
    DIGEST_HOUR,
)
from storage import (
    init_storage,
    get_all_entries,
    get_recent_entries,
    get_pending_corrections,
    mark_correction_processed,
    move_entry,
    log_audit,
    get_state,
    set_state,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_entries_since(category: str, since: datetime) -> list:
    """Get entries added since a given time."""
    entries = get_all_entries(category)
    return [
        e for e in entries
        if datetime.fromisoformat(e.get("timestamp", "2000-01-01")) > since
    ]


def generate_digest() -> str:
    """Generate a digest of recent activity."""
    last_digest = get_state("last_digest_time")
    if last_digest:
        since = datetime.fromisoformat(last_digest)
    else:
        since = datetime.now() - timedelta(days=1)

    lines = ["Daily Digest", "=" * 20, ""]

    total_new = 0
    for category in CATEGORIES + ["inbox"]:
        new_entries = get_entries_since(category, since)
        count = len(new_entries)
        total_new += count

        if count > 0:
            lines.append(f"{category.title()}: {count} new")
            for entry in new_entries[:3]:
                message = entry.get("raw_message", "")
                lines.append(f"  - {message}")
            lines.append("")  # Blank line after each section

    if total_new == 0:
        lines.append("No new entries since last digest.")

    # Check inbox for items needing review
    inbox = get_all_entries("inbox")
    if inbox:
        lines.append("")
        lines.append(f"Inbox: {len(inbox)} items need review")

    return "\n".join(lines)


async def send_digest(bot: Bot, chat_id: int) -> None:
    """Send digest to a specific chat."""
    digest = generate_digest()
    await bot.send_message(chat_id=chat_id, text=digest)
    set_state("last_digest_time", datetime.now().isoformat())
    logger.info(f"Sent digest to {chat_id}")


async def send_inbox_reminder(bot: Bot, chat_id: int) -> None:
    """Send reminder about unreviewed inbox items."""
    inbox = get_all_entries("inbox")
    if not inbox:
        return

    lines = [
        f"You have {len(inbox)} items in inbox:",
        "",
    ]

    for entry in inbox[:5]:
        message = entry.get("raw_message", "")
        conf = int(entry.get("confidence", 0) * 100)
        lines.append(f"- {message} ({conf}%)")

    if len(inbox) > 5:
        lines.append(f"  ... and {len(inbox) - 5} more")

    lines.append("")
    lines.append("Reply to original messages with category to classify.")

    await bot.send_message(chat_id=chat_id, text="\n".join(lines))


def process_pending_corrections() -> int:
    """Process any pending corrections in the queue."""
    pending = get_pending_corrections()
    processed = 0

    for correction in pending:
        entry_id = correction.get("entry_id")
        from_cat = correction.get("from_category")
        to_cat = correction.get("to_category")

        if entry_id == "unknown" or from_cat == "unknown":
            # Can't process without knowing the entry
            # Mark as processed to avoid infinite loop
            mark_correction_processed(correction["id"])
            continue

        result = move_entry(entry_id, from_cat, to_cat)
        if result:
            log_audit(
                action="corrected",
                item_id=entry_id,
                category=to_cat,
                details={"from_category": from_cat, "source": "queue"},
            )
            processed += 1

        mark_correction_processed(correction["id"])

    return processed


async def run_digest(chat_id: int) -> None:
    """Run digest once and exit."""
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not set")

    bot = Bot(token=TELEGRAM_TOKEN)
    init_storage()

    # Check if we've already sent today
    last_digest = get_state("last_digest_time")
    if last_digest:
        last_time = datetime.fromisoformat(last_digest)
        now = datetime.now()
        if now - last_time < timedelta(hours=20):
            logger.info("Digest already sent in last 20 hours, skipping")
            return

    await send_digest(bot, chat_id)
    logger.info(f"Digest sent to {chat_id}")


async def run_corrections() -> None:
    """Process corrections once and exit."""
    init_storage()
    processed = process_pending_corrections()
    if processed:
        logger.info(f"Processed {processed} corrections")
    else:
        logger.info("No corrections to process")


def main():
    """Entry point."""
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Brain processor for Second Brain")
    parser.add_argument("chat_id", type=int, help="Telegram chat ID for digests")
    parser.add_argument("--digest", action="store_true", help="Send daily digest")
    parser.add_argument("--corrections", action="store_true", help="Process corrections queue")

    args = parser.parse_args()

    # Default to both if neither specified
    if not args.digest and not args.corrections:
        args.digest = True
        args.corrections = True

    try:
        if args.corrections:
            asyncio.run(run_corrections())

        if args.digest:
            asyncio.run(run_digest(args.chat_id))
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
