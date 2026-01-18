"""
Telegram bot listener for Second Brain.

Handles:
- Incoming text messages -> classify -> store -> confirm
- Reply-based corrections (reply to bot message with category name)
- Inbox review (reply with category to confirm/reclassify)
"""
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

from config import TELEGRAM_TOKEN, CATEGORIES, CONFIDENCE_THRESHOLD
from classifier import classify_message, should_go_to_inbox
from storage import (
    init_storage,
    create_entry,
    get_entry_by_message_id,
    move_entry,
    log_audit,
    add_correction,
)

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def format_confirmation(entry: dict, result: dict) -> str:
    """Format confirmation message for user."""
    category = entry["category"]
    confidence = entry["confidence"]
    confidence_pct = int(confidence * 100)

    if category == "inbox":
        return (
            f"Saved to inbox (confidence {confidence_pct}%)\n"
            f"Suggested: {result.get('reasoning', 'unclear')}\n\n"
            f"Reply with a category to classify:\n"
            f"{', '.join(CATEGORIES)}"
        )

    return (
        f"{category} ({confidence_pct}%)\n"
        f"Reply with a different category to correct:\n"
        f"{', '.join(CATEGORIES)}"
    )


def parse_correction(text: str) -> str | None:
    """Parse user reply to extract category for correction."""
    text = text.lower().strip()

    # Direct category match
    for cat in CATEGORIES + ["inbox"]:
        if text == cat or text.startswith(cat):
            return cat

    # Common aliases
    aliases = {
        "person": "people",
        "project": "projects",
        "idea": "ideas",
        "todo": "projects",
        "task": "projects",
        "reminder": "admin",
        "note": "ideas",
    }
    for alias, cat in aliases.items():
        if text.startswith(alias):
            return cat

    return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages."""
    if not update.message or not update.message.text:
        return

    message = update.message
    text = message.text.strip()
    chat_id = message.chat_id
    message_id = message.message_id

    logger.info(f"Received: chat_id={chat_id} msg_id={message_id} text={text[:50]}")

    # Check if this is a reply to a bot message (correction flow)
    if message.reply_to_message and message.reply_to_message.from_user.is_bot:
        await handle_correction(update, context)
        return

    # New message - classify and store
    try:
        result = classify_message(text)
        logger.info(f"Classified: {result}")

        # Determine final category
        if should_go_to_inbox(result):
            category = "inbox"
        else:
            category = result.get("category", "inbox")

        # Store entry
        entry = create_entry(
            category=category,
            raw_message=text,
            confidence=result.get("confidence", 0),
            chat_id=chat_id,
            message_id=message_id,
        )

        # Log audit event
        log_audit(
            action="classified",
            item_id=entry["id"],
            category=category,
            confidence=result.get("confidence"),
            details={"reasoning": result.get("reasoning")},
        )

        # Send confirmation
        confirmation = format_confirmation(entry, result)
        sent = await message.reply_text(confirmation)

        logger.info(f"Stored: {entry['id']} -> {category}")

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await message.reply_text(f"Error: {e}")


async def handle_correction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle reply-based corrections."""
    message = update.message
    text = message.text.strip()
    chat_id = message.chat_id

    # Get the original message we're replying to
    original = message.reply_to_message
    original_text = original.text if original else ""

    logger.info(f"Correction attempt: {text} for reply to: {original_text[:30]}")

    # Parse the correction category
    new_category = parse_correction(text)

    if not new_category:
        await message.reply_text(
            f"Didn't understand category. Options:\n{', '.join(CATEGORIES + ['inbox'])}"
        )
        return

    # Try to find the original entry by looking at the bot's confirmation message
    # The confirmation message is a reply to the original user message
    if original.reply_to_message:
        orig_user_msg = original.reply_to_message
        result = get_entry_by_message_id(orig_user_msg.chat_id, orig_user_msg.message_id)

        if result:
            entry, old_category = result

            if old_category == new_category:
                await message.reply_text(f"Already in {new_category}")
                return

            # Move the entry
            moved = move_entry(entry["id"], old_category, new_category)

            if moved:
                # Log correction
                log_audit(
                    action="corrected",
                    item_id=entry["id"],
                    category=new_category,
                    details={"from_category": old_category},
                )

                await message.reply_text(f"Moved to {new_category}")
                logger.info(f"Corrected: {entry['id']} from {old_category} to {new_category}")
                return

    # Couldn't find the entry - queue for manual processing
    add_correction(
        entry_id="unknown",
        from_category="unknown",
        to_category=new_category,
        chat_id=chat_id,
    )

    await message.reply_text(
        f"Couldn't find original entry. Queued correction to {new_category}."
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors."""
    logger.error(f"Update {update} caused error {context.error}")


def main():
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not set. Create .env file with TELEGRAM_TOKEN=your_token")

    # Initialize storage
    init_storage()

    # Build application
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
