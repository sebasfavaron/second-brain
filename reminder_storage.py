"""Reminder storage and trigger logic."""
import json
import uuid
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional, List, Dict

from config import REMINDERS_FILE, DEFAULT_REMINDER_HOUR


def ensure_reminders_file():
    """Create reminders file if it doesn't exist."""
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not REMINDERS_FILE.exists():
        with REMINDERS_FILE.open('w', encoding='utf-8') as f:
            json.dump([], f)


def load_reminders() -> List[Dict]:
    """Load all reminders from storage."""
    ensure_reminders_file()

    with REMINDERS_FILE.open('r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_reminders(reminders: List[Dict]):
    """Save reminders to storage."""
    ensure_reminders_file()

    with REMINDERS_FILE.open('w', encoding='utf-8') as f:
        json.dump(reminders, f, indent=2)


def create_reminder(
    content: str,
    trigger_time: Optional[datetime] = None,
    repeat: str = "none",
    reference_entry_id: Optional[str] = None,
    journal_date: Optional[date] = None
) -> Dict:
    """
    Create a new reminder.

    Args:
        content: The reminder message
        trigger_time: When to trigger (defaults to tomorrow at DEFAULT_REMINDER_HOUR)
        repeat: Repeat pattern - "none", "daily", "weekly", "monthly"
        reference_entry_id: Optional linked entry ID from brain
        journal_date: Optional linked journal date

    Returns:
        The created reminder dict
    """
    if trigger_time is None:
        # Default to tomorrow at 9 AM
        tomorrow = datetime.now() + timedelta(days=1)
        trigger_time = tomorrow.replace(
            hour=DEFAULT_REMINDER_HOUR,
            minute=0,
            second=0,
            microsecond=0
        )

    reminder = {
        "id": str(uuid.uuid4()),
        "content": content,
        "trigger_time": trigger_time.isoformat(),
        "repeat": repeat,
        "status": "pending",
        "reference_entry_id": reference_entry_id,
        "journal_date": journal_date.isoformat() if journal_date else None,
        "created_at": datetime.now().isoformat()
    }

    reminders = load_reminders()
    reminders.append(reminder)
    save_reminders(reminders)

    return reminder


def list_reminders(status: Optional[str] = None) -> List[Dict]:
    """
    List reminders, optionally filtered by status.

    Args:
        status: Optional status filter - "pending", "triggered", "completed"

    Returns:
        List of reminders
    """
    reminders = load_reminders()

    if status:
        reminders = [r for r in reminders if r.get("status") == status]

    # Sort by trigger_time
    reminders.sort(key=lambda r: r.get("trigger_time", ""))

    return reminders


def get_reminder(reminder_id: str) -> Optional[Dict]:
    """Get a specific reminder by ID."""
    reminders = load_reminders()

    for reminder in reminders:
        if reminder.get("id") == reminder_id:
            return reminder

    return None


def update_reminder_status(reminder_id: str, new_status: str) -> bool:
    """
    Update a reminder's status.

    Args:
        reminder_id: The reminder ID
        new_status: New status - "pending", "triggered", "completed"

    Returns:
        True if successful, False if reminder not found
    """
    reminders = load_reminders()

    for reminder in reminders:
        if reminder.get("id") == reminder_id:
            reminder["status"] = new_status
            reminder["updated_at"] = datetime.now().isoformat()

            # If completed, mark completion time
            if new_status == "completed":
                reminder["completed_at"] = datetime.now().isoformat()

            save_reminders(reminders)
            return True

    return False


def delete_reminder(reminder_id: str) -> bool:
    """Delete a reminder."""
    reminders = load_reminders()
    original_count = len(reminders)

    reminders = [r for r in reminders if r.get("id") != reminder_id]

    if len(reminders) < original_count:
        save_reminders(reminders)
        return True

    return False


def get_triggered_reminders() -> List[Dict]:
    """
    Get all reminders that should be triggered now.

    Returns:
        List of reminders that have reached their trigger time and are pending
    """
    reminders = load_reminders()
    now = datetime.now()

    triggered = []

    for reminder in reminders:
        if reminder.get("status") != "pending":
            continue

        trigger_time_str = reminder.get("trigger_time")
        if not trigger_time_str:
            continue

        try:
            trigger_time = datetime.fromisoformat(trigger_time_str)

            if trigger_time <= now:
                triggered.append(reminder)
        except (ValueError, TypeError):
            pass

    return triggered


def process_triggered_reminders() -> List[Dict]:
    """
    Process all triggered reminders.
    - Updates status to "triggered"
    - Handles repeat reminders by creating new ones

    Returns:
        List of triggered reminders to notify about
    """
    triggered = get_triggered_reminders()
    reminders_to_notify = []

    for reminder in triggered:
        # Update status to triggered
        update_reminder_status(reminder["id"], "triggered")

        reminders_to_notify.append(reminder)

        # Handle repeat reminders
        repeat = reminder.get("repeat", "none")
        if repeat != "none":
            trigger_time = datetime.fromisoformat(reminder["trigger_time"])

            # Calculate next trigger time
            if repeat == "daily":
                next_trigger = trigger_time + timedelta(days=1)
            elif repeat == "weekly":
                next_trigger = trigger_time + timedelta(weeks=1)
            elif repeat == "monthly":
                # Simple monthly - same day next month
                next_month = trigger_time.month + 1
                next_year = trigger_time.year
                if next_month > 12:
                    next_month = 1
                    next_year += 1

                try:
                    next_trigger = trigger_time.replace(year=next_year, month=next_month)
                except ValueError:
                    # Handle day overflow (e.g., Jan 31 -> Feb 31)
                    # Use last day of month
                    next_trigger = trigger_time.replace(year=next_year, month=next_month, day=1)
                    next_trigger = next_trigger.replace(day=1) + timedelta(days=32)
                    next_trigger = next_trigger.replace(day=1) - timedelta(days=1)
            else:
                continue

            # Create new reminder for next occurrence
            create_reminder(
                content=reminder["content"],
                trigger_time=next_trigger,
                repeat=repeat,
                reference_entry_id=reminder.get("reference_entry_id"),
                journal_date=None  # Don't link to same journal date
            )

    return reminders_to_notify


def get_upcoming_reminders(days: int = 7) -> List[Dict]:
    """
    Get reminders due in the next N days.

    Args:
        days: Number of days to look ahead

    Returns:
        List of upcoming reminders
    """
    reminders = load_reminders()
    now = datetime.now()
    future = now + timedelta(days=days)

    upcoming = []

    for reminder in reminders:
        if reminder.get("status") != "pending":
            continue

        trigger_time_str = reminder.get("trigger_time")
        if not trigger_time_str:
            continue

        try:
            trigger_time = datetime.fromisoformat(trigger_time_str)

            if now <= trigger_time <= future:
                upcoming.append(reminder)
        except (ValueError, TypeError):
            pass

    # Sort by trigger time
    upcoming.sort(key=lambda r: r["trigger_time"])

    return upcoming


def complete_reminder(reminder_id: str) -> bool:
    """Mark a reminder as completed."""
    return update_reminder_status(reminder_id, "completed")


def add_completion_note(reminder_id: str, note: str, auto_completed: bool = False) -> bool:
    """
    Add a completion note to a reminder and mark it completed.

    Args:
        reminder_id: The reminder ID
        note: Why the reminder was completed (e.g., "Diary entry confirmed task done")
        auto_completed: Whether this was auto-completed by the system

    Returns:
        True if successful, False if reminder not found
    """
    reminders = load_reminders()

    for reminder in reminders:
        if reminder.get("id") == reminder_id:
            reminder["status"] = "completed"
            reminder["completed_at"] = datetime.now().isoformat()
            reminder["updated_at"] = datetime.now().isoformat()
            reminder["completion_note"] = note
            reminder["auto_completed"] = auto_completed
            save_reminders(reminders)
            return True

    return False
