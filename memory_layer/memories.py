'''
========================================================================================
Convert the content/query into embeddings
Create a memory document with required fields and push into memory collection to store
Retrieve memories

MEMORY DOCUMENT STRUCTURE:
    {
        "_id":                   MongoDB auto-generated unique ID
        "content":               the memory text (human readable)
        "embedding":             768 numbers (for vector search)
        "memory_type":           "semantic" | "episodic" | "procedural"
        "source_conversation_id": which conversation created this
        "timestamp":             when it was created (UTC)
        "confidence":            0.0 to 1.0, decays over time
        "frequency":             how many times this was recalled
        "status":                "active" | "conflicted" | "resolved" | "decayed"
    }
 
FLOW — WRITING A MEMORY:
    New information from conversation
        ↓
    write_memory(content, memory_type, conversation_id)
        ↓
    get_embedding() → converts text to 768 numbers via Gemini
        ↓
    build memory document with all fields
        ↓
    insert into Atlas memories collection
        ↓
    return new memory ID
 
FLOW — RETRIEVING MEMORIES:
    User sends a message to the agent
        ↓
    retrieve_memories(query, top_k=5)
        ↓
    get_embedding() → converts query to 768 numbers
        ↓
    Atlas vector search finds closest memory vectors
        (filtered to status="active" only)
        ↓
    returns top 5 most semantically relevant memories
        ↓
    Agent adds these to Gemini's context before responding
 
FLOW — MEMORY LIFECYCLE:
    Memory created → confidence=1.0, frequency=1, status="active"
        ↓
    Gets recalled → update_memory_frequency() → frequency increases
        (higher frequency = slower decay = stays relevant longer)
        ↓
    apply_memory_decay() runs periodically (e.g. once per day)
        → confidence reduces based on age and frequency
        → confidence < 0.1 → status = "decayed"
        → never retrieved again
        ↓
    Conflicts with another memory
        → both marked status = "conflicted"
        → Reconciler runs debate
        → new unified memory created
        → mark_memory_resolved() → status = "resolved"
 
DECAY ALGORITHM:
    Runs entirely inside MongoDB — zero data transferred to Python.
    Formula:
        recency_factor  = 1 + (days_old / 30)
        actual_decay    = (base_decay x recency_factor) / (1 + frequency)
        new_confidence  = confidence x (1 - actual_decay)
 
    Examples (base_decay = 0.05):
        New memory,  frequency=1  → actual_decay = 0.025  (slow)
        Old memory,  frequency=1  → actual_decay = 0.100  (fast)
        Old memory,  frequency=9  → actual_decay = 0.010  (protected by frequency)
 
HOW IT FITS INTO THE PROJECT:
       Agent                            Reconciler
         ↓                                  ↓
    retrieve_memories()         save_conflict_pair()
    write_memory()              save_reconciliation_result()
         ↓                                  ↓
              memories.py (this file)
                      ↓
              MongoDB Atlas
========================================================================================
'''

import os
from datetime import datetime, timezone
from bson  import ObjectId
from memory_layer.db import get_memories_collection, get_conflict_pairs_collection
from memory_layer.embeddings import get_embedding

def write_memory(content: str, memory_type: str, conversation_id: str, auto_detect: bool = True) -> str:
    """
    Converts text to an embedding and stores it as a memory in Atlas.
    
    Args:
        content: the memory text e.g. "User prefers concise answers"
        memory_type: "semantic", "episodic", or "procedural"
        conversation_id: which conversation this memory came from
    
    Returns:
        the ID of the newly created memory as a string
    """
    
    if not content or not content.strip():
        raise ValueError("Memory content cannot be empty")
    
    valid_types = ["semantic", "episodic", "procedural"]
    if memory_type not in valid_types:
        raise ValueError(f"memory_type must be one of {valid_types}")

    # Gets the embedding for the content and store it
    embedding = get_embedding(content)

    memory_document = {
        "content": content,
        "embedding": embedding,
        "memory_type": memory_type,
        "source_conversation_id": conversation_id,
        "timestamp": datetime.now(timezone.utc),
        "confidence": 1.0,
        "frequency": 1,
        "status": "active"
    }

    # Insert the current memory document into the memory
    memory_collection = get_memories_collection()
    result = memory_collection.insert_one(memory_document)
    
    new_memory_id = str(result.inserted_id)
    print(f"Memory written: {new_memory_id}")
    # Check if this new memory conflicts with any existing memories
    if auto_detect:
        conflicts = detect_conflicts(new_memory_id, content, memory_type)
        for conflict in conflicts:
            save_conflict_pair(
                memory_a_id=new_memory_id,
                memory_b_id=conflict["_id"],
                memory_a_content=content,
                memory_b_content=conflict["content"],
                similarity_score=conflict["similarity_score"]
            )

    return new_memory_id

def retrieve_memories(query: str, top_k: int = 5) -> list[dict]:
    """
    Semantically searches Atlas for memories relevant to the query.

    Args:
        query: the search text e.g. "what does the user prefer?"
        top_k: how many memories to return (default 5)

    Returns:
        list of memory documents most relevant to the query
    """

    # Get the embedding values for query
    query_embedding = get_embedding(query)

    memory_collection = get_memories_collection()
    
    results = memory_collection.aggregate([
    {
        "$vectorSearch": {
            "index": "memory_vector_index",
            "path": "embedding",
            "queryVector": query_embedding,
            "numCandidates": top_k * 10,
            "limit": top_k,
            "filter": {
                "status": {"$eq": "active"}
            }
        }
    },
    # Add similarity score
    {
        "$addFields": {
            "similarity_score": {"$meta": "vectorSearchScore"}
        }
    }
])

    memories = []
    for memory in results:
        memory["_id"] = str(memory["_id"])
        memories.append(memory)
    
    return memories

def update_memory_frequency(memory_id: str) -> None:
    """
    Increments the frequency counter of a memory by 1.
    Called every time a memory is retrieved and used by the agent.

    Args:
        memory_id: the ID of the memory that was used
    """

    memory_collection = get_memories_collection()

    memory_collection.update_one(
        {"_id": ObjectId(memory_id)},
        {"$inc": {"frequency": 1}}
    )
    print(f"Frequency updated for memory: {memory_id}")

def apply_memory_decay(base_decay: float = 0.05) -> None:
    """
    Applies intelligent decay to memories entirely inside MongoDB.
    No data transferred between Python and Atlas — zero network overhead.
    All math runs inside Atlas in a single aggregation pipeline call.

    Decay formula:
        actual_decay = (base_decay x recency_factor) / (1 + frequency)
        new_confidence = confidence x (1 - actual_decay)

    Where:
        recency_factor = 1 + (days_old / 30)
        Higher frequency = slower decay (memory is still relevant)
        Older memory = faster decay (more likely to be stale)

    Memories below confidence 0.1 are marked as decayed.

    Args:
        base_decay: base decay rate (default 5%)
    """
    memory_collection = get_memories_collection()

    # Capture current time once in Python so every memory
    # is compared against the exact same timestamp
    now = datetime.now(timezone.utc)

    memory_collection.aggregate([

        # Stage 1 — only process active memories
        {
            "$match": {"status": "active"}
        },

        # Stage 2 — calculate days_old and recency_factor
        # recency_factor = 1 + (days_old / 30)
        # older memories decay faster
        {
            "$addFields": {
                "days_old": {
                    "$dateDiff": {
                        "startDate": "$timestamp",
                        "endDate": now,
                        "unit": "day"
                    }
                },
                "recency_factor": {
                    "$add": [
                        1,
                        {"$divide": [
                            {"$dateDiff": {
                                "startDate": "$timestamp",
                                "endDate": now,
                                "unit": "day"
                            }},
                            30
                        ]}
                    ]
                }
            }
        },

        # Stage 3 — calculate actual decay rate for this specific memory
        # actual_decay = (base_decay * recency_factor) / (1 + frequency)
        # high frequency memories decay much slower
        {
            "$addFields": {
                "actual_decay": {
                    "$divide": [
                        {"$multiply": [base_decay, "$recency_factor"]},
                        {"$add": [1, "$frequency"]}
                    ]
                }
            }
        },

        # Stage 4 — calculate new confidence
        # new_confidence = confidence * (1 - actual_decay)
        {
            "$addFields": {
                "new_confidence": {
                    "$multiply": [
                        "$confidence",
                        {"$subtract": [1, "$actual_decay"]}
                    ]
                }
            }
        },

        # Stage 5 — determine new status
        # below 0.1 confidence → decayed, otherwise stays active
        {
            "$addFields": {
                "new_status": {
                    "$cond": {
                        "if": {"$lt": ["$new_confidence", 0.1]},
                        "then": "decayed",
                        "else": "active"
                    }
                }
            }
        },

        # Stage 6 — write results back to Atlas
        # $$new refers to the pipeline result document
        # only updates confidence and status, leaves everything else untouched
        {
            "$merge": {
                "into": "memories",
                "on": "_id",
                "whenMatched": [
                    {"$addFields": {
                        "confidence": "$$new.new_confidence",
                        "status": "$$new.new_status"
                    }}
                ],
                "whenNotMatched": "discard"
            }
        }
    ])

    print(f"Memory decay applied")

def mark_memory_resolved(memory_id: str, resolved_memory_id: str) -> None:
    """
    Marks a memory as resolved after a conflict has been reconciled.
    Called by Reconciler after the debate produces a new unified memory.

    Args:
        memory_id: the ID of the old conflicting memory to mark resolved
        resolved_memory_id: the ID of the new unified memory that replaced it
    """

    memory_collection = get_memories_collection()
    
    memory_collection.update_one(
        {"_id": ObjectId(memory_id)},
        {"$set": {
            "status": "resolved",
            "resolved_by": resolved_memory_id
        }}
    )
    
    print(f"Memory marked resolved: {memory_id}")

def detect_conflicts(new_memory_id: str, new_content: str, memory_type: str = None, threshold: float = 0.85) -> list[dict]:
    """
    Checks if a newly written memory conflicts with any existing memories.
    Uses vector search to find semantically similar memories,
    then flags pairs above the similarity threshold as potential conflicts.

    Args:
        new_memory_id: ID of the newly written memory
        new_content:   text content of the new memory
        threshold:     similarity score above which we consider a conflict
                       (default 0.85 — very similar but not identical)

    Returns:
        list of conflicting memory documents
    """

    # Convert new content into embeddings
    query_embedding = get_embedding(new_content)

    memory_collection = get_memories_collection()

    # Calculate pipeline threshold before the aggregate call
    pipeline_threshold = threshold - 0.05 if memory_type else threshold

    # Find semantically similar active memories
    results = memory_collection.aggregate([
        {
            "$vectorSearch": {
                "index": "memory_vector_index",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": 50,
                "limit": 10,
                "filter": {"status": "active"}
            }
        },
        # Add the similarity score as a field
        {
            "$addFields": {
                "similarity_score": {"$meta": "vectorSearchScore"}
            }
        },
        # Keep memories above threshold (0.85)
        {
            "$match": {
                "similarity_score": {"$gte": pipeline_threshold}
            }
        }
    ])

    conflicts = []
    for memory in results:
        memory["_id"] = str(memory["_id"])

        if memory["_id"] == new_memory_id:
            continue

        # Same type → keep at lower threshold (already passed pipeline)
        # Different type → enforce full threshold
        if memory.get("memory_type") != memory_type:
            if memory["similarity_score"] < threshold:
                continue

        conflicts.append(memory)

    return conflicts


def save_conflict_pair(
    memory_a_id: str,
    memory_b_id: str,
    memory_a_content: str,
    memory_b_content: str,
    similarity_score: float
) -> str:
    """
    Stores two conflicting memories as a conflict pair in Atlas.
    Person 2 queries conflict_pairs for status="pending" to run debates.

    Args:
        memory_a_id:      ID of the first conflicting memory
        memory_b_id:      ID of the second conflicting memory
        memory_a_content: text of the first memory (so Person 2 doesn't need to fetch it)
        memory_b_content: text of the second memory
        similarity_score: how similar the two memories are (from vector search)

    Returns:
        ID of the newly created conflict pair document
    """

    conflicts_collection = get_conflict_pairs_collection()

    # Check if this conflict pair already exists
    existing = conflicts_collection.find_one({
        "$or": [
            {"memory_a_id": memory_a_id, "memory_b_id": memory_b_id},
            {"memory_a_id": memory_b_id, "memory_b_id": memory_a_id}
        ]
    })

    if existing:
        print(f"Conflict pair already exists, skipping")
        return str(existing["_id"])

    conflict_document = {
        "memory_a_id": memory_a_id,
        "memory_b_id": memory_b_id,
        "memory_a_content": memory_a_content,
        "memory_b_content": memory_b_content,
        "similarity_score": similarity_score,
        "status": "pending",        # pending → resolved after Reconcilers debate
        "detected_at": datetime.now(timezone.utc),
        "debate_transcript": None,  
        "resolved_memory_id": None  # filled in after debate produces new memory
    }

    result = conflicts_collection.insert_one(conflict_document)
    conflict_id = str(result.inserted_id)

    # Mark both memories as conflicted so they're flagged in the UI
    memories_collection = get_memories_collection()
    memories_collection.update_many(
        {"_id": {"$in": [ObjectId(memory_a_id), ObjectId(memory_b_id)]}},
        {"$set": {"status": "conflicted"}}
    )

    print(f"Conflict pair saved: {conflict_id}")
    return conflict_id

def save_reconciliation_result(
    conflict_pair_id: str,
    debate_transcript: dict,
    resolved_content: str,
    resolved_memory_type: str = "semantic"  # Default memory type is Semantic, Reconciler can override
) -> str:
    """
    Stores the outcome of Reconciler debate back into Atlas.
    Creates a new unified memory and updates the conflict pair as resolved.

    Args:
        conflict_pair_id:  ID of the conflict pair that was debated
        debate_transcript: the full debate as a dict from Reconciler
                          e.g. {"argument_a": "...", "argument_b": "...", "judge_reasoning": "..."}
        resolved_content:  the new unified memory text Reconciler produced
                          e.g. "User prefers concise answers unless topic is complex"

    Returns:
        ID of the newly created unified memory
    """

    # Step 1 — write the new unified memory to Atlas
    resolved_memory_id = write_memory(
        content=resolved_content,
        memory_type=resolved_memory_type,
        conversation_id=f"reconciliation_{conflict_pair_id}"
    )

    # Step 2 — update the conflict pair with debate results
    collection = get_conflict_pairs_collection()
    collection.update_one(
        {"_id": ObjectId(conflict_pair_id)},
        {"$set": {
            "status": "resolved",
            "debate_transcript": debate_transcript,
            "resolved_memory_id": resolved_memory_id,
            "resolved_at": datetime.now(timezone.utc)
        }}
    )

    # Step 3 — fetch the conflict pair to get both memory IDs
    conflict_pair = collection.find_one({"_id": ObjectId(conflict_pair_id)})
    if not conflict_pair:
        raise ValueError(f"Conflict pair not found: {conflict_pair_id}")

    # Step 4 — mark both old conflicting memories as resolved
    mark_memory_resolved(conflict_pair["memory_a_id"], resolved_memory_id)
    mark_memory_resolved(conflict_pair["memory_b_id"], resolved_memory_id)

    print(f"Reconciliation saved. New memory: {resolved_memory_id}")
    return resolved_memory_id

def get_conflict_history(status: str = None, limit: int = 20) -> list[dict]:
    """
    Returns past conflict pairs from Atlas for the UI and Reconciler.
    
    Args:
        status: filter by "pending", "resolved", or None for all conflicts
        limit:  how many conflicts to return (default 20)

    Returns:
        list of conflict pair documents sorted by newest first
    """

    conflicts_collection = get_conflict_pairs_collection()

    # Build filter
    query_filter = {}
    if status is not None:
        query_filter["status"] = status

    # Sort by newest conflict first
    results = list(conflicts_collection.find(
        query_filter,
        {"debate_transcript": 0}
    ).sort("detected_at", -1).limit(limit))

    for result in results:
        result["_id"] = str(result["_id"])

    print(f"Retrieved {len(results)} conflict pairs")
    return results