# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import logging
import json

from flask import Blueprint, abort, current_app, jsonify, request
import slack

from asyncev import run_async
from otterbot import talk_to_me
from report import (
    open_disturbance_report_modal,
    open_trail_report_modal,
    handle_report_cancel_modal,
    handle_report_submit_modal,
)
from slack_api import get_file_info, get_bot_user_id

api = Blueprint("api", __name__, url_prefix="/")
logger = logging.getLogger("api")


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
    # rrequest = " ".join(request.form["text"].split()).split()
    return (
        jsonify({"response_type": "ephemeral", "text": "Slash commands not supported"}),
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
    if rjson["type"] == "view_submission":
        run_async(current_app.config["EV_MODE"], handle_report_submit_modal, rjson)
        return "", 200
    elif rjson["type"] == "view_closed":
        run_async(current_app.config["EV_MODE"], handle_report_cancel_modal, rjson)
        return "", 200

    elif rjson["type"] == "block_actions":
        # ts = rjson["container"]["message_ts"]
        # trigger_id, response_url
        rid = rjson["actions"][0]["block_id"]
        value = rjson["actions"][0]["value"]
        state = json.dumps({"rid": rid})

        run_async(
            current_app.config["EV_MODE"],
            start_report,
            value,
            rjson["trigger_id"],
            state,
        )
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
    event_id = payload.get("event_id", "")

    # Check for retry. These are really annoying so we simple ignore them!
    retry_num = request.headers.get("X-Slack-Retry-Num", 0)
    retry_why = request.headers.get("X-Slack-Retry-Reason", "")
    if retry_num:
        logger.warning(
            "Ignoring retry event Id {} try {} reason {}".format(
                event_id, retry_num, retry_why
            )
        )
        return "", 200

    if payload["type"] == "url_verification":
        return dict(challenge=payload["challenge"])
    elif payload["type"] == "event_callback":
        event = payload["event"]
        logger.info("Event id {} {}".format(event_id, event))

        if event["type"] == "app_mention":
            # let's chat
            run_async(current_app.config["EV_MODE"], talk_to_me, event_id, event)
        elif event["type"] == "file_created" or event["type"] == "file_shared":
            run_async(current_app.config["EV_MODE"], handle_file, event)
        elif event["type"] == "message":
            subtype = event.get("subtype", "")
            if subtype and subtype != "file_share":
                # ignore
                logger.info("Ignoring message subtype {}".format(subtype))
            elif event["user"] == get_bot_user_id():
                logger.info("Ignoring message - its from me!")
            else:
                # Treat like a mention - seems like this can only be DMs.
                # hack - make it look same as a @mention.
                event["text"] = "DM " + event["text"]
                run_async(current_app.config["EV_MODE"], talk_to_me, event_id, event)
        else:
            logger.info("Ignored Event type: {}".format(event["type"]))

        # Always respond
        return "", 200
    logger.error("Unknown event {}".format(payload["type"]))
    return "", 200


def handle_file(event):
    # This runs async w/o an app context.
    finfo = get_file_info(event["file_id"])
    finfo = finfo["file"]
    logger.info(
        "IGNORING: File info image link {} channels {}".format(
            finfo["url_private"], finfo["channels"]
        )
    )

    """
    Not sure this is a good idea - we have explicit ways to add photos.
    app = asyncev.wapp
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
            post_ephemeral_message(
                event["channel_id"],
                event["user_id"],
                "Retrieving file and grabbing GPS info.. thanks.",
            )
            report.add_photo(app, finfo, matched[0])
    """
    return {}


def start_report(ttype, trigger, state):
    logger.info(
        "Opening modal type {} trigger_id {} state {}".format(ttype, trigger, state)
    )
    if ttype == "trail":
        open_trail_report_modal(trigger, state)
    else:
        open_disturbance_report_modal(trigger, state)
