# Supply Chain Graph Explorer

A context graph system with an LLM-powered natural language query interface for SAP Order-to-Cash (O2C) data.

![Supply Chain Explorer](https://img.shields.io/badge/Stack-Next.js%20%7C%20FastAPI%20%7C%20SQLite%20%7C%20Groq-blue)

---

## Demo

> Frontend: [localhost:3000](http://localhost:3000) | Backend: [localhost:8000](http://localhost:8000)

---

## What It Does

- Ingests a SAP O2C dataset and builds a **graph of interconnected business entities**
- Visualizes the graph interactively — click any node to expand its relationships
- Provides a **chat interface** where users ask questions in natural language
- The LLM dynamically generates **SQL queries**, executes them against the real dataset, and returns **data-backed answers**
- Highlights graph nodes referenced in query results
- Enforces **guardrails** to reject off-topic prompts

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (Next.js)                   │
│                                                         │
│   ReactFlow Graph Visualizer  │  Chat Interface (Axios) │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP (REST)
┌────────────────────▼────────────────────────────────────┐
│                  Backend (FastAPI)                       │
│                                                         │
│  /graph → NetworkX graph sample                        │
│  /expand/:id → node neighborhood                       │
│  /query → LLM → SQL → SQLite → NL answer               │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
   SQLite (data.db)         Groq API (LLM)
   590 nodes / 3672 edges   llama-3.3-70b-versatile
```

### Key Files

```
graph-o2c/
├── backend/
│   ├── main.py           # FastAPI app, REST endpoints
│   ├── llm.py            # Groq LLM integration, prompting, guardrails
│   ├── graph_builder.py  # NetworkX graph construction from SQLite
│   ├── ingest.py         # Dataset ingestion and normalization
│   └── data.db           # SQLite database
├── frontend/
│   └── app/
│       └── page.tsx      # Single-page React app with ReactFlow + chat
└── data/                 # Raw CSV/Excel source files
```

---

## Graph Modeling

### Nodes (7 entity types)

| Node Type | Represents | Example |
|-----------|-----------|---------|
| `Customer` | Business partner / sold-to party | `Customer_310000108` |
| `SalesOrder` | SAP sales order header | `SalesOrder_740506` |
| `Delivery` | Outbound delivery document | `Delivery_80738041` |
| `BillingDocument` | Invoice / billing doc | `BillingDocument_90504219` |
| `Product` | Material / product | `Product_S8907367039280` |
| `Plant` | Storage/delivery plant | `Plant_PortAlyssatown` |
| `Payment` | Accounts receivable entry | `Payment_...` |

### Edges (relationship types)

| Edge | Meaning |
|------|---------|
| `PLACED` | Customer → SalesOrder |
| `HAS_ITEM` | SalesOrder → Product |
| `DELIVERED_VIA` | SalesOrder → Delivery |
| `STORED_IN` | Delivery → Plant |
| `BILLED_BY` | Delivery → BillingDocument |
| `PAID_BY` | BillingDocument → Payment |

This models the complete **Order-to-Cash flow**: Customer places order → items picked from plant → delivered → billed → paid.

---

## Database Choice: SQLite

**Why SQLite over a dedicated graph database (Neo4j, etc.):**

- The dataset is structured tabular SAP export data — SQLite handles it natively with zero setup
- The LLM generates SQL, which is the most reliable structured query language for LLMs to reason about
- NetworkX is used in-memory for graph traversal and visualization sampling; SQLite for actual query execution
- No need for a graph query language (Cypher, SPARQL) — SQL JOINs express all the O2C relationships we need
- SQLite ships as a single file — no server, no configuration, fully portable

**Tradeoff:** A native graph DB would be faster for deep multi-hop traversals, but for this dataset size (590 nodes, 3672 edges) SQLite with proper indexes is more than sufficient.

---

## LLM Integration & Prompting Strategy

### Model
**Groq `llama-3.3-70b-versatile`** — free tier, low latency (~1-2s), excellent SQL generation quality.

### Prompt Design

The system prompt uses a **schema-injection** approach:

```
You are a supply chain data analyst for a SAP Order-to-Cash system.
You ONLY answer questions about: sales orders, deliveries, billing, payments, customers, products, plants.

[Full DB schema with table names, column names, key joins injected here]

GUARDRAIL: If the question is not related to the supply chain dataset above,
respond ONLY with: {"off_topic": true, "message": "..."}

For valid questions respond ONLY with JSON:
{
  "off_topic": false,
  "sql": "your SQLite SQL here",
  "explanation": "one line: what this query does"
}
```

**Key design decisions:**

1. **JSON-only output** — forces the LLM to return structured data, no markdown fences, making parsing deterministic
2. **Schema injection** — all table names, column names, and key JOIN paths are embedded in the prompt so the LLM never has to guess column names
3. **Two-pass LLM calls** — first call generates SQL, second call summarizes query results in natural language (separated to keep each prompt focused)
4. **Conversation memory** — last 3 turns of history included in each prompt for context continuity
5. **SQLite rules embedded** — `LIMIT 50`, use `LEFT JOIN` for flow tracing, `COALESCE` for nullables, status code meanings

---

## Guardrails

The system enforces domain restrictions at the **LLM prompt level**:

- The system prompt explicitly instructs the model to return `{"off_topic": true}` for any question not related to the supply chain dataset
- Categories rejected: general knowledge, creative writing, coding help, weather, math, etc.
- The backend checks the `off_topic` flag and returns a polite refusal without executing any SQL
- The LLM is also instructed to only use column names from the provided schema — preventing hallucinated column names from causing SQL errors

**Example guardrail response:**
> "This system is designed to answer questions related to the provided dataset only."

---

## Features Implemented

- [x] Graph construction with 7 node types and typed edges
- [x] Interactive graph visualization (ReactFlow) with zoom, pan, minimap
- [x] Node click to expand neighborhood
- [x] Node metadata inspector drawer
- [x] Natural language to SQL translation via LLM
- [x] Data-backed answers (no hallucination — all answers cite record counts)
- [x] SQL transparency (expandable "View SQL" in chat)
- [x] Node highlighting for query results
- [x] Conversation memory (last 3 turns)
- [x] Off-topic guardrails
- [x] Quick-query suggestion buttons

---

## Example Queries

| Question | What it does |
|----------|-------------|
| "Top billed products" | Ranks products by billing document count |
| "Trace order 740506" | Shows full O2C flow for a specific sales order |
| "Incomplete order flows" | Finds orders delivered but not billed |
| "Which customers have the most sales orders?" | Customer-level aggregation |
| "Show payments for billing document 90504219" | Document-level trace |

---

## Setup & Running

### Prerequisites
- Python 3.10+
- Node.js 18+

### Backend

```bash
cd backend
pip install fastapi uvicorn networkx python-dotenv groq
# Create .env file:
echo "GROQ_API_KEY=your_key_here" > .env
uvicorn main:app --reload --port 8000
```

Get a free Groq API key at: https://console.groq.com

### Frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

---

## Tech Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| Frontend | Next.js 16 + React | Fast, SSR-capable, easy deployment |
| Graph viz | ReactFlow | Production-grade, interactive graph library |
| Backend | FastAPI | Async Python, auto-docs, fast |
| Graph engine | NetworkX | In-memory graph traversal, no DB needed |
| Database | SQLite | Zero-config, portable, SQL for LLM compatibility |
| LLM | Groq llama-3.3-70b | Free tier, fast inference, strong SQL generation |
| HTTP client | Axios | Reliable, interceptor support |
| Styling | Tailwind CSS | Utility-first, dark theme support |

---

## AI Tools Used

This project was built with assistance from **Claude (Anthropic)** via claude.ai for:
- Architecture decisions and tradeoffs
- Debugging FastAPI/Next.js integration issues
- LLM prompt engineering and guardrail design
- Fixing CORS, dotenv loading, and Gemini→Groq migration

Session logs are included in `ai-session-logs/claude-conversation.md`.
