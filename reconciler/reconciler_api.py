"""
reconciler_api.py
Person 2 — Day 7 deliverable.

Flask REST endpoints that Person 3's agent calls.
Mount this as a Blueprint in the main Flask app.

Endpoints:
    POST /reconcile          — manually trigger reconciliation for a conflict pair
    GET  /reconcile/pending  — list all pending conflicts (for polling/debug)
    GET  /reconcile/status   — health check
"""

from flask import Blueprint, request, jsonify
from reconciler import adversarial_reconcile

reconciler_bp = Blueprint("reconciler", __name__, url_prefix="/reconcile")


@reconciler_bp.route("/status", methods=["GET"])
def status():
    return jsonify({"status": "ok", "service": "ConflictMind Reconciler"})


@reconciler_bp.route("/pending", methods=["GET"])
def get_pending():
    """
    Returns all pending conflicts.
    Person 3 can poll this to show unresolved conflicts in the UI.
    """
    try:
        import memory_layer.memories as ml
        pending = ml.get_conflict_history(status="pending")

        # Convert ObjectIds to strings for JSON serialisation
        serialisable = []
        for c in pending:
            serialisable.append({
                "_id":              str(c["_id"]),
                "memory_a_id":      str(c["memory_a_id"]),
                "memory_b_id":      str(c["memory_b_id"]),
                "memory_a_content": c["memory_a_content"],
                "memory_b_content": c["memory_b_content"],
                "similarity_score": c.get("similarity_score"),
                "status":           c["status"],
                "detected_at":      str(c.get("detected_at", "")),
            })

        return jsonify({"pending": serialisable, "count": len(serialisable)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@reconciler_bp.route("", methods=["POST"])
def reconcile():
    """
    Manually trigger reconciliation for a conflict pair.
    Person 3 calls this when the agent needs an immediate resolution.

    Request body:
    {
        "conflict_pair_id": "64f3a2b3...",
        "memory_a": { "content": "...", "timestamp": "...", "confidence": 0.8, "frequency": 3 },
        "memory_b": { "content": "...", "timestamp": "...", "confidence": 0.7, "frequency": 1 }
    }

    Response:
    {
        "resolved_content": "...",
        "winner": "merged",
        "judge_reasoning": "...",
        "argument_a": "...",
        "argument_b": "..."
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    memory_a = data.get("memory_a")
    memory_b = data.get("memory_b")
    conflict_pair_id = data.get("conflict_pair_id")

    if not memory_a or not memory_b:
        return jsonify({"error": "memory_a and memory_b are required"}), 400

    try:
        result = adversarial_reconcile(memory_a, memory_b)

        # If conflict_pair_id provided, save result to Atlas automatically
        if conflict_pair_id:
            try:
                import memory_layer.memories as ml
                ml.save_reconciliation_result(
                    conflict_pair_id=conflict_pair_id,
                    debate_transcript={
                        "argument_a":      result["argument_a"],
                        "argument_b":      result["argument_b"],
                        "judge_reasoning": result["judge_reasoning"],
                        "winner":          result["winner"],
                    },
                    resolved_content=result["resolved_content"],
                )
            except Exception as save_err:
                # Return result even if save fails
                result["save_error"] = str(save_err)

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
