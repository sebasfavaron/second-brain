"""
Unified Brain + Diary Telegram bot.

Combines knowledge management and diary/journal in one agentic bot.
Handles text, voice messages, reminders, and cross-references.
"""
import logging
import json
from datetime import datetime, date, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters, CommandHandler

from config import TELEGRAM_TOKEN, ANTHROPIC_API_KEY
from classifier import get_client
from storage import init_storage
from agent_tools import TOOL_DEFINITIONS, execute_tool
from conversation_state import get_conversation_history, add_message, clear_conversation
from voice_handler import handle_voice_message
import journal_storage
import reminder_storage

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
AGENT_SYSTEM_PROMPT = """You are a unified personal assistant managing both knowledge and diary/journal for the user.

MESSAGE TYPES - Route appropriately:
1. **DIARY**: Emotional, reflective, daily logs → write_journal
2. **KNOWLEDGE**: Facts, reminders, people info, projects → create_entry
3. **HYBRID**: Diary with extractable facts → write_journal + create_entry + link_entries

KNOWLEDGE CATEGORIES:
- people: Information about specific people (names, relationships, facts)
- projects: Work tasks, project updates, todos, deadlines
- ideas: Creative thoughts, future plans, insights
- admin: Logistics, appointments, locations
- inbox: Low-confidence items needing review

YOUR TOOLS:
Knowledge base (6):
- list_entries, search_entries, get_entry
- create_entry, move_entry, delete_entry

Journal/Diary (3):
- write_journal: Store diary entries (today's journal by default)
- read_journal: Read journal for specific date
- search_journal: Search across all journal entries

Reminders (2):
- create_reminder: Set time-based reminders (default: tomorrow 9 AM)
- list_reminders: Show pending/upcoming reminders

Cross-reference (2):
- link_entries: Connect journal entry to knowledge entry
- get_audio_file: Retrieve voice recording

ROUTING EXAMPLES:
"Today was rough" → write_journal (pure diary)
"Felipe birthday March 15" → create_entry(people) (pure knowledge)
"Great meeting with Juan, funding deadline March" → write_journal + create_entry(people + projects) + link_entries (hybrid)
"Remind me to call dentist tomorrow" → create_reminder
"What do I know about Felipe?" → search_entries + search_journal (search both)

HYBRID MESSAGE HANDLING:
1. Write full message to journal with write_journal
2. Extract factual info and create_entry for each fact
3. Link them with link_entries(journal_date, entry_id, "extracted_from")

REMINDER HANDLING:
- "Remind me X" → create_reminder (default: tomorrow 9 AM)
- "Remind me X at 3pm" → create_reminder with specific time
- "Remind me X daily/weekly/monthly" → create_reminder with repeat

Be concise and natural. Confirm actions. Voice messages are often diary-like."""


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


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming voice messages."""
    if not update.message or not update.message.voice:
        return

    message = update.message
    chat_id = message.chat_id
    message_id = message.message_id
    timestamp = datetime.fromtimestamp(message.date.timestamp())

    logger.info(f"Received voice: chat_id={chat_id} msg_id={message_id}")

    try:
        # Send "processing" message
        processing_msg = await message.reply_text("🎤 Transcribiendo...")

        # Download and transcribe
        result = await handle_voice_message(context.bot, message.voice, timestamp)

        if not result:
            await processing_msg.edit_text("❌ Error transcribiendo audio")
            return

        transcribed_text = result["text"]
        logger.info(f"Transcribed: {transcribed_text[:100]}")

        # Update processing message
        await processing_msg.edit_text(f"📝 Transcripción: {transcribed_text[:100]}...")

        # Process transcription with agent
        response = await process_message_with_agent(chat_id, transcribed_text, message_id)

        # Send final response
        await message.reply_text(f"🎤 {response}")

        logger.info(f"Voice processed and responded")

    except Exception as e:
        logger.error(f"Error handling voice: {e}", exc_info=True)
        await message.reply_text(f"❌ Error: {e}")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command - show usage information."""
    if not update.message:
        return

    help_text = """🧠 **Unified Brain + Diary Bot**

Tu asistente personal para gestión de conocimiento y diario/journal.

**📝 Tipos de Mensajes:**
• **Diario** - Reflexiones, emociones, logs diarios
  _Ej: "Hoy fue un día difícil"_

• **Conocimiento** - Hechos, personas, proyectos, admin
  _Ej: "Cumpleaños de Felipe: 15 de marzo"_

• **Híbrido** - Diario + hechos extraíbles
  _Ej: "Gran reunión con Juan, deadline viernes"_

• **Recordatorio** - Avisos con tiempo
  _Ej: "Recuérdame llamar al dentista mañana 3pm"_

**🗣️ Voz:**
Envía mensajes de voz - se transcriben y procesan automáticamente.

**📋 Comandos:**
/help - Muestra esta ayuda
/today - Diario de hoy + recordatorios
/day YYYY-MM-DD - Diario de fecha específica
/search <query> - Busca en diario y conocimiento
/reminders - Lista recordatorios pendientes
/inbox - Items de baja confianza para revisar
/reset - Limpia historial de conversación

**📂 Categorías de Conocimiento:**
• people - Personas, relaciones, hechos
• projects - Trabajo, tareas, deadlines
• ideas - Pensamientos creativos, insights
• admin - Logística, citas, ubicaciones
• inbox - Clasificación pendiente

**💡 Ejemplos:**
"Hoy me sentí motivado después de la charla"
"Felipe cumpleaños marzo 15"
"Recuérdame revisar el reporte mañana 9am"
🎤 [mensaje de voz]"""

    await update.message.reply_text(help_text, parse_mode="Markdown")
    logger.info(f"Sent help to chat_id={update.message.chat_id}")


async def handle_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reset command to clear conversation history."""
    if not update.message:
        return

    chat_id = update.message.chat_id
    clear_conversation(chat_id)
    await update.message.reply_text("Conversation history cleared. Starting fresh!")
    logger.info(f"Reset conversation for chat_id={chat_id}")


async def handle_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /today command - show today's journal and reminders."""
    if not update.message:
        return

    try:
        # Read today's journal
        journal = journal_storage.read_journal()

        # Get today's reminders
        reminders = reminder_storage.get_upcoming_reminders(days=1)

        response = "📅 **Hoy**\n\n"

        # Journal section
        if journal.get("exists"):
            content = journal.get("content", "")
            # Show first 500 chars
            preview = content[:500] + ("..." if len(content) > 500 else "")
            response += f"**Diario:**\n{preview}\n\n"
        else:
            response += "**Diario:** Sin entradas hoy\n\n"

        # Reminders section
        if reminders:
            response += f"**Recordatorios ({len(reminders)}):**\n"
            for r in reminders[:5]:
                trigger = datetime.fromisoformat(r["trigger_time"])
                response += f"• {trigger.strftime('%H:%M')} - {r['content']}\n"
        else:
            response += "**Recordatorios:** Ninguno"

        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Error in /today: {e}")
        await update.message.reply_text(f"Error: {e}")


async def handle_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /day command - show journal for specific date."""
    if not update.message:
        return

    try:
        # Parse date from args (format: YYYY-MM-DD)
        if not context.args:
            await update.message.reply_text("Uso: /day YYYY-MM-DD")
            return

        date_str = context.args[0]
        target_date = date.fromisoformat(date_str)

        # Read journal
        journal = journal_storage.read_journal(target_date)

        if not journal.get("exists"):
            await update.message.reply_text(f"No hay entradas para {date_str}")
            return

        content = journal.get("content", "")
        # Split into chunks if too long
        if len(content) > 4000:
            await update.message.reply_text(content[:4000] + "...\n\n(continúa)")
            await update.message.reply_text(content[4000:8000])
        else:
            await update.message.reply_text(content)

    except ValueError:
        await update.message.reply_text("Formato inválido. Uso: /day YYYY-MM-DD")
    except Exception as e:
        logger.error(f"Error in /day: {e}")
        await update.message.reply_text(f"Error: {e}")


async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /search command - search both journal and knowledge."""
    if not update.message:
        return

    try:
        if not context.args:
            await update.message.reply_text("Uso: /search <query>")
            return

        query = " ".join(context.args)

        # Search journal
        journal_matches = journal_storage.search_journal(query)

        # Search knowledge (via agent to get formatted results)
        response = f"🔍 Buscando: '{query}'\n\n"

        # Journal results
        if journal_matches:
            response += f"**Diario ({len(journal_matches)} entradas):**\n"
            for match in journal_matches[:3]:
                response += f"• {match['date']}\n"
            if len(journal_matches) > 3:
                response += f"...y {len(journal_matches) - 3} más\n"
            response += "\n"
        else:
            response += "**Diario:** Sin resultados\n\n"

        # Use agent to search knowledge
        chat_id = update.message.chat_id
        search_request = f"Busca '{query}' en las categorías del conocimiento"
        knowledge_response = await process_message_with_agent(chat_id, search_request, update.message.message_id)

        response += f"**Conocimiento:**\n{knowledge_response}"

        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Error in /search: {e}")
        await update.message.reply_text(f"Error: {e}")


async def handle_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reminders command - list upcoming reminders."""
    if not update.message:
        return

    try:
        reminders = reminder_storage.get_upcoming_reminders(days=30)

        if not reminders:
            await update.message.reply_text("📝 No hay recordatorios pendientes")
            return

        response = f"📝 **Recordatorios ({len(reminders)}):**\n\n"

        for r in reminders[:10]:
            trigger = datetime.fromisoformat(r["trigger_time"])
            days_until = (trigger - datetime.now()).days

            if days_until == 0:
                when = "Hoy " + trigger.strftime('%H:%M')
            elif days_until == 1:
                when = "Mañana " + trigger.strftime('%H:%M')
            else:
                when = trigger.strftime('%Y-%m-%d %H:%M')

            repeat_icon = "🔁" if r.get("repeat") != "none" else ""
            response += f"{repeat_icon} {when}\n  {r['content']}\n\n"

        if len(reminders) > 10:
            response += f"...y {len(reminders) - 10} más"

        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Error in /reminders: {e}")
        await update.message.reply_text(f"Error: {e}")


async def handle_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /inbox command - show low-confidence items."""
    if not update.message:
        return

    try:
        chat_id = update.message.chat_id
        response = await process_message_with_agent(chat_id, "¿Qué hay en inbox?", update.message.message_id)
        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Error in /inbox: {e}")
        await update.message.reply_text(f"Error: {e}")


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

    # Command handlers
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("reset", handle_reset))
    app.add_handler(CommandHandler("today", handle_today))
    app.add_handler(CommandHandler("day", handle_day))
    app.add_handler(CommandHandler("search", handle_search))
    app.add_handler(CommandHandler("reminders", handle_reminders))
    app.add_handler(CommandHandler("inbox", handle_inbox))

    # Message handlers
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Error handler
    app.add_error_handler(error_handler)

    logger.info("Unified Brain + Diary bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
