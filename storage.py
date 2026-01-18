"""JSON storage operations for Second Brain."""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import STORAGE_FILES, AUDIT_FILE, STATE_FILE, CORRECTIONS_QUEUE, BRAIN_DIR


def _ensure_file(path: Path, default: list | dict = None) -> None:
    """Ensure JSON file exists with default content."""
    if default is None:
        default = []
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(default, f)


def _load_json(path: Path) -> list | dict:
    """Load JSON file, creating it if needed."""
    _ensure_file(path, [])
    with open(path) as f:
        return json.load(f)


def _save_json(path: Path, data: list | dict) -> None:
    """Save data to JSON file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def init_storage() -> None:
    """Initialize all storage files."""
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    for path in STORAGE_FILES.values():
        _ensure_file(path, [])
    _ensure_file(AUDIT_FILE, [])
    _ensure_file(STATE_FILE, {})
    _ensure_file(CORRECTIONS_QUEUE, [])


# --- Entry CRUD ---

def create_entry(
    category: str,
    raw_message: str,
    confidence: float,
    chat_id: int = None,
    message_id: int = None,
) -> dict:
    """Create a new entry in the specified category."""
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "raw_message": raw_message,
        "category": category,
        "confidence": confidence,
        "processed_at": datetime.now().isoformat(),
        "chat_id": chat_id,
        "message_id": message_id,
        "corrected_from": None,
    }

    path = STORAGE_FILES.get(category)
    if not path:
        raise ValueError(f"Unknown category: {category}")

    entries = _load_json(path)
    entries.append(entry)
    _save_json(path, entries)

    return entry


def get_entry_by_id(entry_id: str) -> Optional[tuple[dict, str]]:
    """Find entry by ID across all categories. Returns (entry, category)."""
    for category, path in STORAGE_FILES.items():
        entries = _load_json(path)
        for entry in entries:
            if entry.get("id") == entry_id:
                return entry, category
    return None


def get_entry_by_message_id(chat_id: int, message_id: int) -> Optional[tuple[dict, str]]:
    """Find entry by Telegram message ID. Returns (entry, category)."""
    for category, path in STORAGE_FILES.items():
        entries = _load_json(path)
        for entry in entries:
            if entry.get("chat_id") == chat_id and entry.get("message_id") == message_id:
                return entry, category
    return None


def move_entry(entry_id: str, from_category: str, to_category: str, additional_context: str = None) -> Optional[dict]:
    """Move entry from one category to another, optionally adding clarifying context."""
    # Load source
    from_path = STORAGE_FILES.get(from_category)
    to_path = STORAGE_FILES.get(to_category)

    if not from_path or not to_path:
        return None

    from_entries = _load_json(from_path)
    to_entries = _load_json(to_path)

    # Find and remove from source
    entry = None
    for i, e in enumerate(from_entries):
        if e.get("id") == entry_id:
            entry = from_entries.pop(i)
            break

    if not entry:
        return None

    # Update entry
    entry["corrected_from"] = from_category
    entry["category"] = to_category
    entry["processed_at"] = datetime.now().isoformat()

    # Combine original message with clarifying context if provided
    if additional_context and additional_context.strip():
        original_msg = entry.get("raw_message", "")
        entry["raw_message"] = f"{original_msg}\n[Clarification: {additional_context.strip()}]"

    # Add to destination
    to_entries.append(entry)

    # Save both
    _save_json(from_path, from_entries)
    _save_json(to_path, to_entries)

    return entry


def delete_entry(entry_id: str, category: str) -> bool:
    """Delete entry from category."""
    path = STORAGE_FILES.get(category)
    if not path:
        return False

    entries = _load_json(path)
    for i, e in enumerate(entries):
        if e.get("id") == entry_id:
            entries.pop(i)
            _save_json(path, entries)
            return True
    return False


def get_all_entries(category: str) -> list:
    """Get all entries in a category."""
    path = STORAGE_FILES.get(category)
    if not path:
        return []
    return _load_json(path)


def get_recent_entries(category: str, limit: int = 10) -> list:
    """Get most recent entries in a category."""
    entries = get_all_entries(category)
    return sorted(entries, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]


# --- Audit Logging ---

def log_audit(action: str, item_id: str, category: str, confidence: float = None, details: dict = None) -> None:
    """Log an audit event."""
    event = {
        "ts": datetime.now().isoformat(),
        "action": action,
        "item_id": item_id,
        "category": category,
    }
    if confidence is not None:
        event["confidence"] = confidence
    if details:
        event.update(details)

    events = _load_json(AUDIT_FILE)
    events.append(event)
    _save_json(AUDIT_FILE, events)


def get_audit_log(limit: int = 50) -> list:
    """Get recent audit events."""
    events = _load_json(AUDIT_FILE)
    return sorted(events, key=lambda x: x.get("ts", ""), reverse=True)[:limit]


# --- Corrections Queue ---

def add_correction(entry_id: str, from_category: str, to_category: str, chat_id: int = None) -> dict:
    """Add a correction to the queue."""
    correction = {
        "id": str(uuid.uuid4()),
        "entry_id": entry_id,
        "from_category": from_category,
        "to_category": to_category,
        "requested_at": datetime.now().isoformat(),
        "chat_id": chat_id,
        "processed": False,
    }

    queue = _load_json(CORRECTIONS_QUEUE)
    queue.append(correction)
    _save_json(CORRECTIONS_QUEUE, queue)

    return correction


def get_pending_corrections() -> list:
    """Get unprocessed corrections."""
    queue = _load_json(CORRECTIONS_QUEUE)
    return [c for c in queue if not c.get("processed")]


def mark_correction_processed(correction_id: str) -> bool:
    """Mark a correction as processed."""
    queue = _load_json(CORRECTIONS_QUEUE)
    for c in queue:
        if c.get("id") == correction_id:
            c["processed"] = True
            c["processed_at"] = datetime.now().isoformat()
            _save_json(CORRECTIONS_QUEUE, queue)
            return True
    return False


# --- State Management ---

def get_state(key: str, default=None):
    """Get a state value."""
    state = _load_json(STATE_FILE)
    if isinstance(state, list):
        state = {}
        _save_json(STATE_FILE, state)
    return state.get(key, default)


def set_state(key: str, value) -> None:
    """Set a state value."""
    state = _load_json(STATE_FILE)
    if isinstance(state, list):
        state = {}
    state[key] = value
    _save_json(STATE_FILE, state)
