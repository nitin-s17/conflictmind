"""
app.py — ConflictMind Flask Application
Agent conversation loop + API server + UI

Endpoints:
    GET  /                → serves the chat + memory graph UI
    POST /chat            → Gemini agent with memory injection
    GET  /memories        → all active memories
    GET  /conflicts       → conflict history
    GET  /memory-graph    → D3-ready graph {nodes, links}
    GET  /memory/<id>     → single memory + its conflict history

Also mounts the reconciler Blueprint from reconciler/reconciler_api.py:
    POST /reconcile           → manually trigger a debate
    GET  /reconcile/pending   → list pending conflicts
    GET  /reconcile/status    → health check
"""

import os
import sys
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from bson import ObjectId

# ── bootstrap path ────────────────────────────────────────────
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory_layer.memories as ml
from reconciler.conflict_detector import process_new_memory
from reconciler.reconciler_api import reconciler_bp

# ── Flask setup ───────────────────────────────────────────────
app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "conflictmind-dev-key")
app.register_blueprint(reconciler_bp)

# ── Gemini client (lazy singleton) ───────────────────────────
_gemini_client = None

def get_gemini():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _gemini_client

# ── JSON serialiser (handles ObjectId + datetime) ────────────
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

# ── Routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    user_message = data.get("message", "").strip()
    conversation_id = data.get("conversation_id", f"web_{int(datetime.now().timestamp())}")

    if not user_message:
        return jsonify({"error": "message is required"}), 400

    # 1 — Retrieve relevant memories
    try:
        memories = ml.retrieve_memories(user_message, top_k=5)
    except Exception as e:
        print(f"[chat] retrieve_memories error: {e}")
        memories = []

    # 2 — Update frequency for recalled memories
    for m in memories:
        try:
            ml.update_memory_frequency(m["_id"])
        except Exception:
            pass

    # 3 — Build Gemini system prompt with memory context
    if memories:
        memory_lines = "\n".join([
            f"- {m['content']} (confidence: {m.get('confidence', 0.8):.2f}, recalled {m.get('frequency', 1)}x)"
            for m in memories
        ])
        system_prompt = f"""You are ConflictMind, a personal AI assistant with persistent memory.
You genuinely remember things about this user across all conversations.

What you currently know about this user:
{memory_lines}

Guidelines:
- Reference memories naturally when relevant — don't say "I remember you said..."
- Be warm, specific and personal. The memory context is your secret weapon.
- If the user says something that contradicts what you know, acknowledge both gracefully.
- Be concise. Aim for 2-4 sentence responses unless depth is needed."""
    else:
        system_prompt = """You are ConflictMind, a personal AI assistant with persistent memory.
You're just getting to know this user — no prior memories yet.
Be warm and curious. Ask a thoughtful follow-up question to start building their profile.
Keep your response friendly and short (2-3 sentences)."""

    # 4 — Call Gemini for the actual response
    try:
        client = get_gemini()
        full_prompt = f"{system_prompt}\n\nUser: {user_message}\n\nConflictMind:"
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=full_prompt)
        response_text = resp.text.strip()
    except Exception as e:
        return jsonify({"error": f"Gemini error: {e}"}), 500

    # 5 — Extract a new memory from the exchange (second Gemini call)
    new_memory_data = None
    try:
        extract_prompt = f"""You extract a single persistent memory from a user conversation.

User said: "{user_message}"
Assistant responded: "{response_text[:400]}"

Task: Extract ONE reusable fact about the user as a short declarative sentence.
- Start with "User"
- Only extract meaningful preferences, facts, patterns, or experiences
- Do NOT extract greetings, single-word answers, or generic chat
- Return EXACTLY the memory sentence, nothing else
- If nothing meaningful was learned, return the single word: NONE

Examples of good outputs:
"User works as a product manager at a fintech startup."
"User strongly prefers concise technical explanations without filler."
"User has been learning guitar for three months."

Return NONE or the memory sentence:"""

        extract_resp = client.models.generate_content(
            model="gemini-2.5-flash", contents=extract_prompt
        )
        extracted = extract_resp.text.strip()

        if extracted and extracted.upper() != "NONE" and len(extracted) > 15 and extracted.startswith("User"):
            # Classify memory type
            if any(w in extracted.lower() for w in ["always", "usually", "tends to", "habit", "routine", "prefer to", "likes to"]):
                memory_type = "procedural"
            elif any(w in extracted.lower() for w in ["last", "yesterday", "ago", "when", "once", "event", "happened"]):
                memory_type = "episodic"
            else:
                memory_type = "semantic"

            memory_id = ml.write_memory(
                content=extracted,
                memory_type=memory_type,
                conversation_id=conversation_id,
                auto_detect=True
            )

            new_memory_data = {
                "id": memory_id,
                "content": extracted,
                "memory_type": memory_type,
                "confidence": 1.0
            }

            # Fire reconciliation in background — never blocks chat response
            new_mem_dict = {
                "_id": memory_id,
                "content": extracted,
                "timestamp": datetime.now(timezone.utc),
                "confidence": 1.0,
                "frequency": 1,
                "memory_type": memory_type,
                "status": "active"
            }
            existing = ml.retrieve_memories(extracted, top_k=20)
            print(f"[debug] Calling process_new_memory for: '{extracted[:40]}'")
            process_new_memory(new_mem_dict, existing, ml)

    except Exception as e:
        print(f"[chat] memory extraction error: {e}")

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
        "new_memory": new_memory_data
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

        # All memories, no embeddings
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

        # All conflict pairs
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
    """Single memory + its full conflict history (with debate transcripts)."""
    try:
        from memory_layer.db import get_memories_collection, get_conflict_pairs_collection

        mem = get_memories_collection().find_one(
            {"_id": ObjectId(memory_id)},
            {"embedding": 0}
        )
        if not mem:
            return jsonify({"error": "Not found"}), 404

        # Conflicts involving this memory
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


if __name__ == "__main__":
    print("\nConflictMind starting...")
    print("    http://localhost:5000\n")
    app.run(debug=True, port=5000, use_reloader=False)
