"""Bootstrap context files from existing entries."""
from context_manager import bootstrap_context
from config import CATEGORIES


if __name__ == "__main__":
    print("Bootstrapping context files...")
    for category in CATEGORIES:
        print(f"  {category}...", end=" ")
        try:
            bootstrap_context(category)
            print("✓")
        except Exception as e:
            print(f"✗ ({e})")

    print("\nDone! Context files created in brain/")
