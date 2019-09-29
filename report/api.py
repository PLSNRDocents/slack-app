# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import logging
import json

from flask import Blueprint, Flask, abort, current_app, jsonify, request
import slack

from asyncev import event_loop
from dbmodel import TRAIL_VALUE_2_DESC, TYPE_TRAIL, TYPE_DISTURBANCE, ISSUES_2_DESC
from otterbot import talk_to_me
import report
from slack_api import get_file_info, post, post_message, send_update

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

    # remove all extraneous white space and put into list.
    rrequest = " ".join(request.form["text"].split()).split()
    if rrequest[0].startswith("t"):
        open_trail_report_dialogue(request.form["trigger_id"], "")
        return "", 200
    elif rrequest[0].startswith("d"):
        open_disturbance_report_dialogue(request.form["trigger_id"], "")
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
    if not slack.WebClient.validate_slack_signature(
        signing_secret=current_app.config["SIGNING_SECRET"],
        data=request.get_data().decode("utf-8"),
        timestamp=request.headers["X-Slack-Request-Timestamp"],
        signature=request.headers["X-Slack-Signature"],
    ):
        abort(403)

    rjson = json.loads(request.form["payload"])
    if rjson["type"] == "dialog_submission":
        event_loop.call_soon_threadsafe(
            handle_report_submit, current_app._get_current_object(), rjson
        )
        return "", 200
    elif rjson["type"] == "dialog_cancellation":
        # Delete placeholder report
        event_loop.call_soon_threadsafe(
            handle_report_cancel, current_app._get_current_object(), rjson
        )
        return "", 200

    elif rjson["type"] == "block_actions":
        # ts = rjson["container"]["message_ts"]
        # trigger_id, response_url
        rid = rjson["actions"][0]["block_id"]
        state = json.dumps({"ru": rjson["response_url"], "rid": rid})
        value = rjson["actions"][0]["selected_option"]["value"]
        if value == "trail":
            open_trail_report_dialogue(rjson["trigger_id"], state)
        else:
            open_disturbance_report_dialogue(rjson["trigger_id"], state)
        return "", 200

    logger.error("Unhandled type {}: {}".format(rjson["type"], rjson))
    return "", 200


@api.route("/events", methods=["GET", "POST"])
def events():
    if not slack.WebClient.validate_slack_signature(
        signing_secret=current_app.config["SIGNING_SECRET"],
        data=request.get_data().decode("utf-8"),
        timestamp=request.headers["X-Slack-Request-Timestamp"],
        signature=request.headers["X-Slack-Signature"],
    ):
        abort(403)

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
            event_loop.call_soon_threadsafe(
                talk_to_me, event, current_app._get_current_object()
            )
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

    """
    Not sure this is a good idea - we have explicit ways to add photos.
    with app.app_context():
        # Look for existing trail report from user and channel - else - ignore
        matched = []
        reports = app.report.fetch_all(limit=50)

        for r in reports:
            if (
                r.reporter_slack_id == event["user_id"]
                and r.channel == event["channel_id"]
                and (datetime.datetime.utcnow() - r.update_datetime)
                < datetime.timedelta(minutes=5)
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
            report.add_photo(app, finfo, matched[0])
    """


def open_trail_report_dialogue(trigger, state):
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
        "notify_on_cancel": True,
        "state": state,
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


def open_disturbance_report_dialogue(trigger, state):
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
        "notify_on_cancel": True,
        "state": state,
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


def handle_report_submit(app, rjson):
    # Called on dialog submission.
    with app.app_context():
        if rjson["state"]:
            # created via start_new / @xx new report
            # state is json containing report id and response url
            state = json.loads(rjson["state"])
            nr = app.report.get(state["rid"])
            if not nr:
                # hmm - what happened to the report
                post_message(
                    rjson["channel"]["id"],
                    rjson["user"]["id"],
                    "Couldn't find report {}".format(state["rid"]),
                )
                return
            logger.info("Finish report {}".format(nr.id))
            nr = app.report.complete(
                nr,
                rjson["callback_id"],
                rjson["user"],
                rjson["channel"],
                rjson["submission"],
            )
            # inform user - and replace initial message
            send_update(
                state["ru"],
                "Report [{}] saved.".format(report.Report.id_to_name(nr)),
                replace_original=True,
            )
        else:
            nr = app.report.create(
                rjson["callback_id"],
                rjson["user"],
                rjson["channel"],
                rjson["submission"],
            )
            # Inform user
            post_message(
                rjson["channel"]["id"],
                rjson["user"]["id"],
                "Report [{}] saved.".format(report.Report.id_to_name(nr)),
            )


def handle_report_cancel(app, rjson):
    # Called on dialog cancel.
    with app.app_context():
        if rjson["state"]:
            # created via start_new / @xx new report
            # state is json containing report id and response url
            state = json.loads(rjson["state"])
            logger.info("Cancelled - deleting report {}".format(state["rid"]))
            app.report.delete(state["rid"])
            send_update(state["ru"], "", delete_original=True)
