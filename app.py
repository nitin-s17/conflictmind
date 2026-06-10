"""
app.py — ConflictMind Flask Application
"""

import os
import sys
import time
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from bson import ObjectId

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory_layer.memories as ml
from reconciler.reconciler_api import reconciler_bp

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "conflictmind-dev-key")
app.register_blueprint(reconciler_bp)

def _jsonify_safe(obj):
    if isinstance(obj, list):
        return [_jsonify_safe(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _jsonify_safe(v) for k, v in obj.items()}
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/conversations")
def get_conversations():
    return jsonify({"conversations": []})

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    user_message = data.get("message", "").strip()
    conversation_id = data.get("conversation_id", f"web_{int(datetime.now().timestamp())}")

    if not user_message:
        return jsonify({"error": "message is required"}), 400

    try:
        import requests as req

        session_id = conversation_id

        # Create session
        try:
            req.post(
                f"http://localhost:8000/apps/adk_agent/users/user/sessions/{session_id}",
                json={},
                timeout=10
            )
        except Exception as e:
            print(f"[chat] Session create: {e}")

        # Run agent
        adk_response = req.post(
            "http://localhost:8000/run",
            json={
                "app_name": "adk_agent",
                "user_id": "user",
                "session_id": session_id,
                "new_message": {
                    "role": "user",
                    "parts": [{"text": user_message}]
                }
            },
            timeout=240
        )
        adk_data = adk_response.json()

        response_text = ""
        for event in adk_data:
            if isinstance(event, dict):
                content = event.get("content", {})
                if content.get("role") == "model":
                    parts = content.get("parts", [])
                    for part in parts:
                        if "text" in part:
                            response_text += part["text"]

        if not response_text:
            response_text = "I'm thinking..."

    except Exception as e:
        return jsonify({"error": f"ADK agent error: {e}"}), 500

    try:
        memories = ml.retrieve_memories(user_message, top_k=5)
    except Exception:
        memories = []

    return jsonify({
        "response": response_text,
        "memories_used": [
            {
                "id": m["_id"],
                "content": m["content"],
                "memory_type": m.get("memory_type", "semantic"),
                "confidence": round(float(m.get("confidence", 0.8)), 2),
                "similarity_score": round(float(m.get("similarity_score", 0)), 3)
            }
            for m in memories
        ],
        "new_memory": None
    })


@app.route("/memories")
def get_memories():
    try:
        from memory_layer.db import get_memories_collection
        col = get_memories_collection()
        mems = list(
            col.find({"status": "active"}, {"embedding": 0})
               .sort("timestamp", -1)
               .limit(50)
        )
        return jsonify({"memories": _jsonify_safe(mems)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/conflicts")
def get_conflicts():
    try:
        conflicts = ml.get_conflict_history(limit=20)
        return jsonify({"conflicts": _jsonify_safe(conflicts)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/memory-graph")
def memory_graph():
    try:
        from memory_layer.db import get_memories_collection, get_conflict_pairs_collection

        mems = list(
            get_memories_collection()
            .find({}, {"embedding": 0})
            .sort("timestamp", -1)
            .limit(100)
        )

        nodes = []
        for m in mems:
            ts = m.get("timestamp")
            nodes.append({
                "id":          str(m["_id"]),
                "content":     m.get("content", ""),
                "memory_type": m.get("memory_type", "semantic"),
                "confidence":  float(m.get("confidence", 0.8)),
                "frequency":   int(m.get("frequency", 1)),
                "status":      m.get("status", "active"),
                "timestamp":   ts.isoformat() if isinstance(ts, datetime) else str(ts or "")
            })

        pairs = list(
            get_conflict_pairs_collection()
            .find({}, {"debate_transcript": 0})
            .sort("detected_at", -1)
            .limit(100)
        )

        links = []
        for p in pairs:
            links.append({
                "source":           str(p.get("memory_a_id", "")),
                "target":           str(p.get("memory_b_id", "")),
                "resolved":         p.get("status") == "resolved",
                "similarity_score": float(p.get("similarity_score", 0)),
                "conflict_id":      str(p["_id"]),
                "status":           p.get("status", "pending")
            })

        return jsonify({"nodes": nodes, "links": links})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/memory/<memory_id>")
def get_memory_detail(memory_id):
    try:
        from memory_layer.db import get_memories_collection, get_conflict_pairs_collection

        mem = get_memories_collection().find_one(
            {"_id": ObjectId(memory_id)},
            {"embedding": 0}
        )
        if not mem:
            return jsonify({"error": "Not found"}), 404

        conflicts = list(get_conflict_pairs_collection().find({
            "$or": [
                {"memory_a_id": memory_id},
                {"memory_b_id": memory_id}
            ]
        }).sort("detected_at", -1))

        return jsonify({
            "memory":    _jsonify_safe(mem),
            "conflicts": _jsonify_safe(conflicts)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/debug/adk")
def debug_adk():
    import requests as req
    results = {}
    try:
        r = req.get("http://localhost:8000/health", timeout=5)
        results["health"] = {"status": r.status_code, "body": r.text[:200]}
    except Exception as e:
        results["health"] = {"error": str(e)}
    try:
        r = req.get("http://localhost:8000/list-apps", timeout=5)
        results["list_apps"] = {"status": r.status_code, "body": r.text[:200]}
    except Exception as e:
        results["list_apps"] = {"error": str(e)}
    return jsonify(results)

if __name__ == "__main__":
    print("\nConflictMind starting...")
    print("    http://localhost:8080\n")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=False)