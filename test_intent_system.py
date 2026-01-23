#!/usr/bin/env python3
"""
Quick test script to verify the AI-driven intent system.

Tests the determine_intent function with various scenarios.
"""
import asyncio
import sys
from bot_listener import determine_intent, gather_context_for_intent

async def test_intent_determination():
    """Test various intent scenarios."""

    test_cases = [
        {
            "name": "New entry - person",
            "message": "Felipe is my business partner",
            "reply_context": None,
            "expected_action": "store",
            "expected_category": "people"
        },
        {
            "name": "Category correction",
            "message": "projects",
            "reply_context": {
                "entry": {"id": "test-123", "raw_message": "Some message", "confidence": 0.9},
                "category": "people",
                "bot_confirmation": "people (90%)"
            },
            "expected_action": "correct",
            "expected_category": "projects"
        },
        {
            "name": "Delete request",
            "message": "no hace falta",
            "reply_context": {
                "entry": {"id": "test-456", "raw_message": "Some entry", "confidence": 0.8},
                "category": "inbox",
                "bot_confirmation": "inbox (80%)"
            },
            "expected_action": "delete",
            "expected_category": None
        },
        {
            "name": "Acknowledgment - ignore",
            "message": "ok gracias",
            "reply_context": None,
            "expected_action": "ignore",
            "expected_category": None
        },
        {
            "name": "Question - respond",
            "message": "what did I save about Felipe?",
            "reply_context": None,
            "expected_action": "respond",
            "expected_category": None
        }
    ]

    print("Testing AI Intent Determination System")
    print("=" * 60)

    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['name']}")
        print(f"Message: {test['message']}")
        print(f"Has reply context: {test['reply_context'] is not None}")

        try:
            intent = await determine_intent(test['message'], test['reply_context'])

            print(f"Result:")
            print(f"  Action: {intent['action']} (expected: {test['expected_action']})")
            print(f"  Category: {intent.get('category')} (expected: {test['expected_category']})")
            print(f"  Confidence: {intent.get('confidence')}")
            print(f"  Reasoning: {intent.get('reasoning')}")

            # Check if result matches expectations
            action_match = intent['action'] == test['expected_action']
            category_match = intent.get('category') == test['expected_category']

            if action_match and category_match:
                print("  ✓ PASS")
            else:
                print("  ✗ MISMATCH")
                if not action_match:
                    print(f"    Expected action: {test['expected_action']}, got: {intent['action']}")
                if not category_match:
                    print(f"    Expected category: {test['expected_category']}, got: {intent.get('category')}")

        except Exception as e:
            print(f"  ✗ ERROR: {e}")

    print("\n" + "=" * 60)
    print("Testing complete")

if __name__ == "__main__":
    try:
        asyncio.run(test_intent_determination())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        sys.exit(1)
