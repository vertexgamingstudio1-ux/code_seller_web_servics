from services.admin_service import AdminService
def handle_financial_summary(params=None):
    return AdminService.financial_summary(params or {})
def handle_margin_summary(params=None):
    return AdminService.margin_summary(params or {})
def handle_sales_summary(params=None):
    return AdminService.sales_summary(params or {})
def handle_product_list(params=None):
    return AdminService.product_list(params or {})
def handle_order_list(params=None):
    return AdminService.order_list(params or {})
def handle_revenue_summary(params=None):
    return AdminService.revenue_summary(params or {})
