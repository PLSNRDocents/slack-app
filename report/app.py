# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import logging
import threading
import os

from flask import Flask

from api import api
import asyncev
from dbmodel import db
from report import Report

REQUIRED_CONFIG = ["SIGNING_SECRET", "BOT_TOKEN"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("report")


def get_action_values(info):
    return [a.get("value", None) for a in info["actions"]]


def create_app():
    app = Flask(__name__)

    logging.getLogger("botocore").setLevel(logging.INFO)
    logging.getLogger("boto3").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.INFO)
    logging.getLogger("s3transfer").setLevel(logging.INFO)

    mode = os.environ["PLSNRENV"]
    app.config.from_object("settings." + mode + "Settings")

    for rc in REQUIRED_CONFIG:
        if rc not in os.environ:
            raise EnvironmentError("Missing {}".format(rc))
        app.config[rc] = os.environ.get(rc)

    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    db.init_app(app)
    app.register_blueprint(api)

    app.report = Report(db, app)

    @app.before_first_request
    def start_async():
        threading.Thread(target=lambda: asyncev.run_loop(asyncev.event_loop)).start()

    return app


if __name__ == "__main__":
    # reloader doesn't work with additional threads.
    create_app().run(host="localhost", port=5002, debug=True, use_reloader=False)
    asyncev.event_loop.call_soon_threadsafe(asyncev.event_loop.stop)
