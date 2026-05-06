# Banking MCP Server - Notes

Date: 2026-05-06
Scope: follow-up notes after the hardening and cleanup pass

## 1. Domain queries for `scards` are intentionally empty
`data/db_config.json` keeps `domain_queries.scards = {}` by default.

The plumbing is already in place:
- `execute_domain_query`
- compact parameter parsing
- `get_database_context`
- `banking://domain-queries/{connection}`

Add real banking analytics only when there is a concrete use case, for example:
- `cards_lifecycle_funnel(period_days)`
- `transaction_velocity_by_card_type(lookback_days)`
- `expiry_funnel(months_ahead)`

Register them via `db.add_domain_query(...)` or by editing `data/db_config.json`.
