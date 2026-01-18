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
                preview = entry.get("raw_message", "")[:40]
                lines.append(f"  - {preview}...")

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
        preview = entry.get("raw_message", "")[:50]
        conf = int(entry.get("confidence", 0) * 100)
        lines.append(f"- {preview}... ({conf}%)")

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


async def check_digest_time(bot: Bot, chat_id: int) -> None:
    """Check if it's time to send a digest."""
    now = datetime.now()

    # Check if we should send a digest
    if now.hour == DIGEST_HOUR:
        last_digest = get_state("last_digest_time")
        if last_digest:
            last_time = datetime.fromisoformat(last_digest)
            # Only send if we haven't sent one in the last 20 hours
            if now - last_time < timedelta(hours=20):
                return

        await send_digest(bot, chat_id)


async def main_loop(chat_id: int):
    """Main processing loop."""
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not set")

    bot = Bot(token=TELEGRAM_TOKEN)
    init_storage()

    logger.info(f"Brain processor started. Digest chat_id={chat_id}")

    while True:
        try:
            # Process pending corrections
            processed = process_pending_corrections()
            if processed:
                logger.info(f"Processed {processed} corrections")

            # Check if digest time
            await check_digest_time(bot, chat_id)

        except Exception as e:
            logger.error(f"Loop error: {e}")

        # Sleep for 5 minutes
        await asyncio.sleep(300)


def main():
    """Entry point."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python brain-processor.py <chat_id>")
        print("  chat_id: Your Telegram chat ID for receiving digests")
        sys.exit(1)

    chat_id = int(sys.argv[1])
    asyncio.run(main_loop(chat_id))


if __name__ == "__main__":
    main()
