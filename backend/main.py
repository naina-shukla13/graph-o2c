import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

import sqlite3
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .graph_builder import build_graph, find_order_chain, get_graph_sample, get_neighbors
from llm import check_and_generate, extract_node_ids, summarize_results


app = FastAPI(title="Graph O2C API")
DB_PATH = Path(r"D:\DOCUMENTSS\graph-o2c\backend\data.db")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str
    history: List[Any] = Field(default_factory=list)


@app.on_event("startup")
def startup_event() -> None:
    app.state.G = build_graph()


@app.get("/health")
def health() -> Dict[str, Any]:
    G = app.state.G
    return {
        "status": "ok",
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
    }


@app.get("/graph")
def graph() -> Dict[str, List[Dict[str, Any]]]:
    return get_graph_sample(app.state.G, max_per_type=15)


@app.get("/expand/{node_id}")
def expand(node_id: str) -> Dict[str, List[Dict[str, Any]]]:
    return get_neighbors(app.state.G, node_id)


@app.get("/trace/{sales_order_id}")
def trace(sales_order_id: str) -> Dict[str, Any]:
    chain = find_order_chain(app.state.G, f"SalesOrder_{sales_order_id}")
    return {"nodes": chain["nodes"], "edges": chain["edges"]}


@app.post("/query")
def query(payload: QueryRequest) -> Dict[str, Any]:
    generated = check_and_generate(payload.question, payload.history)

    if generated.get("off_topic"):
        return {
            "answer": generated.get(
                "message",
                "This system is designed to answer questions related to the provided dataset only.",
            ),
            "sql": None,
            "data": [],
            "nodes_to_highlight": [],
        }

    sql = generated.get("sql", "")
    if not sql:
        return {
            "answer": "I could not generate a valid SQL query for this question.",
            "sql": None,
            "data": [],
            "nodes_to_highlight": [],
        }

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(sql)
            columns = [col[0] for col in (cur.description or [])]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:  # noqa: BLE001
        return {
            "answer": f"Query error: {str(e)}",
            "sql": sql,
            "data": [],
            "nodes_to_highlight": [],
        }

    try:
        answer = summarize_results(payload.question, sql, rows[:20])
    except Exception as exc:  # noqa: BLE001
        answer = f"Query executed successfully, but summarization failed: {exc}"

    nodes_to_highlight = extract_node_ids(rows)

    return {
        "answer": answer,
        "sql": sql,
        "data": rows[:20],
        "nodes_to_highlight": nodes_to_highlight,
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
