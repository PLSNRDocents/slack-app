# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import datetime
import logging
import json

from flask import Blueprint, Flask, abort, current_app, jsonify, request
import slack

from asyncev import event_loop
from dbmodel import (
    TRAIL_VALUE_2_DESC,
    TYPE_TRAIL,
    TYPE_DISTURBANCE,
    ISSUES_2_DESC,
    PhotoModel,
    xlate_issues,
)
import image
from otterbot import talk_to_me
import report
from slack_api import get_file_info, post_message, post, send_update

api = Blueprint("api", __name__, url_prefix="/")
logger = logging.getLogger("report")


@api.route("/report", methods=["GET", "POST"])
def top():
    # This handles the /report command
    if not slack.WebClient.validate_slack_signature(
        signing_secret=current_app.config["SIGNING_SECRET"],
        data=request.get_data().decode("utf-8"),
        timestamp=request.headers["X-Slack-Request-Timestamp"],
        signature=request.headers["X-Slack-Signature"],
    ):
        abort(403)

    rtype = request.form["text"].strip()
    if rtype.startswith("delete"):
        # TODO authz
        logger.info(
            "User {} requesting to delete report {}".format(
                request.form["user_id"], rtype
            )
        )
        try:
            _, rid = rtype.split(" ")
            if rid.startswith("TR-") or rid.startswith("DR-"):
                rid = rid[3:]
            # TODO convert to async
            current_app.report.delete(rid)
        except ValueError:
            return (
                jsonify(
                    {
                        "response_type": "ephemeral",
                        "text": "To delete a report: /report delete <report_number>",
                    }
                ),
                200,
            )
        return "", 200

    if rtype.startswith("t"):
        open_trail_report_dialogue(request.form["trigger_id"])
        return "", 200
    elif rtype.startswith("d"):
        open_disturbance_report_dialogue(request.form["trigger_id"])
        return "", 200
    return (
        jsonify(
            {
                "response_type": "ephemeral",
                "text": "Please specify a type of report t(rail) or d(isturbance)",
            }
        ),
        200,
    )


@api.route("/interact", methods=["GET", "POST"])
def submit():
    """ Called from slack for all interactions (dialogs, button, etc). """
    rjson = json.loads(request.form["payload"])
    if rjson["type"] == "dialog_submission":
        event_loop.call_soon_threadsafe(
            current_app.report.create,
            rjson["callback_id"],
            rjson["user"],
            rjson["channel"],
            rjson["submission"],
        )
        send_update(rjson["response_url"], "Thanks for your report.")
        return "", 200

    logger.error("Unhandled type {}".format(rjson["type"]))
    return "", 200


@api.route("/events", methods=["GET", "POST"])
def events():
    payload = request.json

    if payload["type"] == "url_verification":
        return dict(challenge=payload["challenge"])
    elif payload["type"] == "event_callback":
        event = payload["event"]

        if event["type"] == "app_mention":
            # let's chat
            logger.info(
                "App_mention from {} channel {}".format(event["user"], event["channel"])
            )
            talk_to_me(event)
        elif event["type"] == "file_created" or event["type"] == "file_shared":
            logger.info(
                "Event {} from {} channel {}".format(
                    event["type"], event["user_id"], event["channel_id"]
                )
            )
            event_loop.call_soon_threadsafe(
                handle_file, event, current_app._get_current_object()
            )
        else:
            logger.info("Unhandled Sub-Event type {}".format(event["type"]))

        # Always respond
        return "", 200
    logger.error("Unknown event {}".format(payload["type"]))
    return "", 200


def handle_file(event, app: Flask):
    # This runs async w/o an app context.
    finfo = get_file_info(event["file_id"])["file"]
    logger.info(
        "File info image link {} channels {}".format(
            finfo["url_private"], finfo["channels"]
        )
    )

    with app.app_context():
        # Look for existing trail report from user and channel - else - ignore
        matched = []
        reports = app.report.fetch_all(limit=50)

        for r in reports:
            if (
                r.reporter_slack_id == event["user_id"]
                and r.channel == event["channel_id"]
                and (datetime.datetime.utcnow() - r.update_datetime)
                < datetime.timedelta(minutes=15)
            ):
                matched.append(r)
        if len(matched) != 1:
            # Lets make sure we don't spam folks with info..
            logger.warning(
                "No or too many report(s) matches for file user {} channel {}".format(
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

            r = matched[0]
            lat = None
            lon = None
            if not r.gps:
                # fetch image, find GPS coordinates - note that IOS actually strips this
                # so likely we won't find any.
                photo = image.fetch_image(finfo["url_private"])
                exif_data = image.get_exif_data(photo)
                lat, lon = image.get_lat_lon(exif_data)
            photo = PhotoModel(r, slack_file_id=event["file_id"])
            photo.s3_url = finfo["url_private"]  # Not really.

            with app.report.acquire_for_update(r, photo) as lrm:
                # lrm is now a locked for update version of 'r'.
                if lat and lon:
                    r.gps = "{},{}".format(lat, lon)


def open_trail_report_dialogue(trigger):
    trail_options = []
    for n, d in TRAIL_VALUE_2_DESC.items():
        trail_options.append(dict(label=d, value=n))
    valid_trail_issues = ["po", "sign", "ca", "tree", "step", "ot"]
    trail_issues = []
    for n, d in ISSUES_2_DESC.items():
        if n in valid_trail_issues:
            trail_issues.append(dict(label=d, value=n))
    payload = {
        "callback_id": TYPE_TRAIL,
        "title": "Trail Report",
        "submit_label": "Submit",
        "notify_on_cancel": False,
        "state": TYPE_TRAIL,
        "elements": [
            {
                "label": "Which Trail",
                "type": "select",
                "name": "location",
                "options": trail_options,
            },
            {
                "label": "Nearest Cross Trail",
                "type": "select",
                "name": "cross",
                "optional": True,
                "options": trail_options,
            },
            {
                "label": "Issue",
                "type": "select",
                "name": "issues",
                "options": trail_issues,
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

    post("dialog.open", dict(trigger_id=trigger, dialog=payload))


def open_disturbance_report_dialogue(trigger):
    trail_options = []
    for n, d in TRAIL_VALUE_2_DESC.items():
        trail_options.append(dict(label=d, value=n))
    valid_dist_issues = [
        "ot",
        "pin",
        "ott",
        "bird",
        "off",
        "jump",
        "climb",
        "eat",
        "pet",
        "bike",
        "tide",
        "take",
        "evil",
        "drone",
        "air",
        "fish",
    ]
    disturbance_issues = []
    for n, d in ISSUES_2_DESC.items():
        if n in valid_dist_issues:
            disturbance_issues.append(dict(label=d, value=n))
    payload = {
        "callback_id": TYPE_DISTURBANCE,
        "title": "Disturbance Report",
        "submit_label": "Submit",
        "notify_on_cancel": False,
        "state": TYPE_DISTURBANCE,
        "elements": [
            {
                "label": "Which Trail",
                "type": "select",
                "name": "location",
                "options": trail_options,
            },
            {
                "label": "Nearest Cross Trail",
                "type": "select",
                "name": "cross",
                "optional": True,
                "options": trail_options,
            },
            {
                "label": "Disturbance",
                "type": "select",
                "name": "issues",
                "options": disturbance_issues,
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

    post("dialog.open", dict(trigger_id=trigger, dialog=payload))
