# Agentic Bot Architecture

## Overview

Complete rewrite from scripted intent system to fully agentic conversational bot. Claude now has direct tool access and maintains conversation history for natural multi-turn interactions.

## Architecture

### Before (Intent-based)
```
Message → Intent Detection → Scripted Dispatch → Fixed Responses
```

### Now (Agentic)
```
Message → Claude Agent (with history + tools) → Tool Loop → Natural Response
```

## Key Components

### 1. agent_tools.py

Defines 6 tools Claude can use:

- **list_entries(category, limit)** - List all entries in a category
- **search_entries(query, categories, limit)** - Search across categories
- **get_entry(entry_id)** - Get specific entry details
- **create_entry(category, message, confidence)** - Store new entry
- **move_entry(entry_id, from_category, to_category)** - Correct classification
- **delete_entry(entry_id, category)** - Remove entry

Each tool returns structured JSON with `success`, data, and error fields.

### 2. conversation_state.py

Manages conversation history per chat_id:

- Stores last 20 messages per user (configurable)
- Maintains conversation context across sessions
- Persists to `brain/conversations.json`
- Supports `/reset` command to clear history

### 3. bot-listener.py (Agentic)

Main bot using Claude's tool use API:

- Loads conversation history (last 10 messages)
- Calls Claude with tools and full context
- Handles tool use loop (Claude → tools → Claude → ...)
- Stores assistant responses in history
- Natural conversation flow

## System Prompt

Instructs Claude to:

1. **Store new information** with appropriate category and confidence
2. **Answer questions** by using list/search tools (no hallucinations)
3. **Handle corrections** by moving entries between categories
4. **Delete entries** after searching and confirming
5. **Maintain context** across messages (remember what was shown)
6. **Ask for clarification** when ambiguous

## Example Flows

### Scenario 1: Asking what's in inbox

**Before:**
```
User: "¿qué hay en inbox?"
Bot: "No hay nada pendiente en inbox..." (HALLUCINATION)
```

**Now:**
```
User: "¿qué hay en inbox?"
Bot: → list_entries(category="inbox")
     → Returns actual data: [{"id": "...", "raw_message": "ballbox", ...}]
Bot: "Hay 1 entrada en inbox:
     - ballbox (40% confidence, Jan 18)"
```

### Scenario 2: Multi-turn deletion

**Before:**
```
User: "no hace falta clasificar ballbox"
Bot: "Found 5 matching entries: ..."
User: "the one in inbox"
Bot: "I'm not sure which entry..." (LOST CONTEXT)
```

**Now:**
```
User: "no hace falta clasificar ballbox"
Bot: → search_entries(query="ballbox")
     → Returns 5 matches
Bot: "Found 5 entries with 'ballbox':
     1. [people] ballbox es un emprendimiento...
     2. [projects] ballbox es un emprendimiento...
     3. [inbox] ballbox
     Which one?"

User: "the one in inbox"
Bot: → Remembers previous search (from conversation history)
     → Filters to inbox entry
     → delete_entry(entry_id="...", category="inbox")
Bot: "Entry deleted: ballbox"
```

### Scenario 3: Natural corrections

**Before:**
```
User: "actually that's a project"
Bot: → Intent detection fails or requires exact phrasing
```

**Now:**
```
User: "actually that's a project"
Bot: → Understands from context which entry
     → move_entry(entry_id="...", from_category="people", to_category="projects")
Bot: "Moved to projects"
```

## Benefits

### 1. No Hallucinations
- Tools return real data from JSON files
- Claude can't make up information
- Everything is grounded in actual storage

### 2. Context Awareness
- Maintains conversation history
- Remembers what was shown to user
- Handles multi-turn clarifications naturally

### 3. Flexible Interactions
- No need to script every flow
- Claude decides which tools to use
- Adapts to natural language variations

### 4. Better Search & Filter
- Can search, evaluate results, then ask user
- Can filter results based on follow-up messages
- Handles ambiguity gracefully

### 5. Natural Language
- Understands intent from context
- Can ask clarifying questions
- Responds conversationally

## Tool Use Loop

```
1. User sends message
2. Load conversation history (last 10 messages)
3. Call Claude with tools + history + new message
4. While Claude requests tools:
   a. Execute tool(s)
   b. Add results to conversation
   c. Call Claude again with results
5. Extract final text response
6. Save to conversation history
7. Send to user
```

## Conversation State

Stored in `brain/conversations.json`:

```json
{
  "236088727": {
    "started_at": "2026-01-23T16:00:00",
    "messages": [
      {
        "role": "user",
        "content": "¿qué hay en inbox?",
        "timestamp": "2026-01-23T16:00:00"
      },
      {
        "role": "assistant",
        "content": "Hay 1 entrada en inbox: ...",
        "timestamp": "2026-01-23T16:00:01"
      }
    ]
  }
}
```

## Commands

- **Regular messages**: Processed by agent with tools
- **/reset**: Clear conversation history for current chat

## Files

| File | Purpose |
|------|---------|
| `bot-listener.py` | Agentic main bot (replaces intent-based) |
| `agent_tools.py` | Tool definitions and implementations |
| `conversation_state.py` | Conversation history management |
| `bot-listener-intent-based.py` | Backup of old intent system |
| `bot-listener-agentic.py` | Original agentic (same as bot-listener.py) |

## Migration

- No data migration needed
- Existing entries work as-is
- Conversation history starts fresh
- Old intent system backed up at `bot-listener-intent-based.py`

## Configuration

Uses existing config:

- `TELEGRAM_TOKEN`: Telegram bot token
- `ANTHROPIC_API_KEY`: Claude API key
- `CATEGORIES`: Valid categories (people, projects, ideas, admin)
- `CONFIDENCE_THRESHOLD`: Threshold for inbox (0.7)

## API Costs

Each message makes 1+ Claude API calls:

- **Simple messages**: 1 call (no tools needed)
- **Storage/search**: 2-3 calls (tool use loop)
- **Complex flows**: 3-5 calls (multiple tool iterations)

Context per call includes:
- System prompt (~400 tokens)
- Conversation history (~200-1000 tokens)
- Tool definitions (~500 tokens)
- User message + tool results (variable)

## Error Handling

1. **Tool execution fails**: Returns error in tool result, Claude explains to user
2. **API error**: Logs error, sends error message to user
3. **Parse error**: Falls back to error response
4. **No matches found**: Claude explains and suggests alternatives

## Future Enhancements

1. **Smart context pruning**: Only load relevant history
2. **Batch operations**: Delete/move multiple entries at once
3. **Query understanding**: More sophisticated search with NLP
4. **Summaries**: Generate category summaries on demand
5. **Export**: Export entries in various formats
6. **Reminders**: Schedule follow-ups for inbox items

## Deployment

Deployed to `ballbox-first` server:
- Service: `second-brain-bot.service`
- Path: `/home/sebas/second-brain/`
- Logs: `sudo journalctl -u second-brain-bot.service`
- Restart: `sudo systemctl restart second-brain-bot.service`

## Testing

Try these flows:

1. **List inbox**: "¿qué hay en inbox?"
2. **Search**: "busca ballbox"
3. **Delete**: "no hace falta ballbox" → "the one in inbox"
4. **Correction**: Send message → "actually that's a project"
5. **New entry**: "Felipe es mi socio"
6. **Multi-turn**: Ask question, then follow up with "tell me more"
7. **Reset**: /reset to clear history
