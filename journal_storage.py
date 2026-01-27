"""Journal storage operations for diary entries."""
import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict
import subprocess

from config import JOURNAL_ENTRIES_DIR, JOURNAL_INDEX


def ensure_journal_dirs():
    """Create journal directories if they don't exist."""
    JOURNAL_ENTRIES_DIR.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL_ENTRIES_DIR.mkdir(parents=True, exist_ok=True)


def get_journal_path(target_date: date) -> Path:
    """Get the path to a journal file for a specific date."""
    year = str(target_date.year)
    month = f"{target_date.month:02d}"
    day = f"{target_date.day:02d}"

    journal_file = JOURNAL_ENTRIES_DIR / year / month / f"{day}.md"
    journal_file.parent.mkdir(parents=True, exist_ok=True)

    return journal_file


def write_journal(content: str, timestamp: Optional[datetime] = None, linked_entries: Optional[List[str]] = None) -> Dict:
    """
    Write a journal entry for a specific date.

    Args:
        content: The journal entry content
        timestamp: Optional timestamp (defaults to now)
        linked_entries: Optional list of entry IDs that are linked to this journal entry

    Returns:
        Dict with journal_date, file_path, and success status
    """
    ensure_journal_dirs()

    if timestamp is None:
        timestamp = datetime.now()

    target_date = timestamp.date()
    journal_file = get_journal_path(target_date)

    # Create or append to journal file
    is_new = not journal_file.exists()

    with journal_file.open('a', encoding='utf-8') as f:
        if is_new:
            # Write front matter for new files
            f.write(f"---\n")
            f.write(f"date: {target_date.isoformat()}\n")
            if linked_entries:
                f.write(f"linked_entries:\n")
                for entry_id in linked_entries:
                    f.write(f"  - {entry_id}\n")
            f.write(f"---\n\n")
            f.write(f"# {target_date.strftime('%A, %B %d, %Y')}\n\n")

        # Write the entry with timestamp
        time_str = timestamp.strftime('%H:%M')
        f.write(f"## {time_str}\n\n")
        f.write(f"{content}\n\n")

    # Update index
    _update_index(target_date, journal_file)

    return {
        "journal_date": target_date.isoformat(),
        "file_path": str(journal_file),
        "timestamp": timestamp.isoformat(),
        "success": True
    }


def read_journal(target_date: Optional[date] = None) -> Dict:
    """
    Read a journal entry for a specific date.

    Args:
        target_date: The date to read (defaults to today)

    Returns:
        Dict with date, content, and linked_entries
    """
    if target_date is None:
        target_date = date.today()

    journal_file = get_journal_path(target_date)

    if not journal_file.exists():
        return {
            "journal_date": target_date.isoformat(),
            "content": None,
            "linked_entries": [],
            "exists": False
        }

    with journal_file.open('r', encoding='utf-8') as f:
        content = f.read()

    # Parse front matter to extract linked entries
    linked_entries = []
    if content.startswith("---\n"):
        end_front_matter = content.find("---\n", 4)
        if end_front_matter != -1:
            front_matter = content[4:end_front_matter]
            # Simple parsing of linked_entries
            if "linked_entries:" in front_matter:
                lines = front_matter.split("\n")
                in_linked = False
                for line in lines:
                    if "linked_entries:" in line:
                        in_linked = True
                    elif in_linked and line.strip().startswith("- "):
                        linked_entries.append(line.strip()[2:])
                    elif in_linked and not line.strip().startswith("- "):
                        in_linked = False

    return {
        "journal_date": target_date.isoformat(),
        "content": content,
        "linked_entries": linked_entries,
        "exists": True,
        "file_path": str(journal_file)
    }


def search_journal(query: str, date_from: Optional[date] = None, date_to: Optional[date] = None) -> List[Dict]:
    """
    Search journal entries using ripgrep.

    Args:
        query: Search query string
        date_from: Optional start date for search range
        date_to: Optional end date for search range

    Returns:
        List of dicts with date, file_path, and matching lines
    """
    ensure_journal_dirs()

    if not JOURNAL_ENTRIES_DIR.exists():
        return []

    # Build ripgrep command
    cmd = [
        "rg",
        "--case-insensitive",
        "--line-number",
        "--context", "2",
        query,
        str(JOURNAL_ENTRIES_DIR)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode not in [0, 1]:  # 0 = found, 1 = not found
            return []

        if not result.stdout:
            return []

        # Parse ripgrep output
        matches = []
        current_file = None
        current_match = None

        for line in result.stdout.split('\n'):
            if not line:
                if current_match:
                    matches.append(current_match)
                    current_match = None
                continue

            # Check if it's a file path line
            if line.endswith('.md'):
                if current_match:
                    matches.append(current_match)

                file_path = Path(line)
                # Extract date from path: YYYY/MM/DD.md
                parts = file_path.parts
                try:
                    year = int(parts[-3])
                    month = int(parts[-2])
                    day = int(file_path.stem)
                    entry_date = date(year, month, day)

                    # Filter by date range if specified
                    if date_from and entry_date < date_from:
                        current_match = None
                        continue
                    if date_to and entry_date > date_to:
                        current_match = None
                        continue

                    current_match = {
                        "date": entry_date.isoformat(),
                        "file_path": str(file_path),
                        "matches": []
                    }
                except (ValueError, IndexError):
                    current_match = None
            elif current_match and ':' in line:
                # Line with match (format: line_number:content)
                try:
                    line_num, content = line.split(':', 1)
                    if line_num.isdigit():
                        current_match["matches"].append({
                            "line": int(line_num),
                            "content": content
                        })
                except ValueError:
                    pass

        # Add last match if exists
        if current_match:
            matches.append(current_match)

        return matches

    except subprocess.TimeoutExpired:
        return []
    except FileNotFoundError:
        # ripgrep not installed
        return []


def _update_index(target_date: date, file_path: Path):
    """Update the journal index with a new entry."""
    index = {}

    if JOURNAL_INDEX.exists():
        with JOURNAL_INDEX.open('r', encoding='utf-8') as f:
            try:
                index = json.load(f)
            except json.JSONDecodeError:
                index = {}

    # Add or update entry
    date_key = target_date.isoformat()
    index[date_key] = {
        "file_path": str(file_path),
        "last_updated": datetime.now().isoformat()
    }

    # Ensure parent directory exists
    JOURNAL_INDEX.parent.mkdir(parents=True, exist_ok=True)

    # Write back
    with JOURNAL_INDEX.open('w', encoding='utf-8') as f:
        json.dump(index, f, indent=2)


def get_recent_journal_dates(limit: int = 7) -> List[str]:
    """Get the most recent journal dates."""
    if not JOURNAL_INDEX.exists():
        return []

    with JOURNAL_INDEX.open('r', encoding='utf-8') as f:
        try:
            index = json.load(f)
        except json.JSONDecodeError:
            return []

    # Sort by date (newest first)
    sorted_dates = sorted(index.keys(), reverse=True)
    return sorted_dates[:limit]


def add_linked_entry_to_journal(journal_date: date, entry_id: str) -> bool:
    """
    Add a linked entry ID to a journal file's front matter.

    Args:
        journal_date: The date of the journal entry
        entry_id: The entry ID to link

    Returns:
        True if successful, False otherwise
    """
    journal_file = get_journal_path(journal_date)

    if not journal_file.exists():
        return False

    with journal_file.open('r', encoding='utf-8') as f:
        content = f.read()

    # Parse and update front matter
    if not content.startswith("---\n"):
        return False

    end_front_matter = content.find("---\n", 4)
    if end_front_matter == -1:
        return False

    front_matter = content[4:end_front_matter]
    body = content[end_front_matter + 4:]

    # Check if linked_entries already exists
    if "linked_entries:" in front_matter:
        # Add to existing list
        lines = front_matter.split("\n")
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if "linked_entries:" in line:
                new_lines.append(f"  - {entry_id}")
        front_matter = "\n".join(new_lines)
    else:
        # Add new linked_entries section
        front_matter += f"\nlinked_entries:\n  - {entry_id}\n"

    # Write back
    with journal_file.open('w', encoding='utf-8') as f:
        f.write(f"---\n{front_matter}---\n{body}")

    return True
