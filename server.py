from flask import Flask
from flask_cors import CORS
from config import Config
from routes.system import bp as system_bp
from routes.auth import bp as auth_bp
from routes.customer import bp as customer_bp
from routes.admin import bp as admin_bp
from routes.products import bp as products_bp
from routes.orders import orders_bp
from routes.community import bp as community_bp
from routes.memberships import bp as memberships_bp
from routes.management import bp as management_bp
from routes.campaigns import bp as campaigns_bp
from routes.downloads import downloads_bp
app = Flask(__name__)
CORS(app, origins=[
    "https://code-seller-static.onrender.com",
    "https://code-seller-static2.onrender.com",
])
app.register_blueprint(system_bp, url_prefix="/api")
app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(customer_bp, url_prefix="/api/customer")
app.register_blueprint(admin_bp, url_prefix="/api/admin")
app.register_blueprint(products_bp, url_prefix="/api/products")
app.register_blueprint(orders_bp, url_prefix="/api/orders")
app.register_blueprint(downloads_bp, url_prefix="/api/downloads")
app.register_blueprint(community_bp, url_prefix="/api/community")
app.register_blueprint(memberships_bp, url_prefix="/api/memberships")
app.register_blueprint(management_bp, url_prefix="/api/admin")
app.register_blueprint(campaigns_bp, url_prefix="/api/campaigns")
if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT)
