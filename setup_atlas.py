'''
=====================================================================================================
Setup Atlas DB for the first time, creates collections : Memory and Conflict pairs, Creates Indexes
Runs only one time

WHAT IT DOES:
    1. Creates the 'memories' collection
       — where all memory documents are stored
    2. Creates the 'conflict_pairs' collection
       — where reconciler stores conflicting memory pairs
    3. Creates indexes on commonly queried fields
       — so MongoDB can find documents quickly without scanning everything
    4. Prints the JSON needed to create the Vector Search index in Atlas UI
       — this cannot be automated, must be done manually in Atlas UI
 
WHY INDEXES?
    Without indexes, MongoDB reads every single document one by one.
    With indexes, it jumps directly to what you need — like a book index
    vs reading the whole book to find one word.
 
    memories indexes:
        idx_status          — filter by active/resolved/decayed quickly
        idx_timestamp       — sort by newest first
        idx_conversation    — find all memories from one conversation
        idx_memory_type     — filter by semantic/episodic/procedural
 
    conflict_pairs indexes:
        idx_cp_status       — find pending conflicts quickly
        idx_cp_detected_at  — sort by newest conflict first
        idx_cp_memory_a     — find conflicts involving a specific memory
        idx_cp_memory_b     — find conflicts involving a specific memory
 
WHY THE VECTOR SEARCH INDEX IS SEPARATE?
    Regular indexes (above) are created via Python code.
    Vector Search indexes must be created through Atlas UI or Admin API.
    This script prints the exact JSON to paste so you don't forget.
 
FLOW:
    Run once → creates collections → creates indexes
        ↓
    Go to Atlas UI → paste vector search JSON → create index
        ↓
    Database is fully ready for the rest of the project
 
HOW IT FITS INTO THE PROJECT:
    setup_atlas.py (run once)
        ↓
    Atlas database ready
        ↓
    db.py connects to it
        ↓
    memories.py reads/writes to it
=====================================================================================================
'''

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from memory_layer.db import get_db, get_memories_collection, get_conflict_pairs_collection
from pymongo import ASCENDING, DESCENDING

def setup_collections():
    db = get_db()
    existing_collections = db.list_collection_names()

    if "memories" not in existing_collections:
        db.create_collection("memories")
        print("Created Collection: Memories")
    else: 
        print("Collection Memories already exists")

    if "conflict_pairs" not in existing_collections:
        db.create_collection("conflict_pairs")
        print("Created Collection: Conflict pairs")
    else:
        print("Collection Conflict pairs already exists")

def setup_indexes():
    memories = get_memories_collection()
    conflict_pairs = get_conflict_pairs_collection()

    # Index Memory Collection
    memories.create_index([("status", ASCENDING)], name="idx_status")
    memories.create_index([("timestamp", DESCENDING)], name="idx_timestamp")
    memories.create_index([("source_conversation_id", ASCENDING)], name="idx_conversation")
    memories.create_index([("memory_type", ASCENDING)], name="idx_memory_type")
    print("Memory collection Indexed")

    # Index Conflict pairs
    conflict_pairs.create_index([("status", ASCENDING)], name="idx_cp_status")
    conflict_pairs.create_index([("detected_at", DESCENDING)], name="idx_cp_detected_at")
    conflict_pairs.create_index([("memory_a_id", ASCENDING)], name="idx_cp_memory_a")
    conflict_pairs.create_index([("memory_b_id", ASCENDING)], name="idx_cp_memory_b")
    print("Conflict pairs collection Indexed")

    # TODO: Setup Vector Indexing in Atlas UI

# Main function
if __name__ == "__main__":
    print("\n ConflictMind — Atlas Setup\n")
    setup_collections()
    setup_indexes()
    print("Setup complete.\n")