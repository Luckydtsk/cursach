import os

from flask import Flask
from config import Config

from routes.main import main_bp
from routes.auth import auth_bp, init_auth
from routes.projects import projects_bp
from routes.tasks import tasks_bp
from routes.students import students_bp
from routes.teachers import teachers_bp
from routes.reports import reports_bp
from routes.submissions import submissions_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["UPLOAD_FOLDER"] = os.path.abspath(app.config["UPLOAD_FOLDER"])
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    init_auth(app)
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(teachers_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(submissions_bp)
    
    return app


app = create_app()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
