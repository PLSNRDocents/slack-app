# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import logging
import threading
import os

from flask import Flask

from api import api
import asyncev
from dbmodel import db
from report import Report
import s3

REQUIRED_CONFIG = ["SIGNING_SECRET", "BOT_TOKEN"]
LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s"
DATE_FMT = "%m/%d/%Y %H:%M:%S"

logging.basicConfig(format=LOG_FORMAT, datefmt=DATE_FMT, level=logging.INFO)
logger = logging.getLogger(__name__)


def get_action_values(info):
    return [a.get("value", None) for a in info["actions"]]


def create_app():
    app = Flask(__name__)

    logging.getLogger("botocore").setLevel(logging.INFO)
    logging.getLogger("boto3").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.INFO)
    logging.getLogger("s3transfer").setLevel(logging.INFO)

    mode = os.environ["PLSNRENV"]
    logger.info("create_app: mode {}".format(mode))
    app.config.from_object("settings." + mode + "Settings")

    for rc in REQUIRED_CONFIG:
        if rc not in os.environ:
            raise EnvironmentError("Missing {}".format(rc))
        app.config[rc] = os.environ.get(rc)
    # let environ overwrite settings
    for rc in app.config:
        if rc in os.environ and (os.environ[rc] != app.config[rc]):
            logger.warning("Config variable {} overwritten by environment".format(rc))
            app.config[rc] = os.environ[rc]

    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
    logger.info("create_app: init db")
    db.init_app(app)
    app.register_blueprint(api)

    app.report = Report(db, app)
    logger.info("create_app: initializing S3")
    app.s3 = s3.S3Storage(app.config)
    app.s3.init()

    @app.before_first_request
    def start_async():
        threading.Thread(target=lambda: asyncev.run_loop(asyncev.event_loop)).start()

    return app


if __name__ == "__main__":
    # reloader doesn't work with additional threads.
    app = create_app()
    asyncev.wapp = app
    app.run(host="localhost", port=5002, debug=True, use_reloader=False)
    asyncev.event_loop.call_soon_threadsafe(asyncev.event_loop.stop)
