"""Transaction classification MCP tools.

Exposes:
  classify_description(text, direction, top_k) -> JSON with top-K matches
"""

import json

from banking_mcp.classification import classify


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
            "This is the safe signal to fall back to a manual review or to "
            "the LLM-enum-constrained fallback in later phases."
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
            result = classify(text=text, direction=direction, top_k=k)
        except ValueError as exc:
            return json.dumps(
                {"error": str(exc), "input": text}, ensure_ascii=False, indent=2
            )
        return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
