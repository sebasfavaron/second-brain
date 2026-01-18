"""Claude API classifier for message categorization."""
import json
from anthropic import Anthropic

from config import ANTHROPIC_API_KEY, CATEGORIES, CONFIDENCE_THRESHOLD

client = None

def get_client():
    """Lazy init Anthropic client."""
    global client
    if client is None:
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set in .env")
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return client


SYSTEM_PROMPT = f"""You are a personal knowledge classifier for a "second brain" system.

Your job is to categorize incoming messages into one of these categories:
- people: Information about specific people (names, contact info, relationships, facts about them)
- projects: Work tasks, project updates, todos, deadlines, technical notes
- ideas: Creative thoughts, future plans, random insights, things to explore
- admin: Logistics, appointments, locations, reminders, household tasks

Respond with JSON only:
{{"category": "<category>", "confidence": <0.0-1.0>, "reasoning": "<brief explanation>"}}

Rules:
- Be decisive. Most messages clearly belong to one category.
- High confidence (0.8+) for clear categorization.
- Medium confidence (0.6-0.8) for reasonable guesses.
- Low confidence (<0.6) when genuinely ambiguous.
- If a message mentions a person but is primarily about a project, classify as "projects".
- Single-word messages or very short ones get lower confidence.
"""


def classify_message(message: str, enable_context: bool = True) -> dict:
    """
    Classify a message using Claude.

    Args:
        message: The message to classify
        enable_context: Whether to load and inject historical context

    Returns:
        dict with keys: category, confidence, reasoning
    """
    if not message or not message.strip():
        return {
            "category": "inbox",
            "confidence": 0.0,
            "reasoning": "Empty message"
        }

    # Prepare user content with optional context
    user_content = message

    if enable_context:
        try:
            from context_manager import load_context
            context_sections = []
            for category in CATEGORIES:
                ctx = load_context(category)
                if ctx and len(ctx.strip()) > 20:
                    context_sections.append(f"## {category.title()} Context\n{ctx}")

            if context_sections:
                context_block = "\n\n".join(context_sections)
                user_content = f"[BACKGROUND CONTEXT]\n{context_block}\n\n[MESSAGE TO CLASSIFY]\n{message}"
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Context load failed: {e}")

    try:
        response = get_client().messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}]
        )

        content = response.content[0].text.strip()

        # Parse JSON response
        # Handle potential markdown code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        result = json.loads(content)

        # Validate category
        if result.get("category") not in CATEGORIES:
            result["category"] = "inbox"
            result["confidence"] = min(result.get("confidence", 0.5), 0.5)

        return result

    except json.JSONDecodeError as e:
        return {
            "category": "inbox",
            "confidence": 0.0,
            "reasoning": f"Failed to parse classifier response: {e}"
        }
    except Exception as e:
        return {
            "category": "inbox",
            "confidence": 0.0,
            "reasoning": f"Classification error: {e}"
        }


def should_go_to_inbox(result: dict) -> bool:
    """Check if result should go to inbox due to low confidence."""
    return result.get("confidence", 0) < CONFIDENCE_THRESHOLD
