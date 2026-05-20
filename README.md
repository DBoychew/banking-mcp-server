# Banking MCP Server

MCP-only banking analytics server for card-payments analysis, transaction
classification, SQL-assisted exploration, and generated Streamlit dashboards.

The server exposes FastMCP tools, resources, and prompts. It does not expose a
business REST API; the only HTTP endpoints outside MCP are operational endpoints
such as `/health`, `/docs`, and redirects into the MCP mount.

## What Is Included

- FastMCP server named `banking-assistant`
- Streamable HTTP, stdio, and legacy SSE transports
- Read-only SQL access with multi-database support
- Oracle-first configuration for the masked `scards` schema
- RestrictedPython sandbox for Python + pandas analysis through `execute_code`
- IRIS PSD2Hub transaction taxonomy classification, Bulgarian-only
- MCP resources for schemas, dialects, taxonomy, glossary, table descriptions,
  and classification stats
- MCP prompts for database overview, SQL help, table analysis, data-quality
  checks, card-payment terminology, categorization, and income-pattern analysis
- Streamlit dashboard generation through MCP tools
- JSON-lines audit logging with basic PII redaction

## Project Layout

```text
banking_mcp/
  server.py                 FastAPI + FastMCP wiring
  config.py                 environment settings
  executor.py               RestrictedPython execution sandbox
  tools/                    MCP tool registration
  db/                       connection config, drivers, schema discovery
  resources/                MCP resources and bundled JSON datasets
  prompts/                  MCP prompt templates
  classification/           transaction classifier
  dashboard/                Streamlit dashboard state and app generator
  audit/                    async audit logging and redaction
data/
  db_config.json            configured database connections and domain queries
  table_descriptions/       human-authored table/column notes
docs/specs/                 UC-CARD-AI-001 source spec and Markdown rendering
tests/unit/                 unit test suite
```

## Requirements

- Python 3.11+
- Oracle client connectivity for the default `scards` connection
- Docker, only if you want to run the nginx + supervisord demo container

Install the full local dependency set:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`pyproject.toml` also defines the package metadata and optional `multi-db`
extras for non-primary drivers:

```powershell
pip install ".[multi-db]"
```

## Configuration

Create a local `.env` from the example and fill in deployment-specific values:

```powershell
Copy-Item .env.example .env
```

Important settings:

| Variable | Purpose | Default |
| --- | --- | --- |
| `MCP_TRANSPORT` | `stdio`, `http`, or `sse` | `stdio` |
| `MCP_HTTP_PATH` | MCP path mounted under `/mcp` | `/banking-assistant` |
| `MCP_STATELESS_HTTP` | FastMCP stateless HTTP mode | `true` |
| `SERVER_HOST` / `SERVER_PORT` | FastAPI bind address | `0.0.0.0` / `8080` |
| `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_DSN`, `ORACLE_SCHEMA` | Default Oracle connection values | empty |
| `DATA_DIR` | Directory for `db_config.json`, schema cache, dashboards | `.` |
| `AUDIT_LOG_PATH` | Audit log base path | `./logs/audit.log` |
| `AUDIT_ENABLED` | Enables query/classification/error audit logging | `true` |
| `DASHBOARD_URL` / `DASHBOARD_PORT` | User-facing Streamlit dashboard location | `http://localhost:8501` / `8501` |
| `DASHBOARD_AUTOSTART` | Start Streamlit with HTTP/SSE server modes | `true` |

Database connections live in `data/db_config.json`. The default connection is
`scards`, an Oracle connection whose DSN and schema are resolved from
environment variables:

```json
{
  "connections": {
    "scards": {
      "dsn": "${ORACLE_DSN}",
      "db_type": "oracle",
      "schema": "${ORACLE_SCHEMA}"
    }
  },
  "default_connection": "scards"
}
```

DSN strings support `${VAR}` substitution so credentials can stay in `.env`.
Supported `db_type` values are `oracle`, `sqlite`, `postgres` / `postgresql`,
`mysql` / `mariadb`, `duckdb`, and `clickhouse`. Non-Oracle drivers are loaded
lazily and require the optional dependencies.

## Running Locally

Stdio mode, for desktop MCP clients:

```powershell
python main.py stdio
```

HTTP mode, for local web clients:

```powershell
python main.py http
```

Default local URLs in HTTP mode:

- Health: `http://localhost:8080/health`
- MCP: `http://localhost:8080/mcp/banking-assistant`
- FastAPI docs: `http://localhost:8080/docs`
- Dashboard, when autostart is enabled: `http://localhost:8501`

Without an argument, `main.py` uses `MCP_TRANSPORT` from the environment.

Legacy SSE mode is still available:

```powershell
python main.py sse
```

## Docker Demo

The compose setup runs FastAPI behind nginx on port 80:

```powershell
docker compose up --build
```

Container URLs:

- Health: `http://localhost/health`
- MCP: `http://localhost/mcp/banking-assistant`
- FastAPI docs: `http://localhost/docs`

The compose file sets:

- `MCP_TRANSPORT=http`
- `MCP_HTTP_PATH=/banking-assistant`
- `MCP_STATELESS_HTTP=true`
- `DATA_DIR=/app/data`
- `AUDIT_LOG_PATH=/app/logs/audit.log`

## MCP Client Configuration

For stdio clients:

```json
{
  "mcpServers": {
    "banking-assistant-stdio": {
      "command": "python",
      "args": ["main.py", "stdio"],
      "env": {
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

For a local HTTP server started with `python main.py http`:

```json
{
  "mcpServers": {
    "banking-assistant-http": {
      "type": "http",
      "url": "http://localhost:8080/mcp/banking-assistant"
    }
  }
}
```

For the Docker demo through nginx:

```json
{
  "mcpServers": {
    "banking-assistant-http": {
      "type": "http",
      "url": "http://localhost/mcp/banking-assistant"
    }
  }
}
```

For a deployed web client, register the externally reachable HTTPS URL:

```text
https://<your-host>/mcp/banking-assistant
```

Use `/health` first to confirm the deployment and the effective MCP endpoint
path before connecting a client.

## MCP Tools

Database and analysis tools:

- `list_databases`
- `get_database_table_list`
- `get_table_info`
- `get_database_context`
- `execute_code`

Classification tools:

- `classify_description`
- `reload_classification_taxonomy`

Dashboard tools:

- `dashboard_add_widget`
- `dashboard_update_widget`
- `dashboard_remove_widget`
- `dashboard_view`

`execute_code` runs RestrictedPython and exposes `pd`, `np`, `json`, `math`,
and a `tools` object. User code must assign its final output to `result`.
The `tools` object provides:

- `tools.execute_sql_query(sql, connection=None)`
- `tools.execute_domain_query(name, connection=None, **params)`
- `tools.classify_transactions(df, description_column=..., direction_column=None)`
- `tools.get_context_for_llm(connection=None)`
- `tools.last_error`

SQL execution is read-only: only `SELECT` and `WITH` statements are accepted,
and dangerous SQL keywords are rejected after stripping comments and literals.

## MCP Resources

Useful resource URIs:

- `banking://databases`
- `banking://schema/{connection}`
- `banking://domain-queries/{connection}`
- `banking://dialects`
- `banking://table-descriptions/{connection}`
- `banking://transaction-categories`
- `banking://transaction-categories/incoming`
- `banking://transaction-categories/outgoing`
- `banking://transaction-categories/payroll-patterns`
- `banking://transaction-categories/codes`
- `banking://payment-glossary`
- `banking://classification-stats`

Read `banking://table-descriptions/{connection}` before writing SQL when table
or column names are ambiguous. The default `scards` setup includes curated
domain queries in `data/db_config.json` for UC-01 through UC-05 card-payment
analysis.

## MCP Prompts

Registered prompts:

- `database_overview`
- `analyze_table`
- `compare_periods`
- `data_quality_check`
- `sql_helper`
- `categorize_transaction`
- `spending_breakdown_by_category`
- `explain_payment_term`
- `income_pattern_analysis`

## Dashboard Flow

Dashboard widgets are persisted under `${DATA_DIR}/dashboards/<dashboard_id>/`.
For the default dashboard this creates:

```text
data/dashboards/default/state.json
data/dashboards/default/app.py
```

In HTTP or SSE mode, Streamlit autostarts when `DASHBOARD_AUTOSTART=true`.
The generated app uses the same `BankingToolsAPI` as the MCP sandbox, so widget
code can query configured databases and render Streamlit charts or tables.

## Audit Logs

Audit logging records:

- SQL query executions
- classification calls
- unexpected request errors

Records are written as JSON lines to a daily rotated file derived from
`AUDIT_LOG_PATH`, for example `logs/audit.2026-05-20.log`. Retention is
controlled by `AUDIT_LOG_RETENTION_DAYS`. Basic PII redaction is applied to
single-quoted email-like values, phone-like values, and long string literals.

## Specifications

- `docs/specs/AI_CardPayments_Agent_UseCase.docx` is the authoritative
  UC-CARD-AI-001 v1.0 source.
- `docs/specs/AI_CardPayments_Agent_UseCase.md` is the Markdown rendering for
  git diffs and grep.

Regenerate the Markdown rendering with:

```powershell
python scripts/convert_usecase_docx.py
```

Cite UC IDs (`UC-01` through `UC-05`) in PRs that touch areas covered by the
spec. The glossary from the spec is exposed at runtime as
`banking://payment-glossary`.

## Tests

Run the unit test suite:

```powershell
pytest
```

Run a focused test module:

```powershell
pytest tests/unit/test_server.py
```

The current tests cover server wiring, MCP tools/resources/prompts, database
configuration, schema fetching, Oracle and multi-DB support, the execution
sandbox, classification, dashboard generation, audit logging, and redaction.
