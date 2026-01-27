"""Embedding generation and semantic search using Claude Haiku."""
import json
import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple
import logging

from config import BRAIN_DIR, ANTHROPIC_API_KEY
from classifier import get_client

logger = logging.getLogger(__name__)

EMBEDDINGS_FILE = BRAIN_DIR / "embeddings.json"


def ensure_embeddings_file():
    """Create embeddings file if it doesn't exist."""
    if not EMBEDDINGS_FILE.exists():
        EMBEDDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with EMBEDDINGS_FILE.open('w', encoding='utf-8') as f:
            json.dump({}, f)


def load_embeddings() -> dict:
    """Load all embeddings from storage."""
    ensure_embeddings_file()

    try:
        with EMBEDDINGS_FILE.open('r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.warning("Embeddings file corrupted, resetting")
        return {}


def save_embeddings(embeddings: dict):
    """Save embeddings to storage."""
    ensure_embeddings_file()

    with EMBEDDINGS_FILE.open('w', encoding='utf-8') as f:
        json.dump(embeddings, f, indent=2)


def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate embedding for text using Claude Haiku (cost-efficient).

    Note: Claude API doesn't directly support embeddings yet,
    so we'll use a simple proxy: encode text to embedding-like vector.

    For now, this is a placeholder that creates a simple hash-based vector.
    When Claude adds embedding support, we can switch to their API.

    Args:
        text: Text to embed

    Returns:
        Embedding vector or None if failed
    """
    try:
        # Placeholder: Simple text-to-vector encoding
        # This creates a deterministic vector based on word frequencies
        # Real implementation would use Claude Haiku embeddings when available

        # Normalize text
        text = text.lower().strip()
        if not text:
            return None

        # Simple TF-IDF-like approach for now
        # This is deterministic and fast, though not as good as real embeddings
        words = text.split()

        # Create a simple vector (384 dimensions for compatibility)
        vector = [0.0] * 384

        for i, word in enumerate(words[:384]):
            # Hash each word to a position and value
            hash_val = hash(word)
            pos = abs(hash_val) % 384
            val = (hash_val % 1000) / 1000.0
            vector[pos] += val

        # Normalize vector
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = (np.array(vector) / norm).tolist()

        return vector

    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return None


def store_embedding(entry_id: str, text: str, category: str) -> bool:
    """
    Generate and store embedding for an entry.

    Args:
        entry_id: Entry UUID
        text: Text to embed
        category: Entry category

    Returns:
        True if successful
    """
    try:
        embedding = generate_embedding(text)
        if not embedding:
            return False

        embeddings = load_embeddings()
        embeddings[entry_id] = {
            "embedding": embedding,
            "category": category,
            "text_preview": text[:100]  # Store preview for debugging
        }
        save_embeddings(embeddings)

        logger.debug(f"Stored embedding for entry {entry_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to store embedding: {e}")
        return False


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    try:
        v1 = np.array(vec1)
        v2 = np.array(vec2)

        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    except Exception as e:
        logger.error(f"Failed to calculate similarity: {e}")
        return 0.0


def semantic_search(
    query: str,
    categories: Optional[List[str]] = None,
    limit: int = 10,
    min_similarity: float = 0.1
) -> List[Tuple[str, float]]:
    """
    Search entries using semantic similarity.

    Args:
        query: Search query
        categories: Optional list of categories to search
        limit: Maximum results
        min_similarity: Minimum similarity threshold

    Returns:
        List of (entry_id, similarity_score) tuples, sorted by score
    """
    try:
        # Generate query embedding
        query_embedding = generate_embedding(query)
        if not query_embedding:
            logger.warning("Failed to generate query embedding")
            return []

        # Load all embeddings
        embeddings = load_embeddings()
        if not embeddings:
            logger.info("No embeddings available for semantic search")
            return []

        # Calculate similarities
        results = []
        for entry_id, data in embeddings.items():
            # Filter by category if specified
            if categories and data.get("category") not in categories:
                continue

            entry_embedding = data.get("embedding")
            if not entry_embedding:
                continue

            similarity = cosine_similarity(query_embedding, entry_embedding)

            if similarity >= min_similarity:
                results.append((entry_id, similarity))

        # Sort by similarity (descending) and limit
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        return []


def rebuild_embeddings(storage_module) -> Tuple[int, int]:
    """
    Rebuild embeddings for all existing entries.
    Useful for backfilling or after changing embedding model.

    Args:
        storage_module: The storage module with get_all_entries function

    Returns:
        Tuple of (successful, failed) counts
    """
    from config import CATEGORIES

    successful = 0
    failed = 0

    logger.info("Rebuilding embeddings for all entries...")

    for category in CATEGORIES + ["inbox"]:
        try:
            entries = storage_module.get_all_entries(category)

            for entry in entries:
                entry_id = entry.get("id")
                text = entry.get("raw_message", "")

                if not entry_id or not text:
                    failed += 1
                    continue

                if store_embedding(entry_id, text, category):
                    successful += 1
                else:
                    failed += 1

        except Exception as e:
            logger.error(f"Failed to process category {category}: {e}")

    logger.info(f"Rebuild complete: {successful} successful, {failed} failed")
    return successful, failed


def get_embedding_stats() -> dict:
    """Get statistics about stored embeddings."""
    try:
        embeddings = load_embeddings()

        stats = {
            "total": len(embeddings),
            "by_category": {}
        }

        for data in embeddings.values():
            category = data.get("category", "unknown")
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

        return stats

    except Exception as e:
        logger.error(f"Failed to get embedding stats: {e}")
        return {"total": 0, "by_category": {}}
