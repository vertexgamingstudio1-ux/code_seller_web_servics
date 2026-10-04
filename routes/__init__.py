from routes.admin import admin_bp
from routes.customer import customer_bp
from routes.products import products_bp
from routes.orders import orders_bp
from routes.finance import finance_bp
from routes.versions import versions_bp
from routes.downloads import downloads_bp
def register_routes(app):
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(customer_bp, url_prefix="/api/customer")
    app.register_blueprint(products_bp, url_prefix="/api/products")
    app.register_blueprint(orders_bp, url_prefix="/api/orders")
    app.register_blueprint(finance_bp, url_prefix="/api/finance")
    app.register_blueprint(versions_bp, url_prefix="/api/versions")
    app.register_blueprint(downloads_bp, url_prefix="/api/downloads")`n    app.register_blueprint(files_bp, url_prefix="/api/files")

from routes.files import files_bp


