# AI-Driven Intent System Implementation

## Overview

Replaced rule-based message handling with Claude AI reasoning. Every message now goes through Claude to determine intent and action.

## What Changed

### Before (Rule-based)
```
Message → Is reply? → Yes → parse_correction() → move_entry()
                   → No  → classify_message() → create_entry()
```

### After (AI-driven)
```
Message → gather_context() → Claude determines intent → execute_action()
```

## Key Components

### 1. `determine_intent(message_text, reply_context)` - bot-listener.py:121

Uses Claude to analyze messages and decide what action to take.

**Returns:**
```python
{
    "action": "store" | "correct" | "delete" | "ignore" | "respond",
    "category": "people" | "projects" | "ideas" | "admin" | None,
    "target_entry_id": "uuid" | None,
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation",
    "response": "text for respond action" | None
}
```

### 2. `gather_context_for_intent(text, reply_context)` - bot-listener.py:77

Builds rich context for Claude including:
- User's current message
- Reply context (if replying to a classification)
- Recent entries across all categories
- Category context summaries

### 3. `execute_action(message, intent, reply_context)` - bot-listener.py:206

Dispatcher that executes the action determined by Claude:
- **store**: Create new entry, enrich context if high confidence
- **correct**: Move entry to new category
- **delete**: Remove entry from storage
- **ignore**: No action (acknowledgments, conversational messages)
- **respond**: Answer user questions

### 4. `handle_message(update, context)` - bot-listener.py:312

Simplified main handler:
1. Extract message and gather reply context if available
2. Call `determine_intent()` to get AI decision
3. Call `execute_action()` to execute the decision

## Removed Code

- `parse_correction()`: Replaced by AI intent determination
- `handle_correction()`: Merged into `execute_action()`
- `format_confirmation()`: Response formatting now inline in `execute_action()`

## Examples

### Example 1: New Entry
```
User: "Felipe es mi socio de ballbox"
Claude thinks: New factual info about a person → store/people
Action: create_entry(category="people", ...)
Bot: "people (92%)"
```

### Example 2: Category Correction
```
Bot: "people (92%)"
User replies: "projects"
Claude thinks: User replying with category name → correct to projects
Action: move_entry(..., "people", "projects")
Bot: "Moved to projects"
```

### Example 3: Natural Language Correction
```
Bot: "people (85%)"
User replies: "actually that's a project not a person"
Claude thinks: User correcting classification → correct to projects
Action: move_entry(..., "people", "projects")
Bot: "Moved to projects"
```

### Example 4: Delete Entry
```
Bot: "inbox (45%)"
User replies: "no hace falta, clasificar ballbox"
Claude thinks: "no hace falta" = not needed, delete the entry
Action: delete_entry(...)
Bot: "Entry deleted"
```

### Example 5: Acknowledgment (Ignore)
```
User: "ok gracias"
Claude thinks: Acknowledgment, no action needed
Action: ignore
Bot: (no response)
```

### Example 6: Question (Respond)
```
User: "what did I save about Felipe?"
Claude thinks: User asking question → respond
Action: respond with relevant information
Bot: "I found these entries about Felipe: ..."
```

## System Prompt

The intent determination uses `INTENT_SYSTEM_PROMPT` (bot-listener.py:40) which instructs Claude on:
- Available actions
- Decision guidelines
- Examples of each action type
- Expected JSON response format

## Error Handling

1. **JSON parse fails**: Defaults to "store" action with inbox category
2. **API error**: Defaults to "store" action with inbox category
3. **No entry found for correction/deletion**: Returns error message to user
4. **Invalid category**: Defaults to inbox

## Testing

Run the test script to verify intent determination:

```bash
python test_intent_system.py
```

Tests include:
- New entry classification
- Category corrections
- Delete requests
- Acknowledgments (ignore)
- Questions (respond)

## Deployment Notes

1. **API costs**: Every message now makes 2 Claude API calls:
   - One for intent determination (~300 tokens)
   - One for classification if action is "store"

2. **Context loading**: System loads recent entries and category contexts for each message. May impact performance with large datasets.

3. **Migration**: No data migration needed. Existing entries work as-is.

4. **Backward compatibility**: All existing functionality preserved, just AI-driven instead of rule-based.

## Benefits

1. **Natural language understanding**: Users can correct entries naturally ("actually that's a project")
2. **Delete support**: Can now delete entries with natural language ("no hace falta")
3. **Conversational**: Ignores acknowledgments without creating entries
4. **Question answering**: Can respond to user queries (future enhancement)
5. **Flexible**: Easy to add new actions without code changes (just update prompt)

## Configuration

No new config variables needed. Uses existing:
- `CATEGORIES`: List of valid categories
- `CONFIDENCE_THRESHOLD`: Threshold for inbox vs. category
- `ANTHROPIC_API_KEY`: Claude API key

## Files Modified

- `bot-listener.py`: Complete refactor of message handling logic
- `test_intent_system.py`: New test file for verification

## Future Enhancements

1. Implement actual "respond" action with knowledge retrieval
2. Add support for editing entries (update existing content)
3. Add support for merging entries
4. Track user preferences over time
5. Implement smarter context selection (only load relevant categories)
