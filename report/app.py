# Copyright 2019-2020 by J. Christopher Wagner (jwag). All rights reserved.

"""
A Flask app that receives slack app calls and reacts.

It also provides a flask-admin web interface for looking at submitted reports.
It uses a proxy to the docent website for authn.

To run locally - start dynamoDB:

cd dynamodb_local_latest
java -Djava.library.path=./DynamoDBLocal_lib -jar DynamoDBLocal.jar -sharedDb

Run ngrok:
ngrok http 5002

Start this app (report)
If ngrok was killed/machine restarted - go to slack app console and replace
the host name (event subscriptions and interactive components)

# Updating AWS
cd reports
zappa update [dev|live]

Note that secrets are stored in AWS - have to change them there.

"""

import logging
import threading
import os

from flask import Flask, redirect, url_for
from flask_admin import Admin
from flask_moment import Moment

from api import api
import asyncev
from constants import LOG_FORMAT, DATE_FMT
import dynamo
from proxy_auth import PLAdminIndexView, init_login
import s3
from slack_api import get_bot_info
from webview import ReportModelView

REQUIRED_CONFIG = ["SIGNING_SECRET", "BOT_TOKEN", "SECRET_KEY"]


def get_action_values(info):
    return [a.get("value", None) for a in info["actions"]]


def create_app():
    app = Flask(__name__)

    logging.basicConfig(format=LOG_FORMAT, datefmt=DATE_FMT, level=logging.INFO)
    logger = logging.getLogger(__name__)
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
    if app.config["USE_DYNAMO"]:
        app.ddb = dynamo.DDB(app.config)
        app.report = dynamo.Report(app.config, app.ddb)
        app.ddb_cache = dynamo.DDBCache(app.config, app.ddb)
    else:
        from dbmodel import db
        from sql import Report

        db.init_app(app)
        app.report = Report(db, app)
    app.register_blueprint(api)

    logger.info("create_app: initializing S3")
    app.s3 = s3.S3Storage(app.config)
    app.s3.init()

    # Flask-Login
    init_login(app)
    app.moment = Moment(app)

    # Flask-admin
    app.config["FLASK_ADMIN_SWATCH"] = "cerulean"
    admin = Admin(
        name="PLSNR-Docent",
        template_mode="bootstrap3",
        index_view=PLAdminIndexView(),
        base_template="pl_master.html",
    )
    admin.init_app(app)
    admin.add_view(ReportModelView(app.report, name="Reports", endpoint="reports"))

    @app.before_first_request
    def start_async():
        threading.Thread(target=lambda: asyncev.run_loop(asyncev.event_loop)).start()

    @app.before_first_request
    def init_tables():
        if app.config["USE_DYNAMO"]:
            # app.ddb.destroy_all()
            app.ddb.create_all()

    @app.before_first_request
    def whoami():
        get_bot_info()

    @app.route("/")
    def index():
        return redirect(url_for("admin.index"))

    return app


if __name__ == "__main__":
    # reloader doesn't work with additional threads.
    app = create_app()
    asyncev.wapp = app
    app.run(host="localhost", port=5002, debug=True, use_reloader=False)
    asyncev.event_loop.call_soon_threadsafe(asyncev.event_loop.stop)
