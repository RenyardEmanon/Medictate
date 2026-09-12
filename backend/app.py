import os

from flask import Flask, jsonify

from config import Config
from extensions import db, login_manager, mail, migrate
from models import User
from auth import auth_bp
from scans import scans_bp
from reports import reports_bp


def create_app():
    app = Flask(
        __name__,
        static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend"),
        static_url_path="",
    )

    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        return jsonify({"error": "Please log in to continue"}), 401

    app.register_blueprint(auth_bp)
    app.register_blueprint(scans_bp)
    app.register_blueprint(reports_bp)

    @app.route("/")
    def index():
        return app.send_static_file("home.html")

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["REPORTS_FOLDER"], exist_ok=True)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=8000)
