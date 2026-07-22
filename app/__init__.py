from flask import Flask
from config import Config

def create_app():
    app = Flask(__name__,
        template_folder="templates",
        static_folder="static"
    )
    
    app.config.from_object(Config)
    
    from app.routes import main
    app.register_blueprint(main)
    
    return app