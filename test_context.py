"""Simple test for context enrichment."""
import json
from storage import create_entry, get_all_entries
from context_manager import enrich_context, load_context
from classifier import classify_message


def test_basic_flow():
    """Test the basic context enrichment flow."""
    print("Testing context enrichment flow...\n")

    # 1. Add a test entry to admin
    print("1. Creating test admin entry...")
    entry = create_entry(
        category="admin",
        raw_message="Doctor appointment on Tuesday at 3pm",
        confidence=0.9,
        chat_id=12345,
        message_id=1,
    )
    print(f"   Created entry: {entry['id']}")

    # 2. Enrich context with this entry
    print("\n2. Enriching admin context...")
    try:
        enrich_context("admin", entry)
        print("   ✓ Context enriched")
    except Exception as e:
        print(f"   ✗ Enrichment failed: {e}")

    # 3. Load and display context
    print("\n3. Loading admin context...")
    context = load_context("admin")
    print(f"   Context length: {len(context.split())} words")
    print(f"   Content preview:\n{context[:200]}...")

    # 4. Test classification with context
    print("\n4. Testing classification with context...")
    result = classify_message("Meeting with doctor next Tuesday", enable_context=True)
    print(f"   Category: {result.get('category')}")
    print(f"   Confidence: {result.get('confidence')}")
    print(f"   Reasoning: {result.get('reasoning')}")

    # 5. Test classification without context
    print("\n5. Testing classification without context (for comparison)...")
    result_no_ctx = classify_message("Meeting with doctor next Tuesday", enable_context=False)
    print(f"   Category: {result_no_ctx.get('category')}")
    print(f"   Confidence: {result_no_ctx.get('confidence')}")
    print(f"   Reasoning: {result_no_ctx.get('reasoning')}")

    print("\n✓ Test completed!")


if __name__ == "__main__":
    test_basic_flow()
