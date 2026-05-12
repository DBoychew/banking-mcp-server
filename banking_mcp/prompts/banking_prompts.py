"""Banking analytics prompts.

Each prompt returns a fully-rendered string that primes the LLM with the
relevant schema, dialect hint, and a focused task. The LLM is expected to
respond with SQL (executed via execute_code's tools.execute_sql_query) and a
short interpretation.
"""

from __future__ import annotations

from banking_mcp.db import get_manager


_ERROR_HANDLING_NOTE = (
    "Error handling (IMPORTANT):\n"
    "- `tools.execute_sql_query` and `tools.execute_domain_query` NEVER raise. "
    "On failure they return an empty DataFrame and store the driver message in "
    "`tools.last_error`.\n"
    "- After every query, if the DataFrame is empty OR the result looks wrong, "
    "check `tools.last_error` BEFORE reporting 'no data'. A non-None value means "
    "the query failed - typically a wrong table/column name (e.g. `account` "
    "instead of `accounts`), a dialect mismatch, or a syntax error.\n"
    "- When `tools.last_error` is set, re-read the Schema block above, correct "
    "the identifier against the real names there, and retry the query. Do not "
    "invent names that are not in the schema.\n"
)


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
            f"{_ERROR_HANDLING_NOTE}\n"
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
            f"{_ERROR_HANDLING_NOTE}\n"
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
            f"{_ERROR_HANDLING_NOTE}\n"
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
            f"{_ERROR_HANDLING_NOTE}\n"
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
            f"{_ERROR_HANDLING_NOTE}\n"
            f"Question: {question!r}\n\n"
            "Tasks:\n"
            "1. Write a SELECT query that answers this question, respecting "
            "the dialect noted above (Oracle uses TO_DATE/TO_CHAR/ROWNUM; "
            "Postgres uses DATE_TRUNC/INTERVAL; etc.).\n"
            "2. Execute it via `tools.execute_sql_query`.\n"
            "3. Show the result and a 1-sentence interpretation. Do NOT run "
            "any non-SELECT statements - they will be rejected."
        )

    @mcp.prompt(
        description=(
            "Classify a single transaction description against the IRIS "
            "PSD2Hub taxonomy (BG-only). Returns the top-K candidate "
            "categories with code, hierarchical path, score, and matched "
            "keywords. Hallucination-safe: codes come verbatim from the "
            "loaded taxonomy."
        )
    )
    def categorize_transaction(description: str, direction: str = "auto", top_k: int = 3) -> str:
        return (
            "You are a banking transaction categorization assistant.\n\n"
            "Goal: classify the description below using the IRIS PSD2Hub "
            "taxonomy. The classifier returns ONLY codes that exist in the "
            "loaded taxonomy, so you must NOT invent codes or category "
            "names yourself.\n\n"
            f"Description: {description!r}\n"
            f"Direction filter: {direction} (one of: auto | incoming | outgoing)\n"
            f"Top-K: {top_k}\n\n"
            "Tasks:\n"
            "1. Call the `classify_description` MCP tool with the values "
            "above (or run it through `execute_code` if you need to chain "
            "with other analysis).\n"
            "2. If `unclassified: true`, report this plainly - DO NOT guess "
            "a category. This is the expected behavior for merchant-name-"
            "only descriptions (e.g. 'ЛИДЛ', 'OMV') where the taxonomy "
            "does not enumerate brands.\n"
            "3. If `payroll_pattern_hit: true`, note that a payroll layout "
            "(e.g. PAYROLL_MM_YYYY) was detected and boosts the salary "
            "code 001001001000.\n"
            "4. Present the top match: code, hierarchical path, score, and "
            "the keywords that matched. If multiple matches are close "
            "(within 20% of the top score), list them too.\n"
            "5. Add a 1-sentence interpretation - what kind of transaction "
            "this is in plain Bulgarian."
        )

    @mcp.prompt(
        description=(
            "Spending breakdown by IRIS category for a customer over a "
            "date range. Fetches transactions via SQL, enriches them with "
            "`tools.classify_transactions`, then groups by category."
        )
    )
    def spending_breakdown_by_category(
        customer_id: str,
        from_date: str,
        to_date: str,
        connection: str = "",
    ) -> str:
        ctx_block = _connection_context(connection)
        return (
            "You are a banking data analyst preparing a per-category "
            "spending breakdown for one customer.\n\n"
            f"{ctx_block}\n\n"
            f"{_ERROR_HANDLING_NOTE}\n"
            f"Customer: {customer_id}\n"
            f"Date range: {from_date} -> {to_date}\n\n"
            "Tasks (run inside `execute_code`):\n"
            "1. Inspect the Schema block above and locate the transactions "
            "table. Identify the columns for customer id, transaction date, "
            "amount, and free-text description (likely names: TRANSACTIONS, "
            "TRANS, MOVEMENTS - read the schema, do not assume).\n"
            "2. Build a SELECT that fetches every row for this customer in "
            "the date range. Use dialect-appropriate date syntax (Oracle: "
            "TO_DATE('YYYY-MM-DD','YYYY-MM-DD')). After running the query, "
            "check `tools.last_error` BEFORE interpreting an empty result.\n"
            "3. Call `tools.classify_transactions(df, description_column='<your column>')`. "
            "The returned DataFrame adds: category_code, category_path, "
            "category_score, category_matched_keywords, category_unclassified.\n"
            "4. Report:\n"
            "   a. Total spent and total received in the period.\n"
            "   b. Breakdown by `category_path` with sum(amount) and "
            "share %, sorted by absolute amount desc.\n"
            "   c. The unclassified rate "
            "(`enriched['category_unclassified'].mean()`). If > 30%, flag "
            "this as a data-quality concern - the taxonomy may not cover "
            "the merchant names in this customer's transactions.\n"
            "5. Add 2-3 sentences of interpretation: dominant categories, "
            "any anomalies, suggestions for follow-up analysis.\n"
            "Save the breakdown to `result` as a list of dicts."
        )

    @mcp.prompt(
        description=(
            "Detect regular income for a customer: payroll-pattern matches "
            "and recurring same-payer credits classified to code "
            "001001001000 (Възнаграждение)."
        )
    )
    def income_pattern_analysis(
        customer_id: str,
        months: int = 6,
        connection: str = "",
    ) -> str:
        ctx_block = _connection_context(connection)
        return (
            "You are a banking risk / KYC analyst looking for recurring "
            "income on this customer's account.\n\n"
            f"{ctx_block}\n\n"
            f"{_ERROR_HANDLING_NOTE}\n"
            f"Customer: {customer_id}\n"
            f"Lookback window: last {months} months\n\n"
            "Background on the taxonomy (do NOT invent codes):\n"
            "- Code `001001001000` = Възнаграждение (salary / payroll).\n"
            "- Payroll patterns from the taxonomy (PAYROLL_MM_YYYY etc.) "
            "  are detected by `tools.classify_transactions` and surfaced "
            "  via `payroll_pattern_hit` on `classify_description`.\n"
            "- Regular-income heuristic per the source workbook: same "
            "  payer (наредител) appearing in >= 2 consecutive months.\n\n"
            "Tasks (run inside `execute_code`):\n"
            "1. Fetch incoming transactions only for the customer in the "
            "lookback window. Include payer / counterparty column if the "
            "schema has it.\n"
            "2. Run `tools.classify_transactions(df, ...)` to enrich.\n"
            "3. Filter to rows with `category_code == '001001001000'` OR "
            "where a payroll pattern was matched.\n"
            "4. Group by (payer, month) and check whether the same payer "
            "appears in at least 2 consecutive months. Use pandas "
            "groupby + a month bucket.\n"
            "5. Report:\n"
            "   a. List of detected recurring-income streams (payer, "
            "      months observed, mean amount, last seen).\n"
            "   b. Whether the customer has a stable income signal.\n"
            "   c. Any payroll-pattern matches that did NOT recur - flag "
            "      as one-off bonuses worth a human review.\n"
            "Do NOT classify anyone manually - rely on the codes the tool "
            "returned. Save the streams list to `result`."
        )
