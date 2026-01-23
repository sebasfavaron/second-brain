#!/usr/bin/env python3
"""
Clean up duplicate entries (those with null chat_id created by the bug).
"""
import json
from pathlib import Path

BRAIN_DIR = Path(__file__).parent / "brain"
ADMIN_FILE = BRAIN_DIR / "admin.json"

def cleanup_duplicates():
    """Remove entries with null chat_id (duplicates from the bug)."""
    with open(ADMIN_FILE) as f:
        entries = json.load(f)

    original_count = len(entries)

    # Filter out entries with null chat_id
    cleaned = [e for e in entries if e.get("chat_id") is not None]

    removed_count = original_count - len(cleaned)

    if removed_count > 0:
        with open(ADMIN_FILE, "w") as f:
            json.dump(cleaned, f, indent=2)
        print(f"Removed {removed_count} duplicate entries from admin.json")
        print(f"Total entries: {original_count} → {len(cleaned)}")
    else:
        print("No duplicates found")

if __name__ == "__main__":
    cleanup_duplicates()
