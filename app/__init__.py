from flask import Flask
from config import Config
import os

def create_app():
    app = Flask(__name__,
        template_folder="templates",
        static_folder="static"
    )

    app.config.from_object(Config)

    from app.routes import main
    app.register_blueprint(main)

    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and app.debug:
        return app

    from apscheduler.schedulers.background import BackgroundScheduler
    from app.routes import refresh_all_drift_caches

    scheduler = BackgroundScheduler()
    scheduler.add_job(refresh_all_drift_caches, 'interval', minutes=15)
    scheduler.start()

    refresh_all_drift_caches()

    return app