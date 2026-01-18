"""Context management for enriched classification."""
import logging
from pathlib import Path
from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, CONTEXT_FILES, CATEGORIES
from storage import get_all_entries

logger = logging.getLogger(__name__)

# Max context size in words
MAX_CONTEXT_WORDS = 500
COMPRESS_THRESHOLD_WORDS = 400


def _get_client():
    """Get Anthropic client."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not set")
    return Anthropic(api_key=ANTHROPIC_API_KEY)


def _count_words(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def bootstrap_context(category: str) -> None:
    """
    Create initial context file from existing entries.

    Args:
        category: The category to bootstrap
    """
    if category not in CONTEXT_FILES:
        logger.warning(f"Unknown category: {category}")
        return

    context_path = CONTEXT_FILES[category]

    # Skip if already exists
    if context_path.exists():
        logger.info(f"Context already exists: {context_path}")
        return

    # Load all entries for this category
    entries = get_all_entries(category)

    # Create template if no entries
    if not entries:
        content = f"# {category.title()} Context\n\nNo entries yet."
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text(content)
        logger.info(f"Created empty context: {context_path}")
        return

    # Synthesize context from entries
    try:
        entries_text = "\n\n".join([
            f"- {e.get('raw_message', '')}" for e in entries
        ])

        prompt = f"""Create a concise markdown summary of these {category} entries.
Group by themes/patterns. Max 500 words. Focus on key facts and patterns.

Entries:
{entries_text}

Format as markdown with sections."""

        client = _get_client()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        content = response.content[0].text.strip()

        # Save context
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text(content)
        logger.info(f"Bootstrapped context: {context_path} ({_count_words(content)} words)")

    except Exception as e:
        logger.error(f"Failed to bootstrap {category} context: {e}")
        # Create minimal template on error
        content = f"# {category.title()} Context\n\nBootstrap failed: {e}"
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text(content)


def load_context(category: str) -> str:
    """
    Load context for a category, bootstrapping if needed.

    Args:
        category: The category to load

    Returns:
        Context markdown content (empty string on error)
    """
    if category not in CONTEXT_FILES:
        return ""

    context_path = CONTEXT_FILES[category]

    # Bootstrap if missing
    if not context_path.exists():
        try:
            bootstrap_context(category)
        except Exception as e:
            logger.warning(f"Failed to bootstrap {category}: {e}")
            return ""

    # Read context
    try:
        content = context_path.read_text()
        return content
    except Exception as e:
        logger.error(f"Failed to read context for {category}: {e}")
        return ""


def compress_context(content: str) -> str:
    """
    Compress context to under 400 words.

    Args:
        content: The context to compress

    Returns:
        Compressed context
    """
    try:
        prompt = f"""Compress this context to under 400 words while preserving key facts.
Remove redundancy but keep all important information.

Context:
{content}"""

        client = _get_client()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )

        compressed = response.content[0].text.strip()
        logger.info(f"Compressed context: {_count_words(content)} -> {_count_words(compressed)} words")
        return compressed

    except Exception as e:
        logger.error(f"Compression failed: {e}")
        # Fallback: truncate to first 400 words
        words = content.split()[:400]
        return " ".join(words)


def enrich_context(category: str, new_entry: dict) -> None:
    """
    Update context with new entry.

    Args:
        category: The category to enrich
        new_entry: The new entry to incorporate
    """
    if category not in CONTEXT_FILES:
        logger.warning(f"Unknown category: {category}")
        return

    context_path = CONTEXT_FILES[category]

    try:
        # Load existing context
        existing_content = load_context(category)

        if not existing_content:
            existing_content = f"# {category.title()} Context\n\nNo entries yet."

        # Prepare new entry text
        entry_text = new_entry.get("raw_message", "")

        # Merge new entry into context
        prompt = f"""Update this context with the new entry. Merge into existing sections.
Remove redundant info. Keep under 500 words total.

Existing context:
{existing_content}

New entry:
{entry_text}

Return updated context as markdown."""

        client = _get_client()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        updated_content = response.content[0].text.strip()

        # Check if compression needed
        word_count = _count_words(updated_content)
        if word_count > COMPRESS_THRESHOLD_WORDS:
            logger.info(f"Context exceeds threshold ({word_count} words), compressing...")
            updated_content = compress_context(updated_content)

        # Save updated context
        context_path.write_text(updated_content)
        logger.info(f"Enriched {category} context ({_count_words(updated_content)} words)")

    except Exception as e:
        logger.error(f"Failed to enrich {category} context: {e}")
        # Don't block on error - enrichment is non-critical
