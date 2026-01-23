"""
Tool definitions and implementations for the agentic bot.

These tools give Claude direct access to the knowledge base.
"""
from typing import List, Dict, Optional
from storage import (
    get_all_entries,
    create_entry as storage_create_entry,
    move_entry as storage_move_entry,
    delete_entry as storage_delete_entry,
    get_entry_by_id,
    log_audit,
)
from config import CATEGORIES, CONFIDENCE_THRESHOLD


# Tool definitions for Claude API
TOOL_DEFINITIONS = [
    {
        "name": "list_entries",
        "description": "List all entries in a specific category (people, projects, ideas, admin, inbox). Returns the actual stored data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["people", "projects", "ideas", "admin", "inbox"],
                    "description": "Category to list entries from"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of entries to return (default: all)",
                    "default": None
                }
            },
            "required": ["category"]
        }
    },
    {
        "name": "search_entries",
        "description": "Search for entries across one or more categories using keywords. Returns matching entries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (keywords to find in entry messages)"
                },
                "categories": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["people", "projects", "ideas", "admin", "inbox"]
                    },
                    "description": "Categories to search in (default: all)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_entry",
        "description": "Get details of a specific entry by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_id": {
                    "type": "string",
                    "description": "UUID of the entry to retrieve"
                }
            },
            "required": ["entry_id"]
        }
    },
    {
        "name": "create_entry",
        "description": "Store a new entry in the knowledge base. Use this when the user provides new information to save.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["people", "projects", "ideas", "admin", "inbox"],
                    "description": "Category to store the entry in"
                },
                "message": {
                    "type": "string",
                    "description": "The message/information to store"
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Confidence in the classification (0.0-1.0)"
                }
            },
            "required": ["category", "message", "confidence"]
        }
    },
    {
        "name": "move_entry",
        "description": "Move an entry from one category to another (correction).",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_id": {
                    "type": "string",
                    "description": "UUID of the entry to move"
                },
                "from_category": {
                    "type": "string",
                    "enum": ["people", "projects", "ideas", "admin", "inbox"],
                    "description": "Current category"
                },
                "to_category": {
                    "type": "string",
                    "enum": ["people", "projects", "ideas", "admin", "inbox"],
                    "description": "Target category"
                }
            },
            "required": ["entry_id", "from_category", "to_category"]
        }
    },
    {
        "name": "delete_entry",
        "description": "Delete an entry from the knowledge base.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_id": {
                    "type": "string",
                    "description": "UUID of the entry to delete"
                },
                "category": {
                    "type": "string",
                    "enum": ["people", "projects", "ideas", "admin", "inbox"],
                    "description": "Category containing the entry"
                }
            },
            "required": ["entry_id", "category"]
        }
    }
]


# Tool implementations

def list_entries(category: str, limit: Optional[int] = None) -> Dict:
    """List entries in a category."""
    try:
        entries = get_all_entries(category)

        if limit:
            entries = entries[:limit]

        return {
            "success": True,
            "category": category,
            "count": len(entries),
            "entries": entries
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def search_entries(query: str, categories: Optional[List[str]] = None, limit: int = 10) -> Dict:
    """Search for entries matching query."""
    if categories is None:
        categories = CATEGORIES + ["inbox"]

    query_lower = query.lower()
    matches = []

    try:
        for category in categories:
            entries = get_all_entries(category)
            for entry in entries:
                msg = entry.get("raw_message", "").lower()
                if query_lower in msg:
                    entry_with_cat = entry.copy()
                    entry_with_cat["_category"] = category
                    matches.append(entry_with_cat)

        # Sort by timestamp (most recent first)
        matches.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return {
            "success": True,
            "query": query,
            "count": len(matches),
            "entries": matches[:limit]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def get_entry(entry_id: str) -> Dict:
    """Get a specific entry by ID."""
    try:
        result = get_entry_by_id(entry_id)
        if result:
            entry, category = result
            return {
                "success": True,
                "entry": entry,
                "category": category
            }
        else:
            return {
                "success": False,
                "error": "Entry not found"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def create_entry(category: str, message: str, confidence: float, chat_id: int = None, message_id: int = None) -> Dict:
    """Create a new entry."""
    try:
        # Low confidence goes to inbox
        if confidence < CONFIDENCE_THRESHOLD:
            category = "inbox"

        entry = storage_create_entry(
            category=category,
            raw_message=message,
            confidence=confidence,
            chat_id=chat_id,
            message_id=message_id
        )

        log_audit("classified", entry["id"], category, confidence)

        # Enrich context for high-confidence entries
        if category != "inbox" and confidence >= CONFIDENCE_THRESHOLD:
            try:
                from context_manager import enrich_context
                enrich_context(category, entry)
            except:
                pass

        return {
            "success": True,
            "entry": entry,
            "category": category
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def move_entry(entry_id: str, from_category: str, to_category: str) -> Dict:
    """Move entry between categories."""
    try:
        moved = storage_move_entry(entry_id, from_category, to_category)
        if moved:
            log_audit("corrected", entry_id, to_category,
                     details={"from_category": from_category})
            return {
                "success": True,
                "entry": moved,
                "from_category": from_category,
                "to_category": to_category
            }
        else:
            return {
                "success": False,
                "error": "Failed to move entry"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def delete_entry(entry_id: str, category: str) -> Dict:
    """Delete an entry."""
    try:
        deleted = storage_delete_entry(entry_id, category)
        if deleted:
            log_audit("deleted", entry_id, category)
            return {
                "success": True,
                "entry_id": entry_id,
                "category": category
            }
        else:
            return {
                "success": False,
                "error": "Failed to delete entry"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# Tool execution dispatcher
def execute_tool(tool_name: str, tool_input: Dict) -> Dict:
    """Execute a tool by name with given input."""
    if tool_name == "list_entries":
        return list_entries(**tool_input)
    elif tool_name == "search_entries":
        return search_entries(**tool_input)
    elif tool_name == "get_entry":
        return get_entry(**tool_input)
    elif tool_name == "create_entry":
        return create_entry(**tool_input)
    elif tool_name == "move_entry":
        return move_entry(**tool_input)
    elif tool_name == "delete_entry":
        return delete_entry(**tool_input)
    else:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}"
        }
