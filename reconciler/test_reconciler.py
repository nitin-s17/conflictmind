"""
test_reconciler.py
Person 2 — Day 6 tuning session.

Run all 15 conflict pairs through the full pipeline.
YOU must read each resolved memory and judge if it makes sense.

Usage:
    python test_reconciler.py

For each test case you will see:
    - The two conflicting memories
    - Memory A's argument
    - Memory B's argument
    - The judge's reasoning
    - The final resolved memory
    - ✅ or ❌ based on your judgment
"""

from datetime import datetime, timedelta
from conflict_classifier import classify_conflict
from reconciler import adversarial_reconcile

# ─── Test conflict pairs ──────────────────────────────────────────────────────
# Format: (memory_a, memory_b, description_of_expected_outcome)

def make_memory(content, days_ago=30, confidence=0.8, frequency=3, memory_type="semantic"):
    return {
        "content": content,
        "timestamp": datetime.utcnow() - timedelta(days=days_ago),
        "confidence": confidence,
        "frequency": frequency,
        "memory_type": memory_type,
    }


TEST_PAIRS = [
    # (memory_a, memory_b, what_good_resolution_looks_like)
    (
        make_memory("User prefers bullet points", days_ago=60, frequency=5),
        make_memory("User asked for prose narrative", days_ago=2, frequency=1),
        "Should acknowledge both: generally prefers bullets but sometimes wants prose"
    ),
    (
        make_memory("User is vegetarian", days_ago=90, confidence=0.95, frequency=8),
        make_memory("User mentioned eating chicken last week", days_ago=5, frequency=1),
        "High-frequency older memory should probably win — one-off vs established fact"
    ),
    (
        make_memory("User works best in the morning", days_ago=45, frequency=4),
        make_memory("User said they do their best work late at night", days_ago=3, frequency=2),
        "Recent memory should influence — maybe user's schedule changed"
    ),
    (
        make_memory("User hates small talk", days_ago=30, frequency=6),
        make_memory("User spent 10 minutes chatting about weekend plans", days_ago=1, frequency=1),
        "General preference should win — one-off exception noted"
    ),
    (
        make_memory("User wants direct, harsh feedback", days_ago=20, frequency=3),
        make_memory("User seemed upset when given harsh criticism", days_ago=2, frequency=2),
        "Should merge — direct feedback but delivered constructively"
    ),
    (
        make_memory("User prefers Python", days_ago=60, frequency=10, confidence=0.95),
        make_memory("User asked to write everything in JavaScript", days_ago=1, frequency=1),
        "Should merge — Python generally but JS for this context"
    ),
    (
        make_memory("User is an introvert who avoids meetings", days_ago=40, frequency=5),
        make_memory("User mentioned enjoying the team standup today", days_ago=1, frequency=1),
        "General preference should hold — standups are short/structured, different from general meetings"
    ),
    (
        make_memory("User wants concise code without comments", days_ago=30, frequency=4),
        make_memory("User asked for heavily commented code with explanations", days_ago=3, frequency=2),
        "Should merge — concise by default, but comments when explaining to others"
    ),
    (
        make_memory("User dislikes emojis in responses", days_ago=20, frequency=7, confidence=0.9),
        make_memory("User used 5 emojis in last message", days_ago=1, frequency=1),
        "High-confidence older memory should win — using emojis ≠ wanting them in responses"
    ),
    (
        make_memory("User is an early-career developer", days_ago=180, confidence=0.6, frequency=2),
        make_memory("User mentioned having 8 years of experience", days_ago=5, frequency=1),
        "Newer memory should win — old low-confidence memory was probably wrong"
    ),
    (
        make_memory("User prefers short answers", days_ago=90, frequency=3),
        make_memory("User always asks for very detailed breakdowns on technical topics", days_ago=10, frequency=5),
        "Both valid — general preference for short, but detailed for technical. Should merge cleanly."
    ),
    (
        make_memory("User works in fintech", days_ago=60, frequency=8, confidence=0.95),
        make_memory("User mentioned switching to a healthcare startup", days_ago=3, frequency=1),
        "Recent info should update — but note the transition"
    ),
    (
        make_memory("User speaks English as first language", days_ago=120, frequency=2),
        make_memory("User asked for responses in French", days_ago=1, frequency=1),
        "Context-dependent — may be bilingual or testing. Should not fully overwrite."
    ),
    (
        make_memory("User is a night owl", days_ago=30, frequency=6),
        make_memory("User mentioned their 6am gym routine", days_ago=2, frequency=2),
        "Should merge — possibly different on weekdays vs weekends"
    ),
    (
        make_memory("User prefers tabs over spaces", days_ago=45, frequency=9, confidence=0.95),
        make_memory("User's code submission used 4-space indentation", days_ago=1, frequency=1),
        "Strong older pattern should win — one file doesn't override consistent preference"
    ),
]


def divider():
    print("\n" + "─" * 70)


def run_test(idx, memory_a, memory_b, expected):
    divider()
    print(f"\nTest {idx + 1}/15")
    print(f"Memory A: \"{memory_a['content']}\"")
    print(f"  (stored {(datetime.utcnow() - memory_a['timestamp']).days}d ago, "
          f"freq={memory_a['frequency']}, conf={memory_a['confidence']})")
    print(f"Memory B: \"{memory_b['content']}\"")
    print(f"  (stored {(datetime.utcnow() - memory_b['timestamp']).days}d ago, "
          f"freq={memory_b['frequency']}, conf={memory_b['confidence']})")
    print(f"\nExpected outcome: {expected}")

    # Step 1 — classify
    print("\n[1/2] Classifying conflict...")
    classification = classify_conflict(memory_a, memory_b)
    print(f"  → {classification['classification']} "
          f"(confidence: {classification['confidence']:.2f})")
    print(f"  → Reason: {classification['reason']}")

    if classification["classification"] != "contradictory":
        print(f"\n  ⚠️  Not classified as contradictory — reconciler skipped.")
        print(f"  Is this correct? If not, the detection threshold may need lowering.")
        return

    # Step 2 — reconcile
    print("\n[2/2] Running adversarial debate...")
    result = adversarial_reconcile(memory_a, memory_b)

    print(f"\n  A argued: {result['argument_a']}")
    print(f"\n  B argued: {result['argument_b']}")
    print(f"\n  Judge: {result['judge_reasoning']}")
    print(f"\n  Winner: {result['winner'].upper()}")
    print(f"\n  ✦ RESOLVED MEMORY: \"{result['resolved_content']}\"")
    print(f"  Resolution confidence: {result['confidence_in_resolution']:.2f}")

    print("\n  👉 Does this resolution make sense? (y/n): ", end="")
    answer = input().strip().lower()
    if answer == "y":
        print("  ✅ Marked as correct")
    else:
        print("  ❌ Marked as incorrect — note what felt wrong and tell Person 2 to adjust the judge prompt")


if __name__ == "__main__":
    print("ConflictMind — Reconciler Tuning Session")
    print("Run through all 15 pairs and mark each resolution as correct or not.")
    print("Target: 12 of 15 correct before moving to Day 7.\n")

    passed = 0
    failed = 0

    for i, (a, b, expected) in enumerate(TEST_PAIRS):
        try:
            run_test(i, a, b, expected)
        except KeyboardInterrupt:
            print("\n\nStopped early.")
            break
        except Exception as e:
            print(f"\n  💥 Error on test {i+1}: {e}")

    divider()
    print("\nTuning session complete.")
    print("If less than 12/15 feel correct, paste the failing cases to your Claude")
    print("and ask: 'Adjust the judge prompt to fix these specific resolutions'")
