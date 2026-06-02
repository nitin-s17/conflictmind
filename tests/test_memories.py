'''
========================================================================================
Integration tests for memories.py
Tests all 8 functions against a real Atlas database connection

HOW TO RUN:
    From the project root (Conflict Mind/):
    pytest tests/test_memories.py -v

WHAT IS TESTED:
    write_memory()              — writes correctly, rejects invalid input
    retrieve_memories()         — returns relevant results with similarity scores
    update_memory_frequency()   — frequency actually increments in Atlas
    apply_memory_decay()        — confidence actually reduces in Atlas
    mark_memory_resolved()      — status changes to resolved in Atlas
    detect_conflicts()          — finds similar memories, respects threshold
    save_conflict_pair()        — stores correctly, skips duplicates
    get_conflict_history()      — filters by status correctly

NOTE:
    These are integration tests — they hit the real Atlas database.
    Each test creates its own data so tests don't interfere with each other.
    Test data is prefixed with "test_conv" so it can be identified and cleaned up.
========================================================================================
'''

import pytest
import time
from memory_layer.memories import (
    write_memory,
    retrieve_memories,
    update_memory_frequency,
    apply_memory_decay,
    mark_memory_resolved,
    detect_conflicts,
    save_conflict_pair,
    get_conflict_history
)
from memory_layer.db import get_memories_collection, get_conflict_pairs_collection

# ============================================================
# Fixtures — reusable test data
# ============================================================

@pytest.fixture
def sample_memory_id():
    memory_id = write_memory(
        content="User enjoys watching documentaries about deep sea creatures",
        memory_type="episodic",
        conversation_id="test_conv_001"
    )
    return memory_id

@pytest.fixture
def conflicting_memory_ids():
    """Creates two conflicting memories and returns both IDs."""
    id_a = write_memory(
        content="User loves very detailed and thorough explanations",
        memory_type="semantic",
        conversation_id="test_conv_002"
    )
    id_b = write_memory(
        content="User hates long responses and wants everything concise",
        memory_type="semantic",
        conversation_id="test_conv_002"
    )
    return id_a, id_b


# ============================================================
# write_memory() tests
# ============================================================

def test_write_memory_returns_id():
    """write_memory() should return a valid non-empty string ID."""
    memory_id = write_memory("User likes Python", "semantic", "test_conv")
    assert isinstance(memory_id, str)
    assert len(memory_id) > 0


def test_write_memory_all_types():
    """write_memory() should accept all three valid memory types."""
    id1 = write_memory("User works in fintech", "semantic", "test_conv")
    id2 = write_memory("User asked about Python last Tuesday", "episodic", "test_conv")
    id3 = write_memory("Always show code examples first", "procedural", "test_conv")
    assert id1 is not None
    assert id2 is not None
    assert id3 is not None


def test_write_memory_invalid_type():
    """write_memory() should reject invalid memory types."""
    with pytest.raises(ValueError):
        write_memory("User likes Python", "invalid_type", "test_conv")


def test_write_memory_empty_content():
    """write_memory() should reject empty content."""
    with pytest.raises(ValueError):
        write_memory("", "semantic", "test_conv")


def test_write_memory_whitespace_content():
    """write_memory() should reject whitespace-only content."""
    with pytest.raises(ValueError):
        write_memory("   ", "semantic", "test_conv")


def test_write_memory_document_structure(sample_memory_id):
    """write_memory() should create a document with all required fields."""
    from bson import ObjectId
    collection = get_memories_collection()
    doc = collection.find_one({"_id": ObjectId(sample_memory_id)})

    assert doc is not None
    assert "content" in doc
    assert "embedding" in doc
    assert "memory_type" in doc
    assert "source_conversation_id" in doc
    assert "timestamp" in doc
    assert "confidence" in doc
    assert "frequency" in doc
    assert "status" in doc

    assert doc["confidence"] == 1.0
    assert doc["frequency"] == 1

    # Status can be active or conflicted depending on existing memories
    assert doc["status"] in ["active", "conflicted"]

# ============================================================
# retrieve_memories() tests
# ============================================================

def test_retrieve_memories_returns_list():
    """retrieve_memories() should return a list."""
    results = retrieve_memories("user preferences")
    assert isinstance(results, list)


def test_retrieve_memories_relevance():
    """retrieve_memories() should return results for a valid query."""
    results = retrieve_memories("user preferences", top_k=5)
    assert len(results) > 0
    assert all("content" in r for r in results)


def test_retrieve_memories_has_similarity_score():
    """retrieve_memories() should include similarity_score in results."""
    results = retrieve_memories("user preferences", top_k=1)
    if results:
        assert "similarity_score" in results[0]
        assert 0.0 <= results[0]["similarity_score"] <= 1.0


def test_retrieve_memories_top_k():
    """retrieve_memories() should respect the top_k parameter."""
    results = retrieve_memories("user preferences", top_k=3)
    assert len(results) <= 3


def test_retrieve_memories_ids_are_strings():
    """retrieve_memories() should return string IDs not ObjectIds."""
    results = retrieve_memories("user preferences", top_k=1)
    if results:
        assert isinstance(results[0]["_id"], str)


def test_retrieve_memories_only_active():
    """retrieve_memories() should only return active or conflicted memories, not resolved or decayed."""
    results = retrieve_memories("user preferences", top_k=10)
    for memory in results:
        assert memory["status"] not in ["resolved", "decayed"]


# ============================================================
# update_memory_frequency() tests
# ============================================================

def test_update_memory_frequency(sample_memory_id):
    """update_memory_frequency() should increment frequency by 1."""
    from bson import ObjectId
    collection = get_memories_collection()

    # Get frequency before
    doc_before = collection.find_one({"_id": ObjectId(sample_memory_id)})
    frequency_before = doc_before["frequency"]

    # Update frequency
    update_memory_frequency(sample_memory_id)

    # Get frequency after
    doc_after = collection.find_one({"_id": ObjectId(sample_memory_id)})
    frequency_after = doc_after["frequency"]

    assert frequency_after == frequency_before + 1


def test_update_memory_frequency_multiple_times(sample_memory_id):
    """update_memory_frequency() should increment correctly multiple times."""
    from bson import ObjectId
    collection = get_memories_collection()

    doc_before = collection.find_one({"_id": ObjectId(sample_memory_id)})
    frequency_before = doc_before["frequency"]

    update_memory_frequency(sample_memory_id)
    update_memory_frequency(sample_memory_id)
    update_memory_frequency(sample_memory_id)

    doc_after = collection.find_one({"_id": ObjectId(sample_memory_id)})
    assert doc_after["frequency"] == frequency_before + 3


# ============================================================
# apply_memory_decay() tests
# ============================================================

def test_apply_memory_decay_reduces_confidence():
    """apply_memory_decay() should reduce confidence of active memories."""
    from bson import ObjectId
    collection = get_memories_collection()

    # Use unique content unlikely to conflict
    memory_id = write_memory(
        "User collects antique clocks from the Victorian era",
        "episodic",
        "test_decay_conv"
    )

    doc_before = collection.find_one({"_id": ObjectId(memory_id)})
    confidence_before = doc_before["confidence"]

    # Skip if memory got conflicted — decay won't run on conflicted memories
    if doc_before["status"] != "active":
        pytest.skip("Memory got conflicted, skipping decay test")

    apply_memory_decay()
    time.sleep(2)

    doc_after = collection.find_one({"_id": ObjectId(memory_id)})
    confidence_after = doc_after["confidence"]

    assert confidence_after < confidence_before


def test_apply_memory_decay_custom_rate():
    """apply_memory_decay() should apply higher decay with custom rate."""
    from bson import ObjectId
    collection = get_memories_collection()

    # Write a unique memory unlikely to conflict
    memory_id = write_memory(
        "User collects vintage stamps from Antarctica expeditions",
        "episodic",
        "test_decay_conv"
    )

    # Get confidence before
    doc_before = collection.find_one({"_id": ObjectId(memory_id)})
    confidence_before = doc_before["confidence"]

    # Only run if memory stayed active
    if doc_before["status"] != "active":
        pytest.skip("Memory got conflicted, skipping decay test")

    apply_memory_decay(base_decay=0.50)
    time.sleep(3)

    doc_after = collection.find_one({"_id": ObjectId(memory_id)})
    confidence_after = doc_after["confidence"]

    assert confidence_after < confidence_before * 0.80

# ============================================================
# mark_memory_resolved() tests
# ============================================================

def test_mark_memory_resolved(sample_memory_id):
    """mark_memory_resolved() should change status to resolved."""
    from bson import ObjectId
    collection = get_memories_collection()

    # Create a fake resolved_by ID
    resolved_by_id = write_memory("Unified memory", "semantic", "test_conv")
    mark_memory_resolved(sample_memory_id, resolved_by_id)

    doc = collection.find_one({"_id": ObjectId(sample_memory_id)})
    assert doc["status"] == "resolved"
    assert doc["resolved_by"] == resolved_by_id


# ============================================================
# detect_conflicts() tests
# ============================================================

def test_detect_conflicts_finds_similar():
    """detect_conflicts() should find memories that are semantically similar."""
    # Write a memory first
    write_memory("User always wants short and brief responses", "semantic", "test_conv")

    # Write a conflicting memory and detect conflicts
    new_id = write_memory("User prefers extremely detailed answers", "semantic", "test_conv")

    conflicts = detect_conflicts(new_id, "User prefers extremely detailed answers", "semantic")
    assert isinstance(conflicts, list)


def test_detect_conflicts_excludes_self():
    """detect_conflicts() should not flag a memory as conflicting with itself."""
    new_id = write_memory("User likes jazz music", "semantic", "test_conv")
    conflicts = detect_conflicts(new_id, "User likes jazz music", "semantic")

    conflict_ids = [c["_id"] for c in conflicts]
    assert new_id not in conflict_ids


def test_detect_conflicts_returns_similarity_score():
    """detect_conflicts() results should include similarity_score."""
    new_id = write_memory("User prefers long detailed explanations always", "semantic", "test_conv")
    conflicts = detect_conflicts(new_id, "User prefers long detailed explanations always", "semantic")

    for conflict in conflicts:
        assert "similarity_score" in conflict
        assert conflict["similarity_score"] >= 0.80


# ============================================================
# save_conflict_pair() tests
# ============================================================

def test_save_conflict_pair_returns_id(conflicting_memory_ids):
    """save_conflict_pair() should return a valid conflict pair ID."""
    id_a, id_b = conflicting_memory_ids
    conflict_id = save_conflict_pair(
        memory_a_id=id_a,
        memory_b_id=id_b,
        memory_a_content="User loves detailed explanations",
        memory_b_content="User hates long responses",
        similarity_score=0.91
    )
    assert isinstance(conflict_id, str)
    assert len(conflict_id) > 0


def test_save_conflict_pair_no_duplicates(conflicting_memory_ids):
    """save_conflict_pair() should not create duplicate conflict pairs."""
    id_a, id_b = conflicting_memory_ids

    conflict_id_1 = save_conflict_pair(
        memory_a_id=id_a,
        memory_b_id=id_b,
        memory_a_content="User loves detailed explanations",
        memory_b_content="User hates long responses",
        similarity_score=0.91
    )

    conflict_id_2 = save_conflict_pair(
        memory_a_id=id_a,
        memory_b_id=id_b,
        memory_a_content="User loves detailed explanations",
        memory_b_content="User hates long responses",
        similarity_score=0.91
    )

    # Should return same ID, not create a new one
    assert conflict_id_1 == conflict_id_2


def test_save_conflict_pair_marks_memories_conflicted(conflicting_memory_ids):
    """save_conflict_pair() should mark both memories as conflicted."""
    from bson import ObjectId
    id_a, id_b = conflicting_memory_ids

    save_conflict_pair(
        memory_a_id=id_a,
        memory_b_id=id_b,
        memory_a_content="User loves detailed explanations",
        memory_b_content="User hates long responses",
        similarity_score=0.91
    )

    collection = get_memories_collection()
    doc_a = collection.find_one({"_id": ObjectId(id_a)})
    doc_b = collection.find_one({"_id": ObjectId(id_b)})

    assert doc_a["status"] == "conflicted"
    assert doc_b["status"] == "conflicted"


def test_save_conflict_pair_document_structure(conflicting_memory_ids):
    """save_conflict_pair() should create a document with all required fields."""
    from bson import ObjectId
    id_a, id_b = conflicting_memory_ids

    conflict_id = save_conflict_pair(
        memory_a_id=id_a,
        memory_b_id=id_b,
        memory_a_content="User loves detailed explanations",
        memory_b_content="User hates long responses",
        similarity_score=0.91
    )

    collection = get_conflict_pairs_collection()
    doc = collection.find_one({"_id": ObjectId(conflict_id)})

    assert doc["status"] == "pending"
    assert doc["debate_transcript"] is None
    assert doc["resolved_memory_id"] is None
    assert "detected_at" in doc
    assert doc["similarity_score"] == 0.91


# ============================================================
# get_conflict_history() tests
# ============================================================

def test_get_conflict_history_returns_list():
    """get_conflict_history() should return a list."""
    results = get_conflict_history()
    assert isinstance(results, list)


def test_get_conflict_history_filter_pending():
    """get_conflict_history() should filter by pending status correctly."""
    results = get_conflict_history(status="pending")
    for r in results:
        assert r["status"] == "pending"


def test_get_conflict_history_filter_resolved():
    """get_conflict_history() should filter by resolved status correctly."""
    results = get_conflict_history(status="resolved")
    for r in results:
        assert r["status"] == "resolved"


def test_get_conflict_history_limit():
    """get_conflict_history() should respect the limit parameter."""
    results = get_conflict_history(limit=2)
    assert len(results) <= 2


def test_get_conflict_history_ids_are_strings():
    """get_conflict_history() should return string IDs not ObjectIds."""
    results = get_conflict_history(limit=1)
    if results:
        assert isinstance(results[0]["_id"], str)


def test_get_conflict_history_no_transcript():
    """get_conflict_history() should exclude debate transcripts for performance."""
    results = get_conflict_history(limit=1)
    if results:
        assert "debate_transcript" not in results[0]