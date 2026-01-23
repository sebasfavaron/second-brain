"""
Telegram bot listener for Second Brain.

Handles:
- Incoming text messages -> AI determines intent -> execute action
- Reply-based corrections via AI reasoning
- AI-driven delete, correct, store, respond actions
"""
import logging
import json
from datetime import datetime

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

from config import TELEGRAM_TOKEN, CATEGORIES, CONFIDENCE_THRESHOLD, ANTHROPIC_API_KEY
from classifier import get_client
from storage import (
    init_storage,
    create_entry,
    get_entry_by_message_id,
    get_recent_entries,
    move_entry,
    delete_entry,
    log_audit,
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

# Intent determination system prompt
INTENT_SYSTEM_PROMPT = """You are a personal knowledge management assistant. Analyze incoming messages and decide what action to take.

AVAILABLE ACTIONS:
- "store": New information to save. Classify into: people, projects, ideas, admin
- "correct": User wants to fix a previous classification. Requires target entry.
- "delete": User wants to remove an entry. Requires target entry.
- "ignore": Message is conversational, no storage action needed.
- "respond": User is asking a question or needs a response (no storage).

CONTEXT PROVIDED:
- message: The user's current message
- reply_to: The original entry/message if user is replying (may be null)
- recent_entries: Last few entries for context
- category_contexts: Summaries of existing knowledge

DECISION GUIDELINES:
1. If message contains new factual information → "store" with appropriate category
2. If user says "no", "wrong", "actually X" referring to a previous entry → "correct" or "delete"
3. If user provides a category name after a classification → "correct" to that category
4. If user says "delete", "remove", "no hace falta" → "delete" the referenced entry
5. If message is just acknowledgment ("ok", "thanks", "gracias") → "ignore"
6. If user asks a question → "respond"
7. If user says "no" or "no hace falta" without context → could be delete or ignore, check reply_to

EXAMPLES:
- "Felipe is my business partner" → store/people
- "no hace falta, clasificar ballbox" → delete (the entry wasn't needed)
- "actually that's a project not a person" → correct to projects
- "people" (as reply to classification) → correct to people
- "ok thanks" → ignore
- "what did I save about Felipe?" → respond

Return JSON ONLY (no markdown blocks):
{"action": "store|correct|delete|ignore|respond", "category": "people|projects|ideas|admin|null", "target_entry_id": "uuid|null", "confidence": 0.0-1.0, "reasoning": "brief explanation", "response": "text for respond action|null"}
"""


def gather_context_for_intent(text: str, reply_context: dict = None) -> str:
    """Build context string for Claude's intent determination."""
    parts = [f"[USER MESSAGE]\n{text}"]

    # Add reply context if available
    if reply_context:
        entry = reply_context.get("entry", {})
        parts.append(f"\n[REPLYING TO ENTRY]")
        parts.append(f"Entry ID: {entry.get('id', 'unknown')}")
        parts.append(f"Category: {reply_context.get('category')}")
        parts.append(f"Message: {entry.get('raw_message', '')}")
        parts.append(f"Confidence: {entry.get('confidence', 0)}")
        parts.append(f"Bot said: {reply_context.get('bot_confirmation', '')}")

    # Add recent entries for context
    recent = []
    for cat in CATEGORIES + ["inbox"]:
        try:
            entries = get_recent_entries(cat, limit=2)
            for e in entries:
                msg_preview = e.get('raw_message', '')[:50]
                recent.append(f"[{cat}] {msg_preview}")
        except:
            pass

    if recent:
        parts.append(f"\n[RECENT ENTRIES]\n" + "\n".join(recent[:5]))

    # Add category contexts
    try:
        from context_manager import load_context
        context_parts = []
        for cat in CATEGORIES:
            ctx = load_context(cat)
            if ctx and len(ctx.strip()) > 20:
                context_parts.append(f"\n[{cat.upper()} CONTEXT]\n{ctx[:200]}...")
        if context_parts:
            parts.append("\n".join(context_parts))
    except:
        pass

    return "\n".join(parts)


async def determine_intent(message_text: str, reply_context: dict = None) -> dict:
    """
    Use Claude to determine what action to take.

    Returns:
        {
            "action": "store" | "correct" | "delete" | "ignore" | "respond",
            "category": "people" | "projects" | "ideas" | "admin" | None,
            "target_entry_id": "uuid" | None,
            "confidence": 0.0-1.0,
            "reasoning": "...",
            "response": "..." | None
        }
    """
    if not message_text or not message_text.strip():
        return {
            "action": "ignore",
            "category": None,
            "target_entry_id": None,
            "confidence": 1.0,
            "reasoning": "Empty message",
            "response": None
        }

    # Build context
    context = gather_context_for_intent(message_text, reply_context)

    try:
        response = get_client().messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=INTENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": context}]
        )

        content = response.content[0].text.strip()

        # Parse JSON response
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        result = json.loads(content)

        # Validate and set defaults
        result.setdefault("action", "store")
        result.setdefault("category", None)
        result.setdefault("target_entry_id", None)
        result.setdefault("confidence", 0.5)
        result.setdefault("reasoning", "")
        result.setdefault("response", None)

        # If correcting/deleting and we have reply_context, use the entry ID from context
        if result["action"] in ["correct", "delete"] and reply_context:
            result["target_entry_id"] = reply_context.get("entry", {}).get("id")

        logger.info(f"Intent determined: {result['action']} (confidence: {result['confidence']})")

        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse intent response: {e}")
        # Fallback to storage
        return {
            "action": "store",
            "category": "inbox",
            "target_entry_id": None,
            "confidence": 0.3,
            "reasoning": f"Parse error, defaulting to store: {e}",
            "response": None
        }
    except Exception as e:
        logger.error(f"Intent determination error: {e}")
        return {
            "action": "store",
            "category": "inbox",
            "target_entry_id": None,
            "confidence": 0.3,
            "reasoning": f"Error, defaulting to store: {e}",
            "response": None
        }


async def execute_action(message, intent: dict, reply_context: dict = None) -> None:
    """Dispatcher based on Claude's decision."""
    action = intent.get("action")

    if action == "store":
        category = intent.get("category", "inbox")
        confidence = intent.get("confidence", 0.5)

        # Validate category
        if category not in CATEGORIES:
            category = "inbox"
            confidence = min(confidence, 0.5)

        # Low confidence goes to inbox
        if confidence < CONFIDENCE_THRESHOLD:
            category = "inbox"

        entry = create_entry(
            category=category,
            raw_message=message.text,
            confidence=confidence,
            chat_id=message.chat_id,
            message_id=message.message_id,
        )

        log_audit("classified", entry["id"], category, confidence,
                  {"reasoning": intent.get("reasoning")})

        # Enrich context for high-confidence
        if category != "inbox" and confidence >= CONFIDENCE_THRESHOLD:
            try:
                from context_manager import enrich_context
                enrich_context(category, entry)
                logger.info(f"Enriched {category} context")
            except Exception as e:
                logger.warning(f"Context enrichment failed: {e}")

        # Send confirmation
        confidence_pct = int(confidence * 100)
        if category == "inbox":
            await message.reply_text(
                f"inbox ({confidence_pct}%)\n"
                f"Reasoning: {intent.get('reasoning', 'unclear')}\n\n"
                f"Reply with category to reclassify:\n{', '.join(CATEGORIES)}"
            )
        else:
            await message.reply_text(f"{category} ({confidence_pct}%)")

        logger.info(f"Stored: {entry['id']} -> {category}")

    elif action == "correct":
        if not reply_context or not reply_context.get("entry"):
            await message.reply_text("No entry found to correct")
            return

        entry = reply_context["entry"]
        old_category = reply_context["category"]
        new_category = intent.get("category")

        if not new_category or new_category not in CATEGORIES + ["inbox"]:
            await message.reply_text(
                f"Invalid category. Options:\n{', '.join(CATEGORIES + ['inbox'])}"
            )
            return

        if new_category == old_category:
            await message.reply_text(f"Already in {new_category}")
            return

        moved = move_entry(entry["id"], old_category, new_category)
        if moved:
            log_audit("corrected", entry["id"], new_category,
                     details={"from_category": old_category, "reasoning": intent.get("reasoning")})
            await message.reply_text(f"Moved to {new_category}")
            logger.info(f"Corrected: {entry['id']} from {old_category} to {new_category}")
        else:
            await message.reply_text("Failed to move entry")

    elif action == "delete":
        entry = None
        category = None

        # First, check if we have reply context
        if reply_context and reply_context.get("entry"):
            entry = reply_context["entry"]
            category = reply_context["category"]
        else:
            # No reply context, search for recent entries matching keywords
            keywords = message.text.lower().split()
            # Remove common words that don't help identify entries
            stop_words = {"no", "hace", "falta", "clasificar", "delete", "remove", "borrar", "eliminar"}
            keywords = [k for k in keywords if k not in stop_words and len(k) > 2]

            if keywords:
                # Search recent entries across all categories
                matches = []
                for cat in CATEGORIES + ["inbox"]:
                    try:
                        entries = get_recent_entries(cat, limit=10)
                        for e in entries:
                            msg_lower = e.get('raw_message', '').lower()
                            # Check if any keyword matches
                            if any(kw in msg_lower for kw in keywords):
                                matches.append((e, cat))
                    except:
                        pass

                if len(matches) == 1:
                    # Found exactly one match
                    entry, category = matches[0]
                    logger.info(f"Found matching entry for deletion: {entry['id']}")
                elif len(matches) > 1:
                    # Multiple matches, show them to user
                    match_list = "\n".join([
                        f"- [{m[1]}] {m[0].get('raw_message', '')[:50]}..."
                        for m in matches[:5]
                    ])
                    await message.reply_text(
                        f"Found {len(matches)} matching entries:\n{match_list}\n\n"
                        f"Reply to my original classification message to delete a specific entry."
                    )
                    return
                else:
                    # No matches found
                    search_terms = ", ".join(keywords)
                    await message.reply_text(f"No recent entry found matching: {search_terms}")
                    return

        if not entry:
            await message.reply_text("No entry found to delete")
            return

        # Delete the entry
        deleted = delete_entry(entry["id"], category)
        if deleted:
            log_audit("deleted", entry["id"], category,
                     details={"reasoning": intent.get("reasoning")})
            await message.reply_text(f"Entry deleted: {entry.get('raw_message', '')[:50]}...")
            logger.info(f"Deleted: {entry['id']} from {category}")
        else:
            await message.reply_text("Failed to delete entry")

    elif action == "ignore":
        # No action needed
        logger.info(f"Ignored message: {intent.get('reasoning')}")
        pass

    elif action == "respond":
        response = intent.get("response", "I'm not sure how to help with that.")
        await message.reply_text(response)
        logger.info(f"Responded: {response[:50]}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages with AI-driven intent determination."""
    if not update.message or not update.message.text:
        return

    message = update.message
    text = message.text.strip()
    chat_id = message.chat_id
    message_id = message.message_id

    logger.info(f"Received: chat_id={chat_id} msg_id={message_id} text={text[:50]}")

    # Gather context
    reply_context = None
    if message.reply_to_message and message.reply_to_message.from_user.is_bot:
        # Get the original entry this reply refers to
        original = message.reply_to_message
        if original.reply_to_message:
            orig_msg = original.reply_to_message
            entry_result = get_entry_by_message_id(orig_msg.chat_id, orig_msg.message_id)
            if entry_result:
                entry, category = entry_result
                reply_context = {
                    "entry": entry,
                    "category": category,
                    "bot_confirmation": original.text
                }
                logger.info(f"Found reply context: entry={entry['id']}, category={category}")

    # Let Claude decide what to do
    try:
        intent = await determine_intent(text, reply_context)
        logger.info(f"Intent: {intent['action']} -> {intent.get('category', 'N/A')}")

        # Execute the action
        await execute_action(message, intent, reply_context)

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await message.reply_text(f"Error: {e}")


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
