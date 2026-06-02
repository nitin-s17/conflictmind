'''
==============================================================================
Creates Embeddings from the user query

WHY EMBEDDINGS?
    Without embeddings, searching for "what does user prefer?"
    would never find "User likes concise answers" because
    they share no words. With embeddings, both phrases produce
    similar vectors so Atlas finds them as related.
 
FLOW:
    1. get_genai_client() creates a Gemini API connection (once)
    2. get_embedding(text) sends text to Gemini's embedding model
    3. Gemini returns 768 decimal numbers representing the text's meaning
    4. These 768 numbers are stored in Atlas alongside the memory text
 
HOW IT FITS INTO THE PROJECT:
    Any text (memory or query)
        ↓
    embeddings.py — calls Gemini API
        ↓
    768 numbers (vector)
        ↓
    memories.py — stores in Atlas or uses for vector search
 
MODEL USED:
    gemini-embedding-001
    Output: 768 dimensions (matches our Atlas vector search index)
==============================================================================
'''
import os
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_genai_client():
    global _client

    # If the client already exists, return
    if _client is not None:
        return _client
    
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError("GEMINI API KEY is not set")
    
    _client = genai.Client(api_key=api_key)
    print("Gemini Client Initialized")
    return _client

def get_embedding(text: str) -> list[float]:
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text")
    
    # Truncate to 2000 characters — well within Gemini's token limit
    text = text[:2000]

    client = get_genai_client()

    for attempt in range(3):
        try:
            response = client.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=768)
            )
            return response.embeddings[0].values
        except Exception as e:
            if attempt == 2:
                raise Exception(f"Embedding failed after 3 attempts: {e}")
            print(f"Embedding attempt {attempt + 1} failed, retrying...")
            time.sleep(1)
