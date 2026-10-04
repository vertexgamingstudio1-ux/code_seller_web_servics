from commands.handlers import (
    handle_financial_summary,
    handle_margin_summary,
    handle_sales_summary,
    handle_product_list,
    handle_order_list,
    handle_revenue_summary,
)
COMMAND_REGISTRY = {
    "FINANCIAL_SUMMARY": {
        "description": "Show overall financial information.",
        "handler": handle_financial_summary,
    },
    "MARGIN_SUMMARY": {
        "description": "Show profit, loss, and margin information.",
        "handler": handle_margin_summary,
    },
    "SALES_SUMMARY": {
        "description": "Show sales information.",
        "handler": handle_sales_summary,
    },
    "PRODUCT_LIST": {
        "description": "List or filter marketplace products.",
        "handler": handle_product_list,
    },
    "ORDER_LIST": {
        "description": "List marketplace orders.",
        "handler": handle_order_list,
    },
    "REVENUE_SUMMARY": {
        "description": "Show total revenue information.",
        "handler": handle_revenue_summary,
    },
}
def get_command(command_type):
    return COMMAND_REGISTRY.get(command_type)
