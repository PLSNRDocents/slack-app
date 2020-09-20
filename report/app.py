# Copyright 2019-2020 by J. Christopher Wagner (jwag). All rights reserved.

"""
A Flask app that receives slack app calls and reacts.

To run locally - start dynamoDB:

cd dynamodb_local_latest
java -Djava.library.path=./DynamoDBLocal_lib -jar DynamoDBLocal.jar -sharedDb

Run ngrok:
ngrok http 6002

Start this app (report)
If ngrok was killed/machine restarted - go to slack app console and replace
the host name (event subscriptions and interactive components)

# Updating AWS
cd report
zappa update [dev|live]

Note that secrets are stored in AWS - have to change them there.

"""

import logging
import threading
import os

from flask import Flask
from flask_moment import Moment

from api import api
import asyncev
from constants import LOG_FORMAT, DATE_FMT
from drupal_api import DrupalApi
from dynamo import DDB, DDBCache
import plweb
from report_drupal import Report as DrupalReport
from scheduled_activity import ScheduledActivity
from slack_api import get_bot_info

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

    logger.info("create_app: init db")
    app.ddb = DDB(app.config)
    # app.report = dynamo.Report(app.config, app.ddb)
    app.ddb_cache = DDBCache(app.config, app.ddb)

    site = DrupalApi(
        app.config["PLSNR_USERNAME"],
        app.config["PLSNR_PASSWORD"],
        "{}/plsnr1933api".format(app.config["PLSNR_HOST"]),
        app.config["SSL_VERIFY"],
    )

    app.report = DrupalReport(app.config, site)
    app.sa = ScheduledActivity(app.config, site)
    app.register_blueprint(api)

    app.plweb = plweb.Plweb(app.config)
    app.moment = Moment(app)

    @app.before_first_request
    def start_async():
        threading.Thread(target=lambda: asyncev.run_loop(asyncev.event_loop)).start()

    @app.before_first_request
    def init_tables():
        # app.ddb.destroy_all()
        app.ddb.create_all()

    @app.before_first_request
    def whoami():
        get_bot_info()

    return app


if __name__ == "__main__":
    # reloader doesn't work with additional threads.
    app = create_app()
    asyncev.wapp = app
    app.run(host="localhost", port=6002, debug=True, use_reloader=False)
    asyncev.event_loop.call_soon_threadsafe(asyncev.event_loop.stop)
