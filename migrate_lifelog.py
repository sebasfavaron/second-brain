"""
Migration script to import existing lifelog.md journal entries into the unified system.

This script:
1. Reads journal entries from /home/sebas/lifelog.md/journal/entries/
2. Copies them to the new journal structure
3. Migrates audio files if they exist
4. Updates the journal index
"""
import os
import shutil
import json
from pathlib import Path
from datetime import datetime
import logging

from config import JOURNAL_ENTRIES_DIR, JOURNAL_AUDIO_DIR, JOURNAL_INDEX

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Source paths (adjust if needed)
OLD_JOURNAL_ENTRIES = Path("/home/sebas/lifelog.md/journal/entries")
OLD_JOURNAL_AUDIO = Path("/home/sebas/lifelog.md/journal/audio")


def ensure_dirs():
    """Create necessary directories."""
    JOURNAL_ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
    JOURNAL_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    JOURNAL_INDEX.parent.mkdir(parents=True, exist_ok=True)


def migrate_journal_entries():
    """Migrate journal entries from old structure to new."""
    if not OLD_JOURNAL_ENTRIES.exists():
        logger.warning(f"Old journal directory not found: {OLD_JOURNAL_ENTRIES}")
        return 0

    count = 0
    index = {}

    # Walk through old structure: YYYY/MM/YYYY-MM-DD.md
    for year_dir in sorted(OLD_JOURNAL_ENTRIES.iterdir()):
        if not year_dir.is_dir():
            continue

        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue

            for day_file in sorted(month_dir.glob("*.md")):
                # Parse date from filename (YYYY-MM-DD.md)
                try:
                    filename = day_file.stem  # e.g., "2026-01-24"
                    parts = filename.split('-')

                    if len(parts) != 3:
                        logger.warning(f"Skipping invalid filename: {day_file.name}")
                        continue

                    year, month, day = parts

                    # Verify it matches directory structure
                    if year != year_dir.name or month != month_dir.name:
                        logger.warning(f"Date mismatch in {day_file}: {filename} vs {year_dir.name}/{month_dir.name}")
                        continue

                    # Create target directory
                    target_dir = JOURNAL_ENTRIES_DIR / year / month
                    target_dir.mkdir(parents=True, exist_ok=True)

                    # Copy file with new name: DD.md
                    target_file = target_dir / f"{day}.md"
                    shutil.copy2(day_file, target_file)

                    # Add to index
                    date_key = f"{year}-{month}-{day}"
                    index[date_key] = {
                        "file_path": str(target_file),
                        "last_updated": datetime.now().isoformat(),
                        "migrated": True
                    }

                    count += 1
                    logger.info(f"Migrated: {date_key} -> {target_file}")

                except Exception as e:
                    logger.error(f"Failed to migrate {day_file}: {e}")

    # Save index
    if index:
        with JOURNAL_INDEX.open('w', encoding='utf-8') as f:
            json.dump(index, f, indent=2)

    return count


def migrate_audio_files():
    """Migrate audio files from old structure to new."""
    # Audio files are in: OLD_JOURNAL_ENTRIES/YYYY/MM/YYYY-MM-DD/*.ogg
    if not OLD_JOURNAL_ENTRIES.exists():
        logger.warning(f"Old journal directory not found: {OLD_JOURNAL_ENTRIES}")
        return 0

    count = 0

    # Walk through old structure: YYYY/MM/YYYY-MM-DD/*.ogg
    for year_dir in sorted(OLD_JOURNAL_ENTRIES.iterdir()):
        if not year_dir.is_dir():
            continue

        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue

            # Look for date subdirectories with audio files
            for date_dir in sorted(month_dir.iterdir()):
                if not date_dir.is_dir():
                    continue

                # Parse date from directory name (YYYY-MM-DD)
                try:
                    date_parts = date_dir.name.split('-')
                    if len(date_parts) != 3:
                        continue

                    year, month, day = date_parts

                    # Create target directory
                    target_dir = JOURNAL_AUDIO_DIR / year / month
                    target_dir.mkdir(parents=True, exist_ok=True)

                    # Copy all audio files with new naming: DD_HHMM.ogg
                    for audio_file in sorted(date_dir.glob("*.ogg")):
                        try:
                            # entry-HHMM.ogg -> DD_HHMM.ogg
                            time_part = audio_file.stem.replace('entry-', '')
                            new_name = f"{day}_{time_part}.ogg"
                            target_file = target_dir / new_name

                            shutil.copy2(audio_file, target_file)
                            count += 1
                            logger.info(f"Migrated audio: {audio_file.name} -> {new_name}")
                        except Exception as e:
                            logger.error(f"Failed to migrate audio {audio_file}: {e}")

                except Exception as e:
                    logger.error(f"Failed to process audio dir {date_dir}: {e}")

    return count


def verify_migration():
    """Verify migration was successful."""
    logger.info("\n=== Migration Verification ===")

    # Count migrated entries
    entry_count = 0
    for year_dir in JOURNAL_ENTRIES_DIR.iterdir():
        if year_dir.is_dir():
            for month_dir in year_dir.iterdir():
                if month_dir.is_dir():
                    entry_count += len(list(month_dir.glob("*.md")))

    logger.info(f"Total journal entries: {entry_count}")

    # Count migrated audio files
    audio_count = 0
    if JOURNAL_AUDIO_DIR.exists():
        for year_dir in JOURNAL_AUDIO_DIR.iterdir():
            if year_dir.is_dir():
                for month_dir in year_dir.iterdir():
                    if month_dir.is_dir():
                        audio_count += len(list(month_dir.glob("*.ogg")))

    logger.info(f"Total audio files: {audio_count}")

    # Check index
    if JOURNAL_INDEX.exists():
        with JOURNAL_INDEX.open('r') as f:
            index = json.load(f)
        logger.info(f"Index entries: {len(index)}")
    else:
        logger.warning("Journal index not found")


def main():
    """Run the migration."""
    logger.info("Starting lifelog.md migration to unified system...")

    # Ensure directories exist
    ensure_dirs()

    # Migrate journal entries
    logger.info("\n=== Migrating Journal Entries ===")
    entries_migrated = migrate_journal_entries()
    logger.info(f"Migrated {entries_migrated} journal entries")

    # Migrate audio files
    logger.info("\n=== Migrating Audio Files ===")
    audio_migrated = migrate_audio_files()
    logger.info(f"Migrated {audio_migrated} audio files")

    # Verify
    verify_migration()

    logger.info("\n=== Migration Complete ===")
    logger.info(f"Journal entries: {entries_migrated}")
    logger.info(f"Audio files: {audio_migrated}")
    logger.info("\nNext steps:")
    logger.info("1. Verify entries at: " + str(JOURNAL_ENTRIES_DIR))
    logger.info("2. Test with: python bot-listener.py")
    logger.info("3. Check /today command to see today's journal")


if __name__ == "__main__":
    main()
