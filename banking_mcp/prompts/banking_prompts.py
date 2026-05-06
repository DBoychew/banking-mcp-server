"""Banking analytics prompts.

Each prompt returns a fully-rendered string that primes the LLM with the
relevant schema, dialect hint, and a focused task. The LLM is expected to
respond with SQL (executed via execute_code's tools.execute_sql_query) and a
short interpretation.
"""

from __future__ import annotations

from banking_mcp.db import get_manager


def _resolve_connection(connection: str) -> str:
    """Return the chosen connection name or fall back to default."""
    db = get_manager()
    return connection or db.get_default_connection() or ""


def _connection_context(connection: str) -> str:
    """Build a short text block: connection name, db_type, dialect hint, schema."""
    db = get_manager()
    conn = _resolve_connection(connection)
    if not conn:
        return "(no connection configured)"

    try:
        ctx = db.get_context_for_llm(conn)
    except Exception as exc:
        return f"(failed to load context for {conn!r}: {exc})"

    return (
        f"Connection: {ctx['connection_name']} ({ctx['db_type']})\n"
        f"Dialect: {ctx['sql_dialect_hint']}\n\n"
        f"Schema:\n{ctx['schema_compact']}"
    )


def register_banking_prompts(mcp) -> None:
    @mcp.prompt(
        description=(
            "High-level overview of the current database: lists tables, "
            "suggests questions the user can ask. Use as a conversation starter."
        )
    )
    def database_overview(connection: str = "") -> str:
        ctx_block = _connection_context(connection)
        return (
            "You are a banking data analyst.\n\n"
            f"{ctx_block}\n\n"
            "Task: Give me a 5-bullet overview of what is in this database "
            "(main entities, relationships, time range if visible from column "
            "names) and suggest 5 concrete analytical questions I could ask. "
            "Use `tools.execute_sql_query` for any quick counts you need."
        )

    @mcp.prompt(
        description=(
            "Focused analysis brief for a single table: schema, sample-row "
            "fetch, suggested KPIs and breakdowns. Pass the table name."
        )
    )
    def analyze_table(table_name: str, connection: str = "") -> str:
        ctx_block = _connection_context(connection)
        return (
            "You are a banking data analyst.\n\n"
            f"{ctx_block}\n\n"
            f"Target table: **{table_name}**\n\n"
            "Tasks:\n"
            f"1. Run `SELECT * FROM {table_name} FETCH FIRST 5 ROWS ONLY` "
            "(or a dialect-appropriate equivalent) to see sample data.\n"
            f"2. Run a row count: `SELECT COUNT(*) FROM {table_name}`.\n"
            "3. Identify likely PII columns and avoid surfacing raw values "
            "for them.\n"
            "4. Propose 3 KPIs and 3 breakdowns (group-by dimensions) that "
            "would be analytically useful for this table.\n"
            "5. For one chosen KPI, write and execute the SQL, then "
            "interpret the result in 2-3 sentences."
        )

    @mcp.prompt(
        description=(
            "Compare a metric between two date ranges - delta, growth %, "
            "and a brief interpretation."
        )
    )
    def compare_periods(
        table_name: str,
        date_column: str,
        metric_sql: str = "COUNT(*)",
        period_a_start: str = "",
        period_a_end: str = "",
        period_b_start: str = "",
        period_b_end: str = "",
        connection: str = "",
    ) -> str:
        ctx_block = _connection_context(connection)
        return (
            "You are a banking data analyst.\n\n"
            f"{ctx_block}\n\n"
            f"Table: {table_name}  |  Date column: {date_column}\n"
            f"Metric: {metric_sql}\n\n"
            f"Period A: {period_a_start} -> {period_a_end}\n"
            f"Period B: {period_b_start} -> {period_b_end}\n\n"
            "Tasks:\n"
            "1. Run the metric for Period A and Period B (one query each, "
            "respecting the dialect's date syntax).\n"
            "2. Compute absolute delta and growth % (B vs A).\n"
            "3. Output a 2-sentence interpretation of what changed and "
            "whether the delta is material."
        )

    @mcp.prompt(
        description=(
            "Data-quality scan for a table: NULL ratio per column, duplicate "
            "rows on the obvious key, simple anomaly hints."
        )
    )
    def data_quality_check(table_name: str, connection: str = "") -> str:
        ctx_block = _connection_context(connection)
        return (
            "You are a banking data analyst running a data-quality scan.\n\n"
            f"{ctx_block}\n\n"
            f"Target table: **{table_name}**\n\n"
            "Tasks:\n"
            "1. Inspect the schema for the table; pick the primary-key "
            "column (or the most likely candidate).\n"
            "2. Run a query that returns: total rows, NULL count per "
            "column (use COUNT(*) - COUNT(col) per column or a CASE-based "
            "aggregate), duplicate count on the PK candidate.\n"
            "3. Flag any column where NULL ratio > 5%, and any duplicates "
            "on the PK candidate.\n"
            "4. Summarize findings in <= 5 bullets and suggest one "
            "follow-up query to investigate the worst issue."
        )

    @mcp.prompt(
        description=(
            "Translate a natural-language question into an executable SQL "
            "query for the current dialect, with a short explanation."
        )
    )
    def sql_helper(question: str, connection: str = "") -> str:
        ctx_block = _connection_context(connection)
        return (
            "You are a banking SQL expert.\n\n"
            f"{ctx_block}\n\n"
            f"Question: {question!r}\n\n"
            "Tasks:\n"
            "1. Write a SELECT query that answers this question, respecting "
            "the dialect noted above (Oracle uses TO_DATE/TO_CHAR/ROWNUM; "
            "Postgres uses DATE_TRUNC/INTERVAL; etc.).\n"
            "2. Execute it via `tools.execute_sql_query`.\n"
            "3. Show the result and a 1-sentence interpretation. Do NOT run "
            "any non-SELECT statements - they will be rejected."
        )
