import os
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from psycopg2.extras import Json
from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.embedding_config import pgvector_literal


SOURCE_DATABASE_URL = os.getenv(
    "SOURCE_DATABASE_URL",
    "postgresql://postgres:1234@localhost:5432/chatbot_db?sslmode=disable",
)
TARGET_DATABASE_URL = os.getenv(
    "TARGET_DATABASE_URL",
    "postgresql://postgres:1234@localhost:5433/chatbot_db?sslmode=disable",
)

APPLICATION_TABLES = [
    "audit_logs",
    "channel_logs",
    "chatbot_channels",
    "chatbots",
    "chunks",
    "conversation_messages",
    "conversation_sessions",
    "documents",
    "flow_nodes",
    "flow_transitions",
    "flows",
    "knowledge_bases",
    "llm_configs",
    "platform_settings",
    "projects",
    "runtime_logs",
    "users",
    "versions",
]

COPY_ORDER = [
    "users",
    "projects",
    "chatbots",
    "versions",
    "knowledge_bases",
    "documents",
    "chunks",
    "flows",
    "flow_nodes",
    "flow_transitions",
    "llm_configs",
    "chatbot_channels",
    "conversation_sessions",
    "conversation_messages",
    "channel_logs",
    "runtime_logs",
    "platform_settings",
    "audit_logs",
]

LEGACY_VECTOR_ERROR = (
    "Embedding dimension is incompatible with the configured vector index. "
    "Reprocess this chunk."
)


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def database_label(url: str) -> str:
    safe = url.replace("postgres:1234", "postgres:****")
    return safe


def table_counts(engine, tables: list[str]) -> dict[str, int]:
    counts = {}
    with engine.connect() as conn:
        for table in tables:
            counts[table] = conn.execute(text(f"SELECT COUNT(*) FROM {quote_ident(table)}")).scalar_one()
    return counts


def revision(engine) -> str | None:
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()


def vector_extension(engine) -> str | None:
    with engine.connect() as conn:
        return conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar_one_or_none()


def target_is_empty(engine) -> bool:
    counts = table_counts(engine, APPLICATION_TABLES)
    return all(value == 0 for value in counts.values())


def dependency_order(engine, tables: list[str]) -> list[str]:
    inspector = inspect(engine)
    graph = defaultdict(set)
    indegree = {table: 0 for table in tables}
    known = set(tables)

    for table in tables:
        for fk in inspector.get_foreign_keys(table, schema="public"):
            referred = fk.get("referred_table")
            if referred in known and referred != table:
                graph[referred].add(table)

    for source, targets in graph.items():
        for target in targets:
            indegree[target] += 1

    queue = deque(sorted(table for table, value in indegree.items() if value == 0))
    order = []
    while queue:
        table = queue.popleft()
        order.append(table)
        for dependent in sorted(graph[table]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)

    if len(order) != len(tables):
        missing = sorted(set(tables) - set(order))
        raise RuntimeError(f"Could not resolve table dependency order for: {', '.join(missing)}")
    return order


def columns(engine, table: str) -> list[str]:
    inspector = inspect(engine)
    return [column["name"] for column in inspector.get_columns(table, schema="public")]


def fetch_rows(engine, table: str, source_columns: list[str]) -> list[dict[str, Any]]:
    selected = ", ".join(quote_ident(column) for column in source_columns)
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(text(f"SELECT {selected} FROM {quote_ident(table)} ORDER BY 1"))]


def normalize_chunk_row(row: dict[str, Any]) -> dict[str, Any]:
    vector = row.get("embedding")
    dimensions = row.get("embedding_dimensions")
    status = row.get("embedding_status")

    if status == "ready" and vector is not None and dimensions == 1536:
        row["embedding_vector"] = pgvector_literal(vector)
        return row

    row["embedding_vector"] = None
    if status == "ready" and vector is not None and dimensions != 1536:
        row["embedding_status"] = "failed"
        row["embedding_error"] = row.get("embedding_error") or LEGACY_VECTOR_ERROR
        row["last_error"] = row.get("last_error") or LEGACY_VECTOR_ERROR
    return row


def insert_rows(conn, table: str, rows: list[dict[str, Any]], target_columns: list[str]) -> None:
    if not rows:
        return

    column_sql = ", ".join(quote_ident(column) for column in target_columns)
    values_sql = []
    for column in target_columns:
        if table == "chunks" and column == "embedding_vector":
            values_sql.append(f"CAST(:{column} AS vector)")
        else:
            values_sql.append(f":{column}")

    statement = text(
        f"INSERT INTO {quote_ident(table)} ({column_sql}) VALUES ({', '.join(values_sql)})"
    )
    adapted_rows = []
    for row in rows:
        adapted = {}
        for key, value in row.items():
            if key == "embedding_vector":
                adapted[key] = value
            elif isinstance(value, (dict, list)):
                adapted[key] = Json(value)
            else:
                adapted[key] = value
        adapted_rows.append(adapted)
    conn.execute(statement, adapted_rows)


def reset_sequences(conn, tables: list[str]) -> None:
    for table in tables:
        pk_column = conn.execute(text("""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = CAST(:table AS regclass)
              AND i.indisprimary
            LIMIT 1
        """), {"table": table}).scalar_one_or_none()
        if not pk_column:
            continue

        sequence_name = conn.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": table, "column_name": pk_column},
        ).scalar_one_or_none()
        if not sequence_name:
            continue

        conn.execute(text(f"""
            SELECT setval(
                :sequence_name,
                COALESCE((SELECT MAX({quote_ident(pk_column)}) FROM {quote_ident(table)}), 1),
                (SELECT COUNT(*) > 0 FROM {quote_ident(table)})
            )
        """), {"sequence_name": sequence_name})


def main() -> int:
    source = create_engine(SOURCE_DATABASE_URL)
    target = create_engine(TARGET_DATABASE_URL)

    print("source=", database_label(SOURCE_DATABASE_URL))
    print("target=", database_label(TARGET_DATABASE_URL))
    print("source_revision=", revision(source))
    print("target_revision=", revision(target))
    print("target_vector_extension=", vector_extension(target))

    if vector_extension(target) is None:
        print("ERROR: target database does not have pgvector enabled", file=sys.stderr)
        return 1

    source_counts = table_counts(source, APPLICATION_TABLES)
    target_counts = table_counts(target, APPLICATION_TABLES)
    print("source_counts=", source_counts)
    print("target_counts_before=", target_counts)

    if not target_is_empty(target):
        print("ERROR: target database contains application rows; refusing to merge automatically", file=sys.stderr)
        return 1

    source_tables = set(inspect(source).get_table_names(schema="public"))
    target_tables = set(inspect(target).get_table_names(schema="public"))
    missing = sorted(set(APPLICATION_TABLES) - source_tables)
    missing_target = sorted(set(APPLICATION_TABLES) - target_tables)
    if missing or missing_target:
        print(f"ERROR: missing source tables={missing}; missing target tables={missing_target}", file=sys.stderr)
        return 1

    try:
        order = dependency_order(target, APPLICATION_TABLES)
    except RuntimeError as exc:
        print(f"dependency_order_warning={exc}")
        order = COPY_ORDER
    print("copy_order=", order)

    source_columns = {table: columns(source, table) for table in APPLICATION_TABLES}
    target_columns = {table: columns(target, table) for table in APPLICATION_TABLES}

    migrated = {}
    with target.begin() as target_conn:
        target_conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
        for table in order:
            common_columns = [column for column in source_columns[table] if column in target_columns[table]]
            if table == "chunks" and "embedding_vector" in target_columns[table]:
                common_columns.append("embedding_vector")
            rows = fetch_rows(source, table, [column for column in common_columns if column in source_columns[table]])
            if table == "chunks":
                rows = [normalize_chunk_row(row) for row in rows]
            target_cols_for_insert = common_columns
            insert_rows(target_conn, table, rows, target_cols_for_insert)
            migrated[table] = len(rows)
            print(f"migrated.{table}={len(rows)}")
        reset_sequences(target_conn, APPLICATION_TABLES)

    after_counts = table_counts(target, APPLICATION_TABLES)
    with target.connect() as conn:
        embedding_summary = conn.execute(text("""
            SELECT embedding_dimensions, embedding_status, embedding_vector IS NOT NULL AS has_vector, COUNT(*)
            FROM chunks
            GROUP BY embedding_dimensions, embedding_status, embedding_vector IS NOT NULL
            ORDER BY embedding_dimensions NULLS FIRST, embedding_status, has_vector
        """)).fetchall()
        user_check = conn.execute(text("""
            SELECT id, email, role, status, password_hash IS NOT NULL AS has_password_hash
            FROM users
            WHERE email = 'balkisdemo@gmail.com'
        """)).fetchall()

    print("target_counts_after=", after_counts)
    print("embedding_summary=", embedding_summary)
    print("balkis_user=", user_check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
