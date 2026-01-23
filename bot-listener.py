"""
Agentic Telegram bot for Second Brain.

Uses Claude with tool use API for natural conversational interaction.
Claude has direct access to storage tools and maintains conversation history.
"""
import logging
import json
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters, CommandHandler

from config import TELEGRAM_TOKEN, ANTHROPIC_API_KEY
from classifier import get_client
from storage import init_storage
from agent_tools import TOOL_DEFINITIONS, execute_tool
from conversation_state import get_conversation_history, add_message, clear_conversation

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

# System prompt for the agent
AGENT_SYSTEM_PROMPT = """You are a personal knowledge management assistant helping a user organize their "second brain."

AVAILABLE CATEGORIES:
- people: Information about specific people (names, relationships, facts)
- projects: Work tasks, project updates, todos, deadlines
- ideas: Creative thoughts, future plans, insights
- admin: Logistics, appointments, locations, reminders
- inbox: Low-confidence items needing review

YOUR CAPABILITIES:
You have tools to:
1. Search and list entries in any category
2. Create new entries when user shares information
3. Move entries between categories (corrections)
4. Delete entries when requested
5. Answer questions about stored information

BEHAVIOR GUIDELINES:
1. **New information**: When user shares facts, create entries with appropriate category and confidence (0.7+ for clear classifications)
2. **Questions**: When user asks what's in a category or searches for info, use list_entries or search_entries tools
3. **Corrections**: When user says an entry is in wrong category, use move_entry
4. **Deletions**: When user wants to delete something, search for it, confirm, then delete
5. **Conversation**: Maintain context across messages. Remember what you showed the user
6. **Honesty**: Only use tools to access real data. Never make up or hallucinate information
7. **Clarification**: If ambiguous, ask user to clarify (e.g., "which entry?" if multiple matches)

EXAMPLES:
User: "Felipe es mi socio"
→ create_entry(category="people", message="Felipe es mi socio", confidence=0.9)
→ Respond: "Guardado en people (90%)"

User: "¿qué hay en inbox?"
→ list_entries(category="inbox")
→ Show user the actual entries found

User: "no hace falta clasificar ballbox"
→ search_entries(query="ballbox")
→ If found, confirm and delete_entry
→ If multiple, list and ask which one

User: "the one in inbox"
→ Remember previous search context, filter to inbox entry
→ delete_entry with that entry

Be concise and natural. Confirm actions when you perform them."""


async def process_message_with_agent(chat_id: int, user_message: str, telegram_message_id: int) -> str:
    """
    Process a user message using the Claude agent with tools.

    Returns the assistant's response text.
    """
    # Get conversation history
    history = get_conversation_history(chat_id, limit=10)

    # Build messages for Claude API (remove timestamp field for API call)
    messages = [{"role": msg["role"], "content": msg["content"]} for msg in history]
    messages.append({"role": "user", "content": user_message})

    # Store user message in history
    add_message(chat_id, "user", user_message)

    logger.info(f"Processing message with {len(history)} history messages")

    # Call Claude with tools (agentic loop)
    try:
        response = get_client().messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=AGENT_SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages
        )

        # Handle tool use loop
        while response.stop_reason == "tool_use":
            # Extract tool uses from response
            tool_uses = [block for block in response.content if block.type == "tool_use"]

            logger.info(f"Agent requested {len(tool_uses)} tool calls")

            # Execute each tool and collect results
            tool_results = []
            for tool_use in tool_uses:
                tool_name = tool_use.name
                tool_input = tool_use.input

                # Pass chat_id and message_id for create_entry BEFORE executing
                if tool_name == "create_entry":
                    tool_input["chat_id"] = chat_id
                    tool_input["message_id"] = telegram_message_id

                logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

                # Execute the tool once
                result = execute_tool(tool_name, tool_input)

                logger.info(f"Tool result: {result}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result)
                })

            # Add assistant's tool use and tool results to messages
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            # Save tool use to conversation history (serialize content blocks)
            serialized_content = [
                {"type": block.type, "text": block.text} if hasattr(block, "text")
                else {"type": block.type, "id": block.id, "name": block.name, "input": block.input}
                for block in response.content
            ]
            add_message(chat_id, "assistant", serialized_content)
            add_message(chat_id, "user", tool_results)

            # Continue conversation with tool results
            response = get_client().messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=AGENT_SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=messages
            )

        # Extract final text response
        text_blocks = [block.text for block in response.content if hasattr(block, "text")]
        assistant_response = "\n".join(text_blocks) if text_blocks else "Lo siento, no pude procesar eso."

        # Store final assistant response in history (serialize content blocks)
        serialized_final = [
            {"type": block.type, "text": block.text} if hasattr(block, "text")
            else {"type": block.type, "id": block.id, "name": block.name, "input": block.input}
            for block in response.content
        ]
        add_message(chat_id, "assistant", serialized_final)

        return assistant_response

    except Exception as e:
        logger.error(f"Error in agent processing: {e}", exc_info=True)
        return f"Error: {e}"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages using the agent."""
    if not update.message or not update.message.text:
        return

    message = update.message
    text = message.text.strip()
    chat_id = message.chat_id
    message_id = message.message_id

    logger.info(f"Received: chat_id={chat_id} msg_id={message_id} text={text[:50]}")

    try:
        # Process with agent
        response = await process_message_with_agent(chat_id, text, message_id)

        # Send response
        await message.reply_text(response)

        logger.info(f"Responded: {response[:100]}")

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await message.reply_text(f"Error: {e}")


async def handle_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reset command to clear conversation history."""
    if not update.message:
        return

    chat_id = update.message.chat_id
    clear_conversation(chat_id)
    await update.message.reply_text("Conversation history cleared. Starting fresh!")
    logger.info(f"Reset conversation for chat_id={chat_id}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors."""
    logger.error(f"Update {update} caused error {context.error}")


def main():
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not set. Create .env file with TELEGRAM_TOKEN=your_token")

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set. Create .env file with ANTHROPIC_API_KEY=your_key")

    # Initialize storage
    init_storage()

    # Build application
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("reset", handle_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Agentic bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
