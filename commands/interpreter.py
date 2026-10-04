import re
from commands.registry import get_command
COMMAND_PATTERNS = [
    (
        "MARGIN_SUMMARY",
        [
            r"\bprofit\b.*\bloss\b",
            r"\bprofit\b.*\bmargin\b",
            r"\bprofit\s+and\s+loss\b",
            r"\bmargin\b.*\btotal\b",
        ],
    ),
    (
        "FINANCIAL_SUMMARY",
        [
            r"\bfinancial\b.*\bsummary\b",
            r"\bfinancials\b",
            r"\bfinance\b",
        ],
    ),
    (
        "SALES_SUMMARY",
        [
            r"\btoday'?s\s+sales\b",
            r"\bsales\s+today\b",
            r"\bshow\s+sales\b",
            r"\bsales\s+summary\b",
        ],
    ),
    (
        "REVENUE_SUMMARY",
        [
            r"\btotal\s+revenue\b",
            r"\brevenue\s+summary\b",
            r"\bshow\s+revenue\b",
            r"\brevenue\b",
        ],
    ),
    (
        "ORDER_LIST",
        [
            r"\brecent\s+orders\b",
            r"\bshow\s+orders\b",
            r"\border\s+list\b",
            r"\borders\b",
        ],
    ),
    (
        "PRODUCT_LIST",
        [
            r"\bpaid\s+products\b",
            r"\bunpublished\s+products\b",
            r"\bshow\s+products\b",
            r"\bproduct\s+list\b",
            r"\bproducts\b",
        ],
    ),
]
def normalize_command(command):
    command = command.strip().lower()
    command = re.sub(r"\s+", " ", command)
    return command
def extract_parameters(command):
    params = {}
    if re.search(r"\btoday('?s)?\b", command):
        params["period"] = "today"
    if re.search(r"\bpaid\b", command):
        params["status"] = "paid"
    if re.search(r"\bunpublished\b", command):
        params["status"] = "unpublished"
    if re.search(r"\brecent\b", command):
        params["scope"] = "recent"
    return params
def interpret(command):
    normalized = normalize_command(command)
    if not normalized:
        return {
            "success": False,
            "error": "Command is required",
        }
    for command_type, patterns in COMMAND_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, normalized):
                registered = get_command(command_type)
                params = extract_parameters(normalized)
                return {
                    "success": True,
                    "command": command,
                    "normalized_command": normalized,
                    "command_type": command_type,
                    "parameters": params,
                    "handler_available": registered is not None,
                }
    return {
        "success": False,
        "command": command,
        "normalized_command": normalized,
        "error": "Command type not recognized",
    }
