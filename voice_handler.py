"""Voice message handling with Whisper transcription."""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
import logging

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

from config import JOURNAL_AUDIO_DIR, WHISPER_MODEL

logger = logging.getLogger(__name__)


def ensure_audio_dirs():
    """Create audio directories if they don't exist."""
    JOURNAL_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def get_audio_path(timestamp: datetime, index: int = 0) -> Path:
    """
    Get the path where an audio file should be stored.

    Args:
        timestamp: When the voice message was received
        index: Index for multiple messages on same day

    Returns:
        Path to store the audio file
    """
    year = str(timestamp.year)
    month = f"{timestamp.month:02d}"
    day = f"{timestamp.day:02d}"

    audio_dir = JOURNAL_AUDIO_DIR / year / month
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Format: DD_HH-MM-SS_index.ogg
    time_str = timestamp.strftime("%H-%M-%S")
    filename = f"{day}_{time_str}_{index}.ogg"

    return audio_dir / filename


async def download_voice_message(bot, file_id: str, timestamp: Optional[datetime] = None) -> Optional[Path]:
    """
    Download a voice message from Telegram.

    Args:
        bot: Telegram bot instance
        file_id: Telegram file ID
        timestamp: When the message was received (defaults to now)

    Returns:
        Path to downloaded file, or None if failed
    """
    ensure_audio_dirs()

    if timestamp is None:
        timestamp = datetime.now()

    try:
        # Get file from Telegram
        file = await bot.get_file(file_id)

        # Find available index
        index = 0
        audio_path = get_audio_path(timestamp, index)
        while audio_path.exists():
            index += 1
            audio_path = get_audio_path(timestamp, index)

        # Download file
        await file.download_to_drive(audio_path)

        logger.info(f"Downloaded voice message to {audio_path}")
        return audio_path

    except Exception as e:
        logger.error(f"Failed to download voice message: {e}")
        return None


def transcribe_audio(audio_path: Path) -> Optional[Dict]:
    """
    Transcribe audio file using Whisper.

    Args:
        audio_path: Path to audio file

    Returns:
        Dict with transcription result, or None if failed
    """
    if not WHISPER_AVAILABLE:
        logger.error("Whisper not available. Install with: pip install openai-whisper")
        return None

    if not audio_path.exists():
        logger.error(f"Audio file not found: {audio_path}")
        return None

    try:
        # Load Whisper model (cached after first load)
        model = whisper.load_model(WHISPER_MODEL)

        # Transcribe
        result = model.transcribe(str(audio_path))

        return {
            "text": result["text"].strip(),
            "language": result.get("language", "unknown"),
            "audio_path": str(audio_path)
        }

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return None


async def handle_voice_message(bot, voice_message, timestamp: Optional[datetime] = None) -> Optional[Dict]:
    """
    Complete voice message handling pipeline: download + transcribe.

    Args:
        bot: Telegram bot instance
        voice_message: Telegram voice message object
        timestamp: When the message was received

    Returns:
        Dict with transcription and audio path, or None if failed
    """
    # Download audio file
    audio_path = await download_voice_message(bot, voice_message.file_id, timestamp)

    if not audio_path:
        return None

    # Transcribe
    transcription = transcribe_audio(audio_path)

    if not transcription:
        return None

    return {
        "text": transcription["text"],
        "language": transcription["language"],
        "audio_path": str(audio_path),
        "timestamp": timestamp.isoformat() if timestamp else datetime.now().isoformat()
    }


def list_audio_files(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> list:
    """
    List all audio files in date range.

    Args:
        date_from: Start date (inclusive)
        date_to: End date (inclusive)

    Returns:
        List of audio file paths
    """
    if not JOURNAL_AUDIO_DIR.exists():
        return []

    all_files = []

    # Walk through year/month directories
    for year_dir in sorted(JOURNAL_AUDIO_DIR.iterdir()):
        if not year_dir.is_dir():
            continue

        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue

            # Get all .ogg files
            for audio_file in sorted(month_dir.glob("*.ogg")):
                # Parse date from directory structure
                try:
                    year = int(year_dir.name)
                    month = int(month_dir.name)
                    # Parse day from filename (DD_HH-MM-SS_index.ogg)
                    day = int(audio_file.name.split("_")[0])

                    file_date = datetime(year, month, day)

                    # Filter by date range
                    if date_from and file_date < date_from:
                        continue
                    if date_to and file_date > date_to:
                        continue

                    all_files.append(audio_file)

                except (ValueError, IndexError):
                    # Skip files with invalid names
                    continue

    return all_files
