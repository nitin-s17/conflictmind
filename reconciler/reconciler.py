"""
reconciler.py
Person 2 — Day 4-5 deliverable. The core novel piece.

adversarial_reconcile(memory_a, memory_b) → dict

Runs a structured 3-step debate between two conflicting memories:
  Step 1 — Memory A argues for itself
  Step 2 — Memory B argues for itself
  Step 3 — Judge weighs both and writes a resolved unified memory
"""

from reconciler.gemini_client import gemini_json_call


# ─── Step 1: Memory A argues ────────────────────────────────────────────────

ARGUE_SYSTEM = """You are a memory in an AI assistant's memory system.
You must argue why you should be the surviving memory when reconciling a conflict.
Respond ONLY with valid JSON. No preamble, no markdown.
"""

ARGUE_PROMPT_TEMPLATE = """You are Memory {label}. You are in a debate with another memory.
Your goal is to argue why you are the more accurate and relevant memory to keep.

Your details:
Content: "{content}"
Created: {timestamp}
Confidence score: {confidence} (out of 1.0)
Times recalled and used: {frequency}
Memory type: {memory_type}

The opposing memory says: "{opposing_content}"

Build your argument. You may cite:
- Your recency (if you are newer)
- Your confidence score (if it is high)
- How often you have been recalled and reinforced (frequency)
- Whether you represent a specific context vs a general preference
- Whether the opposing memory may be outdated or situational

Respond ONLY with this JSON:
{{
  "argument": "<2-4 sentences arguing why you should survive>",
  "strongest_point": "<your single most compelling reason in one sentence>"
}}"""


def _argue(memory: dict, opposing_memory: dict, label: str) -> dict:
    prompt = ARGUE_PROMPT_TEMPLATE.format(
        label=label,
        content=memory.get("content", ""),
        timestamp=str(memory.get("timestamp", "unknown")),
        confidence=round(float(memory.get("confidence", 0.8)), 2),
        frequency=int(memory.get("frequency", 0)),
        memory_type=memory.get("memory_type", "semantic"),
        opposing_content=opposing_memory.get("content", ""),
    )
    return gemini_json_call(prompt, system=ARGUE_SYSTEM)


# ─── Step 3: Judge decides ───────────────────────────────────────────────────

JUDGE_SYSTEM = """You are a neutral judge in a memory reconciliation system.
Two conflicting memories about the same user are in dispute.
Your job is to write a single unified memory that best captures the truth.
Respond ONLY with valid JSON. No preamble, no markdown.
"""

JUDGE_PROMPT_TEMPLATE = """Two memories about a user are in conflict. You must resolve them
into a single unified memory that best captures what is true about this user.

--- MEMORY A ---
Content: "{content_a}"
Created: {timestamp_a}
Confidence: {confidence_a}
Times recalled: {frequency_a}
Memory A's argument: "{argument_a}"
Memory A's strongest point: "{strongest_a}"

--- MEMORY B ---
Content: "{content_b}"
Created: {timestamp_b}
Confidence: {confidence_b}
Times recalled: {frequency_b}
Memory B's argument: "{argument_b}"
Memory B's strongest point: "{strongest_b}"

--- JUDGING CRITERIA ---
Weigh these factors in order of importance:
1. Specificity: A memory that applies to a specific context can COEXIST with a general preference.
   If so, merge them into a nuanced unified memory rather than picking a winner.
2. Frequency: Higher recall frequency means this memory has been reinforced more — it reflects
   a consistent pattern, not a one-off event.
3. Recency: More recent memories generally reflect the user's current state better,
   UNLESS the older memory has much higher frequency (pattern vs anomaly).
4. Confidence: Higher confidence means stronger signal. Low confidence memories
   should yield to high confidence ones unless other factors override.

--- RESOLUTION RULES ---
- If one memory is clearly a general rule and the other is a specific exception,
  write a unified memory that captures both: "generally X, but Y in context Z"
- If one memory is simply outdated (low frequency, old, low confidence), let the newer one win
- If both are equally valid but contradictory, write the most nuanced version that
  captures the real pattern
- The unified memory must be a single clean sentence, not a compound sentence with 5 clauses
- Do NOT just concatenate both memories — synthesize them

Respond ONLY with this JSON:
{{
  "resolved_content": "<single clean sentence that is the unified memory>",
  "winner": "a" | "b" | "merged",
  "judge_reasoning": "<2-3 sentences explaining your decision and what each memory contributed>",
  "confidence_in_resolution": <float 0.0-1.0>
}}"""


def _judge(memory_a: dict, memory_b: dict, argument_a: dict, argument_b: dict) -> dict:
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        content_a=memory_a.get("content", ""),
        timestamp_a=str(memory_a.get("timestamp", "unknown")),
        confidence_a=round(float(memory_a.get("confidence", 0.8)), 2),
        frequency_a=int(memory_a.get("frequency", 0)),
        argument_a=argument_a.get("argument", ""),
        strongest_a=argument_a.get("strongest_point", ""),
        content_b=memory_b.get("content", ""),
        timestamp_b=str(memory_b.get("timestamp", "unknown")),
        confidence_b=round(float(memory_b.get("confidence", 0.8)), 2),
        frequency_b=int(memory_b.get("frequency", 0)),
        argument_b=argument_b.get("argument", ""),
        strongest_b=argument_b.get("strongest_point", ""),
    )
    return gemini_json_call(prompt, system=JUDGE_SYSTEM)


# ─── Public function ─────────────────────────────────────────────────────────

def adversarial_reconcile(memory_a: dict, memory_b: dict) -> dict:
    """
    Run the full 3-step adversarial debate between two conflicting memories.

    Args:
        memory_a: memory dict — keys: content, timestamp, confidence, frequency, memory_type
        memory_b: memory dict — same keys

    Returns:
        dict with keys:
            resolved_content:         str  — the single unified memory sentence
            argument_a:               str  — Memory A's full argument
            argument_b:               str  — Memory B's full argument
            judge_reasoning:          str  — judge's explanation
            winner:                   str  — "a", "b", or "merged"
            confidence_in_resolution: float
    """

    # Step 1 — Memory A argues
    result_a = _argue(memory_a, memory_b, label="A")

    # Step 2 — Memory B argues
    result_b = _argue(memory_b, memory_a, label="B")

    # Step 3 — Judge decides
    judgment = _judge(memory_a, memory_b, result_a, result_b)

    return {
        "resolved_content":         judgment.get("resolved_content", ""),
        "argument_a":               result_a.get("argument", ""),
        "argument_b":               result_b.get("argument", ""),
        "judge_reasoning":          judgment.get("judge_reasoning", ""),
        "winner":                   judgment.get("winner", "merged"),
        "confidence_in_resolution": judgment.get("confidence_in_resolution", 0.7),
    }
