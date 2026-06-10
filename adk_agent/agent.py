import os
import requests as req
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import MCPToolset, StdioConnectionParams
from google.adk.tools import FunctionTool
from mcp import StdioServerParameters

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

def store_memory(content: str, memory_type: str = "semantic") -> dict:
    """Store a memory with embeddings and conflict detection."""
    try:
        response = req.post(
            "http://localhost:8080/store-memory",
            json={"content": content, "memory_type": memory_type, "conversation_id": "agent"},
            timeout=30
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}

root_agent = Agent(
    model="gemini-2.5-flash",
    name="conflictmind",
    instruction="""You are ConflictMind, a personal AI assistant with persistent memory stored in MongoDB Atlas.

MANDATORY RULES on EVERY message, no exceptions:

1. ALWAYS call MongoDB 'find' on the 'memories' collection in 'ConflictMind' database to retrieve relevant memories before responding.

2. ALWAYS call store_memory() after every user message to save what you learned. NEVER use MongoDB insertOne — only use store_memory().

3. NEVER respond without doing both steps.

Be warm and personal. Keep responses to 2-3 sentences.""",
    tools=[
        FunctionTool(store_memory),
        MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="mongodb-mcp-server",
                    args=[],
                    env={"MDB_MCP_CONNECTION_STRING": MONGODB_URI},
                ),
                timeout=60,
            ),
        )
    ],
)