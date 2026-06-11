"""
background_worker.py
Polls Atlas for pending conflicts every 30 seconds and runs the debate loop.

MULTI-INSTANCE SAFETY:
    Cloud Run may run multiple instances of this service simultaneously.
    Each instance spawns this worker, so multiple workers can pick up the
    same pending conflict at the same time.

    Fix: atomic "claim" step using find_one_and_update before processing.
    Only the worker that successfully flips status "pending" → "processing"
    will proceed. All others see None and skip that conflict.

    Stale processing guard: if a conflict is stuck in "processing" for more
    than 5 minutes (worker crashed mid-flight), it is reset to "pending"
    so it can be retried.
"""

import time
import sys
import os
import traceback
from datetime import datetime, timezone, timedelta

from bson import ObjectId
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
STALE_PROCESSING_MINUTES = 5


def claim_conflict(conflict_id: str, collection) -> bool:
    """
    Atomically flip a conflict from "pending" to "processing".
    Returns True if this worker successfully claimed it, False if
    another worker already claimed or resolved it.

    MongoDB's find_one_and_update is atomic — only one caller wins.
    """
    result = collection.find_one_and_update(
        {
            "_id": ObjectId(conflict_id),
            "status": "pending"         # only claim if still pending
        },
        {"$set": {
            "status": "processing",
            "claimed_at": datetime.now(timezone.utc)
        }}
    )
    return result is not None


def reset_stale_claims(collection) -> None:
    """
    If a worker crashed mid-reconciliation, the conflict stays in
    "processing" forever. Reset any that have been processing for
    longer than STALE_PROCESSING_MINUTES so they can be retried.
    """
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_PROCESSING_MINUTES)
    reset_result = collection.update_many(
        {
            "status": "processing",
            "claimed_at": {"$lt": stale_cutoff}
        },
        {"$set": {"status": "pending"}, "$unset": {"claimed_at": ""}}
    )
    if reset_result.modified_count > 0:
        print(f"[worker] Reset {reset_result.modified_count} stale 'processing' conflict(s) to 'pending'", flush=True)


def run_worker(memory_layer):
    print(f"[worker] Starting. Polling every {POLL_INTERVAL_SECONDS}s...", flush=True)

    # Get direct collection access for atomic claim operations
    from memory_layer.db import get_conflict_pairs_collection

    while True:
        try:
            conflicts_collection = get_conflict_pairs_collection()

            # Reset any conflicts stuck in "processing" from a crashed worker
            reset_stale_claims(conflicts_collection)

            pending = memory_layer.get_conflict_history(status="pending")

            if pending:
                print(f"[worker] Found {len(pending)} pending conflict(s).", flush=True)

            for conflict in pending:
                conflict_id = conflict["_id"]

                # Atomically claim this conflict before processing.
                # If another worker instance already claimed it, skip.
                claimed = claim_conflict(conflict_id, conflicts_collection)
                if not claimed:
                    print(f"[worker] Conflict {conflict_id} already claimed by another worker, skipping", flush=True)
                    continue

                try:
                    print(f"[worker] Claimed and reconciling: '{conflict['memory_a_content'][:40]}...' "
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
                        conflict_pair_id=conflict_id,
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
                    print(f"[worker] Error on conflict {conflict_id}: {e}", flush=True)
                    traceback.print_exc()

                    # Release the claim so another worker (or next poll) can retry
                    try:
                        conflicts_collection.update_one(
                            {"_id": ObjectId(conflict_id), "status": "processing"},
                            {"$set": {"status": "pending"}, "$unset": {"claimed_at": ""}}
                        )
                        print(f"[worker] Released claim on {conflict_id} for retry", flush=True)
                    except Exception as release_err:
                        print(f"[worker] Failed to release claim on {conflict_id}: {release_err}", flush=True)

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