# ConflictMind — Reconciler Module
**Owner: Person 2**

The reconciliation engine is the novel core of ConflictMind.
It detects contradictions in the memory layer and resolves them through an adversarial debate.

---

## File structure

```
reconciler/
├── gemini_client.py       ← Gemini API wrapper (all LLM calls go here)
├── conflict_classifier.py ← classify_conflict() — contradictory/redundant/unrelated
├── conflict_detector.py   ← detect_conflicts() + process_new_memory() async pipeline
├── reconciler.py          ← adversarial_reconcile() — the 3-step debate loop
├── reconciler_api.py      ← Flask Blueprint — REST endpoints for Person 3
├── background_worker.py   ← polls Atlas for pending conflicts every 30s
├── test_reconciler.py     ← Day 6 tuning: 15 conflict pairs to validate
└── requirements.txt
```

---

## Setup

```bash
pip install -r requirements.txt
```

Add to your `.env`:
```
GEMINI_API_KEY=your_key_here
MONGODB_URI=get_from_N
MONGODB_DB_NAME=ConflictMind
```

---

## The three-step debate loop

```
Memory A  ──→  argues for itself (recency + confidence + frequency)
                        ↓
Memory B  ──→  argues for itself (same signals)
                        ↓
             Judge weighs both arguments
             against 4 criteria:
               1. Specificity (context-dependent vs general)
               2. Frequency   (reinforcement = pattern)
               3. Recency     (newer = current state)
               4. Confidence  (decay-adjusted signal strength)
                        ↓
             Single resolved memory written to Atlas
             Full debate transcript stored in conflict_pairs
```

---

## How Person 3 integrates

```python
# After write_memory() in the agent loop:
from reconciler.conflict_detector import process_new_memory
import memory_layer.memories as ml

new_memory = { "_id": memory_id, "content": "...", ... }
existing = ml.retrieve_memories(query=new_memory["content"], top_k=20)

# Fires async — does not block chat response
process_new_memory(new_memory, existing, ml)
```

Or via the REST endpoint:
```
POST /reconcile
GET  /reconcile/pending
GET  /reconcile/status
```

---

## Running the background worker

In a separate terminal from the Flask server:
```bash
cd project_root
python reconciler/background_worker.py
```

---

## Day 6 tuning

```bash
python reconciler/test_reconciler.py
```

Read each resolved memory. Mark ✅ or ❌.
Target: 12 of 15 correct.
If below target — paste the failing cases to Claude with:
> "Adjust the judge prompt in reconciler.py to fix these specific resolutions: [paste cases]"
