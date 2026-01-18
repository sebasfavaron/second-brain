"""Configuration for Second Brain system."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent
BRAIN_DIR = BASE_DIR / "brain"
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
