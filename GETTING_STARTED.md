# Getting Started with Second Brain

This guide will walk you through setting up your Second Brain bot from scratch, whether you're running it locally for testing or deploying to a Raspberry Pi for 24/7 operation.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Getting API Keys](#getting-api-keys)
3. [Local Setup (Testing)](#local-setup-testing)
4. [Production Setup (Raspberry Pi)](#production-setup-raspberry-pi)
5. [First Steps](#first-steps)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

**For all platforms:**
- Python 3.11 or higher ([download here](https://www.python.org/downloads/))
- Git ([download here](https://git-scm.com/downloads))
- FFmpeg (for voice message transcription)

**Installing FFmpeg:**

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian/Raspberry Pi
sudo apt-get update
sudo apt-get install ffmpeg

# Windows (using Chocolatey)
choco install ffmpeg
```

### Required Accounts

1. **Telegram Account** - For bot interaction
2. **Anthropic Account** - For Claude API ([sign up](https://console.anthropic.com))

---

## Getting API Keys

### 1. Create Telegram Bot

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` command
3. Follow prompts:
   - Choose a name (e.g., "My Second Brain")
   - Choose a username (must end in `bot`, e.g., `my_secondbrain_bot`)
4. **Save the token** - looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
5. Optional: Set bot description and profile photo

**Important security note:** Never commit this token to git or share it publicly.

### 2. Get Your Telegram Chat ID

Once your bot is created:

1. Send any message to your bot
2. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Look for `"chat":{"id":123456789` - that number is your chat ID
4. **Save this ID** - needed for cron jobs later

### 3. Get Anthropic API Key

1. Sign up at [console.anthropic.com](https://console.anthropic.com)
2. Add payment method (required for API access)
3. Go to API Keys section
4. Click "Create Key"
5. **Save the key** - looks like: `sk-ant-api03-...`

**Pricing:** Pay-as-you-go, typical usage ~$2-5/month for active personal use.

---

## Local Setup (Testing)

Perfect for trying out the bot before deploying to production.

### Step 1: Clone Repository

```bash
# Clone the repo
git clone https://github.com/sebasfavaron/second-brain.git
cd second-brain
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # On macOS/Linux
# OR
venv\Scripts\activate  # On Windows
```

You should see `(venv)` in your terminal prompt.

### Step 3: Install Dependencies

```bash
# Install core dependencies
pip install -r requirements.txt

# Install Whisper for voice transcription
pip install openai-whisper
```

**Note:** Whisper will download AI models (~140MB for base model) on first use.

### Step 4: Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit the file
nano .env  # or use your preferred editor
```

Add your tokens:
```bash
TELEGRAM_TOKEN=your_telegram_bot_token_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

Save and exit (`Ctrl+X`, then `Y`, then `Enter` in nano).

### Step 5: Create Directories

```bash
# Create storage directories
mkdir -p brain journal/entries journal/audio
```

### Step 6: Run the Bot

```bash
python bot-listener.py
```

You should see:
```
INFO - Unified Brain + Diary bot starting...
INFO - Bot commands configured for autocomplete
INFO - Application started
```

**The bot is now running!** Open Telegram and send a message to your bot.

### Testing Locally

Try these commands:
- `/help` - See all commands
- `/today` - View today's journal
- `Test message` - Send a simple message
- Send a voice message
- `Remind me to test tomorrow`

Press `Ctrl+C` to stop the bot.

---

## Production Setup (Raspberry Pi)

For 24/7 operation with automated reminders and digests.

### Prerequisites for Raspberry Pi

- Raspberry Pi 3 or newer
- Raspberry Pi OS (64-bit recommended)
- SSH access enabled
- Internet connection

### Step 1: Initial Setup

```bash
# SSH into your Raspberry Pi
ssh pi@your-pi-address

# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install required packages
sudo apt-get install -y python3-pip python3-venv git ffmpeg
```

### Step 2: Clone and Setup

```bash
# Clone repository
cd ~
git clone https://github.com/sebasfavaron/second-brain.git
cd second-brain

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install openai-whisper

# Create directories
mkdir -p brain journal/entries journal/audio

# Configure environment
cp .env.example .env
nano .env  # Add your tokens
```

### Step 3: Create Systemd Service

This ensures the bot starts automatically on boot and restarts if it crashes.

```bash
# Create service file
sudo nano /etc/systemd/system/second-brain-bot.service
```

Paste this configuration (replace paths and user):

```ini
[Unit]
Description=Second Brain Telegram Bot
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/second-brain
ExecStart=/home/pi/second-brain/venv/bin/python bot-listener.py
Restart=always
RestartSec=10
StandardOutput=append:/home/pi/second-brain/bot.log
StandardError=append:/home/pi/second-brain/bot.log

[Install]
WantedBy=multi-user.target
```

**Important:** Update `/home/pi/` to your actual path if different.

### Step 4: Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable second-brain-bot.service

# Start service
sudo systemctl start second-brain-bot.service

# Check status
sudo systemctl status second-brain-bot.service
```

You should see:
```
● second-brain-bot.service - Second Brain Telegram Bot
   Active: active (running)
```

### Step 5: Setup Cron Jobs

These handle automated tasks like daily digests and reminders.

```bash
# Edit crontab
crontab -e

# Select editor (nano is easiest for beginners)
```

Add these lines (replace `YOUR_CHAT_ID` with your actual chat ID):

```bash
# Daily digest at 9 AM
0 9 * * * cd /home/pi/second-brain && /home/pi/second-brain/venv/bin/python brain-processor.py YOUR_CHAT_ID --digest >> /home/pi/second-brain/cron.log 2>&1

# Process reminders every minute
* * * * * cd /home/pi/second-brain && /home/pi/second-brain/venv/bin/python brain-processor.py YOUR_CHAT_ID --reminders >> /home/pi/second-brain/cron.log 2>&1

# Process corrections every 30 minutes
*/30 * * * * cd /home/pi/second-brain && /home/pi/second-brain/venv/bin/python brain-processor.py YOUR_CHAT_ID --corrections >> /home/pi/second-brain/cron.log 2>&1
```

Save and exit.

**Verify cron jobs are scheduled:**
```bash
crontab -l
```

### Step 6: Verify Everything Works

```bash
# Check bot is running
sudo systemctl status second-brain-bot.service

# Check recent logs
tail -20 ~/second-brain/bot.log

# Check cron logs (wait a minute)
tail -20 ~/second-brain/cron.log
```

Send a message to your bot on Telegram - you should get a response!

---

## First Steps

### 1. Send Your First Message

Open Telegram and find your bot. Try:

```
Hello! This is my first message.
```

The bot should classify it and respond with where it was stored.

### 2. Try Different Message Types

**Knowledge entry:**
```
John's birthday is May 15th
```

**Diary entry:**
```
Today was productive. Finished the project proposal.
```

**Reminder:**
```
Remind me to call the dentist tomorrow at 3pm
```

**Voice message:**
Record and send a voice message - it will be transcribed and stored.

### 3. Explore Commands

Try each command:
- `/help` - Full command list
- `/today` - Today's journal and reminders
- `/search birthday` - Semantic search across all content
- `/reminders` - See upcoming reminders
- `/inbox` - Review low-confidence items
- `/export` - Download complete backup (recommended to test!)

### 4. Review Your Data

Your data is stored in:
```
second-brain/
├── brain/
│   ├── people.json      # People facts
│   ├── projects.json    # Project info
│   ├── ideas.json       # Ideas and thoughts
│   ├── admin.json       # Admin tasks
│   ├── inbox.json       # Unclassified items
│   └── reminders.json   # Your reminders
└── journal/
    └── entries/YYYY/MM/DD.md  # Daily journal entries
```

You can view these files directly:
```bash
# See all people entries
cat brain/people.json

# See today's journal
cat journal/entries/$(date +%Y/%m/%d).md
```

### 5. Backup Your Data

**Important:** Regularly backup your data!

```
/export
```

This creates a complete ZIP backup and sends it via Telegram. The backup includes:
- All knowledge base entries (brain/*.json)
- All journal entries and audio files
- Embeddings and indexes

**Recommended:** Run `/export` weekly or after adding important entries.

### 6. Customize Settings

Edit `config.py` to adjust:
```python
CONFIDENCE_THRESHOLD = 0.7  # Classification confidence (0.0-1.0)
DIGEST_HOUR = 9             # Daily digest time (24-hour format)
DEFAULT_REMINDER_HOUR = 9   # Default reminder time
WHISPER_MODEL = "base"      # Whisper model size
```

Restart the bot after changes:
```bash
# Local
# Press Ctrl+C and run: python bot-listener.py

# Production
sudo systemctl restart second-brain-bot.service
```

---

## Troubleshooting

### Bot Not Responding

**Check if bot is running:**
```bash
# Local
# Look for python process
ps aux | grep bot-listener

# Production
sudo systemctl status second-brain-bot.service
```

**Check logs:**
```bash
# View recent logs
tail -50 bot.log

# Follow logs in real-time
tail -f bot.log
```

**Restart bot:**
```bash
# Local
# Press Ctrl+C and run again: python bot-listener.py

# Production
sudo systemctl restart second-brain-bot.service
```

### Voice Messages Not Working

**Verify FFmpeg is installed:**
```bash
ffmpeg -version
```

**Verify Whisper is installed:**
```bash
python -c "import whisper; print('Whisper OK')"
```

**Check audio directory permissions:**
```bash
ls -la journal/audio/
# Should be writable by your user
```

### Classification Seems Wrong

**Check inbox for low-confidence items:**
```
/inbox
```

Items with <70% confidence go to inbox for manual review.

**Move items to correct category:**
Reply to a bot message with the correct category name:
```
people
projects
ideas
admin
```

### API Errors

**"Anthropic API error" messages:**
- Check your API key is correct in `.env`
- Verify you have credits in your Anthropic account
- Check https://status.anthropic.com for API status

**"Telegram API error":**
- Check your bot token is correct in `.env`
- Ensure bot is not blocked by you
- Try creating a new conversation with the bot

### Reminders Not Sending

**Verify cron job is running:**
```bash
# Check cron logs
tail -f cron.log

# Manually trigger reminder check
cd ~/second-brain
source venv/bin/activate
python brain-processor.py YOUR_CHAT_ID --reminders
```

**Check reminder file:**
```bash
cat brain/reminders.json
# Should show pending reminders
```

### Disk Space Issues (Raspberry Pi)

Voice messages and journal entries can accumulate:

**Check disk usage:**
```bash
df -h
du -sh ~/second-brain/*
```

**Clean old audio files (older than 90 days):**
```bash
find ~/second-brain/journal/audio -name "*.ogg" -mtime +90 -delete
```

### Permission Denied Errors

**Fix directory permissions:**
```bash
cd ~/second-brain
chmod 755 brain journal
chmod 644 brain/*.json
```

### Memory Issues (Raspberry Pi)

Whisper can use significant memory. If bot crashes:

**Use smaller Whisper model:**
Edit `config.py`:
```python
WHISPER_MODEL = "tiny"  # Much lighter than "base"
```

**Monitor memory:**
```bash
free -h
```

---

## Updating the Bot

When new features are added:

```bash
# Stop bot
sudo systemctl stop second-brain-bot.service  # Production
# OR press Ctrl+C (Local)

# Update code
cd ~/second-brain
git pull

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Restart bot
sudo systemctl start second-brain-bot.service  # Production
# OR python bot-listener.py (Local)
```

---

## Getting Help

- **Issues:** [GitHub Issues](https://github.com/sebasfavaron/second-brain/issues)
- **Discussions:** [GitHub Discussions](https://github.com/sebasfavaron/second-brain/discussions)
- **Logs:** Always include logs when asking for help:
  ```bash
  tail -100 bot.log > debug.txt
  ```

---

## Next Steps

Once you're comfortable with the basics:

1. Read [NEXT_STEPS.md](NEXT_STEPS.md) for planned enhancements
2. Set up regular backups (see NEXT_STEPS.md #1)
3. Explore the codebase and customize to your needs
4. Consider contributing improvements back to the project

**Enjoy your Second Brain!** 🧠✨
