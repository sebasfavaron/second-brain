"""
Conversation state management for the agentic bot.

Maintains conversation history per chat_id to enable multi-turn conversations.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from config import BRAIN_DIR

CONVERSATION_FILE = BRAIN_DIR / "conversations.json"
MAX_HISTORY_PER_CHAT = 20  # Keep last 20 messages per chat


def _load_conversations() -> Dict:
    """Load conversation history from file."""
    if not CONVERSATION_FILE.exists():
        return {}
    try:
        with open(CONVERSATION_FILE) as f:
            return json.load(f)
    except:
        return {}


def _save_conversations(conversations: Dict) -> None:
    """Save conversation history to file."""
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONVERSATION_FILE, "w") as f:
        json.dump(conversations, f, indent=2, default=str)


def get_conversation_history(chat_id: int, limit: int = 10) -> List[Dict]:
    """
    Get conversation history for a chat.

    Returns list of messages in Claude API format:
    [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    """
    conversations = _load_conversations()
    chat_key = str(chat_id)

    if chat_key not in conversations:
        return []

    history = conversations[chat_key].get("messages", [])

    # Return last N messages
    return history[-limit:] if limit else history


def add_message(chat_id: int, role: str, content: str | List[Dict]) -> None:
    """
    Add a message to conversation history.

    Args:
        chat_id: Telegram chat ID
        role: "user" or "assistant"
        content: Message content (string or list of content blocks)
    """
    conversations = _load_conversations()
    chat_key = str(chat_id)

    if chat_key not in conversations:
        conversations[chat_key] = {
            "started_at": datetime.now().isoformat(),
            "messages": []
        }

    # Add new message
    conversations[chat_key]["messages"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })

    # Trim history if too long
    if len(conversations[chat_key]["messages"]) > MAX_HISTORY_PER_CHAT:
        conversations[chat_key]["messages"] = conversations[chat_key]["messages"][-MAX_HISTORY_PER_CHAT:]

    _save_conversations(conversations)


def clear_conversation(chat_id: int) -> None:
    """Clear conversation history for a chat."""
    conversations = _load_conversations()
    chat_key = str(chat_id)

    if chat_key in conversations:
        del conversations[chat_key]
        _save_conversations(conversations)


def get_all_active_chats() -> List[int]:
    """Get list of all chat IDs with conversation history."""
    conversations = _load_conversations()
    return [int(chat_id) for chat_id in conversations.keys()]
