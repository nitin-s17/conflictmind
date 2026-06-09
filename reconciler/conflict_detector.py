"""
conflict_detector.py
Person 2 - Day 5 deliverable.

Runs the full reconciliation pipeline in a background thread.
Never blocks the chat response.
"""

import time
import threading
from reconciler.conflict_classifier import classify_conflict

CONFLICT_CONFIDENCE_THRESHOLD = 0.85


def detect_conflicts(new_memory: dict, existing_memories: list[dict]) -> list[dict]:
    """
    Check a newly written memory against existing memories for contradictions.
    """
    conflicts_found = []

    for existing in existing_memories:
        if str(existing.get("_id")) == str(new_memory.get("_id")):
            continue
        if existing.get("status") in ("resolved", "decayed"):
            continue

        time.sleep(5)
        result = classify_conflict(new_memory, existing)

        if (
            result["classification"] == "contradictory"
            and result["confidence"] >= CONFLICT_CONFIDENCE_THRESHOLD
        ):
            conflicts_found.append({
                "memory_a": new_memory,
                "memory_b": existing,
                "classification": result["classification"],
                "confidence": result["confidence"],
                "reason": result["reason"],
            })

    return conflicts_found


def _reconcile_in_background(new_memory, existing_memories, memory_layer):
    """
    Runs the full detect → debate → save pipeline.
    Called in a background thread — never blocks chat.
    """
    from reconciler.reconciler import adversarial_reconcile

    try:
        conflicts = detect_conflicts(new_memory, existing_memories)

        for conflict in conflicts:
            try:
                conflict_pair_id = memory_layer.save_conflict_pair(
                    memory_a_id=str(conflict["memory_a"]["_id"]),
                    memory_b_id=str(conflict["memory_b"]["_id"]),
                    memory_a_content=conflict["memory_a"]["content"],
                    memory_b_content=conflict["memory_b"]["content"],
                    similarity_score=conflict["confidence"],
                )

                time.sleep(5)

                result = adversarial_reconcile(
                    memory_a=conflict["memory_a"],
                    memory_b=conflict["memory_b"],
                )

                memory_layer.save_reconciliation_result(
                    conflict_pair_id=conflict_pair_id,
                    debate_transcript={
                        "argument_a":      result["argument_a"],
                        "argument_b":      result["argument_b"],
                        "judge_reasoning": result["judge_reasoning"],
                        "winner":          result["winner"],
                    },
                    resolved_content=result["resolved_content"],
                    resolved_memory_type=conflict["memory_a"].get("memory_type", "semantic"),
                )

                print(f"[reconciler] Resolved: '{result['resolved_content'][:60]}...'")

            except Exception as e:
                print(f"[reconciler] Error on conflict: {e}")

    except Exception as e:
        print(f"[reconciler] Pipeline error: {e}")


def process_new_memory(
    new_memory: dict,
    existing_memories: list[dict],
    memory_layer,
) -> None:
    """
    Fires the reconciliation pipeline in a background thread.
    Returns immediately — never blocks the chat response.

    Args:
        new_memory:        freshly written memory dict (_id, content, timestamp, confidence, frequency, memory_type)
        existing_memories: list of active memories to check against
        memory_layer:      memory_layer.memories module
    """
    thread = threading.Thread(
        target=_reconcile_in_background,
        args=(new_memory, existing_memories, memory_layer),
        daemon=True
    )
    thread.start()
    print(f"[reconciler] Background reconciliation started for: '{new_memory.get('content', '')[:40]}...'")