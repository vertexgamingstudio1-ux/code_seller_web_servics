class ProductService:
    @staticmethod
    def list_products(params=None):
        return {"status": "pending_database", "products": [], "count": 0}
    @staticmethod
    def get_product(product_id):
        return {"status": "pending_database", "product_id": product_id}
    @staticmethod
    def create_product(data):
        return {"status": "pending_database", "message": "Product creation ready.", "data": data}
    @staticmethod
    def update_product(product_id, data):
        return {"status": "pending_database", "message": "Product update ready.", "product_id": product_id, "data": data}
    @staticmethod
    def delete_product(product_id):
        return {"status": "pending_database", "message": "Product deletion ready.", "product_id": product_id}
