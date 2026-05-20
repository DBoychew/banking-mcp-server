# Domain-Query Catalog Snippet for Production Prompt

Paste the block below into the production agent's system prompt **above** the `Operating procedure` section. Goal: pre-load the agent with the available `execute_domain_query` names so it stops missing the lazy `banking://domain-queries/scards` lookup (flash models skip un-anchored resource reads ~30-40% of the time).

Connection: `scards` (default). All queries are invoked via the `execute_code` sandbox as `tools.execute_domain_query(<name>, **params)`. Date parameters are inclusive `from_date` / exclusive `to_date` in `YYYY-MM-DD`. DEV data ranges: `CARD_TRANSACTIONS` ends 2023-11-10; closed cards exist only from 2023 onward - prefer explicit dates over relative phrases like "last week".

---

```
Available domain queries (use `tools.execute_domain_query(<name>, **params)` from execute_code):

UC-01 Card transactions (CARD_TRANSACTIONS, MERCHANTS):
  - transaction_count_by_period(from_date, to_date)
      Row count of transactions in window.
  - transaction_value_sum_by_period(from_date, to_date)
      Total BGN value + count for window. Money column: AMOUNT_LOCAL_CCY (NOT CARD_AMOUNT).
  - top_n_transactions_in_period(from_date, to_date, n=10)
      Top N largest transactions by AMOUNT_LOCAL_CCY.
  - top_merchants_by_volume(from_date, to_date, n=10)
      Top N merchants by total BGN value (joins MERCHANTS via MERCHANT_IDN).
  - volume_by_scheme_period(from_date, to_date)
      Mastercard / Visa / AmEx breakdown via CARD_COMMUNITY (EUR/VIS/AME).

UC-02 Authorization performance (STG_TRANSACTIONS_BORICA_EO, CARD_AUTHORIZATIONS):
  - approval_rate_by_channel_daily(from_date, to_date, n=10)
      Daily approval % per channel (ATM / Contactless / POS). Counts only TRANSACTION_CODE in ('A','N').
  - top_decline_reasons(from_date, to_date, n=10)
      Top N AUTH_RESPONCE_CODE values on declined auths (TRANSACTION_CODE='N'). ISO 8583 codes.
  - auth_latency_p95_daily(from_date, to_date, n=10)
      Daily bank-side authorization processing latency from CARD_AUTHORIZATIONS: P50/P95/P99/MAX seconds between TIME_STAMP (received) and SEND_DATE (sent to BORICA). NOT full POS-network round-trip - only the internal pipeline. DEV window: 2023-01-03 .. 2023-11-10.
  - approval_rate_period_compare(current_from, current_to, previous_from, previous_to)
      Compare approval rate by channel (ATM / Contactless / POS) between two date windows. Returns per-channel CURR_RATE, PREV_RATE, and RATE_DELTA_PP (pp change). Use for "сравни с предходната седмица / миналия месец".

UC-03 Interchange (MC_IRF_ACQUIRING_TT140):
  - mc_interchange_summary_by_period(from_date, to_date)
      Mastercard acquiring interchange summary by CCY + D_C_INDICATOR (CR/DR).

UC-04 Settlement & files (BORICA_SETTLEMENT, VISA_SETTLEMENT, REPORT_FILES_PROCESSED_V):
  - borica_daily_settlement_net_position(from_date, to_date, n=10)
      Daily BORICA debit/credit/net BGN + error-row count.
  - visa_settlement_summary_by_period(from_date, to_date)
      Visa settlement totals by REPORT_TYPE + AMT_SETTLEMENT_INDICATOR.
  - file_processing_status_period(from_date, to_date)
      Incoming/outgoing file counts by status (BG text).

UC-05 Portfolio (CARDS, CARD_PRODUCTS, CARD_REASON_CLOSE, OFFICES):
  - active_cards_by_product(n=10)
      Active cards (STATUS='2') by product name. Top N.
  - active_cards_by_office(n=10)
      Active cards by issuing office (CARDS.OFFICE_OWNER_ID -> OFFICES). Top N.
  - new_cards_in_period(from_date, to_date, n=10)
      Cards opened in window, by product (CARDS.OPEN_DATE).
  - closed_cards_in_period(from_date, to_date, n=10)
      Cards closed (STATUS='3') in window, by close reason.
  - portfolio_churn_rate_period(from_date, to_date, n=10)
      Per-product churn % = closed-in-window / active-at-start-of-window. Use a window inside 2023-2024 in DEV (no closures before 2023).

Selection rules:
  - Always prefer a domain query over hand-written SQL when the user's intent matches.
  - If no domain query fits, fall back to `tools.execute_sql_query` and consult `banking://schema/scards` + `banking://table-descriptions/scards`.
  - For "top / largest" use `top_n_transactions_in_period`, not raw ORDER BY.
  - For approval-rate or decline questions go through the UC-02 queries - they already exclude 'D' (settlement) and 'B' (journal) rows.
```

---

## Why this matters

- Production agent budget: 5 tool calls per turn. Each `tools.execute_domain_query` collapses ~4 schema-discovery calls into one. Inline-catalog lookup beats the resource-read path.
- Flash models often skip an un-anchored `banking://domain-queries/scards` read. Anchoring the catalog inline removes that failure mode.
- Names + signatures (not full SQL) are enough for matching - the executor expands them server-side.

## When to update this snippet

Re-generate this file whenever a domain query is added, renamed, or removed in `data/db_config.json`. Keep the section ordering by UC for readability.
