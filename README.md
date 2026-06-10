# ConflictMind — AI That Remembers You

> An AI agent with persistent memory and adversarial conflict reconciliation. When it learns contradictory facts about you, it debates them — and resolves them.

**Live demo:** https://conflictmind-674810100969.us-central1.run.app

---

## What It Does

ConflictMind is a personal AI assistant that stores everything it learns about you in MongoDB Atlas. When two memories contradict each other, a structured three-step Gemini debate runs between them — Memory A argues, Memory B argues, a Gemini judge resolves — and the unified result is written back with the full debate history attached.

---

## Architecture

```
Browser (ConflictMind UI)
      │
      ▼
Flask (app.py)  ──────────────────────────────────────┐
      │                                               │
      ▼                                               ▼
Google ADK Agent (adk_agent/)              memory_layer / reconciler
  - gemini-2.5-flash via Vertex AI           - write_memory()
  - MCPToolset → mongodb-mcp-server          - retrieve_memories()
  - FunctionTool → store_memory()            - detect_conflicts()
      │                                      - adversarial debate
      ▼                                               │
MongoDB Atlas (M0)  ◄──────────────────────────────────┘
  - memories collection (+ vector search)
  - conflict_pairs collection
```

**Key design decision:** The MongoDB MCP server (`mongodb-mcp-server`) is installed globally at Docker **build time** (`npm install -g mongodb-mcp-server`) rather than spawned at runtime. This avoids cold-start failures on Cloud Run and eliminates the need for Node.js process management inside the container.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI agent | Google ADK (`google-adk`) + Gemini 2.5 Flash |
| LLM inference | Vertex AI (application default credentials) |
| Agent tools | MongoDB MCP server via `MCPToolset` |
| Memory store | MongoDB Atlas M0 + vector search (text embeddings) |
| Backend | Flask + Flask-CORS |
| Deployment | Google Cloud Run + Docker |

---

## Project Structure

```
conflictmind-memory/
├── app.py                  # Flask backend — all routes + ADK session wiring
├── adk_agent/
│   └── agent.py            # ADK root_agent with MCPToolset + store_memory tool
├── memory_layer/
│   ├── db.py               # MongoDB Atlas connection + collection accessors
│   └── memories.py         # write_memory, retrieve_memories, get_conflict_history
├── reconciler/
│   ├── reconciler_api.py   # Flask blueprint — /reconcile, /conflicts endpoints
│   ├── detect.py           # Conflict detection (vector similarity + LLM classifier)
│   ├── debate.py           # Three-step adversarial debate pipeline
│   └── background_worker.py
├── templates/
│   └── index.html          # Frontend (D3 memory graph + chat UI)
├── Dockerfile
├── startup.sh              # Starts ADK server (port 8000) then Flask (port 8080)
├── requirements.txt
└── setup_atlas.py          # One-time Atlas index setup
```

---

## How the Conflict Pipeline Works

1. **Write** — every user message is summarized and stored as a memory via `store_memory()` (called by the ADK agent as a `FunctionTool`)
2. **Detect** — vector search finds memories with cosine similarity > 0.85 against the new memory; an LLM `classify_conflict()` call filters out false positives
3. **Debate** — three Gemini calls: Memory A argues its case → Memory B argues its case → judge synthesizes a resolved memory
4. **Resolve** — unified memory written to Atlas with `status: resolved` and full `debate_transcript` attached to the conflict pair


---

## Running Locally

### Prerequisites
- Python 3.11+
- Node.js 20+
- `gcloud` CLI authenticated (`gcloud auth application-default login`)
- MongoDB Atlas M0 cluster with vector search index on `memories`

### Setup

```bash
git clone https://github.com/nitin-s17/conflictmind-memory
cd conflictmind-memory

pip install -r requirements.txt
npm install -g mongodb-mcp-server
```

### Environment variables (`.env`)

```
MONGODB_URI=mongodb+srv://...
MONGODB_DB_NAME=ConflictMind
GOOGLE_CLOUD_PROJECT=maximal-kingdom-499004-r9
GOOGLE_GENAI_USE_VERTEXAI=true
```

### Run

```bash
# Terminal 1 — ADK agent server
adk api_server adk_agent/ --port 8000

# Terminal 2 — Flask backend
python app.py
```

Open `http://localhost:8080`

---

## Deployment (Cloud Run)

```bash
gcloud builds submit --tag gcr.io/maximal-kingdom-499004-r9/conflictmind
gcloud run deploy conflictmind \
  --image gcr.io/maximal-kingdom-499004-r9/conflictmind \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars MONGODB_URI=...,GOOGLE_CLOUD_PROJECT=...,GOOGLE_GENAI_USE_VERTEXAI=true
```

The `startup.sh` starts the ADK server on port 8000 first, waits for it to be healthy, then starts Flask on port 8080 (Cloud Run's `PORT`).

> **Note:** Add a `.gcloudignore` to exclude `node_modules/`, `__pycache__/`, `.env`, and test files before submitting to avoid oversized builds.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Frontend UI |
| `POST` | `/chat` | Send message → ADK agent → response + memories used |
| `GET` | `/memories` | All active memories |
| `GET` | `/conflicts` | Conflict history |
| `GET` | `/memory-graph` | Graph nodes + edges for D3 visualization |
| `GET` | `/memory/<id>` | Single memory detail + conflict history |
| `POST` | `/store-memory` | Directly store a memory (used by ADK agent) |
| `GET` | `/health` | Health check |
| `GET` | `/debug/adk` | ADK server status |


## Hackathon

Built for the **Google × MongoDB Hackathon** (June 2026).
Hard requirements met: Google ADK integration, MongoDB MCP server, Vertex AI, MongoDB Atlas vector search.