"""Backup and export functionality for Second Brain."""
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime
import logging

from config import BRAIN_DIR, JOURNAL_DIR

logger = logging.getLogger(__name__)


def create_backup() -> Path:
    """
    Create a timestamped ZIP backup of all data.

    Returns:
        Path to the created ZIP file
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"second_brain_backup_{timestamp}.zip"

    # Create temp file
    temp_dir = Path(tempfile.gettempdir())
    backup_path = temp_dir / backup_filename

    logger.info(f"Creating backup: {backup_path}")

    try:
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Backup brain directory (JSON files)
            if BRAIN_DIR.exists():
                for file_path in BRAIN_DIR.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(BRAIN_DIR.parent)
                        zipf.write(file_path, arcname)
                        logger.debug(f"Added to backup: {arcname}")

            # Backup journal directory (entries and audio)
            if JOURNAL_DIR.exists():
                for file_path in JOURNAL_DIR.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(JOURNAL_DIR.parent)
                        zipf.write(file_path, arcname)
                        logger.debug(f"Added to backup: {arcname}")

        # Get file size for logging
        size_mb = backup_path.stat().st_size / (1024 * 1024)
        logger.info(f"Backup created successfully: {size_mb:.2f} MB")

        return backup_path

    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        raise


def get_backup_stats() -> dict:
    """
    Get statistics about what will be backed up.

    Returns:
        Dict with counts and sizes
    """
    stats = {
        "brain_files": 0,
        "brain_size_mb": 0,
        "journal_entries": 0,
        "audio_files": 0,
        "journal_size_mb": 0,
        "total_size_mb": 0,
    }

    try:
        # Count brain files
        if BRAIN_DIR.exists():
            brain_files = list(BRAIN_DIR.rglob('*'))
            stats["brain_files"] = len([f for f in brain_files if f.is_file()])
            stats["brain_size_mb"] = sum(f.stat().st_size for f in brain_files if f.is_file()) / (1024 * 1024)

        # Count journal files
        if JOURNAL_DIR.exists():
            journal_files = list(JOURNAL_DIR.rglob('*'))
            for f in journal_files:
                if f.is_file():
                    if f.suffix == '.md':
                        stats["journal_entries"] += 1
                    elif f.suffix == '.ogg':
                        stats["audio_files"] += 1

            stats["journal_size_mb"] = sum(f.stat().st_size for f in journal_files if f.is_file()) / (1024 * 1024)

        stats["total_size_mb"] = stats["brain_size_mb"] + stats["journal_size_mb"]

    except Exception as e:
        logger.error(f"Failed to get backup stats: {e}")

    return stats


def cleanup_old_backups(temp_dir: Path = None, keep_last: int = 3):
    """
    Clean up old backup files from temp directory.

    Args:
        temp_dir: Directory to clean (defaults to system temp)
        keep_last: Number of recent backups to keep
    """
    if temp_dir is None:
        temp_dir = Path(tempfile.gettempdir())

    try:
        # Find all backup files
        backup_files = sorted(
            temp_dir.glob("second_brain_backup_*.zip"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )

        # Delete old backups
        for backup_file in backup_files[keep_last:]:
            try:
                backup_file.unlink()
                logger.info(f"Cleaned up old backup: {backup_file.name}")
            except Exception as e:
                logger.warning(f"Failed to delete old backup {backup_file}: {e}")

    except Exception as e:
        logger.error(f"Failed to cleanup old backups: {e}")
