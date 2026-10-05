import os
from flask import Flask, jsonify
from flask_cors import CORS
from config import Config
from routes import register_routes
def create_app():
    app = Flask(__name__)
    allowed_origins = [
        "https://code-seller-static.onrender.com",
        "https://code-seller-static2.onrender.com"
    ]
    CORS(
        app,
        origins=allowed_origins,
        supports_credentials=True,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"]
    )
    app.config["SERVICE_NAME"] = Config.SERVICE_NAME
    app.config["SERVICE_VERSION"] = Config.SERVICE_VERSION
    register_routes(app)
    @app.get("/")
    def home():
        return jsonify({
            "service": Config.SERVICE_NAME,
            "version": Config.SERVICE_VERSION,
            "status": "online"
        })
    @app.get("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "service": Config.SERVICE_NAME,
            "version": Config.SERVICE_VERSION
        })
    return app
app = create_app()
if __name__ == "__main__":
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG
    )
