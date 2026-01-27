# Next Steps & Enhancement Roadmap

This document outlines planned improvements for the Second Brain project, prioritized by impact and implementation complexity.

---

## 1. Backup & Export 📦

**Priority:** CRITICAL
**Effort:** 30 minutes
**Impact:** HIGH - Data safety

### Problem
No backup mechanism. All data at risk if RPi/disk fails.

### Implementation
1. Add `/export` command
2. Create ZIP containing:
   - `brain/*.json`
   - `journal/**/*.md`
   - `journal/audio/**/*.ogg`
   - `index.json`
3. Upload to Telegram as document
4. Optional: Auto-backup to S3/Drive daily via cron

### Code Changes
```python
# New file: backup_manager.py
def create_backup() -> Path:
    """Create timestamped ZIP of all data."""

async def handle_export(update, context):
    """Send backup ZIP to user."""
```

### Acceptance Criteria
- [ ] `/export` creates complete backup
- [ ] ZIP includes all categories and journal
- [ ] File sent via Telegram (or download link)
- [ ] Optional: Daily auto-backup via cron

---

## 2. Semantic Search 🔍

**Priority:** HIGH
**Effort:** 2-3 hours
**Impact:** HIGH - Much better search

### Problem
Current grep-based search misses:
- Synonyms ("birthday" vs "cumpleaños")
- Semantic similarity ("meeting" vs "call" vs "chat")
- Multilingual content

### Implementation
**Use Claude Haiku for embeddings (cheaper):**

1. Generate embeddings on entry creation
2. Store embeddings in separate file: `brain/embeddings.json`
3. Update search to use cosine similarity
4. Fallback to grep if embeddings unavailable

### Code Changes
```python
# classifier.py - add embedding generation
def generate_embedding(text: str) -> list[float]:
    """Generate embedding using Claude Haiku."""
    client = get_client()
    # Use Haiku for cost efficiency
    response = client.messages.create(
        model="claude-haiku-4-20250514",
        ...
    )

# storage.py - store embeddings
def store_embedding(entry_id: str, embedding: list[float]):
    """Store embedding for semantic search."""

# agent_tools.py - semantic search
def semantic_search(query: str, limit: int = 10):
    """Search using embedding similarity."""
```

### Cost Estimate
- Haiku: ~$0.25 per 1M input tokens
- Average entry: ~50 tokens
- 1000 entries: ~$0.01
- Very affordable with Haiku

### Acceptance Criteria
- [ ] Embeddings generated on entry creation (Haiku)
- [ ] Search finds semantically similar entries
- [ ] Works across languages
- [ ] Graceful fallback to grep

---

## 3. Analytics & Insights 📊

**Priority:** HIGH
**Effort:** 1-2 hours
**Impact:** MEDIUM - Nice visibility

### Problem
No visibility into usage patterns or trends.

### Implementation
1. Add `/stats` command - overall statistics
2. Add `/insights` command - AI-generated insights (weekly)
3. Track metrics:
   - Entries per category
   - Journal streak (consecutive days)
   - Most mentioned people/projects
   - Busiest times of day
   - Weekly/monthly trends

### Code Changes
```python
# New file: analytics.py
def get_stats() -> dict:
    """Calculate usage statistics."""
    return {
        "total_entries": count_all_entries(),
        "by_category": count_by_category(),
        "journal_streak": calculate_streak(),
        "top_people": extract_top_mentions("people"),
        "busiest_hour": analyze_timestamps(),
    }

def generate_insights(timeframe: str = "week") -> str:
    """Use Claude to generate insights from stats."""

# bot-listener.py
async def handle_stats(update, context):
    """Show usage statistics."""

async def handle_insights(update, context):
    """Show AI-generated insights."""
```

### Commands
- `/stats` - Numbers and charts (text-based)
- `/insights` - AI analysis of patterns

### Acceptance Criteria
- [ ] `/stats` shows comprehensive statistics
- [ ] `/insights` provides meaningful patterns
- [ ] Journal streak calculation works
- [ ] Top mentions extracted correctly

---

## 4. Relationships & Connections 🔗

**Priority:** MEDIUM
**Effort:** 4-5 hours
**Impact:** HIGH - Rich context

### Problem
No explicit relationship modeling. Can't answer:
- "Who works on ProjectX?"
- "What projects involve Juan?"
- "Timeline of interactions with Felipe"

### Implementation
1. Extract relationships from entries:
   - Person → Project
   - Person → Person
   - Project → Project
2. Store in graph structure: `brain/relationships.json`
3. Commands:
   - `/connections <person>` - Show relationship graph
   - `/timeline <person>` - Show interaction history
4. Visualize in text (ASCII art) or future web UI

### Schema
```json
{
  "relationships": [
    {
      "from": "Juan",
      "to": "ProjectX",
      "type": "works_on",
      "strength": 5,
      "last_mentioned": "2026-01-27"
    }
  ]
}
```

### Code Changes
```python
# New file: relationship_manager.py
def extract_relationships(entry: dict) -> list[dict]:
    """Use Claude to extract relationships from entry."""

def get_connections(entity: str) -> dict:
    """Get all connections for person/project."""

def build_graph(entity: str, depth: int = 2) -> str:
    """Build ASCII graph of connections."""
```

### Acceptance Criteria
- [ ] Relationships extracted automatically
- [ ] `/connections` shows related entities
- [ ] `/timeline` shows chronological interactions
- [ ] Graph stored and queryable

---

## 5. Tags & Labels 🏷️

**Priority:** MEDIUM
**Effort:** 1-2 hours
**Impact:** MEDIUM - Better organization

### Problem
Categories are rigid. Can't cross-cut:
- Entry about work deadline that's also urgent
- Personal health topic that's also a project

### Implementation
1. Parse hashtags from messages: `#work #urgent`
2. Store tags in entry: `"tags": ["work", "urgent"]`
3. Add tag-based search
4. Commands:
   - `/tags` - List all tags with counts
   - `/search #work #urgent` - Find by tags

### Code Changes
```python
# storage.py
def parse_hashtags(text: str) -> list[str]:
    """Extract #hashtags from text."""
    return re.findall(r'#(\w+)', text)

def create_entry(..., tags: list[str] = None):
    """Add tags field to entry."""

# agent_tools.py
def search_by_tags(tags: list[str]) -> list[dict]:
    """Search entries by tags."""
```

### Acceptance Criteria
- [ ] Hashtags automatically parsed and stored
- [ ] `/tags` shows all tags with counts
- [ ] Can search by single or multiple tags
- [ ] Tags work alongside categories

---

## 6. Templates 📝

**Priority:** MEDIUM
**Effort:** 2-3 hours
**Impact:** MEDIUM - Better consistency

### Problem
Repetitive entry types have no structure:
- Daily standup
- Meeting notes
- Weekly reviews

### Implementation
1. Define templates in `brain/templates.json`
2. Command: `/template <name>` starts structured entry
3. Bot guides through template fields
4. Store completed template as regular entry + metadata

### Template Examples
```json
{
  "standup": {
    "name": "Daily Standup",
    "fields": [
      {"name": "yesterday", "prompt": "What did you do yesterday?"},
      {"name": "today", "prompt": "What will you do today?"},
      {"name": "blockers", "prompt": "Any blockers?"}
    ]
  },
  "meeting": {
    "name": "Meeting Notes",
    "fields": [
      {"name": "attendees", "prompt": "Who attended?"},
      {"name": "topics", "prompt": "Topics discussed?"},
      {"name": "decisions", "prompt": "Decisions made?"},
      {"name": "actions", "prompt": "Action items?"}
    ]
  }
}
```

### Code Changes
```python
# New file: template_manager.py
def load_templates() -> dict:
    """Load available templates."""

def start_template(template_name: str, user_id: int):
    """Begin template-guided entry."""

def process_template_response(user_id: int, response: str):
    """Handle user responses to template prompts."""

# bot-listener.py
async def handle_template(update, context):
    """Start template-based entry."""
```

### Acceptance Criteria
- [ ] `/template` lists available templates
- [ ] `/template standup` starts guided entry
- [ ] Bot prompts for each field
- [ ] Completed template saved as entry
- [ ] Users can define custom templates

---

## 7. Smart Reminders ⏰

**Priority:** MEDIUM
**Effort:** 3-4 hours
**Impact:** MEDIUM - Better UX

### Problem
Current reminders are basic:
- No snooze
- No natural language parsing ("in 2 hours")
- No context-aware triggers

### Implementation
1. **Snooze:** Reply to reminder with time
2. **Natural language:** "Remind me in 2 hours"
3. **Smart defaults:**
   - Morning tasks → 9 AM
   - Afternoon → 2 PM
   - Evening → 6 PM
4. **Follow-up:** Ask if reminder was completed

### Code Changes
```python
# reminder_storage.py
def snooze_reminder(reminder_id: str, duration: str):
    """Snooze reminder for specified duration."""

def parse_natural_time(text: str) -> datetime:
    """Parse 'in 2 hours', 'tomorrow', 'next week'."""

# brain-processor.py
async def send_reminder_with_actions(reminder: dict):
    """Send reminder with snooze/complete buttons."""
```

### Acceptance Criteria
- [ ] Can snooze reminders via reply
- [ ] Parses "in X hours/days"
- [ ] Smart defaults based on time of day
- [ ] Follow-up asks about completion
- [ ] Inline buttons for snooze/complete

---

## 8. Error Handling & Resilience 🛡️

**Priority:** HIGH
**Effort:** 2-3 hours
**Impact:** HIGH - Reliability

### Problem
If Claude API is down or slow:
- Bot becomes unresponsive
- Messages lost
- No user feedback

### Implementation
1. **Message queue:** Store incoming messages
2. **Retry logic:** Exponential backoff on API failures
3. **Fallback classification:** Basic keyword matching
4. **Status monitoring:** Health check endpoint
5. **User feedback:** "Processing, this may take a moment..."

### Code Changes
```python
# New file: message_queue.py
def enqueue_message(chat_id: int, message: str):
    """Queue message for processing."""

def process_queue():
    """Process queued messages with retry."""

# bot-listener.py
async def handle_message_with_retry(update, context):
    """Handle message with error recovery."""
    try:
        # Process with Claude
    except AnthropicAPIError:
        # Fallback classification
        category = fallback_classify(text)
        # Queue for later processing
        enqueue_message(chat_id, text)

# New file: fallback_classifier.py
def fallback_classify(text: str) -> tuple[str, float]:
    """Basic keyword-based classification."""
    # Simple rules when Claude unavailable
```

### Health Checks
```python
# New endpoint: /health
@app.route('/health')
def health_check():
    return {
        "status": "ok",
        "claude_api": check_claude_health(),
        "storage": check_storage_health(),
        "queue_size": get_queue_size()
    }
```

### Acceptance Criteria
- [ ] Messages queued if API fails
- [ ] Retry with exponential backoff
- [ ] Fallback classification when needed
- [ ] User sees status updates
- [ ] Health check endpoint works

---

## Implementation Priority

**Phase 1 - Quick Wins (Week 1):**
1. Backup & Export (Critical)
2. Tags/Labels (Easy, useful)
3. Analytics/Stats (High value)

**Phase 2 - Core Improvements (Week 2-3):**
4. Semantic Search with Haiku (High impact)
5. Error Handling (Reliability)
6. Smart Reminders (UX improvement)

**Phase 3 - Advanced Features (Week 4+):**
7. Templates (Nice to have)
8. Relationships (Complex but powerful)

---

## Cost Considerations

**Using Claude Haiku for semantic search:**
- Current: Only Sonnet for classification (~$3/1M tokens)
- Haiku for embeddings: ~$0.25/1M tokens (12x cheaper)
- Expected usage: <$1/month for typical user

**API Usage Breakdown:**
- Classification: Sonnet (needs reasoning)
- Embeddings: Haiku (simple, cheap)
- Insights: Sonnet (needs analysis)
- Total expected: $2-5/month for active user

---

## Notes

- All features should maintain conversation context
- Keep Telegram as primary interface
- Every feature needs proper error handling
- Write tests for critical paths
- Update README with new features
- Consider rate limiting for API calls
