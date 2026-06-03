"""
background_worker.py
Person 2 — Day 7 deliverable.

Polls Atlas for pending conflicts every 30 seconds and runs the debate loop.
Run this as a separate process alongside the Flask server.

Usage:
    python background_worker.py
"""

import time
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Conflict Mind'))

from dotenv import load_dotenv
load_dotenv()

from reconciler import adversarial_reconcile

POLL_INTERVAL_SECONDS = 30


def run_worker(memory_layer):
    """
    Main worker loop. Polls for pending conflicts and reconciles them.
    """
    print(f"[worker] Starting. Polling every {POLL_INTERVAL_SECONDS}s...")

    while True:
        try:
            pending = memory_layer.get_conflict_history(status="pending")

            if pending:
                print(f"[worker] Found {len(pending)} pending conflict(s).")

            for conflict in pending:
                try:
                    print(f"[worker] Reconciling: '{conflict['memory_a_content'][:40]}...' "
                          f"vs '{conflict['memory_b_content'][:40]}...'")

                    # Rebuild memory dicts for the reconciler
                    memory_a = {
                        "_id":         conflict["memory_a_id"],
                        "content":     conflict["memory_a_content"],
                        "timestamp":   conflict.get("detected_at"),
                        "confidence":  0.8,   # fallback — memory layer doesn't return this
                        "frequency":   0,
                        "memory_type": "semantic",
                    }
                    memory_b = {
                        "_id":         conflict["memory_b_id"],
                        "content":     conflict["memory_b_content"],
                        "timestamp":   conflict.get("detected_at"),
                        "confidence":  0.8,
                        "frequency":   0,
                        "memory_type": "semantic",
                    }

                    result = adversarial_reconcile(memory_a, memory_b)

                    memory_layer.save_reconciliation_result(
                        conflict_pair_id=conflict["_id"],
                        debate_transcript={
                            "argument_a":      result["argument_a"],
                            "argument_b":      result["argument_b"],
                            "judge_reasoning": result["judge_reasoning"],
                            "winner":          result["winner"],
                        },
                        resolved_content=result["resolved_content"],
                        resolved_memory_type="semantic",
                    )

                    print(f"[worker] Resolved → '{result['resolved_content'][:60]}...'")

                except Exception as e:
                    print(f"[worker] Error on conflict {conflict.get('_id')}: {e}")

        except Exception as e:
            print(f"[worker] Poll error: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    # Import memory layer — adjust path to match repo structure
    try:
        from memory_layer.memories import (
            get_conflict_history,
            save_reconciliation_result,
        )
        import memory_layer.memories as memory_layer_module
        run_worker(memory_layer_module)
    except ImportError as e:
        print(f"[worker] Could not import memory_layer: {e}")
        print("Make sure you run this from the project root: python reconciler/background_worker.py")
        sys.exit(1)
