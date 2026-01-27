"""
Tool definitions and implementations for the agentic bot.

These tools give Claude direct access to the knowledge base.
"""
import os
import shutil
import subprocess
from typing import List, Dict, Optional
from datetime import datetime, date, timedelta
from pathlib import Path
from storage import (
    get_all_entries,
    create_entry as storage_create_entry,
    move_entry as storage_move_entry,
    delete_entry as storage_delete_entry,
    get_entry_by_id,
    log_audit,
    add_journal_ref_to_entry,
)
from config import (
    BASE_DIR,
    CATEGORIES,
    CONFIDENCE_THRESHOLD,
    JOURNAL_AUDIO_DIR,
    DEFAULT_REMINDER_HOUR,
    LOG_FILE,
)
import journal_storage
import reminder_storage
import skills_manager


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
    },
    {
        "name": "write_journal",
        "description": "Write a diary/journal entry. Use for emotional, reflective, or daily log content. Automatically stores in today's journal (or specified date).",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The journal entry content"
                },
                "timestamp": {
                    "type": "string",
                    "description": "Optional ISO timestamp (defaults to now)",
                    "format": "date-time"
                },
                "linked_entries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of entry IDs to link to this journal entry"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "read_journal",
        "description": "Read a journal entry for a specific date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format (defaults to today)",
                    "format": "date"
                }
            },
            "required": []
        }
    },
    {
        "name": "search_journal",
        "description": "Search journal entries for keywords or phrases. Searches across all journal entries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "date_from": {
                    "type": "string",
                    "description": "Optional start date (YYYY-MM-DD)",
                    "format": "date"
                },
                "date_to": {
                    "type": "string",
                    "description": "Optional end date (YYYY-MM-DD)",
                    "format": "date"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_reminder",
        "description": "Create a reminder for a future time. Use when user asks to be reminded about something. Can be recurring (daily, weekly, monthly).",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Reminder message"
                },
                "trigger_time": {
                    "type": "string",
                    "description": "ISO timestamp when to trigger (defaults to tomorrow 9 AM)",
                    "format": "date-time"
                },
                "repeat": {
                    "type": "string",
                    "enum": ["none", "daily", "weekly", "monthly"],
                    "description": "Repeat pattern (default: none)"
                },
                "reference_entry_id": {
                    "type": "string",
                    "description": "Optional entry ID to link this reminder to"
                },
                "journal_date": {
                    "type": "string",
                    "description": "Optional journal date to link (YYYY-MM-DD)",
                    "format": "date"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "list_reminders",
        "description": "List reminders, optionally filtered by status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "triggered", "completed"],
                    "description": "Optional status filter"
                }
            },
            "required": []
        }
    },
    {
        "name": "complete_reminder",
        "description": "Mark a reminder as completed. Use when the user says they've done something or asks to complete/dismiss a reminder.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reminder_id": {
                    "type": "string",
                    "description": "UUID of the reminder to complete"
                },
                "note": {
                    "type": "string",
                    "description": "Optional note about why it was completed"
                }
            },
            "required": ["reminder_id"]
        }
    },
    {
        "name": "link_entries",
        "description": "Create a cross-reference link between a journal entry and a knowledge entry. Use for HYBRID messages that have both diary content and extractable facts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "journal_date": {
                    "type": "string",
                    "description": "Journal date (YYYY-MM-DD)",
                    "format": "date"
                },
                "entry_id": {
                    "type": "string",
                    "description": "Knowledge entry UUID to link"
                },
                "link_type": {
                    "type": "string",
                    "description": "Type of link (e.g., 'extracted_from', 'related_to')"
                }
            },
            "required": ["journal_date", "entry_id", "link_type"]
        }
    },
    {
        "name": "get_audio_file",
        "description": "Retrieve path to a voice recording for a specific date and index.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date of the recording (YYYY-MM-DD)",
                    "format": "date"
                },
                "index": {
                    "type": "integer",
                    "description": "Recording index for that date (0-based)"
                }
            },
            "required": ["date", "index"]
        }
    },
    {
        "name": "list_files",
        "description": "List files in the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Repository-relative path to list (default: .)"
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max depth to traverse (default: 3)"
                },
                "include_hidden": {
                    "type": "boolean",
                    "description": "Include hidden files (default: false)"
                },
                "max_entries": {
                    "type": "integer",
                    "description": "Max number of entries to return (default: 200)"
                }
            },
            "required": []
        }
    },
    {
        "name": "read_file",
        "description": "Read a text file from the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Repository-relative path to read"
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "Max bytes to read (default: 200000)"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write a text file to the repository (overwrites).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Repository-relative path to write"
                },
                "content": {
                    "type": "string",
                    "description": "File content"
                },
                "create_dirs": {
                    "type": "boolean",
                    "description": "Create parent directories if missing (default: true)"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "search_repo",
        "description": "Search the repository for a text pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (literal string)"
                },
                "path": {
                    "type": "string",
                    "description": "Repository-relative path to search (default: .)"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return (default: 20)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "git_status",
        "description": "Get git status for the repository.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "git_diff",
        "description": "Get git diff for the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "staged": {
                    "type": "boolean",
                    "description": "Show staged diff (default: false)"
                },
                "path": {
                    "type": "string",
                    "description": "Optional path to limit diff"
                }
            },
            "required": []
        }
    },
    {
        "name": "publish_changes",
        "description": "Stage all changes, commit, and push to the git remote.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message (default: 'Update via Telegram admin')"
                }
            },
            "required": []
        }
    },
    {
        "name": "restart_service",
        "description": "Restart the Telegram bot service.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Systemd service name (default: second-brain-bot.service)"
                }
            },
            "required": []
        }
    },
    {
        "name": "tail_log",
        "description": "Return the last N lines of the bot log.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lines": {
                    "type": "integer",
                    "description": "Number of lines (default: 50)"
                }
            },
            "required": []
        }
    },
    {
        "name": "list_skills",
        "description": "List installed skills.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "install_skill",
        "description": "Install a skill from a git repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name"},
                "repo_url": {"type": "string", "description": "Git repository URL"}
            },
            "required": ["name", "repo_url"]
        }
    },
    {
        "name": "enable_skill",
        "description": "Enable a skill.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Skill name"}},
            "required": ["name"]
        }
    },
    {
        "name": "disable_skill",
        "description": "Disable a skill.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Skill name"}},
            "required": ["name"]
        }
    },
    {
        "name": "remove_skill",
        "description": "Remove a skill from the repository.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Skill name"}},
            "required": ["name"]
        }
    }
]


def _resolve_repo_path(path_str: str) -> Path:
    base = BASE_DIR.resolve()
    path = Path(path_str)
    if not path.is_absolute():
        path = (base / path).resolve()
    else:
        path = path.resolve()
    if not str(path).startswith(str(base)):
        raise ValueError("Path outside repository")
    return path


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
    """Search for entries matching query using semantic search + keyword fallback."""
    if categories is None:
        categories = CATEGORIES + ["inbox"]

    try:
        # Try semantic search first
        from embeddings import semantic_search, get_embedding_stats

        stats = get_embedding_stats()
        use_semantic = stats.get("total", 0) > 0

        semantic_results = []
        if use_semantic:
            # Get semantic matches with similarity scores
            semantic_matches = semantic_search(query, categories, limit * 2)

            # Fetch full entries for semantic matches
            for entry_id, similarity in semantic_matches:
                result = get_entry_by_id(entry_id)
                if result:
                    entry, category = result
                    entry_with_meta = entry.copy()
                    entry_with_meta["_category"] = category
                    entry_with_meta["_similarity"] = similarity
                    entry_with_meta["_search_method"] = "semantic"
                    semantic_results.append(entry_with_meta)

        # Also do keyword search for completeness
        query_lower = query.lower()
        keyword_matches = []

        for category in categories:
            entries = get_all_entries(category)
            for entry in entries:
                msg = entry.get("raw_message", "").lower()
                if query_lower in msg:
                    # Skip if already in semantic results
                    entry_id = entry.get("id")
                    if not any(r.get("id") == entry_id for r in semantic_results):
                        entry_with_cat = entry.copy()
                        entry_with_cat["_category"] = category
                        entry_with_cat["_search_method"] = "keyword"
                        keyword_matches.append(entry_with_cat)

        # Combine results: semantic first (sorted by similarity), then keyword (by date)
        keyword_matches.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        all_matches = semantic_results + keyword_matches

        return {
            "success": True,
            "query": query,
            "count": len(all_matches),
            "entries": all_matches[:limit],
            "search_method": "semantic+keyword" if use_semantic else "keyword",
            "embedding_stats": stats if use_semantic else None
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


def write_journal(content: str, timestamp: Optional[str] = None, linked_entries: Optional[List[str]] = None) -> Dict:
    """Write a journal entry, then check pending reminders for auto-completion."""
    try:
        # Parse timestamp if provided
        dt = None
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                return {
                    "success": False,
                    "error": "Invalid timestamp format"
                }

        result = journal_storage.write_journal(content, dt, linked_entries)

        # After writing, review diary against pending reminders
        try:
            from diary_reminder_bridge import review_diary_against_reminders
            pending = reminder_storage.list_reminders(status="pending")
            if pending:
                bridge_result = review_diary_against_reminders(content, pending)

                # Auto-complete confirmed reminders
                auto_completed = []
                for item in bridge_result.get("auto_complete", []):
                    rid = item.get("reminder_id")
                    reason = item.get("reason", "Confirmed by diary entry")
                    if rid and reminder_storage.add_completion_note(rid, reason, auto_completed=True):
                        auto_completed.append(item)

                if auto_completed:
                    result["auto_completed_reminders"] = auto_completed
                relevant = bridge_result.get("relevant_mentions", [])
                if relevant:
                    result["relevant_reminders"] = relevant
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Bridge review failed: {e}")

        return result

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def read_journal(date_str: Optional[str] = None) -> Dict:
    """Read a journal entry for a date."""
    try:
        # Parse date if provided
        target_date = None
        if date_str:
            try:
                target_date = date.fromisoformat(date_str)
            except ValueError:
                return {
                    "success": False,
                    "error": "Invalid date format. Use YYYY-MM-DD"
                }

        result = journal_storage.read_journal(target_date)
        result["success"] = True
        return result

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def search_journal(query: str, date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict:
    """Search journal entries."""
    try:
        # Parse dates if provided
        from_date = None
        to_date = None

        if date_from:
            try:
                from_date = date.fromisoformat(date_from)
            except ValueError:
                return {
                    "success": False,
                    "error": "Invalid date_from format. Use YYYY-MM-DD"
                }

        if date_to:
            try:
                to_date = date.fromisoformat(date_to)
            except ValueError:
                return {
                    "success": False,
                    "error": "Invalid date_to format. Use YYYY-MM-DD"
                }

        matches = journal_storage.search_journal(query, from_date, to_date)

        return {
            "success": True,
            "query": query,
            "count": len(matches),
            "matches": matches
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def create_reminder(
    content: str,
    trigger_time: Optional[str] = None,
    repeat: str = "none",
    reference_entry_id: Optional[str] = None,
    journal_date: Optional[str] = None
) -> Dict:
    """Create a reminder."""
    try:
        # Parse trigger_time if provided
        dt = None
        if trigger_time:
            try:
                dt = datetime.fromisoformat(trigger_time.replace('Z', '+00:00'))
            except ValueError:
                return {
                    "success": False,
                    "error": "Invalid trigger_time format"
                }

        # Parse journal_date if provided
        j_date = None
        if journal_date:
            try:
                j_date = date.fromisoformat(journal_date)
            except ValueError:
                return {
                    "success": False,
                    "error": "Invalid journal_date format"
                }

        reminder = reminder_storage.create_reminder(
            content=content,
            trigger_time=dt,
            repeat=repeat,
            reference_entry_id=reference_entry_id,
            journal_date=j_date
        )

        return {
            "success": True,
            "reminder": reminder
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def list_reminders(status: Optional[str] = None) -> Dict:
    """List reminders."""
    try:
        reminders = reminder_storage.list_reminders(status)

        return {
            "success": True,
            "count": len(reminders),
            "reminders": reminders
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def complete_reminder_tool(reminder_id: str, note: Optional[str] = None) -> Dict:
    """Mark a reminder as completed."""
    try:
        if note:
            success = reminder_storage.add_completion_note(reminder_id, note)
        else:
            success = reminder_storage.complete_reminder(reminder_id)

        if success:
            return {
                "success": True,
                "reminder_id": reminder_id,
                "note": note
            }
        else:
            return {
                "success": False,
                "error": "Reminder not found"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def link_entries(journal_date: str, entry_id: str, link_type: str) -> Dict:
    """Link a journal entry to a knowledge entry."""
    try:
        # Parse journal_date
        try:
            j_date = date.fromisoformat(journal_date)
        except ValueError:
            return {
                "success": False,
                "error": "Invalid journal_date format. Use YYYY-MM-DD"
            }

        # Add link to journal file
        journal_linked = journal_storage.add_linked_entry_to_journal(j_date, entry_id)

        if not journal_linked:
            return {
                "success": False,
                "error": "Journal entry not found or failed to update"
            }

        # Add journal ref to knowledge entry
        entry_linked = add_journal_ref_to_entry(entry_id, journal_date, link_type)

        if not entry_linked:
            return {
                "success": False,
                "error": "Knowledge entry not found or failed to update"
            }

        return {
            "success": True,
            "journal_date": journal_date,
            "entry_id": entry_id,
            "link_type": link_type
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def get_audio_file(date_str: str, index: int) -> Dict:
    """Get path to audio file for a date."""
    try:
        # Parse date
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            return {
                "success": False,
                "error": "Invalid date format. Use YYYY-MM-DD"
            }

        # Build audio file path
        year = str(target_date.year)
        month = f"{target_date.month:02d}"

        audio_dir = JOURNAL_AUDIO_DIR / year / month
        if not audio_dir.exists():
            return {
                "success": False,
                "error": "No audio files for this date"
            }

        # List audio files for this date
        day = f"{target_date.day:02d}"
        audio_files = sorted(audio_dir.glob(f"{day}_*.ogg"))

        if index >= len(audio_files):
            return {
                "success": False,
                "error": f"Audio index {index} not found. Only {len(audio_files)} files exist."
            }

        return {
            "success": True,
            "date": date_str,
            "index": index,
            "file_path": str(audio_files[index])
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def list_files(path: str = ".", max_depth: int = 3, include_hidden: bool = False, max_entries: int = 200) -> Dict:
    """List files in the repository."""
    try:
        root = _resolve_repo_path(path)
        if not root.exists():
            return {"success": False, "error": "Path not found"}

        results: List[str] = []
        base_parts = len(root.parts)

        for dirpath, dirnames, filenames in os.walk(root):
            current_depth = len(Path(dirpath).parts) - base_parts
            if current_depth >= max_depth:
                dirnames[:] = []

            if not include_hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                filenames = [f for f in filenames if not f.startswith(".")]

            for filename in filenames:
                rel = Path(dirpath) / filename
                try:
                    rel_path = rel.resolve().relative_to(BASE_DIR.resolve())
                except Exception:
                    rel_path = rel
                results.append(str(rel_path))
                if len(results) >= max_entries:
                    return {
                        "success": True,
                        "path": str(root),
                        "count": len(results),
                        "truncated": True,
                        "files": results,
                    }

        return {
            "success": True,
            "path": str(root),
            "count": len(results),
            "files": results,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_file(path: str, max_bytes: int = 200000) -> Dict:
    """Read a text file from the repository."""
    try:
        file_path = _resolve_repo_path(path)
        if not file_path.exists() or not file_path.is_file():
            return {"success": False, "error": "File not found"}

        content = file_path.read_text(encoding="utf-8")
        if len(content.encode("utf-8")) > max_bytes:
            truncated = content.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
            return {"success": True, "path": str(file_path), "truncated": True, "content": truncated}

        return {"success": True, "path": str(file_path), "content": content}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path: str, content: str, create_dirs: bool = True) -> Dict:
    """Write a text file to the repository."""
    try:
        file_path = _resolve_repo_path(path)
        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(file_path), "bytes": len(content.encode("utf-8"))}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_repo(query: str, path: str = ".", max_results: int = 20) -> Dict:
    """Search the repository for a query."""
    try:
        root = _resolve_repo_path(path)
        if not root.exists():
            return {"success": False, "error": "Path not found"}

        rg = shutil.which("rg")
        matches: List[Dict] = []

        if rg:
            result = subprocess.run(
                [rg, "-n", "--max-count", str(max_results), query, str(root)],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode not in (0, 1):
                return {"success": False, "error": result.stderr.strip() or "rg failed"}

            for line in result.stdout.splitlines():
                parts = line.split(":", 2)
                if len(parts) < 3:
                    continue
                file_path, line_no, text = parts
                try:
                    rel_path = Path(file_path).resolve().relative_to(BASE_DIR.resolve())
                except Exception:
                    rel_path = Path(file_path)
                matches.append({"file": str(rel_path), "line": int(line_no), "text": text})
                if len(matches) >= max_results:
                    break
        else:
            for file_path in root.rglob("*"):
                if len(matches) >= max_results:
                    break
                if not file_path.is_file():
                    continue
                try:
                    content = file_path.read_text(encoding="utf-8")
                except Exception:
                    continue
                for i, line in enumerate(content.splitlines(), start=1):
                    if query in line:
                        try:
                            rel_path = file_path.resolve().relative_to(BASE_DIR.resolve())
                        except Exception:
                            rel_path = file_path
                        matches.append({"file": str(rel_path), "line": i, "text": line})
                        if len(matches) >= max_results:
                            break

        return {"success": True, "query": query, "count": len(matches), "matches": matches}
    except Exception as e:
        return {"success": False, "error": str(e)}


def git_status() -> Dict:
    """Return git status output."""
    try:
        result = subprocess.run(
            ["git", "status", "-sb"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
        return {"success": result.returncode == 0, "output": result.stdout.strip(), "error": result.stderr.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def git_diff(staged: bool = False, path: Optional[str] = None) -> Dict:
    """Return git diff output."""
    try:
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        if path:
            cmd.extend(["--", path])
        result = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
        return {"success": result.returncode == 0, "output": result.stdout, "error": result.stderr.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def publish_changes(message: Optional[str] = None) -> Dict:
    """Stage, commit, and push changes."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=str(BASE_DIR), check=False)

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
        if not status.stdout.strip():
            return {"success": True, "status": "clean", "message": "No changes to commit"}

        commit_message = message or "Update via Telegram admin"
        commit = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
        if commit.returncode != 0:
            return {"success": False, "error": commit.stderr.strip() or commit.stdout.strip()}

        push = subprocess.run(
            ["git", "push"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=False,
        )
        if push.returncode != 0:
            return {"success": False, "error": push.stderr.strip() or push.stdout.strip()}

        return {"success": True, "commit": commit.stdout.strip(), "push": push.stdout.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def restart_service(service_name: str = "second-brain-bot.service") -> Dict:
    """Restart systemd service."""
    try:
        cmds = [
            ["systemctl", "restart", service_name],
            ["sudo", "-n", "systemctl", "restart", service_name],
        ]
        last_error = ""
        for cmd in cmds:
            result = subprocess.run(
                cmd,
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return {"success": True, "service": service_name, "used": " ".join(cmd)}
            last_error = result.stderr.strip() or result.stdout.strip()

        return {"success": False, "error": last_error or "Failed to restart service"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def tail_log(lines: int = 50) -> Dict:
    """Tail the bot log file."""
    try:
        if not LOG_FILE.exists():
            return {"success": False, "error": "Log file not found"}
        content = LOG_FILE.read_text(encoding="utf-8", errors="ignore")
        all_lines = content.splitlines()
        tail_lines = all_lines[-lines:] if lines > 0 else all_lines
        return {"success": True, "lines": len(tail_lines), "content": "\n".join(tail_lines)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_skills_tool() -> Dict:
    """List installed skills."""
    try:
        skills = skills_manager.list_skills()
        return {"success": True, "count": len(skills), "skills": skills}
    except Exception as e:
        return {"success": False, "error": str(e)}


def install_skill(name: str, repo_url: str) -> Dict:
    """Install a skill from git repo."""
    return skills_manager.install_skill_from_git(name, repo_url)


def enable_skill(name: str) -> Dict:
    """Enable a skill."""
    return skills_manager.enable_skill(name)


def disable_skill(name: str) -> Dict:
    """Disable a skill."""
    return skills_manager.disable_skill(name)


def remove_skill(name: str) -> Dict:
    """Remove a skill."""
    return skills_manager.remove_skill(name)


# Tool execution dispatcher
def execute_tool(tool_name: str, tool_input: Dict) -> Dict:
    """Execute a tool by name with given input."""
    # Knowledge base tools
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
    # Journal tools
    elif tool_name == "write_journal":
        return write_journal(**tool_input)
    elif tool_name == "read_journal":
        # Handle optional date parameter
        date_str = tool_input.get("date")
        return read_journal(date_str)
    elif tool_name == "search_journal":
        return search_journal(**tool_input)
    # Reminder tools
    elif tool_name == "create_reminder":
        return create_reminder(**tool_input)
    elif tool_name == "list_reminders":
        # Handle optional status parameter
        status = tool_input.get("status")
        return list_reminders(status)
    elif tool_name == "complete_reminder":
        return complete_reminder_tool(
            reminder_id=tool_input["reminder_id"],
            note=tool_input.get("note")
        )
    # Cross-reference tools
    elif tool_name == "link_entries":
        return link_entries(**tool_input)
    elif tool_name == "get_audio_file":
        return get_audio_file(**tool_input)
    # Repo/admin tools
    elif tool_name == "list_files":
        return list_files(**tool_input)
    elif tool_name == "read_file":
        return read_file(**tool_input)
    elif tool_name == "write_file":
        return write_file(**tool_input)
    elif tool_name == "search_repo":
        return search_repo(**tool_input)
    elif tool_name == "git_status":
        return git_status()
    elif tool_name == "git_diff":
        return git_diff(**tool_input)
    elif tool_name == "publish_changes":
        return publish_changes(**tool_input)
    elif tool_name == "restart_service":
        return restart_service(**tool_input)
    elif tool_name == "tail_log":
        return tail_log(**tool_input)
    elif tool_name == "list_skills":
        return list_skills_tool()
    elif tool_name == "install_skill":
        return install_skill(**tool_input)
    elif tool_name == "enable_skill":
        return enable_skill(**tool_input)
    elif tool_name == "disable_skill":
        return disable_skill(**tool_input)
    elif tool_name == "remove_skill":
        return remove_skill(**tool_input)
    else:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}"
        }
