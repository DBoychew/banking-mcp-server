"""Transaction classification MCP tools.

Exposes:
  classify_description(text, direction, top_k) -> JSON with top-K matches
  reload_classification_taxonomy()             -> drops in-process caches
"""

import json

from banking_mcp.classification import classify, reload_index


def register_classification_tools(mcp) -> None:
    @mcp.tool(
        description=(
            "Classify a free-text transaction description against the IRIS "
            "PSD2Hub taxonomy (BG-only). Returns up to top_k category "
            "candidates with their codes, hierarchical paths, scores, and the "
            "keywords that matched. Codes are taken verbatim from the loaded "
            "taxonomy - the tool cannot return an invented code.\n\n"
            "Args:\n"
            "  text: raw transaction description (Bulgarian / mixed BG+EN).\n"
            "  direction: 'auto' (default), 'incoming', or 'outgoing'.\n"
            "  top_k: how many candidates to return (default 3, max 10).\n\n"
            "If no keyword matches, 'unclassified': true and 'matches': []. "
            "Read banking://transaction-categories/codes for the full enum "
            "of valid codes if the LLM needs to do structured-output "
            "fallback for unclassified inputs."
        )
    )
    def classify_description(
        text: str,
        direction: str = "auto",
        top_k: int = 3,
    ) -> str:
        try:
            k = max(1, min(int(top_k), 10))
        except (TypeError, ValueError):
            k = 3
        try:
            result = classify(
                text=text, direction=direction, top_k=k, source="mcp_tool"
            )
        except ValueError as exc:
            return json.dumps(
                {"error": str(exc), "input": text}, ensure_ascii=False, indent=2
            )
        return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)

    @mcp.tool(
        description=(
            "Drop the in-process taxonomy + merchant-alias caches and reset "
            "classification stats. Use after editing "
            "transaction_categories.json or merchant_aliases.json so the "
            "next classify call rebuilds the index. No DB activity, returns "
            "a small JSON status."
        )
    )
    def reload_classification_taxonomy() -> str:
        reload_index()
        return json.dumps(
            {"status": "ok", "message": "Taxonomy and aliases reloaded; stats reset."},
            ensure_ascii=False,
        )
