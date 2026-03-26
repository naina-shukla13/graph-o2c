import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence

from dotenv import load_dotenv

try:
    import google.generativeai as legacy_genai
except ImportError:
    legacy_genai = None

try:
    from google import genai as new_genai
except ImportError:
    new_genai = None

DB_SCHEMA = """
Tables and key columns:
- sales_order_headers: salesOrder(PK), soldToParty(→customer), totalNetAmount,
  overallDeliveryStatus(C=complete,A=partial,'  '=none),
  overallOrdReltdBillgStatus(C=billed,A=partial,'  '=none), creationDate
- sales_order_items: salesOrder(FK), salesOrderItem, material(→product), netAmount, requestedQuantity
- outbound_delivery_headers: deliveryDocument(PK), actualGoodsMovementDate, overallGoodsMovementStatus
- outbound_delivery_items: deliveryDocument(FK), referenceSdDocument(→salesOrder), plant, actualDeliveryQuantity
- billing_document_headers: billingDocument(PK), soldToParty, totalNetAmount,
  billingDocumentDate, accountingDocument, billingDocumentIsCancelled
- billing_document_items: billingDocument(FK), referenceSdDocument(→deliveryDocument),
  material(→product), netAmount, billingQuantity
- billing_document_cancellations: billingDocument, cancelledBillingDocument
- payments_accounts_receivable: accountingDocument, customer, amountInTransactionCurrency,
  clearingDate, salesDocument(→salesOrder)
- journal_entry_items_accounts_receivable: accountingDocument, referenceDocument(→billingDocument),
  amountInTransactionCurrency, postingDate, clearingDate, customer
- business_partners: businessPartner, customer(→customer id), businessPartnerFullName, industry
- products: product(PK), productType, grossWeight
- product_descriptions: product(FK), productDescription, language
- plants: plant(PK), plantName
- product_plants: product(FK), plant(FK)

Key joins:
sales_order_headers.soldToParty = business_partners.customer
sales_order_items.salesOrder = sales_order_headers.salesOrder
sales_order_items.material = product_descriptions.product
outbound_delivery_items.referenceSdDocument = sales_order_headers.salesOrder
billing_document_items.referenceSdDocument = outbound_delivery_headers.deliveryDocument
billing_document_headers.accountingDocument = journal_entry_items_accounts_receivable.accountingDocument
billing_document_headers.accountingDocument = payments_accounts_receivable.accountingDocument
"""

SYSTEM_PROMPT = f"""
You are a supply chain data analyst for a SAP Order-to-Cash system.
You ONLY answer questions about: sales orders, deliveries, billing, payments, customers, products, plants.

{DB_SCHEMA}

GUARDRAIL: If the question is not related to the supply chain dataset above,
respond ONLY with this exact JSON:
{{"off_topic": true, "message": "This system is designed to answer questions related to the provided dataset only."}}

For valid questions respond ONLY with this JSON (no markdown, no backticks):
{{
  "off_topic": false,
  "sql": "your SQLite SQL here",
  "explanation": "one line: what this query does"
}}

SQLite rules:
- Always LIMIT 50 unless user asks for more
- Use LEFT JOIN for flow tracing (preserve incomplete chains)
- Use COALESCE for nullable fields
- For status codes: overallDeliveryStatus C=Completed A=Partial ''=None
- Never hallucinate column names — use only columns listed above
"""


def _load_env() -> None:
    backend_dir = Path(__file__).resolve().parent
    # Try both locations
    load_dotenv(dotenv_path=backend_dir / ".env")          # backend/.env  ← yours is here
    load_dotenv(dotenv_path=backend_dir.parent / ".env")   # root/.env
print("KEY LOADED:", bool(os.getenv("GEMINI_API_KEY")))

def _generate_with_model(prompt: str) -> str:
    _load_env()
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GROQ_API_KEY is missing. Set it in .env.")

    from groq import Groq
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return response.choices[0].message.content or ""


def _strip_markdown_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _history_to_text(history: Sequence[Any]) -> str:
    recent = list(history)[-3:]
    lines: List[str] = []
    for idx, turn in enumerate(recent, start=1):
        role = "user"
        content = ""
        if isinstance(turn, dict):
            role = str(turn.get("role", "user"))
            content = str(turn.get("content", ""))
        elif isinstance(turn, (tuple, list)) and len(turn) >= 2:
            role = str(turn[0])
            content = str(turn[1])
        else:
            content = str(turn)
        lines.append(f"{idx}. {role}: {content}")
    return "\n".join(lines) if lines else "No prior turns."


def check_and_generate(question: str, history: Sequence[Any]) -> Dict[str, Any]:
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        "Conversation context (last 3 turns):\n"
        f"{_history_to_text(history)}\n\n"
        f"Current user question:\n{question}\n\n"
        "Return only JSON."
    )

    text = _strip_markdown_fences(_generate_with_model(prompt))
    parsed = json.loads(text)

    if not isinstance(parsed, dict):
        raise ValueError("Gemini response is not a JSON object.")

    return parsed


def summarize_results(question: str, sql: str, results: List[Dict[str, Any]]) -> str:
    preview = results[:20]
    preview_json = json.dumps(preview, ensure_ascii=True, default=str)

    prompt = (
        "You are summarizing SQLite query results for SAP O2C analytics.\n"
        "Answer the user question in 2-3 clear sentences.\n"
        "Use only the provided query results; do not infer missing data.\n"
        "Do not use markdown.\n\n"
        f"Question: {question}\n"
        f"SQL used: {sql}\n"
        f"First 20 rows JSON: {preview_json}\n"
    )

    summary = _strip_markdown_fences(_generate_with_model(prompt)).strip()
    if not summary:
        summary = "No summary could be generated from the results."

    return f"{summary} Based on {len(results)} records found."


def extract_node_ids(results: List[Dict[str, Any]]) -> List[str]:
    node_ids: List[str] = []
    seen = set()

    key_prefix_map = {
        "salesorder": "SalesOrder",
        "referencedsdocument": "SalesOrder",
        "salesdocument": "SalesOrder",
        "deliverydocument": "Delivery",
        "billingdocument": "BillingDocument",
        "cancelledbillingdocument": "BillingDocument",
        "customer": "Customer",
        "soldtoparty": "Customer",
    }

    generic_patterns = [
        (re.compile(r"\b\d{6,12}\b"), "SalesOrder"),
        (re.compile(r"\b(3\d{8,11})\b"), "Customer"),
    ]

    def add(prefix: str, raw: Any) -> None:
        value = str(raw).strip()
        if not value:
            return
        node_id = f"{prefix}_{value}"
        if node_id not in seen:
            seen.add(node_id)
            node_ids.append(node_id)

    for row in results:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            key_norm = str(key).strip().lower()
            if key_norm in key_prefix_map:
                add(key_prefix_map[key_norm], value)
                continue

            if value is None:
                continue
            text = str(value)
            for pattern, prefix in generic_patterns:
                for match in pattern.findall(text):
                    add(prefix, match)

    return node_ids
