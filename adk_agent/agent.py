# import os
# from dotenv import load_dotenv
# from google.adk.agents import Agent
# from google.adk.tools.mcp_tool import MCPToolset, StdioConnectionParams
# from mcp import StdioServerParameters

# load_dotenv()

# MONGODB_URI = os.getenv("MONGODB_URI")

# root_agent = Agent(
#      model="gemini-2.5-flash",
#     name="conflictmind",
#     instruction="""You are ConflictMind, a personal AI assistant with persistent memory stored in MongoDB Atlas.

# IMPORTANT: You MUST use the available MongoDB tools on every single message:
# 1. ALWAYS call 'find' first to query the 'memories' collection in the 'ConflictMind' database for relevant memories about the user
# 2. ALWAYS call 'insert-many' after every user message to store what you learned as a new memory document in the 'memories' collection with fields: content, memory_type (semantic/episodic/procedural), confidence (1.0), frequency (1), status (active), timestamp

# Be warm, specific and personal. Reference memories naturally.
# Keep responses to 2-4 sentences unless depth is needed.""",
#     tools=[
#         MCPToolset(
#             connection_params=StdioConnectionParams(
#                 server_params=StdioServerParameters(
#                     command="npx",
#                     args=["-y", "mongodb-mcp-server"],
#                     env={
#                         "MDB_MCP_CONNECTION_STRING": MONGODB_URI,
#                     },
#                 ),
#                 timeout=30,
#             ),
#         )
#     ],
# )

import os
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import MCPToolset, StdioConnectionParams
from mcp import StdioServerParameters

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

root_agent = Agent(
    model="gemini-3.1-flash-lite",
    name="conflictmind",
    instruction="""You are ConflictMind, a personal AI assistant with persistent memory stored in MongoDB Atlas.
You remember things about the user across all conversations.
Use MongoDB tools when relevant to store or retrieve memories.
Be warm and personal. Keep responses to 2-3 sentences maximum.""",
    tools=[
        MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="npx",
                    args=["-y", "mongodb-mcp-server"],
                    env={
                        "MDB_MCP_CONNECTION_STRING": MONGODB_URI,
                    },
                ),
                timeout=30,
            ),
        )
    ],
)