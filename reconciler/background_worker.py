"""
background_worker.py
Polls Atlas for pending conflicts every 30 seconds and runs the debate loop.
"""

import time
import sys
import os
import traceback

from dotenv import load_dotenv
load_dotenv()

print("[worker] Starting imports...", flush=True)

try:
    from reconciler.reconciler import adversarial_reconcile
    print("[worker] reconciler imported OK", flush=True)
except Exception as e:
    print(f"[worker] Import failed: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

POLL_INTERVAL_SECONDS = 30


def run_worker(memory_layer):
    print(f"[worker] Starting. Polling every {POLL_INTERVAL_SECONDS}s...", flush=True)

    while True:
        try:
            pending = memory_layer.get_conflict_history(status="pending")

            if pending:
                print(f"[worker] Found {len(pending)} pending conflict(s).", flush=True)

            for conflict in pending:
                try:
                    print(f"[worker] Reconciling: '{conflict['memory_a_content'][:40]}...' "
                          f"vs '{conflict['memory_b_content'][:40]}...'", flush=True)

                    memory_a = {
                        "_id":         conflict["memory_a_id"],
                        "content":     conflict["memory_a_content"],
                        "timestamp":   conflict.get("detected_at"),
                        "confidence":  0.8,
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

                    print(f"[worker] Resolved → '{result['resolved_content'][:60]}...'", flush=True)

                except Exception as e:
                    print(f"[worker] Error on conflict {conflict.get('_id')}: {e}", flush=True)
                    traceback.print_exc()

        except Exception as e:
            print(f"[worker] Poll error: {e}", flush=True)
            traceback.print_exc()

        time.sleep(POLL_INTERVAL_SECONDS)


try:
    import memory_layer.memories as memory_layer_module
    print("[worker] memory_layer imported OK", flush=True)
    run_worker(memory_layer_module)
except ImportError as e:
    print(f"[worker] Could not import memory_layer: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"[worker] Fatal error: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)