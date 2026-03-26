import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple


TABLES = [
    "sales_order_headers",
    "sales_order_items",
    "sales_order_schedule_lines",
    "outbound_delivery_headers",
    "outbound_delivery_items",
    "billing_document_headers",
    "billing_document_items",
    "billing_document_cancellations",
    "payments_accounts_receivable",
    "journal_entry_items_accounts_receivable",
    "business_partners",
    "business_partner_addresses",
    "customer_company_assignments",
    "customer_sales_area_assignments",
    "products",
    "product_descriptions",
    "product_plants",
    "product_storage_locations",
    "plants",
]

INDEX_SPECS = {
    "sales_order_headers": ["salesOrder", "soldToParty"],
    "sales_order_items": ["salesOrder", "material"],
    "outbound_delivery_items": ["referenceSdDocument", "deliveryDocument"],
    "billing_document_items": ["referenceSdDocument", "billingDocument"],
    "billing_document_headers": ["soldToParty", "accountingDocument"],
    "journal_entry_items_accounts_receivable": ["referenceDocument"],
    "payments_accounts_receivable": ["salesDocument", "customer"],
}


def q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def normalize_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, bool):
        return int(value)
    return value


def iter_jsonl_rows(files: Iterable[Path]) -> Iterable[Dict[str, Any]]:
    for file_path in files:
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def collect_rows_and_columns(table_dir: Path, table: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    part_files = sorted(table_dir.glob("part*.jsonl"))
    rows: List[Dict[str, Any]] = []
    columns: Set[str] = set(INDEX_SPECS.get(table, []))

    for row in iter_jsonl_rows(part_files):
        rows.append(row)
        columns.update(row.keys())

    if not columns:
        # SQLite tables need at least one column.
        columns.add("_ingest_placeholder")

    return rows, sorted(columns)


def recreate_table(conn: sqlite3.Connection, table: str, columns: List[str]) -> None:
    conn.execute(f"DROP TABLE IF EXISTS {q(table)}")
    column_sql = ", ".join(f"{q(col)} TEXT" for col in columns)
    conn.execute(f"CREATE TABLE {q(table)} ({column_sql})")


def insert_rows(conn: sqlite3.Connection, table: str, columns: List[str], rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return

    col_sql = ", ".join(q(c) for c in columns)
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {q(table)} ({col_sql}) VALUES ({placeholders})"

    payload = []
    for row in rows:
        payload.append([normalize_value(row.get(col)) for col in columns])

    conn.executemany(sql, payload)


def create_indexes(conn: sqlite3.Connection) -> None:
    for table, cols in INDEX_SPECS.items():
        for col in cols:
            index_name = f"idx_{table}_{col}"
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {q(index_name)} ON {q(table)} ({q(col)})"
            )


def print_row_counts(conn: sqlite3.Connection) -> None:
    for table in TABLES:
        count = conn.execute(f"SELECT COUNT(*) FROM {q(table)}").fetchone()[0]
        print(f"{table}: {count}")


def main() -> None:
    backend_dir = Path(__file__).resolve().parent
    data_root = Path(r"D:\DOCUMENTSS\graph-o2c\data\sap-o2c-data\sap-o2c-data")
    db_path = backend_dir / "data.db"

    with sqlite3.connect(db_path) as conn:
        for table in TABLES:
            table_dir = data_root / table
            rows, columns = collect_rows_and_columns(table_dir, table)
            recreate_table(conn, table, columns)
            insert_rows(conn, table, columns, rows)

        create_indexes(conn)
        conn.commit()
        print_row_counts(conn)


if __name__ == "__main__":
    main()
