class OrderService:
    @staticmethod
    def list_orders(params=None):
        return {"status": "pending_database", "orders": [], "count": 0}
    @staticmethod
    def get_order(order_id):
        return {"status": "pending_database", "order_id": order_id}
    @staticmethod
    def create_order(data):
        return {"status": "pending_database", "message": "Order creation ready.", "data": data}
    @staticmethod
    def cancel_order(order_id):
        return {"status": "pending_database", "message": "Order cancellation ready.", "order_id": order_id}
