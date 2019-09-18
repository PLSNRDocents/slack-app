# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import asyncio
import json
import logging
import threading
import os

from flask import Flask, Blueprint, current_app, request
import requests
import slack

from dbmodel import db
from report import Report
import forms
import image
import slack_api

REQUIRED_CONFIG = ["SIGNING_SECRET", "BOT_TOKEN"]

event_loop = asyncio.new_event_loop()


def run_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("report")


def send_update(response_url, text):
    payload = {"text": text, "response_type": "ephemeral"}
    rv = requests.post(response_url, json=payload)
    rv.raise_for_status()


def get_action_values(info):
    return [a.get("value", None) for a in info["actions"]]


def handle_file(event):
    finfo = slack_api.get_file_info(event["file_id"])["file"]
    logger.info(
        "File info image link {} channels {}".format(
            finfo["url_private"], finfo["channels"]
        )
    )

    # Look for existing trail report from user and channel - else - ignore
    matched = []
    reports = current_app.report.fetch_all()

    for r in reports:
        if r.reporter_slack_id == event["user_id"] and r.channel == event["channel_id"]:
            matched.append(r)
    if len(matched) != 1:
        # Lets make sure we don't spam folks with info..
        logger.warning(
            "No report matches for file user {} channel {}".format(
                event["user_id"], event["channel_id"]
            )
        )
        # TODO - but we need to ive feedback - probably need to just check channel?
        return "", 200
    else:
        post_message(
            event["channel_id"],
            event["user_id"],
            "Retrieving file and grabbing GPS info.. thanks.",
        )
        # fetch image, find GPS coordinates - note that IOS actually strips this -
        # so likely we won't find any.
        photo = image.fetch_image(finfo["url_private"])
        exif_data = image.get_exif_data(photo)
        lat, lon = image.get_lat_lon(exif_data)
        matched[0]["gps"] = {"lat": lat, "lon": lon}


def open_report_dialogue(trigger):
    payload = {
        "callback_id": "trail",
        "title": "Trail Report",
        "submit_label": "Submit",
        "notify_on_cancel": True,
        "state": "What is this?",
        "elements": [
            {
                "label": "Location",
                "type": "select",
                "name": "location",
                "options": [
                    {"label": "Granite Point", "value": "Granite Point"},
                    {"label": "Whaler's Cove", "value": "Whaler's Cove"},
                    {"label": "North Shore", "value": "North Shore"},
                    {"label": "Cypress Grove", "value": "Cypress Grove"},
                    {"label": "Sea Lion Pt", "value": "Sea Lion Pt"},
                    {"label": "South Shore", "value": "South Shore"},
                    {"label": "Bird Island", "value": "Bird Island"},
                    {"label": "South Plateau", "value": "South Plateau"},
                    {"label": "Piney Woods", "value": "Piney Woods"},
                ],
            },
            {
                "label": "Issue",
                "type": "select",
                "name": "issue",
                "options": [
                    {"label": "Poison Oak", "value": "Poison Oak"},
                    {"label": "Sign Missing/Broke", "value": "Sign"},
                    {"label": "Tree/obstruction", "value": "Tree/obstruction"},
                    {"label": "Other", "value": "Other"},
                ],
            },
            {
                "label": "GPS Location",
                "type": "text",
                "name": "gps",
                "hint": "Use Compass app (ios) to grab current coordinates",
                "optional": True,
            },
            {
                "label": "Details",
                "type": "textarea",
                "name": "details",
                "hint": "Describe details.",
                "optional": True,
            },
        ],
    }

    slack_api.post("dialog.open", dict(trigger_id=trigger, dialog=payload))


def post_message(channel, user, payload):
    slack_api.post(
        "chat.postEphemeral",
        dict(channel=channel, user=user, text=payload, as_user=True),
    )


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
        threading.Thread(target=lambda: run_loop(event_loop)).start()

    return app


api = Blueprint("api", __name__, url_prefix="/")


@api.route("/report", methods=["GET", "POST"])
def top():
    # This handles the /report command
    if not slack.WebClient.validate_slack_signature(
        signing_secret=current_app.config["SIGNING_SECRET"],
        data=request.data,
        timestamp=request.headers["X-Slack-Request-Timestamp"],
        signature=request.headers["X-Slack-Signature"],
    ):
        pass
        # abort(403)

    open_report_dialogue(request.form["trigger_id"])
    return "", 200


@api.route("/new-report", methods=["GET", "POST"])
def submit():

    rjson = json.loads(request.form["payload"])
    if rjson["type"] == "dialog_submission":
        event_loop.call_soon_threadsafe(
            current_app.report.create,
            rjson["user"],
            rjson["channel"],
            rjson["submission"],
        )
        send_update(
            rjson["response_url"],
            "Thanks for your trail report. Please consider sharing some pictures.",
        )
        return "", 200

    logger.error("Unhandled type {}".format(rjson["type"]))
    return "", 200


@api.route("/events", methods=["GET", "POST"])
def events():
    payload = request.json

    if payload["type"] == "url_verification":
        return dict(challenge=payload["challenge"])
    elif payload["type"] == "event_callback":
        # send back current reports
        event = payload["event"]

        if event["type"] == "app_mention":
            logger.info(
                "App_mention from {} channel {}".format(event["user"], event["channel"])
            )

            tl = "Current Trail Reports"

            reports = current_app.report.fetch_all()
            if reports:
                for r in reports:
                    gps = None
                    if r.gps:
                        gps = "GPS {}".format(r["gps"])
                    tl += "\n[TR-{}] On {} {} reported {} at {} {}".format(
                        r.id,
                        r.create_datetime,
                        r.reporter_slack_handle,
                        r.issue,
                        r.location,
                        gps,
                    )
            post_message(event["channel"], event["user"], tl)
        elif event["type"] == "file_created" or event["type"] == "file_shared":
            logger.info(
                "Event {} from {} channel {}".format(
                    event["type"], event["user_id"], event["channel_id"]
                )
            )
            event_loop.call_soon_threadsafe(lambda: handle_file(event))
        else:
            logger.info("Unhandled Sub-Event type {}".format(event["type"]))

        # Always respond
        return "", 200
    logger.error("Unknown event {}".format(payload["type"]))
    return "", 200


"""
class MyApp(Flask):
    def __init__(self):
        # init underlying flask app
        super().__init__(__name__)
        self._logger = logging.getLogger(__name__)
        logging.getLogger('botocore').setLevel(logging.INFO)
        logging.getLogger('boto3').setLevel(logging.INFO)
        logging.getLogger('urllib3').setLevel(logging.INFO)
        logging.getLogger('s3transfer').setLevel(logging.INFO)

        mode = os.environ['PLSNRENV']
        self.config.from_object('settings.' + mode + 'Settings')

        for rc in REQUIRED_CONFIG:
            if rc not in os.environ:
                raise EnvironmentError("Missing {}".format(rc))
            self.config[rc] = os.environ.get(rc)

        self.sc = slack.WebClient(token=self.config["BOT_TOKEN"])

        self.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
        }
        db.init_app(self)


app = MyApp()"""

if __name__ == "__main__":
    # reloader doesn't work with additional threads.
    create_app().run(host="localhost", port=5002, debug=True, use_reloader=False)
    event_loop.call_soon_threadsafe(event_loop.stop)
