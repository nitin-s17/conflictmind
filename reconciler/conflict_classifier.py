"""
conflict_classifier.py
Person 2 — Day 1-2 deliverable.

classify_conflict(memory_a, memory_b) → dict
Determines if two memories are contradictory, redundant, or unrelated.
"""

from reconciler.gemini_client import gemini_json_call


CLASSIFY_SYSTEM = """You are a memory conflict detection system for an AI assistant.
Your job is to determine whether two stored memories about a user contradict each other,
are redundant (same information expressed differently), or are unrelated.

You must respond ONLY with a valid JSON object. No explanation, no preamble, no markdown.
"""

CLASSIFY_PROMPT_TEMPLATE = """Analyze these two memories about the same user:

Memory A:
Content: {content_a}
Stored: {timestamp_a}
Confidence: {confidence_a}
Times recalled: {frequency_a}

Memory B:
Content: {content_b}
Stored: {timestamp_b}
Confidence: {confidence_b}
Times recalled: {frequency_b}

Determine their relationship. Rules:
- "contradictory" = they DIRECTLY conflict on the EXACT SAME TOPIC (e.g. "hates spicy food" vs "loves spicy food"). Both memories must be about the identical subject.
- "redundant" = they express the same core fact or preference, possibly with different wording
- "unrelated" = they are about DIFFERENT topics or aspects of the user. If the two memories cover different subjects (food vs response style, career vs hobbies, coding vs personality), they are ALWAYS unrelated — even if they seem related.

IMPORTANT: When in doubt, classify as "unrelated". Only classify as "contradictory" if you are absolutely certain both memories make opposing claims about the exact same thing.

Respond with ONLY this JSON:
{{
  "classification": "contradictory" | "redundant" | "unrelated",
  "confidence": <float 0.0-1.0, how confident you are in this classification>,
  "reason": "<one sentence explanation>"
}}"""

def classify_conflict(memory_a: dict, memory_b: dict) -> dict:
    """
    Classify the relationship between two memories.

    Args:
        memory_a: memory dict with keys: content, timestamp, confidence, frequency
        memory_b: memory dict with keys: content, timestamp, confidence, frequency

    Returns:
        dict with keys:
            classification: "contradictory" | "redundant" | "unrelated"
            confidence: float 0.0-1.0
            reason: str
    """
    prompt = CLASSIFY_PROMPT_TEMPLATE.format(
        content_a=memory_a.get("content", ""),
        timestamp_a=str(memory_a.get("timestamp", "unknown")),
        confidence_a=round(float(memory_a.get("confidence", 0.8)), 2),
        frequency_a=int(memory_a.get("frequency", 0)),
        content_b=memory_b.get("content", ""),
        timestamp_b=str(memory_b.get("timestamp", "unknown")),
        confidence_b=round(float(memory_b.get("confidence", 0.8)), 2),
        frequency_b=int(memory_b.get("frequency", 0)),
    )

    result = gemini_json_call(prompt, system=CLASSIFY_SYSTEM)

    # Validate output shape
    if "classification" not in result:
        raise ValueError(f"Missing 'classification' in response: {result}")
    if result["classification"] not in ("contradictory", "redundant", "unrelated"):
        raise ValueError(f"Invalid classification value: {result['classification']}")
    if "confidence" not in result:
        result["confidence"] = 0.5
    if "reason" not in result:
        result["reason"] = ""

    return result
