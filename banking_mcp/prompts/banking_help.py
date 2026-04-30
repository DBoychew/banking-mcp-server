"""MCP prompt: banking_help — reusable system prompt for banking assistance."""


def register_banking_prompts(mcp) -> None:

    @mcp.prompt()
    def banking_help() -> str:
        """
        System prompt for the banking assistant.
        Use this to prime a conversation about account management,
        transactions, FX rates, or spending analysis.
        """
        return (
            "You are a secure banking assistant with access to real account data.\n"
            "\n"
            "Available tools:\n"
            "  • list_accounts       — see all accounts with balances and IBANs\n"
            "  • get_balance         — current balance for a specific account\n"
            "  • list_transactions   — transactions with date and pagination filters\n"
            "  • get_statement       — full monthly statement with opening/closing balances\n"
            "  • get_fx_rates        — BNB exchange rates (EUR-based)\n"
            "  • analyze_spending    — category breakdown and anomaly detection\n"
            "  • get_bank_public_info — branches, contacts, working hours, management\n"
            "\n"
            "Rules:\n"
            "  1. Always confirm which account before acting on financial data.\n"
            "  2. Never invent balances, amounts, or transaction details.\n"
            "  3. Use only the data returned by tools — do not guess or extrapolate.\n"
            "  4. If data is missing or an error occurs, say so clearly.\n"
            "  5. Keep answers concise. Prefer structured JSON when the user asks for data.\n"
        )

    @mcp.prompt()
    def spending_analysis_prompt(account_id: str = "", period: str = "this month") -> str:
        """
        Prompt template for a spending analysis conversation.
        Asks the assistant to summarise spending for a given account and period.
        """
        account_clause = f" for account {account_id}" if account_id else ""
        return (
            f"Please analyse my spending{account_clause} for {period}.\n"
            "Use the analyze_spending tool and then:\n"
            "  1. Show the top spending categories with totals.\n"
            "  2. List the top 5 merchants.\n"
            "  3. Highlight any anomalies (unusually large transactions).\n"
            "  4. Suggest one concrete way to reduce spending."
        )
