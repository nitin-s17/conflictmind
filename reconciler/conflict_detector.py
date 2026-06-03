"""
conflict_detector.py
Person 2 — Day 3 deliverable.

Hooks into the memory layer after every write.
Detects conflicts, queues them, and triggers reconciliation.
"""

import asyncio
from reconciler.conflict_classifier import classify_conflict

# Threshold: only flag conflicts above this classifier confidence
CONFLICT_CONFIDENCE_THRESHOLD = 0.75


def detect_conflicts(new_memory: dict, existing_memories: list[dict]) -> list[dict]:
    """
    Check a newly written memory against existing memories for contradictions.

    Args:
        new_memory:        the freshly written memory dict (must include _id, content, etc.)
        existing_memories: list of existing memory dicts to compare against

    Returns:
        list of dicts, one per detected conflict:
        [
          {
            "memory_a": <new_memory dict>,
            "memory_b": <existing conflicting memory dict>,
            "classification": "contradictory",
            "confidence": 0.91,
            "reason": "..."
          },
          ...
        ]
    """
    conflicts_found = []

    for existing in existing_memories:
        # Skip if same memory
        if str(existing.get("_id")) == str(new_memory.get("_id")):
            continue

        # Skip memories already in conflicted/resolved/decayed state
        if existing.get("status") in ("conflicted", "resolved", "decayed"):
            continue

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


async def process_new_memory_async(
    new_memory: dict,
    existing_memories: list[dict],
    memory_layer,
) -> None:
    """
    Async pipeline — runs after write_memory(), never blocks the chat response.

    Steps:
      1. Detect conflicts between new_memory and existing_memories
      2. For each conflict found:
         a. Save the conflict pair to Atlas (via memory_layer)
         b. Run adversarial_reconcile()
         c. Save the result (via memory_layer)

    Args:
        new_memory:        freshly written memory dict
        existing_memories: list of active existing memories
        memory_layer:      imported memory_layer.memories module
    """
    from reconciler.reconciler import adversarial_reconcile

    conflicts = detect_conflicts(new_memory, existing_memories)

    for conflict in conflicts:
        try:
            # Save the conflict pair
            conflict_pair_id = memory_layer.save_conflict_pair(
                memory_a_id=str(conflict["memory_a"]["_id"]),
                memory_b_id=str(conflict["memory_b"]["_id"]),
                memory_a_content=conflict["memory_a"]["content"],
                memory_b_content=conflict["memory_b"]["content"],
                similarity_score=conflict["confidence"],
            )

            # Run the debate
            result = adversarial_reconcile(
                memory_a=conflict["memory_a"],
                memory_b=conflict["memory_b"],
            )

            # Store the result — memory layer handles everything else
            memory_layer.save_reconciliation_result(
                conflict_pair_id=conflict_pair_id,
                debate_transcript={
                    "argument_a":    result["argument_a"],
                    "argument_b":    result["argument_b"],
                    "judge_reasoning": result["judge_reasoning"],
                    "winner":        result["winner"],
                },
                resolved_content=result["resolved_content"],
                resolved_memory_type=conflict["memory_a"].get("memory_type", "semantic"),
            )

        except Exception as e:
            # Never crash the chat — log and continue
            print(f"[reconciler] Error processing conflict: {e}")


def process_new_memory(
    new_memory: dict,
    existing_memories: list[dict],
    memory_layer,
) -> None:
    """
    Sync wrapper — fires the async pipeline in the background.
    Call this after write_memory(). Returns immediately.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside an async context (e.g. FastAPI) — schedule as task
            asyncio.create_task(
                process_new_memory_async(new_memory, existing_memories, memory_layer)
            )
        else:
            loop.run_until_complete(
                process_new_memory_async(new_memory, existing_memories, memory_layer)
            )
    except Exception as e:
        print(f"[reconciler] Failed to start async pipeline: {e}")
