# Banking MCP Server

This server can run in two modes:

- `stdio` for local desktop clients
- `http` for web clients

## Specifications

- `docs/specs/AI_CardPayments_Agent_UseCase.docx` — UC-CARD-AI-001 v1.0 (authoritative)
- `docs/specs/AI_CardPayments_Agent_UseCase.md` — markdown rendering for git diff/grep (regenerate via `python scripts/convert_usecase_docx.py`)

Cite UC-IDs (UC-01..UC-05) in PRs that touch areas covered by the spec.
The glossary (Section 10) is exposed at runtime as the
`banking://payment-glossary` MCP resource.

## Local HTTP run

```powershell
python main.py http
```

Default local URLs:

- Health: `http://localhost:8080/health`
- `http://localhost:8080/mcp/banking-assistant`

## Docker demo run

```powershell
docker compose up --build
```

The compose file sets:

- `MCP_TRANSPORT=http`
- `MCP_HTTP_PATH=/banking-assistant`
- `MCP_STATELESS_HTTP=true`

That makes the demo MCP endpoint:

- `http://localhost/mcp/banking-assistant`

## Client configuration

For desktop clients that support HTTP MCP, use the URL:

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

For web application, register the externally reachable HTTPS URL:

- `https://<your-host>/mcp/banking-assistant`

Use the health endpoint to confirm the deployment before connecting the client:

- `https://<your-host>/health`
