"""
Diary-Reminder Bridge: AI reasoning to connect diary entries with reminders.

Uses Haiku for cost-efficient analysis (~$0.0003/call).
"""
import json
import logging
from typing import List, Dict

from config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-20250414"


def _get_client():
    """Get Anthropic client."""
    from anthropic import Anthropic
    return Anthropic(api_key=ANTHROPIC_API_KEY)


def review_diary_against_reminders(diary_content: str, pending_reminders: List[Dict]) -> Dict:
    """
    After a diary write, check if any pending reminders are now fulfilled.

    Conservative: only marks complete when diary clearly says task was done.

    Args:
        diary_content: The diary entry just written
        pending_reminders: List of pending reminder dicts

    Returns:
        {
            "auto_complete": [{"reminder_id": ..., "reason": ...}],
            "relevant_mentions": [{"reminder_id": ..., "connection": ...}]
        }
    """
    if not pending_reminders or not diary_content.strip():
        return {"auto_complete": [], "relevant_mentions": []}

    # Build reminder summaries for the prompt
    reminder_list = []
    for r in pending_reminders:
        reminder_list.append({
            "id": r["id"],
            "content": r["content"],
            "trigger_time": r.get("trigger_time", "")
        })

    prompt = f"""Analyze this diary entry against pending reminders.

DIARY ENTRY:
{diary_content}

PENDING REMINDERS:
{json.dumps(reminder_list, indent=2)}

Determine:
1. auto_complete: Reminders clearly fulfilled by the diary (e.g., diary says "called the dentist" and reminder is "call dentist"). Be CONSERVATIVE - only if the diary clearly confirms the task was done.
2. relevant_mentions: Reminders that are mentioned or related but NOT clearly completed (e.g., diary mentions a topic related to a reminder).

Return JSON only:
{{"auto_complete": [{{"reminder_id": "...", "reason": "..."}}], "relevant_mentions": [{{"reminder_id": "...", "connection": "..."}}]}}"""

    try:
        response = _get_client().messages.create(
            model=HAIKU_MODEL,
            max_tokens=500,
            system="You analyze diary entries against reminders. Return only valid JSON. Be conservative about auto-completing - only when the diary clearly confirms the task is done.",
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)
        return {
            "auto_complete": result.get("auto_complete", []),
            "relevant_mentions": result.get("relevant_mentions", [])
        }

    except Exception as e:
        logger.error(f"review_diary_against_reminders failed: {e}")
        return {"auto_complete": [], "relevant_mentions": []}


def enrich_reminder_delivery(reminder: Dict, recent_diary: str, related_knowledge: List[Dict]) -> str:
    """
    When a reminder triggers, add diary/knowledge context to the notification.

    Args:
        reminder: The triggered reminder dict
        recent_diary: Recent diary content (last few days)
        related_knowledge: Related knowledge entries

    Returns:
        Enriched notification text (plain text, not HTML)
    """
    content = reminder.get("content", "")

    # If no context available, return bare content
    if not recent_diary.strip() and not related_knowledge:
        return content

    knowledge_text = ""
    if related_knowledge:
        knowledge_text = "\n".join(
            f"- [{e.get('_category', 'unknown')}] {e.get('raw_message', '')}"
            for e in related_knowledge[:5]
        )

    prompt = f"""Add brief context to this reminder notification using diary and knowledge data.

REMINDER: {content}

RECENT DIARY (last 3 days):
{recent_diary if recent_diary.strip() else "(no recent diary entries)"}

RELATED KNOWLEDGE:
{knowledge_text if knowledge_text else "(none found)"}

Write a 1-2 sentence enriched reminder. Start with the original reminder text, then add relevant context.
Example: "Call Juan - last mentioned in diary 2 days ago re: project deadline."
Keep it brief and useful. If no relevant context, just return the original reminder text."""

    try:
        response = _get_client().messages.create(
            model=HAIKU_MODEL,
            max_tokens=200,
            system="You enrich reminder notifications with brief, relevant context. Be concise.",
            messages=[{"role": "user", "content": prompt}]
        )

        return response.content[0].text.strip()

    except Exception as e:
        logger.error(f"enrich_reminder_delivery failed: {e}")
        return content


def generate_follow_up_suggestions(recent_diary: str, pending_reminders: List[Dict]) -> List[Dict]:
    """
    Daily review: spot patterns, nudge about forgotten items, suggest actions.

    Args:
        recent_diary: Diary content from last few days
        pending_reminders: All pending reminders

    Returns:
        List of suggestion dicts: [{"suggestion": ..., "type": ..., "related_reminder_id": ...}]
    """
    if not recent_diary.strip() and not pending_reminders:
        return []

    reminder_list = []
    for r in pending_reminders:
        reminder_list.append({
            "id": r["id"],
            "content": r["content"],
            "trigger_time": r.get("trigger_time", "")
        })

    prompt = f"""Review recent diary entries and pending reminders. Generate up to 3 brief follow-up suggestions.

RECENT DIARY (last 3 days):
{recent_diary if recent_diary.strip() else "(no recent diary entries)"}

PENDING REMINDERS:
{json.dumps(reminder_list, indent=2) if reminder_list else "(none)"}

Look for:
- Tasks mentioned in diary but not tracked as reminders
- Patterns or recurring themes worth noting
- Reminders that might need attention based on diary context
- Forgotten follow-ups

Return JSON array only (max 3 items):
[{{"suggestion": "...", "type": "follow_up|pattern|nudge|action", "related_reminder_id": "..." or null}}]

If nothing noteworthy, return empty array: []"""

    try:
        response = _get_client().messages.create(
            model=HAIKU_MODEL,
            max_tokens=500,
            system="You generate brief, actionable follow-up suggestions by analyzing diary entries and reminders. Return only valid JSON array. Be selective - only suggest genuinely useful things.",
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        suggestions = json.loads(text)
        if not isinstance(suggestions, list):
            return []
        return suggestions[:3]

    except Exception as e:
        logger.error(f"generate_follow_up_suggestions failed: {e}")
        return []
