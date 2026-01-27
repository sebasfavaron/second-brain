# Second Brain - Unified Knowledge + Diary Bot

An intelligent Telegram bot that combines personal knowledge management with daily journaling. Built with Claude AI (Anthropic API) for natural, conversational interaction.

📚 **[Quick Start Guide →](GETTING_STARTED.md)** | 🚀 **[Roadmap →](NEXT_STEPS.md)**

## What It Does

**Single bot for two systems:**
- 📚 **Knowledge Base** - Store and organize facts about people, projects, ideas, and admin tasks
- 📔 **Daily Journal** - Keep a diary with text and voice entries, searchable across time
- 🔗 **Hybrid Messages** - Automatically extract facts from diary entries and cross-reference them
- ⏰ **Smart Reminders** - Time-based notifications with optional recurring patterns
- 🎤 **Voice Support** - Send voice messages, automatically transcribed via Whisper

## Features

### 🔍 Semantic Search
Search using meaning, not just keywords:
- Finds related content even with different words
- Works across multiple languages
- Hybrid approach: semantic similarity + keyword matching
- Automatic embedding generation on entry creation

### 📦 Backup & Export
Protect your data:
- `/export` command creates complete ZIP backup
- Includes all journal entries, knowledge base, and audio files
- Sent directly via Telegram for easy download
- Auto-cleanup of old backups

### Intelligent Routing
The bot automatically classifies your messages:
- **Diary** - Emotional, reflective content goes to journal
- **Knowledge** - Facts, names, dates go to structured categories
- **Hybrid** - Diary entry + extracted facts, automatically linked

### Knowledge Categories
- `people` - Information about people, relationships
- `projects` - Work tasks, deadlines, project updates
- `ideas` - Creative thoughts, insights, future plans
- `admin` - Logistics, appointments, locations
- `inbox` - Low-confidence items for manual review

### Commands

**Main Commands:**
- `/help` - Show all commands and usage
- `/today` - Today's journal + upcoming reminders
- `/day YYYY-MM-DD` - View journal for specific date
- `/search <query>` - Semantic search across journal and knowledge
- `/reminders` - List upcoming reminders
- `/inbox` - Review items needing classification

**Utilities:**
- `/export` - Download complete backup as ZIP
- `/reset` - Clear conversation history
- `/rebuild_embeddings` - Regenerate semantic search embeddings (admin)

### Voice Messages
Send voice messages in any language - they're automatically:
1. Downloaded and stored
2. Transcribed using OpenAI Whisper (local)
3. Processed by the AI agent
4. Stored in your journal with timestamp

### Reminders
Create reminders with natural language:
- "Remind me to call dentist tomorrow at 3pm"
- "Remind me to review report daily"
- Supports: one-time, daily, weekly, monthly

### Cross-Referencing
Hybrid messages automatically link diary and knowledge:
- Journal entries reference extracted facts
- Knowledge entries link back to journal dates
- Full context available in both systems

## Setup

> 📖 **Complete setup guide:** See **[GETTING_STARTED.md](GETTING_STARTED.md)** for detailed step-by-step instructions, including:
> - Getting API keys (Telegram + Anthropic)
> - Local setup for testing
> - Production deployment to Raspberry Pi
> - Troubleshooting common issues

### Quick Start

1. **Clone and install**
```bash
git clone https://github.com/sebasfavaron/second-brain.git
cd second-brain
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install openai-whisper
```

2. **Configure**
```bash
cp .env.example .env
# Add your TELEGRAM_TOKEN and ANTHROPIC_API_KEY
```

3. **Run**
```bash
mkdir -p brain journal/entries journal/audio
python bot-listener.py
```

For production deployment with systemd and cron, see **[GETTING_STARTED.md](GETTING_STARTED.md)**.

## Architecture

```
Telegram Message (text/voice)
        ↓
   [Voice? → Whisper transcription]
        ↓
   Claude Agent (unified prompt + tools)
        ↓
   Routes to: DIARY | KNOWLEDGE | HYBRID
        ↓
   ┌─────────────────┬─────────────────┐
   │                 │                 │
   ▼                 ▼                 ▼
journal/         brain/*.json      both + links
YYYY/MM/DD.md    (categories)
```

### Files Structure

```
second-brain/
├── bot-listener.py          # Main bot - handles messages, commands
├── brain-processor.py       # Background jobs - digests, reminders
├── agent_tools.py           # Tool definitions for Claude
├── classifier.py            # Claude API client
├── storage.py               # JSON storage for knowledge base
├── journal_storage.py       # Markdown storage for journal
├── reminder_storage.py      # Reminder CRUD + trigger logic
├── voice_handler.py         # Voice transcription via Whisper
├── conversation_state.py    # Conversation history management
├── context_manager.py       # Context enrichment for classification
├── config.py                # Configuration and paths
├── migrate_lifelog.py       # Migration script for existing journals
└── brain/                   # Storage directory
    ├── people.json
    ├── projects.json
    ├── ideas.json
    ├── admin.json
    ├── inbox.json
    ├── reminders.json
    ├── audit.json
    ├── state.json
    └── *_context.md
└── journal/                 # Journal directory
    ├── entries/YYYY/MM/DD.md
    ├── audio/YYYY/MM/*.ogg
    └── index.json
```

## Configuration

Edit `config.py` to customize:
- `CONFIDENCE_THRESHOLD = 0.7` - Classification confidence threshold
- `DIGEST_HOUR = 9` - Daily digest time
- `DEFAULT_REMINDER_HOUR = 9` - Default reminder time
- `WHISPER_MODEL = "base"` - Whisper model (tiny, base, small, medium, large)

## Examples

### Knowledge Entry
```
You: "Felipe's birthday is March 15"
Bot: Guardado en people (90%)
```

### Diary Entry
```
You: "Today was tough, long meeting with the team"
Bot: Entrada guardada en diario ✓
```

### Hybrid Message
```
You: "Great call with Juan, we set deadline for Friday"
Bot: Entrada guardada en diario ✓
    También guardado:
    • Juan (people)
    • Deadline Friday (projects)
```

### Reminder
```
You: "Remind me to call dentist tomorrow at 3pm"
Bot: Recordatorio creado para mañana 15:00 ✓
```

### Voice Message
```
You: [sends voice message]
Bot: 🎤 Transcribiendo...
     📝 Transcripción: [your message]
     Entrada guardada en diario ✓
```

## Tools Available to Claude

The bot has direct access to these tools:

**Knowledge Base:**
- `list_entries` - List entries in a category
- `search_entries` - Search across categories
- `get_entry` - Get specific entry by ID
- `create_entry` - Store new information
- `move_entry` - Move between categories
- `delete_entry` - Delete an entry

**Journal:**
- `write_journal` - Add diary entry
- `read_journal` - Read journal for date
- `search_journal` - Search all journal entries

**Reminders:**
- `create_reminder` - Set time-based reminder
- `list_reminders` - Show upcoming reminders

**Cross-Reference:**
- `link_entries` - Link journal to knowledge
- `get_audio_file` - Retrieve voice recording

## Development

### Adding New Categories
1. Add to `CATEGORIES` in `config.py`
2. Add to `STORAGE_FILES` dict
3. Create context file in `brain/`
4. Update system prompt in `bot-listener.py`

### Adding New Commands
1. Create handler function in `bot-listener.py`
2. Add to command handlers in `main()`
3. Add to `post_init()` for autocomplete

### Testing
```bash
# Test classification
python -c "from classifier import classify_message; print(classify_message('test message'))"

# Test storage
python -c "from storage import get_all_entries; print(get_all_entries('inbox'))"

# Test journal
python -c "from journal_storage import read_journal; print(read_journal())"
```

## Troubleshooting

**Bot not responding:**
```bash
# Check if bot is running
ps aux | grep bot-listener

# Check logs
tail -f bot.log

# Restart service
sudo systemctl restart second-brain-bot.service
```

**Whisper not working:**
```bash
# Install FFmpeg
sudo apt-get install ffmpeg  # Debian/Ubuntu
brew install ffmpeg          # macOS

# Verify Whisper installation
python -c "import whisper; print('OK')"
```

**Commands not autocompleting:**
- Delete and restart the Telegram chat with the bot
- Commands are set on bot startup - check logs for "Bot commands configured"

## Roadmap & Future Enhancements

See **[NEXT_STEPS.md](NEXT_STEPS.md)** for planned improvements including:
- 📦 Backup & Export functionality
- 🔍 Semantic search with embeddings
- 📊 Analytics & insights
- 🔗 Relationship mapping
- 🏷️ Hashtag support
- 📝 Templates for common entries
- And more...

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

Check **[NEXT_STEPS.md](NEXT_STEPS.md)** for ideas on what to work on.

## License

MIT License - See LICENSE file for details

## Credits

Built with:
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) - Telegram Bot API
- [Anthropic Claude](https://www.anthropic.com) - AI agent with tool use
- [OpenAI Whisper](https://github.com/openai/whisper) - Voice transcription

## Author

Created by [@sebasfavaron](https://github.com/sebasfavaron)

Co-developed with Claude Sonnet 4.5 via [Claude Code](https://claude.com/claude-code)
