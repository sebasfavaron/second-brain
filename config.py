"""Configuration for Second Brain system."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent
BRAIN_DIR = BASE_DIR / "brain"
JOURNAL_DIR = BASE_DIR / "journal"
JOURNAL_ENTRIES_DIR = JOURNAL_DIR / "entries"
JOURNAL_AUDIO_DIR = JOURNAL_DIR / "audio"
SKILLS_DIR = BASE_DIR / "skills"
LOG_FILE = BASE_DIR / "bot.log"

# JSON storage files
STORAGE_FILES = {
    "people": BRAIN_DIR / "people.json",
    "projects": BRAIN_DIR / "projects.json",
    "ideas": BRAIN_DIR / "ideas.json",
    "admin": BRAIN_DIR / "admin.json",
    "inbox": BRAIN_DIR / "inbox.json",
}
AUDIT_FILE = BRAIN_DIR / "audit.json"
STATE_FILE = BRAIN_DIR / "state.json"
CORRECTIONS_QUEUE = BRAIN_DIR / "corrections_queue.json"
REMINDERS_FILE = BRAIN_DIR / "reminders.json"
JOURNAL_INDEX = JOURNAL_DIR / "index.json"

# Context files for enriched classification
CONTEXT_FILES = {
    "admin": BRAIN_DIR / "admin_context.md",
    "people": BRAIN_DIR / "people_context.md",
    "projects": BRAIN_DIR / "projects_context.md",
    "ideas": BRAIN_DIR / "ideas_context.md",
}

# Categories
CATEGORIES = ["people", "projects", "ideas", "admin"]

# Classification
CONFIDENCE_THRESHOLD = 0.7

# Secrets (from .env)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Digest settings
DIGEST_HOUR = 9  # 9 AM daily digest

# Whisper settings for voice transcription
WHISPER_MODEL = "base"  # Options: tiny, base, small, medium, large

# Default reminder time (when not specified)
DEFAULT_REMINDER_HOUR = 9  # 9 AM next day

# Daily review/reflection time
REVIEW_HOUR = 21  # 9 PM daily review
