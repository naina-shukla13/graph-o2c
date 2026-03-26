import sqlite3
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import networkx as nx


DB_PATH = Path(r"D:\DOCUMENTSS\graph-o2c\backend\data.db")


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _to_float(value: Any) -> Any:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _to_bool(value: Any) -> bool:
    return _as_str(value).strip().lower() in {"true", "1", "x", "yes"}


def _node_id(node_type: str, raw_id: Any) -> str:
    return f"{node_type}_{_as_str(raw_id)}"


def _edge_key(source: str, target: str, label: str) -> Tuple[str, str, str]:
    return source, target, label


def _add_node(
    G: nx.DiGraph,
    node_id: str,
    node_type: str,
    label: Any,
    properties: Dict[str, Any],
) -> None:
    if not node_id or node_id.endswith("_"):
        return
    attrs = {
        "type": node_type,
        "label": _as_str(label) if label not in (None, "") else node_id,
    }
    attrs.update(properties)
    G.add_node(node_id, **attrs)


def _add_edge(
    G: nx.DiGraph,
    edge_seen: Set[Tuple[str, str, str]],
    source: str,
    target: str,
    label: str,
) -> None:
    if not source or not target:
        return
    if source not in G or target not in G:
        return
    key = _edge_key(source, target, label)
    if key in edge_seen:
        return
    edge_seen.add(key)
    G.add_edge(source, target, label=label)


def _serialize_subgraph(G: nx.DiGraph, node_ids: Set[str]) -> Dict[str, List[Dict[str, Any]]]:
    nodes = []
    for node_id in node_ids:
        data = dict(G.nodes[node_id])
        node_type = data.pop("type", "")
        label = data.pop("label", node_id)
        nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "label": label,
                "properties": data,
            }
        )

    edges = []
    for source, target, data in G.edges(data=True):
        if source in node_ids and target in node_ids:
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "label": data.get("label", ""),
                }
            )

    return {"nodes": nodes, "edges": edges}


def build_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    edge_seen: Set[Tuple[str, str, str]] = set()

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Customer nodes.
        for row in cur.execute(
            """
            SELECT customer, businessPartnerFullName, industry
            FROM business_partners
            """
        ):
            customer = _as_str(row["customer"]).strip()
            if not customer:
                continue
            node_id = _node_id("Customer", customer)
            _add_node(
                G,
                node_id,
                "Customer",
                row["businessPartnerFullName"],
                {"industry": _as_str(row["industry"])},
            )

        # Sales order nodes.
        for row in cur.execute(
            """
            SELECT salesOrder, totalNetAmount, overallDeliveryStatus, overallOrdReltdBillgStatus
            FROM sales_order_headers
            """
        ):
            sales_order = _as_str(row["salesOrder"]).strip()
            if not sales_order:
                continue
            node_id = _node_id("SalesOrder", sales_order)
            _add_node(
                G,
                node_id,
                "SalesOrder",
                sales_order,
                {
                    "amount": _to_float(row["totalNetAmount"]),
                    "deliveryStatus": _as_str(row["overallDeliveryStatus"]),
                    "billingStatus": _as_str(row["overallOrdReltdBillgStatus"]),
                },
            )

        # Product nodes.
        for row in cur.execute(
            """
            SELECT p.product, p.productType, d.productDescription
            FROM products p
            LEFT JOIN product_descriptions d ON p.product = d.product
            """
        ):
            product = _as_str(row["product"]).strip()
            if not product:
                continue
            node_id = _node_id("Product", product)
            label = row["productDescription"] if row["productDescription"] not in (None, "") else product
            _add_node(
                G,
                node_id,
                "Product",
                label,
                {"productType": _as_str(row["productType"])},
            )

        # Delivery nodes.
        for row in cur.execute(
            """
            SELECT deliveryDocument, actualGoodsMovementDate, overallGoodsMovementStatus
            FROM outbound_delivery_headers
            """
        ):
            delivery = _as_str(row["deliveryDocument"]).strip()
            if not delivery:
                continue
            node_id = _node_id("Delivery", delivery)
            _add_node(
                G,
                node_id,
                "Delivery",
                delivery,
                {
                    "goodsMovementDate": _as_str(row["actualGoodsMovementDate"]),
                    "status": _as_str(row["overallGoodsMovementStatus"]),
                },
            )

        # Billing document nodes.
        for row in cur.execute(
            """
            SELECT billingDocument, totalNetAmount, billingDocumentIsCancelled
            FROM billing_document_headers
            """
        ):
            billing = _as_str(row["billingDocument"]).strip()
            if not billing:
                continue
            node_id = _node_id("BillingDocument", billing)
            _add_node(
                G,
                node_id,
                "BillingDocument",
                billing,
                {
                    "amount": _to_float(row["totalNetAmount"]),
                    "isCancelled": _to_bool(row["billingDocumentIsCancelled"]),
                },
            )

        # Payment nodes (distinct accounting document).
        for row in cur.execute(
            """
            SELECT accountingDocument, amountInTransactionCurrency, customer
            FROM payments_accounts_receivable
            WHERE accountingDocument IS NOT NULL AND accountingDocument <> ''
            GROUP BY accountingDocument
            """
        ):
            accounting_document = _as_str(row["accountingDocument"]).strip()
            if not accounting_document:
                continue
            node_id = _node_id("Payment", accounting_document)
            _add_node(
                G,
                node_id,
                "Payment",
                accounting_document,
                {
                    "amount": _to_float(row["amountInTransactionCurrency"]),
                    "customer": _as_str(row["customer"]),
                },
            )

        # Plant nodes.
        for row in cur.execute(
            """
            SELECT plant, plantName
            FROM plants
            """
        ):
            plant = _as_str(row["plant"]).strip()
            if not plant:
                continue
            node_id = _node_id("Plant", plant)
            _add_node(
                G,
                node_id,
                "Plant",
                row["plantName"],
                {},
            )

        # Customer -> SalesOrder (PLACED).
        for row in cur.execute(
            """
            SELECT soldToParty, salesOrder
            FROM sales_order_headers
            WHERE salesOrder IS NOT NULL AND salesOrder <> ''
            """
        ):
            source = _node_id("Customer", row["soldToParty"])
            target = _node_id("SalesOrder", row["salesOrder"])
            _add_edge(G, edge_seen, source, target, "PLACED")

        # SalesOrder -> Delivery (FULFILLED_BY).
        for row in cur.execute(
            """
            SELECT referenceSdDocument, deliveryDocument
            FROM outbound_delivery_items
            WHERE referenceSdDocument IS NOT NULL
              AND referenceSdDocument <> ''
              AND deliveryDocument IS NOT NULL
              AND deliveryDocument <> ''
            """
        ):
            source = _node_id("SalesOrder", row["referenceSdDocument"])
            target = _node_id("Delivery", row["deliveryDocument"])
            _add_edge(G, edge_seen, source, target, "FULFILLED_BY")

        # Delivery -> BillingDocument (BILLED_AS).
        for row in cur.execute(
            """
            SELECT referenceSdDocument, billingDocument
            FROM billing_document_items
            WHERE referenceSdDocument IS NOT NULL
              AND referenceSdDocument <> ''
              AND billingDocument IS NOT NULL
              AND billingDocument <> ''
            """
        ):
            source = _node_id("Delivery", row["referenceSdDocument"])
            target = _node_id("BillingDocument", row["billingDocument"])
            _add_edge(G, edge_seen, source, target, "BILLED_AS")

        # BillingDocument -> Payment (PAID_BY).
        for row in cur.execute(
            """
            SELECT h.billingDocument, h.accountingDocument
            FROM billing_document_headers h
            WHERE h.billingDocument IS NOT NULL
              AND h.billingDocument <> ''
              AND h.accountingDocument IS NOT NULL
              AND h.accountingDocument <> ''
            """
        ):
            source = _node_id("BillingDocument", row["billingDocument"])
            target = _node_id("Payment", row["accountingDocument"])
            _add_edge(G, edge_seen, source, target, "PAID_BY")

        # SalesOrder -> Product (CONTAINS).
        for row in cur.execute(
            """
            SELECT salesOrder, material
            FROM sales_order_items
            WHERE salesOrder IS NOT NULL
              AND salesOrder <> ''
              AND material IS NOT NULL
              AND material <> ''
            """
        ):
            source = _node_id("SalesOrder", row["salesOrder"])
            target = _node_id("Product", row["material"])
            _add_edge(G, edge_seen, source, target, "CONTAINS")

        # Product -> Plant (STORED_IN).
        for row in cur.execute(
            """
            SELECT product, plant
            FROM product_plants
            WHERE product IS NOT NULL
              AND product <> ''
              AND plant IS NOT NULL
              AND plant <> ''
            """
        ):
            source = _node_id("Product", row["product"])
            target = _node_id("Plant", row["plant"])
            _add_edge(G, edge_seen, source, target, "STORED_IN")

    print(f"Total nodes: {G.number_of_nodes()}")
    print(f"Total edges: {G.number_of_edges()}")
    return G


def get_graph_sample(G: nx.DiGraph, max_per_type: int = 15) -> Dict[str, List[Dict[str, Any]]]:
    selected_nodes: Set[str] = set()
    per_type_count: Dict[str, int] = defaultdict(int)

    for node_id, data in G.nodes(data=True):
        node_type = _as_str(data.get("type"))
        if per_type_count[node_type] >= max_per_type:
            continue
        per_type_count[node_type] += 1
        selected_nodes.add(node_id)

    return _serialize_subgraph(G, selected_nodes)


def get_neighbors(G: nx.DiGraph, node_id: str) -> Dict[str, List[Dict[str, Any]]]:
    if node_id not in G:
        return {"nodes": [], "edges": []}

    node_ids: Set[str] = {node_id}
    node_ids.update(G.predecessors(node_id))
    node_ids.update(G.successors(node_id))
    return _serialize_subgraph(G, node_ids)


def find_order_chain(G: nx.DiGraph, sales_order_id: str) -> Dict[str, List[Dict[str, Any]]]:
    sales_node = sales_order_id
    if sales_node not in G:
        sales_node = _node_id("SalesOrder", sales_order_id)
    if sales_node not in G:
        return {"nodes": [], "edges": []}

    allowed_labels = {"PLACED", "FULFILLED_BY", "BILLED_AS", "PAID_BY"}
    visited: Set[str] = {sales_node}
    q_nodes: deque = deque([sales_node])

    while q_nodes:
        current = q_nodes.popleft()
        for neighbor in G.predecessors(current):
            edge_data = G.get_edge_data(neighbor, current, default={})
            if edge_data.get("label") in allowed_labels and neighbor not in visited:
                visited.add(neighbor)
                q_nodes.append(neighbor)
        for neighbor in G.successors(current):
            edge_data = G.get_edge_data(current, neighbor, default={})
            if edge_data.get("label") in allowed_labels and neighbor not in visited:
                visited.add(neighbor)
                q_nodes.append(neighbor)

    return _serialize_subgraph(G, visited)


def get_stats(G: nx.DiGraph) -> Dict[str, Dict[str, int]]:
    node_type_counts: Dict[str, int] = defaultdict(int)
    edge_type_counts: Dict[str, int] = defaultdict(int)

    for _, data in G.nodes(data=True):
        node_type_counts[_as_str(data.get("type"))] += 1

    for _, _, data in G.edges(data=True):
        edge_type_counts[_as_str(data.get("label"))] += 1

    return {
        "totalNodes": G.number_of_nodes(),
        "totalEdges": G.number_of_edges(),
        "nodesByType": dict(node_type_counts),
        "edgesByType": dict(edge_type_counts),
    }


if __name__ == "__main__":
    graph = build_graph()
    print(get_stats(graph))
