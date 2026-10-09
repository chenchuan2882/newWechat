from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app(overrides=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config")
    if overrides:
        app.config.update(overrides)
    db.init_app(app)
    from wxcloudrun import model, retirement_models
    from wxcloudrun.retirement import api

    app.register_blueprint(api)

    @app.cli.command("init-db")
    def init_db():
        """Create missing tables; does not drop existing counter data."""
        db.create_all()
        print("Database tables created.")

    @app.cli.command("refresh-hot")
    def refresh_hot():
        from wxcloudrun.retirement import hot_ids

        hot_ids(force=True)
        print("Hourly wish ranking refreshed.")

    @app.cli.command("dispatch-reminders")
    def dispatch_reminders():
        from wxcloudrun.retirement import schedule_reminders, dispatch_notifications

        schedule_reminders()
        print(dispatch_notifications())

    return app


app = create_app()
from wxcloudrun import views
