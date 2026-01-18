# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Second Brain - AI-powered personal knowledge management system. Receives messages via Telegram, classifies them using Claude API, stores in JSON files, and provides correction/digest features.

## Commands

```bash
# Activate virtualenv
source venv/bin/activate

# Install dependencies
pip install python-telegram-bot anthropic python-dotenv

# Run the bot (main entry point)
python bot-listener.py

# Run digest manually (normally via cron)
python brain-processor.py <your_chat_id> --digest

# Process corrections manually (normally via cron)
python brain-processor.py <your_chat_id> --corrections

# Bootstrap context files from existing entries
python bootstrap_contexts.py
```

## Setup

1. Copy `.env.example` to `.env`
2. Add your `TELEGRAM_TOKEN` and `ANTHROPIC_API_KEY`
3. Run `python bot-listener.py`

## Architecture

```
Telegram
    |
bot-listener.py  ---> classifier.py (Claude API)
    |                       |
    |                  storage.py
    |                       |
    +--------------->  brain/*.json
    |
    +--------------->  Confirmation reply
```

### Files

| File | Purpose |
|------|---------|
| `bot-listener.py` | Telegram bot - receives messages, classifies, stores, sends confirmations |
| `brain-processor.py` | Cron-triggered - daily digests, correction queue processing |
| `classifier.py` | Claude API wrapper - message classification with context enrichment |
| `context_manager.py` | Context loading, bootstrapping, enrichment for classification |
| `storage.py` | JSON CRUD - entries, audit log, corrections queue, state |
| `config.py` | Paths, categories, thresholds, env loading |
| `bootstrap_contexts.py` | One-time script to create context files from existing entries |

### Data Files (brain/)

| File | Content |
|------|---------|
| `people.json` | Facts about people |
| `projects.json` | Work/project items |
| `ideas.json` | Creative thoughts, insights |
| `admin.json` | Logistics, appointments |
| `inbox.json` | Low-confidence items awaiting review |
| `audit.json` | All classification events |
| `state.json` | Digest timestamps, etc. |
| `corrections_queue.json` | Pending corrections |
| `*_context.md` | Context summaries for enriched classification (auto-updated) |

## Entry Schema

```json
{
  "id": "uuid",
  "timestamp": "ISO",
  "raw_message": "...",
  "category": "people",
  "confidence": 0.9,
  "processed_at": "ISO",
  "chat_id": 123456,
  "message_id": 42,
  "corrected_from": null
}
```

## User Flows

### New Message
1. Send text to bot
2. Bot classifies via Claude
3. Bot stores in appropriate category (or inbox if low confidence)
4. Bot replies with category + confidence

### Correction
1. Reply to bot's confirmation message with category name
2. Bot moves entry to new category
3. Bot confirms move

## Configuration

- `CONFIDENCE_THRESHOLD = 0.7` - below this goes to inbox
- `DIGEST_HOUR = 9` - daily digest time
- Categories: people, projects, ideas, admin

## Gotchas

- Token must be in `.env`, not hardcoded
- Reply-based correction only works when replying to the bot's confirmation message
- brain-processor.py needs chat_id arg for digest delivery
- Digests/corrections run via cron, not continuous service
- Context enrichment happens automatically after high-confidence classifications
