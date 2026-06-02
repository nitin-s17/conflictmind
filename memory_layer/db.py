'''
====================================================================================
Find the Atlas Database, login using credentials and access the right collection

FLOW:
    1. Load environment variables from .env (MONGODB_URI, MONGODB_DB_NAME)
    2. First call to get_db() creates the connection and pings Atlas
    3. All subsequent calls reuse the same connection (singleton pattern)
    4. get_memories_collection() and get_conflict_pairs_collection()
       are convenience functions so other files don't need to know
       the collection names

HOW IT FITS INTO THE PROJECT:
    .env (credentials)
        ↓
    db.py (connection)
        ↓
    memories.py (read/write operations)
        ↓
    MongoDB Atlas (storage + vector search)
====================================================================================
'''

import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv

# Reads the .env file and gets the variables
load_dotenv()

# Gets filled in the first connection
_client = None
_db = None

# Main function that others will call to get access to the DB
def get_db():
    global _client, _db

    # If previous connection exist, then return the connection
    if _db is not None:
        return _db

    # Gets the value from .env file    
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB_NAME", "ConflictMind")

    if not uri:
        raise ValueError("MONGODB_URI is not set. Check .env files")
    
    if not uri.startswith("mongodb"):
        raise ValueError("MONGODB_URI looks incorrect. Should start with mongodb:// or mongodb+srv://")

    # Connect to Atlas, waits for 15s before giving timeout
    _client = MongoClient(uri, serverSelectionTimeoutMS=15000)

    try:
        _client.admin.command("ping")
        print("Connected to Atlas")
    except ConnectionFailure as e:
        raise ConnectionFailure(f"Could not connect to Atlas: {e}")

    _db = _client[db_name]
    return _db

# Access the memory part which stores things that conflict mind learns about users
def get_memories_collection():
    return get_db()["memories"]

# In memory, when 2 pairs contradict each other, stored in conflict pairs
def get_conflict_pairs_collection():
    return get_db()["conflict_pairs"]
