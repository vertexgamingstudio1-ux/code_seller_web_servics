class FinanceService:
    @staticmethod
    def summary():
        return {
            "status": "pending_database",
            "revenue": 0,
            "costs": 0,
            "profit": 0,
            "loss": 0,
            "margin_percent": 0,
            "currency": "USD"
        }
    @staticmethod
    def revenue():
        return {"status": "pending_database", "total_revenue": 0, "currency": "USD"}
    @staticmethod
    def sales():
        return {"status": "pending_database", "sales_count": 0, "sales_total": 0, "currency": "USD"}
    @staticmethod
    def margins():
        return {"status": "pending_database", "revenue": 0, "costs": 0, "profit": 0, "margin_percent": 0, "currency": "USD"}
