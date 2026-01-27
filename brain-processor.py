"""
Brain processor for Second Brain.

Background service that handles:
- Daily digest generation and sending
- Inbox review notifications
- Processing orphaned corrections
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta

from telegram import Bot

from config import (
    TELEGRAM_TOKEN,
    CATEGORIES,
    DIGEST_HOUR,
    REVIEW_HOUR,
    ANTHROPIC_API_KEY,
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
import reminder_storage
import journal_storage

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def escape_md_v2(text: str) -> str:
    """Escape text for Telegram MarkdownV2."""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)


def get_entries_since(category: str, since: datetime) -> list:
    """Get entries added since a given time."""
    entries = get_all_entries(category)
    return [
        e for e in entries
        if datetime.fromisoformat(e.get("timestamp", "2000-01-01")) > since
    ]


def collect_digest_data() -> dict:
    """Collect digest data without formatting."""
    last_digest = get_state("last_digest_time")
    if last_digest:
        since = datetime.fromisoformat(last_digest)
    else:
        since = datetime.now() - timedelta(days=1)

    data = {
        "since": since.isoformat(),
        "categories": {},
        "inbox_count": 0,
        "contexts": {}
    }

    # Load contexts for AI understanding
    try:
        from context_manager import load_context
        for category in CATEGORIES:
            ctx = load_context(category)
            if ctx and len(ctx.strip()) > 20:
                data["contexts"][category] = ctx
    except Exception as e:
        logger.warning(f"Failed to load contexts: {e}")

    # Collect entries per category
    for category in CATEGORIES + ["inbox"]:
        entries = get_entries_since(category, since)
        if entries:
            data["categories"][category] = [
                {
                    "message": e.get("raw_message", ""),
                    "confidence": e.get("confidence", 0),
                    "timestamp": e.get("timestamp", ""),
                    "corrected_from": e.get("corrected_from")
                }
                for e in entries
            ]

    # Inbox count
    inbox = get_all_entries("inbox")
    data["inbox_count"] = len(inbox)

    return data


def generate_simple_digest(data: dict) -> str:
    """Fallback simple digest format."""
    lines = ["<b>Daily Digest</b>", ""]

    total_new = 0
    for category, entries in data["categories"].items():
        count = len(entries)
        total_new += count

        if count > 0:
            lines.append(f"<b>{category.title()}</b>: {count} new")
            for entry in entries[:3]:
                msg = entry['message'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                lines.append(f"  {msg}")
            lines.append("")

    if total_new == 0:
        lines.append("No new entries since last digest.")

    if data["inbox_count"] > 0:
        lines.append(f"<b>Inbox</b>: {data['inbox_count']} items need review")

    return "\n".join(lines)


def generate_ai_digest(data: dict) -> str:
    """Generate AI-enhanced digest from structured data."""
    if not any(data["categories"].values()):
        return "<b>Daily Digest</b>\n\nNo new entries since last digest."

    # Build prompt with context
    prompt_parts = ["You are a productivity assistant analyzing daily digest data."]

    # Add context sections
    if data["contexts"]:
        prompt_parts.append("\n[BACKGROUND CONTEXT]")
        for category, context in data["contexts"].items():
            prompt_parts.append(f"\n## {category.title()}")
            prompt_parts.append(context)

    prompt_parts.append("\n[NEW ENTRIES TO DIGEST]")

    # Add entries by category
    for category, entries in data["categories"].items():
        if entries:
            prompt_parts.append(f"\n{category.title()} ({len(entries)} new):")
            for entry in entries:
                prompt_parts.append(f"  - {entry['message']}")
                if entry['confidence'] < 0.7:
                    prompt_parts.append(f"    (low confidence: {int(entry['confidence']*100)}%)")

    if data["inbox_count"] > 0:
        prompt_parts.append(f"\nInbox: {data['inbox_count']} items need review")

    prompt = "\n".join(prompt_parts)

    system_prompt = """Create a prioritized daily digest summary for Telegram.

RULES:
1. Prioritize by urgency/importance (deadlines, appointments, follow-ups first)
2. Group related items logically
3. Include full context from messages - don't truncate
4. Make intelligent assumptions about priorities (meetings > ideas, deadlines > notes)
5. Use sections: "High Priority", "Today", "This Week", "Notes"
6. Call out inbox items that need classification
7. Suggest next actions when relevant
8. Keep tone helpful and actionable

FORMATTING (Telegram HTML):
- Start with "Daily Digest" as first line
- Use <b>bold</b> for section headers
- Use plain text for all message content (no additional formatting)
- Keep it clean and scannable
- Do NOT use unsupported HTML tags - only <b>, <i>, <code> are safe
- Each section separated by blank line
- Special chars (&, <, >) in user content will be escaped automatically"""

    try:
        from anthropic import Anthropic

        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set")

        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        )

        ai_text = response.content[0].text.strip()

        # AI should already return HTML formatted text
        # Just return it as-is
        return ai_text

    except Exception as e:
        logger.error(f"AI digest failed: {e}")
        # Fallback to simple format
        return generate_simple_digest(data)


async def send_digest(bot: Bot, chat_id: int) -> None:
    """Send digest to a specific chat."""
    # Collect structured data
    data = collect_digest_data()

    # Generate AI-enhanced digest
    digest = generate_ai_digest(data)

    # Send with HTML formatting
    await bot.send_message(
        chat_id=chat_id,
        text=digest,
        parse_mode="HTML"
    )
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


def _get_recent_diary_context(days: int = 3) -> str:
    """Get diary content from the last N days."""
    from datetime import date as date_type
    entries = []
    for i in range(days):
        target = date_type.today() - timedelta(days=i)
        journal = journal_storage.read_journal(target)
        if journal.get("exists") and journal.get("content"):
            entries.append(f"[{target.isoformat()}]\n{journal['content']}")
    return "\n\n".join(entries)


def _get_related_knowledge(reminder: dict) -> list:
    """Search knowledge base for entries related to a reminder."""
    content = reminder.get("content", "")
    if not content:
        return []

    try:
        from agent_tools import search_entries
        result = search_entries(content, limit=3)
        if result.get("success"):
            return result.get("entries", [])
    except Exception as e:
        logger.warning(f"Knowledge search failed: {e}")

    return []


async def process_reminders(bot: Bot, chat_id: int) -> int:
    """
    Process triggered reminders and send notifications.

    Returns:
        Number of reminders triggered
    """
    triggered = reminder_storage.process_triggered_reminders()

    # Get diary context once for all reminders
    recent_diary = ""
    if triggered:
        try:
            recent_diary = _get_recent_diary_context(days=3)
        except Exception as e:
            logger.warning(f"Failed to get diary context: {e}")

    for reminder in triggered:
        content = reminder.get("content", "")
        reminder_id = reminder.get("id", "")

        # Enrich reminder with diary/knowledge context
        enriched_content = content
        try:
            from diary_reminder_bridge import enrich_reminder_delivery
            related = _get_related_knowledge(reminder)
            enriched_content = enrich_reminder_delivery(reminder, recent_diary, related)
        except Exception as e:
            logger.warning(f"Reminder enrichment failed: {e}")

        # Build notification message - use HTML
        enriched_html = enriched_content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        message = f"🔔 <b>Recordatorio</b>\n\n{enriched_html}"

        # Send notification
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML"
            )
            logger.info(f"Sent enriched reminder: {content[:50]}")
        except Exception as e:
            logger.error(f"Failed to send reminder {reminder_id}: {e}")

    return len(triggered)


async def run_reminders(chat_id: int) -> None:
    """Process reminders once and exit."""
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not set")

    bot = Bot(token=TELEGRAM_TOKEN)
    init_storage()

    triggered = await process_reminders(bot, chat_id)
    if triggered:
        logger.info(f"Triggered {triggered} reminders")
    else:
        logger.info("No reminders to trigger")


async def run_daily_review(chat_id: int) -> None:
    """Run daily review: generate follow-up suggestions and send reflection message."""
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not set")

    bot = Bot(token=TELEGRAM_TOKEN)
    init_storage()

    try:
        from diary_reminder_bridge import generate_follow_up_suggestions

        recent_diary = _get_recent_diary_context(days=3)
        pending = reminder_storage.list_reminders(status="pending")

        suggestions = generate_follow_up_suggestions(recent_diary, pending)

        if not suggestions:
            logger.info("No follow-up suggestions generated")
            return

        # Build message
        lines = ["🌙 <b>Reflexión del día</b>\n"]
        for s in suggestions[:3]:
            suggestion_text = s.get("suggestion", "")
            suggestion_html = suggestion_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            s_type = s.get("type", "")
            type_icon = {
                "follow_up": "📋",
                "pattern": "🔄",
                "nudge": "👋",
                "action": "⚡"
            }.get(s_type, "💡")
            lines.append(f"{type_icon} {suggestion_html}")

        message = "\n\n".join(lines)

        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="HTML"
        )
        logger.info(f"Sent daily review to {chat_id}")

    except Exception as e:
        logger.error(f"Daily review failed: {e}")


def main():
    """Entry point."""
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Brain processor for Second Brain")
    parser.add_argument("chat_id", type=int, help="Telegram chat ID for notifications")
    parser.add_argument("--digest", action="store_true", help="Send daily digest")
    parser.add_argument("--corrections", action="store_true", help="Process corrections queue")
    parser.add_argument("--reminders", action="store_true", help="Process triggered reminders")
    parser.add_argument("--review", action="store_true", help="Run daily review/reflection")

    args = parser.parse_args()

    # Default to all if none specified (excluding review, which is opt-in)
    if not args.digest and not args.corrections and not args.reminders and not args.review:
        args.digest = True
        args.corrections = True
        args.reminders = True

    try:
        if args.corrections:
            asyncio.run(run_corrections())

        if args.reminders:
            asyncio.run(run_reminders(args.chat_id))

        if args.digest:
            asyncio.run(run_digest(args.chat_id))

        if args.review:
            asyncio.run(run_daily_review(args.chat_id))
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
