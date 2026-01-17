# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python Telegram bot for receiving and logging messages. Uses `python-telegram-bot` library.

## Commands

```bash
# Activate virtualenv
source venv/bin/activate

# Run the bot
python telegram-receive.py

# Install dependencies (after activating venv)
pip install python-telegram-bot
```

## Architecture

Single-file bot (`telegram-receive.py`) that:
- Polls Telegram for text messages
- Logs messages with timestamps to stdout

## Security Note

Bot token is currently hardcoded. Move to environment variable before any production use.
